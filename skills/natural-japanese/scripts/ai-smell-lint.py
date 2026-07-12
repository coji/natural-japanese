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
    ただし、これは「文章の中身」に関する判断を保留するという意味であり、
    ファイルが読めない・存在しない・ディレクトリが指定された等の
    「そもそも lint を実行できない」入力エラーとは区別する。
    入力エラーの場合はエラーメッセージを表示し、exit code 1 で終了する。

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
    # --baseline 比較を行ったときだけ "new" | "persisting" にセットされる
    # （比較しない通常実行では None のまま。to_dict() で省く）。
    status: str | None = None

    def __post_init__(self) -> None:
        # JSON 出力でも detail 表記と同じく重複除去・昇順に正規化する
        if self.related_lines is not None:
            self.related_lines = sorted(set(self.related_lines))

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        # --baseline を使わない通常実行では status は常に None なので、
        # JSON 出力のフィールド構成を従来どおりに保つためキー自体を省く
        # （--baseline なしの挙動は完全に不変、という要件のため）。
        if d.get("status") is None:
            d.pop("status", None)
        return d


def format_related_lines(related_lines: list[int]) -> str:
    """related_lines を人間可読の「対応箇所: L12, L34, ...」形式に整形する（重複除去・昇順ソート）。"""
    uniq_sorted = sorted(set(related_lines))
    return "対応箇所: " + ", ".join(f"L{n}" for n in uniq_sorted)


# ---------------------------------------------------------------------------
# --baseline 差分モード
#
# スキルの利用フローは「lint → 台帳に直した/残すを仕分け → 修正 → 再lint →
# 新規findingが出なくなるまで繰り返す」という収束駆動ループになっている。
# ループのたびに全件を目視で見比べるのは負担が大きいので、前回の --json 出力
# （baseline）と今回の結果を比較し、resolved（解消）/ new（新規）/
# persisting（継続）に分類する。
#
# 同一性キーの設計判断:
#   行番号は修正のたびに増減してズレるため、キーに含めない
#   （同じ指摘でも直した箇所より後ろの行が繰り上がるだけで「新規」扱いに
#   なってしまう）。excerpt は形態素境界のわずかな変化や、直した箇所の
#   前後の空白差などで完全一致しなくなることがあるため、正規化
#   （空白除去）した上で先頭 N 文字の前方一致とする。カテゴリ名は
#   検出器の種類そのものなので、そのまま等価比較に使う。
#   これは完全に正確な同一性判定ではないが、実装が単純で、
#   「同じ場所・同じ理由の指摘かどうか」の近似としては十分安定する。
# ---------------------------------------------------------------------------
_BASELINE_KEY_EXCERPT_PREFIX_LEN = 20

# 文書全体の統計量（burstiness・変動係数・TTR/MTLD 等）を excerpt に直接埋め込んでいる
# カテゴリ。これらは1文書につき高々1件しか出ない「集計そのもの」の finding であり、
# excerpt が「burstiness=-0.623 (...)」のように計算結果の数値そのものなので、
# 無関係な編集で文書の統計量がわずかに変化しただけで excerpt 文字列が変わり、
# 同一性キーに含めると「解消」＋「新規」の偽ペアが発生してしまう。
# このグループはカテゴリ名だけをキーにする（1文書1件が前提なので情報の欠落もない）。
#
# 一方、nominal_ending・repeated_sentence_lead・repeated_syntax_template・
# paragraph_lead_conjunction・antithesis_repetition は「文書全体集計型」ではあるが、
# excerpt 自体は実際にマッチした原文（体言止めの文末・反復した文頭など）であり、
# 数値は detail 側にしか出てこない（同一性キーは detail を見ていない）。
# これらは1文書内に複数の異なる該当箇所を持つのが普通なので、カテゴリ名だけに
# 潰さず、従来どおり excerpt の前方一致キーを使う方が精度が高い。
_CATEGORY_ONLY_KEY_CATEGORIES = {
    "low_burstiness",
    "high_length_autocorrelation",
    "low_sentence_variance",
    "uniform_paragraph_structure",
    "low_lexical_diversity_ttr",
    "low_lexical_diversity_mtld",
}


def _normalize_excerpt_for_key(excerpt: str) -> str:
    """excerpt を同一性キー用に正規化する（空白類を除去）。"""
    return re.sub(r"\s+", "", excerpt or "")


def _finding_identity_key(category: str, excerpt: str) -> tuple[str, str]:
    """(category, 正規化excerptの前方一致キー) を返す。行番号は含めない。
    _CATEGORY_ONLY_KEY_CATEGORIES に該当するカテゴリは excerpt を無視し、
    カテゴリ名のみをキーにする（理由は上のコメント参照）。
    """
    if category in _CATEGORY_ONLY_KEY_CATEGORIES:
        return (category, "")
    normalized = _normalize_excerpt_for_key(excerpt)
    return (category, normalized[:_BASELINE_KEY_EXCERPT_PREFIX_LEN])


