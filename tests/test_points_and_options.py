import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_adapters.local_materials.labels import option_run, option_run_quality
from exam_prep_adapters.local_materials.points import extract, infer_token, verify_total
from exam_prep_lib.lexicon import load


class PointsAndOptionsTests(unittest.TestCase):
    def test_declared_option_sequences_and_unknown_script(self):
        cases = (
            ("A) one\nB) two\nC) three", ("A", "B", "C")),
            ("А) one\nБ) two\nВ) three", ("А", "Б", "В")),
            ("Α) one\nΒ) two\nΓ) three", ("Α", "Β", "Γ")),
            ("I) one\nII) two\nIII) three", ("I", "II", "III")),
            ("1) one\n2) two\n3) three", ("1", "2", "3")),
            ("ア) one\nイ) two\nウ) three", ("ア", "イ", "ウ")),
            ("א) one\nב) two", ("א", "ב")),
        )
        for body, expected in cases:
            self.assertEqual(expected, option_run(body), body)
        self.assertEqual(0.5, option_run_quality("א) one\nב) two"))

    def test_single_option_and_nine_options_are_not_runs(self):
        self.assertEqual((), option_run("В) only"))
        body = "\n".join(f"{number}) option" for number in range(1, 10))
        self.assertEqual((), option_run(body))

    def test_inferred_points_are_verified_and_non_point_units_are_ignored(self):
        pages = (SimpleNamespace(text="\n".join(f"{number}) (10 points)" for number in range(1, 7))),)
        token = infer_token(pages, lexicon=load("en"))
        self.assertEqual("points", token)
        values = [extract("(10 points)", token=token, lexicon=load("en")) for _ in range(6)]
        self.assertEqual([10] * 6, values)
        self.assertTrue(verify_total(values, 60))
        self.assertIsNone(verify_total(values, None))
        self.assertIsNone(extract("(10 min)", token=None, lexicon=load("en")))
        self.assertIsNone(infer_token((SimpleNamespace(text="\n".join(f"{n}) (10 min)" for n in range(1, 6))),), lexicon=load("en")))


if __name__ == "__main__":
    unittest.main()
