# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "numpy>=2.0",
#   "pandas>=2.2",
#   "scipy>=1.13",
#   "scikit-learn>=1.5",
#   "statsmodels>=0.14.4",
#   "sudachipy>=0.6.8",
#   "sudachidict-core>=20240409",
# ]
# ///
"""事前登録どおりに回答を除外し、線形混合モデルの結果を保存する。"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import statistics
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.metrics import root_mean_squared_error
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
DEFAULT_INPUT = HERE / "data" / "responses.jsonl"
DEFAULT_OUTPUT = HERE / "results"


def load_stimuli() -> list[dict]:
    return json.loads((HERE / "stimuli.json").read_text(encoding="utf-8"))


def load_lint():
    scripts = ROOT / "skills" / "natural-japanese" / "scripts"
    sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location("reader_study_lint", scripts / "lint.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def rhythm_metrics(mod, text: str) -> dict[str, float]:
    lines = mod.iter_lines_with_no(text)
    sentences = mod.split_sentences_with_lines(lines, dict(lines))
    tokenized = mod.tokenize_sentences(sentences)
    lengths = [mod.mora_length(item.morphemes) for item in tokenized]
    mean = statistics.mean(lengths)
    diffs = [b - a for a, b in zip(lengths, lengths[1:])]
    lag1 = float(np.corrcoef(lengths[:-1], lengths[1:])[0, 1])
    return {
        "mora_cv": statistics.pstdev(lengths) / mean,
        "adjacent_abs_diff": statistics.mean(abs(x) for x in diffs),
        "rmssd": math.sqrt(statistics.mean(x * x for x in diffs)),
        "lag1_autocorrelation": lag1,
    }


def exclusion_reasons(record: dict, answer_key: dict[str, int]) -> list[str]:
    answers = record.get("answers", [])
    reasons = []
    if len(answers) != 12 or len({a.get("item_id") for a in answers}) != 12:
        reasons.append("incomplete")
        return reasons
    if record.get("attention_check") != 4:
        reasons.append("attention_check")
    correct = sum(a.get("comprehension") == answer_key.get(a.get("item_id")) for a in answers)
    if correct < 6:
        reasons.append("comprehension_below_6")
    elapsed = [a.get("elapsed_ms") for a in answers]
    if any(not isinstance(value, int) for value in elapsed):
        reasons.append("missing_elapsed_time")
    elif statistics.median(elapsed) < 10_000:
        reasons.append("median_time_below_10s")
    rating_fields = ("monotony", "naturalness", "readability")
    if all(len({a.get(field) for a in answers}) == 1 for field in rating_fields):
        reasons.append("straightlining_all_ratings")
    required = {"item_id", "condition", "monotony", "naturalness", "readability", "comprehension", "elapsed_ms"}
    if any(not required.issubset(a) for a in answers):
        reasons.append("technical_missing_value")
    return reasons


def read_records(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: JSONが不正です") from error
    return records


def build_long_data(records: list[dict], stimuli: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    answer_key = {item["id"]: item["question"]["answer"] for item in stimuli}
    item_map = {item["id"]: item for item in stimuli}
    mod = load_lint()
    metric_map = {
        (item["id"], condition): rhythm_metrics(mod, text)
        for item in stimuli for condition, text in item["variants"].items()
    }
    audits, rows, seen = [], [], set()
    for record in records:
        participant = record.get("participant_id", "")
        reasons = exclusion_reasons(record, answer_key)
        if participant in seen:
            reasons.append("duplicate_participant")
        seen.add(participant)
        audits.append({"participant_id": participant, "included": not reasons, "reasons": ";".join(reasons)})
        if reasons:
            continue
        for answer in record["answers"]:
            item = item_map[answer["item_id"]]
            rows.append({
                "participant_id": participant,
                "item_id": answer["item_id"],
                "genre": item["genre"],
                **answer,
                "comprehension_correct": int(answer["comprehension"] == answer_key[answer["item_id"]]),
                **metric_map[(answer["item_id"], answer["condition"])],
            })
    return pd.DataFrame(rows), pd.DataFrame(audits)


def fit_rating(data: pd.DataFrame, outcome: str) -> dict:
    model = smf.mixedlm(
        f"{outcome} ~ C(condition, Treatment(reference='varied'))",
        data,
        groups=np.ones(len(data)),
        vc_formula={
            "participant": "0 + C(participant_id)",
            "item": "0 + C(item_id)",
        },
        re_formula="0",
    ).fit(reml=False, method=["lbfgs", "powell", "cg"])
    term = "C(condition, Treatment(reference='varied'))[T.uniform]"
    estimate = float(model.params[term])
    se = float(model.bse[term])
    return {
        "outcome": outcome,
        "model": "linear mixed model; random intercepts for participant and item",
        "uniform_minus_varied": estimate,
        "standard_error": se,
        "ci95_low": estimate - 1.96 * se,
        "ci95_high": estimate + 1.96 * se,
        "p_value": float(model.pvalues[term]),
        "converged": bool(model.converged),
        "aic": float(model.aic),
    }


def fit_metric(data: pd.DataFrame, outcome: str, metric: str) -> dict:
    frame = data.copy()
    frame["metric_z"] = (frame[metric] - frame[metric].mean()) / frame[metric].std()
    model = smf.mixedlm(
        f"{outcome} ~ metric_z",
        frame,
        groups=np.ones(len(frame)),
        vc_formula={"participant": "0 + C(participant_id)", "item": "0 + C(item_id)"},
        re_formula="0",
    ).fit(reml=False, method=["lbfgs", "powell", "cg"])
    estimate, se = float(model.params["metric_z"]), float(model.bse["metric_z"])
    return {
        "outcome": outcome,
        "metric": metric,
        "estimate_per_sd": estimate,
        "standard_error": se,
        "ci95_low": estimate - 1.96 * se,
        "ci95_high": estimate + 1.96 * se,
        "p_value": float(model.pvalues["metric_z"]),
        "aic": float(model.aic),
        "converged": bool(model.converged),
    }


def cross_validated_metrics(data: pd.DataFrame, outcome: str, metrics: tuple[str, ...]) -> list[dict]:
    participants = data["participant_id"].nunique()
    folds = min(10, participants)
    splitter = GroupKFold(n_splits=folds)
    rows = []
    for metric in metrics:
        errors = []
        features = data[["participant_id", "item_id", metric]]
        for train, test in splitter.split(features, data[outcome], groups=data["participant_id"]):
            transform = ColumnTransformer([
                ("ids", OneHotEncoder(handle_unknown="ignore"), ["participant_id", "item_id"]),
                ("metric", StandardScaler(), [metric]),
            ])
            model = make_pipeline(transform, Ridge(alpha=1.0))
            model.fit(features.iloc[train], data[outcome].iloc[train])
            prediction = model.predict(features.iloc[test])
            errors.append(root_mean_squared_error(data[outcome].iloc[test], prediction))
        rows.append({"outcome": outcome, "metric": metric, "grouped_cv_folds": folds, "rmse": float(np.mean(errors))})
    return rows


def fit_comprehension(data: pd.DataFrame) -> dict:
    if data["comprehension_correct"].nunique() < 2:
        value = int(data["comprehension_correct"].iloc[0])
        return {
            "outcome": "comprehension_correct",
            "model": "not estimable: outcome has no variation",
            "uniform_minus_varied_log_odds": None,
            "posterior_sd": None,
            "credible95_low": None,
            "credible95_high": None,
            "observed_value": value,
        }
    model = BinomialBayesMixedGLM.from_formula(
        "comprehension_correct ~ C(condition, Treatment(reference='varied'))",
        {"participant": "0 + C(participant_id)", "item": "0 + C(item_id)"},
        data,
    ).fit_vb()
    names = model.model.exog_names
    term = "C(condition, Treatment(reference='varied'))[T.uniform]"
    index = names.index(term)
    estimate, sd = float(model.fe_mean[index]), float(model.fe_sd[index])
    return {
        "outcome": "comprehension_correct",
        "model": "Bayesian logistic mixed model; random intercepts for participant and item",
        "uniform_minus_varied_log_odds": estimate,
        "posterior_sd": sd,
        "credible95_low": estimate - 1.96 * sd,
        "credible95_high": estimate + 1.96 * sd,
    }


def write_report(results: list[dict], metric_results: list[dict], cv_results: list[dict], comprehension: dict,
                 audit: pd.DataFrame, data: pd.DataFrame, output: Path) -> None:
    total = len(audit)
    included = int(audit["included"].sum()) if total else 0
    lines = [
        "# 読者実験の解析結果", "",
        f"- 総回答者: {total}人", f"- 有効回答者: {included}人", f"- 除外: {total - included}人", "",
        "## 評定の混合モデル", "",
        "| 評価 | uniform − varied | 95% CI | p | 収束 |", "|---|---:|---:|---:|---:|",
    ]
    for row in results:
        lines.append(f"| {row['outcome']} | {row['uniform_minus_varied']:.3f} | {row['ci95_low']:.3f}–{row['ci95_high']:.3f} | {row['p_value']:.4f} | {row['converged']} |")
    lines += ["", "主要評価は monotony。正の値は uniform のほうが単調と評定されたことを示す。", "",
              "## 理解度", "",
              (f"uniform − varied のlog odds: {comprehension['uniform_minus_varied_log_odds']:.3f} "
               f"（95%信用区間 {comprehension['credible95_low']:.3f}–{comprehension['credible95_high']:.3f}）"
               if comprehension["uniform_minus_varied_log_odds"] is not None
               else f"モデル推定不能: 理解度が全件 {comprehension['observed_value']} で変動がない。"), "",
              "## リズム指標", "", "| 評価 | 指標 | 1 SDあたり係数 | p | AIC | CV RMSE |", "|---|---|---:|---:|---:|---:|"]
    cv_map = {(row["outcome"], row["metric"]): row["rmse"] for row in cv_results}
    for row in metric_results:
        lines.append(f"| {row['outcome']} | {row['metric']} | {row['estimate_per_sd']:.3f} | {row['p_value']:.4f} | {row['aic']:.1f} | {cv_map[(row['outcome'], row['metric'])]:.3f} |")
    lines.append("")
    (output / "results.md").write_text("\n".join(lines), encoding="utf-8")
    payload = {"condition_models": results, "metric_models": metric_results,
               "cross_validation": cv_results, "comprehension_model": comprehension}
    (output / "model-results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    audit.to_csv(output / "exclusions.csv", index=False)
    data.to_csv(output / "responses-long.csv", index=False)

    primary = next(row for row in results if row["outcome"] == "monotony")
    best = min((row for row in cv_results if row["outcome"] == "monotony"), key=lambda row: row["rmse"])
    metric_model = next(row for row in metric_results if row["outcome"] == "monotony" and row["metric"] == best["metric"])
    supported = primary["uniform_minus_varied"] > 0 and primary["p_value"] < 0.05
    metric_supported = metric_model["p_value"] < 0.05
    decision = ["# リズム検出器の実装判断", "",
                f"- 主要仮説: {'支持' if supported else '不支持'}",
                f"- 主要対比 uniform − varied: {primary['uniform_minus_varied']:.3f} "
                f"（95% CI {primary['ci95_low']:.3f}–{primary['ci95_high']:.3f}, p={primary['p_value']:.4f}）",
                f"- 単調さを最もよく予測した指標: {best['metric']}（CV RMSE={best['rmse']:.3f}, p={metric_model['p_value']:.4f}）", ""]
    if supported and metric_supported:
        decision += [f"判断: `{best['metric']}` を単調さの疑いの根拠として残し、他のリズム指標は削除または探索扱いにする。"]
    else:
        decision += ["判断: 文長系列指標を単調さ・自然さの価値判断には使わない。既存のリズム警告から価値判断を外す。"]
    decision += ["", "このファイルは解析結果から自動生成された判断案である。実装変更時に、効果量、区間、逸脱、パイロット所見も確認する。", ""]
    (output / "implementation-decision.md").write_text("\n".join(decision), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="刺激と解析コードのロードだけ確認する")
    args = parser.parse_args()
    stimuli = load_stimuli()
    if args.check:
        assert len(stimuli) == 12
        load_lint()
        print("OK: 解析環境と刺激12件を読み込めました")
        return
    records = read_records(args.input)
    data, audit = build_long_data(records, stimuli)
    if audit.empty or int(audit["included"].sum()) < 2:
        raise SystemExit("解析には有効回答が2人以上必要です")
    args.output.mkdir(parents=True, exist_ok=True)
    outcomes = ("monotony", "naturalness", "readability")
    metrics = ("mora_cv", "adjacent_abs_diff", "rmssd", "lag1_autocorrelation")
    results = [fit_rating(data, outcome) for outcome in outcomes]
    metric_results = [fit_metric(data, outcome, metric) for outcome in outcomes for metric in metrics]
    cv_results = [row for outcome in outcomes for row in cross_validated_metrics(data, outcome, metrics)]
    comprehension = fit_comprehension(data)
    write_report(results, metric_results, cv_results, comprehension, audit, data, args.output)
    print(f"{args.output / 'results.md'} を作成しました")


if __name__ == "__main__":
    main()
