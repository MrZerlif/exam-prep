import sys
import unittest
from datetime import datetime, timedelta, timezone


sys.path.insert(0, "skill/math-study/scripts")

from math_study_lib.scheduler import (  # noqa: E402
    build_review_queue,
    compute_priority,
    select_next_activity,
)


NOW = datetime(2026, 9, 13, 15, 30, tzinfo=timezone.utc)

COURSE = {
    "schema_version": 1,
    "exam": {"date": "2026-09-20T09:00:00+00:00"},
    "scheduler": {"mode": "exam_cram", "max_review_interval_hours": 72},
}

SYLLABUS = {
    "concepts": {
        "chain_rule": {
            "title": "Chain rule",
            "prerequisites": ["derivative_rules"],
            "importance": 0.9,
            "frequency": 0.9,
            "expected_points": 10,
            "estimated_learning_minutes": 30,
        },
        "derivative_rules": {
            "title": "Derivative rules",
            "prerequisites": [],
            "importance": 0.5,
            "frequency": 0.4,
            "expected_points": 4,
            "estimated_learning_minutes": 120,
        },
    }
}


def concept(mastery, status="weak"):
    return {
        "mastery": mastery,
        "status": status,
        "evidence": {
            "independent_successes": 0,
            "hinted_successes": 0,
            "failures": 1,
            "solution_views": 0,
            "delayed_recall_successes": 0,
            "transfer_successes": 0,
            "exam_successes": 0,
        },
    }


def event(outcome, *, session_id="s1", task_type="independent_problem", independent=True):
    return {
        "observation_id": f"{session_id}-{outcome}-{task_type}",
        "concept_id": "chain_rule",
        "task_type": task_type,
        "outcome": outcome,
        "recorded_at": NOW.isoformat(),
        "session_id": session_id,
        "assistance": {
            "requested": not independent,
            "levels_revealed": [] if independent else ["H1"],
            "scaffold_types": [] if independent else ["direction"],
            "partial_transformation_shown": False,
            "full_solution_viewed": False,
        },
        "error_tags": [],
        "diagnostic_confidence": "high",
        "learner_self_confidence": "medium",
        "source_refs": [],
        "expected_seconds": 120,
        "elapsed_seconds": 100,
    }


class SchedulerTests(unittest.TestCase):
    def test_failures_shorten_review_interval(self):
        queue = build_review_queue([event("incorrect")], {}, COURSE, NOW)
        self.assertLessEqual(queue["items"]["chain_rule"]["interval_hours"], 6)

    def test_independent_delayed_recall_gets_longer_interval(self):
        queue = build_review_queue(
            [event("correct", task_type="delayed_recall")], {}, COURSE, NOW
        )
        self.assertGreaterEqual(queue["items"]["chain_rule"]["interval_hours"], 24)

    def test_priority_changes_with_budget_context(self):
        concepts = {
            "chain_rule": concept(
                {"conceptual": 0.3, "procedural": 0.3, "recall": 0.3, "transfer": 0.2, "speed": 0.2}
            ),
            "derivative_rules": concept(
                {"conceptual": 0.3, "procedural": 0.3, "recall": 0.3, "transfer": 0.3, "speed": 0.3}
            ),
        }
        short = compute_priority(
            "chain_rule", SYLLABUS, concepts, {}, COURSE, NOW, 20
        )
        long = compute_priority(
            "chain_rule", SYLLABUS, concepts, {}, COURSE, NOW, 90
        )
        self.assertEqual(short["computed_for"]["budget_minutes"], 20)
        self.assertEqual(long["computed_for"]["budget_minutes"], 90)
        self.assertNotEqual(short["score"], long["score"])

    def test_due_weak_topic_is_selected_and_prerequisite_is_reported(self):
        concepts = {
            "chain_rule": concept(
                {"conceptual": 0.2, "procedural": 0.2, "recall": 0.2, "transfer": 0.1, "speed": 0.1}
            ),
            "derivative_rules": concept(
                {"conceptual": 0.9, "procedural": 0.9, "recall": 0.9, "transfer": 0.8, "speed": 0.8},
                status="mastered",
            ),
        }
        result = select_next_activity(SYLLABUS, concepts, {"chain_rule": {"due_at": NOW.isoformat()}}, COURSE, NOW, 25)
        self.assertEqual(result["concept_id"], "chain_rule")
        self.assertIn("prerequisite", result["reason"])

    def test_interleaving_avoids_repeating_recent_concept_when_possible(self):
        concepts = {
            "chain_rule": concept({"conceptual": 0.2, "procedural": 0.2, "recall": 0.2, "transfer": 0.1, "speed": 0.1}),
            "derivative_rules": concept({"conceptual": 0.4, "procedural": 0.4, "recall": 0.4, "transfer": 0.3, "speed": 0.3}),
        }
        result = select_next_activity(
            SYLLABUS, concepts, {}, COURSE, NOW, 25, recent_concept_ids=["chain_rule"]
        )
        self.assertEqual(result["concept_id"], "derivative_rules")


if __name__ == "__main__":
    unittest.main()
