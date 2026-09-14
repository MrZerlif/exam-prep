import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "exam-prep" / "scripts"))

from exam_prep import main  # noqa: E402
from exam_prep_lib.assessment import assessment_spec_hash  # noqa: E402
from exam_prep_lib.assessment_integrity import AssessmentIntegrityError  # noqa: E402


class AssessmentCliTests(unittest.TestCase):
    def test_freeze_assessment_persists_a_hashed_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assessment = {
                "assessment_id": "assessment-cli-1",
                "target_id": "algebra:linear",
                "capability_id": "independent_problem",
                "prompt": "Solve 2x = 4.",
                "rubric": {"correct": 1},
                "expected_evidence": ["independent_work"],
                "source_refs": [
                    {
                        "source_id": "teacher:algebra",
                        "authority": "teacher_material",
                        "locator": "page 1",
                    }
                ],
                "difficulty": 0.4,
                "question_version": 1,
                "rubric_version": 1,
            }
            path = root / "assessment.json"
            path.write_text(json.dumps(assessment), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, main(["--workspace", str(root), "init"]))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(["--workspace", str(root), "freeze-assessment", str(path)])
            self.assertEqual(0, code)
            result = json.loads(output.getvalue())
            self.assertEqual("assessment-cli-1", result["assessment_id"])
            stored = json.loads((root / ".exam-prep" / "assessments.jsonl").read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(assessment_spec_hash(stored), stored["spec_hash"])

    def test_mock_assessment_cannot_be_practiced_before_the_real_mock(self):
        # A held-out/mock-purpose assessment must not be attemptable through
        # an ordinary study session - that would leak the exam material
        # ahead of time. It becomes attemptable once the session is
        # actually in the "exam" phase (the `exam` command).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frozen_assessment = {
                "assessment_id": "assessment-mock-1",
                "target_id": "algebra:linear",
                "capability_id": "independent_problem",
                "prompt": "Solve 2x = 4.",
                "rubric": {"correct": 1},
                "expected_evidence": ["independent_work"],
                "source_refs": [
                    {
                        "source_id": "teacher:algebra",
                        "authority": "teacher_material",
                        "locator": "page 1",
                    }
                ],
                "difficulty": 0.4,
                "question_version": 1,
                "rubric_version": 1,
                "purpose": "mock",
            }
            assessment_path = root / "assessment.json"
            assessment_path.write_text(json.dumps(frozen_assessment), encoding="utf-8")
            proposal = {
                "schema_version": 2,
                "observation_id": "mock-attempt-1",
                "target_id": "algebra:linear",
                "task_id": "assessment-task",
                "capability_id": "independent_problem",
                "task_type": "independent_problem",
                "outcome": "correct",
                "assistance": {"levels_revealed": []},
                "error_tags": [],
                "diagnostic_confidence": "high",
                "source_refs": [],
                "assessment_id": "assessment-mock-1",
            }
            proposal_path = root / "proposal.json"
            proposal_path.write_text(json.dumps(proposal), encoding="utf-8")

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, main(["--workspace", str(root), "init"]))
                self.assertEqual(
                    0,
                    main(["--workspace", str(root), "freeze-assessment", str(assessment_path)]),
                )

            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(AssessmentIntegrityError):
                    main(["--workspace", str(root), "record-observation", str(proposal_path)])

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, main(["--workspace", str(root), "exam"]))
                code = main(["--workspace", str(root), "record-observation", str(proposal_path)])
            self.assertEqual(0, code)


if __name__ == "__main__":
    unittest.main()
