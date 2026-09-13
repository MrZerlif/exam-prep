"""Regression test: `next`'s activity_type must reflect real pedagogical
state, not just "does a review-queue entry with a due_at exist" (every
concept gets one, including untouched ones, via the diagnostic fallback
entry in build_review_queue - so that alone can never mean "review")."""

import sys
import unittest
from datetime import datetime, timedelta, timezone


sys.path.insert(0, "skill/math-study/scripts")

from math_study_lib.reducer import reduce_learning_state  # noqa: E402
from math_study_lib.scheduler import build_review_queue, select_next_activity  # noqa: E402


NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
SYLLABUS = {
    "schema_version": 1,
    "concepts": {
        "functions": {
            "title": "Functions",
            "prerequisites": [],
            "importance": 0.9,
            "frequency": 0.9,
            "expected_points": 10,
            "estimated_learning_minutes": 20,
        },
    },
}
COURSE = {"schema_version": 1, "exam": {"date": None}, "scheduler": {"mode": "exam_cram"}}


class ActivityClassificationTests(unittest.TestCase):
    def test_unseen_concept_is_not_classified_as_review(self):
        concepts = reduce_learning_state(COURSE, SYLLABUS, [], {})["concepts"]
        reviews = build_review_queue([], concepts, COURSE, NOW, SYLLABUS)["items"]
        selected = select_next_activity(SYLLABUS, concepts, reviews, COURSE, NOW, 25)
        self.assertEqual(selected["concept_id"], "functions")
        self.assertNotEqual(selected["activity_type"], "review")

    def test_weak_concept_with_due_review_is_targeted_review_not_plain_review(self):
        event = {
            "schema_version": 1,
            "observation_id": "obs-1",
            "recorded_at": (NOW).isoformat(),
            "session_id": "s1",
            "concept_id": "functions",
            "task_id": "t1",
            "task_type": "independent_problem",
            "outcome": "incorrect",
            "assistance": {
                "requested": False,
                "levels_revealed": [],
                "scaffold_types": [],
                "partial_transformation_shown": False,
                "full_solution_viewed": False,
            },
            "error_tags": ["conceptual_error"],
            "diagnostic_confidence": "high",
            "source_refs": [],
            "expected_seconds": None,
            "elapsed_seconds": None,
        }
        concepts = reduce_learning_state(COURSE, SYLLABUS, [event], {})["concepts"]
        self.assertEqual(concepts["functions"]["mastery_status"], "weak")
        # Evaluate well after the computed review interval has elapsed, so
        # the item is actually due - not at the moment of the mistake itself
        # (which correctly schedules the review for later, not immediately).
        later = NOW + timedelta(hours=12)
        reviews = build_review_queue([event], concepts, COURSE, later, SYLLABUS)["items"]
        self.assertIn(reviews["functions"]["review_status"], ("due", "overdue"))
        selected = select_next_activity(SYLLABUS, concepts, reviews, COURSE, later, 25)
        self.assertIn(selected["activity_type"], ("targeted_review", "review"))
        self.assertNotEqual(selected["activity_type"], "new_learning")


if __name__ == "__main__":
    unittest.main()
