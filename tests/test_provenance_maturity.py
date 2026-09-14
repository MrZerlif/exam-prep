import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.evidence_maturity import derive_evidence_maturity  # noqa: E402
from exam_prep_lib.provenance import SourceRef, source_ref_from_mapping  # noqa: E402
from exam_prep_lib.reducer import reduce_learning_state  # noqa: E402


class ProvenanceAndMaturityTests(unittest.TestCase):
    def test_source_ref_preserves_authority_and_locator(self):
        ref = source_ref_from_mapping(
            {
                "source_id": "teacher:week-1",
                "authority": "teacher_material",
                "locator": "page 4",
                "title": "Week 1 notes",
            }
        )
        self.assertEqual("teacher:week-1", ref.source_id)
        self.assertEqual("teacher_material", ref.authority)
        self.assertEqual("page 4", ref.locator)
        self.assertEqual("teacher:week-1", ref.to_mapping()["source_id"])

    def test_source_ref_requires_structured_identity(self):
        with self.assertRaises(ValueError):
            SourceRef.from_mapping({"authority": "general_reference"})

    def test_source_ref_defaults_optional_metadata_without_authority_inference(self):
        minimal = source_ref_from_mapping({"source_id": "s1"})
        self.assertEqual("unknown", minimal.authority)
        self.assertEqual("unknown", minimal.provider_id)
        self.assertEqual(
            "unknown",
            source_ref_from_mapping({"source_id": "teacher:fake"}).authority,
        )

        notebooklm = source_ref_from_mapping(
            {
                "source_id": "s1",
                "provider": "notebooklm-mcp",
                "location": {"page": 1},
            }
        )
        self.assertEqual("notebooklm-mcp", notebooklm.provider_id)
        self.assertEqual({"page": 1}, notebooklm.location)
        self.assertEqual("", notebooklm.locator)

    def test_source_policy_order_matches_authority_rank(self):
        root = Path(__file__).resolve().parents[1]
        course = json.loads(
            (root / "skill" / "exam-prep" / "templates" / "course.json").read_text(encoding="utf-8")
        )
        priority = course["source_policy"]["priority_order"]
        self.assertLess(priority.index("teacher_material"), priority.index("official_exam_list"))
        from exam_prep_lib.provenance import AUTHORITY_RANKS
        self.assertGreater(
            AUTHORITY_RANKS["teacher_material"],
            AUTHORITY_RANKS["official_exam_list"],
        )
    def test_transfer_can_be_demonstrated_without_retention(self):
        maturity = derive_evidence_maturity(
            [
                {
                    "recorded_at": "2026-01-03T10:00:00+00:00",
                    "task_type": "transfer",
                    "outcome": "correct",
                    "assistance": {"levels_revealed": []},
                }
            ]
        )
        self.assertEqual(1, maturity["demonstrated"]["count"])
        self.assertEqual(0, maturity["retained"]["count"])
        self.assertEqual(1, maturity["transferred"]["count"])
        self.assertIsNone(maturity["retained"]["last_at"])

    def test_maturity_is_separate_from_mastery_dimensions(self):
        result = reduce_learning_state(
            {},
            {"concepts": {"limits": {"prerequisites": []}}},
            [
                {
                    "concept_id": "limits",
                    "task_type": "transfer",
                    "outcome": "correct",
                    "assistance": {"levels_revealed": []},
                    "recorded_at": "2026-01-03T10:00:00+00:00",
                }
            ],
            {},
        )
        state = result["concepts"]["limits"]
        self.assertIn("evidence_maturity", state)
        self.assertEqual(1, state["evidence_maturity"]["transferred"]["count"])
        self.assertIn("mastery", state)
        self.assertNotEqual(state["evidence_maturity"], state["mastery"])

    def test_transfer_maturity_uses_capability_dimensions_not_task_type(self):
        result = reduce_learning_state(
            {},
            {
                "schema_version": 2,
                "learning_targets": [
                    {"target_id": "security:dac-mac", "prerequisites": []}
                ],
                "assessment_capabilities": {
                    "scenario_application": {"affected_dimensions": ["transfer"]}
                },
            },
            [
                {
                    "schema_version": 2,
                    "observation_id": "scenario-1",
                    "target_id": "security:dac-mac",
                    "capability_id": "scenario_application",
                    "task_type": "scenario",
                    "outcome": "correct",
                    "assistance": {"levels_revealed": []},
                }
            ],
            {},
        )
        maturity = result["targets"]["security:dac-mac"]["evidence_maturity"]
        self.assertEqual(1, maturity["transferred"]["count"])
        self.assertEqual(0, maturity["retained"]["count"])

    def test_retention_maturity_uses_capability_requirements_independently(self):
        result = reduce_learning_state(
            {},
            {
                "schema_version": 2,
                "learning_targets": [
                    {"target_id": "history:dates", "prerequisites": []}
                ],
                "assessment_capabilities": {
                    "retrieval_check": {
                        "affected_dimensions": ["recall"],
                        "evidence_requirements": ["delayed_recall"],
                    }
                },
            },
            [
                {
                    "schema_version": 2,
                    "observation_id": "retention-1",
                    "target_id": "history:dates",
                    "capability_id": "retrieval_check",
                    "task_type": "quiz",
                    "outcome": "correct",
                    "assistance": {"levels_revealed": []},
                }
            ],
            {},
        )
        maturity = result["targets"]["history:dates"]["evidence_maturity"]
        self.assertEqual(1, maturity["retained"]["count"])
        self.assertEqual(0, maturity["transferred"]["count"])


if __name__ == "__main__":
    unittest.main()
