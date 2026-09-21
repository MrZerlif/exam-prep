import sys
import unittest
from datetime import datetime, timedelta, timezone


sys.path.insert(0, "skill/exam-prep/scripts")

from exam_prep_lib.scheduler import (  # noqa: E402
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


def concept(mastery, status="weak", independent_successes=0, hinted_successes=0):
    return {
        "mastery": mastery,
        "status": status,
        "evidence": {
            "independent_successes": independent_successes,
            "hinted_successes": hinted_successes,
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
        self.assertEqual(
            "delayed_recall", queue["items"]["chain_rule"]["review_kind"]
        )

    def test_v2_capability_review_kind_overrides_generic_task_type(self):
        syllabus = {
            "schema_version": 2,
            "learning_targets": [
                {
                    "target_id": "argument",
                    "prerequisites": [],
                    "capability_ids": ["oral_argument"],
                }
            ],
            "assessment_capabilities": {
                "oral_argument": {
                    "affected_dimensions": ["conceptual"],
                    "review_kind": "oral_answer",
                }
            },
        }
        v2_event = {
            **event("correct", task_type="open_activity"),
            "schema_version": 2,
            "target_id": "argument",
            "capability_id": "oral_argument",
            "task_type": "open_activity",
        }
        queue = build_review_queue([v2_event], {}, COURSE, NOW, syllabus)
        self.assertEqual("oral_answer", queue["items"]["argument"]["review_kind"])

    def test_unknown_v2_capability_uses_safe_unmapped_review_kind(self):
        syllabus = {
            "schema_version": 2,
            "learning_targets": [{"target_id": "argument", "prerequisites": []}],
        }
        v2_event = {
            **event("correct", task_type="transfer"),
            "schema_version": 2,
            "target_id": "argument",
            "capability_id": "provider:future-orals",
            "task_type": "transfer",
        }
        queue = build_review_queue([v2_event], {}, COURSE, NOW, syllabus)
        self.assertEqual(
            "unmapped_assessment", queue["items"]["argument"]["review_kind"]
        )

    def test_priority_uses_configured_exam_timezone_for_naive_dates(self):
        course = dict(COURSE)
        course["exam"] = {"date": "2026-09-20T09:00:00", "timezone": "+03:00"}
        result = compute_priority(
            "chain_rule", SYLLABUS, {"chain_rule": concept({})}, {}, course, NOW, 25
        )
        self.assertIn("score", result)
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

    def test_question_model_blueprint_flips_priority_order(self):
        # 1.2: ticket_list raises recall / lowers transfer weight, problem_set
        # is the mirror image. Two targets, otherwise identical, weak in
        # opposite dimensions - the blueprint alone must decide which one
        # `next` picks, in both directions, not just move the score a bit.
        blueprint_syllabus = {
            "schema_version": 2,
            "learning_targets": [
                {
                    "target_id": "recall_weak",
                    "title": "Recall-weak topic",
                    "prerequisites": [],
                    "importance": 0.6,
                    "frequency": 0.6,
                    "expected_points": 5,
                    "estimated_learning_minutes": 30,
                    # delayed_transfer (not delayed_recall): needs both
                    # recall and transfer required so the blueprint weights
                    # actually have two dimensions to trade off between
                    # (delayed_recall is recall-only since 2.2).
                    "capability_ids": ["delayed_transfer"],
                },
                {
                    "target_id": "transfer_weak",
                    "title": "Transfer-weak topic",
                    "prerequisites": [],
                    "importance": 0.6,
                    "frequency": 0.6,
                    "expected_points": 5,
                    "estimated_learning_minutes": 30,
                    "capability_ids": ["delayed_transfer"],
                },
            ],
        }
        concepts = {
            "recall_weak": concept(
                {"conceptual": 0.6, "procedural": 0.6, "recall": 0.1, "transfer": 0.7, "speed": None}
            ),
            "transfer_weak": concept(
                {"conceptual": 0.6, "procedural": 0.6, "recall": 0.7, "transfer": 0.1, "speed": None}
            ),
        }
        ticket_list_course = {**COURSE, "exam": {**COURSE["exam"], "question_model": "ticket_list"}}
        problem_set_course = {**COURSE, "exam": {**COURSE["exam"], "question_model": "problem_set"}}

        ticket_list_pick = select_next_activity(
            blueprint_syllabus, concepts, {}, ticket_list_course, NOW, 25
        )
        problem_set_pick = select_next_activity(
            blueprint_syllabus, concepts, {}, problem_set_course, NOW, 25
        )

        self.assertEqual("recall_weak", ticket_list_pick["concept_id"])
        self.assertEqual("transfer_weak", problem_set_pick["concept_id"])

    def test_oral_delivery_does_not_require_speed(self):
        # speed is never measured by the CLI (record-observation always
        # passes expected/elapsed_seconds=None), so mastery["speed"] is
        # always None and _mastery_gap drops it before any weight could
        # apply - requiring it would be inert. Confirms that dead mechanism
        # is gone rather than silently doing nothing.
        syllabus = {
            "schema_version": 2,
            "learning_targets": [
                {
                    "target_id": "argument",
                    "prerequisites": [],
                    "capability_ids": ["explanation"],
                }
            ],
        }
        course = {**COURSE, "exam": {**COURSE["exam"], "delivery": "oral"}}
        result = compute_priority(
            "argument", syllabus, {"argument": concept({"conceptual": 0.5})}, {}, course, NOW, 25
        )
        self.assertNotIn("speed", result["required_mastery_dimensions"])

    def test_oral_delivery_boosts_recall_weight_in_the_mastery_gap(self):
        syllabus = {
            "schema_version": 2,
            "learning_targets": [
                {
                    "target_id": "ticket",
                    "prerequisites": [],
                    # delayed_transfer: needs both recall and transfer
                    # required for the weighting to move the blended gap at
                    # all (a single required dimension is a no-op for
                    # weighting - see _mastery_gap).
                    "capability_ids": ["delayed_transfer"],
                }
            ],
        }
        concepts = {
            "ticket": concept(
                {"conceptual": 0.6, "procedural": 0.6, "recall": 0.1, "transfer": 0.9, "speed": None}
            )
        }
        written = compute_priority(
            "ticket", syllabus, concepts, {}, {**COURSE, "exam": {**COURSE["exam"], "delivery": "written"}}, NOW, 25
        )
        oral = compute_priority(
            "ticket", syllabus, concepts, {}, {**COURSE, "exam": {**COURSE["exam"], "delivery": "oral"}}, NOW, 25
        )
        # recall is the dominant weakness here (0.9 gap vs 0.1 for transfer);
        # weighting recall up must raise the blended gap versus the
        # unweighted written baseline.
        self.assertGreater(oral["mastery_gap"], written["mastery_gap"])

    def test_oral_independence_pressure_favors_hinted_heavy_evidence(self):
        syllabus = {
            "schema_version": 2,
            "learning_targets": [
                {"target_id": "independent_one", "prerequisites": [], "capability_ids": ["explanation"]},
                {"target_id": "hinted_one", "prerequisites": [], "capability_ids": ["explanation"]},
            ],
        }
        mastery = {"conceptual": 0.5, "procedural": 0.5, "recall": 0.5, "transfer": 0.5, "speed": None}
        concepts = {
            "independent_one": concept(dict(mastery), independent_successes=5, hinted_successes=0),
            "hinted_one": concept(dict(mastery), independent_successes=0, hinted_successes=5),
        }
        written_course = {**COURSE, "exam": {**COURSE["exam"], "delivery": "written"}}
        oral_course = {**COURSE, "exam": {**COURSE["exam"], "delivery": "oral"}}

        written_independent = compute_priority("independent_one", syllabus, concepts, {}, written_course, NOW, 25)
        written_hinted = compute_priority("hinted_one", syllabus, concepts, {}, written_course, NOW, 25)
        self.assertEqual(written_independent["score"], written_hinted["score"])

        oral_independent = compute_priority("independent_one", syllabus, concepts, {}, oral_course, NOW, 25)
        oral_hinted = compute_priority("hinted_one", syllabus, concepts, {}, oral_course, NOW, 25)
        self.assertGreater(oral_hinted["score"], oral_independent["score"])

    def test_interleaving_avoids_repeating_recent_concept_when_possible(self):
        concepts = {
            "chain_rule": concept({"conceptual": 0.2, "procedural": 0.2, "recall": 0.2, "transfer": 0.1, "speed": 0.1}),
            "derivative_rules": concept({"conceptual": 0.4, "procedural": 0.4, "recall": 0.4, "transfer": 0.3, "speed": 0.3}),
        }
        result = select_next_activity(
            SYLLABUS, concepts, {}, COURSE, NOW, 25, recent_concept_ids=["chain_rule"]
        )
        self.assertEqual(result["concept_id"], "derivative_rules")


    def test_prerequisite_blocked_target_never_wins_over_available_recent_target(self):
        concepts = {
            "chain_rule": {**concept({"conceptual": 0.1}), "availability": "prerequisite_blocked"},
            "derivative_rules": {**concept({"conceptual": 0.4}), "availability": "available"},
        }
        result = select_next_activity(
            SYLLABUS, concepts, {}, COURSE, NOW, 25,
            recent_concept_ids=["derivative_rules"],
        )
        self.assertEqual("derivative_rules", result["concept_id"])
        self.assertNotEqual("prerequisite_blocked", result.get("availability"))

    def test_all_prerequisite_blocked_targets_return_no_available_activity(self):
        concepts = {
            "chain_rule": {**concept({"conceptual": 0.1}), "availability": "prerequisite_blocked"},
            "derivative_rules": {**concept({"conceptual": 0.2}), "availability": "prerequisite_blocked"},
        }
        result = select_next_activity(SYLLABUS, concepts, {}, COURSE, NOW, 25)
        self.assertEqual(
            {
                "status": "no_available_activity",
                "activity_type": "no_available_activity",
                "score": 0.0,
                "reason": "all_targets_prerequisite_blocked",
            },
            result,
        )

    def test_interleaving_prefers_non_recent_available_target(self):
        concepts = {
            "chain_rule": {**concept({"conceptual": 0.2}), "availability": "available"},
            "derivative_rules": {**concept({"conceptual": 0.4}), "availability": "available"},
        }
        result = select_next_activity(
            SYLLABUS, concepts, {}, COURSE, NOW, 25,
            recent_concept_ids=["chain_rule"],
        )
        self.assertEqual("derivative_rules", result["concept_id"])
        self.assertNotEqual("prerequisite_blocked", result.get("availability"))
if __name__ == "__main__":
    unittest.main()
