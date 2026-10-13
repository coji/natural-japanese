"""UTF-8 input regression tests; no tokenizer dependencies required."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/natural-japanese/scripts"))

from outline import build_outline
from textcore import mask_markdown_structure, read_source_file


class SourceEncodingTests(unittest.TestCase):
    def test_bom_preserves_markdown_structure(self):
        samples = [
            "# Heading\n\nBody.\n",
            "---\ntitle: metadata\n---\n\n# Heading\n",
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "draft.md"
            for sample in samples:
                for encoding in ("utf-8", "utf-8-sig"):
                    with self.subTest(sample=sample, encoding=encoding):
                        path.write_bytes(sample.encode(encoding))
                        source, error = read_source_file(path)
                        self.assertIsNone(error)
                        self.assertEqual(build_outline(source), build_outline(sample))
                        self.assertEqual(mask_markdown_structure(source), mask_markdown_structure(sample))

    def test_internal_bom_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "draft.md"
            text = "Body\ufefftext.\n"
            path.write_bytes(text.encode("utf-8-sig"))
            self.assertEqual(read_source_file(path), (text, None))

    def test_invalid_utf8_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "draft.md"
            path.write_bytes(b"\xff")
            source, error = read_source_file(path)
            self.assertIsNone(source)
            self.assertIsNotNone(error)


if __name__ == "__main__":
    unittest.main()
