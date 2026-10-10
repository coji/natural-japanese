# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""corpus/paired/validate_lexicon.py — S4 の語彙候補を検証用セットで確かめる(ロードマップ S5)。

timeslice/qiita-aug/lexicon-candidates.md の候補語について、検証用セットの
H'(human)・G(タイトル条件の各モデル)・G′(推敲条件の各モデル)で、1,000字あたりの率と、
H' に対する比を出す。開発用セットで見つけた候補が、使っていないセットでも増えているかを見る。

出力: corpus/paired/<set>/lexicon-validation.md(数値のみ)

使い方:
    uv run corpus/paired/validate_lexicon.py --set tech-qiita-holdout
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = ROOT / "corpus" / "timeslice" / "qiita-aug" / "data"
CANDS = ROOT / "corpus" / "timeslice" / "qiita-aug" / "lexicon-candidates.md"
RATIO_MIN = 2.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", default="tech-qiita-holdout")
    args = parser.parse_args()

    words = [m.group(1) for m in re.finditer(r"^\| (\S+) \| [\d.]+ \|", CANDS.read_text(encoding="utf-8"), re.M)]
    with gzip.open(DATA / f"features-paired-{args.set}.jsonl.gz", "rt", encoding="utf-8") as f:
        rows = [json.loads(l) for l in f]
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[r["group"]].append(r)

    def per_k(g: str) -> dict[str, float]:
        chars = sum(r["prose_chars"] for r in groups[g]) / 1000
        c: Counter = Counter()
        for r in groups[g]:
            c.update(r["lemmas"])
        return {w: (c[w] + 0.5) / chars for w in words}

    order = ["human"] + sorted(g for g in groups if g != "human" and "/" not in g) + sorted(g for g in groups if "/" in g)
    rates = {g: per_k(g) for g in order}
    ai_groups = [g for g in order if g != "human"]

    out = [f"# 語彙候補の検証(S5): {args.set}", ""]
    out.append(
        f"候補は開発用セットと時系列コーパスで見つけた {len(words)} 語。各セルは H'(human)に対する 1,000字あたりの率の比"
        f"(0件は0.5件として計算)。{RATIO_MIN} 倍以上を太字にした。記事数: "
        + ", ".join(f"{g} {len(groups[g])}" for g in order)
    )
    out += ["", "| 語 | H' の率 | " + " | ".join(ai_groups) + " | タイトル条件で2倍以上のモデル数 |", "|---|---|" + "---|" * (len(ai_groups) + 1)]
    title_groups = [g for g in ai_groups if "/" not in g]
    held = 0
    for w in words:
        base = rates["human"][w]
        cells = []
        for g in ai_groups:
            r = rates[g][w] / base
            cells.append(f"**{r:.1f}**" if r >= RATIO_MIN else f"{r:.1f}")
        n_title = sum(rates[g][w] / base >= RATIO_MIN for g in title_groups)
        held += n_title == len(title_groups)
        out.append(f"| {w} | {base:.3f} | " + " | ".join(cells) + f" | {n_title}/{len(title_groups)} |")
    out.insert(3, f"\nタイトル条件の全モデルで {RATIO_MIN} 倍以上を保った候補: {held} / {len(words)} 語")
    (HERE / args.set / "lexicon-validation.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out[:8]))


if __name__ == "__main__":
    main()
