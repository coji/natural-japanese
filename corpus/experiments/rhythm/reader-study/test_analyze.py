# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "numpy>=2.0", "pandas>=2.2", "scipy>=1.13", "scikit-learn>=1.5",
#   "statsmodels>=0.14.4", "sudachipy>=0.6.8", "sudachidict-core>=20240409",
# ]
# ///
import importlib.util
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("reader_analysis", HERE / "analyze.py")
analysis = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = analysis
spec.loader.exec_module(analysis)


def record(**overrides):
    answers = [{
        "item_id": f"item-{index}", "condition": ("uniform", "varied", "control")[index % 3],
        "monotony": 3 + index % 2, "naturalness": 4 + index % 2, "readability": 5 + index % 2,
        "comprehension": 0, "elapsed_ms": 15_000,
    } for index in range(12)]
    value = {"participant_id": "participant-0001", "attention_check": 4, "answers": answers}
    value.update(overrides)
    return value


class AnalyzeTest(unittest.TestCase):
    def setUp(self):
        self.key = {f"item-{index}": 0 for index in range(12)}

    def test_valid_record_is_included(self):
        self.assertEqual(analysis.exclusion_reasons(record(), self.key), [])

    def test_preregistered_exclusions(self):
        value = record(attention_check=3)
        for answer in value["answers"]:
            answer.update(monotony=4, naturalness=4, readability=4, comprehension=1, elapsed_ms=5_000)
        self.assertEqual(set(analysis.exclusion_reasons(value, self.key)), {
            "attention_check", "comprehension_below_6", "median_time_below_10s",
            "straightlining_all_ratings",
        })

    def test_incomplete_record_stops_other_checks(self):
        value = record()
        value["answers"].pop()
        self.assertEqual(analysis.exclusion_reasons(value, self.key), ["incomplete"])


if __name__ == "__main__":
    unittest.main()
