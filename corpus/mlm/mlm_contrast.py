# /// script
# requires-python = ">=3.11"
# dependencies = ["torch", "transformers>=4.44", "accelerate", "fugashi", "unidic-lite", "numpy", "peft"]
# ///
"""corpus/mlm/mlm_contrast.py — AI 以前と AI 時代の2つの BERT に穴埋めをさせ、AI 時代の言い回しを見つける。

語の表や組み合わせの数え上げでは、「パターンを拾う」「静かに壊れる」のような言い回しを見分けられなかった
(どの組み合わせも AI 以前にまれに出ており、違いは「使われるかどうか」ではなく「どれくらい自然に選ばれるか」)。
そこで、同じ土台のモデルを2つに分けて追加学習し、文の各語を伏せて当てさせる。

    土台   tohoku-nlp/bert-base-japanese-v3(CC-100 と 2023年1月の Wikipedia。生成AI以前の日本語)
    A      AI 以前の文章で追加学習: Qiita 2019〜2021年 + LLM-jp 由来の生成AI以前の説明的な文章
    B      AI 時代の文章で追加学習: Qiita 2026年(検査用の500件を除く)+ タイトルをそろえた生成記事
    差     log P_B(語) − log P_A(語)。大きいほど「AI 時代のモデルだけがそこにその語を置く」
    候補   A がその位置に予想する語(AI 以前の人ならここにこう書く)

段階:
    prepare  学習用の文と検査用の文書を作る(corpus/private/mlm/)
    train    A または B を追加学習する(corpus/private/mlm/model-A, model-B)
    score    検査用の文書の各語に差と候補を付ける(corpus/private/mlm/scores-*.jsonl)

使い方:
    uv run corpus/mlm/mlm_contrast.py prepare
    uv run corpus/mlm/mlm_contrast.py train A --steps 3000
    uv run corpus/mlm/mlm_contrast.py train B --steps 3000
    uv run corpus/mlm/mlm_contrast.py score --docs 100
"""
from __future__ import annotations

import argparse
import glob
import gzip
import json
import math
import random
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "corpus/timeslice/qiita-aug/data"
PRIV = ROOT / "corpus/private/mlm"
BASE = "tohoku-nlp/bert-base-japanese-v3"
SEQ = 256
SENT_SPLIT = re.compile(r"(?<=[。！？!?])|\n")


