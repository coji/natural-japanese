# /// script
# requires-python = ">=3.11"
# dependencies = ["onnxruntime", "numpy", "fugashi", "unidic-lite", "huggingface_hub"]
# ///
"""style_check.py — 生成AI時代に増えた言い回しを、AI 以前の書き手を基準にして調べる。

2つの BERT を使う(Hugging Face の coji/ja-ai-style-bert の onnx/。初回に約450MB をダウンロードする)。
torch は使わず、onnxruntime で動かす(重みは fp16。torch 版と同じ差が出ることを確かめてある)。
    A(pre-ai)   AI 以前の人間の文書で追加学習
    B(ai-era)   同じ話題で生成AIに書かせた文章で追加学習
    差 d        log P_B(語) − log P_A(語)。語を伏せて当てさせたとき、B だけがそこにその語を置くほど大きい

サブコマンド:
    flag FILE              差 > 3 の語を含む文を、行番号と語つきで示す
    rank ITEMS.json        文ごとの言い換え候補を、AI 以前の人が書きそうな順に並べる
    compare ORIG REVISED   直した文書に、原文になかった AI 時代の語が増えていないかを調べる

カタカナ語・英字の語・固有名詞・数詞は対象にしない(新しい技術用語は、AI 以前のモデルが知らないだけなので)。
示すのは疑いで、直すかどうかは文脈で決める。語ごとの言い換えはこのスクリプトでは出さない。

使い方(--models・--threshold はサブコマンドの前に書く):
    uv run scripts/style_check.py flag draft.md [--json]
    uv run scripts/style_check.py rank items.json        # [{"id": "...", "sentence": "...", "candidates": ["...", ...]}]
    uv run scripts/style_check.py compare original.md revised.md [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from textcore import _blank_inline_code_spans, read_source_file  # noqa: E402

MODEL_REPO = "coji/ja-ai-style-bert"
SEQ = 256
CONTENT = {"動詞", "形容詞", "副詞", "名詞", "形状詞"}
THRESHOLD = 3.0

_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
_TABLE_RE = re.compile(r"^\s*\|.*\|\s*$")
_MARKER_RE = re.compile(r"^\s*(?:#{1,6}\s+|>\s*|[-*+]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+)")
_HTML_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"https?://\S+")
_SPLIT_RE = re.compile(r"(?<=[。！？!?])")


def sentences(text: str) -> list[tuple[int, str]]:
    """(行番号, 文)。見出し・箇条書き・引用は記号を外して本文として扱う(推敲で語が入るのは見出しにも多い)。
    コードブロック・表・フロントマター・HTML・URL・インラインコードは外す。"""
    out, fence, front = [], None, False
    for no, line in enumerate(text.split("\n"), start=1):
        if no == 1 and line.strip() == "---":
            front = True
            continue
        if front:
            front = line.strip() != "---"
            continue
        m = _FENCE_RE.match(line)
        if m:
            fence = None if fence and m.group(1)[0] == fence else (fence or m.group(1)[0])
            continue
        if fence or _TABLE_RE.match(line):
            continue
        body = _MARKER_RE.sub("", _blank_inline_code_spans(line))
        body = _URL_RE.sub(" ", _HTML_RE.sub(" ", body))
        body = re.sub(r"\*\*|__|(?<![\w*])\*(?=\S)|(?<=\S)\*(?![\w*])", "", body)  # 強調の記号
        for s in _SPLIT_RE.split(body):
            s = re.sub(r"\s+", " ", s).strip(" *_")
            if re.search(r"[ぁ-んァ-ヶ一-龠]", s):
                out.append((no, s))
    return out


def ok_word(w: dict) -> bool:
    return not re.fullmatch(r"[ァ-ヶー・]+", w["w"]) and "-" not in w["lemma"] and not re.search(r"[A-Za-z]", w["w"])


class Pair:
    def __init__(self, models: str | None = None):
        import fugashi
        import numpy as np
        import onnxruntime as ort
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        if models:
            root = Path(models)
        else:
            from huggingface_hub import snapshot_download
            root = Path(snapshot_download(MODEL_REPO, allow_patterns=["onnx/*"])) / "onnx"
        self.np = np
        with open(root / "vocab.txt", encoding="utf-8") as f:
            self.vocab = {line.rstrip("\n"): i for i, line in enumerate(f)}
        self.cls, self.sep, self.mask, self.unk = (self.vocab[t] for t in ("[CLS]", "[SEP]", "[MASK]", "[UNK]"))
        so = ort.SessionOptions()
        so.log_severity_level = 3
        # 重みは fp16、入出力は fp32。伏せた位置の log 確率だけを返す(corpus/mlm/onnx_pair.py export-skill で作る)
        self.A = ort.InferenceSession(str(root / "pre-ai.onnx"), so, providers=["CPUExecutionProvider"])
        self.B = ort.InferenceSession(str(root / "ai-era.onnx"), so, providers=["CPUExecutionProvider"])
        self.tagger = fugashi.Tagger()

    def words(self, s: str):
        return [(w.surface, w.feature.pos1, w.feature.pos2, w.feature.lemma or w.surface) for w in self.tagger(s)]

    def lemmas(self, text: str) -> set[str]:
        return {lem for _, s in sentences(text) for _, _, _, lem in self.words(s)}

    def subwords(self, word: str) -> list[int]:
        """WordPiece(最長一致)。tohoku-nlp/bert-base-japanese-v3 の subword_tokenizer と同じ分け方をする。"""
        out = []
        for tok in word.split():
            if len(tok) > 100:
                out.append(self.unk)
                continue
            start, sub = 0, []
            while start < len(tok):
                end = len(tok)
                while start < end:
                    piece = ("##" if start else "") + tok[start:end]
                    if piece in self.vocab:
                        sub.append(self.vocab[piece])
                        break
                    end -= 1
                else:
                    sub = [self.unk]
                    break
                start = end
            out += sub
        return out

    def ids(self, ws):
        ids, spans = [self.cls], []
        for surf, *_ in ws:
            sub = self.subwords(surf) if surf.strip() else []
            spans.append((len(ids), len(ids) + len(sub)))
            ids += sub
        ids.append(self.sep)
        return ids, spans

    def _logp(self, x, pos: list[int], target: list[int]):
        """x の行ごとに伏せた位置 pos(行 × 長さで平らにした番号)での target の log 確率を、A と B で返す。"""
        np = self.np
        feed = {"input_ids": x, "attention_mask": np.ones_like(x),
                "pos": np.array(pos, dtype=np.int64), "target": np.array(target, dtype=np.int64)}
        return self.A.run(["logp"], feed)[0], self.B.run(["logp"], feed)[0]

    def score(self, s: str, batch: int = 48) -> list[dict]:
        """文の内容語を1語ずつ伏せ(語の全トークンを同時に)、A と B での log 確率の差を返す。"""
        np = self.np
        ws = self.words(s)
        ids, spans = self.ids(ws)
        if len(ids) > SEQ:
            return []
        targets = [i for i, (surf, p1, p2, _) in enumerate(ws)
                   if p1 in CONTENT and p2 not in {"固有名詞", "数詞", "非自立可能"} and spans[i][1] > spans[i][0]
                   and re.search(r"[ぁ-んァ-ヶ一-龠]", surf)]
        n, out = len(ids), []
        for k in range(0, len(targets), batch):
            tb = targets[k:k + batch]
            x = np.array([ids] * len(tb), dtype=np.int64)
            pos, tgt = [], []
            for r, i in enumerate(tb):
                a, b = spans[i]
                x[r, a:b] = self.mask
                pos += [r * n + t for t in range(a, b)]
                tgt += ids[a:b]
            la, lb = self._logp(x, pos, tgt)
            j = 0
            for i in tb:
                a, b = spans[i]
                pa, pb = float(la[j:j + b - a].sum()), float(lb[j:j + b - a].sum())
                j += b - a
                surf, p1, _, lem = ws[i]
                out.append({"w": surf, "lemma": lem, "d": round(pb - pa, 2)})
        return out

    def pll(self, s: str) -> tuple[float, float]:
        """文全体の擬似対数尤度(各トークンを1つずつ伏せて当てた log 確率の合計)を A と B で返す。"""
        np = self.np
        ids, _ = self.ids(self.words(s))
        n = len(ids) - 2
        if n <= 0 or len(ids) > SEQ:
            return 0.0, 0.0
        x = np.array([ids] * n, dtype=np.int64)
        for r in range(n):
            x[r, r + 1] = self.mask
        la, lb = self._logp(x, [r * len(ids) + r + 1 for r in range(n)], ids[1:-1])
        return float(la.sum()), float(lb.sum())

    def flagged(self, text: str, threshold: float) -> tuple[list[dict], int]:
        rows, chars = [], 0
        for no, s in sentences(text):
            chars += len(s)
            ws = [w for w in self.score(s) if ok_word(w) and w["d"] > threshold]
            if ws:
                rows.append({"line": no, "sentence": s, "words": sorted(ws, key=lambda w: -w["d"])})
        return rows, chars

    def rank(self, sentence: str, candidates: list[str]) -> dict:
        """候補を並べる。dA は AI 以前のモデル A での自然さの変化(大きいほど AI 以前の人が書きそう)、
        d は B − A の差の変化(負なら AI 時代らしさが下がった)。dA − max(d, 0) の大きい順。"""
        a0, b0 = self.pll(sentence)
        out = []
        for c in dict.fromkeys(candidates):
            if not c or c == sentence:
                continue
            a1, b1 = self.pll(c)
            out.append({"candidate": c, "dA": round(a1 - a0, 2), "d": round((b1 - a1) - (b0 - a0), 2)})
        out.sort(key=lambda r: -(r["dA"] - max(r["d"], 0)))
        return {"sentence": sentence, "ranked": out, "chosen": out[0]["candidate"] if out else None}


def read(path: str) -> str:
    text, err = read_source_file(Path(path))
    if err:
        print(err, file=sys.stderr)
        sys.exit(1)
    return text


def cmd_flag(a) -> None:
    pair = Pair(a.models)
    rows, chars = pair.flagged(read(a.file), a.threshold)
    if a.json:
        print(json.dumps({"sentences_flagged": len(rows), "chars": chars, "flags": rows}, ensure_ascii=False, indent=1))
        return
    for r in rows:
        print(f"L{r['line']}: {r['sentence']}")
        print("    " + "、".join(f"{w['w']}({w['d']:.1f})" for w in r["words"]))
    n = sum(len(r["words"]) for r in rows)
    print(f"\n{len(rows)} 文・{n} 語(本文 {chars} 字、1,000字あたり {n / max(chars, 1) * 1000:.1f} 語)")


def cmd_rank(a) -> None:
    pair = Pair(a.models)
    items = json.loads(read(a.items))
    out = []
    for it in items:
        r = pair.rank(it["sentence"], it.get("candidates") or [])
        out.append({"id": it.get("id"), **r})
    print(json.dumps(out, ensure_ascii=False, indent=1))


def cmd_compare(a) -> None:
    pair = Pair(a.models)
    orig = pair.lemmas(read(a.original))
    rows, _ = pair.flagged(read(a.revised), a.threshold)
    intro = []
    for r in rows:
        ws = [w for w in r["words"] if w["lemma"] not in orig]
        if ws:
            intro.append({**r, "words": ws})
    if a.json:
        print(json.dumps({"introduced": intro}, ensure_ascii=False, indent=1))
        return
    for r in intro:
        print(f"L{r['line']}: {r['sentence']}")
        print("    原文にない語: " + "、".join(f"{w['w']}({w['d']:.1f})" for w in r["words"]))
    print(f"\n原文になかった AI 時代の語: {sum(len(r['words']) for r in intro)} 語")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--models", help="手元のモデルのディレクトリ(pre-ai.onnx・ai-era.onnx・vocab.txt を置く)。既定は Hugging Face から取得")
    ap.add_argument("--threshold", type=float, default=THRESHOLD)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("flag")
    p.add_argument("file")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("rank")
    p.add_argument("items")
    p = sub.add_parser("compare")
    p.add_argument("original")
    p.add_argument("revised")
    p.add_argument("--json", action="store_true")
    a = ap.parse_args()
    {"flag": cmd_flag, "rank": cmd_rank, "compare": cmd_compare}[a.cmd](a)


if __name__ == "__main__":
    main()
