import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.schema_validation import (  # noqa: E402
    load_schema,
    validate_document,
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
            "concepts": {},
            "assessment_capabilities": {},
        }
        validate_document(source_ref, load_schema("source-ref.schema.json"))
        validate_document(syllabus, load_schema("syllabus.schema.json"))

    def test_v2_observation_uses_target_id_and_capability_id(self):
        validate_observation_proposal(
            {
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
            }
        )


if __name__ == "__main__":
    unittest.main()
