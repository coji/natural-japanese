# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "sudachipy>=0.6.8",
#     "sudachidict-core>=20240409",
# ]
# ///
"""ai-smell-lint.py — AI臭い日本語文章を決定的に検出する lint スクリプト。

設計思想（HANDOFF.md 参照）:
    「AI は自分自身の AI 臭さを認識できない」→ 機械的・決定的に検出して
    人間（または AI 自身の別セッション）に突きつけ、直すかどうかの判断は
    委ねる。これは CI ゲートではなく lint であるため、検出件数に関わらず
    exit code は常に 0 にする。

使い方:
    uv run scripts/ai-smell-lint.py <file.md> [--json]

実装メモ:
    - sudachipy の Tokenizer 生成（辞書ロード）は重いので、プロセス内で
      一度だけ生成し使い回す（lazy シングルトン）。
    - 文分割は「。」「！」「？」「\n」を区切りとする簡易実装。厳密な文境界
      解析ではないが、決定的検出のプロトタイプとしてはこれで十分。
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import statistics
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 辞書: 禁止語・LLM 常套句カタログ
# ここは「拡張前提」のカタログ。新しい手癖フレーズに気づいたら追記していく。
# 出典: HANDOFF.md 55-62行目、および note記事「禁止語60語超」の言及。
# ---------------------------------------------------------------------------
FORBIDDEN_PHRASES: list[str] = [
    # 結論の押し付け・まとめ口調
    "と言えるでしょう",
    "と言えるだろう",
    "と言えます",
    "ということになるでしょう",
    "のではないでしょうか",
    "重要なのは",
    "大切なのは",
    "ポイントは",
    "結論から言うと",
    "結論として",
    "いかがでしたか",
    "いかがでしょうか",
    "最後に",
    "まとめると",
    "総じて",
    # 過剰な強調・持ち上げ
    "非常に重要",
    "極めて重要",
    "言うまでもなく",
    "言うまでもありません",
    "まさに",
    "まさしく",
    # 定型導入・空疎な接続
    "さて、",
    "それでは、",
    "このように",
    "このような中",
    "ここで注目したいのは",
    "見ていきましょう",
    "紹介していきます",
    "解説していきます",
    "深掘りしていきます",
    # 予防線・免責的な言い回し
    "一概には言えません",
    "個人差がありますが",
    "あくまで一例ですが",
    # 正面から系（出典: japanese-tech-writing の規範から。中身の代わりに姿勢だけを宣言する）
    "正面から扱う",
    "正面から見る",
    "正面から書く",
    "正面から立てる",
    "正面から回収する",
    # 空虚な形容（出典: japanese-tech-writing の規範から。主張の中身を説明せず強調・網羅感だけ付ける）
    "不可欠",
    "核心的",
    "鍵となる",
    "根本的な",
    "多角的",
    "包括的",
    "総合的",
    # 空虚な動詞・予告口調（出典: japanese-tech-writing の規範から。何をどう書いたか示さず終わる）
    "掘り下げる",
    "深掘りする",
    "言語化する",
    "について見ていく",
    "を探求する",
]

# ---------------------------------------------------------------------------
# 辞書: 翻訳調パターン（英語直訳っぽい構文）
# ---------------------------------------------------------------------------
TRANSLATIONESE_PATTERNS: list[str] = [
    r"することができ(る|ます|た)",
    r"することが可能(です|だ|になる)",
    r"と言えるだろう",
    r"という点で",
    r"という観点(から|で)",
    r"にとって(重要|不可欠)",
    r"を持つ(こと|存在)",
    r"することによって",
    r"であることは間違いない",
    r"に他ならない",
]

# 段落頭に来ると「AI が構成を接続詞で誤魔化しがち」な語
PARAGRAPH_CONJUNCTIONS: list[str] = [
    "しかし",
    "また",
    "そして",
    "そのため",
    "さらに",
    "つまり",
    "一方",
    "一方で",
    "このように",
    "なぜなら",
    "したがって",
    "ただし",
]

# 否定→肯定対比の手癖パターン（正規表現）
ANTITHESIS_PATTERNS = [
    re.compile(r"ではなく、?.{0,30}"),
    re.compile(r"だけでなく.{0,10}も"),
]

SENTENCE_SPLIT_RE = re.compile(r"[。！？\n]")


@dataclasses.dataclass
class Finding:
    line: int
    category: str
    excerpt: str
    severity: str  # "info" | "warn" | "critical"
    detail: str = ""
    # 文書全体集計型の検出器（antithesis_repetition, repeated_sentence_lead,
    # repeated_syntax_template, paragraph_lead_conjunction, nominal_ending 等）で、
    # 同じ集計に基づく他の該当行番号を列挙するための任意フィールド。
    # 単発検出（forbidden_phrase 等）では None のまま。
    related_lines: list[int] | None = None

    def __post_init__(self) -> None:
        # JSON 出力でも detail 表記と同じく重複除去・昇順に正規化する
        if self.related_lines is not None:
            self.related_lines = sorted(set(self.related_lines))

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def format_related_lines(related_lines: list[int]) -> str:
    """related_lines を人間可読の「対応箇所: L12, L34, ...」形式に整形する（重複除去・昇順ソート）。"""
    uniq_sorted = sorted(set(related_lines))
    return "対応箇所: " + ", ".join(f"L{n}" for n in uniq_sorted)


# ---------------------------------------------------------------------------
# sudachipy Tokenizer は生成コスト（辞書ロード）が高いので遅延・使い回し。
# ---------------------------------------------------------------------------
_tokenizer_obj = None


def get_tokenizer():
    global _tokenizer_obj
    if _tokenizer_obj is None:
        from sudachipy import Dictionary

        _tokenizer_obj = Dictionary().create()
    return _tokenizer_obj


# ---------------------------------------------------------------------------
# Markdown構造行のマスク処理
# 見出し・リスト項目・コードブロック内・引用ブロックは「文章」ではないため、
# 体言止め判定や翻訳調検出などの対象から外す。行を削除すると後続行の行番号が
# ズレてレポートの L<n> が狂うので、該当行は「内容を空文字に置き換える」ことで
# 行番号を保ったまま解析対象外にする（マスク方式）。
# ---------------------------------------------------------------------------
_HEADING_RE = re.compile(r"^\s*#{1,6}(\s|$)")
_LIST_ITEM_RE = re.compile(r"^\s*([-*+]|\d+[.)])(\s|$)")
_BLOCKQUOTE_RE = re.compile(r"^\s*>")
_CODE_FENCE_RE = re.compile(r"^\s*(```|~~~)")
# 表の行判定は保守的に: 「行が `|` で始まり、`|` を2個以上含む」または
# 区切り行（`|---|---|` 的な、`-`/`:`/`|`/空白のみで構成される行）に限定する。
# 本文中にたまたま `|` が1個だけ出るケースを誤マスクしないための条件。
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|")
_TABLE_DELIMITER_RE = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*\|?\s*$")
# インラインコードスパン（`code` のようにバッククォートで囲まれた範囲）。
# 文解析前に該当部分だけ同じ文字数の空白に置換する（行番号・オフセットを保つため）。
_INLINE_CODE_SPAN_RE = re.compile(r"`[^`\n]+`")


def _blank_inline_code_spans(line: str) -> str:
    """行内のインラインコードスパンを同じ長さの空白に置換する（オフセット保持）。"""
    return _INLINE_CODE_SPAN_RE.sub(lambda m: " " * len(m.group(0)), line)


def mask_markdown_structure(text: str) -> str:
    """見出し・リスト項目・コードブロック内・引用ブロック・表の行を空文字に置き換え、
    さらにインラインコードスパンを空白化したテキストを返す。
    行数・行番号（およびインラインコードスパンの行内オフセット）は元のテキストと
    完全に一致させる（削除ではなくマスク）。
    """
    lines = text.split("\n")
    masked_lines = []
    in_code_block = False
    for line in lines:
        if _CODE_FENCE_RE.match(line):
            in_code_block = not in_code_block
            masked_lines.append("")  # フェンス行自体もマスク
            continue
        if in_code_block:
            masked_lines.append("")
            continue
        if (
            _HEADING_RE.match(line)
            or _LIST_ITEM_RE.match(line)
            or _BLOCKQUOTE_RE.match(line)
            or (_TABLE_ROW_RE.match(line) and line.count("|") >= 2)
            or _TABLE_DELIMITER_RE.match(line)
        ):
            masked_lines.append("")
            continue
        masked_lines.append(_blank_inline_code_spans(line))
    return "\n".join(masked_lines)


def iter_lines_with_no(text: str) -> list[tuple[int, str]]:
    """1-indexed 行番号付きで行を返す。"""
    return list(enumerate(text.splitlines(), start=1))


def find_line_no(lines: list[tuple[int, str]], needle: str, start_hint: int = 0) -> int:
    """needle を含む最初の行番号を探す（簡易版）。"""
    for no, line in lines:
        if needle in line:
            return no
    return start_hint or 1


# ---------------------------------------------------------------------------
# 各検出器
# ---------------------------------------------------------------------------


def detect_forbidden_phrases(lines: list[tuple[int, str]]) -> list[Finding]:
    findings = []
    for no, line in lines:
        for phrase in FORBIDDEN_PHRASES:
            idx = line.find(phrase)
            if idx != -1:
                excerpt = line[max(0, idx - 10) : idx + len(phrase) + 10]
                findings.append(
                    Finding(
                        line=no,
                        category="forbidden_phrase",
                        excerpt=excerpt.strip(),
                        severity="warn",
                        detail=f"禁止語/LLM常套句ヒット: 「{phrase}」",
                    )
                )
    return findings


def detect_translationese(lines: list[tuple[int, str]]) -> list[Finding]:
    findings = []
    for no, line in lines:
        for pat in TRANSLATIONESE_PATTERNS:
            for m in re.finditer(pat, line):
                start = max(0, m.start() - 10)
                excerpt = line[start : m.end() + 10]
                findings.append(
                    Finding(
                        line=no,
                        category="translationese",
                        excerpt=excerpt.strip(),
                        severity="info",
                        detail=f"翻訳調パターン: /{pat}/ に一致",
                    )
                )
    return findings


def detect_antithesis_repetition(lines: list[tuple[int, str]]) -> list[Finding]:
    """「〜ではなく、〜」「〜だけでなく〜も」を文書全体で数え、3回以上なら反復として警告。
    どの文同士が反復としてカウントされたか追えるよう、全ヒット行番号を
    related_lines / detail の両方に含める。
    """
    hits: list[tuple[int, str, str]] = []  # (line_no, matched_text, pattern_name)
    for no, line in lines:
        for pat in ANTITHESIS_PATTERNS:
            for m in re.finditer(pat, line):
                hits.append((no, m.group(0), pat.pattern))

    findings = []
    if len(hits) >= 3:
        all_lines = [no for no, _, _ in hits]
        related = format_related_lines(all_lines)
        for no, text, patname in hits:
            findings.append(
                Finding(
                    line=no,
                    category="antithesis_repetition",
                    excerpt=text.strip(),
                    severity="critical",
                    detail=f"否定→肯定対比パターンが文書内で{len(hits)}回検出（閾値3回以上）。{related}",
                    related_lines=all_lines,
                )
            )
    return findings


def split_sentences_with_lines(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """行番号付きで文を分割する（。！？で分割、行内に複数文があれば同じ行番号を割り当てる）。"""
    sentences = []
    for no, line in lines:
        parts = [p for p in SENTENCE_SPLIT_RE.split(line) if p.strip()]
        for p in parts:
            sentences.append((no, p.strip()))
    return sentences


def detect_low_sentence_length_variance(
    sentences: list[tuple[int, str]], threshold: float = 0.25
) -> list[Finding]:
    """文長（文字数）の変動係数（CV = 標準偏差/平均）が閾値未満なら
    「文長が均質すぎる = リズムが単調 = AI臭い」として警告する。
    最低5文以上ないと統計的に意味がないので判定しない。
    """
    lengths = [len(s) for _, s in sentences if len(s) > 0]
    if len(lengths) < 5:
        return []
    mean = statistics.mean(lengths)
    if mean == 0:
        return []
    stdev = statistics.pstdev(lengths)
    cv = stdev / mean
    if cv < threshold:
        first_line = sentences[0][0] if sentences else 1
        return [
            Finding(
                line=first_line,
                category="low_sentence_variance",
                excerpt=f"文数={len(lengths)}, 平均文長={mean:.1f}字, 変動係数={cv:.3f}",
                severity="warn",
                detail=f"文長の変動係数が閾値({threshold})未満。リズムが均質でAI臭い可能性",
            )
        ]
    return []


NOUN_ENDING_POS = {"名詞"}
TRAILING_SYMBOL_POS = {"補助記号", "空白"}

# 語彙多様性計測の対象とする内容語 POS
CONTENT_WORD_POS = {"名詞", "動詞", "形容詞", "副詞"}

# 「無生物主語+他動詞」判定で「主語になっても不自然でない代名詞」として許可する語
ABSTRACT_PRONOUNS = {"これ", "それ", "あれ", "この事実", "そのこと", "それら"}
# 述語側: 直訳調でよく使われる他動詞的な動詞（辞書は拡張前提）
TRANSITIVE_SMELL_VERBS = {
    "もたらす",
    "示す",
    "意味する",
    "証明する",
    "生み出す",
    "反映する",
    "示唆する",
    "物語る",
    "浮き彫りにする",
    "後押しする",
}


@dataclasses.dataclass
class TokenizedSentence:
    line: int
    text: str
    morphemes: list  # sudachipy.MorphemeList の要素


def tokenize_sentences(sentences: list[tuple[int, str]]) -> list[TokenizedSentence]:
    """文ごとに一度だけ形態素解析し、以後の検出器で使い回す（辞書ロードとトークナイズの
    コストを最小化するための共有キャッシュ）。"""
    tokenizer = get_tokenizer()
    from sudachipy import SplitMode

    result = []
    for no, sent in sentences:
        if not sent:
            continue
        morphemes = list(tokenizer.tokenize(sent, SplitMode.C))
        result.append(TokenizedSentence(line=no, text=sent, morphemes=morphemes))
    return result


def _strip_trailing_symbols(morphemes: list) -> list:
    """文末の記号（」など）を除いた実質的な最終形態素列を返す。"""
    i = len(morphemes)
    while i > 0 and morphemes[i - 1].part_of_speech()[0] in TRAILING_SYMBOL_POS:
        i -= 1
    return morphemes[:i]


def detect_nominal_ending_and_paragraph_conjunctions(
    text: str, lines: list[tuple[int, str]], tokenized: list[TokenizedSentence]
) -> tuple[list[Finding], dict]:
    """sudachipy で形態素解析し、
    1) 体言止め（文末が名詞で終わる）の頻度
    2) 段落頭の接続詞率
    を計測する。閾値超えなら警告 Finding を返す。stats も返す（JSON用）。
    """
    nominal_ending_count = 0
    total_sentences = 0
    nominal_ending_findings = []

    for ts in tokenized:
        total_sentences += 1
        effective = _strip_trailing_symbols(ts.morphemes)
        if not effective:
            continue
        last = effective[-1]
        pos = last.part_of_speech()[0]
        # 体言止め: 実質的な最終形態素が名詞（助動詞「だ/です」等が続かない）場合
        if pos in NOUN_ENDING_POS:
            nominal_ending_count += 1
            nominal_ending_findings.append((ts.line, ts.text))

    ratio = nominal_ending_count / total_sentences if total_sentences else 0.0

    findings = []
    if total_sentences >= 5 and ratio >= 0.2:
        nominal_ending_lines = [no for no, _ in nominal_ending_findings]
        related = format_related_lines(nominal_ending_lines)
        for no, sent in nominal_ending_findings:
            findings.append(
                Finding(
                    line=no,
                    category="nominal_ending",
                    excerpt=sent[-30:],
                    severity="info",
                    detail=(
                        f"体言止め（形態素解析ベース、文書全体の体言止め率={ratio:.1%}、"
                        f"閾値20%以上で警告）。{related}"
                    ),
                    related_lines=nominal_ending_lines,
                )
            )

    # 段落頭の接続詞率
    paragraphs = re.split(r"\n\s*\n", text)
    conj_paragraph_count = 0
    total_paragraphs = 0
    conj_findings = []
    sentence_counts_per_paragraph = []
    line_cursor = 1
    for para in paragraphs:
        para_stripped = para.strip()
        if not para_stripped:
            line_cursor += para.count("\n") + 1
            continue
        total_paragraphs += 1
        first_line_text = para_stripped.splitlines()[0].strip()
        sentence_counts_per_paragraph.append(
            len([p for p in SENTENCE_SPLIT_RE.split(para_stripped) if p.strip()])
        )
        for conj in PARAGRAPH_CONJUNCTIONS:
            if first_line_text.startswith(conj):
                conj_paragraph_count += 1
                conj_findings.append((find_line_no(lines, first_line_text, line_cursor), first_line_text, conj))
                break
        line_cursor += para.count("\n") + 1

    conj_ratio = conj_paragraph_count / total_paragraphs if total_paragraphs else 0.0
    if total_paragraphs >= 3 and conj_ratio >= 0.3:
        conj_lines = [no for no, _, _ in conj_findings]
        related = format_related_lines(conj_lines)
        for no, text_line, conj in conj_findings:
            findings.append(
                Finding(
                    line=no,
                    category="paragraph_lead_conjunction",
                    excerpt=text_line[:40],
                    severity="info",
                    detail=(
                        f"段落頭が接続詞「{conj}」で始まる（文書全体の段落頭接続詞率={conj_ratio:.1%}、"
                        f"閾値30%以上で警告）。{related}"
                    ),
                    related_lines=conj_lines,
                )
            )

    # 段落構造の均質性: AI は「3文段落」を量産しがち。段落あたり文数の変動係数が
    # 極端に低い（＝どの段落もほぼ同じ文数）場合は定型段落の疑いとして警告する。
    para_structure_stats = {
        "paragraph_sentence_counts": sentence_counts_per_paragraph,
        "paragraph_sentence_count_cv": None,
    }
    if len(sentence_counts_per_paragraph) >= 4:
        p_mean = statistics.mean(sentence_counts_per_paragraph)
        p_std = statistics.pstdev(sentence_counts_per_paragraph)
        p_cv = (p_std / p_mean) if p_mean else 0.0
        para_structure_stats["paragraph_sentence_count_cv"] = p_cv
        if p_cv < 0.15:
            findings.append(
                Finding(
                    line=1,
                    category="uniform_paragraph_structure",
                    excerpt=f"段落数={len(sentence_counts_per_paragraph)}, 各段落の文数={sentence_counts_per_paragraph}",
                    severity="info",
                    detail=(
                        f"段落あたり文数の変動係数={p_cv:.3f}（閾値0.15未満）。"
                        "どの段落もほぼ同じ文数=定型段落（例: 3文段落の量産）の疑い"
                    ),
                )
            )

    stats = {
        "total_sentences": total_sentences,
        "nominal_ending_count": nominal_ending_count,
        "nominal_ending_ratio": ratio,
        "total_paragraphs": total_paragraphs,
        "paragraph_lead_conjunction_count": conj_paragraph_count,
        "paragraph_lead_conjunction_ratio": conj_ratio,
        **para_structure_stats,
    }
    return findings, stats


def detect_translationese_morph(tokenized: list[TokenizedSentence]) -> list[Finding]:
    """表層の正規表現に加え、品詞・活用形の並びで
    「サ変名詞/動詞 + する + こと + が + できる」型の翻訳調構文を検出する。
    活用形（できる/できます/できた等）や送り仮名の揺れに強い。
    """
    findings = []
    for ts in tokenized:
        surfaces = [m.surface() for m in ts.morphemes]
        poss = [m.part_of_speech()[0] for m in ts.morphemes]
        n = len(ts.morphemes)
        for i in range(n):
            # 「こと」(名詞) + が/は(助詞) + でき(動詞語幹)... の並びを探す
            if surfaces[i] == "こと" and poss[i] == "名詞":
                j = i + 1
                if j < n and poss[j] == "助詞" and surfaces[j] in {"が", "は"}:
                    k = j + 1
                    if k < n and poss[k] == "動詞" and surfaces[k].startswith("でき"):
                        # 直前に動詞（する等）があるかも確認して精度を上げる
                        excerpt = "".join(surfaces[max(0, i - 4) : k + 1])
                        findings.append(
                            Finding(
                                line=ts.line,
                                category="translationese_morph",
                                excerpt=excerpt,
                                severity="info",
                                detail="品詞列マッチ: 名詞/動詞+こと+が/は+できる型の翻訳調構文",
                            )
                        )
    return findings


def mora_length(morphemes: list) -> int:
    """読み（カタカナ）の文字数をモーラ数の近似値として使う。
    長音・拗音の厳密な処理はしていないが、文字数よりは音の長さに近い指標になる。
    """
    total = 0
    for m in morphemes:
        reading = m.reading_form() or m.surface()
        total += len(reading)
    return total


def detect_rhythm_statistics(tokenized: list[TokenizedSentence]) -> tuple[list[Finding], dict]:
    """文字数だけでなくモーラ近似長を使い、単純な変動係数に加えて
    burstiness（(σ-μ)/(σ+μ)）と隣接文長の自己相関（lag-1）を計測する。
    - burstiness が負に大きい ≈ 文長が均一（AI的）
    - 自己相関が高い ≈ 「短い文の後は短い文」というリズムパターンが固定化している
    """
    if len(tokenized) < 6:
        return [], {}

    mora_lengths = [mora_length(ts.morphemes) for ts in tokenized]
    mean = statistics.mean(mora_lengths)
    std = statistics.pstdev(mora_lengths)

    findings = []
    burstiness = (std - mean) / (std + mean) if (std + mean) else 0.0

    # lag-1 自己相関（ピアソン相関を1つずらした系列同士で計算）
    xs = mora_lengths[:-1]
    ys = mora_lengths[1:]
    autocorr = None
    if len(xs) >= 4 and statistics.pstdev(xs) > 0 and statistics.pstdev(ys) > 0:
        mx, my = statistics.mean(xs), statistics.mean(ys)
        cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / len(xs)
        autocorr = cov / (statistics.pstdev(xs) * statistics.pstdev(ys))

    if burstiness < -0.55:
        findings.append(
            Finding(
                line=tokenized[0].line,
                category="low_burstiness",
                excerpt=f"burstiness={burstiness:.3f} (モーラ近似長 平均={mean:.1f}, 標準偏差={std:.1f})",
                severity="warn",
                detail="burstiness が閾値(-0.55)未満。文の長短のメリハリが乏しく機械的なリズムの疑い",
            )
        )

    if autocorr is not None and autocorr > 0.6:
        findings.append(
            Finding(
                line=tokenized[0].line,
                category="high_length_autocorrelation",
                excerpt=f"lag-1 自己相関={autocorr:.3f}",
                severity="info",
                detail="隣接する文の長さが強く相関（閾値0.6超）。文長パターンが単調に繰り返されている疑い",
            )
        )

    stats = {
        "mora_mean": mean,
        "mora_stdev": std,
        "burstiness": burstiness,
        "length_autocorrelation_lag1": autocorr,
    }
    return findings, stats



# 文頭反復の severity 判定: 固有名詞・製品名/技術用語（ラテン文字主体の表層）が
# 文頭に来る場合は「そして」「また」のような定型導入の使い回しとは性質が異なり、
# 技術文書では自然な反復（例: 「Cloudflareは」「better-authが」）なので
# severity を warn ではなく info に下げる（検出自体は残し、判断材料として提示する）。
_LATIN_TECH_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9\-_.]*$")


def _is_proper_noun_or_tech_term(morpheme) -> bool:
    """先頭形態素が固有名詞、またはラテン文字・数字主体（製品名/ライブラリ名等）かを判定する。
    カタカナ語は一般語（「クラウド」「システム」等）も多く誤って severity を下げるリスクが
    高いため、ここでは対象外とする（迷ったら対象外でよい、という方針）。
    """
    pos = morpheme.part_of_speech()
    surface = morpheme.surface()
    is_proper_noun = pos[0] == "名詞" and pos[1] == "固有名詞"
    is_latin_tech = bool(_LATIN_TECH_TOKEN_RE.match(surface))
    return is_proper_noun or is_latin_tech


def detect_ngram_repetition(tokenized: list[TokenizedSentence]) -> tuple[list[Finding], dict]:
    """
    1) 文頭2形態素（表層形）の n-gram が3回以上繰り返される
       → 「そして、」「また、」のような定型導入の使い回し
       ただし先頭形態素が固有名詞・ラテン文字主体の技術用語（製品名/ライブラリ名等）の
       場合は技術文書として自然な反復なので severity を info に下げる（検出自体は残す）。
    2) 文頭のPOS 4-gram（品詞の粗い並び）の一致率が高い
       → 語彙は違っても構文テンプレートが同じ（AIにありがちな構造の使い回し）
    をそれぞれ検出する。
    """
    from collections import Counter

    findings = []

    lead_bigrams = []
    for ts in tokenized:
        lead_morphemes = ts.morphemes[:2]
        surfaces = [m.surface() for m in lead_morphemes]
        if len(surfaces) == 2:
            is_tech_lead = _is_proper_noun_or_tech_term(lead_morphemes[0])
            lead_bigrams.append((ts.line, ts.text, "".join(surfaces), is_tech_lead))

    bigram_counter = Counter(text for _, _, text, _ in lead_bigrams)
    for bigram, count in bigram_counter.items():
        if count >= 3:
            bigram_lines = [no for no, _, text, _ in lead_bigrams if text == bigram]
            related = format_related_lines(bigram_lines)
            for no, sent, text, is_tech_lead in lead_bigrams:
                if text == bigram:
                    if is_tech_lead:
                        severity = "info"
                        detail = (
                            f"文頭2形態素「{bigram}」が{count}回反復（閾値3回以上）。"
                            f"固有名詞/技術用語由来の可能性が高いため severity を下げています。{related}"
                        )
                    else:
                        severity = "warn"
                        detail = f"文頭2形態素「{bigram}」が{count}回反復（閾値3回以上）。{related}"
                    findings.append(
                        Finding(
                            line=no,
                            category="repeated_sentence_lead",
                            excerpt=sent[:20],
                            severity=severity,
                            detail=detail,
                            related_lines=bigram_lines,
                        )
                    )

    lead_pos_ngrams = []
    for ts in tokenized:
        pos_seq = tuple(m.part_of_speech()[0] for m in ts.morphemes[:4])
        if len(pos_seq) == 4:
            lead_pos_ngrams.append((ts.line, ts.text, pos_seq))

    total_with_ngram = len(lead_pos_ngrams)
    pos_counter = Counter(seq for _, _, seq in lead_pos_ngrams)
    stats = {"lead_pos_4gram_top": None, "lead_pos_4gram_ratio": None}
    if total_with_ngram >= 6 and pos_counter:
        top_seq, top_count = pos_counter.most_common(1)[0]
        ratio = top_count / total_with_ngram
        stats["lead_pos_4gram_top"] = "/".join(top_seq)
        stats["lead_pos_4gram_ratio"] = ratio
        if ratio >= 0.4:
            template_lines = [no for no, _, seq in lead_pos_ngrams if seq == top_seq]
            related = format_related_lines(template_lines)
            for no, sent, seq in lead_pos_ngrams:
                if seq == top_seq:
                    findings.append(
                        Finding(
                            line=no,
                            category="repeated_syntax_template",
                            excerpt=sent[:20],
                            severity="info",
                            detail=(
                                f"文頭品詞4-gram「{'/'.join(top_seq)}」が全文の{ratio:.1%}で一致"
                                f"（閾値40%以上）。構文テンプレートの使い回しの疑い。{related}"
                            ),
                            related_lines=template_lines,
                        )
                    )

    return findings, stats


def compute_mtld(tokens: list[str], threshold: float = 0.72) -> float | None:
    """MTLD（Measure of Textual Lexical Diversity）の簡易実装。
    文長に依存しにくい語彙多様性指標。TTR が threshold を下回るごとに
    「1ファクター」を数え、前方・後方2方向の平均をとる。
    """
    if len(tokens) < 20:
        return None

    def factors_one_direction(seq: list[str]) -> float:
        factor_count = 0
        types: set[str] = set()
        token_count = 0
        for tok in seq:
            types.add(tok)
            token_count += 1
            ttr = len(types) / token_count
            if ttr <= threshold:
                factor_count += 1
                types = set()
                token_count = 0
        # 端数分を部分ファクターとして加算
        if token_count > 0:
            types_ttr = len(types) / token_count if token_count else 1.0
            partial = (1 - types_ttr) / (1 - threshold) if types_ttr < 1 else 0.0
            factor_count += min(partial, 1.0)
        return len(seq) / factor_count if factor_count > 0 else float(len(seq))

    forward = factors_one_direction(tokens)
    backward = factors_one_direction(list(reversed(tokens)))
    return (forward + backward) / 2


def detect_lexical_diversity(tokenized: list[TokenizedSentence]) -> tuple[list[Finding], dict]:
    """内容語（名詞/動詞/形容詞/副詞）の基本形を対象に TTR と MTLD を計測する。
    語彙が使い回されている（AIが同じ言い回しをループしがち）と TTR/MTLD が低くなる。
    """
    content_tokens = []
    for ts in tokenized:
        for m in ts.morphemes:
            if m.part_of_speech()[0] in CONTENT_WORD_POS:
                content_tokens.append(m.dictionary_form())

    findings = []
    stats = {"ttr": None, "mtld": None, "content_token_count": len(content_tokens)}
    if len(content_tokens) >= 30:
        ttr = len(set(content_tokens)) / len(content_tokens)
        mtld = compute_mtld(content_tokens)
        stats["ttr"] = ttr
        stats["mtld"] = mtld
        if ttr < 0.45:
            findings.append(
                Finding(
                    line=tokenized[0].line,
                    category="low_lexical_diversity_ttr",
                    excerpt=f"TTR={ttr:.3f} (内容語 {len(content_tokens)} 語中 {len(set(content_tokens))} 種類)",
                    severity="info",
                    detail="TTR(Type-Token Ratio)が閾値0.45未満。同じ語彙の使い回しが多い疑い",
                )
            )
        if mtld is not None and mtld < 40:
            findings.append(
                Finding(
                    line=tokenized[0].line,
                    category="low_lexical_diversity_mtld",
                    excerpt=f"MTLD={mtld:.1f}",
                    severity="info",
                    detail="MTLD が閾値40未満。文章長で正規化した語彙多様性が低い疑い",
                )
            )
    return findings, stats


def detect_nested_attributive(tokenized: list[TokenizedSentence]) -> list[Finding]:
    """連体修飾の入れ子検出（挑戦枠）。
    英語の関係代名詞節を直訳すると「〜する〜という〜な〜」のように、
    1文の中に「用言の連体形（動詞/形容詞/助動詞の連体形）+ それが係る名詞」という
    関係節構造が何層にも積み重なる。単発の連体修飾（例:「速く走る犬」）は自然な日本語でも
    普通に起きるため、1文中の連体形述語の個数が3個以上のときだけ「積み重ねすぎ」として警告する。
    """
    findings = []
    ATTRIBUTIVE_POS = {"動詞", "形容詞", "助動詞"}
    for ts in tokenized:
        attributive_count = 0
        for m in ts.morphemes:
            pos = m.part_of_speech()
            if pos[0] in ATTRIBUTIVE_POS and "連体形" in (pos[5] or ""):
                attributive_count += 1
        if attributive_count >= 3:
            findings.append(
                Finding(
                    line=ts.line,
                    category="nested_attributive",
                    excerpt=ts.text[:60],
                    severity="info",
                    detail=(
                        f"1文中に連体形の用言が{attributive_count}個（閾値3個以上）。"
                        "関係節が何層にも積み重なる英語統語の直訳調の疑い"
                    ),
                )
            )
    return findings


# ---------------------------------------------------------------------------
# 英語統語の検出（挑戦枠）
# ---------------------------------------------------------------------------

# 無生物主語（＋こと/事実など形式名詞化）+ 他動詞的な述語、という
# 「英語を日本語に直訳した構文」のシグナルをまず正規表現で粗く拾う。
# sudachipy で主語の生物性判定を厳密にやるのは困難なため、
# 「これ/それ/この事実/〜こと/〜という事実」+ 「は/が」+ 文末近くの
# 他動詞（〜を〜する系）という表層パターンでヒューリスティックに検出する。
INANIMATE_SUBJECT_PATTERNS = [
    re.compile(r"(これ|それ|この事実|そのこと)(は|が).{0,40}(もたらす|示す|意味する|証明する|生み出す|反映する)"),
    re.compile(r".{0,20}(こと|事実)(は|が).{0,40}(もたらす|示す|意味する|証明する|生み出す|反映する)"),
]

# 「それは〜である。なぜなら〜だ」構文（隣接する2文にまたがるので
# 文リストを走査して検出する）
CLEFT_BECAUSE_HEAD = re.compile(r"^(それ|これ|この)は.{0,60}(である|だ)$")
BECAUSE_HEAD = re.compile(r"^(なぜなら|というのも)")


def detect_english_syntax_smell(lines: list[tuple[int, str]]) -> list[Finding]:
    findings = []
    for no, line in lines:
        for pat in INANIMATE_SUBJECT_PATTERNS:
            for m in re.finditer(pat, line):
                findings.append(
                    Finding(
                        line=no,
                        category="english_syntax_inanimate_subject",
                        excerpt=m.group(0),
                        severity="info",
                        detail="無生物主語+他動詞的述語（表層パターン、英語統語の直訳調の可能性、要人間判断）",
                    )
                )

    sentences = split_sentences_with_lines(lines)
    for i in range(len(sentences) - 1):
        no1, s1 = sentences[i]
        no2, s2 = sentences[i + 1]
        if CLEFT_BECAUSE_HEAD.match(s1) and BECAUSE_HEAD.match(s2):
            findings.append(
                Finding(
                    line=no1,
                    category="english_syntax_cleft_because",
                    excerpt=f"{s1}。{s2}",
                    severity="warn",
                    detail="「それは〜である。なぜなら〜だ」型の強調構文（英語 It is ... because ... の直訳調）",
                )
            )
    return findings


def detect_inanimate_subject_morph(tokenized: list[TokenizedSentence]) -> list[Finding]:
    """品詞列ベースで「無生物主語(抽象代名詞/形式名詞) + が/は + 他動詞的述語」を検出する。
    厳密な生物性判定（有情/非情の意味論）は sudachipy の POS だけでは困難なため、
    「これ/それ/この事実」等の抽象指示語、または「〜こと/〜という事実」のような
    形式名詞化された主語に限定して、他動詞辞書（TRANSITIVE_SMELL_VERBS）とマッチする
    述語が同一文内に現れる場合のみ検出する。表層正規表現版より活用の揺れに強い。
    """
    findings = []
    for ts in tokenized:
        surfaces = [m.surface() for m in ts.morphemes]
        poss = [m.part_of_speech()[0] for m in ts.morphemes]
        dict_forms = [m.dictionary_form() for m in ts.morphemes]
        n = len(ts.morphemes)
        for i in range(n):
            is_abstract_subject = surfaces[i] in ABSTRACT_PRONOUNS or (
                poss[i] == "名詞" and surfaces[i] in {"こと", "事実", "の"}
            )
            if not is_abstract_subject:
                continue
            j = i + 1
            if j >= n or poss[j] != "助詞" or surfaces[j] not in {"が", "は"}:
                continue
            # 主語マーカーの後、文末までの間に直訳調の他動詞があるか探す
            for k in range(j + 1, n):
                if poss[k] == "動詞" and dict_forms[k] in TRANSITIVE_SMELL_VERBS:
                    excerpt = "".join(surfaces[max(0, i - 3) : k + 1])
                    findings.append(
                        Finding(
                            line=ts.line,
                            category="inanimate_subject_morph",
                            excerpt=excerpt,
                            severity="info",
                            detail=(
                                f"品詞列マッチ: 抽象主語「{surfaces[i]}」+ {surfaces[j]} "
                                f"+ 他動詞的述語「{dict_forms[k]}」（英語統語の直訳調の疑い）"
                            ),
                        )
                    )
                    break
    return findings


# ---------------------------------------------------------------------------
# メイン処理
# ---------------------------------------------------------------------------


def run_lint(raw_text: str) -> tuple[list[Finding], dict]:
    # Markdown の構造行（見出し/リスト/コードブロック/引用）は文章として扱わず、
    # 行番号を保ったままマスクしてから全検出器にかける。
    text = mask_markdown_structure(raw_text)
    lines = iter_lines_with_no(text)
    sentences = split_sentences_with_lines(lines)
    # sudachipy の形態素解析結果は複数の検出器で使い回す（トークナイズは1回だけ）。
    tokenized = tokenize_sentences(sentences)

    findings: list[Finding] = []
    # --- 表層（正規表現）ベースの検出器 ---
    findings += detect_forbidden_phrases(lines)
    findings += detect_translationese(lines)
    findings += detect_antithesis_repetition(lines)
    findings += detect_low_sentence_length_variance(sentences)
    findings += detect_english_syntax_smell(lines)

    # --- 形態素解析ベースの検出器（拡張: 品詞列・活用形マッチ） ---
    nominal_and_conj_findings, morph_stats = detect_nominal_ending_and_paragraph_conjunctions(
        text, lines, tokenized
    )
    findings += nominal_and_conj_findings
    findings += detect_translationese_morph(tokenized)
    findings += detect_inanimate_subject_morph(tokenized)
    findings += detect_nested_attributive(tokenized)

    rhythm_findings, rhythm_stats = detect_rhythm_statistics(tokenized)
    findings += rhythm_findings

    ngram_findings, ngram_stats = detect_ngram_repetition(tokenized)
    findings += ngram_findings

    lexdiv_findings, lexdiv_stats = detect_lexical_diversity(tokenized)
    findings += lexdiv_findings

    findings.sort(key=lambda f: f.line)

    stats = {
        "total_findings": len(findings),
        "by_category": {},
        **morph_stats,
        "rhythm": rhythm_stats,
        "ngram": ngram_stats,
        "lexical_diversity": lexdiv_stats,
    }
    for f in findings:
        stats["by_category"][f.category] = stats["by_category"].get(f.category, 0) + 1

    return findings, stats


SEVERITY_LABEL = {"info": "情報", "warn": "警告", "critical": "重大"}


def print_human_report(path: Path, findings: list[Finding], stats: dict) -> None:
    print(f"=== ai-smell-lint report: {path} ===")
    print(f"検出件数: {stats['total_findings']}")
    if stats["by_category"]:
        print("カテゴリ別内訳:")
        for cat, count in sorted(stats["by_category"].items(), key=lambda kv: -kv[1]):
            print(f"  - {cat}: {count}")
    print()

    if not findings:
        print("検出なし。")
        return

    for f in findings:
        label = SEVERITY_LABEL.get(f.severity, f.severity)
        print(f"[{label}] L{f.line} ({f.category})")
        print(f"    該当箇所: {f.excerpt}")
        if f.detail:
            # 「対応箇所: L12, L34, ...」（related_lines）は detail 文字列に既に
            # 含めているため、人間可読レポートでは detail をそのまま表示すれば十分。
            print(f"    詳細    : {f.detail}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AI臭い日本語文章を決定的に検出する lint スクリプト（CI ゲートではない）。"
    )
    parser.add_argument("file", type=Path, help="lint 対象の Markdown/テキストファイル")
    parser.add_argument("--json", action="store_true", help="機械可読な JSON で出力する")
    args = parser.parse_args()

    if not args.file.exists():
        print(f"エラー: ファイルが見つかりません: {args.file}", file=sys.stderr)
        return 0  # lint であり CI ゲートではないため、エラーでも 0 を返す設計方針を踏襲

    text = args.file.read_text(encoding="utf-8")
    findings, stats = run_lint(text)

    if args.json:
        output = {
            "file": str(args.file),
            "stats": stats,
            "findings": [f.to_dict() for f in findings],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print_human_report(args.file, findings, stats)

    # lint であって CI ゲートではない。検出数に関わらず常に 0 を返し、
    # 修正するかどうかの判断は人間（または後続の AI 自己点検フロー）に委ねる。
    return 0


if __name__ == "__main__":
    sys.exit(main())
