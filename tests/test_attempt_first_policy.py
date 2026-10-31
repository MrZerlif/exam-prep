import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AttemptFirstPolicyTests(unittest.TestCase):
    def test_attempt_first_boundary_is_limited_to_mock_exam_mode(self):
        skill = (ROOT / "skill" / "exam-prep" / "SKILL.md").read_text(encoding="utf-8").casefold()
        pedagogy = (ROOT / "skill" / "exam-prep" / "references" / "pedagogy.md").read_text(encoding="utf-8").casefold()
        combined = skill + "\n" + pedagogy
        for phrase in ("full solution", "attempt-first", "pressure", "end-session --stopped"):
            self.assertIn(phrase, combined)
        self.assertIn("python engine cannot prevent", combined)
        self.assertIn("outside a mock, honor the learner's explicit request", pedagogy)
        for obsolete in (
            "only pre-attempt route to the solution",
            "preserve attempt-first outside the diagnostic exit",
            "ask for a start or brief answer structure first",
        ):
            self.assertNotIn(obsolete, combined)

    def test_explicit_solution_exposure_modes_are_observable_and_separate(self):
        pedagogy = (ROOT / "skill" / "exam-prep" / "references" / "pedagogy.md").read_text(
            encoding="utf-8"
        ).casefold()
        for phrase in (
            "teaching exposure",
            "cram exposure",
            "exam mode",
            "explicit request",
            "solution_seen",
            "optional",
            "skip it or stop",
        ):
            self.assertIn(phrase, pedagogy)


if __name__ == "__main__":
    unittest.main()
