# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "sudachipy>=0.6.8",
#     "sudachidict-core>=20240409",
# ]
# ///
"""corpus/paired/analyze_detectors.py — 語・パターン単位で human と AI の差を見る。

forbidden_phrase(禁止語)と translationese(直訳調)は、1つの検出器の中に多数の
語・パターンを抱えている。検出器全体の発火率では、AI 側に偏る語と人間も普通に
使う語が混ざって見えないため、語・パターンごとに「その語を含む文書の数」を
human と AI(全モデル合算)で比べる。

出力(corpus/paired/<set>/detector-breakdown.md。数値のみ):
    語・パターンごとに human 文書率、AI 文書率(7モデル平均)、比(AI / human)

使い方:
    uv run corpus/paired/analyze_detectors.py --sets tech-qiita tech-qiita-s100
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "skills" / "natural-japanese" / "scripts"))
sys.path.insert(0, str(HERE))
from evaluate_pairs import body_of  # noqa: E402
from lint import run_lint  # noqa: E402

CATEGORIES = ("forbidden_phrase", "translationese", "translationese_morph")
KEY_RES = (
    re.compile(r"「(.+?)」"),
    re.compile(r"パターン: (/.+?/)"),
    re.compile(r"品詞列マッチ: (.+?)$"),
)


def key_of(detail: str) -> str:
    for r in KEY_RES:
        m = r.search(detail)
        if m:
            return m.group(1)
    return detail[:40]


def keys_in(text: str) -> set[tuple[str, str]]:
    findings, _ = run_lint(text, genre="tech")
    return {(f.category, key_of(f.detail)) for f in findings if f.category in CATEGORIES}


def main() -> None:
    parser = argparse.ArgumentParser(description="語・パターン単位の human / AI 比較")
    parser.add_argument("--sets", nargs="+", default=["tech-qiita"])
    args = parser.parse_args()

    for set_name in args.sets:
        set_dir = HERE / set_name
        human_docs = [keys_in(body_of(p)) for p in sorted((set_dir / "human").glob("*.md"))]
        models = sorted(p.name for p in (set_dir / "ai").iterdir() if p.is_dir())
        ai_docs = {m: [keys_in(body_of(p)) for p in sorted((set_dir / "ai" / m).glob("*.md"))] for m in models}

        human_count = Counter(k for d in human_docs for k in d)
        ai_counts = {m: Counter(k for d in docs for k in d) for m, docs in ai_docs.items()}
        all_keys = set(human_count).union(*ai_counts.values())
        ai_rate = {
            k: [ai_counts[m][k] / len(ai_docs[m]) for m in models if ai_docs[m]] for k in all_keys
        }

        out = [f"## {set_name}", "", f"human {len(human_docs)} 本、AI {len(models)} モデル。", ""]
        out += ["| 検出器 | 語・パターン | human | AI 平均 | AI 最大 | 比 |", "|---|---|---|---|---|---|"]
        rows = []
        for k in all_keys:
            rates = ai_rate[k]
            h = human_count[k] / len(human_docs)
            a = sum(rates) / len(rates)
            ratio = a / h if h else float("inf")
            rows.append((k, h, a, max(rates), ratio))
        for (cat, key), h, a, amax, ratio in sorted(rows, key=lambda r: (r[0][0], -r[2])):
            ratio_s = "∞" if ratio == float("inf") else f"{ratio:.1f}"
            out.append(f"| {cat} | {key} | {h:.0%} | {a:.0%} | {amax:.0%} | {ratio_s} |")
        text = "\n".join(out) + "\n"
        print(text)
        (set_dir / "detector-breakdown.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
