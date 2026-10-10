# /// script
# requires-python = ">=3.11"
# dependencies = ["sudachipy>=0.6.8", "sudachidict-core>=20240409"]
# ///
"""corpus/llmjp/burstiness_by_type.py — low_burstiness の誤検知を文書の種類別に測り、閾値ごとの反応率を出す。

人間側: LLM-jp 由来の基準データ(スコア 0.7 以上)を URL から推定した種類別に。
AI 側: モデル評価ベンチで書かせた顧客向け文書(report 課題)と、Zenn 記事(article 課題)。
lint の burstiness の値そのものを取り出し、閾値を動かしたときの反応率を並べる。

出力: corpus/llmjp/burstiness-by-type.md(数値のみ)
"""
from __future__ import annotations
import json, random, re, sys
from collections import defaultdict
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "skills/natural-japanese/scripts"))
sys.path.insert(0, str(HERE))
from lint import run_lint  # noqa: E402
from label_sample import trim  # noqa: E402

THRESHOLDS = [-0.24, -0.30, -0.35, -0.40]

def burst(text: str) -> tuple[float | None, int]:
    _, stats = run_lint(text)
    r = stats.get("rhythm") or {}
    return r.get("burstiness"), stats.get("total_sentences", 0)

def main() -> None:
    groups: dict[str, list[tuple[float, int]]] = defaultdict(list)
    rows = [json.loads(l) for f in sorted((ROOT / "corpus/private/llmjp").glob("*.scored.jsonl")) for l in open(f, encoding="utf-8")]
    pool = [r for r in rows if r["score"] >= 0.7]
    rng = random.Random(0)
    by_type = defaultdict(list)
    for r in pool:
        by_type[r["type"]].append(r)
    for t, rs in by_type.items():
        for r in rng.sample(rs, min(150, len(rs))):
            b, n = burst(trim(r["text"]))
            if b is not None:
                groups[f"人間: {t}"].append((b, n))
    bench = ROOT / "corpus/private/bench"
    for p in sorted((bench / "out").glob("*@low/*.md")):
        kind = p.stem.split("-")[0]
        if kind not in ("report", "article"):
            continue
        b, n = burst(p.read_text(encoding="utf-8"))
        if b is not None:
            groups[f"AI {p.parent.name.split('@')[0]}: {kind}"].append((b, n))
    out = ["# low_burstiness の反応率(閾値別・文書の種類別)", "",
           "人間は LLM-jp 由来の基準データ(スコア 0.7 以上、種類ごとに最大150本)。AI はベンチの生成(effort low)。",
           "値は burstiness が閾値未満の文書の割合。括弧内は文が20以上の文書に限った割合。", ""]
    out += ["| 群 | n | " + " | ".join(str(t) for t in THRESHOLDS) + " |", "|---|---|" + "---|" * len(THRESHOLDS)]
    for g in sorted(groups):
        v = groups[g]
        long = [x for x in v if x[1] >= 20]
        cells = []
        for t in THRESHOLDS:
            a = sum(b < t for b, _ in v) / len(v)
            l = sum(b < t for b, _ in long) / len(long) if long else float("nan")
            cells.append(f"{a:.0%} ({l:.0%})")
        out.append(f"| {g} | {len(v)} | " + " | ".join(cells) + " |")
    (HERE / "burstiness-by-type.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))

if __name__ == "__main__":
    main()
