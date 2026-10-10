# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "sudachipy>=0.6.8",
#     "sudachidict-core>=20240409",
# ]
# ///
"""corpus/timeslice/fp_base.py — FP の基準にする人間の文章の選び方で、FP 率がどう変わるか(ロードマップ S16)。

現行の lint(--genre tech)の検出器ごとの文書発火率を、次の3つの人間の集合で並べる。
    既存基準: corpus/human/web の tech のうち quality: high(手作業で選んだ上手な文章)
    H': 対コーパスの human(ストック30以上、開発用2セット)
    H: 時系列コーパスの AI 以前(2019〜2022年8月)から無作為に N 本
H は地の文の長さで3層に分けた率も出す(長さの交絡を見るため。ROADMAP.md 5章)。

出力: qiita-aug/fp-base.md(数値のみ)

使い方:
    uv run corpus/timeslice/fp_base.py --sample 600
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "skills" / "natural-japanese" / "scripts"))
from lint import run_lint  # noqa: E402

DATA = HERE / "qiita-aug" / "data"
FM_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def cats(text: str) -> set[str]:
    findings, _ = run_lint(text, genre="tech")
    return {f.category for f in findings}


def strip_fm(text: str) -> tuple[str, str]:
    m = FM_RE.match(text)
    return (m.group(1), text[m.end():]) if m else ("", text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=600)
    args = parser.parse_args()

    sets: dict[str, list[str]] = {"既存基準(tech, quality:high)": [], "H'(ストック30以上)": []}
    # quality の手作業ラベルは各ファイルではなく sources.json にある
    sources = json.loads((ROOT / "corpus" / "sources.json").read_text(encoding="utf-8"))
    high_tech = {x["id"] for x in sources if x.get("genre") == "tech" and x.get("quality") == "high"}
    for p in sorted((ROOT / "corpus" / "human" / "web").glob("*.md")):
        if p.stem in high_tech:
            sets["既存基準(tech, quality:high)"].append(strip_fm(p.read_text(encoding="utf-8"))[1])
    for s in ("tech-qiita", "tech-qiita-s100"):
        for p in sorted((ROOT / "corpus" / "paired" / s / "human").glob("*.md")):
            sets["H'(ストック30以上)"].append(strip_fm(p.read_text(encoding="utf-8"))[1])
    recs = []
    for y in (2019, 2020, 2021, 2022):
        with gzip.open(DATA / f"{y}.jsonl.gz", "rt", encoding="utf-8") as f:
            recs += [json.loads(l) for l in f]
    rng = random.Random(0)
    sample = rng.sample(recs, args.sample)
    sets["H(無作為抽出)"] = [r["body"] for r in sample]
    for lo, hi, label in ((0, 1000, "H: 地の文1,000字未満"), (1000, 3000, "H: 1,000〜3,000字"), (3000, 10**9, "H: 3,000字以上")):
        sets[label] = [r["body"] for r in sample if lo <= r["prose_chars"] < hi]

    results = {}
    for name, texts in sets.items():
        c = Counter()
        for t in texts:
            c.update(cats(t))
        results[name] = (len(texts), c)
        print(name, len(texts), file=sys.stderr)

    all_cats = sorted(set().union(*(c for _, c in results.values())))
    names = list(results)
    out = ["# FP 基準の見直し(S16)", "", "現行 lint(`--genre tech`)の検出器ごとの文書発火率。どれも人間の文章なので、発火は FP にあたる。", ""]
    out += ["| 検出器 | " + " | ".join(f"{n}(n={results[n][0]})" for n in names) + " |", "|---|" + "---|" * len(names)]
    for cat in all_cats:
        out.append(f"| {cat} | " + " | ".join(f"{results[n][1][cat] / results[n][0]:.0%}" if results[n][0] else "-" for n in names) + " |")
    (HERE / "qiita-aug" / "fp-base.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
