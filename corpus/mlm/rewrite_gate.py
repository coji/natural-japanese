# /// script
# requires-python = ">=3.11"
# dependencies = ["torch", "transformers>=4.44", "fugashi", "unidic-lite", "huggingface_hub"]
# ///
"""corpus/mlm/rewrite_gate.py — 指した文に言い換えを出し、モデルで並べて、原文が最も自然なら黙る段を確かめる(F49)。

F48 で、差 > 3 の語を含む文をそのまま書き手に見せると誤りが多い(ふつうの使い方の「作る」「共有」なども指す)とわかった。
次の版の中心になる流れを、作者が文章を読まずに測る:
    1. 指した文(差 > 3 の語を【】で囲む)を LLM(claude-opus-5-5、effort low)に渡し、【】の周りだけを
       意味を変えずに書き換えた文を3つまで出させる。変える必要がないと思うかどうか(keep)も答えさせる
    2. 原文と候補を2つのモデルで測る。dA = 候補の PLL_A − 原文の PLL_A(大きいほど AI 以前の人が書きそう)、
       d = 候補の (PLL_B − PLL_A) − 原文の (PLL_B − PLL_A)(正なら AI 時代らしくなった)。
       dA − max(d, 0) が最大の候補を選び、0 以下なら原文のまま(黙る)
    3. 選んだ候補の意味が保たれたかを gpt-6-luna(codex、effort low)に判定させる
正解の目安(読まずに済む): AI 以前の人間の文は黙るのが正しく、生成記事の文は書き換えが出るのが正しい。
作者の文書はその間に入るはず。

入力: corpus/private/mlm/scores-m3-*.jsonl(F48 と同じ)
モデル: 公開した coji/ja-ai-style-bert(公開用リポジトリの scripts/mlm.py の Pair。JA_AI_STYLE_SCRIPTS で場所を変えられる)
出力: corpus/private/mlm/rewrite-gate.jsonl、corpus/mlm/rewrite-gate.md(数値のみ。コミットする)

--top1: 1文につき、差がいちばん大きい語だけを【】で囲む(複数の語を囲むと、LLM が別の語を直して肝心の語を残すことがあったため)。
        同じ文で回し、rewrite-gate-top1.jsonl・rewrite-gate-top1.md に書く

使い方: uv run corpus/mlm/rewrite_gate.py [--n 80] [--top1]
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PRIV = ROOT / "corpus/private/mlm"
sys.path.insert(0, str(ROOT / "corpus"))
import generate as g  # noqa: E402
# 公開用リポジトリにも generate.py があるので、こちらは後ろに足す(mlm.py だけを使う)
sys.path.append(os.environ.get("JA_AI_STYLE_SCRIPTS", str(Path.home() / "progs/oss/ja-ai-style-corpus/scripts")))

GROUPS = {"pre": ("qiita2022", "llmjp"), "gen": ("generated_holdout",), "self": ("self",)}
LABEL = {"pre": "AI 以前の人間の文", "gen": "生成記事(学習外)", "self": "作者の文書"}
T = 3.0
BATCH = 10
TAG = ""  # --top1 のとき "-top1"
_SCORES: dict[str, list[dict]] = {}
PROPOSE = """次の各文で【】に入った語は、AI 以前の日本語の書き手なら別の言い方を選んだかもしれない語です。
【】の周りだけを書き換えた文を、3つまで出してください。

- 意味を変えない。文脈にない事実・数値・固有名詞を足さない。言い切りの強さも変えない
- 【】の語とその前後の数語以外は、1字も変えない。【】の記号は出力に含めない
- 文字どおりの意味で使っている、題材の用語や固有の呼び名であるなど、変える必要がないと思えば keep を true にする。そのときも候補は出す

次の JSON 配列だけを出力してください:
[{{"id": "...", "keep": false, "candidates": ["...", "..."]}}, ...]

{items}
"""
JUDGE = """次の各組で、書き換えた文(B)は元の文(A)と比べて意味が保たれているかを判定してください。
文体や自然さではなく、伝えている内容だけを見ます。

- meaning: 同じ / 少し変わる / 変わる
- added: B に、A にない事実・数値・条件が足されていれば true

次の JSON 配列だけを出力してください: [{{"id": "...", "meaning": "同じ", "added": false}}, ...]

