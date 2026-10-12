# /// script
# requires-python = ">=3.11"
# dependencies = ["torch", "transformers>=4.44", "fugashi", "unidic-lite", "huggingface_hub", "onnx", "onnxruntime", "onnxscript", "onnxconverter-common"]
# ///
"""onnx_pair.py — 2つの BERT を ONNX に変換して8ビットに圧縮し、torch なしで同じ差 d が出るかを確かめる。

ユーザーの手元で style_check を軽く動かすための第1段。学習はし直さず、形式だけを変える。
    export   公開モデル(coji/ja-ai-style-bert)の pre-ai・ai-era を ONNX にする。全体の fp32・int8 版と、
             語彙への射影を外した本体だけの fp32・int8・fp16 版(射影は伏せた位置だけ numpy で計算する)
    check    学習外の文書(lexicon.py の採点済みの文)で、torch 版と ONNX 版の d を比べる。
             大きさ・読み込み時間・1文あたりの時間・d の一致・差 > 3 の判定の一致・文書ごとの密度の一致を出す

    uv run corpus/mlm/onnx_pair.py export
    uv run corpus/mlm/onnx_pair.py check
    uv run corpus/mlm/onnx_pair.py export-skill   # スキルで配る版(corpus/private/mlm/onnx-skill/)
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/natural-japanese/scripts"))
sys.path.insert(0, str(ROOT / "corpus/mlm"))
OUT = ROOT / "corpus/private/mlm/onnx"
SCORES = ROOT / "corpus/private/mlm/lexicon-scores.jsonl"
T = 3.0
SUFFIXES = ("", ".int8", ".body", ".body.int8", ".body.fp16")


def Body(m):
    import torch

    class _Body(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.bert, self.transform = m.bert, m.cls.predictions.transform

        def forward(self, input_ids, attention_mask):
            return self.transform(self.bert(input_ids=input_ids, attention_mask=attention_mask)[0])
    return _Body()


SKILL_OUT = ROOT / "corpus/private/mlm/onnx-skill"


def LogpAt(m):
    """伏せた位置(平らにした番号 pos)だけで語彙へ射影し、目標のトークン target の log 確率を返すグラフ。
    語彙への射影の重みは埋め込みと共有なので、ファイルには1つしか入らない。"""
    import torch

    class _L(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.bert, self.pred = m.bert, m.cls.predictions

        def forward(self, input_ids, attention_mask, pos, target):
            h = self.pred.transform(self.bert(input_ids=input_ids, attention_mask=attention_mask)[0])
            h = h.reshape(-1, h.shape[-1]).index_select(0, pos)
            lp = torch.log_softmax(self.pred.decoder(h), -1)
            return lp.gather(1, target.unsqueeze(1)).squeeze(1)
    return _L()


def export_skill() -> None:
    """スキルで配る版: 伏せた位置の log 確率だけを出すグラフを、重み fp16(LogSoftmax は fp32)で書き出す。"""
    import onnx
    import torch
    from huggingface_hub import snapshot_download
    from onnxconverter_common import float16
    from transformers import AutoModelForMaskedLM
    from style_check_torch import MODEL_REPO
    root = Path(snapshot_download(MODEL_REPO))
    SKILL_OUT.mkdir(parents=True, exist_ok=True)
    for name in ("pre-ai", "ai-era"):
        m = AutoModelForMaskedLM.from_pretrained(root / name, dtype=torch.float32).eval()
        g = LogpAt(m).eval()
        x = torch.ones(2, 16, dtype=torch.long)
        pos, tgt = torch.tensor([3, 20]), torch.tensor([5, 7])
        tmp = SKILL_OUT / f"{name}.f32.onnx"
        torch.onnx.export(g, (x, torch.ones_like(x), pos, tgt), tmp,
                          input_names=["input_ids", "attention_mask", "pos", "target"], output_names=["logp"],
                          dynamic_axes={"input_ids": {0: "b", 1: "s"}, "attention_mask": {0: "b", 1: "s"}, "pos": {0: "n"},
                                        "target": {0: "n"}, "logp": {0: "n"}}, opset_version=17, dynamo=False)
        m16 = float16.convert_float_to_float16(onnx.load(tmp), keep_io_types=True,
                                               op_block_list=list(float16.DEFAULT_OP_BLOCK_LIST) + ["LogSoftmax"])
        onnx.save(m16, SKILL_OUT / f"{name}.onnx")
        tmp.unlink()
        print(name, f"{(SKILL_OUT / f'{name}.onnx').stat().st_size / 1e6:.0f}MB")


def check_skill() -> None:
    """スキルの style_check.py(ONNX 版、SKILL_OUT のモデル)と torch の基準版を比べる。
    60本の文で、トークン列・内容語の d・文の擬似対数尤度(rank が使う)が一致するか、
    47本の推敲結果(s0a)で compare の原文になかった語の一覧が一致するかを出す。"""
    import importlib.util
    import numpy as np
    from style_check_torch import Pair as TorchPair
    spec = importlib.util.spec_from_file_location("style_check_onnx", ROOT / "skills/natural-japanese/scripts/style_check.py")
    sc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sc)
    t, o = TorchPair(), sc.Pair(str(SKILL_OUT))
    docs = [json.loads(l) for l in SCORES.read_text(encoding="utf-8").splitlines()]
    rng = random.Random(0)
    by = {}
    for d in docs:
        by.setdefault(d["set"], []).append(d)
    sents = [s["s"] for k in by for d in rng.sample(by[k], min(15, len(by[k]))) for s in d["sents"]]
    same_ids = 0
    ref, got, pa, pb = [], [], [], []
    t0 = time.time()
    for s in sents:
        ws = t.words(s)
        same_ids += t.ids(ws) == o.ids(ws)
        a, b = t.score(s), o.score(s)
        if [x["w"] for x in a] == [x["w"] for x in b]:
            ref += [x["d"] for x in a]
            got += [x["d"] for x in b]
    for s in sents[:300]:
        pa.append(t.pll(s))
        pb.append(o.pll(s))
    ref, got = np.array(ref), np.array(got)
    tp = ((ref > T) & (got > T)).sum()
    dp = np.abs(np.array(pa) - np.array(pb))
    print(f"文 {len(sents)}: トークン列の一致 {same_ids / len(sents):.2%}、語 {len(ref)}、d の差の最大 {np.abs(ref - got).max():.2f}・平均 {np.abs(ref - got).mean():.4f}、"
          f"差>3 の一致 適合 {tp / max((got > T).sum(), 1):.1%}・再現 {tp / max((ref > T).sum(), 1):.1%}")
    print(f"擬似対数尤度(300文): A の差の最大 {dp[:, 0].max():.2f}、B の差の最大 {dp[:, 1].max():.2f}(文の合計値で)")
    same = n = 0
    for doc in sorted(p.parent for p in (ROOT / "corpus/private/versions").glob("*/s0a.md")):
        before, after = (doc / "before.md").read_text(encoding="utf-8"), (doc / "s0a.md").read_text(encoding="utf-8")
        res = []
        for pair in (t, o):
            orig = pair.lemmas(before)
            rows, _ = pair.flagged(after, T)
            res.append(sorted(w["lemma"] for r in rows for w in r["words"] if w["lemma"] not in orig))
        n += 1
        same += res[0] == res[1]
        if res[0] != res[1]:
            print("  違い", doc.name, res[0], res[1])
    print(f"compare(47本の s0a): 原文になかった語の一覧が一致 {same}/{n}")


def export() -> None:
    import numpy as np
    import torch
    from huggingface_hub import snapshot_download
    from onnxruntime.quantization import QuantType, quantize_dynamic
    from transformers import AutoModelForMaskedLM
    from style_check_torch import MODEL_REPO
    root = Path(snapshot_download(MODEL_REPO))
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ("pre-ai", "ai-era"):
        m = AutoModelForMaskedLM.from_pretrained(root / name, dtype=torch.float32).eval()
        x = torch.ones(2, 16, dtype=torch.long)
        f32 = OUT / f"{name}.onnx"
        torch.onnx.export(m, (x, torch.ones_like(x)), f32, input_names=["input_ids", "attention_mask"],
                          output_names=["logits"], dynamic_axes={"input_ids": {0: "b", 1: "s"}, "attention_mask": {0: "b", 1: "s"},
                                                                 "logits": {0: "b", 1: "s"}}, opset_version=17, dynamo=False)
        quantize_dynamic(f32, OUT / f"{name}.int8.onnx", weight_type=QuantType.QInt8)
        print(name, f"fp32 {f32.stat().st_size / 1e6:.0f}MB", f"int8 {(OUT / f'{name}.int8.onnx').stat().st_size / 1e6:.0f}MB")
        # 本体だけの版。出力は語彙へ射影する直前の隠れ状態。射影の重みは fp16 の numpy で別に持つ
        body = Body(m).eval()
        hb = OUT / f"{name}.body.onnx"
        torch.onnx.export(body, (x, torch.ones_like(x)), hb, input_names=["input_ids", "attention_mask"],
                          output_names=["hidden"], dynamic_axes={"input_ids": {0: "b", 1: "s"}, "attention_mask": {0: "b", 1: "s"},
                                                                 "hidden": {0: "b", 1: "s"}}, opset_version=17, dynamo=False)
        dec = m.cls.predictions.decoder
        np.save(OUT / f"{name}.head-w.npy", dec.weight.detach().numpy().astype(np.float16))
        np.save(OUT / f"{name}.head-b.npy", m.cls.predictions.bias.detach().numpy().astype(np.float32))
        quantize_dynamic(hb, OUT / f"{name}.body.int8.onnx", weight_type=QuantType.QInt8, per_channel=True,
                         op_types_to_quantize=["MatMul"])
        print(name, f"body fp32 {hb.stat().st_size / 1e6:.0f}MB",
              f"body int8 {(OUT / f'{name}.body.int8.onnx').stat().st_size / 1e6:.0f}MB",
              f"head {(OUT / f'{name}.head-w.npy').stat().st_size / 1e6:.0f}MB")
        # 重みを fp16 にした版(入出力は fp32 のまま)
        import onnx
        from onnxconverter_common import float16
        onnx.save(float16.convert_float_to_float16(onnx.load(hb), keep_io_types=True), OUT / f"{name}.body.fp16.onnx")


class OnnxPair:
    """style_check.Pair と同じ score を、onnxruntime で計算する。"""

    def __init__(self, suffix: str):
        import fugashi
        import numpy as np
        import onnxruntime as ort
        from transformers import AutoTokenizer
        from style_check_torch import BASE
        self.np = np
        self.tok = AutoTokenizer.from_pretrained(BASE)
        so = ort.SessionOptions()
        self.body = ".body" in suffix
        self.A = ort.InferenceSession(str(OUT / f"pre-ai{suffix}.onnx"), so, providers=["CPUExecutionProvider"])
        self.B = ort.InferenceSession(str(OUT / f"ai-era{suffix}.onnx"), so, providers=["CPUExecutionProvider"])
        if self.body:
            self.head = {id(self.A): (np.load(OUT / "pre-ai.head-w.npy").astype(np.float32), np.load(OUT / "pre-ai.head-b.npy")),
                         id(self.B): (np.load(OUT / "ai-era.head-w.npy").astype(np.float32), np.load(OUT / "ai-era.head-b.npy"))}
        self.tagger = fugashi.Tagger()

    from style_check_torch import Pair as _P
    words = _P.words
    ids = _P.ids
    del _P

    def _logp(self, sess, x):
        np = self.np
        lg = sess.run(["logits"], {"input_ids": x, "attention_mask": np.ones_like(x)})[0]
        lg = lg - lg.max(-1, keepdims=True)
        return lg - np.log(np.exp(lg).sum(-1, keepdims=True))

    def score(self, s: str, batch: int = 48) -> list[dict]:
        import re
        from style_check_torch import CONTENT, SEQ
        np = self.np
        ws = self.words(s)
        ids, spans = self.ids(ws)
        if len(ids) > SEQ:
            return []
        targets = [i for i, (surf, p1, p2, _) in enumerate(ws)
                   if p1 in CONTENT and p2 not in {"固有名詞", "数詞", "非自立可能"} and spans[i][1] > spans[i][0]
                   and re.search(r"[ぁ-んァ-ヶ一-龠]", surf)]
        out = []
        for k in range(0, len(targets), batch):
            tb = targets[k:k + batch]
            x = np.array([ids] * len(tb), dtype=np.int64)
            for r, i in enumerate(tb):
                a, b = spans[i]
                x[r, a:b] = self.tok.mask_token_id
            if self.body:
                rows = [(r, spans[i][0] + j, t) for r, i in enumerate(tb) for j, t in enumerate(ids[spans[i][0]:spans[i][1]])]
                lp = {}
                for sess in (self.A, self.B):
                    h = sess.run(["hidden"], {"input_ids": x, "attention_mask": np.ones_like(x)})[0]
                    w, bias = self.head[id(sess)]
                    hh = np.stack([h[r, pos] for r, pos, _ in rows])
                    lg = hh @ w.T + bias
                    lg = lg - lg.max(-1, keepdims=True)
                    lg = lg - np.log(np.exp(lg).sum(-1, keepdims=True))
                    lp[id(sess)] = {(r, pos): float(lg[n, t]) for n, (r, pos, t) in enumerate(rows)}
                la = {k: v for k, v in lp[id(self.A)].items()}
                lb = {k: v for k, v in lp[id(self.B)].items()}
            else:
                la, lb = self._logp(self.A, x), self._logp(self.B, x)
            for r, i in enumerate(tb):
                a, b = spans[i]
                if self.body:
                    pa = sum(la[(r, a + j)] for j in range(b - a))
                    pb = sum(lb[(r, a + j)] for j in range(b - a))
                else:
                    pa = sum(float(la[r, a + j, t]) for j, t in enumerate(ids[a:b]))
                    pb = sum(float(lb[r, a + j, t]) for j, t in enumerate(ids[a:b]))
                surf, p1, _, lem = ws[i]
                out.append({"w": surf, "lemma": lem, "d": round(pb - pa, 2)})
        return out


def check(n_docs: int) -> None:
    from style_check_torch import ok_word
    docs = [json.loads(l) for l in SCORES.read_text(encoding="utf-8").splitlines()]
    rng = random.Random(0)
    by = {}
    for d in docs:
        by.setdefault("AI" if d["set"] == "generated_holdout" else "人間" if d["set"] in ("qiita2022", "llmjp") else "qiita2026", []).append(d)
    sample = [d for k in by for d in rng.sample(by[k], min(n_docs, len(by[k])))]
    print(f"文書 {len(sample)} 本、文 {sum(len(d['sents']) for d in sample)} 個。基準は torch 版(lexicon.py で採点済み)")
    print("| 版 | 大きさ(2つ) | 読み込み | 1文あたり | d の相関 | |d の差| の平均 | 最大 | 差>3 の一致(適合/再現) | 文書の密度の相関 |")
    print("|---|---|---|---|---|---|---|---|---|")
    for suffix in SUFFIXES:
        size = sum((OUT / f"{n}{suffix}.onnx").stat().st_size for n in ("pre-ai", "ai-era")) / 1e6
        if ".body" in suffix:
            size += sum((OUT / f"{n}.head-w.npy").stat().st_size for n in ("pre-ai", "ai-era")) / 1e6
        t0 = time.time()
        p = OnnxPair(suffix)
        load = time.time() - t0
        ref, got, dens_ref, dens_got, ns = [], [], [], [], 0
        t0 = time.time()
        for d in sample:
            fr = fg = 0
            for s in d["sents"]:
                ns += 1
                g = p.score(s["s"])
                if len(g) != len(s["w"]):
                    continue
                for (w, lem, dr), x in zip(s["w"], g):
                    if ok_word({"w": w, "lemma": lem}):
                        ref.append(dr)
                        got.append(x["d"])
                        fr += dr > T
                        fg += x["d"] > T
            dens_ref.append(fr / d["chars"] * 1000)
            dens_got.append(fg / d["chars"] * 1000)
        per = (time.time() - t0) / ns
        np = p.np
        r = np.corrcoef(ref, got)[0, 1]
        diff = np.abs(np.array(ref) - np.array(got))
        tp = sum(a > T and b > T for a, b in zip(ref, got))
        prec = tp / max(sum(b > T for b in got), 1)
        rec = tp / max(sum(a > T for a in ref), 1)
        rd = np.corrcoef(dens_ref, dens_got)[0, 1]
        print(f"| {suffix or 'fp32'} | {size:.0f}MB | {load:.1f}秒 | {per * 1000:.0f}ms | {r:.4f} | {diff.mean():.3f} | "
              f"{diff.max():.2f} | {prec:.1%} / {rec:.1%} | {rd:.4f} |", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["export", "check", "export-skill", "check-skill"])
    ap.add_argument("--docs", type=int, default=20, help="check で使う文書の数(束ごと)")
    a = ap.parse_args()
    {"export": export, "export-skill": export_skill, "check": lambda: check(a.docs), "check-skill": check_skill}[a.cmd]()


if __name__ == "__main__":
    main()