def validate_baseline_data(baseline_data) -> tuple[dict | None, list[str]]:
    """--baseline で読み込んだ JSON の形を検証する。

    スキーマが想定外（トップレベルが dict でない、"findings" が配列でない、
    配列内の要素が dict でない等）でも compute_baseline_diff() をクラッシュ
    させたくないため、ここで軽量な検証を行い、
    - 完全に想定外の形なら (None, [警告メッセージ]) を返し、呼び出し側は
      baseline 比較そのものを諦めて通常の lint 実行にフォールバックする
      （graceful degradation。lint はそもそも CI ゲートではないので、
      baseline ファイルの不備で実行全体を落とすべきではない）
    - "findings" 配列の一部の要素だけが dict でない場合は、その要素だけを
      読み飛ばして残りで比較を続行する
    """
    warnings: list[str] = []
    if not isinstance(baseline_data, dict):
        warnings.append(
            "--baseline の内容が JSON オブジェクトではありません。baseline比較を無視して通常のlintを実行します。"
        )
        return None, warnings

    findings_raw = baseline_data.get("findings")
    if not isinstance(findings_raw, list):
        warnings.append(
            "--baseline に 'findings' 配列が見つかりません。baseline比較を無視して通常のlintを実行します。"
        )
        return None, warnings

    valid_findings = []
    skipped = 0
    for item in findings_raw:
        # dict であることに加え、_finding_identity_key() が触るフィールドの型も
        # ここで検証する（category が非文字列だと set 判定、excerpt が非文字列だと
        # re.sub がクラッシュするため。JSON としては valid でも型が壊れた baseline
        # は要素単位で読み飛ばす）。
        if (
            isinstance(item, dict)
            and isinstance(item.get("category"), str)
            and isinstance(item.get("excerpt"), str)
        ):
            valid_findings.append(item)
        else:
            skipped += 1
    if skipped:
        warnings.append(
            f"--baseline の findings 配列内に不正な要素が{skipped}件あったため読み飛ばしました。"
        )
    return {"findings": valid_findings}, warnings


def compute_baseline_diff(
    findings: list[Finding], baseline_data: dict
) -> tuple[list[dict], dict[str, int]]:
    """今回の findings と、前回の --json 出力（baseline_data、事前に
    validate_baseline_data() を通した想定）を比較する。

    各 Finding の `.status` を "new"（今回のみ）または "persisting"
    （両方に存在）に破壊的に設定する。baseline にしかない finding は
    「resolved（解消）」として別途リストで返す（対応する現在の Finding
    オブジェクトが存在しないため、baseline の生 dict のまま返す）。

    多重集合としてマッチングする（同じキーの finding が複数あっても、
    件数分だけ 1 対 1 で対応付ける）ため、同じ指摘が複数箇所にある
    ケースでも resolved/persisting の件数がズレない。
    """
    from collections import defaultdict

    baseline_findings = baseline_data.get("findings", [])
    baseline_by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for bf in baseline_findings:
        key = _finding_identity_key(bf.get("category", ""), bf.get("excerpt", ""))
        baseline_by_key[key].append(bf)

    for f in findings:
        key = _finding_identity_key(f.category, f.excerpt)
        bucket = baseline_by_key.get(key)
        if bucket:
            bucket.pop(0)
            f.status = "persisting"
        else:
            f.status = "new"

    resolved = [bf for bucket in baseline_by_key.values() for bf in bucket]

    summary = {
        "resolved": len(resolved),
        "new": sum(1 for f in findings if f.status == "new"),
        "persisting": sum(1 for f in findings if f.status == "persisting"),
    }
    return resolved, summary


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
# フェンス行の検出。開始/終了の判定では「同じ文字種（`` ` `` か `~`）かつ
# 長さが開始フェンス以上」であることを別途チェックする（``` と ~~~ の混同や、
# フェンス内に出てくる別種・より短いフェンス様の行での誤クローズを防ぐため）。
_CODE_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
# 表の行判定は保守的に: 「行が `|` で始まり、`|` を2個以上含む」または
# 区切り行（`|---|---|` 的な、`-`/`:`/`|`/空白のみで構成される行）に限定する。
# 本文中にたまたま `|` が1個だけ出るケースを誤マスクしないための条件。
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|")
_TABLE_DELIMITER_RE = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*\|?\s*$")
# YAML フロントマター（ファイル先頭の `---` ... `---`）。先頭行が単独の `---` の
# ときだけフロントマターとみなし、次の単独 `---` までをまとめてマスクする。
_FRONT_MATTER_DELIM_RE = re.compile(r"^---\s*$")
# インラインコードスパン（`code` / ``code`` のようにバッククォート1〜2個で
# 囲まれた範囲）。CommonMark 完全準拠までは不要だが、コード自体にバッククォートを
# 含む場合に使われる `` code `` 記法（主用途: コード中に単一のバッククォートが
# 含まれる場合、例: `` `code` ``）程度は拾えるようにする。そのため、ダブル
# バッククォート側の中身は「バッククォート以外」または「直後がバッククォートでない
# 単独のバッククォート」を許可する（`(?:[^`]|`(?!`))+`）。貪欲になりすぎないよう
# `` の直前で止まるようにしている。
# 文解析前に該当部分だけ同じ文字数の空白に置換する（行番号・オフセットを保つため）。
_INLINE_CODE_SPAN_RE = re.compile(r"``(?:[^`\n]|`(?!`))+``|`[^`\n]+`")
# インデントコードブロック（4スペース以上のインデント）はマスク対象に含めない。
# 通常の文中でも字下げされた引用・リストの続きなど紛らわしいケースが多く、
# 誤マスクのリスクの方が高いと判断して見送る（要検討事項として明示しておく）。
# Markdown 内のリンク・画像 `[text](url)` / `![alt](url)` の url 部分。
# alt/text 側は自然文の一部として残し、URL のみ空白化する。
_MARKDOWN_LINK_URL_RE = re.compile(r"(\]\()([^)]*)(\))")


