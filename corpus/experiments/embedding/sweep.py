# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "numpy",
# ]
# ///
"""sweep.py — トラックB(文埋め込みによる意味的反復・結束性検出)の3指標を
embed_corpus.py が作ったキャッシュ(npz)上で計算し、閾値スイープする。

指標定義(すべて cos類似度。埋め込みは normalize_embeddings=True 済みなので内積=cos類似度):
    1. semantic_repetition_max / _p95:
       非隣接文ペア(|i-j|>=2)の類似度のうち上位(max, 95%ile)。
       「同じことを言い換えて繰り返す」の検出。
    2. coherence_flatness_var / _range:
       隣接文類似度(|i-j|==1)の分散・レンジ。低いほど「平板」(AI仮説)。
    3. topic_jump_min:
       隣接文類似度の最小値。低いほど「脈絡のない飛躍」。

判定規律: FP基準集合(human quality:high web + aozora modern-colloquial-classic)での
誤検知率<5%を保ちつつAI検出率が意味のある水準(目安10%以上)の閾値が存在するかを
readability-sweep.py と同じ全方向探索(value>=th / value<=th)で調べる。

使い方:
    uv run corpus/experiments/embedding/sweep.py [--model cl-nagoya/ruri-v3-310m]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
CACHE_ROOT = SCRIPT_DIR / "cache"


@dataclass
class DocRecord:
    doc_id: str
    group: str
    genre: str
    ai_model: str
    quality: str
    register: str
    n_sentences: int
    metrics: dict


def cosine_matrix_stats(embeddings: np.ndarray) -> dict:
    n = embeddings.shape[0]
    out = {
        "semantic_repetition_max": None, "semantic_repetition_p95": None,
        "coherence_flatness_var": None, "coherence_flatness_range": None,
        "topic_jump_min": None,
    }
    if n < 3:
        return out
    sim = embeddings @ embeddings.T  # normalized -> cosine

    # 隣接文類似度 (|i-j|==1)
    adj = np.array([sim[i, i + 1] for i in range(n - 1)])
    if len(adj) >= 2:
        out["coherence_flatness_var"] = float(np.var(adj))
        out["coherence_flatness_range"] = float(adj.max() - adj.min())
        out["topic_jump_min"] = float(adj.min())
    elif len(adj) == 1:
        out["topic_jump_min"] = float(adj[0])

    # 非隣接文ペア (|i-j|>=2)
    iu = np.triu_indices(n, k=2)
    non_adj = sim[iu]
    if non_adj.size:
        out["semantic_repetition_max"] = float(non_adj.max())
        out["semantic_repetition_p95"] = float(np.percentile(non_adj, 95))

    return out


def load_all(model_slug: str) -> list[DocRecord]:
    cache_dir = CACHE_ROOT / model_slug
    records = []
    for fpath in sorted(cache_dir.glob("*.npz")):
        data = np.load(fpath, allow_pickle=True)
        embeddings = data["embeddings"]
        n = embeddings.shape[0]
        m = cosine_matrix_stats(embeddings)
        records.append(DocRecord(
            doc_id=str(data["doc_id"]), group=str(data["group"]), genre=str(data["genre"]),
            ai_model=str(data["ai_model"]), quality=str(data["quality"]), register=str(data["register"]),
            n_sentences=n, metrics=m,
        ))
    return records


def sweep_threshold(values_fp: list[float], values_ai: list[float]):
    """readability-sweep.py の sweep_threshold と同じ規律:
    FP率<5%制約下でAI検出率最大の閾値を全方向(value>=th / value<=th)から探す。
    """
    if not values_fp or not values_ai:
        return None
    all_vals = sorted(set(values_fp + values_ai))
    best = None

    def consider(cand):
        nonlocal best
        if cand["fp_rate"] >= 0.05:
            return
        if best is None or cand["ai_detection_rate"] > best["ai_detection_rate"]:
            best = cand

    for th in all_vals:
        fp_hits = sum(1 for v in values_fp if v >= th)
        ai_hits = sum(1 for v in values_ai if v >= th)
        consider({"threshold": th, "direction": "value >= threshold",
                   "fp_rate": fp_hits / len(values_fp), "ai_detection_rate": ai_hits / len(values_ai)})
        fp_hits_lo = sum(1 for v in values_fp if v <= th)
        ai_hits_lo = sum(1 for v in values_ai if v <= th)
        consider({"threshold": th, "direction": "value <= threshold",
                   "fp_rate": fp_hits_lo / len(values_fp), "ai_detection_rate": ai_hits_lo / len(values_ai)})
    return best


METRIC_KEYS = [
    "semantic_repetition_max", "semantic_repetition_p95",
    "coherence_flatness_var", "coherence_flatness_range",
    "topic_jump_min",
]

METRIC_LABELS = {
    "semantic_repetition_max": "semantic_repetition (非隣接ペア類似度 max)",
    "semantic_repetition_p95": "semantic_repetition (非隣接ペア類似度 p95)",
    "coherence_flatness_var": "coherence_flatness (隣接文類似度の分散)",
    "coherence_flatness_range": "coherence_flatness (隣接文類似度のレンジ)",
    "topic_jump_min": "topic_jump (隣接文類似度の最小値)",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="cl-nagoya/ruri-v3-310m")
    args = ap.parse_args()
    slug = args.model.replace("/", "__")

    print(f"[1/2] キャッシュ読み込み・類似度計算中 ({slug})...", file=sys.stderr)
    records = load_all(slug)
    fp_base = [r for r in records if r.group == "human_fp_base"]
    human_ref = [r for r in records if r.group == "human_reference"]
    ai_docs = [r for r in records if r.group == "ai"]
    print(f"  human_fp_base={len(fp_base)} human_reference={len(human_ref)} ai={len(ai_docs)}", file=sys.stderr)

    print("[2/2] 閾値スイープ・内訳集計中...", file=sys.stderr)
    lines = []
    lines.append("# トラックB: 文埋め込みによる意味的反復・結束性検出 — 実験結果\n")
    lines.append(f"モデル: `{args.model}`\n")
    lines.append(
        f"\nコーパス規模: human_fp_base={len(fp_base)}, human_reference(参考)={len(human_ref)}, ai={len(ai_docs)}\n"
    )

    summary_rows = []

    for key in METRIC_KEYS:
        vals_fp = [r.metrics[key] for r in fp_base if r.metrics[key] is not None]
        vals_ai = [r.metrics[key] for r in ai_docs if r.metrics[key] is not None]
        lines.append(f"\n## {METRIC_LABELS[key]}\n")
        lines.append(f"- n(fp_base)={len(vals_fp)}, n(ai)={len(vals_ai)}\n")
        if vals_fp:
            lines.append(
                f"- human_fp_base分布: mean={statistics.mean(vals_fp):.4f}, median={statistics.median(vals_fp):.4f}, "
                f"min={min(vals_fp):.4f}, max={max(vals_fp):.4f}, stdev={statistics.pstdev(vals_fp):.4f}\n"
            )
        if vals_ai:
            lines.append(
                f"- ai分布: mean={statistics.mean(vals_ai):.4f}, median={statistics.median(vals_ai):.4f}, "
                f"min={min(vals_ai):.4f}, max={max(vals_ai):.4f}, stdev={statistics.pstdev(vals_ai):.4f}\n"
            )
        best = sweep_threshold(vals_fp, vals_ai) if vals_fp and vals_ai else None
        verdict = "NO-GO"
        if best:
            lines.append(
                f"- **最良閾値**: {best['threshold']:.4f} ({best['direction']}) → "
                f"FP率={best['fp_rate']:.1%}, AI検出率={best['ai_detection_rate']:.1%}\n"
            )
            if best["fp_rate"] < 0.05 and best["ai_detection_rate"] >= 0.10:
                verdict = "GO"
            elif best["fp_rate"] < 0.05 and best["ai_detection_rate"] > 0:
                verdict = "WEAK(検出率不足)"
            else:
                verdict = "NO-GO"
        else:
            lines.append("- スイープ不能(サンプル不足)\n")

        # ジャンル別
        lines.append("\n**ジャンル別内訳(FP基準集合、参考値)**\n")
        genre_fp_rates = {}
        for genre in ("essay", "tech", "business", "blog", "note"):
            g_vals = [r.metrics[key] for r in fp_base if r.genre == genre and r.metrics[key] is not None]
            if g_vals:
                lines.append(f"- {genre}: n={len(g_vals)}, mean={statistics.mean(g_vals):.4f}\n")
                if best:
                    th = best["threshold"]
                    if best["direction"] == "value >= threshold":
                        hits = sum(1 for v in g_vals if v >= th)
                    else:
                        hits = sum(1 for v in g_vals if v <= th)
                    genre_fp_rates[genre] = hits / len(g_vals)
        if genre_fp_rates:
            lines.append(f"\n閾値適用時のジャンル別FP率: {genre_fp_rates}\n")

        # モデル別AI検出率
        lines.append("\n**モデル別内訳(AI, 閾値適用時の検出率)**\n")
        model_det_rates = {}
        for r in ai_docs:
            pass
        ai_models = sorted(set(r.ai_model for r in ai_docs if r.ai_model))
        for am in ai_models:
            m_vals = [r.metrics[key] for r in ai_docs if r.ai_model == am and r.metrics[key] is not None]
            if m_vals and best:
                th = best["threshold"]
                if best["direction"] == "value >= threshold":
                    hits = sum(1 for v in m_vals if v >= th)
                else:
                    hits = sum(1 for v in m_vals if v <= th)
                rate = hits / len(m_vals)
                model_det_rates[am] = rate
                lines.append(f"- {am}: n={len(m_vals)}, mean={statistics.mean(m_vals):.4f}, 検出率={rate:.1%}\n")

        lines.append(f"\n**判定: {verdict}**\n")
        summary_rows.append({
            "key": key, "label": METRIC_LABELS[key], "verdict": verdict,
            "fp": f"{best['fp_rate']:.1%}" if best else "N/A",
            "ai_det": f"{best['ai_detection_rate']:.1%}" if best else "N/A",
        })

    summary = ["\n## サマリ\n", "| 指標 | 判定 | FP率 | AI検出率 |", "|---|---|---|---|"]
    for s in summary_rows:
        summary.append(f"| {s['label']} | {s['verdict']} | {s['fp']} | {s['ai_det']} |")
    lines = lines[:2] + summary + ["\n"] + lines[2:]

    out_path = SCRIPT_DIR / "sweep-result.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")

    # 生データもJSONで保存
    raw = [{
        "doc_id": r.doc_id, "group": r.group, "genre": r.genre, "ai_model": r.ai_model,
        "n_sentences": r.n_sentences, **r.metrics,
    } for r in records]
    (SCRIPT_DIR / "sweep-raw.json").write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"完了: {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