{items}
"""


def ok(w) -> bool:
    return not re.fullmatch(r"[ァ-ヶー・]+", w["w"]) and "-" not in w["lemma"] and not re.search(r"[A-Za-z]", w["w"])


def top_word(it: dict) -> str:
    """その文で差がいちばん大きい内容語(カタカナ語・英字の語を除く)。"""
    if it["set"] not in _SCORES:
        _SCORES[it["set"]] = [json.loads(l) for l in open(PRIV / f"scores-m3-{it['set']}.jsonl", encoding="utf-8")]
    ws = [w for w in _SCORES[it["set"]][it["sid"]]["words"] if ok(w) and w["w"] in it["s"]]
    return max(ws, key=lambda w: w["d"])["w"]


def collect(n: int) -> list[dict]:
    rng = random.Random(0)
    items = []
    for grp, names in GROUPS.items():
        pool = []
        for name in names:
            for si, l in enumerate(open(PRIV / f"scores-m3-{name}.jsonl", encoding="utf-8")):
                r = json.loads(l)
                flagged = sorted({w["w"] for w in r["words"] if ok(w) and w["d"] > T and w["w"] in r["s"]}, key=len, reverse=True)
                if not flagged:
                    continue
                marked = r["s"]
                for w in flagged:
                    marked = marked.replace(w, "\0" + w + "\1", 1)
                marked = marked.replace("\0", "【").replace("\1", "】")
                pool.append({"group": grp, "set": name, "sid": si, "s": r["s"], "marked": marked, "words": flagged})
        rng.shuffle(pool)
        items += pool if grp == "self" else pool[:n]
    for i, it in enumerate(items):
        it["id"] = f"r{i}"
    return items


def ask(kind: str, prompt: str, ids: set[str], slot: int) -> list[dict]:
    for _ in range(3):
        try:
            if kind == "claude":
                res = g.run_claude(prompt, "claude-opus-5-5", "low")
            else:
                home = g.ISOLATION_DIR / f"codex-home-rg-{slot % 3}"
                home.mkdir(parents=True, exist_ok=True)
                (home / "auth.json").write_bytes((g.CODEX_HOME / "auth.json").read_bytes())
                res = g.run_codex(prompt, "gpt-6-luna", "low", codex_home=home)
            m = re.search(r"\[.*\]", res, re.S)
            rows = [x for x in (json.loads(m.group(0)) if m else []) if isinstance(x, dict) and x.get("id") in ids]
            if len(rows) >= len(ids) * 0.8:
                return rows
        except Exception as e:  # noqa: BLE001
            print(f"  ERR {kind}: {e}", file=sys.stderr)
    return []


def run_llm(items: list[dict], key: str, kind: str, template: str, fmt) -> None:
    todo = [it for it in items if key not in it and (key != "judge" or it.get("chosen"))]
    batches = [todo[k:k + BATCH] for k in range(0, len(todo), BATCH)]
    by_id = {it["id"]: it for it in items}

    def work(job):
        i, batch = job
        return ask(kind, template.format(items="\n\n".join(fmt(it) for it in batch)), {b["id"] for b in batch}, i)

    with ThreadPoolExecutor(3) as ex:
        for rows in ex.map(work, enumerate(batches)):
            for x in rows:
                by_id[x["id"]][key] = x
            save(items)
            print(f"{key}: {sum(key in it for it in items)} / {len(items)}", flush=True)


def save(items: list[dict]) -> None:
    (PRIV / f"rewrite-gate{TAG}.jsonl").write_text("".join(json.dumps(it, ensure_ascii=False) + "\n" for it in items), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=80)
    ap.add_argument("--top1", action="store_true")
    a = ap.parse_args()
    global TAG
    TAG = "-top1" if a.top1 else ""
    path = PRIV / f"rewrite-gate{TAG}.jsonl"
    if path.exists():
        items = [json.loads(l) for l in open(path, encoding="utf-8")]
    elif a.top1:
        # 元の試しと同じ文で、差がいちばん大きい語だけを囲む
        items = []
        for l in open(PRIV / "rewrite-gate.jsonl", encoding="utf-8"):
            it = {k: v for k, v in json.loads(l).items() if k in ("group", "set", "sid", "s", "words", "id")}
            w = top_word(it)
            it["marked"] = it["s"].replace(w, "【" + w + "】", 1)
            items.append(it)
    else:
        items = collect(a.n)
    save(items)
    print(Counter(it["group"] for it in items), flush=True)
    g.prepare_isolation()

    run_llm(items, "propose", "claude", PROPOSE, lambda it: f"### id: {it['id']}\n{it['marked']}")

    from mlm import Pair  # noqa: E402
    pair = Pair()
    for it in items:
        if "ranked" in it or "propose" not in it:
            continue
        cands = [c for c in dict.fromkeys(it["propose"].get("candidates") or []) if isinstance(c, str) and c.strip() and c != it["s"]]
        a0, b0 = pair.pll(it["s"])
        ranked = []
        for c in cands[:3]:
            a1, b1 = pair.pll(c)
            ranked.append({"cand": c, "dA": round(a1 - a0, 2), "d": round((b1 - a1) - (b0 - a0), 2)})
        ranked.sort(key=lambda r: -(r["dA"] - max(r["d"], 0)))
        it["ranked"] = ranked
        best = ranked[0] if ranked else None
        it["chosen"] = best["cand"] if best and best["dA"] - max(best["d"], 0) > 0 else None
        it["first"] = cands[0] if cands else None
    save(items)

    run_llm(items, "judge", "codex", JUDGE, lambda it: f"### id: {it['id']}\nA: {it['s']}\nB: {it['chosen']}")
    report(items)


def report(items: list[dict]) -> None:
    out = ["# 言い換えをモデルで並べ、原文が最も自然なら黙る段" + ("(1文に1語)" if TAG else ""), "",
           *(["差がいちばん大きい語だけを【】で囲んだ。", ""] if TAG else []),
           f"差 > {T} の語を含む文に、claude-opus-5-5(effort low)が【】の周りだけを書き換えた候補を3つまで出し、"
           "公開したモデル(coji/ja-ai-style-bert)で dA − max(d, 0) の最大の候補を選んだ。0 以下なら原文のまま(黙る)。"
           "意味の保持は gpt-6-luna(effort low)が判定した。", "",
           "| 文 | 件数 | LLM が「変えなくてよい」 | モデルが黙る | 書き換えを出す(LLM も変える側) | 意味が同じ | 少し変わる | 変わる | 事実の追加 | 選んだ候補の d の平均 | 書き換えで差が最大の語が消えた |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for grp in GROUPS:
        xs = [it for it in items if it["group"] == grp and "ranked" in it]
        if not xs:
            continue
        n = len(xs)
        keep = sum(bool(it["propose"].get("keep")) for it in xs)
        silent = sum(it["chosen"] is None for it in xs)
        shown = [it for it in xs if it["chosen"] and not it["propose"].get("keep")]
        ch = [it for it in xs if it["chosen"] and "judge" in it]
        mc = Counter(it["judge"].get("meaning") for it in ch)
        add = sum(bool(it["judge"].get("added")) for it in ch)
        dd = [it["ranked"][0]["d"] for it in xs if it["chosen"]]
        out.append(f"| {LABEL[grp]} | {n} | {keep / n:.0%} | {silent / n:.0%} | {len(shown) / n:.0%} | "
                   f"{mc['同じ'] / max(len(ch), 1):.0%} | {mc['少し変わる'] / max(len(ch), 1):.0%} | {mc['変わる'] / max(len(ch), 1):.0%} | "
                   f"{add / max(len(ch), 1):.0%} | {sum(dd) / max(len(dd), 1):.2f} | "
                   f"{sum(top_word(it) not in it['chosen'] for it in shown) / max(len(shown), 1):.0%} |")
    out += ["", "意味の判定は、モデルが原文以外を選んだ文(LLM が keep としたものも含む)だけ。"]
    for grp in ("pre", "gen"):
        xs = [it for it in items if it["group"] == grp and "ranked" in it]
        silent_words = Counter(w for it in xs if it["chosen"] is None for w in it["words"])
        shown_words = Counter(w for it in xs if it["chosen"] for w in it["words"])
        out += ["", f"{LABEL[grp]}: 黙った文の語 " + "、".join(f"{w} {c}" for w, c in silent_words.most_common(15)),
                f"{LABEL[grp]}: 書き換えた文の語 " + "、".join(f"{w} {c}" for w, c in shown_words.most_common(15))]
    (HERE / f"rewrite-gate{TAG}.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
