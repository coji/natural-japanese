# /// script
# requires-python = ">=3.10"
# dependencies = ["scipy>=1.13", "sudachipy>=0.6.8", "sudachidict-core>=20240409"]
# ///
"""人間文とAI生成文の文長系列指標を同じ条件で比較する。"""

from __future__ import annotations

import importlib.util
import json
import math
import statistics
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from scipy.optimize import linear_sum_assignment
from scipy.stats import mannwhitneyu, pearsonr, spearmanr, wilcoxon

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
CORPUS = ROOT / "corpus"
OUT_JSON = CORPUS / "reports/research/sentence-length-analysis.json"
OUT_MD = CORPUS / "reports/research/sentence-length-analysis.md"
MIN_SENTENCES = 10


def load_lint():
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("rhythm_lint", SCRIPTS / "lint.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("scripts/lint.py をロードできない")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass
class Row:
    kind: str
    genre: str
    model: str
    doc_id: str
    path: str
    char_count: int
    n_sentences: int
    char_mean: float
    char_sd: float
    char_cv: float
    mora_mean: float
    mora_sd: float
    mora_cv: float
    burstiness: float
    adjacent_abs_diff: float
    adjacent_rmssd: float
    lag1_autocorr: float | None


def source_metadata() -> dict[str, dict]:
    entries = json.loads((CORPUS / "sources.json").read_text(encoding="utf-8"))
    return {entry["id"]: entry for entry in entries}


def human_paths(meta: dict[str, dict]) -> list[tuple[Path, str]]:
    result = []
    for path in sorted((CORPUS / "human/web").glob("*")):
        if path.suffix not in {".md", ".txt"}:
            continue
        entry = meta.get(path.stem)
        if not entry or entry.get("ai_era_risk") or entry.get("quality") != "high":
            continue
        result.append((path, entry.get("genre", "unknown")))
    for path in sorted((CORPUS / "human/aozora").glob("*")):
        if path.suffix not in {".md", ".txt"}:
            continue
        entry = meta.get(path.stem)
        if entry and entry.get("register") == "modern-colloquial-classic":
            result.append((path, "essay"))
    return result


def metric_row(mod, path: Path, kind: str, genre: str, model: str = "human") -> Row | None:
    raw = path.read_text(encoding="utf-8")
    masked = mod.mask_markdown_structure(raw)
    lines = mod.iter_lines_with_no(masked)
    sentences = mod.split_sentences_with_lines(lines, dict(mod.iter_lines_with_no(raw)))
    tokenized = mod.tokenize_sentences(sentences)
    if len(tokenized) < MIN_SENTENCES:
        return None
    chars = [len(text) for _, text, _ in sentences if text]
    mora = [mod.mora_length(item.morphemes) for item in tokenized]
    if len(chars) < MIN_SENTENCES or len(mora) < MIN_SENTENCES:
        return None
    cm, mm = statistics.mean(chars), statistics.mean(mora)
    cs, ms = statistics.pstdev(chars), statistics.pstdev(mora)
    diffs = [b - a for a, b in zip(mora, mora[1:])]
    lag1 = None
    if statistics.pstdev(mora[:-1]) and statistics.pstdev(mora[1:]):
        lag1 = float(pearsonr(mora[:-1], mora[1:]).statistic)
    return Row(
        kind, genre, model, path.stem, str(path.relative_to(ROOT)), len(raw), len(mora),
        cm, cs, cs / cm, mm, ms, ms / mm, (ms - mm) / (ms + mm),
        statistics.mean(abs(x) for x in diffs) / mm,
        math.sqrt(statistics.mean(x * x for x in diffs)) / mm,
        lag1,
    )


METRICS = [
    "char_mean", "char_sd", "char_cv", "mora_mean", "mora_sd", "mora_cv",
    "burstiness", "adjacent_abs_diff", "adjacent_rmssd", "lag1_autocorr",
]


def cliff_delta(ai: list[float], human: list[float]) -> float:
    greater = sum(a > h for a in ai for h in human)
    lower = sum(a < h for a in ai for h in human)
    return (greater - lower) / (len(ai) * len(human))


def bh_adjust(items: list[dict]) -> None:
    ordered = sorted(enumerate(items), key=lambda pair: pair[1]["p"])
    q, n = 1.0, len(items)
    for reverse_rank, (idx, item) in enumerate(reversed(ordered), 1):
        rank = n - reverse_rank + 1
        q = min(q, item["p"] * n / rank)
        items[idx]["q"] = q


def compare(rows: list[Row], genre: str) -> list[dict]:
    selected = [r for r in rows if genre == "all" or r.genre == genre]
    output = []
    for metric in METRICS:
        human = [getattr(r, metric) for r in selected if r.kind == "human" and getattr(r, metric) is not None]
        ai = [getattr(r, metric) for r in selected if r.kind == "ai" and getattr(r, metric) is not None]
        if not human or not ai:
            continue
        delta = cliff_delta(ai, human)
        output.append({
            "metric": metric, "n_human": len(human), "n_ai": len(ai),
            "human_median": statistics.median(human), "ai_median": statistics.median(ai),
            "cliffs_delta_ai_minus_human": delta, "auc_ai_higher": (delta + 1) / 2,
            "p": float(mannwhitneyu(ai, human, alternative="two-sided").pvalue),
        })
    bh_adjust(output)
    return output


def length_matched(rows: list[Row], genre: str) -> list[dict]:
    """同ジャンル内でlog総文字数の差が最小になる1対1対応を作る。"""
    human = [r for r in rows if r.kind == "human" and r.genre == genre]
    ai = [r for r in rows if r.kind == "ai" and r.genre == genre]
    if not human or not ai:
        return []
    cost = [[abs(math.log1p(h.char_count) - math.log1p(a.char_count)) for a in ai] for h in human]
    h_idx, a_idx = linear_sum_assignment(cost)
    pairs = [(human[i], ai[j]) for i, j in zip(h_idx, a_idx)]
    output = []
    for metric in METRICS:
        usable = [(getattr(h, metric), getattr(a, metric)) for h, a in pairs if getattr(h, metric) is not None and getattr(a, metric) is not None]
        if not usable:
            continue
        hv, av = zip(*usable)
        diffs = [a - h for h, a in usable]
        test = wilcoxon(diffs, alternative="two-sided")
        output.append({
            "metric": metric, "n_pairs": len(usable),
            "human_median": statistics.median(hv), "ai_median": statistics.median(av),
            "median_paired_difference_ai_minus_human": statistics.median(diffs),
            "p": float(test.pvalue),
        })
    bh_adjust(output)
    return output


def fmt(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.2e}" if 0 < abs(value) < 0.001 else f"{value:.3f}"


def report(rows: list[Row], comparisons: dict[str, list[dict]], matched: dict[str, list[dict]]) -> str:
    human = [r for r in rows if r.kind == "human"]
    ai = [r for r in rows if r.kind == "ai"]
    rho = spearmanr([r.mora_cv for r in rows], [r.burstiness for r in rows]).statistic
    threshold_rows = []
    for threshold in [-0.36, -0.34, -0.32, -0.30, -0.28, -0.26, -0.24]:
        threshold_rows.append((
            threshold,
            sum(r.burstiness < threshold for r in human) / len(human),
            sum(r.burstiness < threshold for r in ai) / len(ai),
        ))
    current_auto_h = sum((r.lag1_autocorr or -2) > 0.6 for r in human) / len(human)
    current_auto_a = sum((r.lag1_autocorr or -2) > 0.6 for r in ai) / len(ai)
    lines = [
        "# 文長系列のどの指標が人間文とAI文を分けるか", "", "## 結論", "",
        f"FP基準に使える人間文{len(human)}件とAI生成文{len(ai)}件を同じ処理で比較した。"
        " `burstiness=(σ−μ)/(σ+μ)` は `CV=σ/μ` の単調変換であり、独立した指標ではない。"
        f" 実測でもSpearmanの順位相関は {rho:.6f} だった。", "",
        "人間文とAI文の差はCliff's deltaで示す。正ならAI側が高く、負なら人間側が高い。"
        " 絶対値0.147未満はごく小さく、0.147以上は小、0.33以上は中、0.474以上は大の目安である。", "",
        "現行の `burstiness < -0.24` は人間文の32.4%にも発火した。FP率5%未満を優先するなら、"
        "この標本では閾値を `-0.36` まで下げる必要があり、そのときAI検出率は57.5%になる。"
        f" `lag1_autocorr > 0.6` の発火率は人間{current_auto_h:.1%}、AI{current_auto_a:.1%}で、"
        "方向も中央値も仮説と逆だった。AI的な単調さの検出器として維持する根拠はない。", "",
        "総文字数を揃えてもtechではCV・隣接差・自己相関の差が残った。businessではCVと隣接差の差が"
        "多重比較補正後に有意でなくなり、自己相関の差だけが明確に残った。文長変動の識別力は"
        "ジャンル依存であり、全ジャンル共通の品質規範にはできない。", "",
        "## データと方法", "",
        "人間文は `quality: high` かつ2022年以前を原則とし、青空文庫は現代口語に近い作品だけを含めた。"
        "AI文は7モデルの全生成物を対象とした。10文未満の文書は除外した。文分割とモーラ近似は"
        " `scripts/lint.py` と同じ実装を使った。Mann–WhitneyのU検定、Cliff's delta、"
        "Benjamini–Hochberg法による多重比較補正を用いた。", "",
    ]
    for genre, results in comparisons.items():
        title = "全ジャンル" if genre == "all" else genre
        n_h = sum(r.kind == "human" and (genre == "all" or r.genre == genre) for r in rows)
        n_a = sum(r.kind == "ai" and (genre == "all" or r.genre == genre) for r in rows)
        lines += [f"## {title}（人間n={n_h}、AI n={n_a}）", "", "| 指標 | 人間中央値 | AI中央値 | delta | AUC（AIが高い向き） | q |", "|---|---:|---:|---:|---:|---:|"]
        for item in results:
            lines.append(f"| `{item['metric']}` | {fmt(item['human_median'])} | {fmt(item['ai_median'])} | {fmt(item['cliffs_delta_ai_minus_human'])} | {fmt(item['auc_ai_higher'])} | {fmt(item['q'])} |")
        lines.append("")
    lines += [
        "## `burstiness` 閾値の再評価", "",
        "| 閾値 | 人間FP率 | AI検出率 |", "|---:|---:|---:|",
    ]
    for threshold, fp, detection in threshold_rows:
        lines.append(f"| {threshold:.2f} | {fp:.1%} | {detection:.1%} |")
    lines.append("")
    lines += [
        "## 総文字数を揃えた比較", "",
        "同じジャンル内で、総文字数の対数が最も近い人間文とAI文を重複なしで1対1対応させた。"
        "人間標本が十分あるbusinessとtechだけを示す。差は `AI−人間` のペア差中央値である。", "",
    ]
    for genre, results in matched.items():
        lines += [f"### {genre}", "", "| 指標 | n組 | 人間中央値 | AI中央値 | ペア差中央値 | q |", "|---|---:|---:|---:|---:|---:|"]
        for item in results:
            lines.append(f"| `{item['metric']}` | {item['n_pairs']} | {fmt(item['human_median'])} | {fmt(item['ai_median'])} | {fmt(item['median_paired_difference_ai_minus_human'])} | {fmt(item['q'])} |")
        lines.append("")
    by_model: dict[str, list[Row]] = defaultdict(list)
    for row in ai:
        by_model[row.model].append(row)
    lines += ["## モデル別の再現性", "", "| モデル | n | mora CV中央値 | 隣接絶対差中央値 | lag-1自己相関中央値 |", "|---|---:|---:|---:|---:|"]
    for model, group in sorted(by_model.items()):
        ac = [r.lag1_autocorr for r in group if r.lag1_autocorr is not None]
        lines.append(f"| {model} | {len(group)} | {fmt(statistics.median(r.mora_cv for r in group))} | {fmt(statistics.median(r.adjacent_abs_diff for r in group))} | {fmt(statistics.median(ac))} |")
    lines += [
        "", "## 限界", "",
        "文書は内容を対応させた刺激ではなく、ジャンル構成と文書長も完全には一致しない。AI側は同じ課題を"
        "複数モデルで生成しているため、各文書が完全に独立ともいえない。結果はこのコーパス内の識別力であり、"
        "AI性の因果効果ではない。読者評定がないため、知覚されるリズムの妥当性も証明しない。", "",
        "## 再現手順", "", "```bash", "uv run corpus/experiments/rhythm/sentence_length_analysis.py", "```", "",
    ]
    return "\n".join(lines)


def main() -> None:
    mod, meta, rows = load_lint(), source_metadata(), []
    for path, genre in human_paths(meta):
        if row := metric_row(mod, path, "human", genre):
            rows.append(row)
    for path in sorted((CORPUS / "ai").glob("*/*")):
        if path.suffix in {".md", ".txt"}:
            if row := metric_row(mod, path, "ai", path.name.split("-", 1)[0], path.parent.name):
                rows.append(row)
    genres = ["all"] + sorted({r.genre for r in rows} & {"essay", "tech", "business", "slide"})
    comparisons = {genre: compare(rows, genre) for genre in genres}
    matched = {genre: length_matched(rows, genre) for genre in ["business", "tech"]}
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({"minimum_sentences": MIN_SENTENCES, "rows": [asdict(r) for r in rows], "comparisons": comparisons, "length_matched": matched}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUT_MD.write_text(report(rows, comparisons, matched), encoding="utf-8")
    print(f"wrote {OUT_MD.relative_to(ROOT)} and {OUT_JSON.relative_to(ROOT)} ({len(rows)} docs)")


if __name__ == "__main__":
    main()
