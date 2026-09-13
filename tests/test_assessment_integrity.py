import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "math-study" / "scripts"))

from math_study_lib.assessment import FrozenAssessment  # noqa: E402
from math_study_lib.assessment_integrity import (  # noqa: E402
    AssessmentIntegrityError,
    assess_attempt_evidence,
)
from math_study_lib.reducer import reduce_learning_state  # noqa: E402
from math_study_lib.storage import AssessmentConflict, StudyStore  # noqa: E402


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
                {"assessment_id": frozen.assessment_id, "outcome": "solution_seen"},
                frozen,
                prior_events=[],
            )
        decision = assess_attempt_evidence(
            {
                "assessment_id": frozen.assessment_id,
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
                "outcome": "correct",
                "assistance": {"full_solution_viewed": True},
            },
            frozen,
            prior_events=[
                {"assessment_id": frozen.assessment_id, "outcome": "incorrect"}
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


if __name__ == "__main__":
    unittest.main()