def _blank_inline_code_spans(line: str) -> str:
    """行内のインラインコードスパン・Markdownリンク/画像のURL部分を
    同じ長さの空白に置換する（オフセット保持）。"""
    line = _INLINE_CODE_SPAN_RE.sub(lambda m: " " * len(m.group(0)), line)
    # `](url)` の url 部分だけ空白化し、`](` と `)` はそのまま残す
    # （text/alt 側は文章の一部として解析対象に残すため）。
    line = _MARKDOWN_LINK_URL_RE.sub(lambda m: m.group(1) + " " * len(m.group(2)) + m.group(3), line)
    return line


def mask_markdown_structure(text: str) -> str:
    """見出し・リスト項目・コードブロック内・引用ブロック・表・YAMLフロントマターの行を
    空文字に置き換え、さらにインラインコードスパンとリンク/画像URLを空白化したテキストを返す。
    行数・行番号（およびインラインコードスパンの行内オフセット）は元のテキストと
    完全に一致させる（削除ではなくマスク）。

    インデントコードブロック（4スペースインデント）はマスク対象に含めない。
    箇条書きの折り返しや引用の字下げ等と見分けがつきにくく、誤マスクのリスクが
    フェンスコードブロックより高いと判断し、プロトタイプの段階では見送っている。
    """
    lines = text.split("\n")
    masked_lines = []
    in_code_block = False
    # 開いているフェンスの (文字種, 長さ)。``` と ~~~ の混同や、フェンス内に
    # 出てくる別種・より短いフェンス様の行での誤クローズを防ぐため、開始フェンスと
    # 同じ文字種かつ同じ長さ以上の行でしか閉じない（CommonMark 準拠までは行わない）。
    open_fence: tuple[str, int] | None = None
    # YAML フロントマターは「ファイル先頭行が単独の `---`」の場合のみ認識する。
    in_front_matter = False
    for idx, line in enumerate(lines):
        if idx == 0 and _FRONT_MATTER_DELIM_RE.match(line):
            in_front_matter = True
            masked_lines.append("")
            continue
        if in_front_matter:
            masked_lines.append("")
            if _FRONT_MATTER_DELIM_RE.match(line):
                in_front_matter = False
            continue

        fence_match = _CODE_FENCE_RE.match(line)
        if fence_match:
            fence_run = fence_match.group(1)
            fence_char = fence_run[0]
            fence_len = len(fence_run)
            # CommonMark に合わせ、閉じフェンスは「フェンス文字の連続＋後続は空白のみ」の
            # 行に限定する（開始フェンスは ```python のような info string を許容するが、
            # 閉じ側でそれを許すと、フェンス内の地の文がたまたま ``` で始まっただけの
            # 行を誤ってクローズ扱いしてしまう）。
            remainder_after_fence = line[fence_match.end() :]
            is_close_eligible = remainder_after_fence.strip() == ""
            if open_fence is None:
                open_fence = (fence_char, fence_len)
            elif fence_char == open_fence[0] and fence_len >= open_fence[1] and is_close_eligible:
                open_fence = None
            # 種類・長さが一致しない行、あるいは後ろに文字が続く行は
            # 「フェンス内の地の文（例: ```内で ~~ とだけ書いた行や ```これはコード）」
            # として扱い、トグルしない。
            masked_lines.append("")
            continue
        if open_fence is not None:
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
    """needle を含む行番号を探す。

    start_hint（探索を始めたい行番号、例: 対象段落の開始行）以降を優先的に走査する。
    同一内容の段落が文書中に複数回登場する場合、常に先頭から検索すると
    最初に出現した行に誤帰属してしまうため、start_hint 以降の一致を優先し、
    見つからない場合のみ文書全体（start_hint より前）にフォールバックする。
    """
    for no, line in lines:
        if no >= start_hint and needle in line:
            return no
    for no, line in lines:
        if needle in line:
            return no
    return start_hint or 1


