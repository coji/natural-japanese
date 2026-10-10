# /// script
# requires-python = ">=3.11"
# ///
"""corpus/mlm/analyze.py — mlm_contrast.py の score の結果をまとめる。

見ること:
    1. 差(log P_B − log P_A)が閾値を超えた語の数。AI 以前の検査セット(参照外)と、AI 時代の検査セットで比べる
    2. 逆瀬川さんの記事の語(教えていない)が、差の大きい語として出てくるか
    3. 差の大きい語の例と、A(AI 以前のモデル)が出す言い換えの候補(本文を含むので private に出す)

出力: corpus/mlm/report.md(数値と語。本文の引用は入れない。コミットする)
      corpus/private/mlm/examples.md(例文と候補。コミットしない)

使い方: uv run corpus/mlm/analyze.py
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PRIV = ROOT / "corpus/private/mlm"
SETS = {"qiita2022": "Qiita 2022年(AI以前)", "llmjp": "仕事の文章(AI以前)", "qiita2026": "Qiita 2026年",
        "generated_holdout": "生成記事(学習外)", "self": "作者の文書"}
BLOG = ["実測", "疑う", "照合", "見落とす", "突き合わせる", "断定", "取り違える", "入口", "入り口", "土台", "道具", "核心", "主役", "構図",
        "線引き", "事故", "混ざる", "落とし穴", "破綻", "実害", "素通り", "切り分ける", "潰す", "踏み込む", "塞ぐ", "溶かす", "逃がす",
        "倒す", "既定", "別物", "定番", "要点", "素朴", "定石", "桁違い", "効く", "瞬間", "壊れる", "境界", "静か", "黙る", "正本",
        "拾う", "寄せる", "畳む", "刺さる"]
THRESHOLDS = [2.0, 3.0, 4.0]


def load(name):
    rows = []
    p = PRIV / f"scores-{name}.jsonl"
    if not p.exists():
        return rows
    for l in open(p, encoding="utf-8"):
        rows.append(json.loads(l))
    return rows


def main() -> None:
    data = {k: load(k) for k in SETS}
    out = ["# 2つの BERT の穴埋めで見る、AI 時代の言い回し", "",
           "A = AI 以前の文章で追加学習、B = AI 時代の文章で追加学習(土台はどちらも tohoku-nlp/bert-base-japanese-v3)。",
           "差 = log P_B(語) − log P_A(語)。大きいほど、AI 時代のモデルだけがその位置にその語を置く。", "",
           "## 差が閾値を超えた語の数(地の文1,000字あたり / 1件以上ある文書の割合)", "",
           "| 検査セット | 文書 | 語 | " + " | ".join(f"差 > {t}" for t in THRESHOLDS) + " |",
           "|---|---|---|" + "---|" * len(THRESHOLDS)]
    for k, label in SETS.items():
        rows = data[k]
        if not rows:
            continue
        chars = sum(len(r["s"]) for r in rows)
        docs = {r["doc"] for r in rows}
        nw = sum(len(r["words"]) for r in rows)
        cells = []
        for t in THRESHOLDS:
            n = sum(1 for r in rows for w in r["words"] if w["d"] > t)
            dd = {r["doc"] for r in rows if any(w["d"] > t for w in r["words"])}
            cells.append(f"{n / chars * 1000:.2f} / {len(dd) / len(docs):.0%}")
        out.append(f"| {label} | {len(docs)} | {nw:,} | " + " | ".join(cells) + " |")

    # 記事の語の差の分布
    out += ["", "## 逆瀬川さんの記事の語(モデルには教えていない)", "",
            "各語の出現ごとの差の中央値。AI 以前の2セットと、AI 時代の2セット(Qiita 2026年・生成記事)で分ける。全内容語の中央値も並べる。", "",
            "| 語 | AI以前での出現 | 差の中央値(AI以前) | AI時代での出現 | 差の中央値(AI時代) |", "|---|---|---|---|---|"]
    def med(xs):
        xs = sorted(xs)
        return xs[len(xs) // 2] if xs else float("nan")
    pre = [w for k in ("qiita2022", "llmjp") for r in data[k] for w in r["words"]]
    post = [w for k in ("qiita2026", "generated_holdout") for r in data[k] for w in r["words"]]
    out.append(f"| (全内容語) | {len(pre):,} | {med([w['d'] for w in pre]):.2f} | {len(post):,} | {med([w['d'] for w in post]):.2f} |")
    by_pre, by_post = defaultdict(list), defaultdict(list)
    for w in pre:
        by_pre[w["lemma"]].append(w["d"])
    for w in post:
        by_post[w["lemma"]].append(w["d"])
    for b in BLOG:
        if by_pre.get(b) or by_post.get(b):
            out.append(f"| {b} | {len(by_pre.get(b, []))} | {med(by_pre.get(b, [])):.2f} | {len(by_post.get(b, []))} | {med(by_post.get(b, [])):.2f} |")

    # AI 時代のセットで差が大きく出た語(教えていない語の発見)
    t = 3.0
    flag_post = Counter(w["lemma"] for w in post if w["d"] > t)
    flag_pre = Counter(w["lemma"] for w in pre if w["d"] > t)
    out += ["", f"## AI 時代のセットで差 > {t} になった回数が多い語(上位50)", "",
            "| 語 | AI時代で差>3 | 出現 | AI以前で差>3 | 出現 | 記事の語 |", "|---|---|---|---|---|---|"]
    for lem, n in flag_post.most_common(50):
        out.append(f"| {lem} | {n} | {len(by_post[lem])} | {flag_pre.get(lem, 0)} | {len(by_pre.get(lem, []))} | {'○' if lem in BLOG else ''} |")
    out += ["", f"## AI 以前のセットで差 > {t} になった語(誤検知の候補、上位20)", "", "| 語 | 回数 | 出現 |", "|---|---|---|"]
    for lem, n in flag_pre.most_common(20):
        out.append(f"| {lem} | {n} | {len(by_pre[lem])} |")
    (HERE / "report.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))

    # 例文(private)
    ex = ["# 差の大きい語の例と、AI 以前のモデルの候補", ""]
    for k in ("self", "qiita2026", "generated_holdout", "qiita2022", "llmjp"):
        ex += [f"## {SETS[k]}", ""]
        items = sorted(((w["d"], r["s"], w) for r in data[k] for w in r["words"]), key=lambda x: -x[0])[:40]
        for d, s, w in items:
            ex.append(f"- **{w['w']}**(差 {d:.1f}、A の候補: {'・'.join(w['topA'][:5]) or '—'}) {s}")
        ex.append("")
    (PRIV / "examples.md").write_text("\n".join(ex), encoding="utf-8")


if __name__ == "__main__":
    main()