def clean(text: str) -> str:
    text = re.sub(r"```.*?```|~~~.*?~~~", "\n", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", "X", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"<[^>]+>|!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\*\*|__", "", text)
    return text


def sentences(text: str) -> list[str]:
    out = []
    for s in SENT_SPLIT.split(clean(text)):
        s = s.strip().lstrip("#>-*|0123456789. ").strip()
        if 10 <= len(s) <= 200 and re.search(r"[ぁ-ん]", s) and s.count("|") < 2:
            out.append(s)
    return out


# ---------- prepare ----------

def prepare() -> None:
    rng = random.Random(0)
    PRIV.mkdir(parents=True, exist_ok=True)
    q = lambda y: [json.loads(l) for l in gzip.open(DATA / f"{y}.jsonl.gz", "rt", encoding="utf-8")]
    llm = [json.loads(l) for f in sorted((ROOT / "corpus/private/llmjp").glob("level0-*.scored.jsonl"))
           for l in open(f, encoding="utf-8") if json.loads(l)["score"] >= 0.5]
    rng.shuffle(llm)
    q26 = q(2026)
    rng.shuffle(q26)
    q22 = q(2022)
    tests = {
        "qiita2026": [d["body"] for d in q26[:500]],
        "qiita2022": [d["body"] for d in rng.sample(q22, 500)],
        "llmjp": [d["text"] for d in llm[:500]],
        "generated_holdout": [],
        "self": [(d / "before.md").read_text(encoding="utf-8") for d in sorted((ROOT / "corpus/private/skill-apply").iterdir()) if (d / "before.md").exists()],
    }
    gen = sorted(glob.glob(str(ROOT / "corpus/paired/tech-qiita*/ai/*/*.md")))
    rng.shuffle(gen)
    tests["generated_holdout"] = [Path(p).read_text(encoding="utf-8") for p in gen[:100]]
    b_docs = [d["body"] for d in q26[500:]] + [Path(p).read_text(encoding="utf-8") for p in gen[100:]]
    a_docs = [d["body"] for y in (2019, 2020, 2021) for d in q(y)] + [d["text"] for d in llm[500:]]
    rng.shuffle(a_docs)

    def write(name, docs, limit_chars=None):
        n = 0
        with open(PRIV / f"train-{name}.txt", "w", encoding="utf-8") as f:
            for d in docs:
                for s in sentences(d):
                    f.write(s + "\n")
                    n += len(s)
                if limit_chars and n >= limit_chars:
                    break
        return n

    nb = write("B", b_docs)
    na = write("A", a_docs, limit_chars=nb)  # A を B と同じ文字数にそろえる
    (PRIV / "tests.json").write_text(json.dumps(tests, ensure_ascii=False), encoding="utf-8")
    print(f"学習 A {na:,} 字 / B {nb:,} 字、検査 { {k: len(v) for k, v in tests.items()} }")


PREAMBLE_RE = re.compile(r"承知|かしこまり|執筆しました|作成しました|作成いたしました|ご提示いただいた|骨子をもとに|^以下は")
PLACEHOLDER_RE = re.compile(r"X{2,}|〇〇|○○|202X|20XX")
POSTSCRIPT_RE = re.compile(r"字数")
CONTACT_RE = re.compile(r"TEL|Tel|電話|FAX|ファックス|E-?mail|メール|〒|住所|所在地|URL")
SEPS = {"---", "***", "___"}


def clean_generated(text: str) -> str:
    """AI に書かせた文書から、本文でないものだけを除く(2026-10-10 に監査して直した)。
    - 冒頭のチャットの返事(「承知いたしました。〜執筆しました。」「以下は〜の記事です。」)。最初の「---」か見出しまでを捨てる
    - 末尾の最後の「---」以降が、見出しのない4行以下の注記(字数・修正の申し出など)なら捨てる。
      Gemini は「---」を節の区切りに使うので、本文の「まとめ」などは残す
    - 伏せ字(XX・○○・202X など)を含む行のうち、ひらがながほとんどない行(日付・署名)と、60字未満の連絡先・住所の行。
      「もし〇〇ならAをする」のように〇〇を変数として使う地の文は残す"""
    lines = text.strip().split("\n")
    if PREAMBLE_RE.search("\n".join(lines[:4])):
        cut = next((i for i, l in enumerate(lines[:12]) if l.strip() in SEPS or l.lstrip().startswith("#")), None)
        if cut is not None:
            lines = lines[cut + (1 if lines[cut].strip() in SEPS else 0):]
    seps = [i for i, l in enumerate(lines) if l.strip() in SEPS]
    if seps:
        tail = [l for l in lines[seps[-1] + 1:] if l.strip()]
        if len(tail) <= 4 and not any(l.lstrip().startswith("#") for l in tail) and \
                (any(POSTSCRIPT_RE.search(l) for l in tail) or all(PLACEHOLDER_RE.search(l) for l in tail)):
            lines = lines[:seps[-1]]
    lines = [l for l in lines if not (PLACEHOLDER_RE.search(l) and
                                      (len(re.findall(r"[ぁ-ん]", l)) < 5 or (CONTACT_RE.search(l) and len(l.strip()) < 60)))]
    return "\n".join(lines).strip()


def prepare_matched(tags: list[str], suffix: str = "2") -> None:
    """F43 を受けて、A と B の話題・分野をそろえる。B は gen_matched.py で書かせた AI の文章、
    A はそのプロンプトの元になった人間の文書(同じタイトルの Qiita 記事・同じ冒頭の業務文書)。
    検査用の文書は A から除く。"""
    prompts = [p for tag in tags for p in json.loads((PRIV / "gen" / f"prompts-{tag}.json").read_text(encoding="utf-8"))]
    tests = json.loads((PRIV / "tests.json").read_text(encoding="utf-8"))
    test_texts = {t for v in tests.values() for t in v}
    qid = {p["id"][2:] for p in prompts if p["src"] == "qiita"}
    bid = {p["id"][2:] for p in prompts if p["src"] == "biz"}
    human = []
    for y in (2019, 2020, 2021):
        for l in gzip.open(DATA / f"{y}.jsonl.gz", "rt", encoding="utf-8"):
            d = json.loads(l)
            if d["id"] in qid and d["body"] not in test_texts:
                human.append(d["body"])
    for f in sorted((ROOT / "corpus/private/llmjp").glob("level0-*.scored.jsonl")):
        for l in open(f, encoding="utf-8"):
            d = json.loads(l)
            if d["docId"] in bid and d["text"] not in test_texts:
                human.append(d["text"])
    ai = [clean_generated(p.read_text(encoding="utf-8")) for tag in tags for e in ("claude", "codex", "gemini")
          for p in sorted((PRIV / "gen" / tag / e).glob("*.md"))]
    a_name, b_name = f"A{suffix}", f"B{suffix}"
    for name, docs in ((a_name, human), (b_name, ai)):
        n = 0
        with open(PRIV / f"train-{name}.txt", "w", encoding="utf-8") as f:
            for d in docs:
                for s_ in sentences(d):
                    f.write(s_ + "\n")
                    n += len(s_)
        print(f"{name}: {len(docs)} 文書、{n:,} 字")
    # AI の文書は長いので、B2 の文を無作為に減らして A2 と同じ字数にそろえる(学習の周回数をそろえる)
    a_chars = sum(len(l) for l in (PRIV / f"train-{a_name}.txt").read_text(encoding="utf-8").split("\n"))
    b_lines = [l for l in (PRIV / f"train-{b_name}.txt").read_text(encoding="utf-8").split("\n") if l]
    random.Random(0).shuffle(b_lines)
    kept, n = [], 0
    for l in b_lines:
        if n >= a_chars:
            break
        kept.append(l)
        n += len(l)
    (PRIV / f"train-{b_name}.txt").write_text("\n".join(kept) + "\n", encoding="utf-8")
    print(f"{b_name} を {n:,} 字にそろえた")


# ---------- train ----------

def train(which: str, steps: int, batch: int, lr: float, bf16: bool = False, lora: int = 0, lora_bias: bool = False) -> None:
    """lora > 0 なら、土台に重ねる差分(LoRA、ランク lora)だけを学習して保存する(配布物を数MBにするため)。
    lora_bias なら全層のバイアスも学習する(出力層のバイアスは語の出やすさそのものを表すので、凍らせると差が弱まる)。"""
    import torch
    from transformers import AutoModelForMaskedLM, AutoTokenizer, Trainer, TrainingArguments
    tok = AutoTokenizer.from_pretrained(BASE)
    model = AutoModelForMaskedLM.from_pretrained(BASE)
    if lora:
        from peft import LoraConfig, get_peft_model
        model = get_peft_model(model, LoraConfig(r=lora, lora_alpha=lora * 2, lora_dropout=0.05,
                                                 target_modules=["query", "key", "value", "dense"],
                                                 bias="all" if lora_bias else "none"))
        model.print_trainable_parameters()
    lines = (PRIV / f"train-{which}.txt").read_text(encoding="utf-8").split("\n")
    # 文をつなげて SEQ トークン前後の塊にする
    chunks, cur = [], ""
    for s in lines:
        if len(cur) + len(s) > SEQ * 1.3:
            chunks.append(cur)
            cur = ""
        cur += s
    if cur:
        chunks.append(cur)
    random.Random(0).shuffle(chunks)
    need = steps * batch
    chunks = chunks[:need] if len(chunks) >= need else chunks

    class DS(torch.utils.data.Dataset):
        def __len__(self):
            return len(chunks)

        def __getitem__(self, i):
            return tok(chunks[i], truncation=True, max_length=SEQ)

    args = TrainingArguments(
        output_dir=str(PRIV / f"ckpt-{which}"), max_steps=steps, per_device_train_batch_size=batch,
        learning_rate=lr, warmup_steps=int(steps * 0.06), weight_decay=0.01, logging_steps=50,
        save_strategy="no", report_to=[], dataloader_num_workers=0, seed=0, bf16=bf16)
    vocab_tokens = tok.convert_ids_to_tokens(list(range(len(tok))))
    cont = torch.tensor([t.startswith("##") for t in vocab_tokens])
    special = set(tok.all_special_ids)

    def collator(features):
        """語単位の伏せ字(whole word masking)。「##」で始まるトークンは前の語の続きとみなす。"""
        batch_ = tok.pad(features, return_tensors="pt")
        ids = batch_["input_ids"]
        labels = ids.clone()
        mask = torch.zeros_like(ids, dtype=torch.bool)
        g = torch.Generator().manual_seed(int(time.time() * 1000) % (2**31))
        for r in range(ids.size(0)):
            words, cur = [], []
            for c, t in enumerate(ids[r].tolist()):
                if t in special:
                    if cur:
                        words.append(cur)
                    cur = []
                    continue
                if cont[t] and cur:
                    cur.append(c)
                else:
                    if cur:
                        words.append(cur)
                    cur = [c]
            if cur:
                words.append(cur)
            n = max(1, round(len(words) * 0.15))
            for wi in torch.randperm(len(words), generator=g)[:n].tolist():
                mask[r, words[wi]] = True
        labels[~mask] = -100
        rnd = torch.rand(ids.shape, generator=g)
        ids[mask & (rnd < 0.8)] = tok.mask_token_id
        swap = mask & (rnd >= 0.8) & (rnd < 0.9)
        ids[swap] = torch.randint(len(tok), ids.shape, generator=g)[swap]
        batch_["input_ids"], batch_["labels"] = ids, labels
        return batch_
    t0 = time.time()
    Trainer(model=model, args=args, train_dataset=DS(), data_collator=collator).train()
    name = f"model-{which}" + (f"-lora{lora}" + ("b" if lora_bias else "") if lora else "")
    model.save_pretrained(PRIV / name)
    tok.save_pretrained(PRIV / name)
    print(f"{which}: {len(chunks)} 塊、{time.time() - t0:.0f} 秒")


# ---------- score ----------

CONTENT = {"動詞", "形容詞", "副詞", "名詞", "形状詞"}


def score(n_docs: int, max_sents: int, batch: int, a_model: str = "A", tag: str = "", b_model: str = "B") -> None:
    import fugashi
    import torch
    from transformers import AutoModelForMaskedLM, AutoTokenizer
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    def load_model(name):
        """model-<name> を読む。LoRA の差分(adapter_config.json がある)なら土台に重ねて合わせる。"""
        if name == "base":
            return AutoModelForMaskedLM.from_pretrained(BASE)
        path = PRIV / f"model-{name}"
        if (path / "adapter_config.json").exists():
            from peft import PeftModel
            return PeftModel.from_pretrained(AutoModelForMaskedLM.from_pretrained(BASE), path).merge_and_unload()
        return AutoModelForMaskedLM.from_pretrained(path)

    tok = AutoTokenizer.from_pretrained(BASE)
    mA = load_model(a_model).to(dev).eval()
    mB = load_model(b_model).to(dev).eval()
    tagger = fugashi.Tagger()
    tests = json.loads((PRIV / "tests.json").read_text(encoding="utf-8"))
    rng = random.Random(0)

    def words_of(s):
        ws = []
        for w in tagger(s):
            f = w.feature
            ws.append((w.surface, f.pos1, f.pos2, f.lemma or w.surface))
        return ws

    @torch.no_grad()
    def run_sentence(s):
        ws = words_of(s)
        ids, spans = [tok.cls_token_id], []
        for surf, *_ in ws:
            sub = tok.convert_tokens_to_ids(tok.subword_tokenizer.tokenize(surf)) if surf.strip() else []
            spans.append((len(ids), len(ids) + len(sub)))
            ids += sub
        ids.append(tok.sep_token_id)
        if len(ids) > SEQ:
            return []
        targets = [i for i, (surf, p1, p2, lem) in enumerate(ws)
                   if p1 in CONTENT and p2 not in {"固有名詞", "数詞", "非自立可能"} and spans[i][1] > spans[i][0]
                   and re.search(r"[ぁ-んァ-ヶ一-龠]", surf)]
        out = []
        for k in range(0, len(targets), batch):
            tb = targets[k:k + batch]
            x = torch.tensor([ids] * len(tb))
            for r, i in enumerate(tb):
                a, b = spans[i]
                x[r, a:b] = tok.mask_token_id
            x = x.to(dev)
            la = torch.log_softmax(mA(x).logits, -1)
            lb = torch.log_softmax(mB(x).logits, -1)
            for r, i in enumerate(tb):
                a, b = spans[i]
                true = ids[a:b]
                pa = sum(la[r, a + j, t].item() for j, t in enumerate(true))
                pb = sum(lb[r, a + j, t].item() for j, t in enumerate(true))
                top = []
                if b - a == 1:
                    top = tok.convert_ids_to_tokens(torch.topk(la[r, a], 6).indices.tolist())
                # A の予想の自信: 1トークン目の位置での最上位の確率と、分布のエントロピー
                pr = la[r, a].exp()
                top1p = pr.max().item()
                ent = -(pr * la[r, a]).sum().item()
                surf, p1, p2, lem = ws[i]
                out.append({"w": surf, "lemma": lem, "pos": p1, "lpA": round(pa, 3), "lpB": round(pb, 3),
                            "d": round(pb - pa, 3), "topA": top, "top1p": round(top1p, 4), "entA": round(ent, 3)})
        return out

    for name, docs in tests.items():
        path = PRIV / f"scores{tag}-{name}.jsonl"
        if path.exists():
            continue
        docs = docs if len(docs) <= n_docs else rng.sample(docs, n_docs)
        t0 = time.time()
        with open(path, "w", encoding="utf-8") as f:
            for di, d in enumerate(docs):
                ss = sentences(d)
                if len(ss) > max_sents:
                    ss = random.Random(di).sample(ss, max_sents)
                for s in ss:
                    rows = run_sentence(s)
                    f.write(json.dumps({"doc": di, "s": s, "words": rows}, ensure_ascii=False) + "\n")
        print(f"{name}: {len(docs)} 文書、{time.time() - t0:.0f} 秒", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare")
    pm = sub.add_parser("prepare-matched")
    pm.add_argument("--tags", nargs="+", default=["prod"])
    pm.add_argument("--suffix", default="2", help="出力の名前(train-A<suffix>.txt・train-B<suffix>.txt)")
    t = sub.add_parser("train")
    t.add_argument("which", choices=["A", "B", "A2", "B2", "A3", "B3"])
    t.add_argument("--lora", type=int, default=0, help="LoRA のランク(0 なら全体を学習)")
    t.add_argument("--lora-bias", action="store_true", help="LoRA で全層のバイアスも学習する")
    t.add_argument("--bf16", action="store_true")
    t.add_argument("--steps", type=int, default=3000)
    t.add_argument("--batch", type=int, default=32)
    t.add_argument("--lr", type=float, default=5e-5)
    s = sub.add_parser("score")
    s.add_argument("--docs", type=int, default=100)
    s.add_argument("--max-sents", type=int, default=40)
    s.add_argument("--batch", type=int, default=48)
    s.add_argument("--a-model", default="A", help="A・base・A2・A3・A3-lora16 など(corpus/private/mlm/model-<名前>)")
    s.add_argument("--b-model", default="B", help="B・B2・B3・B3-lora16 など")
    s.add_argument("--tag", default="")
    a = ap.parse_args()
    if a.cmd == "prepare":
        prepare()
    elif a.cmd == "prepare-matched":
        prepare_matched(a.tags, a.suffix)
    elif a.cmd == "train":
        train(a.which, a.steps, a.batch, a.lr, a.bf16, a.lora, a.lora_bias)
    else:
        score(a.docs, a.max_sents, a.batch, a.a_model, a.tag, a.b_model)


if __name__ == "__main__":
    main()