def iter_paragraphs_with_lines(
    lines: list[tuple[int, str]],
) -> list[list[tuple[int, str]]]:
    """行番号付きの行リストを、空行区切りの段落（行のグループ）に分ける。

    段落の開始行が呼び出し側に正確に分かるため、re.split(r"\\n\\s*\\n", text) と
    テキスト検索（find_line_no）による近似の line_cursor 計算に頼らずに済む。
    同一内容の段落が複数回登場しても、行番号を直接持っているので誤帰属しない。
    """
    paragraphs: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    for no, line in lines:
        if line.strip():
            current.append((no, line))
        else:
            if current:
                paragraphs.append(current)
                current = []
    if current:
        paragraphs.append(current)
    return paragraphs


# ---------------------------------------------------------------------------
# 各検出器
# ---------------------------------------------------------------------------


def _raw_or_masked(raw_lines_by_no: dict[int, str] | None, no: int, fallback: str) -> str:
    """行番号に対応する原文行を返す（無ければマスク済み行にフォールバック）。"""
    if raw_lines_by_no is None:
        return fallback
    return raw_lines_by_no.get(no, fallback)


def detect_forbidden_phrases(
    lines: list[tuple[int, str]], raw_lines_by_no: dict[int, str] | None = None
) -> list[Finding]:
    """マスク済み行（コードスパン等を空白化したテキスト）でパターンマッチし、
    excerpt は同じオフセットで原文行から切り出す（マスクは解析専用、表示は原文）。
    """
    findings = []
    for no, line in lines:
        raw_line = _raw_or_masked(raw_lines_by_no, no, line)
        for phrase in FORBIDDEN_PHRASES:
            idx = line.find(phrase)
            if idx != -1:
                start = max(0, idx - 10)
                end = idx + len(phrase) + 10
                excerpt = raw_line[start:end] if len(raw_line) >= end else line[start:end]
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


def detect_translationese(
    lines: list[tuple[int, str]], raw_lines_by_no: dict[int, str] | None = None
) -> list[Finding]:
    findings = []
    for no, line in lines:
        raw_line = _raw_or_masked(raw_lines_by_no, no, line)
        for pat in TRANSLATIONESE_PATTERNS:
            for m in re.finditer(pat, line):
                start = max(0, m.start() - 10)
                end = m.end() + 10
                excerpt = raw_line[start:end] if len(raw_line) >= end else line[start:end]
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


def detect_antithesis_repetition(
    lines: list[tuple[int, str]], raw_lines_by_no: dict[int, str] | None = None
) -> list[Finding]:
    """「〜ではなく、〜」「〜だけでなく〜も」を文書全体で数え、3回以上なら反復として警告。
    どの文同士が反復としてカウントされたか追えるよう、全ヒット行番号を
    related_lines / detail の両方に含める。excerpt は原文から切り出す。
    """
    hits: list[tuple[int, str, str]] = []  # (line_no, matched_excerpt(raw), pattern_name)
    for no, line in lines:
        raw_line = _raw_or_masked(raw_lines_by_no, no, line)
        for pat in ANTITHESIS_PATTERNS:
            for m in re.finditer(pat, line):
                excerpt = raw_line[m.start() : m.end()] if len(raw_line) >= m.end() else m.group(0)
                hits.append((no, excerpt, pat.pattern))

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


def split_sentences_with_lines(
    lines: list[tuple[int, str]], raw_lines_by_no: dict[int, str] | None = None
) -> list[tuple[int, str, str]]:
    """行番号付きで文を分割する（。！？で分割、行内に複数文があれば同じ行番号を割り当てる）。

    マスク済みテキスト（見出し・表マスクやインラインコードスパンの空白置換済み）と
    原文（raw_lines_by_no）を同じオフセットで同時に切り出し、
    (行番号, マスク済み文, 原文の文) の3要素タプルを返す。
    マスク処理は「行の全置換（同じ長さの空文字ではなく行そのものを""にする）」か
    「インラインコードスパンを同じ文字数の空白に置換」のいずれかで、
    どちらも文字位置を保つため、マスク済みテキストで見つけた区切り位置をそのまま
    原文の同じオフセットに適用できる。
    見出し・表・コードブロックなどマスクで丸ごと空文字になった行は、マスク済み側が
    空になり文が生成されないため、原文にレポートに出したくない構造行の内容が
    紛れ込むことはない。
    """
    sentences = []
    for no, line in lines:
        raw_line = raw_lines_by_no.get(no, line) if raw_lines_by_no else line
        bounds = []
        prev = 0
        for m in SENTENCE_SPLIT_RE.finditer(line):
            bounds.append((prev, m.start()))
            prev = m.end()
        bounds.append((prev, len(line)))
        for s, e in bounds:
            piece = line[s:e]
            if piece.strip():
                raw_piece = raw_line[s:e] if len(raw_line) >= e else piece
                sentences.append((no, piece.strip(), raw_piece.strip()))
    return sentences


def detect_low_sentence_length_variance(
    sentences: list[tuple[int, str, str]], threshold: float = 0.25
) -> list[Finding]:
    """文長（文字数）の変動係数（CV = 標準偏差/平均）が閾値未満なら
    「文長が均質すぎる = リズムが単調 = AI臭い」として警告する。
    最低5文以上ないと統計的に意味がないので判定しない。
    """
    lengths = [len(s) for _, s, _ in sentences if len(s) > 0]
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

