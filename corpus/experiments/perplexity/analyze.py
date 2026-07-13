# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""analyze.py — perplexity_sweep.py が出した raw_results.json を集計し、
閾値スイープ表・ジャンル別/モデル別内訳・一次判定を Markdown で出力する。

FP基準: human_high の誤検知率 <5% を保ちつつ AI 側検出率が意味のある水準(目安10%以上)
になる閾値が存在するかを探す。閾値は「doc_ppl が X 以下なら AI 疑い」という向き
（AI文はより予測しやすく perplexity が低いという仮説）と、逆向き（AI文は退屈で
定型的なぶん逆にpplが低い/高いどちらの仮説もありうるため）両方を試す。
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
raw = json.loads((HERE / "raw_results.json").read_text(encoding="utf-8"))
meta = json.loads((HERE / "run_meta.json").read_text(encoding="utf-8"))

human_high = [r for r in raw if r["bucket"] == "human_high" and not (r["doc_ppl"] != r["doc_ppl"])]
human_ordinary = [r for r in raw if r["bucket"] == "human_ordinary" and not (r["doc_ppl"] != r["doc_ppl"])]
ai = [r for r in raw if r["bucket"].startswith("ai:") and not (r["doc_ppl"] != r["doc_ppl"])]

def desc(xs, key="doc_ppl"):
    vals = [x[key] for x in xs]
    if not vals:
        return {"n": 0}
    return {
        "n": len(vals),
        "mean": statistics.mean(vals),
        "median": statistics.median(vals),
        "stdev": statistics.pstdev(vals) if len(vals) > 1 else 0.0,
        "min": min(vals),
        "max": max(vals),
    }

lines = []
lines.append("# perplexity_sweep 結果報告（トラックD: perplexity系AI検出）\n")
lines.append(f"モデル: `{meta['model_name']}` / device: `{meta['device']}` / 文書あたり平均 {meta['total_compute_sec']/max(1,meta['n_docs']):.2f}s\n")
lines.append(f"モデルロード: {meta['load_sec']:.1f}s / 全体計算時間: {meta['total_compute_sec']:.1f}s / 対象文書: {meta['n_docs']}\n")
lines.append(f"文書は Markdown構造マスク後、先頭 {meta['max_chars']} 字に切って計測（ブリーフ許可のサンプリング）。\n")

lines.append("\n## 1. 分布サマリ（doc_ppl = 文書全体のperplexity）\n")
lines.append("| bucket | n | mean | median | stdev | min | max |")
lines.append("|---|---|---|---|---|---|---|")
for label, xs in [("human_high", human_high), ("human_ordinary", human_ordinary), ("ai(全体)", ai)]:
    d = desc(xs)
    if d["n"] == 0:
        lines.append(f"| {label} | 0 | - | - | - | - | - |")
        continue
    lines.append(f"| {label} | {d['n']} | {d['mean']:.1f} | {d['median']:.1f} | {d['stdev']:.1f} | {d['min']:.1f} | {d['max']:.1f} |")

# モデル別
lines.append("\n## 2. モデル別 doc_ppl\n")
lines.append("| model | n | mean | median | stdev |")
lines.append("|---|---|---|---|---|")
models = sorted({r["model"] for r in ai if r["model"]})
for m in models:
    xs = [r for r in ai if r["model"] == m]
    d = desc(xs)
    lines.append(f"| {m} | {d['n']} | {d['mean']:.1f} | {d['median']:.1f} | {d['stdev']:.1f} |")

# ジャンル別
lines.append("\n## 3. ジャンル別 doc_ppl（human_high vs ai）\n")
lines.append("| genre | human_high mean(n) | ai mean(n) |")
lines.append("|---|---|---|")
genres = sorted({r["genre"] for r in raw})
for g in genres:
    hh = [r for r in human_high if r["genre"] == g]
    aa = [r for r in ai if r["genre"] == g]
    hh_s = f"{statistics.mean([x['doc_ppl'] for x in hh]):.1f}({len(hh)})" if hh else "-"
    aa_s = f"{statistics.mean([x['doc_ppl'] for x in aa]):.1f}({len(aa)})" if aa else "-"
    lines.append(f"| {g} | {hh_s} | {aa_s} |")

# 閾値スイープ（両方向）
lines.append("\n## 4. 閾値スイープ（doc_ppl 閾値で「AI疑い」を判定した場合）\n")
lines.append("FP基準: human_high の誤検知率<5%を保つ閾値の中で、AI検出率が最大になる点を探す。\n")

def sweep(direction: str):
    """direction: 'low' なら ppl<=閾値をAI疑いとする。'high' なら ppl>=閾値。"""
    hh_vals = sorted(x["doc_ppl"] for x in human_high)
    if not hh_vals:
        return None
    candidates = sorted({round(x["doc_ppl"], 1) for x in raw if not (x["doc_ppl"] != x["doc_ppl"])})
    rows = []
    for t in candidates:
        if direction == "low":
            fp = sum(1 for v in hh_vals if v <= t) / len(hh_vals)
            tp = sum(1 for x in ai if x["doc_ppl"] <= t) / len(ai) if ai else 0
        else:
            fp = sum(1 for v in hh_vals if v >= t) / len(hh_vals)
            tp = sum(1 for x in ai if x["doc_ppl"] >= t) / len(ai) if ai else 0
        rows.append((t, fp, tp))
    return rows

best = {"low": None, "high": None}
for direction in ("low", "high"):
    rows = sweep(direction)
    lines.append(f"\n### 方向: {direction} ({'ppl<=閾値をAI疑い' if direction=='low' else 'ppl>=閾値をAI疑い'})\n")
    lines.append("| threshold | human_high FP率 | AI検出率 |")
    lines.append("|---|---|---|")
    # サンプリングして代表的な行だけ出す(全閾値だと長すぎる)
    shown = rows[::max(1, len(rows)//30)]
    for t, fp, tp in shown:
        lines.append(f"| {t:.1f} | {fp*100:.1f}% | {tp*100:.1f}% |")
    valid = [r for r in rows if r[1] < 0.05]
    if valid:
        b = max(valid, key=lambda r: r[2])
        best[direction] = b
        lines.append(f"\nFP<5%を満たす中でAI検出率最大: 閾値={b[0]:.1f}, FP率={b[1]*100:.1f}%, AI検出率={b[2]*100:.1f}%\n")
    else:
        lines.append("\nFP<5%を満たす閾値なし。\n")

lines.append("\n## 5. 一次判定\n")
verdict_meets_bar = False
for direction, b in best.items():
    if b and b[2] >= 0.10:
        verdict_meets_bar = True
if verdict_meets_bar:
    lines.append("**採用可（限定的）** — FP<5%を満たしつつAI検出率10%以上を達成する閾値が存在した。詳細は上表参照。\n")
else:
    lines.append("**不可（検出器化不可、判断領域）** — FP<5%を満たす閾値でのAI検出率が10%未満、"
                  "またはFP<5%を満たす閾値自体が存在しない。事前調査（embed-research.md §3）の結論と一致。\n")

(HERE / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
print("wrote", HERE / "REPORT.md")
