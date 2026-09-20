import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_adapters.local_materials.extractor import ExtractedPage, ExtractedSource
from exam_prep_adapters.local_materials.questions import extract_questions
from exam_prep_lib.lexicon import available


class LanguageFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = Path(__file__).parent / "fixtures" / "languages.json"
        cls.languages = json.loads(fixture.read_text(encoding="utf-8"))

    def test_all_supported_languages_have_working_question_fixture(self):
        expected = {"de", "fr", "es", "it", "pt", "pl", "tr", "uk", "zh", "ja"}
        self.assertTrue(expected.issubset(set(available())))
        self.assertEqual(expected, set(self.languages))
        for language, fixture in self.languages.items():
            with self.subTest(language=language):
                questions = ExtractedSource(
                    f"{language}.txt",
                    "homework",
                    (ExtractedPage(1, fixture["questions"]),),
                    "questions",
                    None,
                    None,
                )
                solutions = ExtractedSource(
                    f"{language}_solutions.txt",
                    "solution",
                    (ExtractedPage(1, fixture["solutions"]),),
                    "solutions",
                    None,
                    None,
                )
                result = extract_questions(
                    (questions, solutions),
                    language=language,
                    expected_total_points=None,
                )
                self.assertEqual(3, len(result))
                self.assertTrue(all(item.reference_answer for item in result[:2]))
                self.assertEqual(2, len(result[2].options))
                self.assertEqual(10, result[2].points)


if __name__ == "__main__":
    unittest.main()