# 「無生物主語+他動詞」判定で「主語になっても不自然でない代名詞」として許可する語。
# sudachipy は「この事実」「そのこと」を単一形態素にせず複数形態素
# （例:「この」+「事実」）に分割するため、単一形態素の表層文字列と比較する
# 判定では到達不可能。単一形態素で成立する語だけをここに残し、
# 複数形態素にまたがる語は ABSTRACT_PRONOUN_PHRASES で別途、
# 隣接形態素を連結して比較する。
ABSTRACT_PRONOUNS = {"これ", "それ", "あれ", "それら"}
# 2形態素にまたがる指示表現（連結した表層文字列で比較する）
ABSTRACT_PRONOUN_PHRASES = {"この事実", "そのこと"}
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
    text: str  # マスク済みテキスト（形態素解析・パターンマッチ用）
    morphemes: list  # sudachipy.MorphemeList の要素（text を解析した結果）
    raw_text: str = ""  # 原文（レポートのexcerpt表示は必ずこちらを使う）


def tokenize_sentences(sentences: list[tuple[int, str, str]]) -> list[TokenizedSentence]:
    """文ごとに一度だけ形態素解析し、以後の検出器で使い回す（辞書ロードとトークナイズの
    コストを最小化するための共有キャッシュ）。
    形態素解析はマスク済みテキスト（text）に対して行うが、レポート表示用の原文
    （raw_text、インラインコードスパンのバッククォート内文字列などを含む）も保持し、
    excerpt はそちらから切り出す。
    """
    tokenizer = get_tokenizer()
    from sudachipy import SplitMode

    result = []
    for no, sent, raw_sent in sentences:
        if not sent:
            continue
        morphemes = list(tokenizer.tokenize(sent, SplitMode.C))
        result.append(TokenizedSentence(line=no, text=sent, morphemes=morphemes, raw_text=raw_sent or sent))
    return result


def _strip_trailing_symbols(morphemes: list) -> list:
    """文末の記号（」など）を除いた実質的な最終形態素列を返す。"""
    i = len(morphemes)
    while i > 0 and morphemes[i - 1].part_of_speech()[0] in TRAILING_SYMBOL_POS:
        i -= 1
    return morphemes[:i]


