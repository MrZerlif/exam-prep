import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.text_normalize import canonical_key, keys, loose_key


class TextNormalizeTests(unittest.TestCase):
    def test_canonical_key_keeps_diacritic_distinctions(self):
        self.assertNotEqual(canonical_key("Зачёт"), canonical_key("ЗАЧЕТ"))
        self.assertEqual(canonical_key("  Foo--bar  "), "foo bar")

    def test_loose_key_folds_latin_and_cyrillic_marks(self):
        self.assertEqual(loose_key("Зачёт"), loose_key("ЗАЧЕТ"))
        self.assertEqual(loose_key("Prüfung"), loose_key("PRUFUNG"))
        self.assertEqual(loose_key("Straße"), loose_key("STRASSE"))
        self.assertEqual(loose_key("ё"), loose_key("е"))

    def test_turkish_fold_is_applied_before_mark_stripping(self):
        fold = {"ı": "i", "İ": "i"}
        self.assertEqual(loose_key("Sınav", fold), loose_key("SINAV", fold))
        self.assertNotEqual(loose_key("Sınav"), loose_key("SINAV"))

    def test_greek_and_vietnamese_marks_are_preserved(self):
        self.assertNotEqual(loose_key("ορισμός"), loose_key("ορισμος"))
        self.assertEqual(loose_key("tiếng Việt"), canonical_key("tiếng Việt"))

    def test_empty_values_and_keys_are_safe(self):
        self.assertEqual("", canonical_key("   "))
        self.assertEqual("", loose_key(""))
        self.assertEqual(("foo", "foo"), keys(" Foo "))

    def test_keys_are_idempotent_for_a_fixed_alphabet(self):
        random.seed(20260920)
        alphabet = "abcXYZ  -ёЁüßЗачетορισμός"
        for _ in range(300):
            value = "".join(random.choice(alphabet) for _ in range(random.randrange(30)))
            self.assertEqual(canonical_key(value), canonical_key(canonical_key(value)))
            self.assertEqual(loose_key(value), loose_key(loose_key(value)))


if __name__ == "__main__":
    unittest.main()
