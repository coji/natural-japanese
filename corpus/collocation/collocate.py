# /// script
# requires-python = ">=3.11"
# dependencies = ["sudachipy", "sudachidict-core"]
# ///
"""corpus/collocation/collocate.py — 語の組み合わせが、AI 以前の日本語でふつうに使われていたかを測る。

AI の文章に増えた「静かに壊れる」「パターンを拾う」「設計が効く」は、どの単語も普通の日本語なのに、
組み合わせが日本語としておかしい。英語の決まった言い回しを、日本語の単語に置き換えたものが多い。
単語の表を作らず、組み合わせが AI 以前の文章に出ていたかどうかで見分けられるかを試す。

取り出す組み合わせ(sudachipy の形態素解析、基本形):
    名詞+格助詞+動詞   「パターン を 拾う」「設計 が 効く」(間の副詞は飛ばす)
    名詞+の+名詞       「分析 の 土台」
    副詞+動詞          「静か(に) 壊れる」
判定: AI 以前の参照コーパスで、名詞と動詞はそれぞれよく出るのに、その組み合わせは一度も出ていないものを
「ふつうでない組み合わせ」とする。期待値は c(名詞,助詞) × c(助詞,動詞) / c(助詞)。期待値が E_MIN 以上で、
実際の回数が 0 のものだけを数える。

参照: Qiita の AI 以前(2019〜2021年)と、LLM-jp 由来の生成AI以前の説明的な文章(500件を除く)
検査: Qiita 2022年(AI 以前、参照に入れない) / LLM-jp の除いた500件 / Qiita 2026年 / 生成記事 / 作者の文書

出力: corpus/collocation/report.md(数値と組み合わせ。本文の引用は入れない。コミットする)
      corpus/private/collocation/(数え上げと、知らせた文の一覧。コミットしない)

使い方: uv run corpus/collocation/collocate.py [--sample 500]
"""
from __future__ import annotations

import argparse
import glob
import gzip
import json
import pickle
import random
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = ROOT / "corpus/timeslice/qiita-aug/data"
PRIV = ROOT / "corpus/private/collocation"
E_MIN = 3.0
CASE = {"が", "を", "に", "で", "へ", "と", "から", "は", "も"}
GENERIC_VERB = {"する", "ある", "いる", "なる", "できる", "れる", "られる", "せる", "させる", "おる"}
FORMAL_NOUN = {"こと", "もの", "ため", "よう", "ところ", "方", "時", "場合", "中", "前", "後", "上", "下", "間", "とき",
               "点", "的", "通り", "以下", "以上", "部分", "必要", "感じ", "形", "際", "毎", "他", "ほか", "等", "など",
               "今回", "今", "一つ", "全て", "すべて", "次", "最初", "自分", "人"}
SENT_SPLIT = re.compile(r"(?<=[。！？!?])|\n")

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
    text = re.sub(r"<[^>]+>", "", text)
    return text


def is_noun(m) -> bool:
    pos = m.part_of_speech()
    return pos[0] == "名詞" and pos[1] == "普通名詞" and m.dictionary_form() not in FORMAL_NOUN and len(m.surface()) >= 2


def noun_at(ms, i) -> str | None:
    """i 番目が名詞なら基本形を、名詞+接尾辞(「順序性」「自動化」)なら合わせた形を返す。"""
    m = ms[i]
    if m.part_of_speech()[0] == "接尾辞" and m.part_of_speech()[1] == "名詞的" and i > 0 and is_noun(ms[i - 1]):
        return ms[i - 1].dictionary_form() + m.surface()
    return m.dictionary_form() if is_noun(m) else None


def skippable(ms, j) -> int:
    """名詞と述語のあいだで飛ばしてよい語の長さ(副詞、「形状詞+に」、「後から」のような副詞的な名詞+助詞)。0 なら飛ばさない。"""
    pos = ms[j].part_of_speech()
    if pos[0] == "副詞":
        return 1
    if pos[0] == "形状詞" and j + 1 < len(ms) and ms[j + 1].surface() == "に":
        return 2
    if pos[0] == "名詞" and len(pos) > 2 and pos[2] == "副詞可能":
        return 2 if j + 1 < len(ms) and ms[j + 1].surface() in {"から", "に", "まで", "は"} else 1
    return 0


