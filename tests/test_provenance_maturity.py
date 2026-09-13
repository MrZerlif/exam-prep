import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "math-study" / "scripts"))

from math_study_lib.evidence_maturity import derive_evidence_maturity  # noqa: E402
from math_study_lib.provenance import SourceRef, source_ref_from_mapping  # noqa: E402
from math_study_lib.reducer import reduce_learning_state  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
