# /// script
# requires-python = ">=3.11"
# dependencies = ["torch", "transformers>=4.44", "fugashi", "unidic-lite", "huggingface_hub"]
# ///
"""lexicon.py — 2つの BERT が拾う語を、torch なしで配れる語のリストと規則に落とせるかを調べる。

最初の問い: BERT が差 > 3 で拾う語は、出てくればほぼ必ず拾われる語(語のリストで足りる)か、
文脈しだいで拾われる語(前後の語を見る規則が要る)か。語ごとに、出てきた回数のうち差 > 3 になった割合を出す。

データ: corpus/private/mlm/tests.json の学習外の束(47本の評価セットに使った文書は除く)。各文書の先頭 CHARS 字。
doc_meter.py で使った文書は hold として印をつけ、リストを作るときには使わず、後で精度を測るのに残す。

    uv run corpus/mlm/lexicon.py score     # 公開したモデルで語ごとの差を付けて保存する(途中から再開できる)
    uv run corpus/mlm/lexicon.py profile   # 拾われた語が、どちらの種類に偏っているかを出す
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/natural-japanese/scripts"))
sys.path.insert(0, str(ROOT / "corpus/mlm"))
sys.path.insert(0, str(ROOT / "corpus/mlm"))
from doc_meter import body, load  # noqa: E402

OUT = ROOT / "corpus/private/mlm/lexicon-scores.jsonl"
CHARS = 2000
N_PER = {"generated_holdout": 100, "self": 16, "qiita2022": 300, "llmjp": 300, "qiita2026": 300}
T = 3.0
AI, HUMAN = ("generated_holdout",), ("qiita2022", "llmjp")


def rows() -> list[dict]:
    tests = json.loads((ROOT / "corpus/private/mlm/tests.json").read_text(encoding="utf-8"))
    used = {(p / "before.md").read_text(encoding="utf-8").strip()
            for p in (ROOT / "corpus/private/versions").iterdir() if (p / "before.md").exists()}
    hold = {r["text"].strip() for r in load()}
    rng = random.Random(1)
    out = []
    for name, n in N_PER.items():
        xs = [body(x) for x in tests[name] if body(x).strip() not in used and x.strip() not in used]
        rng.shuffle(xs)
        for i, x in enumerate(xs[:n]):
            out.append({"id": f"{name}-{i}", "set": name, "hold": x.strip() in hold, "text": x})
    return out


def score() -> None:
    from style_check_torch import Pair, sentences  # noqa: E402
    done = {json.loads(l)["id"] for l in OUT.read_text(encoding="utf-8").splitlines()} if OUT.exists() else set()
    pair = Pair()
    with OUT.open("a", encoding="utf-8") as f:
        for r in rows():
            if r["id"] in done:
                continue
            sents, chars = [], 0
            for _, s in sentences(r["text"]):
                if chars >= CHARS:
                    break
                chars += len(s)
                sents.append({"s": s, "w": [[w["w"], w["lemma"], w["d"]] for w in pair.score(s)]})
            f.write(json.dumps({"id": r["id"], "set": r["set"], "hold": r["hold"], "chars": chars, "sents": sents},
                               ensure_ascii=False) + "\n")
            f.flush()
            print(r["id"], chars, flush=True)


def profile() -> None:
    from style_check_torch import ok_word  # noqa: E402
    docs = [json.loads(l) for l in OUT.read_text(encoding="utf-8").splitlines()]
    # 生成AIの文書は全部 doc_meter.py で使った(hold)ので、この記述的な集計では hold も含めて全部を使う
    build = docs
    n, k = defaultdict(int), defaultdict(int)          # 出てきた回数、差 > T の回数(全束)
    per = defaultdict(lambda: defaultdict(int))        # 束ごとの出てきた回数
    words = defaultdict(int)
    for d in build:
        for s in d["sents"]:
            for w, lem, dd in s["w"]:
                if not ok_word({"w": w, "lemma": lem}):
                    continue
                n[lem] += 1
                k[lem] += dd > T
                per[d["set"]][lem] += 1
                words[d["set"]] += 1
    rate = {lem: k[lem] / n[lem] for lem in n}
    print(f"文書: {len(build)} 本。拾われた語の延べ数: {sum(k.values())}")
    for name in N_PER:
        ds = [d for d in build if d["set"] == name]
        if ds:
            f = sum(dd > T for d in ds for s in d["sents"] for w, lem, dd in s["w"] if ok_word({"w": w, "lemma": lem}))
            print(f"  {name}: {len(ds)} 本、拾われた語 {f} 個、1000字あたり {f / sum(d['chars'] for d in ds) * 1000:.2f}")
    bands = [("ほぼ必ず(80%以上)", 0.8, 1.01), ("多くの場合(50〜80%)", 0.5, 0.8), ("ときどき(20〜50%)", 0.2, 0.5),
             ("まれ(20%未満)", 0.0, 0.2)]
    for title, sets in (("全束", None), ("生成AIの文書", AI), ("生成AI以前の人間", HUMAN), ("qiita2026", ("qiita2026",))):
        tot = defaultdict(int)
        for d in build:
            if sets and d["set"] not in sets:
                continue
            for s in d["sents"]:
                for w, lem, dd in s["w"]:
                    if dd > T and ok_word({"w": w, "lemma": lem}):
                        rare = n[lem] < 5
                        tot["出現5回未満" if rare else next(b[0] for b in bands if b[1] <= rate[lem] < b[2])] += 1
        all_ = sum(tot.values())
        print(f"\n## {title}: 拾われた語 {all_} 個が、その語の拾われやすさのどの帯に入るか")
        for b in [b[0] for b in bands] + ["出現5回未満"]:
            print(f"  {b}: {tot[b]} ({tot[b] / max(all_, 1):.0%})")
    # 語ごとの一覧(拾われた回数の多い順)。頻度比は生成AIの文書と生成AI以前の人間の文書での100万語あたりの出現の比
    def pm(sets, lem):
        return sum(per[s][lem] for s in sets) / max(sum(words[s] for s in sets), 1) * 1e6
    print("\n| 語 | 出現 | 拾われた | 割合 | 頻度比(AI/人間) |\n|---|---|---|---|---|")
    for lem in sorted(k, key=lambda x: -k[x])[:60]:
        r = pm(AI, lem) / pm(HUMAN, lem) if pm(HUMAN, lem) else float("inf")
        print(f"| {lem} | {n[lem]} | {k[lem]} | {rate[lem]:.0%} | {r:.1f} |")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["score", "profile"])
    a = ap.parse_args()
    {"score": score, "profile": profile}[a.cmd]()


if __name__ == "__main__":
    main()