def detect_nominal_ending_and_paragraph_conjunctions(
    lines: list[tuple[int, str]],
    tokenized: list[TokenizedSentence],
    raw_lines_by_no: dict[int, str] | None = None,
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
            nominal_ending_findings.append((ts.line, ts.raw_text))

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
    # 段落を行番号付きでグルーピングすることで、段落開始行が直接分かる
    # （re.split + テキスト検索による line_cursor 近似だと、同一内容の段落が
    # 複数回登場したときに誤帰属していたため、行ベースの分割に置き換えた）。
    paragraphs = iter_paragraphs_with_lines(lines)
    conj_paragraph_count = 0
    total_paragraphs = len(paragraphs)
    conj_findings = []
    sentence_counts_per_paragraph = []
    for para_lines in paragraphs:
        first_no, first_line_raw = para_lines[0]
        first_line_text = first_line_raw.strip()
        para_joined = "\n".join(t for _, t in para_lines)
        sentence_counts_per_paragraph.append(
            len([p for p in SENTENCE_SPLIT_RE.split(para_joined) if p.strip()])
        )
        for conj in PARAGRAPH_CONJUNCTIONS:
            if first_line_text.startswith(conj):
                conj_paragraph_count += 1
                conj_findings.append((first_no, first_line_text, conj))
                break

    conj_ratio = conj_paragraph_count / total_paragraphs if total_paragraphs else 0.0
    if total_paragraphs >= 3 and conj_ratio >= 0.3:
        conj_lines = [no for no, _, _ in conj_findings]
        related = format_related_lines(conj_lines)
        for no, text_line, conj in conj_findings:
            excerpt_source = _raw_or_masked(raw_lines_by_no, no, text_line)
            findings.append(
                Finding(
                    line=no,
                    category="paragraph_lead_conjunction",
                    excerpt=excerpt_source[:40],
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
    """品詞列で「こと（名詞）+ が/は（助詞）+ でき〜（動詞、"でき"始まりの活用形）」の並びを
    検出する、翻訳調「〜することができる」の品詞列版。
    表層の正規表現（TRANSLATIONESE_PATTERNS）と違い、直前の動詞部分の送り仮名や
    活用（〜することができる/〜出来ます/〜出来た 等）の表記揺れに影響されない。
    注意: 「こと」の前に本当に動詞（〜する）が来ているかまでは確認していない
    （「このことができる」のような非対象ケースを完全には除外できない）。
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
                        # excerptは形態素のbegin/end（マスク済みテキスト内オフセット）を使い、
                        # 原文（raw_text）から同じ位置を切り出す（インラインコードスパンの
                        # バッククォート内文字列が欠落しないようにするため）。
                        span_start = ts.morphemes[max(0, i - 4)].begin()
                        span_end = ts.morphemes[k].end()
                        excerpt = ts.raw_text[span_start:span_end]
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


# 拗音を作る小書き文字（ャュョァィゥェォヮ）。「キャ」のように直前の文字と
# 合わせて1モーラを構成するため、単純な文字数カウントだと過大カウントになる。
# 促音（ッ）・長音（ー）は独立した1モーラとして数えるため、ここには含めない。
_SMALL_KANA_MERGE = set("ァィゥェォャュョヮ")


def mora_length(morphemes: list) -> int:
    """読み（カタカナ）を基にモーラ数の近似値を計算する。
    拗音の小書き文字（ャュョ等）は直前の文字と合算して1モーラとして数える
    補正を行うが、それ以外の長音・促音等の厳密な処理まではしていない。
    """
    total = 0
    for m in morphemes:
        reading = m.reading_form() or m.surface()
        count = 0
        for ch in reading:
            if ch in _SMALL_KANA_MERGE and count > 0:
                # 直前の文字と合わせて1モーラなので、追加でカウントしない
                continue
            count += 1
        total += count
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

    # 閾値 -0.62: このスキルの原則は「自然な人間の文章で誤検知しない」こと。
    # 人間が書いた自然な文章（fixtures/natural.md 相当）でも burstiness は
    # -0.55 前後まで下がることが実測で分かっている（モーラ計算の拗音補正後の実測値）。
    # -0.55 ちょうどを閾値にすると、その実測値のごく僅かな変動で人間の文章にまで
    # 誤検知するため、マージンを取って -0.62 まで緩めている。
    if burstiness < -0.62:
        findings.append(
            Finding(
                line=tokenized[0].line,
                category="low_burstiness",
                excerpt=f"burstiness={burstiness:.3f} (モーラ近似長 平均={mean:.1f}, 標準偏差={std:.1f})",
                severity="warn",
                detail="burstiness が閾値(-0.62)未満。文の長短のメリハリが乏しく機械的なリズムの疑い",
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
            lead_bigrams.append((ts.line, ts.raw_text, "".join(surfaces), is_tech_lead))

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
            lead_pos_ngrams.append((ts.line, ts.raw_text, pos_seq))

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


def build_line_to_paragraph_map(lines: list[tuple[int, str]]) -> dict[int, int]:
    """行番号 → 段落インデックス（0始まり）の対応表を作る。
    段落は空行区切りとみなし、iter_paragraphs_with_lines() で実際の行番号を
    直接グルーピングする（テキストの re.split + 行数カウントによる近似ではないため、
    同一内容の段落が複数回登場しても正しく対応付けられる）。
    """
    mapping: dict[int, int] = {}
    for idx, para_lines in enumerate(iter_paragraphs_with_lines(lines)):
        for ln, _ in para_lines:
            mapping[ln] = idx
    return mapping


def detect_nested_attributive(tokenized: list[TokenizedSentence], lines: list[tuple[int, str]]) -> list[Finding]:
    """連体修飾の入れ子検出（挑戦枠）。
    英語の関係代名詞節を直訳すると「〜する〜という〜な〜」のように、
    1文の中に「用言の連体形（動詞/形容詞/助動詞の連体形）+ それが係る名詞」という
    関係節構造が何層にも積み重なる。単発の連体修飾（例:「速く走る犬」）は自然な日本語でも
    普通に起きるため、1文中の連体形述語の個数が3個以上のときだけ「積み重ねすぎ」として警告する。

    同一段落内に複数文でヒットした場合は、その段落内の他のヒット行を
    related_lines / detail に付記する（段落単位でリズムの均質さ・手癖を見るため）。
    段落内ヒットが1件だけなら related_lines=None のまま。
    """
    findings = []
    ATTRIBUTIVE_POS = {"動詞", "形容詞", "助動詞"}
    para_map = build_line_to_paragraph_map(lines)

    raw_hits: list[tuple[int, str, int]] = []  # (line, excerpt(raw), attributive_count)
    for ts in tokenized:
        attributive_count = 0
        for m in ts.morphemes:
            pos = m.part_of_speech()
            if pos[0] in ATTRIBUTIVE_POS and "連体形" in (pos[5] or ""):
                attributive_count += 1
        if attributive_count >= 3:
            raw_hits.append((ts.line, ts.raw_text[:60], attributive_count))

    lines_by_paragraph: dict[int, list[int]] = {}
    for no, _, _ in raw_hits:
        pid = para_map.get(no, -1)
        lines_by_paragraph.setdefault(pid, []).append(no)

    for no, excerpt, count in raw_hits:
        pid = para_map.get(no, -1)
        paragraph_lines = lines_by_paragraph.get(pid, [no])
        # 同じ物理行に複数文がヒットしただけ（行番号が重複するだけ）では
        # 「段落内の別の対応箇所」として意味がないため、行番号の重複を除いた
        # ユニークな行数で2件以上ある場合だけ related_lines を付ける。
        distinct_paragraph_lines = sorted(set(paragraph_lines))
        detail = (
            f"1文中に連体形の用言が{count}個（閾値3個以上）。"
            "関係節が何層にも積み重なる英語統語の直訳調の疑い"
        )
        related_lines = None
        if len(distinct_paragraph_lines) > 1:
            related_lines = distinct_paragraph_lines
            detail += f"。同一段落内の{format_related_lines(distinct_paragraph_lines)}"
        findings.append(
            Finding(
                line=no,
                category="nested_attributive",
                excerpt=excerpt,
                severity="info",
                detail=detail,
                related_lines=related_lines,
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


def detect_english_syntax_smell(
    lines: list[tuple[int, str]], raw_lines_by_no: dict[int, str] | None = None
) -> list[Finding]:
    findings = []
    for no, line in lines:
        raw_line = _raw_or_masked(raw_lines_by_no, no, line)
        for pat in INANIMATE_SUBJECT_PATTERNS:
            for m in re.finditer(pat, line):
                excerpt = raw_line[m.start() : m.end()] if len(raw_line) >= m.end() else m.group(0)
                findings.append(
                    Finding(
                        line=no,
                        category="english_syntax_inanimate_subject",
                        excerpt=excerpt,
                        severity="info",
                        detail="無生物主語+他動詞的述語（表層パターン、英語統語の直訳調の可能性、要人間判断）",
                    )
                )

    # マスク済みテキストで構文マッチしつつ、excerpt は原文の文（raw）から組み立てる
    sentences = split_sentences_with_lines(lines, raw_lines_by_no)
    for i in range(len(sentences) - 1):
        no1, s1, r1 = sentences[i]
        no2, s2, r2 = sentences[i + 1]
        if CLEFT_BECAUSE_HEAD.match(s1) and BECAUSE_HEAD.match(s2):
            findings.append(
                Finding(
                    line=no1,
                    category="english_syntax_cleft_because",
                    excerpt=f"{r1}。{r2}",
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
        # 2形態素の指示表現（例:「この事実」）を「この」で先にマッチさせた場合、
        # 続く「事実」単体も形式名詞として再マッチしてしまい、同じ箇所が
        # 二重に検出されてしまう。skip_until でその形態素インデックスまでの
        # 単独マッチを抑制する。
        skip_until = -1
        for i in range(n):
            if i <= skip_until:
                continue
            # 単一形態素で成立する指示語・形式名詞
            is_abstract_subject = surfaces[i] in ABSTRACT_PRONOUNS or (
                poss[i] == "名詞" and surfaces[i] in {"こと", "事実", "の"}
            )
            subject_end = i
            if not is_abstract_subject:
                # 2形態素にまたがる指示表現（「この」+「事実」等）を、
                # 隣接する形態素を連結した表層文字列で判定する
                if i + 1 < n and (surfaces[i] + surfaces[i + 1]) in ABSTRACT_PRONOUN_PHRASES:
                    is_abstract_subject = True
                    subject_end = i + 1
            if not is_abstract_subject:
                continue
            skip_until = max(skip_until, subject_end)
            j = subject_end + 1
            if j >= n or poss[j] != "助詞" or surfaces[j] not in {"が", "は"}:
                continue
            # 主語マーカーの後、文末までの間に直訳調の他動詞があるか探す
            for k in range(j + 1, n):
                if poss[k] == "動詞" and dict_forms[k] in TRANSITIVE_SMELL_VERBS:
                    # excerptはbegin/end（マスク済みテキスト内オフセット）を使い、
                    # 原文（raw_text）から同じ位置を切り出す
                    span_start = ts.morphemes[max(0, i - 3)].begin()
                    span_end = ts.morphemes[k].end()
                    excerpt = ts.raw_text[span_start:span_end]
                    subject_text = "".join(surfaces[i : subject_end + 1])
                    findings.append(
                        Finding(
                            line=ts.line,
                            category="inanimate_subject_morph",
                            excerpt=excerpt,
                            severity="info",
                            detail=(
                                f"品詞列マッチ: 抽象主語「{subject_text}」+ {surfaces[j]} "
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
    # Markdown の構造行（見出し/リスト/コードブロック/引用/表）とインラインコードスパンは
    # 文章として扱わず、行番号を保ったままマスクしてから解析用テキストとして使う。
    # ただし excerpt（レポート表示）は必ず raw_text（原文）から同じオフセットで切り出す。
    # マスクは「解析専用」であり、表示用ではないことに注意。
    text = mask_markdown_structure(raw_text)
    lines = iter_lines_with_no(text)
    raw_lines_by_no = dict(iter_lines_with_no(raw_text))
    sentences = split_sentences_with_lines(lines, raw_lines_by_no)
    # sudachipy の形態素解析結果は複数の検出器で使い回す（トークナイズは1回だけ）。
    tokenized = tokenize_sentences(sentences)

    findings: list[Finding] = []
    # --- 表層（正規表現）ベースの検出器 ---
    findings += detect_forbidden_phrases(lines, raw_lines_by_no)
    findings += detect_translationese(lines, raw_lines_by_no)
    findings += detect_antithesis_repetition(lines, raw_lines_by_no)
    findings += detect_low_sentence_length_variance(sentences)
    findings += detect_english_syntax_smell(lines, raw_lines_by_no)

    # --- 形態素解析ベースの検出器（拡張: 品詞列・活用形マッチ） ---
    nominal_and_conj_findings, morph_stats = detect_nominal_ending_and_paragraph_conjunctions(
        lines, tokenized, raw_lines_by_no
    )
    findings += nominal_and_conj_findings
    findings += detect_translationese_morph(tokenized)
    findings += detect_inanimate_subject_morph(tokenized)
    findings += detect_nested_attributive(tokenized, lines)

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


STATUS_LABEL = {"new": "新規", "persisting": "継続"}


def print_human_report(
    path: Path,
    findings: list[Finding],
    stats: dict,
    baseline_summary: dict[str, int] | None = None,
) -> None:
    print(f"=== ai-smell-lint report: {path} ===")
    print(f"検出件数: {stats['total_findings']}")
    if stats["by_category"]:
        print("カテゴリ別内訳:")
        for cat, count in sorted(stats["by_category"].items(), key=lambda kv: -kv[1]):
            print(f"  - {cat}: {count}")

    # --baseline 指定時のみ、解消/新規/継続のサマリを追加表示する
    # （--baseline なしの場合はこのブロックごと出力されず、既存の挙動と完全に同じ）。
    if baseline_summary is not None:
        print(
            f"ベースライン比較: 解消: {baseline_summary['resolved']}件 / "
            f"新規: {baseline_summary['new']}件 / "
            f"継続: {baseline_summary['persisting']}件"
        )
    print()

    if not findings:
        print("検出なし。")
        return

    for f in findings:
        label = SEVERITY_LABEL.get(f.severity, f.severity)
        # baseline比較時は各行に新規/継続タグを付ける（比較しない場合は付けない＝従来どおり）
        status_tag = f"[{STATUS_LABEL.get(f.status, f.status)}] " if f.status else ""
        print(f"{status_tag}[{label}] L{f.line} ({f.category})")
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
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        metavar="PREV.json",
        help=(
            "前回の --json 出力ファイルと比較し、resolved（解消）/ new（新規）/ "
            "persisting（継続）を判定する（収束駆動の修正ループ支援。指定しない場合の"
            "挙動は完全に不変）"
        ),
    )
    args = parser.parse_args()

    # 「文章の中身に関する判断」と「そもそも実行できない入力エラー」は区別する。
    # 前者（検出結果）は exit 0（lintでありCIゲートではない）、
    # 後者（ファイル不在/ディレクトリ指定/読み取り不可/非UTF-8等）は exit 1。
    if not args.file.exists():
        print(f"エラー: ファイルが見つかりません: {args.file}", file=sys.stderr)
        return 1
    if args.file.is_dir():
        print(f"エラー: ディレクトリが指定されました（ファイルを指定してください）: {args.file}", file=sys.stderr)
        return 1

    try:
        text = args.file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"エラー: ファイルを読み込めません: {args.file} ({exc})", file=sys.stderr)
        return 1

    baseline_data = None
    if args.baseline is not None:
        if not args.baseline.exists():
            print(f"エラー: --baseline ファイルが見つかりません: {args.baseline}", file=sys.stderr)
            return 1
        try:
            loaded_baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(f"エラー: --baseline ファイルを読み込めません: {args.baseline} ({exc})", file=sys.stderr)
            return 1

        # JSON としては読めても、スキーマが想定外（トップレベルが配列、findings が
        # 欠けている、findings 内の要素が dict でない等）だと compute_baseline_diff()
        # がクラッシュしうる。lint は CI ゲートではなく、baseline はあくまで補助
        # 情報なので、想定外の形式のときは実行全体を落とさず、baseline比較を諦めて
        # 通常の lint 実行にフォールバックする（警告は出す）。
        baseline_data, baseline_warnings = validate_baseline_data(loaded_baseline)
        for w in baseline_warnings:
            print(f"警告: {w}", file=sys.stderr)

    findings, stats = run_lint(text)

    resolved: list[dict] = []
    baseline_summary: dict[str, int] | None = None
    if baseline_data is not None:
        resolved, baseline_summary = compute_baseline_diff(findings, baseline_data)

    if args.json:
        output = {
            "file": str(args.file),
            "stats": stats,
            "findings": [f.to_dict() for f in findings],
        }
        # --baseline を指定したときだけ baseline セクションを追加する
        # （指定しない場合の JSON 構造は従来と完全に同じ）。
        if baseline_summary is not None:
            output["baseline"] = {
                "file": str(args.baseline),
                "summary": baseline_summary,
                "resolved": resolved,
            }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print_human_report(args.file, findings, stats, baseline_summary)

    # lint であって CI ゲートではない。文章の検出結果は件数に関わらず常に exit 0 とし、
    # 修正するかどうかの判断は人間（または後続の AI 自己点検フロー）に委ねる。
    return 0


if __name__ == "__main__":
    sys.exit(main())
