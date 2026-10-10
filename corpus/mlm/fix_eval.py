# /// script
# requires-python = ">=3.11"
# dependencies = ["torch", "transformers>=4.44", "fugashi", "unidic-lite"]
# ///
"""corpus/mlm/fix_eval.py — 直し方の分担(AI が言い換えを出し、AI 以前のモデルが選ぶ)を確かめる。

judge_flags.py で、判定モデル(LLM)は AI 時代の言い回しを不自然と感じないことが分かった。
そこで役割を分ける:
    AI(claude)      意味を保つ言い換えを5つ出す。専門用語や文字どおりの意味なら「変えない」と答える
    モデル A・B     候補を入れた文の自然さを、AI 以前のモデル A で測り、AI 時代のモデル B との差で
                    AI 時代の語を外して、1つ選ぶ(suggest.Suggester.rank)
比べるもの:
    - AI の1番目の候補 と モデルが選んだ候補 の、AI 時代らしさ(B − A の差の変化)
    - 意味が保たれたか(gpt-6-luna に元の文と比べさせる。意味の判定は LLM でもできる)

出力: corpus/private/mlm/fix-eval.jsonl、corpus/mlm/fix-eval.md(数値のみ。コミットする)

使い方: uv run corpus/mlm/fix_eval.py [--n 60]
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PRIV = ROOT / "corpus/private/mlm"
sys.path.insert(0, str(ROOT / "corpus"))
sys.path.insert(0, str(HERE))
import generate as g  # noqa: E402

BATCH = 10
PROPOSE = """次の各文の【】の部分を、意味を変えずに、日本語でふつうに使う言い方に言い換える候補を5つ出してください。

- 候補は【】の部分をそのまま置き換えられる形にする(活用も前後に合わせる)
- 意味・言い切りの強さ・対象の範囲を変えない。文脈にない事実を足さない
- 【】が専門用語・固有の名前・文字どおりの意味で、言い換える必要がないなら keep を true にする

次の JSON 配列だけを出力してください: [{{"id": "...", "keep": false, "cands": ["...", "...", "...", "...", "..."]}}, ...]

{items}
"""
MEANING = """各件について、「元の文」と「書き直した文」の意味が同じかを判定してください。

- same: 同じ / 少し変わる / 変わる

次の JSON 配列だけを出力してください: [{{"id": "...", "same": "同じ"}}, ...]

