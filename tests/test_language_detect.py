import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.language_detect import detect


class LanguageDetectTests(unittest.TestCase):
    def test_stopwords_and_script_identify_representative_languages(self):
        cases = {
            "en": "The limit and the derivative are defined in this chapter.",
            "de": "Die Aufgabe und der Beweis sind in diesem Kapitel.",
            "ru": "Задача и решение находятся в этой главе.",
            "zh": "题目定义极限并证明定理。",
            "ja": "問題を定義して証明します。",
        }
        for expected, text in cases.items():
            with self.subTest(language=expected):
                result = detect(text, candidates=("de", "en", "ja", "ru", "zh"))
                self.assertIsNotNone(result)
                self.assertEqual(expected, result[0])
                self.assertGreaterEqual(result[1], 0.6)

    def test_low_confidence_returns_none(self):
        self.assertIsNone(detect("qzxv nmb", candidates=("de", "en", "fr")))


if __name__ == "__main__":
    unittest.main()
