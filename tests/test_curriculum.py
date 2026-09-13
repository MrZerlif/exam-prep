import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.curriculum import (  # noqa: E402
    CurriculumValidationError,
    apply_curriculum_proposal,
    build_syllabus_from_proposal,
    validate_curriculum_proposal,
)
from exam_prep_lib.storage import StudyStore  # noqa: E402


def valid_proposal():
    return {
        "schema_version": 1,
        "proposal_id": "proposal-1",
        "source_refs": [
            {
                "source_id": "teacher:week-1",
                "authority": "teacher_material",
                "locator": "page 2",
            }
        ],
        "learning_targets": [
            {
                "target_id": "limits",
                "title": "Limits",
                "prerequisites": [],
                "capability_ids": ["independent_problem"],
                "exam_question_ids": ["q1"],
                "source_refs": ["teacher:week-1"],
            },
            {
                "target_id": "derivatives",
                "title": "Derivatives",
                "prerequisites": ["limits"],
                "capability_ids": ["independent_problem"],
                "exam_question_ids": ["q2"],
                "source_refs": ["teacher:week-1"],
            },
        ],
        "assessment_capabilities": [],
        "exam_questions": [
            {
                "question_id": "q1",
                "target_ids": ["limits"],
                "capability_ids": ["independent_problem"],
            },
            {
                "question_id": "q2",
                "target_ids": ["derivatives"],
                "capability_ids": ["independent_problem"],
            },
        ],
    }


class CurriculumTests(unittest.TestCase):
    def assert_invalid(self, proposal, fragment):
        with self.assertRaises(CurriculumValidationError) as caught:
            validate_curriculum_proposal(proposal)
        self.assertTrue(any(fragment in issue for issue in caught.exception.issues))

    def test_valid_target_graph_and_exam_mapping_builds_syllabus(self):
        proposal = valid_proposal()
        validated = validate_curriculum_proposal(proposal)
        syllabus = build_syllabus_from_proposal(validated)
        self.assertEqual(2, len(syllabus["learning_targets"]))
        self.assertEqual(["limits"], syllabus["concepts"]["derivatives"]["prerequisites"])
        self.assertEqual(["q2"], syllabus["concepts"]["derivatives"]["exam_question_ids"])
        self.assertTrue(syllabus["source_coverage"]["targets_without_sources"] == [])

    def test_missing_prerequisite_is_rejected(self):
        proposal = valid_proposal()
        proposal["learning_targets"][1]["prerequisites"] = ["missing"]
        self.assert_invalid(proposal, "unknown prerequisite")

    def test_prerequisite_cycle_is_rejected(self):
        proposal = valid_proposal()
        proposal["learning_targets"][0]["prerequisites"] = ["derivatives"]
        self.assert_invalid(proposal, "cycle")

    def test_unknown_source_ref_is_rejected(self):
        proposal = valid_proposal()
        proposal["learning_targets"][0]["source_refs"] = ["missing:source"]
        self.assert_invalid(proposal, "unknown source")

    def test_open_capability_id_is_rejected_until_descriptor_exists(self):
        proposal = valid_proposal()
        proposal["learning_targets"][0]["capability_ids"] = ["proof:short"]
        self.assert_invalid(proposal, "unknown capability")

        proposal["assessment_capabilities"] = [
            {
                "capability_id": "proof:short",
                "affected_dimensions": ["conceptual"],
                "response_type": "free_text",
                "review_kind": "proof",
                "evidence_requirements": ["independent"],
            }
        ]
        validate_curriculum_proposal(proposal)

    def test_exam_question_mapping_and_coverage_gaps_are_diagnostics(self):
        proposal = valid_proposal()
        proposal["exam_questions"][0]["target_ids"] = ["missing"]
        self.assert_invalid(proposal, "exam question")

        proposal = valid_proposal()
        proposal["learning_targets"][0]["source_refs"] = []
        self.assert_invalid(proposal, "coverage")

    def test_curriculum_updates_are_incremental_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StudyStore.for_exam_prep(Path(tmp))
            first = apply_curriculum_proposal(store, valid_proposal())
            repeat = apply_curriculum_proposal(store, valid_proposal())
            self.assertTrue(first.changed)
            self.assertFalse(repeat.changed)

            proposal = valid_proposal()
            proposal["proposal_id"] = "proposal-2"
            proposal["learning_targets"].append(
                {
                    "target_id": "integrals",
                    "title": "Integrals",
                    "prerequisites": ["derivatives"],
                    "capability_ids": ["independent_problem"],
                    "exam_question_ids": [],
                    "source_refs": ["teacher:week-1"],
                }
            )
            updated = apply_curriculum_proposal(store, proposal)
            self.assertTrue(updated.changed)
            self.assertEqual(
                3,
                len(updated.syllabus["learning_targets"]),
            )
            repeat_updated = apply_curriculum_proposal(store, proposal)
            self.assertFalse(repeat_updated.changed)


if __name__ == "__main__":
    unittest.main()
