# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "sudachipy>=0.6.8",
#     "sudachidict-core>=20240409",
# ]
# ///
"""corpus/paired/evaluate_conditions.py — 生成条件を比べる(ロードマップ S6)。

同じセット・同じモデルで、生成条件(title / materials / polish)ごとに次を比べる。
比べるのは、指定したモデルすべてでその条件の記事がそろっている記事 ID だけ。

    1. S4 の語彙候補(上位)と「実測」「静か」の 1,000字あたりの出現率
    2. 構造の特徴(太字・ダッシュの 1,000字あたり件数、「まとめ」見出しの割合)
    3. lint の検出器ごとの文書発火率
    4. polish 条件だけ: 元の human 記事では反応せず、推敲後に反応した検出器の割合
       (軽い推敲で検出器が反応するかを見る。ROADMAP.md の仮説 H6)

出力: corpus/paired/<set>/conditions.md(数値のみ)

使い方:
    uv run corpus/paired/evaluate_conditions.py --set tech-qiita \
        --models claude-opus-5-5 gpt-6.1-sol gemini-3.8-flash
"""

from __future__ import annotations

import argparse
import gzip
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "skills" / "natural-japanese" / "scripts"))
sys.path.insert(0, str(HERE))
from evaluate_pairs import body_of  # noqa: E402
from lint import run_lint  # noqa: E402

FEATURES = ROOT / "corpus" / "timeslice" / "qiita-aug" / "data"
WORDS = ["瞬間", "効く", "境界", "守る", "止まる", "上限", "判断", "土台", "壊れる", "道具", "実測", "静か"]
CONDITIONS = {"title": "ai", "materials": "ai-materials", "polish": "ai-polish"}


def main() -> None:
    parser = argparse.ArgumentParser(description="生成条件の比較")
    parser.add_argument("--set", default="tech-qiita")
    parser.add_argument("--models", nargs="+", required=True)
    args = parser.parse_args()
    set_dir = HERE / args.set

    with gzip.open(FEATURES / f"features-paired-{args.set}.jsonl.gz", "rt", encoding="utf-8") as f:
        feats = {(r["group"], r["id"]): r for r in map(json.loads, f)}

    def group_name(cond: str, model: str) -> str:
        return model if cond == "title" else f"{cond}/{model}"

    # 条件ごとに、全モデルでそろっている記事 ID
    common: dict[str, list[str]] = {}
    for cond, sub in CONDITIONS.items():
        ids = None
        for m in args.models:
            d = set_dir / sub / m
            got = {p.stem for p in d.glob("*.md")} if d.exists() else set()
            ids = got if ids is None else ids & got
        common[cond] = sorted(ids or [])

    out = [f"# 生成条件の比較(S6): {args.set}", ""]
    out.append(f"モデル: {', '.join(args.models)}。各条件で全モデルがそろった記事だけを比べる。")
    out.append("human 列は、その条件で比べた記事 ID の元の human 記事。")
    out += ["", "| 条件 | 記事数 |", "|---|---|"]
    out += [f"| {c} | {len(ids)} |" for c, ids in common.items()]

    # 1, 2: 語彙と構造(1,000字あたり)
    out += ["", "## 語彙と構造(1,000字あたり。「まとめ」は記事の割合)", ""]
    cols = WORDS + ["太字", "ダッシュ", "「まとめ」"]
    out += ["| 条件 | 書き手 | " + " | ".join(cols) + " |", "|---|---|" + "---|" * len(cols)]
    for cond, ids in common.items():
        if not ids:
            continue
        for who in ["human"] + args.models:
            rows = [feats.get(("human" if who == "human" else group_name(cond, who), i)) for i in ids]
            rows = [r for r in rows if r]
            chars = sum(r["prose_chars"] for r in rows) / 1000
            cells = [f"{sum(r['lemmas'].get(w, 0) for r in rows) / chars:.2f}" for w in WORDS]
            cells.append(f"{sum(r['bold'] for r in rows) / chars:.2f}")
            cells.append(f"{sum(r['dashes'] for r in rows) / chars:.2f}")
            cells.append(f"{statistics.fmean(float(r['summary_heading']) for r in rows):.0%}")
            out.append(f"| {cond} | {who} | " + " | ".join(cells) + " |")

    # 3, 4: lint の検出器
    def cats(path: Path) -> set[str]:
        findings, _ = run_lint(body_of(path), genre="tech")
        return {f.category for f in findings}

    human_cats = {i: cats(set_dir / "human" / f"{i}.md") for ids in common.values() for i in ids}
    rates: dict[tuple[str, str], dict[str, float]] = {}
    new_in_polish: dict[str, dict[str, float]] = {}
    all_cats: set[str] = set().union(*human_cats.values()) if human_cats else set()
    for cond, sub in CONDITIONS.items():
        ids = common[cond]
        if not ids:
            continue
        rates[(cond, "human")] = {}
        for m in args.models:
            per_doc = {i: cats(set_dir / sub / m / f"{i}.md") for i in ids}
            all_cats |= set().union(*per_doc.values())
            counts: dict[str, int] = defaultdict(int)
            new: dict[str, int] = defaultdict(int)
            for i, cs in per_doc.items():
                for c in cs:
                    counts[c] += 1
                    if c not in human_cats[i]:
                        new[c] += 1
            rates[(cond, m)] = {c: n / len(ids) for c, n in counts.items()}
            if cond == "polish":
                new_in_polish[m] = {c: n / len(ids) for c, n in new.items()}
        hc: dict[str, int] = defaultdict(int)
        for i in ids:
            for c in human_cats[i]:
                hc[c] += 1
        rates[(cond, "human")] = {c: n / len(ids) for c, n in hc.items()}

    keys = list(rates)
    out += ["", "## lint の検出器ごとの文書発火率", ""]
    out += ["| 検出器 | " + " | ".join(f"{c}/{w}" for c, w in keys) + " |", "|---|" + "---|" * len(keys)]
    for c in sorted(all_cats):
        out.append(f"| {c} | " + " | ".join(f"{rates[k].get(c, 0):.0%}" for k in keys) + " |")

    if new_in_polish:
        out += ["", "## 推敲で新たに反応した検出器(元の human 記事では反応していなかった記事の割合)", ""]
        out += ["| 検出器 | " + " | ".join(args.models) + " |", "|---|" + "---|" * len(args.models)]
        for c in sorted(all_cats):
            out.append(f"| {c} | " + " | ".join(f"{new_in_polish.get(m, {}).get(c, 0):.0%}" for m in args.models) + " |")

    report = set_dir / "conditions.md"
    report.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
