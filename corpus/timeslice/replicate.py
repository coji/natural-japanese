# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""corpus/timeslice/replicate.py — 外部調査の見出し数値を自前の集計で再現する(ロードマップ S2)。

features.py が出した年ごとの特徴量から、外部調査と同じ指標を年別に出し、
AI以前(2019〜2022年)の平均と2026年を比べる。外部調査と同じく、AI以前の年平均を
直線で延ばした予測値からのずれを、AI以前の記事ごとの標準偏差で割った値も出す。

外部調査の値(比較対象):
    地の文字数 976 → 1,914 / 太字 1.26 → 3.83(1,000字あたり) / 箇条書き 8.9% → 16.4%
    ダッシュ 0.043 → 0.426(1,000字あたり) / 「まとめ」見出し 12% → 52%
    です・ます調 50% → 66% / 「効く」2.0% → 22.3%(記事の割合)

出力: qiita-aug/replication.md(数値のみ。コミットする)

使い方:
    uv run corpus/timeslice/replicate.py
"""

from __future__ import annotations

import gzip
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "qiita-aug" / "data"
PRE = [2019, 2020, 2021, 2022]
TARGET = 2026

REFERENCE = {
    "地の文字数": (976, 1914),
    "太字(1,000字あたり)": (1.26, 3.83),
    "箇条書きの行の割合": (0.089, 0.164),
    "ダッシュ(1,000字あたり)": (0.043, 0.426),
    "「まとめ」見出しのある記事": (0.12, 0.52),
    "です・ます調の記事": (0.50, 0.66),
    "「効く」を含む記事": (0.020, 0.223),
}


def per_doc(row: dict) -> dict[str, float]:
    pc = max(row["prose_chars"], 1)
    return {
        "地の文字数": row["prose_chars"],
        "太字(1,000字あたり)": row["bold"] / pc * 1000,
        "箇条書きの行の割合": row["list_lines"] / max(row["nonblank_lines"], 1),
        "ダッシュ(1,000字あたり)": row["dashes"] / pc * 1000,
        "「まとめ」見出しのある記事": float(row["summary_heading"]),
        "です・ます調の記事": float(row["desu_masu"] >= 0.5),
        "「効く」を含む記事": float("効く" in row["lemmas"]),
    }


def load(year: int) -> list[dict[str, float]]:
    path = DATA / f"features-{year}.jsonl.gz"
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [per_doc(json.loads(l)) for l in f]


def main() -> None:
    years = [y for y in range(2019, 2027) if (DATA / f"features-{y}.jsonl.gz").exists()]
    docs = {y: load(y) for y in years}
    means = {y: {k: statistics.fmean(d[k] for d in docs[y]) for k in REFERENCE} for y in years}

    out = ["# 外部調査の再現(S2)", ""]
    out.append("Qiita の各年8月の記事。除外基準は外部調査に合わせた(`collect_qiita_timeslice.py`)。")
    out.append("太字・ダッシュは記事ごとの率の平均、箇条書きは記事ごとの「箇条書きの行 / 空でない行」の平均。")
    out += ["", "## 件数", "", "| 年 | 記事数 |", "|---|---|"]
    out += [f"| {y} | {len(docs[y]):,} |" for y in years]

    out += ["", "## 年別の平均", "", "| 指標 | " + " | ".join(str(y) for y in years) + " |", "|---|" + "---|" * len(years)]
    for k in REFERENCE:
        out.append(f"| {k} | " + " | ".join(f"{means[y][k]:.3g}" for y in years) + " |")

    pre_years = [y for y in PRE if y in years]
    if pre_years and TARGET in years:
        out += ["", "## AI以前と2026年の比較", ""]
        out += ["| 指標 | AI以前(自前) | 2026(自前) | 倍率 | AI以前(外部) | 2026(外部) | 傾向線からのずれ(SD) |", "|---|---|---|---|---|---|---|"]
        for k, (ref_pre, ref_post) in REFERENCE.items():
            pre_vals = [d[k] for y in pre_years for d in docs[y]]
            pre_mean = statistics.fmean(pre_vals)
            pre_sd = statistics.pstdev(pre_vals) or 1.0
            post = means[TARGET][k]
            # AI以前の年平均を直線で延ばした 2026 年の予測値
            xs = pre_years
            ys = [means[y][k] for y in xs]
            xbar, ybar = statistics.fmean(xs), statistics.fmean(ys)
            slope = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / sum((x - xbar) ** 2 for x in xs)
            pred = ybar + slope * (TARGET - xbar)
            z = (post - pred) / pre_sd
            ratio = post / pre_mean if pre_mean else float("inf")
            out.append(
                f"| {k} | {pre_mean:.3g} | {post:.3g} | {ratio:.2f} | {ref_pre:.3g} | {ref_post:.3g} | {z:+.2f} |"
            )

    report = HERE / "qiita-aug" / "replication.md"
    report.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
