# /// script
# requires-python = ">=3.11"
# dependencies = ["scikit-learn>=1.5", "numpy"]
# ///
"""corpus/llmjp/train_classifier.py — LLM のラベルで軽い分類器を学習させ、絞り込んだ全文書に当てる。

FineWeb-Edu と同じ考え方で、少数(数千件)に付けた LLM のラベルを、安い分類器で全件に広げる。
目的変数は「説明的・実務的な文章として使える」(usable が 2 以上。翻訳記事とスパムは 0 とみなす)。
特徴量は本文(先頭と末尾の短い行を切り落とした先頭 1,500 字)の文字 2〜4-gram の TF-IDF。

出力:
    corpus/llmjp/classifier-report.md         精度の報告(コミットする)
    corpus/llmjp/manifest/<file>.scored.jsonl 本文なしの一覧にスコアを足したもの(公開できる形)
    corpus/private/llmjp/<file>.scored.jsonl  本文つき(コミットしない)

使い方: uv run corpus/llmjp/train_classifier.py --labels labels-v2.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_curve, roc_auc_score
from sklearn.model_selection import train_test_split

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIV = ROOT / "corpus/private/llmjp"
sys.path.insert(0, str(HERE))
from label_sample import MAX_CHARS, trim  # noqa: E402


def target(label: dict) -> int:
    if label.get("translated") or label.get("spam"):
        return 0
    return 1 if (label.get("usable") or 0) >= 2 else 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default="labels-v2.jsonl")
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(PRIV / a.labels, encoding="utf-8")]
    X = [r["excerpt"] for r in rows]
    y = np.array([target(r["label"]) for r in rows])
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=0, stratify=y)
    vec = TfidfVectorizer(analyzer="char", ngram_range=(2, 4), min_df=3, max_features=200_000, sublinear_tf=True)
    clf = LogisticRegression(max_iter=2000, C=4.0, class_weight="balanced")
    clf.fit(vec.fit_transform(Xtr), ytr)
    p = clf.predict_proba(vec.transform(Xte))[:, 1]
    auc = roc_auc_score(yte, p)
    prec, rec, thr = precision_recall_curve(yte, p)

    out = ["# 分類器の精度", "",
           f"ラベル {len(rows)} 件(正例 {int(y.sum())} 件、{y.mean():.0%})。学習 80% / 評価 20%。",
           f"目的変数: usable >= 2 かつ翻訳記事でもスパムでもない。特徴量: 文字 2〜4-gram の TF-IDF。",
           "", f"評価データでの AUC: {auc:.3f}", "", "| 閾値 | 適合率 | 再現率 |", "|---|---|---|"]
    for t in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
        i = np.searchsorted(thr, t)
        if i < len(thr):
            out.append(f"| {t} | {prec[i]:.2f} | {rec[i]:.2f} |")
    # 全件で学習し直して、絞り込んだ全文書に当てる
    vec.fit(X)
    clf.fit(vec.transform(X), y)
    totals = []
    (HERE / "manifest").mkdir(exist_ok=True)
    for f in sorted(PRIV.glob("level0-*.jsonl")):
        if f.name.endswith(".scored.jsonl"):
            continue
        docs = [json.loads(l) for l in open(f, encoding="utf-8")]
        texts = [trim(d["text"])[:MAX_CHARS] for d in docs]
        scores = clf.predict_proba(vec.transform(texts))[:, 1]
        with open(PRIV / f"{f.stem}.scored.jsonl", "w", encoding="utf-8") as fp, \
             open(HERE / "manifest" / f"{f.stem}.scored.jsonl", "w", encoding="utf-8") as fm:
            for d, s in zip(docs, scores):
                row = {k: d[k] for k in ("source", "docId", "url", "date", "type", "sha256", "rule_version")}
                row["score"] = round(float(s), 3)
                fm.write(json.dumps(row, ensure_ascii=False) + "\n")
                fp.write(json.dumps({**row, "text": d["text"]}, ensure_ascii=False) + "\n")
        totals.append((f.stem, len(docs), int((scores >= 0.5).sum()), int((scores >= 0.7).sum())))
    out += ["", "## 全文書への適用", "", "| ファイル | 文書数 | スコア 0.5 以上 | 0.7 以上 |", "|---|---|---|---|"]
    out += [f"| {n} | {t} | {a5} | {a7} |" for n, t, a5, a7 in totals]
    (HERE / "classifier-report.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
