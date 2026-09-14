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

    def test_repeated_freeze_of_same_id_with_changed_purpose_is_rejected(self):
        # Re-freezing assessment_id "assessment-1" as mock after it was
        # already frozen as practice must not be a one-step way around pool
        # isolation: same id, same content, only purpose flipped. The
        # existing same-id/different-contract conflict check already
        # catches this (purpose is part of the frozen contract), so this
        # pins that it stays caught rather than accidentally special-cased.
        with tempfile.TemporaryDirectory() as tmp:
            store = StudyStore(Path(tmp))
            practiced = FrozenAssessment.from_mapping(assessment(purpose="practice"))
            store.append_assessment(practiced)
            with self.assertRaises((AssessmentConflict, AssessmentIntegrityError)):
                store.append_assessment(
                    FrozenAssessment.from_mapping(
                        assessment(assessment_id=practiced.assessment_id, purpose="mock")
                    )
                )
            self.assertEqual(
                "practice",
                FrozenAssessment.from_mapping(store.read_assessments()[0]).purpose,
            )

    def test_repeated_freeze_of_an_identical_pool_isolated_assessment_is_idempotent(self):
        # The guard must recognize "the same assessment, re-applied" as
        # idempotent, not as the assessment colliding with itself in its
        # own pool - this is what re-running an authoring pipeline (e.g.
        # applying the same curriculum proposal twice) depends on. Uses
        # purpose=mock specifically, since that is the side of the guard
        # with a non-trivial opposing-pool comparison to get wrong.
        with tempfile.TemporaryDirectory() as tmp:
            store = StudyStore(Path(tmp))
            mocked = FrozenAssessment.from_mapping(assessment(purpose="mock"))
            first = store.append_assessment(mocked)
            second = store.append_assessment(mocked)
            self.assertTrue(first.appended)
            self.assertFalse(second.appended)
            self.assertEqual(1, len(store.read_assessments()))

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

            retry = store.append_observation(
                proposal,
                "session-1",
                "2026-09-13T12:00:00+00:00",
                60,
                30,
            )
            self.assertFalse(
                retry.appended,
                "identical retry of an assessment-linked observation must be "
                "idempotent, not an ObservationConflict",
            )

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

    def test_mock_assessment_rejects_attempt_outside_exam_phase(self):
        frozen = FrozenAssessment.from_mapping(assessment(purpose="mock"))
        event = {
            "assessment_id": frozen.assessment_id,
            "target_id": frozen.target_id,
            "capability_id": frozen.capability_id,
            "outcome": "correct",
        }
        with self.assertRaises(AssessmentIntegrityError):
            assess_attempt_evidence(event, frozen, prior_events=[], session_phase="study")
        decision = assess_attempt_evidence(event, frozen, prior_events=[], session_phase="exam")
        self.assertTrue(decision.accepted)

    def test_practice_assessment_rejects_attempt_during_exam_phase(self):
        frozen = FrozenAssessment.from_mapping(assessment(purpose="practice"))
        event = {
            "assessment_id": frozen.assessment_id,
            "target_id": frozen.target_id,
            "capability_id": frozen.capability_id,
            "outcome": "correct",
        }
        with self.assertRaises(AssessmentIntegrityError):
            assess_attempt_evidence(event, frozen, prior_events=[], session_phase="exam")
        decision = assess_attempt_evidence(event, frozen, prior_events=[], session_phase="study")
        self.assertTrue(decision.accepted)

    def test_purpose_defaults_to_practice_and_session_phase_defaults_to_study(self):
        frozen = FrozenAssessment.from_mapping(assessment())
        self.assertEqual("practice", frozen.purpose)
        event = {
            "assessment_id": frozen.assessment_id,
            "target_id": frozen.target_id,
            "capability_id": frozen.capability_id,
            "outcome": "correct",
        }
        decision = assess_attempt_evidence(event, frozen, prior_events=[])
        self.assertTrue(decision.accepted)

    def test_store_rejects_recording_a_mock_attempt_outside_exam_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StudyStore.for_exam_prep(Path(tmp))
            frozen = FrozenAssessment.from_mapping(assessment(purpose="mock"))
            store.append_assessment(frozen)
            proposal = {
                "schema_version": 2,
                "observation_id": "mock-leak",
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
            with self.assertRaises(AssessmentIntegrityError):
                store.append_observation(
                    proposal,
                    "session-1",
                    "2026-09-13T12:00:00+00:00",
                    60,
                    30,
                    session_phase="study",
                )
            self.assertEqual([], store.read_complete_observations())
            result = store.append_observation(
                proposal,
                "session-1",
                "2026-09-13T12:00:00+00:00",
                60,
                30,
                session_phase="exam",
            )
            self.assertEqual("frozen_attempt", result.canonical_event["assessment_integrity"])

    def test_mock_assessment_cannot_reuse_content_already_frozen_as_practice(self):
        # Pool isolation is keyed on mere freezing, not on whether the
        # content was ever attempted: requiring an attempt first would leave
        # a window where a freshly-frozen-but-unattempted practice item's
        # content could still be reused for mock.
        with tempfile.TemporaryDirectory() as tmp:
            store = StudyStore.for_exam_prep(Path(tmp))
            practiced = FrozenAssessment.from_mapping(
                assessment(assessment_id="assessment-practiced", purpose="practice")
            )
            store.append_assessment(practiced)

            same_content_mock = FrozenAssessment.from_mapping(
                assessment(assessment_id="assessment-mock-same-content", purpose="mock")
            )
            with self.assertRaises(AssessmentIntegrityError):
                store.append_assessment(same_content_mock)

    def test_held_out_assessment_cannot_reuse_content_already_frozen_as_practice(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StudyStore.for_exam_prep(Path(tmp))
            practiced = FrozenAssessment.from_mapping(
                assessment(assessment_id="assessment-practiced-2", purpose="practice")
            )
            store.append_assessment(practiced)

            same_content_held_out = FrozenAssessment.from_mapping(
                assessment(assessment_id="assessment-held-out-same-content", purpose="held_out")
            )
            with self.assertRaises(AssessmentIntegrityError):
                store.append_assessment(same_content_held_out)

    def test_practice_assessment_cannot_reuse_content_already_frozen_as_mock(self):
        # Symmetric direction: content already committed to the exam pool
        # (held_out/mock) must not be reusable for ordinary practice either
        # - that would expose held-out/mock material through the back door,
        # regardless of freeze order.
        with tempfile.TemporaryDirectory() as tmp:
            store = StudyStore.for_exam_prep(Path(tmp))
            mocked = FrozenAssessment.from_mapping(
                assessment(assessment_id="assessment-mock-first", purpose="mock")
            )
            store.append_assessment(mocked)

            same_content_practice = FrozenAssessment.from_mapping(
                assessment(assessment_id="assessment-practice-after-mock", purpose="practice")
            )
            with self.assertRaises(AssessmentIntegrityError):
                store.append_assessment(same_content_practice)

    def test_retest_assessment_cannot_reuse_content_already_frozen_as_held_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StudyStore.for_exam_prep(Path(tmp))
            held_out = FrozenAssessment.from_mapping(
                assessment(assessment_id="assessment-held-out-first", purpose="held_out")
            )
            store.append_assessment(held_out)

            same_content_retest = FrozenAssessment.from_mapping(
                assessment(assessment_id="assessment-retest-after-held-out", purpose="retest")
            )
            with self.assertRaises(AssessmentIntegrityError):
                store.append_assessment(same_content_retest)

    def test_mock_assessment_may_be_frozen_when_content_is_not_in_the_training_pool(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StudyStore.for_exam_prep(Path(tmp))
            fresh_mock = FrozenAssessment.from_mapping(
                assessment(assessment_id="assessment-mock-fresh", purpose="mock")
            )
            result = store.append_assessment(fresh_mock)
            self.assertTrue(result.appended)

    def test_mock_cannot_reuse_content_differing_only_by_question_version(self):
        # question_version/rubric_version must not be a loophole: the same
        # prompt/rubric under a bumped version number is still the same
        # question content for pool-isolation purposes (spec_hash still
        # differs, since version numbers stay part of the frozen contract).
        with tempfile.TemporaryDirectory() as tmp:
            store = StudyStore.for_exam_prep(Path(tmp))
            practiced = FrozenAssessment.from_mapping(
                assessment(
                    assessment_id="assessment-practiced-v1", purpose="practice", question_version=1
                )
            )
            store.append_assessment(practiced)

            same_prompt_new_version_mock = FrozenAssessment.from_mapping(
                assessment(
                    assessment_id="assessment-mock-v2", purpose="mock", question_version=2
                )
            )
            with self.assertRaises(AssessmentIntegrityError):
                store.append_assessment(same_prompt_new_version_mock)

    def test_mock_cannot_reuse_content_differing_only_by_trailing_newline(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StudyStore.for_exam_prep(Path(tmp))
            practiced = FrozenAssessment.from_mapping(
                assessment(assessment_id="assessment-practiced-plain", purpose="practice")
            )
            store.append_assessment(practiced)

            trailing_newline_mock = FrozenAssessment.from_mapping(
                assessment(
                    assessment_id="assessment-mock-trailing-newline",
                    purpose="mock",
                    prompt="Solve 2x = 4.\n",
                )
            )
            with self.assertRaises(AssessmentIntegrityError):
                store.append_assessment(trailing_newline_mock)

    def test_question_hash_ignores_assessment_id_purpose_difficulty_and_version_numbers(self):
        base = FrozenAssessment.from_mapping(assessment())
        same_content_different_id = FrozenAssessment.from_mapping(
            assessment(assessment_id="assessment-2")
        )
        same_content_different_purpose = FrozenAssessment.from_mapping(
            assessment(purpose="retest")
        )
        same_content_different_difficulty = FrozenAssessment.from_mapping(
            assessment(difficulty=0.9)
        )
        same_content_different_versions = FrozenAssessment.from_mapping(
            assessment(question_version=7, rubric_version=3)
        )
        different_prompt = FrozenAssessment.from_mapping(
            assessment(prompt="Solve 3x = 9.")
        )
        self.assertEqual(base.question_hash, same_content_different_id.question_hash)
        self.assertEqual(base.question_hash, same_content_different_purpose.question_hash)
        self.assertEqual(base.question_hash, same_content_different_difficulty.question_hash)
        self.assertEqual(base.question_hash, same_content_different_versions.question_hash)
        self.assertNotEqual(base.question_hash, different_prompt.question_hash)
        self.assertNotEqual(base.spec_hash, same_content_different_id.spec_hash)
        self.assertNotEqual(base.spec_hash, same_content_different_versions.spec_hash)

    def test_question_hash_ignores_rubric_expected_evidence_and_source_refs(self):
        # The learner is only ever shown the prompt; rubric/expected_evidence
        # /source_refs are grading and provenance bookkeeping. Hashing them
        # would let a cosmetic edit to any of the three re-launder
        # already-practiced content into the exam pool without changing
        # anything the learner actually sees.
        base = FrozenAssessment.from_mapping(assessment())
        different_rubric = FrozenAssessment.from_mapping(
            assessment(rubric={"correct": 1, "shows_steps": 1, "extra_note": "clarified"})
        )
        different_expected_evidence = FrozenAssessment.from_mapping(
            assessment(expected_evidence=["independent_work", "shows_algebra"])
        )
        different_source_refs = FrozenAssessment.from_mapping(
            assessment(
                source_refs=[
                    {
                        "source_id": "teacher:week-2",
                        "authority": "teacher_material",
                        "locator": "page 9",
                    }
                ]
            )
        )
        self.assertEqual(base.question_hash, different_rubric.question_hash)
        self.assertEqual(base.question_hash, different_expected_evidence.question_hash)
        self.assertEqual(base.question_hash, different_source_refs.question_hash)
        self.assertNotEqual(base.spec_hash, different_rubric.spec_hash)
        self.assertNotEqual(base.spec_hash, different_expected_evidence.spec_hash)
        self.assertNotEqual(base.spec_hash, different_source_refs.spec_hash)

    def test_question_hash_normalizes_prompt_whitespace(self):
        base = FrozenAssessment.from_mapping(assessment())
        padded_and_trailing_newline = FrozenAssessment.from_mapping(
            assessment(prompt="  Solve   2x = 4.\n")
        )
        internal_whitespace_run = FrozenAssessment.from_mapping(
            assessment(prompt="Solve 2x\t=  4.")
        )
        self.assertEqual(base.question_hash, padded_and_trailing_newline.question_hash)
        self.assertEqual(base.question_hash, internal_whitespace_run.question_hash)

    def test_recorded_event_is_self_describing_with_assessment_purpose(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StudyStore.for_exam_prep(Path(tmp))
            frozen = FrozenAssessment.from_mapping(assessment(purpose="retest"))
            store.append_assessment(frozen)
            proposal = {
                "schema_version": 2,
                "observation_id": "self-describing-1",
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
                proposal, "session-1", "2026-09-13T12:00:00+00:00", 60, 30, session_phase="study"
            )
            self.assertEqual("retest", result.canonical_event["assessment_purpose"])
            self.assertEqual(frozen.spec_hash, result.canonical_event["assessment_spec_hash"])

    def test_held_out_assessment_has_no_phase_restriction(self):
        # held_out is a reserved/candidate pool, not an in-progress mock -
        # its protection is the content-hash pool-isolation check, not a
        # phase gate, so it may be attempted in either phase.
        frozen = FrozenAssessment.from_mapping(assessment(purpose="held_out"))
        event = {
            "assessment_id": frozen.assessment_id,
            "target_id": frozen.target_id,
            "capability_id": frozen.capability_id,
            "outcome": "correct",
        }
        for phase in ("study", "exam"):
            decision = assess_attempt_evidence(
                event, frozen, prior_events=[], session_phase=phase
            )
            self.assertTrue(decision.accepted)

    def test_new_v2_non_assessment_event_is_not_legacy_unfrozen(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StudyStore.for_exam_prep(Path(tmp))
            result = store.append_observation(
                {
                    "schema_version": 2,
                    "observation_id": "practice-1",
                    "target_id": "algebra:linear",
                    "task_id": "practice-task",
                    "capability_id": "independent_problem",
                    "task_type": "independent_problem",
                    "outcome": "correct",
                    "assistance": {"levels_revealed": []},
                    "error_tags": [],
                    "diagnostic_confidence": "high",
                    "source_refs": [],
                },
                "session-1",
                "2026-09-13T12:00:00+00:00",
                None,
                None,
            )
            self.assertEqual(
                "not_assessment", result.canonical_event["assessment_integrity"]
            )


if __name__ == "__main__":
    unittest.main()
