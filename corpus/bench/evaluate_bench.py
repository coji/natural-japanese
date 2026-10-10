# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "sudachipy>=0.6.8",
#     "sudachidict-core>=20240409",
# ]
# ///
"""corpus/bench/evaluate_bench.py — ベンチの生成結果を評価し、成績表を出す(ロードマップ S40)。

モデルごと(model@effort)に、次を出す。
    1. 読みやすさ: 評価軸(corpus/selfcorpus/rubric.md の A1〜A10)で、作者の版(推敲課題では元の文書)と
       対にして比べる。判定は評価対象と別系統の2モデルが、並び順を入れ替えて2回ずつ行い、
       食い違いは「差がない」とする
    2. 事実の正確さ: 材料にある大事な事実の抜け、材料にない事実の追加を、別系統の1モデルが数える
    3. AI 時代の癖: 検証済みの語彙(1,000字あたり)、ダッシュ、太字、箇条書きの行の割合
    4. 分量: 作者の版に対する文字数の比

判定結果はキャッシュする(corpus/private/bench/judge/)。新しいモデルを足しても、既存の判定は再利用される。
出力: corpus/private/bench/scorecard.md(作者の文書の数値を含むのでコミットしない)

使い方:
    uv run corpus/bench/evaluate_bench.py [--parallel 4]
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "corpus"))
sys.path.insert(0, str(ROOT / "corpus/selfcorpus"))
sys.path.insert(0, str(ROOT / "corpus/timeslice"))
import generate as g  # noqa: E402
from features import features  # noqa: E402
sys.path.insert(0, str(ROOT / "skills/natural-japanese/scripts"))
from textcore import mask_markdown_structure  # noqa: E402
from judge_axes import AXES, PROMPT as AXES_PROMPT, RUBRIC, parse_json  # noqa: E402

BENCH = ROOT / "corpus/private/bench"
JUDGE_DIR = BENCH / "judge"
WORDS = ["瞬間", "境界", "守る", "任せる", "上限", "本番", "土台", "道具", "届く", "自然", "セッション",
         "たび", "検証", "明示", "基準", "残る", "明確", "つながる", "応答", "履歴", "習慣", "効く", "壊れる"]
# 判定に使うモデル(系統ごとに1つ)。評価対象と同じ系統は判定に使わない
JUDGES = {"claude": ("claude-sonnet-5-5", g.run_claude), "gpt": ("gpt-6-luna", g.run_codex), "gemini": ("gemini-3.8-flash", g.run_agy)}

FACTS_PROMPT = """次の「材料」と、それをもとに書かれた「文書」を比べてください。
- missing: 材料にある大事な事実・数値・決定事項のうち、文書に書かれていないもの
- unsupported: 文書が書き足した、材料からは言えない断定(数値、評価、比較、原因、顧客や人物の描写、予定の確定など)。読み手が事実として受け取ってしまうもの
- illustrative: 説明をわかりやすくするために足した例や補足(コードの置き場所の例、一般的な使い方の例など)。事実の断定ではないもの
次の JSON だけを出力してください。
{{"missing": ["…"], "unsupported": ["…"], "illustrative": ["…"]}}

## 材料
{materials}

