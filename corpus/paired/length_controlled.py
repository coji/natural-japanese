# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "sudachipy>=0.6.8",
#     "sudachidict-core>=20240409",
# ]
# ///
"""corpus/paired/length_controlled.py — 長さをそろえて検出器を比べる(ロードマップ S15)。

検出器の多くは出現回数で反応するため、長い記事ほど反応しやすい(qiita-aug/fp-base.md)。
AI の記事は human より長いことが多いので、対コーパスでの検出率の差の一部は長さの差かもしれない。
そこで、human と AI の両方の記事を、先頭から段落の切れ目で約 N 字(地の文ではなく本文の文字数)に
切りそろえてから lint を当て、検出器ごとの文書発火率を比べる。N 字に満たない記事は除く。

出力: corpus/paired/length-controlled.md(数値のみ。長さごとに length-controlled-<字数>.md に改名して残す)

使い方:
    uv run corpus/paired/length_controlled.py --sets tech-qiita tech-qiita-s100 --chars 2500
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "skills" / "natural-japanese" / "scripts"))
sys.path.insert(0, str(HERE))
from evaluate_pairs import body_of  # noqa: E402
from lint import run_lint  # noqa: E402


def truncate(text: str, n: int) -> str | None:
    """段落(空行)の切れ目で、n 字を超えた最初の位置までを返す。n 字に満たなければ None。
    コードブロックの途中で切らないよう、フェンスの開閉を数えて閉じている切れ目だけを使う。"""
    if len(text) < n:
        return None
    out, total, fences = [], 0, 0
    for para in text.split("\n\n"):
        out.append(para)
        total += len(para) + 2
        fences += sum(1 for line in para.splitlines() if line.lstrip().startswith(("```", "~~~")))
        if total >= n and fences % 2 == 0:
            return "\n\n".join(out)
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sets", nargs="+", default=["tech-qiita", "tech-qiita-s100"])
    parser.add_argument("--chars", type=int, default=2500)
    args = parser.parse_args()

    counts: dict[str, Counter] = defaultdict(Counter)
    n_docs: Counter = Counter()
    full_counts: dict[str, Counter] = defaultdict(Counter)
    for s in args.sets:
        d = HERE / s
        groups = {"human": sorted((d / "human").glob("*.md"))}
        for m in sorted(x for x in (d / "ai").iterdir() if x.is_dir()):
            groups[m.name] = sorted(m.glob("*.md"))
        for g, paths in groups.items():
            for p in paths:
                text = body_of(p)
                cut = truncate(text, args.chars)
                if cut is None:
                    continue
                n_docs[g] += 1
                counts[g].update({f.category for f in run_lint(cut, genre="tech")[0]})
                full_counts[g].update({f.category for f in run_lint(text, genre="tech")[0]})
        print(s, dict(n_docs), file=sys.stderr)

    groups = list(n_docs)
    cats = sorted(set().union(*counts.values(), *full_counts.values()))
    out = [f"# 長さをそろえた比較(S15): 先頭約 {args.chars} 字", ""]
    out.append("各セルは「切りそろえた後 / 切りそろえる前(同じ記事)」の文書発火率。切りそろえる長さに満たない記事は除いた。")
    out += ["", "| 検出器 | " + " | ".join(f"{g}(n={n_docs[g]})" for g in groups) + " |", "|---|" + "---|" * len(groups)]
    for c in cats:
        out.append(
            f"| {c} | "
            + " | ".join(f"{counts[g][c] / n_docs[g]:.0%} / {full_counts[g][c] / n_docs[g]:.0%}" for g in groups)
            + " |"
        )
    (HERE / "length-controlled.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
