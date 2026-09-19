import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.scheduler import compute_priority
from exam_prep_lib.schema_validation import SchemaError, load_schema, validate_document


NOW = datetime(2026, 9, 19, tzinfo=timezone.utc)


def state(**extra):
    return {"mastery": {"conceptual": 0.2, "procedural": 0.2, "recall": 0.2, "transfer": 0.2}, **extra}


class SchedulerModeTests(unittest.TestCase):
    def test_emergency_boosts_exam_value_and_recurring_mistakes(self):
        syllabus = {"schema_version": 2, "learning_targets": [
            {"target_id": "high", "importance": 1.0, "frequency": 1.0, "expected_points": 5, "prerequisites": []},
            {"target_id": "low", "importance": 0.2, "frequency": 0.2, "expected_points": 1, "prerequisites": []},
        ]}
        course = {"exam": {"date": (NOW + timedelta(hours=12)).isoformat()}, "scheduler": {"mode": "emergency"}}
        high = compute_priority("high", syllabus, {"high": state(recurring_mistakes=[{"tag": "sign", "recurring": True}])}, {}, course, NOW, 25)
        low = compute_priority("low", syllabus, {"low": state()}, {}, course, NOW, 25)
        self.assertGreater(high["score"], low["score"])
        self.assertEqual("emergency", high["computed_for"]["effective_mode"])

    def test_accelerated_auto_escalates_but_normal_does_not(self):
        syllabus = {"schema_version": 2, "learning_targets": [{"target_id": "t", "prerequisites": []}]}
        short = {"exam": {"date": (NOW + timedelta(hours=12)).isoformat()}, "scheduler": {"mode": "accelerated"}}
        normal = {"exam": {"date": (NOW + timedelta(hours=12)).isoformat()}, "scheduler": {"mode": "normal"}}
        self.assertEqual("emergency", compute_priority("t", syllabus, {"t": state()}, {}, short, NOW, 25)["computed_for"]["effective_mode"])
        self.assertEqual("normal", compute_priority("t", syllabus, {"t": state()}, {}, normal, NOW, 25)["computed_for"]["effective_mode"])

    def test_unknown_mode_is_rejected_by_course_schema(self):
        course = {"schema_version": 2, "course_id": "c", "title": "C", "exam": {"date": None}, "time_budget": {}, "source_policy": {}, "scheduler": {"mode": "turbo"}}
        with self.assertRaises(SchemaError):
            validate_document(course, load_schema("course.schema.json"))


if __name__ == "__main__":
    unittest.main()
