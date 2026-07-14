# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "numpy>=2.0",
#   "pandas>=2.2",
#   "scipy>=1.13",
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
DEFAULT_INPUT = HERE / "data" / "responses.jsonl"
DEFAULT_OUTPUT = HERE / "results"


def load_stimuli() -> list[dict]:
    return json.loads((HERE / "stimuli.json").read_text(encoding="utf-8"))


def load_lint():
    scripts = ROOT / "scripts"
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
    }


def write_report(results: list[dict], audit: pd.DataFrame, data: pd.DataFrame, output: Path) -> None:
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
    lines += ["", "主要評価は monotony。正の値は uniform のほうが単調と評定されたことを示す。", ""]
    (output / "results.md").write_text("\n".join(lines), encoding="utf-8")
    (output / "model-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    audit.to_csv(output / "exclusions.csv", index=False)
    data.to_csv(output / "responses-long.csv", index=False)


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
    results = [fit_rating(data, outcome) for outcome in ("monotony", "naturalness", "readability")]
    write_report(results, audit, data, args.output)
    print(f"{args.output / 'results.md'} を作成しました")


if __name__ == "__main__":
    main()
