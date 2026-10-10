# /// script
# requires-python = ">=3.11"
# ///
"""corpus/mlm/compare_pairs.py — 話題をそろえ直したモデル対(A2・B2、A3・B3)と、元の対(A・B)を比べる。

元の対: A = AI 以前の Qiita + LLM-jp、B = Qiita 2026年 + 生成記事(話題がずれている)
新しい対: B2 = AI 以前の Qiita のタイトルと業務文書の冒頭で3社に書かせた文章、A2 = その元の人間の文書(話題がそろっている)
         A3・B3 は同じ作り方でデータを2.5倍にしたもの。全体を学習した版(-m3)と LoRA 版(-m3l)
見ること: 差が大きい語の量、記事の語が残るか、業務・話題の語が外れるか、上位の語

入力: corpus/private/mlm/scores-v2-*.jsonl(元の対)、scores-m2-*.jsonl・scores-m3-*.jsonl・scores-m3l-*.jsonl(新しい対)
出力: corpus/mlm/compare-pairs.md(数値と語のみ。コミットする)
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PRIV = ROOT / "corpus/private/mlm"
SETS = {"qiita2022": "Qiita 2022年(AI以前)", "llmjp": "仕事の文章(AI以前)", "qiita2026": "Qiita 2026年",
        "generated_holdout": "生成記事(学習外)", "self": "作者の文書"}
PRE, POST = ("qiita2022", "llmjp"), ("qiita2026", "generated_holdout", "self")
BLOG = {"実測", "疑う", "照合", "見落とす", "突き合わせる", "断定", "取り違える", "入り口", "土台", "道具", "核心", "主役", "構図",
        "線引き", "事故", "混ざる", "落とし穴", "破綻", "実害", "素通り", "切り分ける", "潰す", "踏み込む", "塞ぐ", "溶かす", "逃がす",
        "倒す", "既定", "別物", "定番", "要点", "素朴", "定石", "桁違い", "利く", "瞬間", "壊れる", "境界", "静か", "黙る", "正本",
        "拾う", "寄せる", "畳む", "刺さる", "地味"}
WORK = {"少額", "前回", "日次", "起票", "商談", "推論", "生成", "会話", "本文", "技術", "月次", "額", "平常", "推定", "習い事", "目安",
        "起こし", "差分", "個人", "開発", "人間"}
T = 3.0


def ok(w) -> bool:
    return not re.fullmatch(r"[ァ-ヶー・]+", w["w"]) and "-" not in w["lemma"] and not re.search(r"[A-Za-z]", w["w"])


def load(tag, name):
    p = PRIV / f"scores{tag}-{name}.jsonl"
    return [json.loads(l) for l in open(p, encoding="utf-8")] if p.exists() else []


def med(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else float("nan")


def main() -> None:
    pairs = {"元の対(A・B)": "-v2", "話題をそろえた対(A2・B2)": "-m2", "データを2.5倍にした対(A3・B3)": "-m3",
             "同じデータで LoRA の対(A3・B3、r=16)": "-m3l",
             "LoRA r=32・バイアスも学習(A3・B3)": "-m3lb"}
    data = {k: {n: load(t, n) for n in SETS} for k, t in pairs.items()}
    pairs = {k: t for k, t in pairs.items() if any(data[k].values())}
    out = ["# 話題をそろえたモデル対と、元のモデル対の比較", "",
           f"カタカナ語・英字の語を除いた内容語。閾値は差 > {T}。", "",
           "## 差が大きい語の量(地の文1,000字あたり)", "", "| 検査セット | " + " | ".join(pairs) + " |", "|---|" + "---|" * len(pairs)]
    for n, lab in SETS.items():
        cells = []
        for k in pairs:
            rows = data[k][n]
            chars = sum(len(r["s"]) for r in rows) or 1
            cells.append(f"{sum(1 for r in rows for w in r['words'] if ok(w) and w['d'] > T) / chars * 1000:.2f}")
        out.append(f"| {lab} | " + " | ".join(cells) + " |")
    out += ["", "## 記事の語と、業務・話題の語(AI 時代の3セット)", "",
            "| 対 | 記事の語の差の中央値 | 記事の語で差 > 3 の割合 | 業務・話題の語の差の中央値 | 業務・話題の語で差 > 3 の割合 | 全内容語の差の中央値 |",
            "|---|---|---|---|---|---|"]
    for k in pairs:
        ws = [w for n in POST for r in data[k][n] for w in r["words"] if ok(w)]
        b = [w["d"] for w in ws if w["lemma"] in BLOG]
        wk = [w["d"] for w in ws if w["lemma"] in WORK]
        out.append(f"| {k} | {med(b):.2f} | {sum(x > T for x in b) / max(len(b), 1):.0%} | {med(wk):.2f} | "
                   f"{sum(x > T for x in wk) / max(len(wk), 1):.0%} | {med([w['d'] for w in ws]):.2f} |")
    for k in pairs:
        post = Counter(w["lemma"] for n in POST for r in data[k][n] for w in r["words"] if ok(w) and w["d"] > T)
        pre = Counter(w["lemma"] for n in PRE for r in data[k][n] for w in r["words"] if ok(w) and w["d"] > T)
        out += ["", f"## {k}: AI 時代の3セットで差 > {T} が多い語(上位40)", "",
                "| 語 | AI時代 | AI以前 | 群 |", "|---|---|---|---|"]
        for lem, c in post.most_common(40):
            grp = "記事" if lem in BLOG else ("業務・話題" if lem in WORK else "")
            out.append(f"| {lem} | {c} | {pre.get(lem, 0)} | {grp} |")
    # LoRA 版が全体を学習した版の代わりになるか(同じ文を選んでいるので、語ごとの差を並べて相関を見る)
    full = "データを2.5倍にした対(A3・B3)"
    for lora in ("同じデータで LoRA の対(A3・B3、r=16)", "LoRA r=32・バイアスも学習(A3・B3)"):
        if full not in pairs or lora not in pairs:
            continue
        xs, ys = [], []
        for n in SETS:
            for r1, r2 in zip(data[full][n], data[lora][n]):
                if r1["s"] == r2["s"]:
                    for w1, w2 in zip(r1["words"], r2["words"]):
                        if ok(w1):
                            xs.append(w1["d"])
                            ys.append(w2["d"])
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        r = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(
            sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
        both = sum(1 for x, y in zip(xs, ys) if x > T and y > T)
        out += ["", f"## {lora} と全体を学習した版の一致", "",
                f"- 内容語 {len(xs):,} 件での、語ごとの差の相関係数: {r:.3f}",
                f"- 差 > {T} の語: 全体 {sum(x > T for x in xs):,} 件、LoRA {sum(y > T for y in ys):,} 件、両方 {both:,} 件"]
    (HERE / "compare-pairs.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