def is_pred(m) -> bool:
    pos = m.part_of_speech()
    return pos[0] in {"動詞", "形容詞"} and m.dictionary_form() not in GENERIC_VERB


def pairs_in_sentence(s: str) -> list[str]:
    t, mode = tok()
    ms = list(t.tokenize(s[:600], mode))
    out = []
    for i, m in enumerate(ms):
        if i + 1 >= len(ms):
            break
        nxt = ms[i + 1]
        # 名詞 + 格助詞 + 動詞(副詞・「形状詞+に」などを飛ばす)
        n = noun_at(ms, i)
        if n and nxt.part_of_speech()[0] == "助詞" and nxt.surface() in CASE:
            j = i + 2
            while j < len(ms) and (k := skippable(ms, j)):
                j += k
            if j < len(ms) and is_pred(ms[j]):
                out.append(f"{n}|{nxt.surface()}|{ms[j].dictionary_form()}")
        # 名詞 + の + 名詞
        if n and nxt.surface() == "の" and i + 2 < len(ms) and (n2 := noun_at(ms, i + 3) if i + 3 < len(ms) and ms[i + 3].part_of_speech()[0] == "接尾辞" else noun_at(ms, i + 2)):
            out.append(f"{n}|の|{n2}")
        # 副詞(または形状詞+に) + 動詞
        if m.part_of_speech()[0] == "副詞" and is_pred(nxt):
            out.append(f"{m.dictionary_form()}|ADV|{nxt.dictionary_form()}")
        if m.part_of_speech()[0] == "形状詞" and nxt.surface() == "に" and i + 2 < len(ms) and is_pred(ms[i + 2]):
            out.append(f"{m.dictionary_form()}|ADV|{ms[i + 2].dictionary_form()}")
    return out


def doc_pairs(text: str) -> tuple[int, list[tuple[str, str]]]:
    """(地の文の文字数, [(組み合わせ, 文)])"""
    chars, out = 0, []
    try:
        for s in SENT_SPLIT.split(clean(text)):
            s = s.strip().lstrip("#>-*|0123456789. ")
            if len(s) < 8 or not re.search(r"[ぁ-ん]", s):
                continue
            chars += len(s)
            for k in pairs_in_sentence(s):
                out.append((k, s[:160]))
    except Exception:  # noqa: BLE001
        pass
    return chars, out


def load() -> dict[str, list[str]]:
    rng = random.Random(0)
    c: dict[str, list[str]] = {}
    c["ref_qiita"] = [json.loads(l)["body"] for y in (2019, 2020, 2021) for l in gzip.open(DATA / f"{y}.jsonl.gz", "rt", encoding="utf-8")]
    b = [json.loads(l)["text"] for f in sorted((ROOT / "corpus/private/llmjp").glob("level0-*.scored.jsonl"))
         for l in open(f, encoding="utf-8") if json.loads(l)["score"] >= 0.5]
    rng.shuffle(b)
    c["test_llmjp"], c["ref_llmjp"] = b[:500], b[500:]
    q22 = [json.loads(l)["body"] for l in gzip.open(DATA / "2022.jsonl.gz", "rt", encoding="utf-8")]
    c["test_qiita2022"] = rng.sample(q22, 500)
    q26 = [json.loads(l)["body"] for l in gzip.open(DATA / "2026.jsonl.gz", "rt", encoding="utf-8")]
    c["test_qiita2026"] = rng.sample(q26, 500)
    c["test_generated"] = [Path(p).read_text(encoding="utf-8") for p in sorted(glob.glob(str(ROOT / "corpus/paired/tech-qiita*/ai/*/*.md")))]
    c["test_self"] = [(d / "before.md").read_text(encoding="utf-8") for d in sorted((ROOT / "corpus/private/skill-apply").iterdir()) if (d / "before.md").exists()]
    return c


def extract(corpora) -> dict:
    cache = PRIV / "pairs.pkl"
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    res = {}
    with ProcessPoolExecutor(8) as ex:
        for name, docs in corpora.items():
            rows = list(ex.map(doc_pairs, docs, chunksize=32))
            if name.startswith("ref_"):
                cnt = Counter()
                for _, ps in rows:
                    cnt.update(k for k, _ in ps)
                res[name] = cnt
            else:
                res[name] = rows
            print(f"  {name}: {len(docs)} 文書", flush=True)
    PRIV.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(pickle.dumps(res))
    return res