{items}
"""


def parse(out: str) -> list[dict]:
    m = re.search(r"\[.*\]", out, re.S)
    try:
        return json.loads(m.group(0)) if m else []
    except json.JSONDecodeError:
        return []


def collect(n: int) -> list[dict]:
    rng = random.Random(1)
    pool = []
    for name in ("self", "qiita2026", "generated_holdout"):
        for l in open(PRIV / f"scores-{name}.jsonl", encoding="utf-8"):
            r = json.loads(l)
            for w in r["words"]:
                if w["d"] > 4 and not re.fullmatch(r"[ァ-ヶー・]+", w["w"]) and "-" not in w["lemma"] \
                        and not re.search(r"[A-Za-z]", w["w"]) and r["s"].count(w["w"]) == 1:
                    pool.append({"set": name, "s": r["s"], "w": w["w"], "lemma": w["lemma"], "d": w["d"]})
    rng.shuffle(pool)
    seen, out = Counter(), []
    for it in sorted(pool, key=lambda x: x["set"] != "self"):  # 作者の文書を先に
        if seen[it["lemma"]] >= 2:
            continue
        seen[it["lemma"]] += 1
        out.append(it)
        if len(out) >= n:
            break
    for i, it in enumerate(out):
        it["id"] = f"f{i}"
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60)
    a = ap.parse_args()
    g.prepare_isolation()
    path = PRIV / "fix-eval.jsonl"
    if path.exists():
        items = [json.loads(l) for l in open(path, encoding="utf-8")]
    else:
        items = collect(a.n)
        # 1. AI に候補を出させる
        for k in range(0, len(items), BATCH):
            batch = items[k:k + BATCH]
            body = "\n\n".join(f"### id: {it['id']}\n{it['s'].replace(it['w'], '【' + it['w'] + '】', 1)}" for it in batch)
            rows = {r.get("id"): r for r in parse(g.run_claude(PROPOSE.format(items=body), "opus", "low"))}
            for it in batch:
                r = rows.get(it["id"], {})
                it["keep"] = bool(r.get("keep"))
                it["cands"] = [c for c in r.get("cands", []) if isinstance(c, str) and c and c != it["w"]][:5]
            print(f"候補: {k + len(batch)} 件", flush=True)
        # 2. モデルで並べる
        from suggest import Suggester
        sg = Suggester()
        for it in items:
            if it["keep"] or not it["cands"]:
                continue
            ranked = sg.rank(it["s"], it["w"], it["cands"])
            it["ranked"] = ranked
            it["llm_first"] = next(r for r in ranked if r["cand"] == it["cands"][0])
            it["model_pick"] = ranked[0]
        with open(path, "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
    # 3. 意味の判定(AI の1番目とモデルが選んだもの)
    todo = [it for it in items if "ranked" in it and "same_model" not in it]
    home = g.ISOLATION_DIR / "codex-home-fix"
    home.mkdir(parents=True, exist_ok=True)
    (home / "auth.json").write_bytes((g.CODEX_HOME / "auth.json").read_bytes())
    for which in ("model_pick", "llm_first"):
        for k in range(0, len(todo), BATCH):
            batch = todo[k:k + BATCH]
            body = "\n\n".join(f"### id: {it['id']}\n元の文: {it['s']}\n書き直した文: {it['s'].replace(it['w'], it[which]['cand'], 1)}" for it in batch)
            rows = {r.get("id"): r for r in parse(g.run_codex(MEANING.format(items=body), "gpt-6-luna", "low", codex_home=home))}
            for it in batch:
                it["same_" + ("model" if which == "model_pick" else "llm")] = rows.get(it["id"], {}).get("same", "不明")
    if todo:
        with open(path, "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")

    ranked = [it for it in items if "ranked" in it]
    def avg(xs):
        return sum(xs) / max(len(xs), 1)
    out = ["# 直し方の分担: AI が言い換えを出し、AI 以前のモデルが選ぶ", "",
           f"差 > 4 の語 {len(items)} 件(作者の文書を優先、語ごとに2件まで)。AI(claude opus)が言い換えを5つ出し、",
           "AI 以前のモデル A と AI 時代のモデル B で並べた。意味の判定は gpt-6-luna。", "",
           f"- AI が「変えない」とした語: {sum(it['keep'] for it in items)} 件",
           f"- 並べた語: {len(ranked)} 件", "",
           "| 選び方 | A での自然さの変化(文全体の対数尤度、元の文との差) | AI 時代らしさの変化(B − A の差の変化) | 意味が同じ | 少し変わる | 変わる |",
           "|---|---|---|---|---|---|"]
    for key, lab, sk in (("llm_first", "AI の1番目の候補", "same_llm"), ("model_pick", "モデルが選んだ候補", "same_model")):
        c = Counter(it.get(sk) for it in ranked)
        n = max(len(ranked), 1)
        out.append(f"| {lab} | {avg([it[key]['dA'] for it in ranked]):+.2f} | {avg([it[key]['d'] for it in ranked]):+.2f} | "
                   f"{c['同じ'] / n:.0%} | {c['少し変わる'] / n:.0%} | {c['変わる'] / n:.0%} |")
    same_pick = sum(it["llm_first"]["cand"] == it["model_pick"]["cand"] for it in ranked)
    still_ai = sum(it["llm_first"]["d"] > 0 for it in ranked)
    out += ["", f"- モデルが AI の1番目と同じ候補を選んだ: {same_pick} / {len(ranked)}",
            f"- AI の1番目の候補が、元の語より AI 時代らしさを上げていた(差の変化 > 0): {still_ai} / {len(ranked)}"]
    (HERE / "fix-eval.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
