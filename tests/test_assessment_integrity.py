import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.assessment import FrozenAssessment  # noqa: E402
from exam_prep_lib.assessment_integrity import (  # noqa: E402
    AssessmentIntegrityError,
    assess_attempt_evidence,
)
from exam_prep_lib.reducer import reduce_learning_state  # noqa: E402
from exam_prep_lib.storage import AssessmentConflict, StudyStore  # noqa: E402


def assessment(**overrides):
    value = {
        "assessment_id": "assessment-1",
        "target_id": "algebra:linear",
        "capability_id": "independent_problem",
        "prompt": "Solve 2x = 4.",
        "rubric": {"correct": 1, "shows_steps": 1},
        "expected_evidence": ["independent_work"],
        "source_refs": [
            {
                "source_id": "teacher:week-1",
                "authority": "teacher_material",
                "locator": "page 2",
            }
        ],
        "difficulty": 0.4,
        "question_version": 1,
        "rubric_version": 1,
    }
    value.update(overrides)
    return value


class AssessmentIntegrityTests(unittest.TestCase):
    def test_frozen_assessment_hash_is_stable_and_detects_tampering(self):
        first = FrozenAssessment.from_mapping(assessment())
        reordered = FrozenAssessment.from_mapping(
            {key: assessment()[key] for key in reversed(list(assessment()))}
        )
        self.assertEqual(first.spec_hash, reordered.spec_hash)
        with self.assertRaises(ValueError):
            FrozenAssessment.from_mapping(
                {**assessment(), "spec_hash": first.spec_hash[:-1] + "0"}
            )

    def test_solution_before_attempt_requires_explicit_reason(self):
        frozen = FrozenAssessment.from_mapping(assessment())
        with self.assertRaises(AssessmentIntegrityError):
            assess_attempt_evidence(
                {
                    "assessment_id": frozen.assessment_id,
                    "target_id": frozen.target_id,
                    "capability_id": frozen.capability_id,
                    "outcome": "solution_seen",
                },
                frozen,
                prior_events=[],
            )
        decision = assess_attempt_evidence(
            {
                "assessment_id": frozen.assessment_id,
                "target_id": frozen.target_id,
                "capability_id": frozen.capability_id,
                "outcome": "solution_seen",
                "explicit_exposure_reason": "learner requested a worked example",
            },
            frozen,
            prior_events=[],
        )
        self.assertTrue(decision.accepted)
        self.assertFalse(decision.mastery_eligible)

    def test_full_solution_work_never_promotes_independent_mastery(self):
        frozen = FrozenAssessment.from_mapping(assessment())
        decision = assess_attempt_evidence(
            {
                "assessment_id": frozen.assessment_id,
                "target_id": frozen.target_id,
                "capability_id": frozen.capability_id,
                "outcome": "correct",
                "assistance": {"full_solution_viewed": True},
            },
            frozen,
            prior_events=[
                {
                    "assessment_id": frozen.assessment_id,
                    "target_id": frozen.target_id,
                    "capability_id": frozen.capability_id,
                    "outcome": "incorrect",
                }
            ],
        )
        self.assertTrue(decision.accepted)
        self.assertFalse(decision.mastery_eligible)

    def test_downgraded_solution_exposure_flag_never_promotes_reducer_mastery(self):
        syllabus = {"concepts": {"algebra:linear": {"prerequisites": []}}}
        result = reduce_learning_state(
            {},
            syllabus,
            [
                {
                    "observation_id": "exposed-work",
                    "concept_id": "algebra:linear",
                    "capability_id": "independent_problem",
                    "task_type": "independent_problem",
                    "outcome": "correct",
                    "solution_exposed": True,
                    "assistance": {"levels_revealed": []},
                }
            ],
            {},
        )
        state = result["concepts"]["algebra:linear"]
        self.assertEqual(0.0, state["mastery"]["procedural"])
        self.assertEqual(0, state["evidence"]["independent_successes"])

    def test_explicit_exposure_integrity_state_alone_is_non_promoting(self):
        result = reduce_learning_state(
            {},
            {"schema_version": 2, "learning_targets": [{"target_id": "algebra:linear"}]},
            [
                {
                    "schema_version": 2,
                    "observation_id": "exposed-integrity",
                    "target_id": "algebra:linear",
                    "capability_id": "independent_problem",
                    "task_type": "independent_problem",
                    "outcome": "correct",
                    "assessment_integrity": "explicit_exposure",
                    "assistance": {},
                    "error_tags": [],
                }
            ],
            {},
        )
        state = result["targets"]["algebra:linear"]
        self.assertEqual(0.0, state["mastery"]["procedural"])
        self.assertEqual(0, state["evidence"]["independent_successes"])

    def test_store_assessment_is_idempotent_and_conflicts_on_divergence(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StudyStore(Path(tmp))
            frozen = FrozenAssessment.from_mapping(assessment())
            self.assertTrue(store.append_assessment(frozen).appended)
            self.assertFalse(store.append_assessment(frozen).appended)
            with self.assertRaises(AssessmentConflict):
                store.append_assessment(
                    FrozenAssessment.from_mapping(
                        assessment(prompt="Solve 3x = 6.", assessment_id="assessment-1")
                    )
                )
            self.assertEqual([frozen.assessment_id], [item["assessment_id"] for item in store.read_assessments()])

    def test_store_rejects_assessment_outside_contract_ranges(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StudyStore(Path(tmp))
            with self.assertRaises(ValueError):
                store.append_assessment(assessment(difficulty=1.5))

    def test_frozen_linkage_requires_target_capability_and_spec_hash(self):
        frozen = FrozenAssessment.from_mapping(assessment())
        for mismatch in (
            {"target_id": "other-target"},
            {"capability_id": "transfer"},
            {"assessment_spec_hash": "wrong-hash"},
        ):
            event = {
                "assessment_id": frozen.assessment_id,
                "target_id": frozen.target_id,
                "capability_id": frozen.capability_id,
                "outcome": "correct",
                **mismatch,
            }
            with self.assertRaises(AssessmentIntegrityError):
                assess_attempt_evidence(event, frozen, prior_events=[])

    def test_store_persists_integrity_decision_on_canonical_v2_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StudyStore.for_exam_prep(Path(tmp))
            frozen = FrozenAssessment.from_mapping(assessment())
            store.append_assessment(frozen)
            proposal = {
                "schema_version": 2,
                "observation_id": "frozen-obs",
                "target_id": frozen.target_id,
                "task_id": "assessment-task",
                "capability_id": frozen.capability_id,
                "task_type": "independent_problem",
                "outcome": "correct",
                "assistance": {"levels_revealed": []},
                "error_tags": [],
                "diagnostic_confidence": "high",
                "source_refs": [],
                "assessment_id": frozen.assessment_id,
            }
            result = store.append_observation(
                proposal,
                "session-1",
                "2026-09-13T12:00:00+00:00",
                60,
                30,
            )
            self.assertEqual("frozen_attempt", result.canonical_event["assessment_integrity"])
            self.assertEqual(frozen.spec_hash, result.canonical_event["assessment_spec_hash"])

            exposed = dict(proposal)
            exposed["observation_id"] = "exposed-obs"
            exposed["outcome"] = "solution_seen"
            exposed["explicit_exposure_reason"] = "cram"
            exposed["solution_exposed"] = True
            exposed_result = store.append_observation(
                exposed,
                "session-1",
                "2026-09-13T12:01:00+00:00",
                60,
                30,
            )
            self.assertEqual("explicit_exposure", exposed_result.canonical_event["assessment_integrity"])


if __name__ == "__main__":
    unittest.main()
