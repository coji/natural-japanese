# /// script
# requires-python = ">=3.11"
# ///
"""corpus/bench/pairwise_bench.py — モデル同士を直接比べる(ロードマップ S40)。

作者の版を基準にすると、作者の版が持っている情報(PR の再現手順など)や、作者の版の出来に結果が
引っ張られる。そこで同じ課題について、モデルの出力どうしを評価軸(rubric.md の A1〜A10)で比べる。
判定は、比べる2つのモデルのどちらとも系統が違う3つ目の系統のモデルが、並び順を入れ替えて2回行う
(食い違いは「差がない」)。課題ごとに、軸の票の差し引きで勝ち負けを決める。

出力: corpus/private/bench/pairwise.md(コミットしない)。判定は judge/ にキャッシュする

使い方:
    uv run corpus/bench/pairwise_bench.py --models claude-opus-5-5@low gpt-6-luna@low gemini-3.8-flash@low
"""
from __future__ import annotations

import argparse
import itertools
import json
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import evaluate_bench as ev

BENCH = ev.BENCH


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--parallel", type=int, default=6)
    a = ap.parse_args()
    ev.g.prepare_isolation()
    tasks = {p.parent.name: json.loads(p.read_text(encoding="utf-8")) for p in (BENCH / "tasks").glob("*/task.json")}

    jobs = []
    for m1, m2 in itertools.combinations(a.models, 2):
        fams = {ev.family(m1.split("@")[0]), ev.family(m2.split("@")[0])}
        judges = [f for f in ev.JUDGES if f not in fams]
        if not judges:
            continue
        jf = judges[0]
        for tid in tasks:
            p1, p2 = BENCH / "out" / m1 / f"{tid}.md", BENCH / "out" / m2 / f"{tid}.md"
            if not (p1.exists() and p2.exists()):
                continue
            t1, t2 = p1.read_text(encoding="utf-8"), p2.read_text(encoding="utf-8")
            for order in ("12", "21"):
                jobs.append((m1, m2, tid, jf, order, t1, t2))

    def run(j):
        m1, m2, tid, jf, order, t1, t2 = j
        jm, jfn = ev.JUDGES[jf]
        a_txt, b_txt = (t1, t2) if order == "12" else (t2, t1)
        prompt = ev.AXES_PROMPT.format(rubric=ev.RUBRIC, a=a_txt, b=b_txt, later="B")
        key = f"pair__{m1}__{m2}__{tid}__{jm}__{order}"
        return j, ev.cached(key, lambda: ev.parse_json(jfn(prompt, jm, "low")))

    res_by = defaultdict(dict)
    with ThreadPoolExecutor(a.parallel) as ex:
        for j, res in ex.map(run, jobs):
            print(f"{j[0]} vs {j[1]} {j[2]} {j[4]} {'ok' if res else 'FAIL'}", flush=True)
            if res:
                res_by[(j[0], j[1], j[2], j[3])][j[4]] = res

    def vote(orders: dict, ax: str) -> str:
        def side(order, b):
            if b not in ("A", "B"):
                return "tie"
            first_is_m1 = order == "12"
            return ("m1" if b == "A" else "m2") if first_is_m1 else ("m2" if b == "A" else "m1")
        v1 = side("12", orders["12"].get("axes", {}).get(ax, {}).get("better"))
        v2 = side("21", orders["21"].get("axes", {}).get(ax, {}).get("better"))
        return v1 if v1 == v2 else "tie"

    kinds = sorted({t["kind"] for t in tasks.values()})
    names = {ax: re.search(rf"\| {ax} ([^|]+) \|", ev.RUBRIC).group(1).strip() for ax in ev.AXES}
    out = ["# モデル同士の直接比較(S40)", "",
           "判定は比べる2モデルのどちらとも系統が違うモデル。並び順を入れ替えて2回、食い違いは「差がない」。"
           "課題ごとに軸の票の差し引きで勝ち負けを決める(左のモデルの 勝ち / 引き分け / 負け)。", ""]
    out += ["| 対戦 | 判定 | 全体 | " + " | ".join(kinds) + " |", "|---|---|---|" + "---|" * len(kinds)]
    axis_rows = defaultdict(Counter)
    for m1, m2 in itertools.combinations(a.models, 2):
        per = defaultdict(Counter)
        jname = ""
        for (x1, x2, tid, jf), orders in res_by.items():
            if (x1, x2) != (m1, m2) or len(orders) < 2:
                continue
            jname = ev.JUDGES[jf][0]
            votes = Counter(vote(orders, ax) for ax in ev.AXES)
            net = votes["m1"] - votes["m2"]
            r = "win" if net > 0 else "loss" if net < 0 else "tie"
            per["全体"][r] += 1
            per[tasks[tid]["kind"]][r] += 1
            for ax in ev.AXES:
                axis_rows[(m1, m2, ax)][vote(orders, ax)] += 1
        if per:
            fmt = lambda c: f"{c['win']}/{c['tie']}/{c['loss']}"
            out.append(f"| {m1} vs {m2} | {jname} | {fmt(per['全体'])} | " + " | ".join(fmt(per[k]) for k in kinds) + " |")
    out += ["", "## 軸ごと(左のモデルがよい / 差がない / 右のモデルがよい)", ""]
    pairs = list(itertools.combinations(a.models, 2))
    out += ["| 軸 | " + " | ".join(f"{m1} vs {m2}" for m1, m2 in pairs) + " |", "|---|" + "---|" * len(pairs)]
    for ax in ev.AXES:
        cells = [f"{axis_rows[(m1, m2, ax)]['m1']} / {axis_rows[(m1, m2, ax)]['tie']} / {axis_rows[(m1, m2, ax)]['m2']}" for m1, m2 in pairs]
        out.append(f"| {ax} {names[ax]} | " + " | ".join(cells) + " |")
    (BENCH / "pairwise.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
