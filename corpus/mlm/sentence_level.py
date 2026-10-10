# /// script
# requires-python = ">=3.11"
# ///
"""corpus/mlm/sentence_level.py — 2つのモデルの差で、語ではなく文を指せるかを確かめる(F48)。

次の版のスキルは「AI 以前の人はこう書かない文」を指して言い換えを出す。その前に確かめること:
    1. 文の単位で、AI 以前の人間の文と生成文を分けられるか
       文の値: 差 > T の内容語の数、内容語の差の最大値(カタカナ語・英字の語は除く)
       分けやすさは AUC と、「差 > T の語を1つでも含む文」の割合で見る。文の長さで分けた割合も出す
    2. 作者の文書で指された文のうち、文書の題材や業務の用語だけで指されたものが何割か
       指された語が用語かどうかを gpt-6-luna(codex、effort low)に判定させる。
       自然かどうかは聞かない(LLM はこの言い回しを不自然と感じない。F41)

入力: corpus/private/mlm/scores-m3-*.jsonl(A3・B3 の対。検査用の文書は学習に使っていない)
出力: corpus/mlm/sentence-level.md(数値のみ。コミットする)、corpus/private/mlm/topic-labels.jsonl

使い方:
    uv run corpus/mlm/sentence_level.py measure
    uv run corpus/mlm/sentence_level.py topic      # 作者の文書の指された語を判定させてから集計する
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PRIV = ROOT / "corpus/private/mlm"
SETS = {"qiita2022": "Qiita 2022年(AI以前)", "llmjp": "仕事の文章(AI以前)", "qiita2026": "Qiita 2026年",
        "generated_holdout": "生成記事(学習外)", "self": "作者の文書"}
PRE = ("qiita2022", "llmjp")
TS = (3.0, 4.0, 5.0)
BATCH = 15
PROMPT = """次の各文で【】に入った語が、どちらに当たるかを判定してください。語の選び方の良し悪しや自然さは判定しません。

- 用語: その文書の題材・業務・技術の用語、または固有の呼び名として使われている。別の語に言い換えると、指すものが変わる
- 一般: ふつうの言葉として使われている。別の語に言い換えても、指すものは変わらない

次の JSON 配列だけを出力してください: [{{"id": "...", "label": "用語"}}, ...]

