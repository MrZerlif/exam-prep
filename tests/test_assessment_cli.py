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


if __name__ == "__main__":
    unittest.main()
