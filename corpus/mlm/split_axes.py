# /// script
# requires-python = ">=3.11"
# ///
"""corpus/mlm/split_axes.py — 差が大きい語を「A に代わりの語がある」と「A の予想が定まらない」に分ける。

Fable の指摘(2026-10-10): 差 d = log P_B − log P_A が大きい理由は2種類ある。
    (a) A がその位置に自信のある別の語を持っている(効く → 影響する)。言い回しの癖で、直す対象
    (b) A の予想が定まらず、その語を知らないだけ(起票・商談・推論)。最近の業務や話題の語で、直す対象ではない
A の1トークン目の位置での最上位の確率(top1p)と分布のエントロピー(entA)で分けられるかを見る。

あわせて、追加学習した A の代わりに素の土台(tohoku-nlp/bert-base-japanese-v3)を使った差(d_base)が、
d_A とどれくらい一致するかを見る。一致すれば A の追加学習は要らない。

入力: corpus/private/mlm/scores-v2-*.jsonl(A=追加学習)、scores-base-*.jsonl(A=素の土台)
出力: corpus/mlm/split-axes.md(数値と語のみ。コミットする)

使い方: uv run corpus/mlm/split_axes.py
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PRIV = ROOT / "corpus/private/mlm"
SETS = ["qiita2022", "llmjp", "qiita2026", "generated_holdout", "self"]
AI_SETS = ["qiita2026", "generated_holdout", "self"]
BLOG = {"実測", "疑う", "照合", "見落とす", "突き合わせる", "断定", "取り違える", "入り口", "土台", "道具", "核心", "主役", "構図",
        "線引き", "事故", "混ざる", "落とし穴", "破綻", "実害", "素通り", "切り分ける", "潰す", "踏み込む", "塞ぐ", "溶かす", "逃がす",
        "倒す", "既定", "別物", "定番", "要点", "素朴", "定石", "桁違い", "利く", "瞬間", "壊れる", "境界", "静か", "黙る", "正本",
        "拾う", "寄せる", "畳む", "刺さる", "地味"}
WORK = {"少額", "前回", "日次", "起票", "商談", "推論", "生成", "会話", "本文", "技術", "月次", "額", "平常", "推定", "習い事", "目安",
        "起こし", "差分", "個人", "開発", "人間"}


def ok(w) -> bool:
    return not re.fullmatch(r"[ァ-ヶー・]+", w["w"]) and "-" not in w["lemma"] and not re.search(r"[A-Za-z]", w["w"])


def load(tag, name):
    p = PRIV / f"scores{tag}-{name}.jsonl"
    return [json.loads(l) for l in open(p, encoding="utf-8")] if p.exists() else []


def med(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else float("nan")


def main() -> None:
    out = ["# 差が大きい語を、A の予想の自信で分ける", ""]
    v2 = {n: load("-v2", n) for n in SETS}
    flagged = [w for n in AI_SETS for r in v2[n] for w in r["words"] if ok(w) and w["d"] > 4]
    pre_flagged = [w for n in ("qiita2022", "llmjp") for r in v2[n] for w in r["words"] if ok(w) and w["d"] > 4]
    blog = [w for w in flagged if w["lemma"] in BLOG]
    work = [w for w in flagged if w["lemma"] in WORK]
    out += ["## 1. 記事の語と業務・話題の語で、A の自信はちがうか(AI 時代の文章で差 > 4 の語)", "",
            "| 群 | 件数 | A の最上位の確率(中央値) | A のエントロピー(中央値) |", "|---|---|---|---|",
            f"| 逆瀬川さんの記事の語 | {len(blog)} | {med([w['top1p'] for w in blog]):.3f} | {med([w['entA'] for w in blog]):.2f} |",
            f"| 業務・話題の語(F42 で混ざった語) | {len(work)} | {med([w['top1p'] for w in work]):.3f} | {med([w['entA'] for w in work]):.2f} |",
            f"| 差 > 4 の語すべて | {len(flagged)} | {med([w['top1p'] for w in flagged]):.3f} | {med([w['entA'] for w in flagged]):.2f} |",
            f"| AI 以前の文章で差 > 4 の語 | {len(pre_flagged)} | {med([w['top1p'] for w in pre_flagged]):.3f} | {med([w['entA'] for w in pre_flagged]):.2f} |"]
    # 閾値で分けたときの、記事の語の残り方と業務の語の落ち方
    out += ["", "## 2. A の最上位の確率で絞ったとき", "",
            "| 条件 | 記事の語が残る割合 | 業務・話題の語が残る割合 | AI 時代の文章 1,000字あたり | AI 以前の文章 1,000字あたり |", "|---|---|---|---|---|"]
    chars_ai = sum(len(r["s"]) for n in AI_SETS for r in v2[n])
    chars_pre = sum(len(r["s"]) for n in ("qiita2022", "llmjp") for r in v2[n])
    for th in (0.0, 0.1, 0.2, 0.3, 0.5):
        cond = lambda w: w["top1p"] >= th
        out.append(f"| 差 > 4 かつ最上位の確率 ≥ {th} | {sum(map(cond, blog)) / max(len(blog), 1):.0%} | {sum(map(cond, work)) / max(len(work), 1):.0%} | "
                   f"{sum(map(cond, flagged)) / chars_ai * 1000:.2f} | {sum(map(cond, pre_flagged)) / chars_pre * 1000:.2f} |")
    for th in (6.0, 5.0, 4.0, 3.0):
        cond = lambda w: w["entA"] <= th
        out.append(f"| 差 > 4 かつエントロピー ≤ {th} | {sum(map(cond, blog)) / max(len(blog), 1):.0%} | {sum(map(cond, work)) / max(len(work), 1):.0%} | "
                   f"{sum(map(cond, flagged)) / chars_ai * 1000:.2f} | {sum(map(cond, pre_flagged)) / chars_pre * 1000:.2f} |")
    # 語ごとの中央値
    by = defaultdict(list)
    for w in flagged:
        by[w["lemma"]].append(w)
    out += ["", "## 3. 語ごと(AI 時代の文章で差 > 4 が3回以上の語、A の最上位の確率の中央値が高い順)", "",
            "| 語 | 回数 | A の最上位の確率 | エントロピー | 群 |", "|---|---|---|---|---|"]
    rows = [(lem, ws) for lem, ws in by.items() if len(ws) >= 3]
    rows.sort(key=lambda x: -med([w["top1p"] for w in x[1]]))
    for lem, ws in rows:
        grp = "記事" if lem in BLOG else ("業務・話題" if lem in WORK else "")
        out.append(f"| {lem} | {len(ws)} | {med([w['top1p'] for w in ws]):.3f} | {med([w['entA'] for w in ws]):.2f} | {grp} |")

    # 素の土台との比較
    base = {n: load("-base", n) for n in SETS}
    if all(base.values()):
        da, db = [], []
        for n in SETS:
            for r1, r2 in zip(v2[n], base[n]):
                if r1["s"] != r2["s"]:
                    continue
                for w1, w2 in zip(r1["words"], r2["words"]):
                    if ok(w1):
                        da.append(w1["d"])
                        db.append(w2["d"])
        ma, mb = sum(da) / len(da), sum(db) / len(db)
        cov = sum((x - ma) * (y - mb) for x, y in zip(da, db))
        r = cov / math.sqrt(sum((x - ma) ** 2 for x in da) * sum((y - mb) ** 2 for y in db))
        out += ["", "## 4. A の代わりに素の土台を使った差(d_base)と、d_A の一致", "",
                f"内容語 {len(da):,} 件での相関係数: {r:.3f}", "",
                "| 検査セット | d_A > 3(1,000字あたり) | d_base > 3(1,000字あたり) |", "|---|---|---|"]
        for n in SETS:
            chars = sum(len(r_["s"]) for r_ in v2[n])
            na = sum(1 for r_ in v2[n] for w in r_["words"] if ok(w) and w["d"] > 3)
            nb = sum(1 for r_ in base[n] for w in r_["words"] if ok(w) and w["d"] > 3)
            out.append(f"| {n} | {na / chars * 1000:.2f} | {nb / chars * 1000:.2f} |")
    (HERE / "split-axes.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
