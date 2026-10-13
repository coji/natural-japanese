"""lint の誤検出の回帰テスト(2026-10 の修正)。生成AI以前の人間の文書で多く出ていた誤検出の型を、短い例で固定する。

    uv run --with sudachipy --with sudachidict-core python dev/test_lint_precision.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/natural-japanese/scripts"))

from lint import run_lint, run_reading_load  # noqa: E402
from textcore import mask_markdown_structure  # noqa: E402


def cats(text, reading_load=False):
    findings, _ = run_reading_load(text) if reading_load else run_lint(text)
    return [f.category for f in findings]


class MaskTests(unittest.TestCase):
    def test_image_url_html_and_non_japanese_lines_are_masked(self):
        text = "\n".join([
            "![image.png](https://example.com/a.png)",
            "https://example.com/path/to/page",
            "<details><summary>設定の例</summary>",
            "This is an English quotation that is not Japanese prose.",
            "本文は残る。",
        ])
        masked = mask_markdown_structure(text).split("\n")
        self.assertEqual(len(masked), 5)              # 行番号は保つ
        self.assertEqual(masked[0].strip(), "")
        self.assertEqual(masked[1].strip(), "")
        self.assertNotIn("<details>", masked[2])
        self.assertIn("設定の例", masked[2])          # タグの中の日本語は残す
        self.assertEqual(masked[3].strip(), "")
        self.assertEqual(masked[4], "本文は残る。")

    def test_link_text_is_kept(self):
        masked = mask_markdown_structure("詳しくは[公式の説明](https://example.com)を読む。")
        self.assertIn("公式の説明", masked)
        self.assertNotIn("example.com", masked)


class LeadRepetitionTests(unittest.TestCase):
    def test_image_lines_do_not_count_as_sentence_leads(self):
        text = "\n\n".join(f"![image.png](https://example.com/{i}.png)\n手順{i}の画面です。" for i in range(8))
        self.assertNotIn("repeated_sentence_lead", cats(text))

    def test_proper_noun_and_date_leads_are_not_counted(self):
        text = "".join(f"2019年{i}月に会議を開いた。" for i in range(1, 9))
        text += "".join(f"Amazonの機能{i}を使った。" for i in range(8))
        self.assertNotIn("repeated_sentence_lead", cats(text))

    def test_repeated_conjunction_lead_is_one_finding(self):
        text = "".join(f"また、項目{i}を確認した。" for i in range(8))
        self.assertEqual(cats(text).count("repeated_sentence_lead"), 1)


class ForbiddenPhraseTests(unittest.TestCase):
    def test_part_of_a_longer_word_is_not_matched(self):
        self.assertNotIn("forbidden_phrase", cats("クラスターエンドポイントは更新も参照もできる。"))
        self.assertNotIn("forbidden_phrase", cats("日英包括的経済連携協定が発効した。"))

    def test_standalone_phrase_is_matched_every_time(self):
        found = cats("ポイントは二つある。もう一つのポイントは速さだ。")
        self.assertEqual(found.count("forbidden_phrase"), 2)


class KotoGaDekiruTests(unittest.TestCase):
    def test_suru_koto_ga_dekiru_is_reading_load_not_ai_smell(self):
        text = "設定を変更することができる。"
        self.assertNotIn("translationese", cats(text))
        self.assertNotIn("translationese_morph", cats(text))
        self.assertIn("translationese_morph", cats(text, reading_load=True))


if __name__ == "__main__":
    unittest.main()