## 文書
{doc}
"""


def family(model: str) -> str:
    return "claude" if model.startswith("claude") else "gpt" if model.startswith("gpt") else "gemini"


def cached(key: str, fn) -> dict | None:
    p = JUDGE_DIR / f"{key}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    res = None
    for _ in range(2):
        try:
            res = fn()
        except Exception as e:  # noqa: BLE001
            print(f"  ERR {key}: {e}", file=sys.stderr)
        if res:
            break
    if res:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res


def judge_axes(model_key: str, task_id: str, judge_fam: str, order: str, gen: str, ref: str) -> dict | None:
    jm, jfn = JUDGES[judge_fam]
    # order "rg": A=作者の版・B=生成 / "gr": A=生成・B=作者の版
    a, b, later = (ref, gen, "B") if order == "rg" else (gen, ref, "A")
    prompt = AXES_PROMPT.format(rubric=RUBRIC, a=a, b=b, later=later)
    return cached(f"axes__{model_key}__{task_id}__{jm}__{order}", lambda: parse_json(jfn(prompt, jm, "low")))


def judge_facts(model_key: str, task_id: str, judge_fam: str, materials: str, gen: str) -> dict | None:
    jm, jfn = JUDGES[judge_fam]
    prompt = FACTS_PROMPT.format(materials=materials, doc=gen)
    return cached(f"facts2__{model_key}__{task_id}__{jm}", lambda: parse_json(jfn(prompt, jm, "low")))


def gen_wins(order: str, better: str) -> str:
    if better not in ("A", "B"):
        return "tie"
    gen_label = "B" if order == "rg" else "A"
    return "gen" if better == gen_label else "ref"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parallel", type=int, default=4)
    a = ap.parse_args()
    g.prepare_isolation()
    tasks = {p.parent.name: json.loads(p.read_text(encoding="utf-8")) for p in (BENCH / "tasks").glob("*/task.json")}
    models = sorted(p.name for p in (BENCH / "out").iterdir() if p.is_dir())

    jobs = []
    for mk in models:
        fam = family(mk.split("@")[0])
        others = [f for f in JUDGES if f != fam]
        for tid in tasks:
            gp = BENCH / "out" / mk / f"{tid}.md"
            if not gp.exists():
                continue
            gen = gp.read_text(encoding="utf-8")
            ref = (BENCH / "tasks" / tid / "reference.md").read_text(encoding="utf-8")
            mat = (BENCH / "tasks" / tid / "materials.md").read_text(encoding="utf-8")
            for jf in others:
                for order in ("rg", "gr"):
                    jobs.append(("axes", mk, tid, jf, order, gen, ref))
            jobs.append(("facts", mk, tid, others[0], None, gen, mat))

    def run(j):
        kind, mk, tid, jf, order, gen, other = j
        if kind == "axes":
            return j, judge_axes(mk, tid, jf, order, gen, other)
        return j, judge_facts(mk, tid, jf, other, gen)

    results = []
    with ThreadPoolExecutor(a.parallel) as ex:
        for j, res in ex.map(run, jobs):
            results.append((j, res))
            print(f"{j[0]} {j[1]} {j[2]} {j[3]} {j[4] or ''} {'ok' if res else 'FAIL'}", flush=True)

    # 集計
    axes_by = defaultdict(lambda: defaultdict(dict))  # mk -> (tid, judge) -> order -> res
    facts_by = defaultdict(dict)
    facts_judge = {}
    for (kind, mk, tid, jf, order, _, _), res in results:
        if not res:
            continue
        if kind == "axes":
            axes_by[mk][(tid, jf)][order] = res
        else:
            facts_by[mk][tid] = res
            facts_judge[mk] = JUDGES[jf][0]

    def axis_vote(orders: dict, ax: str) -> str:
        v1 = gen_wins("rg", orders["rg"].get("axes", {}).get(ax, {}).get("better", "tie"))
        v2 = gen_wins("gr", orders["gr"].get("axes", {}).get(ax, {}).get("better", "tie"))
        return v1 if v1 == v2 else "tie"

    def axes_for(tid: str) -> list[str]:
        # PR の作者の版には差分にない文脈(再現手順・検証結果など)が入るため、
        # 具体性(A6)と条件の位置(A10)は PR の集計から外す
        return [ax for ax in AXES if not (tasks[tid]["kind"] == "pr" and ax in ("A6", "A10"))]

    def a11(res: dict) -> str | None:
        # 判定モデルによっては A11 を axes の中に書くので、両方を見る
        x = res.get("A11") or res.get("axes", {}).get("A11") or {}
        return x.get("preservation")

    out = ["# モデル評価ベンチの成績表(S40)", ""]
    out.append(f"課題 {len(tasks)} 本({dict(Counter(t['kind'] for t in tasks.values()))})。"
               "読みやすさは作者の版(推敲課題は元の文書)との対比較で、評価対象と別系統の2モデルが並び順を入れ替えて判定。"
               "PR では具体性(A6)と条件の位置(A10)を集計から外す。")

    # 課題単位: 課題×判定モデルごとに、軸の票(生成がよい − 作者の版がよい)の符号で勝ち負けを決める
    out += ["", "## 課題単位の勝ち負け(作者の版に対して 勝ち / 引き分け / 負け)", ""]
    judge_names = sorted({jf for mk in models for (_, jf) in axes_by[mk]})
    kinds = sorted({t["kind"] for t in tasks.values()})
    out += ["| モデル | 判定モデル | 全体 | " + " | ".join(kinds) + " |", "|---|---|---|" + "---|" * len(kinds)]
    for mk in models:
        for jf in judge_names:
            per_kind = defaultdict(Counter)
            for (tid, j), orders in axes_by[mk].items():
                if j != jf or len(orders) < 2:
                    continue
                votes = Counter(axis_vote(orders, ax) for ax in axes_for(tid))
                net = votes["gen"] - votes["ref"]
                res = "win" if net > 0 else "loss" if net < 0 else "tie"
                per_kind["全体"][res] += 1
                per_kind[tasks[tid]["kind"]][res] += 1
            if not per_kind:
                continue
            fmt = lambda c: f"{c['win']}/{c['tie']}/{c['loss']}"
            out.append(f"| {mk} | {JUDGES[jf][0]} | {fmt(per_kind['全体'])} | " + " | ".join(fmt(per_kind[k]) for k in kinds) + " |")

    out += ["", "## 軸ごと(生成がよい / 差がない / 作者の版がよい。課題×判定モデルの数)", ""]
    names = {ax: re.search(rf"\| {ax} ([^|]+) \|", RUBRIC).group(1).strip() for ax in AXES}
    out += ["| 軸 | " + " | ".join(models) + " |", "|---|" + "---|" * len(models)]
    for ax in AXES:
        cells = []
        for mk in models:
            c = Counter()
            for (tid, jf), orders in axes_by[mk].items():
                if len(orders) < 2 or ax not in axes_for(tid):
                    continue
                c[axis_vote(orders, ax)] += 1
            cells.append(f"{c['gen']} / {c['tie']} / {c['ref']}")
        out.append(f"| {ax} {names[ax]} | " + " | ".join(cells) + " |")

    out += ["", "## 推敲課題の内容の保持(判定の数)", "", "| モデル | 保っている | 一部崩れている | 大きく崩れている |", "|---|---|---|---|"]
    for mk in models:
        c = Counter()
        for (tid, jf), orders in axes_by[mk].items():
            if tasks[tid]["kind"] != "polish":
                continue
            for res in orders.values():
                c[a11(res)] += 1
        out.append(f"| {mk} | {c['保っている']} | {c['一部崩れている']} | {c['大きく崩れている']} |")

    out += ["", "## 事実の正確さ(課題あたりの平均件数。判定モデルが違う行どうしは比べられない)", "",
            "| モデル | 判定モデル | 抜け | 材料にない断定 | 説明のための例 |", "|---|---|---|---|---|"]
    for mk in models:
        fs = facts_by[mk].values()
        if fs:
            out.append(
                f"| {mk} | {facts_judge.get(mk, '')} | {statistics.fmean(len(f.get('missing', [])) for f in fs):.1f} "
                f"| {statistics.fmean(len(f.get('unsupported', [])) for f in fs):.1f} "
                f"| {statistics.fmean(len(f.get('illustrative', [])) for f in fs):.1f} |"
            )

    # 機械的な指標(判定モデルに依らない)
    def sentences(text: str) -> list[str]:
        masked = mask_markdown_structure(re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S))
        return [x.strip() for x in re.split(r"[。！？\n]", masked) if len(x.strip()) >= 5]

    def ngrams(t: str, n: int = 6) -> set[str]:
        t = re.sub(r"\s+", "", t)
        return {t[i:i + n] for i in range(len(t) - n + 1)}

    out += ["", "## 機械的な指標(判定モデルに依らない)", "",
            "| モデル | 文の長さ 中央値 | 60字超の文 | 語彙(地の文1,000字あたり) | ダッシュ(本文1,000字あたり) | 太字(同) | 箇条書きの行 | 文字数の比(作者の版=1) | 推敲での元文との一致率 |",
            "|---|---|---|---|---|---|---|---|---|"]
    ref_sents = [len(x) for tid in tasks for x in sentences((BENCH / "tasks" / tid / "reference.md").read_text(encoding="utf-8"))]
    out_rows = []
    for mk in models:
        fs, ratios, sl, overlap = [], [], [], []
        total = 0
        for tid in tasks:
            gp = BENCH / "out" / mk / f"{tid}.md"
            if not gp.exists():
                continue
            gen = gp.read_text(encoding="utf-8")
            ref = (BENCH / "tasks" / tid / "reference.md").read_text(encoding="utf-8")
            fs.append(features(gen))
            ratios.append(len(gen) / max(len(ref), 1))
            total += len(gen)
            sl += [len(x) for x in sentences(gen)]
            if tasks[tid]["kind"] == "polish":
                rg = ngrams(ref)
                overlap.append(len(ngrams(gen) & rg) / max(len(rg), 1))
        chars = sum(f["prose_chars"] for f in fs) / 1000 or 1
        total = total / 1000 or 1
        vocab = sum(sum(f["lemmas"].get(w, 0) for w in WORDS) for f in fs) / chars
        out_rows.append(
            f"| {mk} | {statistics.median(sl):.0f} | {sum(x > 60 for x in sl) / len(sl):.0%} | {vocab:.2f} "
            f"| {sum(f['dashes'] for f in fs)/total:.2f} | {sum(f['bold'] for f in fs)/total:.2f} "
            f"| {sum(f['list_lines'] for f in fs)/max(sum(f['nonblank_lines'] for f in fs),1):.2f} | {statistics.median(ratios):.2f} "
            f"| {statistics.fmean(overlap):.2f} |" if overlap else ""
        )
        if not overlap:
            out_rows[-1] = out_rows[-1].rstrip() + " - |"
    out += out_rows
    out.append(f"| (作者の版) | {statistics.median(ref_sents):.0f} | {sum(x > 60 for x in ref_sents) / len(ref_sents):.0%} | | | | | 1.00 | |")
    (BENCH / "scorecard.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