{items}
"""


def ok(w) -> bool:
    return not re.fullmatch(r"[ァ-ヶー・]+", w["w"]) and "-" not in w["lemma"] and not re.search(r"[A-Za-z]", w["w"])


def load(name: str) -> list[dict]:
    return [json.loads(l) for l in open(PRIV / f"scores-m3-{name}.jsonl", encoding="utf-8")]


def auc(neg: list[float], pos: list[float]) -> float:
    """pos が neg より大きい確率(同点は半分)。"""
    allv = sorted([(v, 0) for v in neg] + [(v, 1) for v in pos])
    rank_sum, i = 0.0, 0
    while i < len(allv):
        j = i
        while j < len(allv) and allv[j][0] == allv[i][0]:
            j += 1
        r = (i + j + 1) / 2
        rank_sum += r * sum(1 for k in range(i, j) if allv[k][1] == 1)
        i = j
    n1, n0 = len(pos), len(neg)
    return (rank_sum - n1 * (n1 + 1) / 2) / (n1 * n0)


def feats(r: dict) -> dict:
    ds = [w["d"] for w in r["words"] if ok(w)]
    return {"len": len(r["s"]), "max": max(ds, default=0.0), **{f"n{int(t)}": sum(d > t for d in ds) for t in TS}}


def measure() -> list[str]:
    data = {n: [feats(r) for r in load(n)] for n in SETS}
    pre = data["qiita2022"] + data["llmjp"]
    out = ["# 文の単位で指せるか", "",
           "2つのモデル(A3・B3)の差を文ごとにまとめた。内容語はカタカナ語・英字の語を除く。検査用の文書は学習に使っていない。", "",
           "## 差 > T の語を1つでも含む文の割合", "",
           "| 検査セット | 文 | " + " | ".join(f"T={t:g}" for t in TS) + " |", "|---|---|" + "---|" * len(TS)]
    for n, lab in SETS.items():
        out.append(f"| {lab} | {len(data[n])} | " + " | ".join(f"{sum(f[f'n{int(t)}'] > 0 for f in data[n]) / len(data[n]):.0%}" for t in TS) + " |")
    out += ["", "## AI 以前の文(Qiita 2022年+仕事の文章)と分けられるか(AUC)", "",
            "| 比べる相手 | 差の最大値 | 差 > 3 の語の数 | 文の長さ(参考) |", "|---|---|---|---|"]
    for n in ("generated_holdout", "qiita2026", "self"):
        out.append(f"| {SETS[n]} | {auc([f['max'] for f in pre], [f['max'] for f in data[n]]):.3f} | "
                   f"{auc([f['n3'] for f in pre], [f['n3'] for f in data[n]]):.3f} | "
                   f"{auc([f['len'] for f in pre], [f['len'] for f in data[n]]):.3f} |")
    out += ["", "## 文の長さで分けた、差 > 3 の語を含む文の割合", "",
            "| 文の長さ | AI 以前 | 生成記事 | 作者の文書 |", "|---|---|---|---|"]
    for lo, hi in ((0, 30), (30, 60), (60, 90), (90, 10_000)):
        cells = []
        for fs in (pre, data["generated_holdout"], data["self"]):
            b = [f for f in fs if lo <= f["len"] < hi]
            cells.append(f"{sum(f['n3'] > 0 for f in b) / max(len(b), 1):.0%}({len(b)})")
        out.append(f"| {lo}〜{hi if hi < 10_000 else ''}字 | " + " | ".join(cells) + " |")
    return out


def topic() -> list[str]:
    sys.path.insert(0, str(ROOT / "corpus"))
    import generate as g  # noqa: E402
    g.prepare_isolation()
    items = []
    for si, r in enumerate(load("self")):
        for wi, w in enumerate(r["words"]):
            if ok(w) and w["d"] > 3:
                i = r["s"].find(w["w"])
                if i >= 0:
                    items.append({"id": f"t{si}_{wi}", "sent": si, "lemma": w["lemma"], "d": w["d"],
                                  "text": r["s"][:i] + "【" + w["w"] + "】" + r["s"][i + len(w["w"]):]})
    path = PRIV / "topic-labels.jsonl"
    done = {}
    if path.exists():
        for l in open(path, encoding="utf-8"):
            x = json.loads(l)
            done[x["id"]] = x["label"]
    todo = [it for it in items if it["id"] not in done]
    random.Random(0).shuffle(todo)
    batches = [todo[k:k + BATCH] for k in range(0, len(todo), BATCH)]

    def work(job):
        i, batch = job
        prompt = PROMPT.format(items="\n\n".join(f"### id: {it['id']}\n{it['text']}" for it in batch))
        ids = {b["id"] for b in batch}
        for _ in range(3):
            try:
                home = g.ISOLATION_DIR / f"codex-home-tl-{i % 3}"
                home.mkdir(parents=True, exist_ok=True)
                (home / "auth.json").write_bytes((g.CODEX_HOME / "auth.json").read_bytes())
                res = g.run_codex(prompt, "gpt-6-luna", "low", codex_home=home)
                m = re.search(r"\[.*\]", res, re.S)
                rows = [x for x in (json.loads(m.group(0)) if m else []) if isinstance(x, dict) and x.get("id") in ids]
                if len(rows) >= len(batch) * 0.8:
                    return rows
            except Exception as e:  # noqa: BLE001
                print(f"  ERR: {e}", file=sys.stderr)
        return []

    with open(path, "a", encoding="utf-8") as f, ThreadPoolExecutor(3) as ex:
        for rows in ex.map(work, enumerate(batches)):
            for x in rows:
                done[x["id"]] = x.get("label")
                f.write(json.dumps({"id": x["id"], "label": x.get("label")}, ensure_ascii=False) + "\n")
            f.flush()
            print(f"{len(done)} / {len(items)}", flush=True)

    labeled = [it for it in items if it["id"] in done]
    by_sent: dict[int, list[str]] = {}
    for it in labeled:
        by_sent.setdefault(it["sent"], []).append(done[it["id"]])
    n_sent = len(by_sent)
    only_term = sum(all(l == "用語" for l in ls) for ls in by_sent.values())
    term_words = Counter(it["lemma"] for it in labeled if done[it["id"]] == "用語")
    gen_words = Counter(it["lemma"] for it in labeled if done[it["id"]] == "一般")
    return ["", "## 作者の文書で、用語だけで指された文", "",
            f"差 > 3 の語(カタカナ語・英字の語を除く)を gpt-6-luna(effort low)に「用語/一般」で判定させた。判定できた語 {len(labeled)} / {len(items)}。", "",
            f"- 指された文: {n_sent}(作者の文書の文 {len(load('self'))} のうち)",
            f"- 指された語がすべて用語の文: {only_term}({only_term / max(n_sent, 1):.0%})",
            f"- 一般の語を1つ以上含む文: {n_sent - only_term}({(n_sent - only_term) / max(n_sent, 1):.0%})",
            f"- 語の内訳: 用語 {sum(term_words.values())}、一般 {sum(gen_words.values())}", "",
            "用語とされた語(多い順): " + "、".join(f"{w} {c}" for w, c in term_words.most_common(25)), "",
            "一般とされた語(多い順): " + "、".join(f"{w} {c}" for w, c in gen_words.most_common(25))]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["measure", "topic"])
    a = ap.parse_args()
    out = measure()
    if a.cmd == "topic":
        out += topic()
    (HERE / "sentence-level.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
