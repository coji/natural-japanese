# /// script
# requires-python = ">=3.11"
# dependencies = ["torch", "transformers>=4.44", "fugashi", "unidic-lite"]
# ///
"""corpus/mlm/suggest.py — 差が大きい語の言い換え候補を、AI 以前のモデル(A)に出させる。

score の候補は1トークンの語にしか出ず、質も低かった。ここでは:
    1. 語の位置を1〜3個の [MASK] に置き換え、A に左から順に埋めさせる(ビーム幅 BEAM)
    2. できた候補を、品詞が元の語と同じもの(1語目の品詞で見る)に絞る
    3. 候補を入れた文で、候補部分の当てやすさを A と B で測り直す
       - A で当てやすい(AI 以前の人が選ぶ)
       - B − A の差が小さい(候補そのものが AI 時代の語ではない)
    4. A の当てやすさ(トークン数で割らない合計)で並べ、上位3つを返す

使い方(試し): uv run corpus/mlm/suggest.py "文" "語"
モジュールとして: from suggest import Suggester
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRIV = ROOT / "corpus/private/mlm"
BEAM = 8
MAX_MASK = 3


class Suggester:
    def __init__(self):
        import fugashi
        import torch
        from transformers import AutoModelForMaskedLM, AutoTokenizer
        self.torch = torch
        self.dev = "mps" if torch.backends.mps.is_available() else "cpu"
        self.tok = AutoTokenizer.from_pretrained(PRIV / "model-A")
        self.A = AutoModelForMaskedLM.from_pretrained(PRIV / "model-A").to(self.dev).eval()
        self.B = AutoModelForMaskedLM.from_pretrained(PRIV / "model-B").to(self.dev).eval()
        self.tagger = fugashi.Tagger()
        vocab = self.tok.convert_ids_to_tokens(list(range(len(self.tok))))
        # 埋める候補から外すトークン(記号・数字・英字・特殊トークン)
        self.bad = torch.tensor([not re.fullmatch(r"(##)?[ぁ-んァ-ヶー一-龠々]+", t) for t in vocab])

    def _words(self, s):
        return [(w.surface, w.feature.pos1) for w in self.tagger(s)]

    def _ids(self, words):
        ids, spans = [self.tok.cls_token_id], []
        for surf, _ in words:
            sub = self.tok.convert_tokens_to_ids(self.tok.subword_tokenizer.tokenize(surf)) if surf.strip() else []
            spans.append((len(ids), len(ids) + len(sub)))
            ids += sub
        ids.append(self.tok.sep_token_id)
        return ids, spans

    def _span_lp(self, model, ids, a, b):
        """ids[a:b] を同時に伏せたときの、各トークンの log 確率の合計。"""
        torch = self.torch
        x = torch.tensor([ids]).to(self.dev)
        x[0, a:b] = self.tok.mask_token_id
        with torch.no_grad():
            lp = torch.log_softmax(model(x).logits[0], -1)
        return sum(lp[a + j, t].item() for j, t in enumerate(ids[a:b]))

    def _hidden(self, ids, a, b):
        """A の最終層で、ids[a:b](語の位置)の隠れ状態の平均。文脈の中での語の意味として使う。"""
        torch = self.torch
        x = torch.tensor([ids]).to(self.dev)
        with torch.no_grad():
            h = self.A(x, output_hidden_states=True).hidden_states[-1][0]
        return h[a:b].mean(0)

    def suggest(self, sentence: str, word: str, k: int = 3) -> list[dict]:
        torch = self.torch
        words = self._words(sentence)
        idx = next((i for i, (s, _) in enumerate(words) if s == word), None)
        if idx is None:
            return []
        pos = words[idx][1]
        ids, spans = self._ids(words)
        a, b = spans[idx]
        orig_A = self._span_lp(self.A, ids, a, b)
        orig_B = self._span_lp(self.B, ids, a, b)
        cands: dict[str, None] = {}
        h_orig = self._hidden(ids, a, b)
        # 伏せずに元の語を見せたときの候補(意味の近い語が出やすい)
        x = torch.tensor([ids]).to(self.dev)
        with torch.no_grad():
            lp0 = torch.log_softmax(self.A(x).logits[0, a], -1)
        lp0[self.bad.to(self.dev)] = -1e9
        for t in torch.topk(lp0, 30).indices.tolist():
            ts = self.tok.convert_ids_to_tokens(t)
            if not ts.startswith("##"):
                cands[ts] = None
        for n in range(1, MAX_MASK + 1):
            base = ids[:a] + [self.tok.mask_token_id] * n + ids[b:]
            beams = [(0.0, base)]
            for j in range(n):
                x = torch.tensor([bm for _, bm in beams]).to(self.dev)
                with torch.no_grad():
                    lp = torch.log_softmax(self.A(x).logits[:, a + j], -1)
                lp[:, self.bad.to(self.dev)] = -1e9
                if j == 0:  # 1トークン目は「##」で始まらない
                    pass
                nxt = []
                top = torch.topk(lp, BEAM, dim=-1)
                for r, (score, bm) in enumerate(beams):
                    for v, t in zip(top.values[r].tolist(), top.indices[r].tolist()):
                        tokstr = self.tok.convert_ids_to_tokens(t)
                        if j == 0 and tokstr.startswith("##"):
                            continue
                        if j > 0 and not tokstr.startswith("##"):
                            continue  # 1語にまとめる(2トークン目以降は「##」の続きだけ)
                        nb = list(bm)
                        nb[a + j] = t
                        nxt.append((score + v, nb))
                beams = sorted(nxt, key=lambda x: -x[0])[:BEAM]
                if not beams:
                    break
            for _, bm in beams:
                toks = self.tok.convert_ids_to_tokens(bm[a:a + n])
                cands["".join(t.removeprefix("##") for t in toks)] = None
        out = []
        for c in cands:
            if not c or c == word:
                continue
            cw = self._words(c)
            if not cw or cw[0][1] != pos:
                continue
            new_words = words[:idx] + [(c, pos)] + words[idx + 1:]
            nids, nspans = self._ids(new_words)
            na, nb = nspans[idx]
            lA = self._span_lp(self.A, nids, na, nb)
            lB = self._span_lp(self.B, nids, na, nb)
            if lB - lA > 1.5:  # 候補そのものが AI 時代の語
                continue
            sim = self.torch.nn.functional.cosine_similarity(h_orig, self._hidden(nids, na, nb), dim=0).item()
            out.append({"cand": c, "lpA": round(lA, 2), "d": round(lB - lA, 2), "sim": round(sim, 3),
                        "score": round(lA / max(nb - na, 1) + 8 * sim, 3)})
        out.sort(key=lambda x: -x["score"])
        return [{"orig": word, "orig_lpA": round(orig_A, 2), "orig_d": round(orig_B - orig_A, 2), **o} for o in out[:k]]


    def pll(self, sentence: str) -> tuple[float, float]:
        """文全体の擬似対数尤度(各トークンを1つずつ伏せて当てた log 確率の合計)を A と B で返す。"""
        torch = self.torch
        ids, _ = self._ids(self._words(sentence))
        n = len(ids) - 2
        x = torch.tensor([ids] * n).to(self.dev)
        for r in range(n):
            x[r, r + 1] = self.tok.mask_token_id
        res = []
        with torch.no_grad():
            for m in (self.A, self.B):
                lp = torch.log_softmax(m(x).logits, -1)
                res.append(sum(lp[r, r + 1, ids[r + 1]].item() for r in range(n)))
        return res[0], res[1]

    def rank(self, sentence: str, old: str, candidates: list[str]) -> list[dict]:
        """old を各候補に置き換えた文を、A の自然さ(元の文との差)と、B − A の差で並べる。
        候補は意味を保つ言い換え(AI に出させる)。モデルは「AI 以前の人が書くか」だけを見る。"""
        a0, b0 = self.pll(sentence)
        out = []
        for c in candidates:
            s2 = sentence.replace(old, c, 1)
            a1, b1 = self.pll(s2)
            out.append({"cand": c, "dA": round(a1 - a0, 2), "d": round((b1 - a1) - (b0 - a0), 2)})
        out.sort(key=lambda r: -(r["dA"] - max(r["d"], 0)))
        return out


if __name__ == "__main__":
    s = Suggester()
    for r in s.suggest(sys.argv[1], sys.argv[2]):
        print(r)
