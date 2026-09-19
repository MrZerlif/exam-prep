import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_adapters.local_materials.questions import ExtractedQuestion
from exam_prep_lib.assessment_draft import DraftValidationError, build_draft, finalize_draft
from exam_prep_lib.schema_validation import load_schema, validate_document


def question(question_id: str, source_id: str, kind: str = "homework") -> ExtractedQuestion:
    return ExtractedQuestion(
        question_id, "1", "Compute x", "x=1", kind, (), 2, 1,
        {"source_id": source_id, "locator": source_id}, issues=()
    )


class AssessmentDraftTests(unittest.TestCase):
    def test_draft_accepts_null_target_and_records_origin(self):
        draft = build_draft((question("q1", "hw.md"),))
        validate_document(draft, load_schema("assessment-draft.schema.json"))
        self.assertIsNone(draft["assessments"][0]["target_id"])
        self.assertEqual("extracted", draft["assessments"][0]["origin"])

    def test_finalize_rejects_incomplete_target_map(self):
        draft = build_draft((question("q1", "hw.md"), question("q2", "hw.md")))
        with self.assertRaises(DraftValidationError):
            finalize_draft(draft, {"q1": "target-a"})

    def test_latest_exam_source_is_held_out_as_a_whole(self):
        draft = build_draft((question("q1", "exam_2024.pdf", "exam"), question("q2", "exam_2025.pdf", "exam")))
        purposes = {entry["question_id"]: entry["purpose"] for entry in draft["assessments"]}
        self.assertEqual("practice", purposes["q1"])
        self.assertEqual("held_out", purposes["q2"])

    def test_explicit_reserve_for_mock_moves_whole_source(self):
        draft = build_draft((question("q1", "exam_2024.pdf", "exam"), question("q2", "exam_2025.pdf", "exam")), reserve_for_mock=("exam_2024.pdf",))
        self.assertEqual("held_out", next(item for item in draft["assessments"] if item["question_id"] == "q1")["purpose"])

    def test_holdout_ratio_controls_deterministic_exam_source_split(self):
        questions = tuple(
            question(f"q{i}", f"exam_202{i}.pdf", "exam")
            for i in range(1, 5)
        )
        draft = build_draft(questions, holdout_ratio=0.5)
        held_out = {
            item["question_id"]
            for item in draft["assessments"]
            if item["purpose"] == "held_out"
        }
        self.assertEqual({"q3", "q4"}, held_out)
        no_holdout = build_draft(questions, holdout_ratio=0)
        self.assertTrue(all(item["purpose"] == "practice" for item in no_holdout["assessments"]))


if __name__ == "__main__":
    unittest.main()
