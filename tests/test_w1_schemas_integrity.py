import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.assessment import FrozenAssessment  # noqa: E402
from exam_prep_lib.assessment_integrity import assess_attempt_evidence, is_attempt  # noqa: E402
from exam_prep_lib.evidence_maturity import derive_evidence_maturity  # noqa: E402
from exam_prep_lib.schema_validation import (  # noqa: E402
    SchemaError,
    load_schema,
    validate_document,
    validate_observation_event,
    validate_observation_proposal,
)


def proposal(**updates):
    value = {
        "schema_version": 2,
        "observation_id": "obs-new",
        "target_id": "limits",
        "task_id": "task-new",
        "capability_id": "independent_problem",
        "task_type": "independent_problem",
        "outcome": "correct",
        "assistance": {"levels_revealed": []},
        "error_tags": [],
        "diagnostic_confidence": "high",
        "source_refs": [],
    }
    value.update(updates)
    return value


def event(**updates):
    value = {
        **proposal(),
        "recorded_at": "2026-10-25T10:00:00+00:00",
        "session_id": "session-1",
        "expected_seconds": None,
        "elapsed_seconds": None,
        "assessment_integrity": "not_assessment",
    }
    value.update(updates)
    return value


class W1ObservationSchemaTests(unittest.TestCase):
    def test_unclear_and_supersedes_are_valid_v2_proposal_fields(self):
        validate_observation_proposal(
            proposal(outcome="unclear", supersedes_observation_id="obs-old"),
            known_observation_ids={"obs-old"},
        )

    def test_unknown_superseded_observation_is_rejected(self):
        with self.assertRaisesRegex(SchemaError, "unknown observation"):
            validate_observation_proposal(
                proposal(supersedes_observation_id="missing"),
                known_observation_ids={"obs-old"},
            )

    def test_supersedes_reference_requires_event_context(self):
        with self.assertRaisesRegex(SchemaError, "known observation IDs"):
            validate_observation_proposal(proposal(supersedes_observation_id="obs-old"))

    def test_late_recording_flag_is_engine_owned_and_event_only(self):
        with self.assertRaisesRegex(SchemaError, "elapsed_includes_recording_delay"):
            validate_observation_proposal(
                proposal(elapsed_includes_recording_delay=True),
                known_observation_ids=set(),
            )

        validate_observation_event(
            event(
                outcome="unclear",
                supersedes_observation_id="obs-old",
                elapsed_includes_recording_delay=True,
            )
        )

    def test_invalid_late_recording_flag_type_is_rejected(self):
        with self.assertRaisesRegex(SchemaError, "elapsed_includes_recording_delay"):
            validate_observation_event(event(elapsed_includes_recording_delay="yes"))

    def test_correction_example_validates_with_known_prior_id(self):
        path = ROOT / "skill" / "exam-prep" / "examples" / "observation-correction-proposal.json"
        correction = json.loads(path.read_text(encoding="utf-8"))
        validate_observation_proposal(
            correction,
            known_observation_ids={"obs-example-0001"},
        )


class W1ReadinessSchemaTests(unittest.TestCase):
    def test_target_and_concept_schemas_accept_missing_maturity_reason(self):
        target_snapshot = {
            "schema_version": 2,
            "derived_from_revision": 1,
            "targets": {
                "limits": {
                    "mastery_status": "learning",
                    "mastery_status_details": {"missing": ["retained_or_transferred"]},
                }
            },
            "aliases": {},
        }
        validate_document(target_snapshot, load_schema("targets.schema.json"))

        concepts = {
            "schema_version": 1,
            "derived_from_revision": 1,
            "concepts": {
                "limits": {
                    "mastery_status": "learning",
                    "mastery_status_details": {"missing": ["retained_or_transferred"]},
                }
            },
        }
        validate_document(concepts, load_schema("concepts.schema.json"))


class W1AssessmentAndMaturityTests(unittest.TestCase):
    def test_unclear_is_not_attempt_or_mastery_eligible(self):
        frozen = FrozenAssessment.from_mapping(
            {
                "assessment_id": "assessment-1",
                "target_id": "limits",
                "capability_id": "independent_problem",
                "prompt": "Solve 2x = 4.",
                "rubric": {"correct": 1},
                "expected_evidence": ["independent_work"],
                "source_refs": [],
                "difficulty": 0.4,
                "question_version": 1,
                "rubric_version": 1,
            }
        )
        observation = {
            "assessment_id": "assessment-1",
            "target_id": "limits",
            "capability_id": "independent_problem",
            "outcome": "unclear",
            "assistance": {"levels_revealed": ["H0"]},
        }

        self.assertFalse(is_attempt(observation))
        decision = assess_attempt_evidence(observation, frozen, prior_events=[])
        self.assertTrue(decision.accepted)
        self.assertFalse(decision.mastery_eligible)

    def test_superseded_attempt_does_not_unlock_solution_exposure(self):
        frozen = FrozenAssessment.from_mapping(
            {
                "assessment_id": "assessment-1",
                "target_id": "limits",
                "capability_id": "independent_problem",
                "prompt": "Solve 2x = 4.",
                "rubric": {"correct": 1},
                "expected_evidence": ["independent_work"],
                "source_refs": [],
                "difficulty": 0.4,
                "question_version": 1,
                "rubric_version": 1,
            }
        )
        with self.assertRaisesRegex(ValueError, "before attempt requires an explicit reason"):
            assess_attempt_evidence(
                {
                    "observation_id": "replacement",
                    "supersedes_observation_id": "old-attempt",
                    "assessment_id": "assessment-1",
                    "target_id": "limits",
                    "capability_id": "independent_problem",
                    "outcome": "solution_seen",
                },
                frozen,
                prior_events=[
                    {
                        "observation_id": "old-attempt",
                        "assessment_id": "assessment-1",
                        "outcome": "incorrect",
                    }
                ],
            )

    def test_unclear_outcome_does_not_create_maturity_even_with_explicit_facets(self):
        maturity = derive_evidence_maturity(
            [
                {
                    "outcome": "unclear",
                    "task_type": "transfer",
                    "evidence_facets": ["demonstrated", "retained", "transferred"],
                }
            ]
        )

        self.assertEqual(0, maturity["demonstrated"]["count"])
        self.assertEqual(0, maturity["retained"]["count"])
        self.assertEqual(0, maturity["transferred"]["count"])

    def test_evidence_maturity_ignores_superseded_events(self):
        maturity = derive_evidence_maturity(
            [
                {"observation_id": "old", "task_type": "transfer", "outcome": "correct"},
                {
                    "observation_id": "new",
                    "task_type": "independent_problem",
                    "outcome": "incorrect",
                    "supersedes_observation_id": "old",
                },
            ]
        )

        self.assertEqual(0, maturity["demonstrated"]["count"])
        self.assertEqual(0, maturity["transferred"]["count"])


if __name__ == "__main__":
    unittest.main()
