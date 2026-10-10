# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "sudachipy>=0.6.8",
#     "sudachidict-core>=20240409",
# ]
# ///
"""corpus/paired/evaluate_pairs.py — 対コーパスの健全性と lint の弁別を測る。

出力(corpus/paired/<set>/report.md。数値だけで本文は含まない):
    1. 記憶の混入: AI 記事の文字 N-gram のうち、対になる human 記事にも現れる割合。
       2022年以前の人気記事は学習データに入っているはずなので、タイトルから
       覚えている本文を言い換えて返していないかを見る。閾値超えの対に印を付ける
    2. 文字数の追従: コードを除いた実測文字数 / 指示した文字数
    3. lint の検出器ごとの文書発火率(human と各モデル)。対の設計なので、
       同じ話題・同じ長さの human と比べた差がそのまま文体の差になる

使い方:
    uv run corpus/paired/evaluate_pairs.py --set tech-qiita
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "skills" / "natural-japanese" / "scripts"))
from lint import run_lint  # noqa: E402

NGRAM = 10
OVERLAP_FLAG = 0.05
FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.S)
FENCE_RE = re.compile(r"^\s*(```|~~~).*?^\s*(```|~~~)\s*$", re.M | re.S)


def body_of(path: Path) -> str:
    return FRONTMATTER_RE.sub("", path.read_text(encoding="utf-8"), count=1).lstrip("\n")


def meta_of(path: Path) -> dict:
    m = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
    meta = {}
    if m:
        for line in m.group(0).splitlines()[1:-1]:
            k, _, v = line.partition(": ")
            try:
                meta[k] = json.loads(v)
            except json.JSONDecodeError:
                meta[k] = v
    return meta


def prose(text: str) -> str:
    return re.sub(r"\s+", "", FENCE_RE.sub("", text))


def ngrams(s: str) -> set[str]:
    return {s[i : i + NGRAM] for i in range(len(s) - NGRAM + 1)}


def categories(text: str) -> set[str]:
    findings, _ = run_lint(text, genre="tech")
    return {f.category for f in findings}


def main() -> None:
    parser = argparse.ArgumentParser(description="対コーパスの評価")
    parser.add_argument("--set", default="tech-qiita")
    args = parser.parse_args()

    set_dir = HERE / args.set
    human = {p.stem: p for p in sorted((set_dir / "human").glob("*.md"))}
    models = sorted(p.name for p in (set_dir / "ai").iterdir() if p.is_dir())

    human_cats = {pid: categories(body_of(p)) for pid, p in human.items()}
    rows_overlap: dict[str, list[float]] = defaultdict(list)
    rows_len: dict[str, list[float]] = defaultdict(list)
    flagged: list[tuple[str, str, float]] = []
    ai_cats: dict[str, dict[str, set[str]]] = defaultdict(dict)

    for model in models:
        for p in sorted((set_dir / "ai" / model).glob("*.md")):
            pid = p.stem
            if pid not in human:
                continue
            ai_text = body_of(p)
            h_ng = ngrams(prose(body_of(human[pid])))
            a_ng = ngrams(prose(ai_text))
            ov = len(a_ng & h_ng) / len(a_ng) if a_ng else 0.0
            rows_overlap[model].append(ov)
            if ov > OVERLAP_FLAG:
                flagged.append((model, pid, ov))
            target = meta_of(p).get("target_chars")
            if target:
                rows_len[model].append(len(prose(ai_text)) / target)
            ai_cats[model][pid] = categories(ai_text)

    out = [f"# 対コーパス評価: {args.set}", ""]
    out.append(f"human {len(human)} 本、モデル {len(models)} 種。lint は `--genre tech` 相当。")
    out += ["", "## 1. 記憶の混入(AI 記事の文字10-gram のうち human 記事にも出る割合)", ""]
    out += ["| モデル | 対の数 | 中央値 | 最大 | 5%超の対 |", "|---|---|---|---|---|"]
    for m in models:
        v = rows_overlap[m]
        if v:
            n_flag = sum(1 for x in v if x > OVERLAP_FLAG)
            out.append(f"| {m} | {len(v)} | {statistics.median(v):.3f} | {max(v):.3f} | {n_flag} |")
    if flagged:
        out += ["", "5%超の対:", ""]
        out += [f"- {m} / {pid}: {ov:.3f}" for m, pid, ov in sorted(flagged, key=lambda x: -x[2])]

    out += ["", "## 2. 文字数の追従(コードを除いた実測 / 指示した文字数)", ""]
    out += ["| モデル | 中央値 | 最小 | 最大 |", "|---|---|---|---|"]
    for m in models:
        v = rows_len[m]
        if v:
            out.append(f"| {m} | {statistics.median(v):.2f} | {min(v):.2f} | {max(v):.2f} |")

    all_cats = sorted(set().union(*human_cats.values(), *(c for d in ai_cats.values() for c in d.values())))
    out += ["", "## 3. 検出器ごとの文書発火率", ""]
    out.append("同じ記事 ID の対だけで数える。human 列が FP 率、各モデル列が検出率にあたる。")
    out += ["", "| 検出器 | human | " + " | ".join(models) + " |", "|---|---|" + "---|" * len(models)]
    for c in all_cats:
        h = sum(1 for cs in human_cats.values() if c in cs) / len(human_cats)
        cells = []
        for m in models:
            d = ai_cats[m]
            cells.append(f"{sum(1 for cs in d.values() if c in cs) / len(d):.0%}" if d else "-")
        out.append(f"| {c} | {h:.0%} | " + " | ".join(cells) + " |")
    any_h = sum(1 for cs in human_cats.values() if cs) / len(human_cats)
    any_cells = [
        f"{sum(1 for cs in ai_cats[m].values() if cs) / len(ai_cats[m]):.0%}" if ai_cats[m] else "-" for m in models
    ]
    out.append(f"| (いずれか) | {any_h:.0%} | " + " | ".join(any_cells) + " |")

    report = set_dir / "report.md"
    report.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"-> {report}", file=sys.stderr)


if __name__ == "__main__":
    main()
