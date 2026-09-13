import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.answer_pack import ExamAnswerPack, build_exam_answer_pack  # noqa: E402


def build_kwargs():
    return {
        "pack_id": "pack:categorical-imperative",
        "target_id": "philosophy:categorical-imperative",
        "definition_or_thesis": "Act only on principles you could will as universal law.",
        "key_points": ["universalizability", "rational autonomy"],
        "required_terminology": ["maxim", "categorical imperative"],
        "answer_structure": ["define", "state argument", "address objection"],
        "likely_examiner_follow_ups": ["How does this differ from a hypothetical imperative?"],
        "practice_prompt": "Give a two-minute oral answer and handle one objection.",
        "source_refs": [{"source_id": "lecture:ethics", "authority": "teacher_material", "locator": "section 2"}],
        "coverage": {"teacher_material": True, "official_exam_list": False},
        "confidence": 0.8,
    }


class ExamAnswerPackTests(unittest.TestCase):
    def test_exam_answer_pack_is_generic_and_preserves_provenance(self):
        pack = build_exam_answer_pack(**build_kwargs())
        self.assertEqual("philosophy:categorical-imperative", pack.target_id)
        self.assertIsNone(pack.assessment_id)
        self.assertEqual("lecture:ethics", pack.source_refs[0]["source_id"])
        self.assertTrue(pack.pack_hash)

    def test_pack_hash_is_stable_and_tampering_is_rejected(self):
        pack = build_exam_answer_pack(**build_kwargs())
        same = ExamAnswerPack.from_mapping(pack.to_mapping())
        self.assertEqual(pack.pack_hash, same.pack_hash)
        with self.assertRaises(ValueError):
            ExamAnswerPack.from_mapping(
                {**pack.to_mapping(), "pack_hash": pack.pack_hash[:-1] + "0"}
            )

    def test_assessment_linked_pack_requires_attempt_except_explicit_cram(self):
        from exam_prep_lib.assessment import FrozenAssessment

        assessment = FrozenAssessment.from_mapping(
            {
                "assessment_id": "a-1",
                "target_id": "math:limits",
                "capability_id": "exam_problem",
                "prompt": "Explain the limit.",
                "rubric": {"definition": 1},
                "expected_evidence": ["definition"],
                "source_refs": [],
                "difficulty": 0.5,
                "question_version": 1,
                "rubric_version": 1,
            }
        )
        kwargs = {
            **build_kwargs(),
            "target_id": assessment.target_id,
            "assessment": assessment,
            "definition_or_thesis": "A limit is the value approached by a function.",
            "key_points": ["approach"],
            "practice_prompt": "Reconstruct the definition blind.",
        }
        with self.assertRaisesRegex(ValueError, "independent attempt"):
            build_exam_answer_pack(**kwargs)
        cram = build_exam_answer_pack(**kwargs, exposure_mode="cram")
        self.assertEqual(assessment.assessment_id, cram.assessment_id)
        attempted = build_exam_answer_pack(**kwargs, attempt_made=True)
        self.assertEqual(assessment.spec_hash, attempted.assessment_spec_hash)
        with self.assertRaisesRegex(ValueError, "target_id"):
            build_exam_answer_pack(
                **{**kwargs, "target_id": "math:derivatives"},
                attempt_made=True,
            )


if __name__ == "__main__":
    unittest.main()
