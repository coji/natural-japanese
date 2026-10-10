# /// script
# requires-python = ">=3.11"
# dependencies = ["sudachipy", "sudachidict-core"]
# ///
"""corpus/timeslice/usage_frames.py — 比喩の語を「文の形」に分け、AI 以前にもあった使い方と、増えた使い方を分ける。

語の頻度比には話題の変化が混ざる(2026年の Qiita は AI エージェントの話題が多い)。
同じ語の中で「どの形で使われているか」の割合を比べると、話題の影響を受けにくい。
例: 「効く」は AI 以前から「補完が効く」(が+効く)があり、「効いたのは〜」「一番効いた」が増えた。

文の形(frame)は、語の直前の1語(+語)と、直後の付属語の並び(語+)で表す。
    前: 「が+効く」「一番+効く」「の+土台」
    後: 「効く+て+くる」「効く+た+の+は」「土台+と+し+て」
各コーパスで、その形を含む文書の数(1,000文書あたり)と、その語の出現のうちその形が占める割合を出す。

コーパス:
    H    Qiita の AI 以前(2019〜2022年)
    W    Qiita 2026年
    G    タイトルをそろえて生成した AI 記事(tech-qiita / s100 / holdout の全モデル)
    B    LLM-jp コーパス由来の、生成AI以前の説明的・実務的な Web 文章(スコア 0.5 以上)
         仕事の文書での誤検知の目安

出力:
    corpus/timeslice/qiita-aug/usage-frames.md       数値のみ(コミットする)
    corpus/private/usage-frames/examples.json         形ごとの例文(コミットしない)

使い方: uv run corpus/timeslice/usage_frames.py
"""
from __future__ import annotations

import glob
import gzip
import json
import random
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
# 比喩の語の一覧(2026-10-09 時点で lint.py に置いていたものと同じ)
METAPHOR_VOCAB = {
    "効く", "壊れる", "土台", "境界", "入口", "道具", "守る", "届く", "残る", "任せる",
    "繋がる", "つながる", "瞬間", "落とし穴", "踏み込む", "切り分ける", "潰す", "静か",
}

DATA = HERE / "qiita-aug" / "data"
PRIV = ROOT / "corpus/private/usage-frames"
STEMS = re.compile(r"効|壊|土台|境界|入口|入り口|道具|守|届|残|任せ|繋が|つなが|瞬間|落とし穴|踏み込|切り分|潰|静か")
SENT_SPLIT = re.compile(r"(?<=[。！？!?])|\n")
MIN_W = 15          # W でこの文書数以上に出た形だけを表に出す
PER_WORD = 8        # 語ごとに出す形の数

_tok = None


def tok():
    global _tok
    if _tok is None:
        from sudachipy import dictionary, tokenizer
        _tok = (dictionary.Dictionary(dict="core").create(), tokenizer.Tokenizer.SplitMode.C)
    return _tok


