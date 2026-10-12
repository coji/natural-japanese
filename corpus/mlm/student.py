# /// script
# requires-python = ">=3.11"
# dependencies = ["torch", "transformers>=4.48", "tokenizers", "fugashi", "unidic-lite", "huggingface_hub", "numpy",
#                 "onnx", "onnxruntime", "onnxscript", "onnxconverter-common"]
# ///
"""student.py — 2つの BERT が出す差 d を、1つの小さなモデルに1回読むだけで出させる(第2段)。

先生   公開モデルの2つの BERT。語を1つずつ伏せて d = log P_B − log P_A を出す(lexicon.py で採点済みの文を使う)
生徒   sbintuitions/modernbert-ja-30m(MIT、3,700万パラメータ)に、トークンごとに d を出す回帰の頭をつける。
       分かち書きの辞書は要らない(tokenizer.json だけで動く)
正解   先生の内容語(ok_word を満たす語)の d を、その語の文字の範囲に重なるトークンに付ける。ほかのトークンは損失に入れない。
       推論では、語の範囲に重なるトークンの予測の最大値をその語の d とする。どの分かち書きで語を区切っても使える
検査   onnx_pair.py check と同じ60本(学習には使わない)。F64 と同じ列に加えて、
       同じ語の中での相関(拾われる割合が10〜50%の語。語のリストなら0になる)と、
       47本の推敲結果(s0a)で原文になかった語(introduced)が先生と一致するかを出す

    uv run corpus/mlm/student.py label [--docs 6000]   # 学習用の正解を先生に増やさせる(Qiita 2022〜2025年)
    uv run corpus/mlm/student.py train [--epochs 4]
    uv run corpus/mlm/student.py eval
    uv run corpus/mlm/student.py export
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/natural-japanese/scripts"))
SCORES = ROOT / "corpus/private/mlm/lexicon-scores.jsonl"
OUT = ROOT / "corpus/private/mlm/student"
BASE = "sbintuitions/modernbert-ja-30m"
T = 3.0
MAXLEN = 160


LABELS = OUT / "labels.jsonl"
CHARS = 2000


def label(n_docs: int) -> None:
    """先生(公開モデルの2つの BERT)で、学習に使われていない Qiita 2022〜2025年の文書を採点する(MPS で動かす)。
    tests.json の文書(検査用)は除く。途中から再開できる。"""
    import gzip
    import torch
    from style_check import CONTENT, SEQ, Pair, sentences
    tests = json.loads((ROOT / "corpus/private/mlm/tests.json").read_text(encoding="utf-8"))
    used = {x.strip() for v in tests.values() for x in v}
    docs = []
    for y in (2022, 2023, 2024, 2025):
        for i, l in enumerate(gzip.open(ROOT / f"corpus/timeslice/qiita-aug/data/{y}.jsonl.gz", "rt", encoding="utf-8")):
            b = json.loads(l)["body"]
            if b.strip() not in used and len(b) >= 1000:
                docs.append((f"q{y}-{i}", f"qiita{y}", b))
    random.Random(0).shuffle(docs)
    done = {json.loads(l)["id"] for l in LABELS.read_text(encoding="utf-8").splitlines()} if LABELS.exists() else set()
    OUT.mkdir(parents=True, exist_ok=True)
    pair = Pair()
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    pair.A.to(dev)
    pair.B.to(dev)
    t0, n = time.time(), 0
    with LABELS.open("a", encoding="utf-8") as f:
        for did, name, text in docs[:n_docs]:
            if did in done:
                continue
            sents, chars = [], 0
            for _, s in sentences(text):
                if chars >= CHARS:
                    break
                chars += len(s)
                ws = pair.words(s)
                ids, sp = pair.ids(ws)
                if len(ids) > SEQ:
                    continue
                tg = [i for i, (surf, p1, p2, _) in enumerate(ws) if p1 in CONTENT and p2 not in {"固有名詞", "数詞", "非自立可能"}
                      and sp[i][1] > sp[i][0] and __import__("re").search(r"[ぁ-んァ-ヶ一-龠]", surf)]
                out = []
                for k in range(0, len(tg), 64):
                    tb = tg[k:k + 64]
                    x = torch.tensor([ids] * len(tb))
                    for r, i in enumerate(tb):
                        x[r, sp[i][0]:sp[i][1]] = pair.tok.mask_token_id
                    x = x.to(dev)
                    with torch.no_grad():
                        la = torch.log_softmax(pair.A(x).logits, -1).cpu()
                        lb = torch.log_softmax(pair.B(x).logits, -1).cpu()
                    for r, i in enumerate(tb):
                        a, b = sp[i]
                        pa = sum(la[r, a + j, t].item() for j, t in enumerate(ids[a:b]))
                        pb = sum(lb[r, a + j, t].item() for j, t in enumerate(ids[a:b]))
                        out.append([ws[i][0], ws[i][3], round(pb - pa, 2)])
                sents.append({"s": s, "w": out})
            f.write(json.dumps({"id": did, "set": name, "hold": False, "chars": chars, "sents": sents}, ensure_ascii=False) + "\n")
            f.flush()
            n += 1
            if n % 50 == 0:
                print(f"{n} 本 {time.time() - t0:.0f}s", flush=True)


def ok(w: str, lem: str) -> bool:
    from style_check import ok_word
    return ok_word({"w": w, "lemma": lem})


def spans(s: str, words: list) -> list[tuple[int, int, str, str, float]]:
    """先生の語(表層・見出し語・d)を文の中で順に探し、文字の範囲を付ける。"""
    out, cur = [], 0
    for w, lem, d in words:
        i = s.find(w, cur)
        if i < 0:
            continue
        out.append((i, i + len(w), w, lem, d))
        cur = i + len(w)
    return out


def holdout_ids() -> set[str]:
    """onnx_pair.py check と同じ抜き出し(束ごとに20本、乱数の種0)。"""
    docs = [json.loads(l) for l in SCORES.read_text(encoding="utf-8").splitlines()]
    rng = random.Random(0)
    by = {}
    for d in docs:
        by.setdefault("AI" if d["set"] == "generated_holdout" else "人間" if d["set"] in ("qiita2022", "llmjp") else "qiita2026", []).append(d)
    return {d["id"] for k in by for d in rng.sample(by[k], min(20, len(by[k])))}


def tokenizer():
    from huggingface_hub import hf_hub_download
    from tokenizers import Tokenizer
    tk = Tokenizer.from_file(hf_hub_download(BASE, "tokenizer.json"))
    tk.enable_truncation(MAXLEN)
    return tk


def examples(split: str) -> list[dict]:
    hold = holdout_ids()
    out = []
    lines = SCORES.read_text(encoding="utf-8").splitlines()
    if split == "train" and LABELS.exists():
        lines += LABELS.read_text(encoding="utf-8").splitlines()
    for l in lines:
        d = json.loads(l)
        if (d["id"] in hold) != (split == "hold"):
            continue
        for s in d["sents"]:
            sp = [x for x in spans(s["s"], s["w"]) if ok(x[2], x[3])]
            if sp:
                out.append({"doc": d["id"], "set": d["set"], "chars": d["chars"], "s": s["s"], "sp": sp})
    return out


def token_labels(tk, s: str, sp: list) -> tuple[list[int], list[float], list[float]]:
    e = tk.encode(s)
    lab, msk = [0.0] * len(e.ids), [0.0] * len(e.ids)
    for t, (a, b) in enumerate(e.offsets):
        if a == b:
            continue
        ds = [d for (x, y, _, _, d) in sp if x < b and a < y]
        if ds:
            lab[t], msk[t] = max(ds), 1.0
    return e.ids, lab, msk


class Student:
    def __new__(cls, *a, **k):
        import torch
        from transformers import AutoModel

        class _S(torch.nn.Module):
            def __init__(self, path=BASE):
                super().__init__()
                self.enc = AutoModel.from_pretrained(path, attn_implementation="eager")
                self.head = torch.nn.Linear(self.enc.config.hidden_size, 1)

            def forward(self, input_ids, attention_mask):
                return self.head(self.enc(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state).squeeze(-1)
        return _S(*a, **k)


def train(epochs: int, lr: float, batch: int) -> None:
    import torch
    torch.manual_seed(0)
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    tk = tokenizer()
    pad = tk.token_to_id("<pad>") or 0
    data = [token_labels(tk, x["s"], x["sp"]) for x in examples("train")]
    print(f"学習の文 {len(data)}、ラベルのあるトークン {sum(sum(m) for _, _, m in data):.0f}", flush=True)
    m = Student().to(dev)
    opt = torch.optim.AdamW(m.parameters(), lr=lr, weight_decay=0.01)
    steps = epochs * (len(data) // batch)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=steps, pct_start=0.06)
    rng = random.Random(0)
    step, t0 = 0, time.time()
    for ep in range(epochs):
        rng.shuffle(data)
        m.train()
        tot = 0.0
        for k in range(0, len(data) - batch + 1, batch):
            b = data[k:k + batch]
            L = max(len(x[0]) for x in b)
            ids = torch.tensor([x[0] + [pad] * (L - len(x[0])) for x in b], device=dev)
            am = torch.tensor([[1] * len(x[0]) + [0] * (L - len(x[0])) for x in b], device=dev)
            y = torch.tensor([x[1] + [0.0] * (L - len(x[1])) for x in b], device=dev)
            w = torch.tensor([x[2] + [0.0] * (L - len(x[2])) for x in b], device=dev)
            loss = (torch.nn.functional.huber_loss(m(ids, am), y, reduction="none", delta=1.0) * w).sum() / w.sum()
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(m.parameters(), 1.0)
            opt.step()
            sched.step()
            step += 1
            tot += loss.item()
            if step % 500 == 0:
                print(f"ep {ep} step {step}/{steps} loss {tot / 500:.4f} {time.time() - t0:.0f}s", flush=True)
                tot = 0.0
    OUT.mkdir(parents=True, exist_ok=True)
    torch.save(m.state_dict(), OUT / "student.pt")
    print("saved", OUT / "student.pt")


class Predictor:
    """学習済みの生徒で、語の範囲ごとの d を出す(torch 版。export 後は onnx も使える)。"""

    def __init__(self, onnx: str | None = None):
        import numpy as np
        self.np, self.tk = np, tokenizer()
        if onnx:
            import onnxruntime as ort
            self.sess = ort.InferenceSession(onnx, providers=["CPUExecutionProvider"])
            self.m = None
        else:
            import torch
            self.torch = torch
            self.m = Student()
            self.m.load_state_dict(torch.load(OUT / "student.pt", map_location="cpu"))
            self.m.eval()

    def token_d(self, s: str):
        e = self.tk.encode(s)
        np = self.np
        if self.m is None:
            x = np.array([e.ids], dtype=np.int64)
            p = self.sess.run(["d"], {"input_ids": x, "attention_mask": np.ones_like(x)})[0][0]
        else:
            with self.torch.no_grad():
                x = self.torch.tensor([e.ids])
                p = self.m(x, self.torch.ones_like(x))[0].numpy()
        return e.offsets, p

    def word_d(self, s: str, sp: list[tuple[int, int]]) -> list[float | None]:
        offs, p = self.token_d(s)
        out = []
        for a, b in sp:
            v = [float(p[t]) for t, (x, y) in enumerate(offs) if x != y and x < b and a < y]
            out.append(max(v) if v else None)
        return out


def evaluate(onnx: str | None = None) -> None:
    import numpy as np
    pr = Predictor(onnx)
    ex = examples("hold")
    ref, got, lems = [], [], []
    dens = defaultdict(lambda: [0, 0, 0])
    t0 = time.time()
    for x in ex:
        ps = pr.word_d(x["s"], [(a, b) for a, b, *_ in x["sp"]])
        for (a, b, w, lem, d), p in zip(x["sp"], ps):
            if p is None:
                continue
            ref.append(d)
            got.append(p)
            lems.append(lem)
            dens[x["doc"]][0] += d > T
            dens[x["doc"]][1] += p > T
            dens[x["doc"]][2] = x["chars"]
    per = (time.time() - t0) / len(ex)
    ref, got = np.array(ref), np.array(got)
    tp = ((ref > T) & (got > T)).sum()
    dr = np.array([v[0] / v[2] * 1000 for v in dens.values()])
    dg = np.array([v[1] / v[2] * 1000 for v in dens.values()])
    print(f"検査: {len(dens)} 本、{len(ex)} 文、語 {len(ref)}")
    print("| 版 | 1文あたり | d の相関 | |d の差| の平均 | 差>3 の一致(適合/再現) | 文書の密度の相関 |\n|---|---|---|---|---|---|")
    print(f"| 生徒{'(onnx)' if onnx else ''} | {per * 1000:.1f}ms | {np.corrcoef(ref, got)[0, 1]:.4f} | {np.abs(ref - got).mean():.3f} | "
          f"{tp / max((got > T).sum(), 1):.1%} / {tp / max((ref > T).sum(), 1):.1%} | {np.corrcoef(dr, dg)[0, 1]:.4f} |")
    # 同じ語の中での相関: 学習側で拾われる割合が10〜50%の語ごとに、先生と生徒の d の相関をとり、出現数で重みづけて平均する
    n, k = defaultdict(int), defaultdict(int)
    for x in examples("train"):
        for *_, lem, d in x["sp"]:
            n[lem] += 1
            k[lem] += d > T
    mid = {l for l in n if n[l] >= 20 and 0.1 <= k[l] / n[l] <= 0.5}
    by = defaultdict(list)
    for r, g, l in zip(ref, got, lems):
        if l in mid:
            by[l].append((r, g))
    cs = [(len(v), np.corrcoef(*zip(*v))[0, 1]) for v in by.values() if len(v) >= 8 and np.std([a for a, _ in v]) > 0]
    print(f"同じ語の中での相関(拾われる割合10〜50%の語 {len(cs)} 種類、出現で重みづけ): "
          f"{sum(w * c for w, c in cs) / max(sum(w for w, _ in cs), 1):.3f}")
    introduced(pr)


def introduced(pr) -> None:
    """47本の推敲結果(s0a)で、原文になかった差 > 3 の語の一覧を生徒で出し、先生(metrics.json)と比べる。"""
    import fugashi
    from style_check import CONTENT, sentences
    tagger = fugashi.Tagger()
    agree = tp = fp = fn = 0
    docs = sorted(p.parent for p in (ROOT / "corpus/private/versions").glob("*/metrics.json"))
    for doc in docs:
        m = json.loads((doc / "metrics.json").read_text(encoding="utf-8"))
        if "s0a" not in m or not (doc / "s0a.md").exists():
            continue
        orig = {w.feature.lemma or w.surface for _, s in sentences((doc / "before.md").read_text(encoding="utf-8")) for w in tagger(s)}
        mine = set()
        for _, s in sentences((doc / "s0a.md").read_text(encoding="utf-8")):
            ws, cur = [], 0
            for w in tagger(s):
                i = s.find(w.surface, cur)
                cur = i + len(w.surface) if i >= 0 else cur
                lem = w.feature.lemma or w.surface
                if (i >= 0 and w.feature.pos1 in CONTENT and w.feature.pos2 not in {"固有名詞", "数詞", "非自立可能"}
                        and ok(w.surface, lem)):
                    ws.append((i, i + len(w.surface), lem))
            for (a, b, lem), d in zip(ws, pr.word_d(s, [(a, b) for a, b, _ in ws])):
                if d is not None and d > T and lem not in orig:
                    mine.add(lem)
        ref = set(m["s0a"]["introduced"])
        tp, fp, fn = tp + len(ref & mine), fp + len(mine - ref), fn + len(ref - mine)
        agree += ref == mine
    print(f"推敲結果の introduced(47本): 先生 {tp + fn} 語、生徒 {tp + fp} 語、両方 {tp}"
          f"(適合 {tp / max(tp + fp, 1):.0%}・再現 {tp / max(tp + fn, 1):.0%})、一覧が完全に一致した文書 {agree}")


def export() -> None:
    import numpy as np
    import onnx
    import torch
    from onnxconverter_common import float16
    m = Student()
    m.load_state_dict(torch.load(OUT / "student.pt", map_location="cpu"))
    m.eval()
    x = torch.ones(1, 12, dtype=torch.long)
    f32 = OUT / "student.onnx"
    torch.onnx.export(m, (x, torch.ones_like(x)), f32, input_names=["input_ids", "attention_mask"], output_names=["d"],
                      dynamic_axes={"input_ids": {0: "b", 1: "s"}, "attention_mask": {0: "b", 1: "s"}, "d": {0: "b", 1: "s"}},
                      opset_version=17, dynamo=False)
    onnx.save(float16.convert_float_to_float16(onnx.load(f32), keep_io_types=True), OUT / "student.fp16.onnx")
    for f in (f32, OUT / "student.fp16.onnx"):
        print(f.name, f"{f.stat().st_size / 1e6:.0f}MB")
    del np


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["label", "train", "eval", "export"])
    ap.add_argument("--docs", type=int, default=6000, help="label で採点する文書の数")
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--onnx", help="eval で onnx の生徒を使う(student.onnx など)")
    a = ap.parse_args()
    if a.cmd == "label":
        label(a.docs)
    elif a.cmd == "train":
        train(a.epochs, a.lr, a.batch)
    elif a.cmd == "eval":
        evaluate(a.onnx)
    else:
        export()


if __name__ == "__main__":
    main()
