# /// script
# requires-python = ">=3.11"
# ///
"""corpus/selfcorpus/judge_axes.py — 前後の対を、読みやすさの評価軸ごとに判定する(ロードマップ S30)。

軸の定義は corpus/selfcorpus/rubric.md。推敲に使ったモデル(Claude)と別系統の2モデル
(gpt-6-luna・gemini-3.8-flash)に、同じ対を並び順を入れ替えて2回ずつ判定させる。

入力: corpus/private/skill-apply/<id>/before.md, after.md
出力: corpus/private/skill-apply/<id>/judge-<model>-<order>.json と、全体の集計
      corpus/private/skill-apply/judge-summary.md(コミットしない)

使い方:
    uv run corpus/selfcorpus/judge_axes.py [--parallel 4]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "corpus"))
import generate as g  # noqa: E402

DIR = ROOT / "corpus/private/skill-apply"
RUBRIC = (ROOT / "corpus/selfcorpus/rubric.md").read_text(encoding="utf-8")
AXES = ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "A10"]
JUDGES = {"gpt-6-luna": g.run_codex, "gemini-3.8-flash": g.run_agy}

PROMPT = """あなたは日本語の文章の編集者です。同じ内容の文書の2つの版(A と B)を、次の評価軸の定義だけに照らして比べてください。好みではなく定義で判断します。

{rubric}

## 出力
次の JSON だけを出力してください(コードブロックや説明は不要)。
{{
  "axes": {{
    "A1": {{"better": "A" または "B" または "tie", "reason": "1文", "evidence": "根拠の短い引用"}},
    ... A1〜A10 のすべて
  }},
  "A11": {{"version": "{later}", "preservation": "保っている" または "一部崩れている" または "大きく崩れている", "reason": "1文"}}
}}
A11 は版 {later} について、もう一方の版の内容(事実・数値・固有名詞・判断)を保っているか、元にない内容を足していないかを判定してください。

## 版 A
{a}

## 版 B
{b}
"""


def parse_json(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def judge(pair: Path, model: str, order: str, before_name: str = "before.md", after_name: str = "after.md") -> tuple[str, str, str, dict | None]:
    suffix = "" if (before_name, after_name) == ("before.md", "after.md") else f"-{Path(before_name).stem}-vs-{Path(after_name).stem}"
    out = pair / f"judge-{model}-{order}{suffix}.json"
    if out.exists():
        return pair.name, model, order, json.loads(out.read_text(encoding="utf-8"))
    before = (pair / before_name).read_text(encoding="utf-8")
    after = (pair / after_name).read_text(encoding="utf-8")
    # order "ba": A=前・B=後 / "ab": A=後・B=前
    a, b, later = (before, after, "B") if order == "ba" else (after, before, "A")
    prompt = PROMPT.format(rubric=RUBRIC, a=a, b=b, later=later)
    res = None
    for _ in range(2):
        try:
            res = parse_json(JUDGES[model](prompt, model, "low"))
        except Exception as e:  # noqa: BLE001
            print(f"  ERR {pair.name} {model} {order}: {e}", file=sys.stderr)
        if res:
            break
    if res:
        out.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return pair.name, model, order, res


def to_after(order: str, better: str) -> str:
    """判定を「後の版がよい / 前の版がよい / 差がない」に直す。"""
    if better not in ("A", "B"):
        return "tie"
    after_label = "B" if order == "ba" else "A"
    return "after" if better == after_label else "before"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--before", default="before.md", help="前の版として比べるファイル名")
    ap.add_argument("--after", default="after.md", help="後の版として比べるファイル名")
    args = ap.parse_args()
    pairs = sorted(p for p in DIR.iterdir() if (p / args.after).exists() and (p / args.before).exists())
    jobs = [(p, m, o, args.before, args.after) for p in pairs for m in JUDGES for o in ("ba", "ab")]
    results = []
    with ThreadPoolExecutor(args.parallel) as ex:
        for r in ex.map(lambda j: judge(*j), jobs):
            results.append(r)
            print(f"{r[0]} {r[1]} {r[2]} {'ok' if r[3] else 'FAIL'}", flush=True)

    # 対×モデルごとに、2つの並び順の判定を合わせる(食い違ったら tie)
    verdict: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    preservation: Counter = Counter()
    by = defaultdict(dict)
    for name, model, order, res in results:
        if res:
            by[(name, model)][order] = res
    for (name, model), orders in by.items():
        if len(orders) < 2:
            continue
        for ax in AXES:
            v1 = to_after("ba", orders["ba"].get("axes", {}).get(ax, {}).get("better", "tie"))
            v2 = to_after("ab", orders["ab"].get("axes", {}).get(ax, {}).get("better", "tie"))
            verdict[(name, model)][ax] = v1 if v1 == v2 else "tie"
        for o in orders.values():
            preservation[o.get("A11", {}).get("preservation", "不明")] += 1

    names = {ax: re.search(rf"\| {ax} ([^|]+) \|", RUBRIC).group(1).strip() for ax in AXES}
    out = ["# 読みやすさの評価軸ごとの判定(S30)", "", f"前の版: {args.before} / 後の版: {args.after}", ""]
    out.append(f"対の数 {len(pairs)}、判定モデル {', '.join(JUDGES)}、各対を並び順を入れ替えて2回判定(食い違いは「差がない」)。")
    out += ["", "## 軸ごと(後の版がよい / 差がない / 前の版がよい、対×モデルの数)", ""]
    out += ["| 軸 | " + " | ".join(f"{m}" for m in JUDGES) + " | 2モデルが一致した対 |", "|---|" + "---|" * (len(JUDGES) + 1)]
    for ax in AXES:
        cells = []
        for m in JUDGES:
            c = Counter(v[ax] for (n, mm), v in verdict.items() if mm == m and ax in v)
            cells.append(f"{c['after']} / {c['tie']} / {c['before']}")
        agree = sum(
            1 for p in pairs
            if all((p.name, m) in verdict for m in JUDGES)
            and len({verdict[(p.name, m)][ax] for m in JUDGES}) == 1
        )
        out.append(f"| {ax} {names[ax]} | " + " | ".join(cells) + f" | {agree} |")
    out += ["", "## 内容の保持(A11、全判定)", ""]
    out += [f"- {k}: {v}" for k, v in preservation.most_common()]
    summary = "judge-summary.md" if (args.before, args.after) == ("before.md", "after.md") else f"judge-summary-{Path(args.before).stem}-vs-{Path(args.after).stem}.md"
    (DIR / summary).write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
