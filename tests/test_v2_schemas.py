import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.schema_validation import (  # noqa: E402
    load_schema,
    validate_document,
    validate_observation_event,
    validate_observation_proposal,
)


class V2SchemaTests(unittest.TestCase):
    def test_target_syllabus_and_source_ref_contracts_are_loadable(self):
        source_ref = {
            "source_id": "teacher:week-1",
            "authority": "teacher_material",
            "locator": "page 2",
            "provider_id": "local",
        }
        syllabus = {
            "schema_version": 2,
            "course_id": "algebra-1",
            "source_refs": [source_ref],
            "learning_targets": [
                {
                    "target_id": "algebra:linear",
                    "title": "Linear equations",
                    "prerequisites": [],
                    "capability_ids": ["independent_problem"],
                    "source_refs": [source_ref],
                }
            ],
            "assessment_capabilities": {},
        }
        validate_document(source_ref, load_schema("source-ref.schema.json"))
        validate_document(syllabus, load_schema("syllabus.schema.json"))
        validate_document(
            {"schema_version": 2, "derived_from_revision": 1, "targets": {}, "aliases": {}},
            load_schema("targets.schema.json"),
        )

    def test_source_ref_requires_only_source_id(self):
        validate_document({"source_id": "s1"}, load_schema("source-ref.schema.json"))
        validate_document(
            {
                "source_id": "s1",
                "provider": "notebooklm-mcp",
                "location": {"page": 1},
            },
            load_schema("source-ref.schema.json"),
        )

    def test_v2_observation_uses_target_id_and_capability_id(self):
        proposal = {
                "schema_version": 2,
                "observation_id": "obs-v2",
                "target_id": "algebra:linear",
                "task_id": "task-v2",
                "capability_id": "independent_problem",
                "task_type": "independent_problem",
                "outcome": "correct",
                "assistance": {
                    "requested": False,
                    "levels_revealed": [],
                    "scaffold_types": [],
                    "partial_transformation_shown": False,
                    "full_solution_viewed": False,
                },
                "error_tags": [],
                "diagnostic_confidence": "high",
                "source_refs": [
                    {
                        "source_id": "teacher:week-1",
                        "authority": "teacher_material",
                        "locator": "page 2",
                        "provider_id": "local",
                    }
                ],
                "assessment_id": "assessment-1",
                "assessment_spec_id": "assessment-1:v1",
                "exposure_metadata": {"mode": "blind_attempt"},
                "evaluation_context": {"protocol_id": "pilot"},
                "assessment_result": {"score": 1, "max_score": 1},
            }
        validate_observation_proposal(proposal)
        event = {
            **proposal,
            "recorded_at": "2026-09-13T12:00:00+00:00",
            "session_id": "session-1",
            "expected_seconds": 60,
            "elapsed_seconds": 45,
            "assessment_spec_hash": "hash",
            "assessment_integrity": "frozen_attempt",
        }
        validate_observation_event(event)

    def test_engine_owned_integrity_fields_are_rejected_from_proposals(self):
        proposal = {
            "schema_version": 2,
            "observation_id": "obs-v2",
            "target_id": "algebra:linear",
            "task_id": "task-v2",
            "capability_id": "independent_problem",
            "task_type": "independent_problem",
            "outcome": "correct",
            "assistance": {},
            "error_tags": ["new_open_error_tag"],
            "diagnostic_confidence": "high",
            "source_refs": [],
            "assessment_integrity": "frozen_attempt",
        }
        with self.assertRaisesRegex(ValueError, "assessment_integrity"):
            validate_observation_proposal(proposal)
        nested = {**proposal}
        nested.pop("assessment_integrity")
        nested["assessment"] = {"assessment_integrity": "frozen_attempt"}
        with self.assertRaises(ValueError):
            validate_observation_proposal(nested)


if __name__ == "__main__":
    unittest.main()
