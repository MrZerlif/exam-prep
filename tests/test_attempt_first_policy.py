import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AttemptFirstPolicyTests(unittest.TestCase):
    def test_tutor_policy_contains_premature_answer_pressure_cases(self):
        skill = (ROOT / "skill" / "exam-prep" / "SKILL.md").read_text(encoding="utf-8").casefold()
        pedagogy = (ROOT / "skill" / "exam-prep" / "references" / "pedagogy.md").read_text(encoding="utf-8").casefold()
        combined = skill + "\n" + pedagogy
        for phrase in ("premature answer", "full solution", "attempt-first", "pressure"):
            self.assertIn(phrase, combined)
        self.assertIn("python engine cannot prevent", combined)


if __name__ == "__main__":
    unittest.main()