class Reference:
    def __init__(self, counts: Counter):
        self.c = counts
        self.left, self.right, self.mid = Counter(), Counter(), Counter()
        for k, v in counts.items():
            a, p, b = k.split("|")
            self.left[(a, p)] += v
            self.right[(p, b)] += v
            self.mid[p] += v

    def expected(self, k: str) -> float:
        a, p, b = k.split("|")
        return self.left[(a, p)] * self.right[(p, b)] / max(self.mid[p], 1)

    def unusual(self, k: str) -> bool:
        return self.c.get(k, 0) == 0 and self.expected(k) >= E_MIN


def main() -> None:
    global E_MIN
    ap = argparse.ArgumentParser()
    ap.add_argument("--e-min", type=float, default=3.0)
    a = ap.parse_args()
    E_MIN = a.e_min
    corpora = load()
    print({k: len(v) for k, v in corpora.items()}, flush=True)
    res = extract(corpora)
    ref = Reference(res["ref_qiita"] + res["ref_llmjp"])
    print(f"参照の組み合わせ: {len(ref.c):,} 種類", flush=True)

    label = {"test_qiita2022": "Qiita 2022年(AI以前・参照外)", "test_llmjp": "仕事の文章(AI以前・参照外)",
             "test_qiita2026": "Qiita 2026年", "test_generated": "生成記事", "test_self": "作者の文書"}
    out = ["# 語の組み合わせで見る、ふつうでない言い回し", "",
           "参照: Qiita の AI 以前(2019〜2021年)と、LLM-jp 由来の生成AI以前の説明的な文章。",
           f"判定: 参照で、名詞と動詞はそれぞれよく出る(組み合わせの期待値 {E_MIN} 以上)のに、組み合わせは一度も出ていない。", "",
           "| 検査セット | 文書 | 1,000字あたり | 1件以上ある文書 |", "|---|---|---|---|"]
    flagged: dict[str, list[tuple[str, str, float]]] = {}
    kinds: dict[str, Counter] = {}
    for name in label:
        rows = res[name]
        chars = sum(c for c, _ in rows)
        hits = []
        ndoc = 0
        for di, (_, ps) in enumerate(rows):
            h = [(k, s, ref.expected(k)) for k, s in ps if ref.unusual(k)]
            ndoc += bool(h)
            hits += [(f"{name}:{di}", k, s, e) for k, s, e in h]
        flagged[name] = hits
        kinds[name] = Counter(k for _, k, _, _ in hits)
        out.append(f"| {label[name]} | {len(rows)} | {len(hits) / max(chars, 1) * 1000:.2f} | {ndoc / max(len(rows), 1):.0%} |")

    # AI 側でよく出た、ふつうでない組み合わせ(Qiita 2026年と生成記事の合計)
    ai = kinds["test_qiita2026"] + kinds["test_generated"]
    human = kinds["test_qiita2022"] + kinds["test_llmjp"]
    out += ["", "## AI の文章でよく出た、ふつうでない組み合わせ(上位40)", "",
            "| 組み合わせ | Qiita 2026年 | 生成記事 | AI以前(参照外) | 参照での期待値 |", "|---|---|---|---|---|"]
    for k, n in ai.most_common(40):
        out.append(f"| {k.replace('|ADV|', ' に/と + ').replace('|', ' ')} | {kinds['test_qiita2026'][k]} | {kinds['test_generated'][k]} | {human[k]} | {ref.expected(k):.1f} |")
    out += ["", "## AI 以前の文章(参照外)で知らせた組み合わせ(誤検知の候補、上位20)", "",
            "| 組み合わせ | 回数 | 参照での期待値 |", "|---|---|---|"]
    for k, n in human.most_common(20):
        out.append(f"| {k.replace('|ADV|', ' に/と + ').replace('|', ' ')} | {n} | {ref.expected(k):.1f} |")
    (HERE / "report.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    PRIV.mkdir(parents=True, exist_ok=True)
    (PRIV / "flagged.json").write_text(json.dumps(flagged, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
