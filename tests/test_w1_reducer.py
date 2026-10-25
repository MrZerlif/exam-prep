import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.reducer import reduce_learning_state  # noqa: E402


SYLLABUS = {"schema_version": 1, "concepts": {"limits": {"prerequisites": []}}}
COURSE = {"schema_version": 1}


def event(observation_id, **updates):
    value = {
        "schema_version": 1,
        "observation_id": observation_id,
        "concept_id": "limits",
        "task_id": observation_id,
        "task_type": "independent_problem",
        "outcome": "correct",
        "assistance": {"levels_revealed": []},
        "error_tags": [],
        "diagnostic_confidence": "high",
        "learner_self_confidence": "high",
        "recorded_at": "2026-10-25T10:00:00+00:00",
        "elapsed_seconds": None,
        "expected_seconds": None,
    }
    value.update(updates)
    return value


class UnclearOutcomeTests(unittest.TestCase):
    def test_unclear_event_has_no_effect_on_mastery_or_error_state(self):
        baseline = reduce_learning_state(COURSE, SYLLABUS, [], {})["concepts"]["limits"]
        result = reduce_learning_state(
            COURSE,
            SYLLABUS,
            [
                event(
                    "voice-unclear",
                    outcome="unclear",
                    error_tags=["conceptual_error"],
                    elapsed_seconds=90,
                    expected_seconds=30,
                )
            ],
            {},
        )["concepts"]["limits"]

        self.assertEqual(baseline, result)


class SupersededObservationTests(unittest.TestCase):
    def test_reducer_uses_replacement_and_keeps_old_event_out_of_evidence(self):
        original = event("old", outcome="correct")
        replacement = event(
            "new",
            outcome="incorrect",
            error_tags=["algebra_error"],
            supersedes_observation_id="old",
        )

        actual = reduce_learning_state(COURSE, SYLLABUS, [original, replacement], {})
        replacement_only = reduce_learning_state(COURSE, SYLLABUS, [replacement], {})

        self.assertEqual(replacement_only["concepts"]["limits"], actual["concepts"]["limits"])
        self.assertEqual(0, actual["concepts"]["limits"]["evidence"]["independent_successes"])
        self.assertEqual(1, actual["concepts"]["limits"]["evidence"]["failures"])


class ReadinessMaturityGateTests(unittest.TestCase):
    def _mature_syllabus(self):
        return {
            "schema_version": 2,
            "learning_targets": [
                {
                    "target_id": "limits",
                    "prerequisites": [],
                    "capability_ids": ["independent_problem"],
                }
            ],
        }

    def test_missing_retention_or_transfer_caps_status_at_learning_with_reason(self):
        events = [event(f"correct-{index}") for index in range(4)]
        state = reduce_learning_state({}, self._mature_syllabus(), events, {})["targets"]["limits"]

        self.assertEqual("learning", state["mastery_status"])
        self.assertEqual(
            ["retained_or_transferred"],
            state["mastery_status_details"]["missing"],
        )

    def test_retention_or_transfer_evidence_allows_exam_ready(self):
        events = [event(f"correct-{index}") for index in range(4)]
        events.append(event("retained", task_type="delayed_recall"))
        state = reduce_learning_state({}, self._mature_syllabus(), events, {})["targets"]["limits"]

        self.assertEqual("exam_ready", state["mastery_status"])
        self.assertEqual([], state["mastery_status_details"]["missing"])


if __name__ == "__main__":
    unittest.main()
