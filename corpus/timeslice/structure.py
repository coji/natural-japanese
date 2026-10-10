# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""corpus/timeslice/structure.py — 構造の特徴を層ごとに比べる(ロードマップ S9)。

太字・箇条書き・ダッシュ・「まとめ」見出し・です・ます調を、H(AI以前)・W(2026年)・
H'(対コーパスの human)・G(対コーパスの各モデル)で並べる。記事ごとの率は外れ値に
引っ張られるため(S2 で太字の2025年が 9.05 に跳ねた)、中央値と「その特徴が閾値を超えた記事の割合」で見る。

出力: qiita-aug/structure.md(数値のみ)

使い方:
    uv run corpus/timeslice/structure.py --paired tech-qiita tech-qiita-s100
"""

from __future__ import annotations

import argparse
import gzip
import json
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "qiita-aug" / "data"

# 「閾値を超えた記事の割合」の閾値。H の記事の 90 パーセンタイル付近を目安に置く
METRICS = {
    "太字/1,000字": (lambda r: r["bold"] / max(r["prose_chars"], 1) * 1000, 5.0),
    "箇条書きの行の割合": (lambda r: r["list_lines"] / max(r["nonblank_lines"], 1), 0.25),
    "ダッシュ/1,000字": (lambda r: r["dashes"] / max(r["prose_chars"], 1) * 1000, 0.5),
    "「まとめ」見出し": (lambda r: float(r["summary_heading"]), 0.5),
}


def load(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(l) for l in f]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paired", nargs="*", default=["tech-qiita", "tech-qiita-s100"])
    args = parser.parse_args()
    groups: dict[str, list[dict]] = {
        "H(2019-22)": [r for y in (2019, 2020, 2021, 2022) for r in load(DATA / f"features-{y}.jsonl.gz")],
        "W(2026)": load(DATA / "features-2026.jsonl.gz"),
    }
    paired: dict[str, list[dict]] = defaultdict(list)
    for s in args.paired:
        for r in load(DATA / f"features-paired-{s}.jsonl.gz"):
            paired["H'" if r["group"] == "human" else r["group"]].append(r)
    groups.update(paired)

    out = ["# 構造の特徴(S9)", "", "各セルは「中央値 / 閾値を超えた記事の割合」。閾値は列見出しの括弧内。", ""]
    head = "| 層 | 記事数 | " + " | ".join(f"{k}(>{t})" for k, (_, t) in METRICS.items()) + " |"
    out += [head, "|---|---|" + "---|" * len(METRICS)]
    for name, rows in groups.items():
        cells = []
        for f, t in METRICS.values():
            vals = [f(r) for r in rows]
            cells.append(f"{statistics.median(vals):.2f} / {sum(v > t for v in vals) / len(vals):.0%}")
        out.append(f"| {name} | {len(rows):,} | " + " | ".join(cells) + " |")
    (HERE / "qiita-aug" / "structure.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
