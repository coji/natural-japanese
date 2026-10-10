# /// script
# requires-python = ">=3.11"
# dependencies = ["sudachipy>=0.6.8", "sudachidict-core>=20240409"]
# ///
"""corpus/llmjp/fp_compare.py — LLM-jp 由来の基準データで、現行 lint の誤検知の率を測る。

分類器のスコアが閾値以上の文書(説明的・実務的な、生成AI以前の Web 文章)から無作為に N 本を選び、
lint(--genre なし・tech)の検出器ごとの文書発火率を、地の文の長さの層別つきで出す。
既存の基準(Qiita の AI 以前の無作為抽出、corpus/timeslice/qiita-aug/fp-base.md)と並べて見る。

出力: corpus/llmjp/fp-compare.md(数値のみ。コミットする)
使い方: uv run corpus/llmjp/fp_compare.py --threshold 0.7 --n 600
"""
from __future__ import annotations
import argparse, json, random, re, sys
from collections import Counter
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "skills/natural-japanese/scripts"))
sys.path.insert(0, str(HERE))
from lint import run_lint  # noqa: E402
from textcore import mask_markdown_structure  # noqa: E402
from label_sample import trim  # noqa: E402

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.7)
    ap.add_argument("--n", type=int, default=600)
    a = ap.parse_args()
    rows = [json.loads(l) for f in sorted((ROOT / "corpus/private/llmjp").glob("*.scored.jsonl")) for l in open(f, encoding="utf-8")]
    pool = [r for r in rows if r["score"] >= a.threshold]
    sample = random.Random(0).sample(pool, min(a.n, len(pool)))
    groups = {"全体": [], "地の文1,000字未満": [], "1,000〜3,000字": [], "3,000字以上": []}
    for r in sample:
        t = trim(r["text"])
        pc = len(re.sub(r"\s+", "", mask_markdown_structure(t)))
        cats = {f.category for f in run_lint(t)[0]}
        groups["全体"].append(cats)
        groups["地の文1,000字未満" if pc < 1000 else "1,000〜3,000字" if pc < 3000 else "3,000字以上"].append(cats)
    allc = sorted(set().union(*groups["全体"]))
    out = ["# LLM-jp 由来の基準データでの lint の誤検知(生成AI以前の説明的・実務的な Web 文章)", "",
           f"分類器のスコア {a.threshold} 以上の {len(pool):,} 本から無作為に {len(sample)} 本。lint は既定(--genre なし)。", ""]
    out += ["| 検出器 | " + " | ".join(f"{k}(n={len(v)})" for k, v in groups.items()) + " |", "|---|" + "---|" * len(groups)]
    for c in allc:
        out.append(f"| {c} | " + " | ".join(f"{sum(c in x for x in v)/len(v):.0%}" if v else "-" for v in groups.values()) + " |")
    out.append(f"| (いずれか) | " + " | ".join(f"{sum(bool(x) for x in v)/len(v):.0%}" if v else "-" for v in groups.values()) + " |")
    (HERE / "fp-compare.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))

if __name__ == "__main__":
    main()
