"""Regression tests for the mastery model remediation: speed evidence must
be nullable (absence != zero), status must not conflate independent axes,
and recurring mistakes need a real threshold plus resolution semantics."""

import sys
import unittest


sys.path.insert(0, "skill/exam-prep/scripts")

from exam_prep_lib.reducer import reduce_learning_state  # noqa: E402


SYLLABUS = {
    "schema_version": 1,
    "concepts": {
        "chain_rule": {
            "title": "Chain rule",
            "prerequisites": [],
            "importance": 0.9,
            "frequency": 0.8,
            "expected_points": 10,
            "estimated_learning_minutes": 30,
        },
    },
}
COURSE = {"schema_version": 1, "scheduler": {"mode": "exam_cram"}}


def event(
    *,
    observation_id,
    task_type="independent_problem",
    outcome="correct",
    error_tags=None,
    session_id="session-1",
):
    return {
        "schema_version": 1,
        "observation_id": observation_id,
        "recorded_at": "2026-09-13T15:30:00+00:00",
        "session_id": session_id,
        "concept_id": "chain_rule",
        "task_id": observation_id,
        "task_type": task_type,
        "outcome": outcome,
        "assistance": {
            "requested": False,
            "levels_revealed": [],
            "scaffold_types": [],
            "partial_transformation_shown": False,
            "full_solution_viewed": False,
        },
        "error_tags": error_tags or [],
        "diagnostic_confidence": "high",
        "learner_self_confidence": "medium",
        "source_refs": [],
        # No timing ever supplied by the CLI today - this is the normal case.
        "elapsed_seconds": None,
        "expected_seconds": None,
    }


class SpeedEvidenceTests(unittest.TestCase):
    def test_unseen_concept_has_unknown_not_zero_speed(self):
        result = reduce_learning_state(COURSE, SYLLABUS, [], {})
        self.assertIsNone(result["concepts"]["chain_rule"]["mastery"]["speed"])

    def test_speed_stays_unknown_without_timing_evidence(self):
        events = [
            event(observation_id=f"obs-{i}", task_type="transfer")
            for i in range(6)
        ]
        result = reduce_learning_state(COURSE, SYLLABUS, events, {})
        self.assertIsNone(result["concepts"]["chain_rule"]["mastery"]["speed"])

    def test_strong_evidence_without_speed_can_reach_mastered(self):
        events = []
        for i in range(8):
            events.append(event(observation_id=f"obs-ind-{i}", task_type="independent_problem"))
        for i in range(8):
            events.append(event(observation_id=f"obs-transfer-{i}", task_type="transfer"))
        for i in range(8):
            events.append(event(observation_id=f"obs-recall-{i}", task_type="definition_recall"))
        result = reduce_learning_state(COURSE, SYLLABUS, events, {})
        state = result["concepts"]["chain_rule"]
        self.assertIsNone(state["mastery"]["speed"])
        self.assertEqual(state["mastery_status"], "mastered")


class StatusModelTests(unittest.TestCase):
    def test_mastery_status_key_replaces_conflated_status_field(self):
        result = reduce_learning_state(COURSE, SYLLABUS, [], {})
        state = result["concepts"]["chain_rule"]
        self.assertIn("mastery_status", state)
        self.assertEqual(state["mastery_status"], "unseen")

    def test_prerequisite_blocked_availability_is_independent_of_mastery_status(self):
        syllabus = {
            "schema_version": 1,
            "concepts": {
                "derivative_rules": SYLLABUS["concepts"]["chain_rule"],
                "chain_rule": {**SYLLABUS["concepts"]["chain_rule"], "prerequisites": ["derivative_rules"]},
            },
        }
        result = reduce_learning_state(COURSE, syllabus, [], {})
        self.assertEqual(result["concepts"]["chain_rule"]["availability"], "prerequisite_blocked")
        self.assertEqual(result["concepts"]["derivative_rules"]["availability"], "available")


class RecurringMistakeTests(unittest.TestCase):
    def test_single_occurrence_is_not_yet_recurring(self):
        events = [event(observation_id="obs-1", outcome="incorrect", error_tags=["conceptual_error"])]
        result = reduce_learning_state(COURSE, SYLLABUS, events, {})
        mistake = result["concepts"]["chain_rule"]["recurring_mistakes"][0]
        self.assertFalse(mistake["recurring"])
        self.assertFalse(mistake["resolved"])

    def test_two_sessions_crosses_the_recurring_threshold(self):
        events = [
            event(observation_id="obs-1", outcome="incorrect", error_tags=["conceptual_error"], session_id="s1"),
            event(observation_id="obs-2", outcome="incorrect", error_tags=["conceptual_error"], session_id="s2"),
        ]
        result = reduce_learning_state(COURSE, SYLLABUS, events, {})
        mistake = result["concepts"]["chain_rule"]["recurring_mistakes"][0]
        self.assertTrue(mistake["recurring"])

    def test_mistake_resolves_after_independent_clean_streak(self):
        events = [
            event(observation_id="obs-err", outcome="incorrect", error_tags=["conceptual_error"]),
        ]
        for i in range(3):
            events.append(event(observation_id=f"obs-clean-{i}", outcome="correct"))
        result = reduce_learning_state(COURSE, SYLLABUS, events, {})
        mistake = result["concepts"]["chain_rule"]["recurring_mistakes"][0]
        self.assertTrue(mistake["resolved"])

    def test_mistake_resolution_is_not_too_aggressive(self):
        events = [
            event(observation_id="obs-err", outcome="incorrect", error_tags=["conceptual_error"]),
            event(observation_id="obs-clean-0", outcome="correct"),
        ]
        result = reduce_learning_state(COURSE, SYLLABUS, events, {})
        mistake = result["concepts"]["chain_rule"]["recurring_mistakes"][0]
        self.assertFalse(mistake["resolved"])

    def test_reoccurrence_resets_resolution(self):
        events = [
            event(observation_id="obs-err", outcome="incorrect", error_tags=["conceptual_error"]),
        ]
        for i in range(3):
            events.append(event(observation_id=f"obs-clean-{i}", outcome="correct"))
        events.append(
            event(
                observation_id="obs-relapse",
                outcome="incorrect",
                error_tags=["conceptual_error"],
                session_id="session-2",
            )
        )
        result = reduce_learning_state(COURSE, SYLLABUS, events, {})
        mistake = result["concepts"]["chain_rule"]["recurring_mistakes"][0]
        self.assertFalse(mistake["resolved"])
        self.assertTrue(mistake["recurring"])


if __name__ == "__main__":
    unittest.main()
