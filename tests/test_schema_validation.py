import sys
import unittest


sys.path.insert(0, "skill/exam-prep/scripts")

from exam_prep_lib.schema_validation import (  # noqa: E402
    SchemaError,
    validate_observation_proposal,
    validate_state_bundle,
)


def valid_proposal():
    return {
        "schema_version": 1,
        "observation_id": "obs-1",
        "concept_id": "chain_rule",
        "task_id": "transfer-1",
        "task_type": "transfer",
        "outcome": "incorrect",
        "assistance": {
            "requested": True,
            "levels_revealed": ["H1"],
            "scaffold_types": ["method_prompt"],
            "partial_transformation_shown": False,
            "full_solution_viewed": False,
        },
        "error_tags": ["conceptual_error"],
        "diagnostic_confidence": "high",
        "learner_self_confidence": "medium",
        "learner_explanation": "Я забыл производную внутренней функции.",
        "source_refs": ["official-exam-list:q7"],
    }


class SchemaValidationTests(unittest.TestCase):
    def test_valid_observation_proposal_is_accepted(self):
        validate_observation_proposal(valid_proposal())

    def test_missing_observation_id_reports_json_path(self):
        proposal = valid_proposal()
        del proposal["observation_id"]
        with self.assertRaisesRegex(SchemaError, "observation_id"):
            validate_observation_proposal(proposal)

    def test_invalid_task_type_is_rejected(self):
        proposal = valid_proposal()
        proposal["task_type"] = "guessing"
        with self.assertRaisesRegex(SchemaError, "task_type"):
            validate_observation_proposal(proposal)

    def test_confidence_is_bounded_and_separate(self):
        proposal = valid_proposal()
        proposal["diagnostic_confidence"] = 1.4
        with self.assertRaisesRegex(SchemaError, "diagnostic_confidence"):
            validate_observation_proposal(proposal)

    def test_llm_proposal_rejects_engine_owned_timing(self):
        proposal = valid_proposal()
        proposal["elapsed_seconds"] = 12
        with self.assertRaisesRegex(SchemaError, "elapsed_seconds"):
            validate_observation_proposal(proposal)

    def test_malformed_assistance_is_rejected(self):
        proposal = valid_proposal()
        proposal["assistance"]["levels_revealed"] = ["H9"]
        with self.assertRaisesRegex(SchemaError, "levels_revealed"):
            validate_observation_proposal(proposal)

    def test_learner_self_confidence_is_optional(self):
        proposal = valid_proposal()
        del proposal["learner_self_confidence"]
        validate_observation_proposal(proposal)

    def test_diagnostic_confidence_stays_required(self):
        proposal = valid_proposal()
        del proposal["diagnostic_confidence"]
        with self.assertRaisesRegex(SchemaError, "diagnostic_confidence"):
            validate_observation_proposal(proposal)

    def test_non_numeric_mastery_is_rejected(self):
        bundle = {
            "schema_version": 1,
            "derived_from_revision": 0,
            "concepts": {
                "chain_rule": {
                    "mastery": {
                        "conceptual": "high",
                        "procedural": 0.0,
                        "recall": 0.0,
                        "transfer": 0.0,
                        "speed": 0.0,
                    },
                    "confidence": {
                        "diagnostic": 0.8,
                        "learner_self_report": 0.6,
                    },
                }
            },
        }
        with self.assertRaisesRegex(SchemaError, "conceptual"):
            validate_state_bundle(bundle)


if __name__ == "__main__":
    unittest.main()