def clean(text: str) -> str:
    text = re.sub(r"```.*?```|~~~.*?~~~", "\n", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", "X", text)
    text = re.sub(r"https?://\S+", "", text)
    return text


FUNC = {"助詞", "助動詞", "接尾辞"}


def frames_in(text: str) -> list[tuple[str, list[str], str]]:
    """(語, 形の一覧, 文) を返す。"""
    t, mode = tok()
    out = []
    for s in SENT_SPLIT.split(clean(text)):
        s = s.strip().lstrip("#>-*0123456789. ")
        if len(s) < 6 or not STEMS.search(s):
            continue
        ms = list(t.tokenize(s, mode))
        for i, m in enumerate(ms):
            w = m.dictionary_form()
            if w not in METAPHOR_VOCAB or m.part_of_speech()[0] not in {"動詞", "名詞", "形状詞"}:
                continue
            fr = [f"{w}"]
            if i > 0:
                fr.append(f"{ms[i - 1].surface()}+{w}")
            after, j = [], i + 1
            while j < len(ms) and len(after) < 4 and (ms[j].part_of_speech()[0] in FUNC or ms[j].dictionary_form() in {"くる", "いる", "しまう", "する"}):
                after.append(ms[j].surface())
                j += 1
            for k in range(1, len(after) + 1):
                fr.append(f"{w}+" + "+".join(after[:k]))
            if re.search(r"(のは|のが)", "".join(x.surface() for x in ms[i + 1:i + 5])):
                fr.append(f"{w}…のは(分裂文)")
            out.append((w, fr, s[:120]))
    return out


def doc_frames(text: str) -> list[tuple[str, list[str], str]]:
    try:
        return frames_in(text)
    except Exception:  # noqa: BLE001
        return []


def load_corpora() -> dict[str, list[str]]:
    c: dict[str, list[str]] = {}
    for name, years in (("H", [2019, 2020, 2021, 2022]), ("W", [2026])):
        c[name] = [json.loads(l)["body"] for y in years for l in gzip.open(DATA / f"{y}.jsonl.gz", "rt", encoding="utf-8")]
    c["G"] = [Path(p).read_text(encoding="utf-8") for p in glob.glob(str(ROOT / "corpus/paired/tech-qiita*/ai/*/*.md"))]
    b = []
    for f in sorted((ROOT / "corpus/private/llmjp").glob("level0-*.scored.jsonl")):
        for l in open(f, encoding="utf-8"):
            d = json.loads(l)
            if d["score"] >= 0.5:
                b.append(d["text"])
    c["B"] = b
    return c


def main() -> None:
    corpora = load_corpora()
    n_docs = {k: len(v) for k, v in corpora.items()}
    print("文書数:", n_docs, flush=True)
    docfreq: dict[str, Counter] = {k: Counter() for k in corpora}      # 形 → 文書数
    occ: dict[str, Counter] = {k: Counter() for k in corpora}          # 形 → 出現数
    word_occ: dict[str, Counter] = {k: Counter() for k in corpora}     # 語 → 出現数
    examples: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    with ProcessPoolExecutor(8) as ex:
        for name, docs in corpora.items():
            for res in ex.map(doc_frames, docs, chunksize=64):
                seen = set()
                for w, frs, s in res:
                    word_occ[name][w] += 1
                    for f in frs:
                        occ[name][f] += 1
                        seen.add(f)
                        if len(examples[f][name]) < 30:
                            examples[f][name].append(s)
                docfreq[name].update(seen)
            print(f"  {name} 済み", flush=True)

    def per1k(name, f):
        return docfreq[name][f] / n_docs[name] * 1000

    def share(name, f):
        w = f.split("+")[0].split("…")[0] if not f.startswith(tuple("のがにをでもはと")) else f.split("+")[-1]
        w = next((x for x in METAPHOR_VOCAB if f == x or f.startswith(x + "+") or f.endswith("+" + x) or f.startswith(x + "…")), w)
        return occ[name][f] / max(word_occ[name][w], 1)

    out = ["# 比喩の語の「文の形」ごとの増え方", "",
           "H = Qiita AI 以前(2019〜2022年) / W = Qiita 2026年 / G = タイトルをそろえて生成した AI 記事 / B = LLM-jp 由来の生成AI以前の説明的な Web 文章(スコア 0.5 以上)",
           f"文書数: H {n_docs['H']:,} / W {n_docs['W']:,} / G {n_docs['G']:,} / B {n_docs['B']:,}", "",
           "- 「1,000文書あたり」は、その形を含む文書の数。B の値が仕事の文書での誤検知の目安",
           "- 「語の中の割合」は、その語の出現のうち、その形が占める割合。話題が変わっても語の使い方が変わらなければ、この割合は動かない",
           f"- W で {MIN_W} 文書以上に出た形のうち、語の中の割合が H から W で増えた順に、語ごとに {PER_WORD} 個まで", ""]
    words = sorted(METAPHOR_VOCAB, key=lambda w: -word_occ["W"][w])
    for w in words:
        if word_occ["W"][w] < 30:
            continue
        frs = [f for f in docfreq["W"] if f != w and (f.startswith(w + "+") or f.endswith("+" + w) or f.startswith(w + "…")) and docfreq["W"][f] >= MIN_W]
        frs.sort(key=lambda f: -(share("W", f) - share("H", f)))
        out += [f"## {w}", "",
                f"語そのもの(1,000文書あたり): H {per1k('H', w):.1f} / W {per1k('W', w):.1f} / G {per1k('G', w):.1f} / B {per1k('B', w):.1f}", "",
                "| 形 | H | W | G | B | 語の中の割合 H → W | G |", "|---|---|---|---|---|---|---|"]
        for f in frs[:PER_WORD]:
            out.append(f"| {f} | {per1k('H', f):.1f} | {per1k('W', f):.1f} | {per1k('G', f):.1f} | {per1k('B', f):.1f} | {share('H', f):.0%} → {share('W', f):.0%} | {share('G', f):.0%} |")
        # 割合が減った形(昔からある使い方)も上位3つ
        old = sorted([f for f in frs if docfreq["H"][f] >= 20], key=lambda f: share("W", f) - share("H", f))[:3]
        if old:
            out.append("")
            out.append("割合が減った形(AI 以前の主な使い方): " + "、".join(f"{f}({share('H', f):.0%} → {share('W', f):.0%})" for f in old))
        out.append("")
    (HERE / "qiita-aug" / "usage-frames.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    PRIV.mkdir(parents=True, exist_ok=True)
    rng = random.Random(0)
    ex_out = {f: {k: rng.sample(v, min(8, len(v))) for k, v in d.items()} for f, d in examples.items()}
    (PRIV / "examples.json").write_text(json.dumps(ex_out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
