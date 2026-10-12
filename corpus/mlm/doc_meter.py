# /// script
# requires-python = ">=3.11"
# dependencies = ["torch", "transformers>=4.44", "fugashi", "unidic-lite", "huggingface_hub"]
# ///
"""doc_meter.py — 2つの BERT で、文書全体の「生成AI時代の書き手らしさ」を1つの値にする物差しを作る。

これまでの物差し(style_check の密度)は内容語しか見ない。ここでは助詞・文末も含め、文の全トークンを
1つずつ伏せて当てた log 確率の差(B − A)を使う案も並べ、学習に使っていない文書で人間と生成AIを分けられるかを比べる。

データ(corpus/private/mlm/tests.json の学習外の束。47本の評価セットに使った文書は除く):
    AI      generated_holdout
    人間    qiita2022・llmjp(生成AI以前)
    参考    qiita2026(生成AI時代の人間の記事)、self(作者の文書)
長さの交絡を避けるため、どの文書も本文の先頭 CHARS 字ぶんの文だけを使う。
文書は dev と test に半分ずつ分け、測り方は dev で選び、test は最後に1回だけ見る。

    uv run corpus/mlm/doc_meter.py score      # 文書ごとの値を計算して保存する(途中から再開できる)
    uv run corpus/mlm/doc_meter.py report     # dev での AUC を出す(--test で test も出す)
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/natural-japanese/scripts"))
sys.path.insert(0, str(ROOT / "corpus/mlm"))
OUT = ROOT / "corpus/private/mlm/doc-meter.jsonl"
CHARS = 2000
N_PER = {"generated_holdout": 79, "qiita2022": 40, "llmjp": 40, "qiita2026": 40, "self": 16}


def body(t: str) -> str:
    return t.split("\n---\n", 1)[1] if t.startswith("---\n") and "\n---\n" in t else t


def load() -> list[dict]:
    tests = json.loads((ROOT / "corpus/private/mlm/tests.json").read_text(encoding="utf-8"))
    used = {(OUT.parent.parent / "versions" / d / "before.md").read_text(encoding="utf-8").strip()
            for d in [p.name for p in (ROOT / "corpus/private/versions").iterdir() if (p / "before.md").exists()]}
    rng = random.Random(0)
    rows = []
    for name, n in N_PER.items():
        xs = [x for x in tests[name] if body(x).strip() not in used and x.strip() not in used and len(body(x)) >= 1000]
        rng.shuffle(xs)
        for i, x in enumerate(xs[:n]):
            rows.append({"id": f"{name}-{i}", "set": name, "split": "dev" if i % 2 == 0 else "test", "text": body(x)})
    return rows


def token_diffs(pair, s: str) -> list[float]:
    """文の各トークンを1つずつ伏せ、B と A での log 確率の差を返す(PLL の内訳)。"""
    torch = pair.torch
    ids, _ = pair.ids(pair.words(s))
    n = len(ids) - 2
    if n <= 0 or len(ids) > 256:
        return []
    x = torch.tensor([ids] * n)
    for r in range(n):
        x[r, r + 1] = pair.tok.mask_token_id
    with torch.no_grad():
        la = torch.log_softmax(pair.A(x).logits, -1)
        lb = torch.log_softmax(pair.B(x).logits, -1)
    return [round(lb[r, r + 1, ids[r + 1]].item() - la[r, r + 1, ids[r + 1]].item(), 3) for r in range(n)]


def score(rows: list[dict] | None = None, out: Path = OUT) -> None:
    from style_check_torch import Pair, ok_word, sentences  # noqa: E402
    done = {json.loads(l)["id"] for l in out.read_text(encoding="utf-8").splitlines()} if out.exists() else set()
    pair = Pair()
    with out.open("a", encoding="utf-8") as f:
        for row in rows if rows is not None else load():
            if row["id"] in done:
                continue
            sents, chars = [], 0
            for _, s in sentences(row["text"]):
                if chars >= CHARS:
                    break
                sents.append(s)
                chars += len(s)
            words, toks = [], []
            for s in sents:
                words += [w["d"] for w in pair.score(s) if ok_word(w)]
                toks.append(token_diffs(pair, s))
            f.write(json.dumps({"id": row["id"], "set": row["set"], "split": row["split"], "chars": chars,
                                "word_d": words, "tok_d": toks}, ensure_ascii=False) + "\n")
            f.flush()
            print(row["id"], chars, len(words), flush=True)


def metrics(r: dict) -> dict:
    flat = [d for s in r["tok_d"] for d in s]
    wd = r["word_d"]
    sent_mean = [sum(s) / len(s) for s in r["tok_d"] if s]
    return {
        "密度(差>3 の内容語/1000字)": sum(d > 3 for d in wd) / max(r["chars"], 1) * 1000,
        "内容語の差の平均": sum(wd) / max(len(wd), 1),
        "全トークンの差の平均": sum(flat) / max(len(flat), 1),
        "全トークンの差 > 3 の割合": sum(d > 3 for d in flat) / max(len(flat), 1),
        "文ごとの平均の上位25%": sorted(sent_mean)[int(len(sent_mean) * 0.75)] if sent_mean else 0.0,
    }


def auc(pos: list[float], neg: list[float]) -> float:
    if not pos or not neg:
        return float("nan")
    s = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return s / (len(pos) * len(neg))


def report(test: bool) -> None:
    rows = [json.loads(l) for l in OUT.read_text(encoding="utf-8").splitlines()]
    splits = ["dev", "test"] if test else ["dev"]
    names = list(metrics(rows[0]).keys())
    print("| 物差し | 分割 | AUC(AI 対 生成AI以前の人間) | 平均 AI | qiita2022 | llmjp | qiita2026 | 作者 |")
    print("|---|---|---|---|---|---|---|---|")
    for m in names:
        for sp in splits:
            v = {k: [metrics(r)[m] for r in rows if r["set"] == k and (r["split"] == sp or k == "self")] for k in N_PER}
            a = auc(v["generated_holdout"], v["qiita2022"] + v["llmjp"])
            avg = {k: sum(x) / len(x) if x else float("nan") for k, x in v.items()}
            print(f"| {m} | {sp} | {a:.3f} | {avg['generated_holdout']:.3f} | {avg['qiita2022']:.3f} | {avg['llmjp']:.3f} | "
                  f"{avg['qiita2026']:.3f} | {avg['self']:.3f} |")


INJ = ROOT / "corpus/private/mlm/inject"
OUT_INJ = ROOT / "corpus/private/mlm/doc-meter-inject.jsonl"


def score_inject() -> None:
    rows = [{"id": f.stem, "set": f.stem.rsplit("-", 1)[1], "split": "dev", "text": f.read_text(encoding="utf-8")}
            for f in sorted(INJ.glob("*.md"))]
    score(rows, OUT_INJ)


def report_inject() -> None:
    """生成AIらしさを入れた版(word・rhet)で、元より値が上がった文書の割合と、上がり幅を
    AI と人間の平均の差(dev)に対する比で出す。"""
    rows = {json.loads(l)["id"]: json.loads(l) for l in OUT_INJ.read_text(encoding="utf-8").splitlines()}
    base = [json.loads(l) for l in OUT.read_text(encoding="utf-8").splitlines()]
    names = list(metrics(base[0]).keys())
    print("| 物差し | 入れたもの | 本数 | 元より上がった | 上がり幅の平均 / AI と人間の差 |")
    print("|---|---|---|---|---|")
    for m in names:
        ai = [metrics(r)[m] for r in base if r["set"] == "generated_holdout" and r["split"] == "dev"]
        hu = [metrics(r)[m] for r in base if r["set"] in ("qiita2022", "llmjp") and r["split"] == "dev"]
        gap = sum(ai) / len(ai) - sum(hu) / len(hu)
        for kind in ("word", "rhet", "split", "plain", "join"):
            ds = []
            for k, r in rows.items():
                if k.endswith(f"-{kind}") and k.replace(f"-{kind}", "-orig") in rows:
                    ds.append(metrics(r)[m] - metrics(rows[k.replace(f"-{kind}", "-orig")])[m])
            up = sum(d > 0 for d in ds)
            print(f"| {m} | {kind} | {len(ds)} | {up}({up / max(len(ds), 1):.0%}) | {sum(ds) / max(len(ds), 1) / gap:+.2f} |")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["score", "report", "score-inject", "report-inject"])
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    {"score": score, "report": lambda: report(a.test), "score-inject": score_inject, "report-inject": report_inject}[a.cmd]()


if __name__ == "__main__":
    main()
