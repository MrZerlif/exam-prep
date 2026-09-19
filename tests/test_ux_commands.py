import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.planner import build_cheatsheet, forecast_plan, last_minute_review


NOW = datetime(2026, 9, 19, tzinfo=timezone.utc)
SYLLABUS = {"schema_version": 2, "learning_targets": [
    {"target_id": "weak", "title": "Weak", "importance": 1.0, "frequency": 1.0, "expected_points": 5, "prerequisites": []},
    {"target_id": "strong", "title": "Strong", "importance": 0.2, "frequency": 0.2, "expected_points": 1, "prerequisites": []},
]}
CONCEPTS = {"weak": {"mastery_status": "weak", "mastery": {"conceptual": 0.1}}, "strong": {"mastery_status": "mastered", "mastery": {"conceptual": 0.9}}}
COURSE = {"exam": {"date": (NOW + timedelta(hours=12)).isoformat()}, "scheduler": {"mode": "emergency"}}


class UxCommandTests(unittest.TestCase):
    def test_cheatsheet_only_repeats_evidence_excerpts(self):
        text = build_cheatsheet(SYLLABUS, CONCEPTS, {}, [{"source_ref": {"source_id": "s1", "locator": "p.1"}, "excerpt": "f(x)=x^2"}])
        self.assertIn("f(x)=x^2", text)
        self.assertNotIn("f(x)=x^3", text)

    def test_last_minute_review_prioritizes_weak_high_value_target(self):
        result = last_minute_review(SYLLABUS, CONCEPTS, {}, COURSE, NOW, 25)
        self.assertEqual("weak", result[0]["target_id"])

    def test_forecast_respects_daily_budget(self):
        result = forecast_plan(SYLLABUS, CONCEPTS, {}, COURSE, NOW, days=2, minutes_per_day=30)
        self.assertEqual(2, len(result["days"]))
        self.assertTrue(all(day["minutes"] <= 30 for day in result["days"]))


if __name__ == "__main__":
    unittest.main()
