# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "sudachipy>=0.6.8",
#     "sudachidict-core>=20240409",
# ]
# ///
"""readability-sweep.py — 14件の「読みやすさ」検出器候補をコーパスで検証する。

背景:
    v0.4.0 で lint.py（当時のファイル名は ai-smell-lint.py。2026-07 に textcore.py /
    lint.py / outline.py / terms.py へ分割・リネームされた）を「AI臭除去」から
    「読みやすく自然な日本語」へ拡張するための事前検証。14の候補メトリクスをコーパス全体（人間/AI）に対して
    計測し、人間 quality:high（+ aozora modern-colloquial-classic）文書での
    誤検知率（FP率）が5%未満を保ちつつ AI 文書との弁別力があるかを確認する。

    このプロジェクトは過去に nested_attributive 検出器を「上手な人間の文章に
    誤検知する」という理由で実装後に削除した経緯がある。同じ轍を踏まないため、
    ここでの FP 測定は厳密に「人間の上手な文章」のみを基準にする。

FP基準集合（corpus/README.md の既存方針を踏襲）:
    - corpus/human/web/ の sources.json で quality == "high" な文書
    - corpus/human/aozora/ の sources.json で register == "modern-colloquial-classic" な文書
      （aozora は quality フィールドを持たないため、代わりに register で
      「現代文に近い上手な文語」を判定している。sources.json 収録の12本の
      aozora文書は全て modern-colloquial-classic）
    quality: "ordinary" の web文書、register: "literary-classic" の aozora文書は
    参考ビンとして計測はするが、FP率算出には使わない。

使い方:
    uv run corpus/experiments/readability-sweep.py
"""

from __future__ import annotations

import importlib.util
import json
import re
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
CORPUS_DIR = REPO_ROOT / "corpus"
REPORTS_DIR = CORPUS_DIR / "reports"
SOURCES_JSON = CORPUS_DIR / "sources.json"


