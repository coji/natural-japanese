# /// script
# requires-python = ">=3.10"
# dependencies = ["sudachipy>=0.6.8", "sudachidict-core>=20240409"]
# ///
"""読者実験の刺激が事前登録の機械的要件を満たすか検査する。"""

from __future__ import annotations

import importlib.util
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
SCRIPTS = ROOT / "skills" / "natural-japanese" / "scripts"
CONDITIONS = {"uniform", "varied", "control"}


def load_lint():
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("stimulus_lint", SCRIPTS / "lint.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("scripts/lint.py をロードできない")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def metrics(mod, text: str) -> dict:
    lines = mod.iter_lines_with_no(text)
    sentences = mod.split_sentences_with_lines(lines, dict(lines))
    tokenized = mod.tokenize_sentences(sentences)
    mora = [mod.mora_length(item.morphemes) for item in tokenized]
    mean = statistics.mean(mora)
    sd = statistics.pstdev(mora)
    return {
        "characters": len(text),
        "sentences": len(mora),
        "mora_mean": mean,
        "mora_sd": sd,
        "mora_cv": sd / mean,
    }


def main() -> None:
    path = HERE / "stimuli.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    mod = load_lint()
    errors = []
    seen = set()
    rows = []
    if len(data) != 12:
        errors.append(f"刺激数は12件必要: {len(data)}件")
    for item in data:
        item_id = item.get("id")
        if not item_id or item_id in seen:
            errors.append(f"idが空または重複: {item_id}")
        seen.add(item_id)
        variants = item.get("variants", {})
        if set(variants) != CONDITIONS:
            errors.append(f"{item_id}: 条件が不正: {sorted(variants)}")
            continue
        if len(item.get("question", {}).get("choices", [])) != 3:
            errors.append(f"{item_id}: 理解問題の選択肢は3件必要")
        if item.get("question", {}).get("answer") not in {0, 1, 2}:
            errors.append(f"{item_id}: 正答indexが不正")
        measured = {condition: metrics(mod, text) for condition, text in variants.items()}
        lengths = [value["characters"] for value in measured.values()]
        if max(lengths) / min(lengths) > 1.10:
            errors.append(f"{item_id}: 条件間の総文字数差が10%超: {lengths}")
        for condition, value in measured.items():
            if not 8 <= value["sentences"] <= 12:
                errors.append(f"{item_id}/{condition}: 文数が8〜12外: {value['sentences']}")
            if not 210 <= value["characters"] <= 320:
                errors.append(f"{item_id}/{condition}: 文字数が210〜320外: {value['characters']}")
        gap = measured["varied"]["mora_cv"] - measured["uniform"]["mora_cv"]
        if gap < 0.20:
            errors.append(f"{item_id}: CV差が0.20未満: {gap:.3f}")
        rows.append({"id": item_id, **{f"{c}_cv": measured[c]["mora_cv"] for c in sorted(CONDITIONS)}, "cv_gap": gap})

    print("id\tuniform_cv\tvaried_cv\tcontrol_cv\tgap")
    for row in rows:
        print(f"{row['id']}\t{row['uniform_cv']:.3f}\t{row['varied_cv']:.3f}\t{row['control_cv']:.3f}\t{row['cv_gap']:.3f}")
    if errors:
        print("\nERRORS:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        raise SystemExit(1)
    print("\nOK: 12刺激すべてが機械的要件を満たした")


if __name__ == "__main__":
    main()
