# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "scikit-learn>=1.4",
#     "numpy",
# ]
# ///
"""classify_eval.py — トラックC: 埋め込み+ロジスティック回帰による human/AI 分類器の評価。

embed_cache.py が作った cache/embeddings.npz + cache/meta.json を読み込み、
以下4種の評価を行う(すべて README/ブリーフの判定規律に従う):

1. ランダム分割 5-fold CV (楽観ベースライン): AUC / accuracy
2. モデル外挿 (leave-one-model-out): AI 7モデルのうち6で学習→残り1で評価、7通り全部
3. ジャンル外挿 (leave-one-genre-out): ジャンルごとに1つ除いて学習→評価
4. human 側 FP: quality:high human を AI と誤判定する率。
   FP<5% に閾値を合わせたときの AI 検出率(recall)も報告。

出力: このディレクトリ直下に report.md (Markdown) として保存 (gitignore 対象)。
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler

SCRIPT_DIR = Path(__file__).resolve().parent
CACHE_DIR = SCRIPT_DIR / "cache"


def load_cache():
    npz = np.load(CACHE_DIR / "embeddings.npz")
    vectors = npz["vectors"]
    meta = json.loads((CACHE_DIR / "meta.json").read_text(encoding="utf-8"))
    assert len(meta) == vectors.shape[0]
    return vectors, meta


def make_labels(meta):
    # label 1 = AI, 0 = human
    return np.array([1 if m["group"] == "ai" else 0 for m in meta])


def fit_predict(X_train, y_train, X_test):
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X_train)
    Xt = scaler.transform(X_test)
    clf = LogisticRegression(max_iter=2000, C=1.0, class_weight="balanced")
    clf.fit(Xs, y_train)
    proba = clf.predict_proba(Xt)[:, 1]
    return proba


def random_split_cv(X, y, n_splits=5, seed=42):
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    aucs, accs = [], []
    for train_idx, test_idx in skf.split(X, y):
        proba = fit_predict(X[train_idx], y[train_idx], X[test_idx])
        y_test = y[test_idx]
        aucs.append(roc_auc_score(y_test, proba))
        preds = (proba >= 0.5).astype(int)
        accs.append((preds == y_test).mean())
    return dict(auc_mean=float(np.mean(aucs)), auc_std=float(np.std(aucs)),
                acc_mean=float(np.mean(accs)), acc_std=float(np.std(accs)),
                folds=n_splits)


def leave_one_model_out(X, y, meta, seed=42):
    """AI 7モデルのうち6で学習→残り1で評価、7通り全部。

    human 側は「モデルの入れ替え」とは無関係の分布シフト軸なので、doc単位のリーク
    (同じ human 文書が train/test 両方に入る)を避けるため、human は固定の
    80/20 split をあらかじめ切り、test 側の human だけを全 fold で評価に使う
    (train 側の human はどの fold でも学習に使う)。
    """
    ai_models = sorted({m["model_or_source"] for m in meta if m["group"] == "ai"})
    model_or_source = np.array([m["model_or_source"] for m in meta])
    group = np.array([m["group"] for m in meta])

    human_idx = np.where(group == "human")[0]
    rng = np.random.RandomState(seed)
    shuffled = human_idx.copy()
    rng.shuffle(shuffled)
    n_test_human = max(1, int(len(shuffled) * 0.2))
    human_test_idx = set(shuffled[:n_test_human].tolist())
    human_train_idx = set(shuffled[n_test_human:].tolist())

    results = {}
    for held_out in ai_models:
        ai_test_mask = (group == "ai") & (model_or_source == held_out)
        ai_train_mask = (group == "ai") & (model_or_source != held_out)

        train_idx = np.array(sorted(human_train_idx) + np.where(ai_train_mask)[0].tolist())
        test_idx = np.array(sorted(human_test_idx) + np.where(ai_test_mask)[0].tolist())

        proba = fit_predict(X[train_idx], y[train_idx], X[test_idx])
        y_test = y[test_idx]
        auc = roc_auc_score(y_test, proba) if len(set(y_test.tolist())) > 1 else float("nan")
        ai_recall_at_50 = float((proba[y_test == 1] >= 0.5).mean())
        human_fp_at_50 = float((proba[y_test == 0] >= 0.5).mean())
        results[held_out] = dict(auc=float(auc), ai_recall_at_50=ai_recall_at_50,
                                  human_fp_at_50=human_fp_at_50,
                                  n_ai_test=int((y_test == 1).sum()), n_human_test=int((y_test == 0).sum()))
    return results


def leave_one_genre_out(X, y, meta):
    genres = sorted({m["genre"] for m in meta if m.get("genre")})
    results = {}
    genre_arr = np.array([m.get("genre") for m in meta])
    for g in genres:
        test_mask = genre_arr == g
        train_mask = ~test_mask
        test_idx = np.where(test_mask)[0]
        train_idx = np.where(train_mask)[0]
        y_test = y[test_idx]
        if len(set(y_test.tolist())) < 2:
            continue
        proba = fit_predict(X[train_idx], y[train_idx], X[test_idx])
        auc = roc_auc_score(y_test, proba)
        ai_recall_at_50 = float((proba[y_test == 1] >= 0.5).mean())
        human_fp_at_50 = float((proba[y_test == 0] >= 0.5).mean())
        results[g] = dict(auc=float(auc), ai_recall_at_50=ai_recall_at_50,
                           human_fp_at_50=human_fp_at_50,
                           n_ai_test=int((y_test == 1).sum()), n_human_test=int((y_test == 0).sum()))
    return results


def fp_threshold_sweep(X, y, meta, n_splits=5, seed=42):
    """5-fold CV の out-of-fold 予測確率を使い、human quality:high の FP率 <5% を
    満たす閾値でのAI検出率を求める(readability-sweep.py と同じ判定規律)。
    """
    quality = np.array([m.get("quality") for m in meta])
    is_human_high = (np.array([m["group"] for m in meta]) == "human") & (quality == "high")
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    oof_proba = np.zeros(len(y))
    for train_idx, test_idx in skf.split(X, y):
        oof_proba[test_idx] = fit_predict(X[train_idx], y[train_idx], X[test_idx])

    human_high_scores = oof_proba[is_human_high]
    ai_scores = oof_proba[y == 1]

    rows = []
    for thresh in np.arange(0.05, 1.0, 0.05):
        fp_rate = float((human_high_scores >= thresh).mean())
        ai_detect = float((ai_scores >= thresh).mean())
        rows.append(dict(threshold=round(float(thresh), 2), human_high_fp_rate=fp_rate, ai_detect_rate=ai_detect))

    # find threshold(s) achieving FP < 5%, report the one maximizing AI detection
    feasible = [r for r in rows if r["human_high_fp_rate"] < 0.05]
    best = max(feasible, key=lambda r: r["ai_detect_rate"]) if feasible else None
    return rows, best, int(is_human_high.sum()), int((y == 1).sum())


def main():
    X, meta = load_cache()
    y = make_labels(meta)
    print(f"n_docs={len(meta)} n_human={(y==0).sum()} n_ai={(y==1).sum()}")

    report = {}
    report["random_split_cv"] = random_split_cv(X, y)
    report["leave_one_model_out"] = leave_one_model_out(X, y, meta)
    report["leave_one_genre_out"] = leave_one_genre_out(X, y, meta)
    sweep_rows, best, n_human_high, n_ai = fp_threshold_sweep(X, y, meta)
    report["fp_threshold_sweep"] = sweep_rows
    report["fp_threshold_best"] = best
    report["n_human_quality_high"] = n_human_high
    report["n_ai_total"] = n_ai

    (SCRIPT_DIR / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
