import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("reader_app", HERE / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


def fake_stimuli():
    return [{
        "id": f"item-{i:02}", "genre": "test",
        "variants": {condition: f"{condition}-{i}" for condition in app.CONDITIONS},
        "question": {"prompt": "正しいものは？", "choices": ["A", "B", "C"], "answer": 0},
    } for i in range(12)]


class ReaderStudyTest(unittest.TestCase):
    def test_assignment_is_balanced_and_reproducible(self):
        stimuli = fake_stimuli()
        first = app.assignment("participant-0001", stimuli)
        second = app.assignment("participant-0001", stimuli)
        self.assertEqual(first, second)
        counts = {condition: 0 for condition in app.CONDITIONS}
        for item in first:
            counts[item["condition"]] += 1
        self.assertEqual(counts, {"uniform": 4, "varied": 4, "control": 4})
        self.assertEqual(len({item["id"] for item in first}), 12)

    def test_validation_rejects_wrong_assignment(self):
        stimuli = fake_stimuli()
        participant = "participant-0001"
        answers = [{
            "item_id": item["id"], "condition": item["condition"],
            "monotony": 4, "naturalness": 4, "readability": 4,
            "comprehension": 0, "elapsed_ms": 15000,
        } for item in app.assignment(participant, stimuli)]
        payload = {"participant_id": participant, "attention_check": 4, "answers": answers}
        self.assertEqual(app.validate_submission(payload, stimuli), (True, ""))
        answers[0]["condition"] = "wrong"
        self.assertFalse(app.validate_submission(payload, stimuli)[0])

    def test_saved_record_does_not_contain_ip(self):
        payload = {"participant_id": "participant-0001", "attention_check": 4, "answers": []}
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "responses.jsonl"
            with patch.object(app, "DATA_DIR", Path(directory)), patch.object(app, "RESPONSES", target):
                app.save_submission(payload, "192.0.2.1")
            record = json.loads(target.read_text())
            self.assertNotIn("ip", record)
            self.assertNotIn("192.0.2.1", target.read_text())

    def test_duplicate_participant_is_not_saved(self):
        payload = {"participant_id": "participant-0001", "attention_check": 4, "answers": []}
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "responses.jsonl"
            with patch.object(app, "DATA_DIR", Path(directory)), patch.object(app, "RESPONSES", target):
                self.assertTrue(app.save_submission(payload))
                self.assertFalse(app.save_submission(payload))
            self.assertEqual(len(target.read_text().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