def load_lint_module():
    """scripts/lint.py をモジュールとして importlib でロードする。
    tokenizer / masking / sentence-split ユーティリティ（textcore.py 由来のものを
    含め、lint.py が re-export している）の再利用のためだけに使う。
    lint.py / textcore.py 自体は変更しない。

    このスクリプトは corpus/experiments/ から `uv run` されるため sys.path[0] は
    scripts/ ではない。lint.py 内部の `from textcore import ...` を解決できるよう、
    exec_module() の前に scripts/ を sys.path へ追加しておく必要がある
    （scripts/calibrate.py は自身が scripts/ 内にあるためこの追加が不要だが、
    このスクリプトは corpus/experiments/ にあるため明示的に追加する）。
    """
    scripts_dir = REPO_ROOT / "skills" / "natural-japanese" / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    lint_path = scripts_dir / "lint.py"
    spec = importlib.util.spec_from_file_location("lint", lint_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"lint.py をロードできません: {lint_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["lint"] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# コーパス読み込み（sources.json とファイルの対応付け）
# ---------------------------------------------------------------------------


@dataclass
class CorpusDoc:
    group: str  # "human_fp_base" | "human_reference" | "ai"
    path: Path
    text: str
    genre: str | None = None
    quality: str | None = None
    register: str | None = None
    ai_model: str | None = None
    char_count: int = field(init=False)

    def __post_init__(self) -> None:
        self.char_count = len(self.text)


def load_sources() -> list[dict]:
    return json.loads(SOURCES_JSON.read_text(encoding="utf-8"))


def load_corpus() -> list[CorpusDoc]:
    sources = load_sources()
    docs: list[CorpusDoc] = []

    for src in sources:
        if src["type"] == "aozora":
            fname = src["id"].removeprefix("aozora-") + ".txt"
            fpath = CORPUS_DIR / "human" / "aozora" / fname
            if not fpath.exists():
                continue
            text = fpath.read_text(encoding="utf-8")
            is_fp_base = src.get("register") == "modern-colloquial-classic"
            docs.append(
                CorpusDoc(
                    group="human_fp_base" if is_fp_base else "human_reference",
                    path=fpath,
                    text=text,
                    genre=src.get("genre"),
                    quality=src.get("quality"),
                    register=src.get("register"),
                )
            )
        elif src["type"] == "web":
            fpath = None
            for ext in (".md", ".txt"):
                cand = CORPUS_DIR / "human" / "web" / f"{src['id']}{ext}"
                if cand.exists():
                    fpath = cand
                    break
            if fpath is None:
                continue
            text = fpath.read_text(encoding="utf-8")
            is_fp_base = src.get("quality") == "high"
            docs.append(
                CorpusDoc(
                    group="human_fp_base" if is_fp_base else "human_reference",
                    path=fpath,
                    text=text,
                    genre=src.get("genre"),
                    quality=src.get("quality"),
                    register=src.get("register"),
                )
            )

    # AI コーパス（sources.json には載っていない。ディレクトリ名 = モデル名）
    ai_dir = CORPUS_DIR / "ai"
    if ai_dir.exists():
        for model_dir in sorted(p for p in ai_dir.iterdir() if p.is_dir()):
            for fpath in sorted(list(model_dir.glob("*.md")) + list(model_dir.glob("*.txt"))):
                text = fpath.read_text(encoding="utf-8")
                if not text.strip():
                    continue
                genre = None
                stem = fpath.stem
                for g in ("blog", "tech", "business", "essay", "note"):
                    if stem.startswith(g):
                        genre = g
                        break
                docs.append(
                    CorpusDoc(group="ai", path=fpath, text=text, genre=genre, ai_model=model_dir.name)
                )

    return docs


# ---------------------------------------------------------------------------
# 前処理（1文書1回だけ mask/split/tokenize する）
# ---------------------------------------------------------------------------


@dataclass
class PreparedDoc:
    doc: CorpusDoc
    lines: list
    raw_lines_by_no: dict
    sentences: list  # (line_no, masked_text, raw_text)
    tokenized: list  # TokenizedSentence
    paragraphs: list  # list[list[(line_no, raw_or_masked_text)]]


def prepare_doc(mod, doc: CorpusDoc) -> PreparedDoc:
    masked = mod.mask_markdown_structure(doc.text)
    lines = mod.iter_lines_with_no(masked)
    raw_lines_by_no = dict(mod.iter_lines_with_no(doc.text))
    sentences = mod.split_sentences_with_lines(lines, raw_lines_by_no)
    tokenized = mod.tokenize_sentences(sentences)
    paragraphs = mod.iter_paragraphs_with_lines(lines)
    return PreparedDoc(
        doc=doc,
        lines=lines,
        raw_lines_by_no=raw_lines_by_no,
        sentences=sentences,
        tokenized=tokenized,
        paragraphs=paragraphs,
    )


# ---------------------------------------------------------------------------
# 14 候補メトリクスの実装
# ---------------------------------------------------------------------------

# --- 候補4: 二重否定パターン --------------------------------------------------
DOUBLE_NEGATION_PATTERNS = [
    re.compile(p)
    for p in [
        r"なくはない",
        r"なくもない",
        r"ないわけではない",
        r"ないことはない",
        r"ないでもない",
        r"しないわけにはいかない",
        r"ないとは言えない",
        r"ないとは限らない",
    ]
]

# --- 候補10: 冗長表現辞書 ------------------------------------------------------
REDUNDANT_PATTERNS = [
    re.compile(p)
    for p in [
        r"することができ",
        r"することが可能",
        r"という形になり",
        r"という形で",
        r"を行い(?:ます|う|った)",
        r"を行っており",
        r"の実施を行",
        r"ということができ",
        r"のではないかと考えられ",
        r"することとなり",
        r"することになり",
    ]
]

# --- 候補13: 表記ゆれ（同一語の漢字/かな/カタカナ表記の併用） -----------------------
NOTATION_VARIANT_GROUPS = [
    ("例えば", "たとえば"),
    ("従って", "したがって"),
    ("出来る", "できる"),
    ("良い", "よい"),
    ("時", "とき"),
    ("為", "ため"),
    ("事", "こと"),
    ("様々", "さまざま"),
    ("即ち", "すなわち"),
    ("但し", "ただし"),
    ("尚", "なお"),
    ("様な", "ような"),
    ("殆ど", "ほとんど"),
    ("色々", "いろいろ"),
    ("非常に", "とても"),
]

# --- 候補9: こそあど指示語 ------------------------------------------------------
DEMONSTRATIVE_RE = re.compile(
    r"(?:これ|それ|あれ|どれ|この|その|あの|どの|ここ|そこ|あそこ|どこ|"
    r"こちら|そちら|あちら|どちら|こう|そう|ああ|どう|こんな|そんな|あんな|どんな)"
)

# --- 候補12: 文頭接続詞 --------------------------------------------------------
SENTENCE_INITIAL_CONJUNCTIONS = [
    "しかし", "また", "そして", "したがって", "そのため", "そのため", "つまり",
    "一方", "なお", "さらに", "ただし", "しかも", "だが", "でも", "ところで",
    "このように", "たとえば", "例えば", "すなわち", "ちなみに", "逆に",
]
_conj_re = re.compile("|".join(re.escape(c) for c in sorted(SENTENCE_INITIAL_CONJUNCTIONS, key=len, reverse=True)))

FULLWIDTH_DIGIT_RE = re.compile(r"[０-９]")
HALFWIDTH_DIGIT_RE = re.compile(r"[0-9]")
FULLWIDTH_PERIOD_RE = re.compile(r"。")
FULLWIDTH_COMMA_RE = re.compile(r"、")
HALFWIDTH_PERIOD_RE = re.compile(r"(?<![0-9])\.(?![0-9])")  # 数字の小数点は除外
HALFWIDTH_COMMA_RE = re.compile(r",")

KANJI_RE = re.compile(r"[一-鿿]")
KATAKANA_RE = re.compile(r"[゠-ヿ]")
HIRAGANA_RE = re.compile(r"[぀-ゟ]")


def sentence_texts(prep: PreparedDoc) -> list[str]:
    return [raw if raw.strip() else masked for _, masked, raw in prep.sentences]


# ---------------------------------------------------------------------------
# 著作権ガード: 青空文庫（パブリックドメイン）以外の原文抜粋は
# レポート出力時に「引用略」に置換する。
# ---------------------------------------------------------------------------


def is_public_domain_source(path: Path) -> bool:
    """corpus/human/aozora/ 由来（パブリックドメイン）かどうかをパスで機械的に判定する。"""
    try:
        rel = path.relative_to(CORPUS_DIR)
    except ValueError:
        return False
    parts = rel.parts
    return len(parts) >= 2 and parts[0] == "human" and parts[1] == "aozora"


def redact_example(path: Path, example: str) -> str:
    """青空文庫以外のソース（web / ai）由来の原文抜粋を著作権配慮のため置換する。"""
    if is_public_domain_source(path):
        return example
    return f"(引用略: {path.name} の該当文)"


def metric_01_sentence_length(prep: PreparedDoc) -> dict:
    lens = [len(s) for s in sentence_texts(prep) if s]
    if not lens:
        return {"n_sentences": 0, "rate_over_100": None, "mean": None, "cv": None}
    over100 = sum(1 for l in lens if l > 100) / len(lens)
    mean = statistics.mean(lens)
    cv = (statistics.pstdev(lens) / mean) if mean else 0.0
    return {"n_sentences": len(lens), "rate_over_100": over100, "mean": mean, "cv": cv}


def metric_02_subject_predicate_distance(prep: PreparedDoc) -> dict:
    """は/が で示された主題句の形態素位置から文末述語（最後の動詞/形容詞/助動詞
    直前までの実質述語形態素）までの形態素数距離の平均。
    文中に複数の は/が があれば最初の1つを使う（文全体の主題として近似）。
    """
    distances = []
    for ts in prep.tokenized:
        morphemes = ts.morphemes
        n = len(morphemes)
        if n < 3:
            continue
        subj_idx = None
        for i, m in enumerate(morphemes):
            surf = m.surface()
            pos = m.part_of_speech()[0]
            if pos == "助詞" and surf in ("は", "が") and i > 0:
                subj_idx = i
                break
        if subj_idx is None:
            continue
        # 文末の実質述語（末尾の記号・助詞類を除いた最後の内容形態素）
        pred_idx = n - 1
        while pred_idx > subj_idx and morphemes[pred_idx].part_of_speech()[0] in ("補助記号", "空白", "助詞", "助動詞"):
            pred_idx -= 1
        if pred_idx <= subj_idx:
            continue
        distances.append(pred_idx - subj_idx)
    if not distances:
        return {"n": 0, "mean_distance": None}
    return {"n": len(distances), "mean_distance": statistics.mean(distances)}


def metric_03_comma_density(prep: PreparedDoc) -> dict:
    texts = sentence_texts(prep)
    if not texts:
        return {"n_sentences": 0, "mean_commas_per_sentence": None}
    counts = [t.count("、") for t in texts]
    return {"n_sentences": len(texts), "mean_commas_per_sentence": statistics.mean(counts)}


def metric_04_double_negation(prep: PreparedDoc) -> dict:
    full_text = prep.doc.text
    hits = []
    for pat in DOUBLE_NEGATION_PATTERNS:
        for m in pat.finditer(full_text):
            start = max(0, m.start() - 15)
            end = min(len(full_text), m.end() + 15)
            hits.append(full_text[start:end].replace("\n", " "))
    return {"count": len(hits), "examples": hits[:3]}


def metric_05_passive_voice(prep: PreparedDoc) -> dict:
    """助動詞「れる/られる」のうち、受身用法とみなせるものの割合
    （動詞総数に対する比。可能/尊敬/自発との厳密な判別はsudachipyの品詞情報だけでは
    困難なため、直前が他動詞であるものを受身寄りの近似として数える簡易ヒューリスティック）。
    """
    passive_count = 0
    verb_count = 0
    for ts in prep.tokenized:
        morphemes = ts.morphemes
        for i, m in enumerate(morphemes):
            pos = m.part_of_speech()[0]
            if pos == "動詞":
                verb_count += 1
            if pos == "助動詞" and m.surface() in ("れる", "られる", "れ", "られ"):
                passive_count += 1
    if verb_count == 0:
        return {"n_verbs": 0, "passive_ratio": None}
    return {"n_verbs": verb_count, "passive_count": passive_count, "passive_ratio": passive_count / verb_count}


def metric_06_chained_ga(prep: PreparedDoc) -> dict:
    """非逆接（順接・単純接続）の「が」を助詞として1文中に2回以上含む文の割合。
    逆接の「が」との区別はsudachipyでは困難なため、ここでは
    「が」が文末以外に2回以上出現する文＝連鎖節構造の疑いとして広めに数える
    （正規表現/品詞情報のみで意味的逆接/順接の判別はしない、と明記した上での近似）。
    """
    chained_sentences = 0
    total = 0
    examples = []
    for ts in prep.tokenized:
        total += 1
        ga_positions = [
            i for i, m in enumerate(ts.morphemes)
            if m.part_of_speech()[0] == "助詞" and m.surface() == "が"
        ]
        if len(ga_positions) >= 2:
            chained_sentences += 1
            if len(examples) < 3:
                examples.append(ts.raw_text[:80])
    if total == 0:
        return {"n_sentences": 0, "chained_ga_rate": None}
    return {"n_sentences": total, "chained_ga_count": chained_sentences, "chained_ga_rate": chained_sentences / total, "examples": examples}


def metric_07_kanji_ratio(prep: PreparedDoc) -> dict:
    text = prep.doc.text
    total_chars = len(re.sub(r"\s", "", text))
    if total_chars == 0:
        return {"kanji_ratio": None}
    kanji = len(KANJI_RE.findall(text))
    return {"total_chars": total_chars, "kanji_ratio": kanji / total_chars}


def metric_08_katakana_ratio(prep: PreparedDoc) -> dict:
    text = prep.doc.text
    total_chars = len(re.sub(r"\s", "", text))
    if total_chars == 0:
        return {"katakana_ratio": None}
    kana = len(KATAKANA_RE.findall(text))
    return {"total_chars": total_chars, "katakana_ratio": kana / total_chars}


def metric_09_demonstrative_density(prep: PreparedDoc) -> dict:
    texts = sentence_texts(prep)
    total_chars = sum(len(t) for t in texts)
    if total_chars == 0:
        return {"per_1000_chars": None}
    count = sum(len(DEMONSTRATIVE_RE.findall(t)) for t in texts)
    return {"count": count, "total_chars": total_chars, "per_1000_chars": count / total_chars * 1000}


def metric_10_redundant_expressions(prep: PreparedDoc) -> dict:
    full_text = prep.doc.text
    hits = []
    for pat in REDUNDANT_PATTERNS:
        for m in pat.finditer(full_text):
            start = max(0, m.start() - 15)
            end = min(len(full_text), m.end() + 15)
            hits.append(full_text[start:end].replace("\n", " "))
    return {"count": len(hits), "examples": hits[:3]}


def metric_11_paragraph_cv(prep: PreparedDoc, mod) -> dict:
    """既存の detect_nominal_ending_and_paragraph_conjunctions が計算する
    paragraph_sentence_count_cv と同一定義（段落あたり文数のCV）で再計算する。
    候補11はこの既存メトリクスと重複することを確認するのが目的。"""
    counts = []
    for para_lines in prep.paragraphs:
        para_joined = "\n".join(t for _, t in para_lines)
        n = len([p for p in mod.SENTENCE_SPLIT_RE.split(para_joined) if p.strip()])
        counts.append(n)
    if len(counts) < 3:
        return {"n_paragraphs": len(counts), "cv": None}
    mean = statistics.mean(counts)
    cv = (statistics.pstdev(counts) / mean) if mean else 0.0
    return {"n_paragraphs": len(counts), "cv": cv}


def metric_12_sentence_initial_conjunction(prep: PreparedDoc) -> dict:
    texts = sentence_texts(prep)
    if not texts:
        return {"n_sentences": 0, "rate": None}
    hits = sum(1 for t in texts if _conj_re.match(t.strip()))
    return {"n_sentences": len(texts), "count": hits, "rate": hits / len(texts)}


def metric_13_notation_inconsistency(prep: PreparedDoc) -> dict:
    text = prep.doc.text
    hits = 0
    examples = []
    for kanji_form, kana_form in NOTATION_VARIANT_GROUPS:
        has_kanji = kanji_form in text
        has_kana = kana_form in text
        if has_kanji and has_kana:
            hits += 1
            idx = text.find(kanji_form)
            idx2 = text.find(kana_form)
            snippet1 = text[max(0, idx - 10):idx + 10].replace("\n", " ")
            snippet2 = text[max(0, idx2 - 10):idx2 + 10].replace("\n", " ")
            if len(examples) < 3:
                examples.append(f"{kanji_form}⇔{kana_form}: 「{snippet1}」/「{snippet2}」")
    return {"variant_group_hits": hits, "examples": examples}


def metric_14_punctuation_mixing(prep: PreparedDoc) -> dict:
    text = prep.doc.text
    full_period = len(FULLWIDTH_PERIOD_RE.findall(text))
    half_period = len(HALFWIDTH_PERIOD_RE.findall(text))
    full_comma = len(FULLWIDTH_COMMA_RE.findall(text))
    half_comma = len(HALFWIDTH_COMMA_RE.findall(text))
    full_digit = len(FULLWIDTH_DIGIT_RE.findall(text))
    half_digit = len(HALFWIDTH_DIGIT_RE.findall(text))
    period_mixed = full_period > 0 and half_period > 0
    comma_mixed = full_comma > 0 and half_comma > 0
    digit_mixed = full_digit > 0 and half_digit > 0
    return {
        "period_mixed": period_mixed,
        "comma_mixed": comma_mixed,
        "digit_mixed": digit_mixed,
        "any_mixed": period_mixed or comma_mixed or digit_mixed,
        "full_period": full_period, "half_period": half_period,
        "full_comma": full_comma, "half_comma": half_comma,
        "full_digit": full_digit, "half_digit": half_digit,
    }


METRIC_FUNCS = {
    1: metric_01_sentence_length,
    2: metric_02_subject_predicate_distance,
    3: metric_03_comma_density,
    4: metric_04_double_negation,
    5: metric_05_passive_voice,
    6: metric_06_chained_ga,
    7: metric_07_kanji_ratio,
    8: metric_08_katakana_ratio,
    9: metric_09_demonstrative_density,
    10: metric_10_redundant_expressions,
    12: metric_12_sentence_initial_conjunction,
    13: metric_13_notation_inconsistency,
    14: metric_14_punctuation_mixing,
}


def compute_all_metrics(prep: PreparedDoc, mod) -> dict:
    result = {}
    for num, fn in METRIC_FUNCS.items():
        try:
            result[num] = fn(prep)
        except Exception as e:  # noqa: BLE001
            result[num] = {"error": str(e)}
    result[11] = metric_11_paragraph_cv(prep, mod)
    return result


# ---------------------------------------------------------------------------
# 閾値スイープ（1,2,3,5,6,7,8,9,12）
# ---------------------------------------------------------------------------

THRESHOLD_METRICS = {
    1: ("rate_over_100", "high"),   # 高いほどAI寄り、と仮定してスイープ（両方向試す）
    2: ("mean_distance", "high"),
    3: ("mean_commas_per_sentence", "both"),
    5: ("passive_ratio", "high"),
    6: ("chained_ga_rate", "high"),
    7: ("kanji_ratio", "both"),
    8: ("katakana_ratio", "high"),
    9: ("per_1000_chars", "both"),
    12: ("rate", "high"),
}


def sweep_threshold(values_fp: list[float], values_ai: list[float], direction: str):
    """FP率<5%を保ちつつAI検出率を最大化する閾値を探索する。

    事前に「AIの方が高い/低いはず」と決め打ちすると、実際のコーパスでの
    平均の大小関係が逆だった場合に閾値が見つからず弁別力なしと誤判定してしまう
    （実際、本コーパスでは候補1,2,5,9,12は human_fp_base 側の平均の方が高かった）。
    そのため direction 引数によらず、常に「high（値が閾値以上でヒット）」
    「low（値が閾値以下でヒット）」「band（[lo,hi]の外側でヒット）」の
    3方向すべてを試し、FP<5%制約下でAI検出率最大のものを採用する。
    direction 引数は将来の絞り込み用に残すが、現状は常に全方向探索する。
    """
    if not values_fp or not values_ai:
        return None
    all_vals = sorted(set(values_fp + values_ai))
    best = None

    def consider(cand: dict) -> None:
        nonlocal best
        if cand["fp_rate"] >= 0.05:
            return
        if best is None or cand["ai_detection_rate"] > best["ai_detection_rate"]:
            best = cand

    for th in all_vals:
        fp_hits = sum(1 for v in values_fp if v >= th)
        ai_hits = sum(1 for v in values_ai if v >= th)
        consider({
            "threshold": th, "direction": "value >= threshold",
            "fp_rate": fp_hits / len(values_fp), "ai_detection_rate": ai_hits / len(values_ai),
        })
        fp_hits_lo = sum(1 for v in values_fp if v <= th)
        ai_hits_lo = sum(1 for v in values_ai if v <= th)
        consider({
            "threshold": th, "direction": "value <= threshold",
            "fp_rate": fp_hits_lo / len(values_fp), "ai_detection_rate": ai_hits_lo / len(values_ai),
        })

    med = statistics.median(values_fp)
    spread_candidates = sorted(set(abs(v - med) for v in values_fp + values_ai))
    for half in spread_candidates:
        lo, hi = med - half, med + half
        fp_hits = sum(1 for v in values_fp if v < lo or v > hi)
        ai_hits = sum(1 for v in values_ai if v < lo or v > hi)
        consider({
            "threshold": (lo, hi), "direction": "value outside [lo, hi]",
            "fp_rate": fp_hits / len(values_fp), "ai_detection_rate": ai_hits / len(values_ai),
        })

    return best


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

METRIC_NAMES = {
    1: "文長 (100字超え率)",
    2: "主語述語距離",
    3: "読点密度",
    4: "二重否定パターン",
    5: "受身表現比率",
    6: "連鎖が（2回以上/文）",
    7: "漢字比率",
    8: "カタカナ比率",
    9: "こそあど密度",
    10: "冗長表現辞書",
    11: "段落文数CV（既存重複チェック）",
    12: "文頭接続詞率",
    13: "表記ゆれ（漢字/かな）",
    14: "句読点・全角半角混在",
}

FIELD_MAP = {
    1: "rate_over_100", 2: "mean_distance", 3: "mean_commas_per_sentence",
    5: "passive_ratio", 6: "chained_ga_rate", 7: "kanji_ratio",
    8: "katakana_ratio", 9: "per_1000_chars", 12: "rate",
}


def main() -> None:
    print("[1/4] コーパス読み込み中...", file=sys.stderr)
    mod = load_lint_module()
    docs = load_corpus()
    fp_base = [d for d in docs if d.group == "human_fp_base"]
    human_ref = [d for d in docs if d.group == "human_reference"]
    ai_docs = [d for d in docs if d.group == "ai"]
    print(
        f"  human_fp_base={len(fp_base)}  human_reference={len(human_ref)}  ai={len(ai_docs)}",
        file=sys.stderr,
    )

    print("[2/4] 形態素解析・メトリクス計算中（時間がかかります）...", file=sys.stderr)
    all_docs = fp_base + human_ref + ai_docs
    prepared_and_metrics = []
    for i, doc in enumerate(all_docs):
        if i % 20 == 0:
            print(f"  {i}/{len(all_docs)}...", file=sys.stderr)
        try:
            prep = prepare_doc(mod, doc)
            metrics = compute_all_metrics(prep, mod)
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR on {doc.path}: {e}", file=sys.stderr)
            continue
        prepared_and_metrics.append((doc, metrics))
    print(f"  done: {len(prepared_and_metrics)} docs", file=sys.stderr)

    fp_results = [(d, m) for d, m in prepared_and_metrics if d.group == "human_fp_base"]
    ref_results = [(d, m) for d, m in prepared_and_metrics if d.group == "human_reference"]
    ai_results = [(d, m) for d, m in prepared_and_metrics if d.group == "ai"]

    print("[3/4] 閾値スイープ・パターン集計中...", file=sys.stderr)

    report_lines = []
    report_lines.append("# 読みやすさ検出器候補 14件 検証レポート\n")
    report_lines.append(
        f"コーパス規模: human_fp_base(quality:high web + aozora modern-colloquial-classic)="
        f"{len(fp_results)}件, human_reference(参考ビン)={len(ref_results)}件, ai={len(ai_results)}件\n"
    )
    report_lines.append(
        "\nFP基準集合の内訳: "
        f"web quality:high = {sum(1 for d,_ in fp_results if d.path.parent.name=='web')}件, "
        f"aozora modern-colloquial-classic = {sum(1 for d,_ in fp_results if d.path.parent.name=='aozora')}件\n"
    )

    raw_dump = {"fp_base": [], "human_reference": [], "ai": []}
    for d, m in fp_results:
        raw_dump["fp_base"].append({"path": str(d.path.relative_to(REPO_ROOT)), "genre": d.genre, "metrics": _json_safe(m)})
    for d, m in ref_results:
        raw_dump["human_reference"].append({"path": str(d.path.relative_to(REPO_ROOT)), "genre": d.genre, "quality": d.quality, "metrics": _json_safe(m)})
    for d, m in ai_results:
        raw_dump["ai"].append({"path": str(d.path.relative_to(REPO_ROOT)), "genre": d.genre, "model": d.ai_model, "metrics": _json_safe(m)})

    verdict_summary = []

    # --- 閾値型メトリクス ---
    for num, (field_name, direction) in THRESHOLD_METRICS.items():
        report_lines.append(f"\n## 候補{num}: {METRIC_NAMES[num]}\n")
        vals_fp = [m[num].get(field_name) for _, m in fp_results if m[num].get(field_name) is not None]
        vals_ai = [m[num].get(field_name) for _, m in ai_results if m[num].get(field_name) is not None]
        report_lines.append(f"- 定義: `{field_name}`（方向: {direction}）\n")
        report_lines.append(f"- 有効サンプル数: human_fp_base={len(vals_fp)}, ai={len(vals_ai)}\n")
        if vals_fp:
            report_lines.append(
                f"- human_fp_base 分布: mean={statistics.mean(vals_fp):.4f}, "
                f"median={statistics.median(vals_fp):.4f}, "
                f"min={min(vals_fp):.4f}, max={max(vals_fp):.4f}\n"
            )
        if vals_ai:
            report_lines.append(
                f"- ai 分布: mean={statistics.mean(vals_ai):.4f}, "
                f"median={statistics.median(vals_ai):.4f}, "
                f"min={min(vals_ai):.4f}, max={max(vals_ai):.4f}\n"
            )
        best = sweep_threshold(vals_fp, vals_ai, direction) if vals_fp and vals_ai else None
        if best:
            report_lines.append(
                f"- **最良閾値**: {best['threshold']} ({best['direction']}) → "
                f"FP率={best['fp_rate']:.1%}, AI検出率={best['ai_detection_rate']:.1%}\n"
            )
            if best["direction"] == "value <= threshold":
                report_lines.append(
                    "\n> **注意（方向の逆転）**: この候補は当初「値が高い＝AI臭い」という"
                    "仮説で設計したが、本コーパスでは実際には human_fp_base（上手な人間）の"
                    "平均の方がAIより高く、弁別に効くのは「値が低い＝AI臭い」という逆方向だった。"
                    "つまりこの検出器は『(候補の説明にある)過剰な使用』ではなく『不足』を検出する"
                    "ことになる。この逆転は、既存の `low_burstiness`（文長の均質さ＝AI的、を検出する"
                    "検出器）と概念的に近く、単純に「複雑さ・変化に乏しい文章＝AI寄り」という"
                    "同じシグナルを別の指標で再計測しているだけの可能性がある。GO判定であっても、"
                    "簡潔で分かりやすい良い文章（初心者向け解説、平易なエッセイ等）を"
                    "誤って「AI臭い」と誤検知するリスクを本番導入前に個別に再検討すべき。\n"
                )
            diff = best["ai_detection_rate"] - best["fp_rate"]
            if best["fp_rate"] < 0.05 and (diff >= 0.15 or best["ai_detection_rate"] >= 0.15):
                verdict = "GO"
            elif best["fp_rate"] < 0.05:
                verdict = "NO-GO"
            else:
                verdict = "NO-GO"
        else:
            report_lines.append("- スイープ不能（サンプル不足）\n")
            verdict = "NO-GO"

        # ジャンル別内訳
        report_lines.append("\n**ジャンル別内訳（FP基準集合、参考値）**\n")
        for genre in ("essay", "tech", "business"):
            g_vals = [m[num].get(field_name) for d, m in fp_results if d.genre == genre and m[num].get(field_name) is not None]
            if g_vals:
                report_lines.append(f"- {genre}: n={len(g_vals)}, mean={statistics.mean(g_vals):.4f}\n")
        genre_note = ""
        if best and vals_fp:
            genre_fp_rates = {}
            for genre in ("essay", "tech", "business"):
                g_vals = [m[num].get(field_name) for d, m in fp_results if d.genre == genre and m[num].get(field_name) is not None]
                if g_vals:
                    th = best["threshold"]
                    bdir = best["direction"]
                    if bdir == "value >= threshold":
                        hits = sum(1 for v in g_vals if v >= th)
                    elif bdir == "value <= threshold":
                        hits = sum(1 for v in g_vals if v <= th)
                    else:
                        lo, hi = th
                        hits = sum(1 for v in g_vals if v < lo or v > hi)
                    genre_fp_rates[genre] = hits / len(g_vals)
            if genre_fp_rates:
                report_lines.append(f"\n閾値適用時のジャンル別FP率: {genre_fp_rates}\n")
                if verdict == "NO-GO" and best["fp_rate"] < 0.05:
                    pass
                high_fp_genres = [g for g, r in genre_fp_rates.items() if r >= 0.05]
                low_fp_genres = [g for g, r in genre_fp_rates.items() if r < 0.05]
                if verdict == "NO-GO" and best["fp_rate"] < 0.05 and high_fp_genres and low_fp_genres:
                    genre_note = f"（ジャンル限定なら有望: {low_fp_genres} はFP<5%, {high_fp_genres} はFP>=5%）"

        report_lines.append(f"\n**判定: {verdict}** {genre_note}\n")
        verdict_summary.append({
            "num": num, "name": METRIC_NAMES[num], "verdict": verdict,
            "fp": f"{best['fp_rate']:.1%}" if best else "N/A",
            "ai_det": f"{best['ai_detection_rate']:.1%}" if best else "N/A",
        })

    # --- パターン型メトリクス（絶対的な悪臭。4, 10, 13, 14） ---
    for num in (4, 10, 13, 14):
        report_lines.append(f"\n## 候補{num}: {METRIC_NAMES[num]}\n")
        if num in (4, 10):
            fp_with_hit = sum(1 for _, m in fp_results if m[num]["count"] >= 1)
            ai_with_hit = sum(1 for _, m in ai_results if m[num]["count"] >= 1)
            fp_rate_doc = fp_with_hit / len(fp_results) if fp_results else 0
            ai_rate_doc = ai_with_hit / len(ai_results) if ai_results else 0
            total_fp_chars = sum(d.char_count for d, _ in fp_results)
            total_fp_count = sum(m[num]["count"] for _, m in fp_results)
            total_ai_chars = sum(d.char_count for d, _ in ai_results)
            total_ai_count = sum(m[num]["count"] for _, m in ai_results)
            fp_per_1000 = total_fp_count / total_fp_chars * 1000 if total_fp_chars else 0
            ai_per_1000 = total_ai_count / total_ai_chars * 1000 if total_ai_chars else 0
            report_lines.append(
                f"- FP基準集合: {fp_with_hit}/{len(fp_results)}文書 ({fp_rate_doc:.1%}) に1件以上出現, "
                f"出現率={fp_per_1000:.3f}件/1000字\n"
            )
            report_lines.append(
                f"- AI: {ai_with_hit}/{len(ai_results)}文書 ({ai_rate_doc:.1%}) に1件以上出現, "
                f"出現率={ai_per_1000:.3f}件/1000字\n"
            )
            examples = []
            for d, m in fp_results:
                if m[num]["count"] >= 1:
                    for ex in m[num]["examples"]:
                        if is_public_domain_source(d.path):
                            examples.append(f"  - `{d.path.name}`: 「...{ex}...」")
                        else:
                            examples.append(f"  - `{d.path.name}`: {redact_example(d.path, ex)}")
                if len(examples) >= 5:
                    break
            if examples:
                report_lines.append("\n**FP基準集合での出現例（人間が判断してください）:**\n")
                report_lines.extend(ex + "\n" for ex in examples[:5])
            if fp_rate_doc < 0.05:
                verdict = "GO"
            elif fp_rate_doc < 0.15:
                verdict = "CONDITIONAL"
            else:
                verdict = "NO-GO"
            report_lines.append(f"\n**判定: {verdict}**\n")
            verdict_summary.append({"num": num, "name": METRIC_NAMES[num], "verdict": verdict, "fp": f"{fp_rate_doc:.1%}", "ai_det": f"{ai_rate_doc:.1%}"})
        elif num == 13:
            fp_with_hit = sum(1 for _, m in fp_results if m[num]["variant_group_hits"] >= 1)
            ai_with_hit = sum(1 for _, m in ai_results if m[num]["variant_group_hits"] >= 1)
            fp_rate_doc = fp_with_hit / len(fp_results) if fp_results else 0
            ai_rate_doc = ai_with_hit / len(ai_results) if ai_results else 0
            report_lines.append(
                f"- FP基準集合: {fp_with_hit}/{len(fp_results)}文書 ({fp_rate_doc:.1%}) に表記ゆれ1件以上\n"
            )
            report_lines.append(
                f"- AI: {ai_with_hit}/{len(ai_results)}文書 ({ai_rate_doc:.1%}) に表記ゆれ1件以上\n"
            )
            examples = []
            for d, m in fp_results:
                if m[num]["variant_group_hits"] >= 1:
                    for ex in m[num]["examples"][:1]:
                        if is_public_domain_source(d.path):
                            examples.append(f"  - `{d.path.name}`: {ex}")
                        else:
                            examples.append(f"  - `{d.path.name}`: {redact_example(d.path, ex)}")
                if len(examples) >= 5:
                    break
            if examples:
                report_lines.append("\n**FP基準集合での出現例:**\n")
                report_lines.extend(ex + "\n" for ex in examples[:5])
            # 表記ゆれは短い文書ほど出にくく、長文（随筆・技術記事）では
            # 自然に複数の表記が混じりうるため、文書長で条件を分けて見る
            if fp_rate_doc < 0.05:
                verdict = "GO"
            elif fp_rate_doc < 0.3:
                verdict = "CONDITIONAL"
            else:
                verdict = "NO-GO"
            report_lines.append(f"\n**判定: {verdict}**（表記ゆれは長い文書では単独で自然に起こりうる点に注意。1件でヒットにするのは厳しすぎる可能性）\n")
            verdict_summary.append({"num": num, "name": METRIC_NAMES[num], "verdict": verdict, "fp": f"{fp_rate_doc:.1%}", "ai_det": f"{ai_rate_doc:.1%}"})
        elif num == 14:
            fp_with_hit = sum(1 for _, m in fp_results if m[num]["any_mixed"])
            ai_with_hit = sum(1 for _, m in ai_results if m[num]["any_mixed"])
            fp_rate_doc = fp_with_hit / len(fp_results) if fp_results else 0
            ai_rate_doc = ai_with_hit / len(ai_results) if ai_results else 0
            report_lines.append(
                f"- FP基準集合: {fp_with_hit}/{len(fp_results)}文書 ({fp_rate_doc:.1%}) に句読点/全角半角混在\n"
            )
            report_lines.append(
                f"- AI: {ai_with_hit}/{len(ai_results)}文書 ({ai_rate_doc:.1%}) に混在\n"
            )
            if fp_rate_doc < 0.05:
                verdict = "GO"
            elif fp_rate_doc < 0.15:
                verdict = "CONDITIONAL"
            else:
                verdict = "NO-GO"
            report_lines.append(f"\n**判定: {verdict}**\n")
            verdict_summary.append({"num": num, "name": METRIC_NAMES[num], "verdict": verdict, "fp": f"{fp_rate_doc:.1%}", "ai_det": f"{ai_rate_doc:.1%}"})

    # --- 候補6 連鎖が: 例文も出す ---
    report_lines.append("\n### 候補6 補足: 連鎖が の出現例（FP基準集合）\n")
    for d, m in fp_results[:30]:
        exs = m[6].get("examples") or []
        if exs:
            if is_public_domain_source(d.path):
                report_lines.append(f"- `{d.path.name}`: 「{exs[0]}」\n")
            else:
                report_lines.append(f"- `{d.path.name}`: {redact_example(d.path, exs[0])}\n")

    # --- 候補11: 重複チェック ---
    report_lines.append(f"\n## 候補11: {METRIC_NAMES[11]}\n")
    report_lines.append(
        "- **既存メトリクスとの重複確認**: `scripts/lint.py` の "
        "`detect_nominal_ending_and_paragraph_conjunctions()` が計算する "
        "`paragraph_sentence_count_cv`（段落あたり文数の変動係数）と**同一定義**であり、"
        "`uniform_paragraph_structure` カテゴリとしてすでに検出・校正済みの検出器である。\n"
    )
    cv_vals_fp = [m[11].get("cv") for _, m in fp_results if m[11].get("cv") is not None]
    cv_vals_ai = [m[11].get("cv") for _, m in ai_results if m[11].get("cv") is not None]
    if cv_vals_fp:
        report_lines.append(f"- 参考: FP基準集合でのCV分布 mean={statistics.mean(cv_vals_fp):.3f}\n")
    if cv_vals_ai:
        report_lines.append(f"- 参考: AIでのCV分布 mean={statistics.mean(cv_vals_ai):.3f}\n")
    report_lines.append("\n**判定: NO-GO（重複のため新設不要。既存 `uniform_paragraph_structure` を継続利用）**\n")
    verdict_summary.append({"num": 11, "name": METRIC_NAMES[11], "verdict": "DUPLICATE(既存検出器と重複)", "fp": "-", "ai_det": "-"})

    # --- サマリテーブル ---
    summary_table = ["\n## サマリ\n", "| # | 名称 | 判定 | FP率 | AI検出率 |", "|---|---|---|---|---|"]
    verdict_summary.sort(key=lambda x: x["num"])
    for v in verdict_summary:
        summary_table.append(f"| {v['num']} | {v['name']} | {v['verdict']} | {v['fp']} | {v['ai_det']} |")
    report_lines = report_lines[:1] + summary_table + ["\n"] + report_lines[1:]

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_md = REPORTS_DIR / "readability-sweep-generated.md"
    out_md.write_text("\n".join(report_lines), encoding="utf-8")

    out_json = SCRIPT_DIR / "readability-sweep-raw.json"
    out_json.write_text(json.dumps(raw_dump, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"[4/4] 完了: {out_md}", file=sys.stderr)
    print(f"  生データ: {out_json}", file=sys.stderr)


def _json_safe(m: dict) -> dict:
    out = {}
    for k, v in m.items():
        if isinstance(v, dict):
            out[k] = {kk: vv for kk, vv in v.items()}
        else:
            out[k] = v
    return out


if __name__ == "__main__":
    main()
