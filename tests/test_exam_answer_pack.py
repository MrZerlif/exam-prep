import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "math-study" / "scripts"))

from math_study_lib.assessment import FrozenAssessment  # noqa: E402
from math_study_lib.answer_pack import ExamAnswerPack, build_exam_answer_pack  # noqa: E402


class ExamAnswerPackTests(unittest.TestCase):
    def test_pack_is_assessment_bound_and_preserves_provenance(self):
        assessment = FrozenAssessment.from_mapping(
            {
                "assessment_id": "a-1",
                "target_id": "physics:newton-2",
                "capability_id": "exam_problem",
                "prompt": "Find acceleration.",
                "rubric": {"units": 1, "method": 1},
                "expected_evidence": ["equation", "units"],
                "source_refs": [
                    {
                        "source_id": "physics:syllabus",
                        "authority": "teacher_material",
                        "locator": "p. 8",
                    }
                ],
                "difficulty": 0.7,
                "question_version": 2,
                "rubric_version": 1,
            }
        )
        pack = build_exam_answer_pack(
            assessment,
            learner_response="a = F / m",
            verification={"status": "passed"},
        )
        self.assertEqual("a-1", pack.assessment_id)
        self.assertEqual(assessment.spec_hash, pack.assessment_spec_hash)
        self.assertEqual("physics:syllabus", pack.source_refs[0]["source_id"])
        self.assertEqual("passed", pack.verification["status"])
        self.assertTrue(pack.pack_hash)

    def test_pack_hash_is_stable_and_tampering_is_rejected(self):
        assessment = FrozenAssessment.from_mapping(
            {
                "assessment_id": "a-2",
                "target_id": "algebra:linear",
                "capability_id": "independent_problem",
                "prompt": "Solve x + 1 = 2.",
                "rubric": {"correct": 1},
                "expected_evidence": ["answer"],
                "source_refs": [],
                "difficulty": 0.2,
                "question_version": 1,
                "rubric_version": 1,
            }
        )
        pack = build_exam_answer_pack(assessment, learner_response="x = 1")
        same = ExamAnswerPack.from_mapping(pack.to_mapping())
        self.assertEqual(pack.pack_hash, same.pack_hash)
        with self.assertRaises(ValueError):
            ExamAnswerPack.from_mapping(
                {**pack.to_mapping(), "pack_hash": pack.pack_hash[:-1] + "0"}
            )


if __name__ == "__main__":
    unittest.main()
