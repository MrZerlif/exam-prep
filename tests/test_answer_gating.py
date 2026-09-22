import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep import main
from exam_prep_lib.storage import StudyStore


class AnswerGatingTests(unittest.TestCase):
    def test_answer_assets_require_attempt_or_explicit_exposure(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._call(root, "init")
            assessment = {
                "assessment_id": "a1", "target_id": "t1", "capability_id": "calculation",
                "prompt": "Compute x", "rubric": {}, "expected_evidence": [], "source_refs": [],
                "difficulty": 0.5, "question_version": 1, "rubric_version": 1,
            }
            assessment_path = root / "assessment.json"
            assessment_path.write_text(json.dumps(assessment), encoding="utf-8")
            self._call(root, "freeze-assessment", str(assessment_path))
            asset_dir = root / ".exam-prep" / "assets" / "answer"
            asset_dir.mkdir(parents=True)
            asset = asset_dir / "deadbeef.png"
            asset.write_bytes(b"png")
            (root / ".exam-prep" / "assets" / "index.json").write_text(
                json.dumps({"assets": [{"asset_id": "deadbeef", "path": str(asset), "role": "answer", "assessment_id": "a1"}]}),
                encoding="utf-8",
            )
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["--workspace", str(root), "reveal-answer", "a1"])
            self.assertEqual(1, code)
            self.assertNotIn("assets/answer/", output.getvalue().replace("\\", "/"))
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["--workspace", str(root), "reveal-answer", "a1", "--exposure"])
            self.assertEqual(0, code)
            self.assertIn("deadbeef.png", output.getvalue())
            event = StudyStore.for_exam_prep(root).read_complete_observations()[-1]
            self.assertEqual("solution_seen", event["outcome"])

    def test_skipped_outcome_does_not_unlock_answer_assets(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._call(root, "init")
            assessment = {
                "assessment_id": "a1", "target_id": "t1", "capability_id": "calculation",
                "prompt": "Compute x", "rubric": {}, "expected_evidence": [], "source_refs": [],
                "difficulty": 0.5, "question_version": 1, "rubric_version": 1,
            }
            assessment_path = root / "assessment.json"
            assessment_path.write_text(json.dumps(assessment), encoding="utf-8")
            self._call(root, "freeze-assessment", str(assessment_path))
            skipped = {
                "schema_version": 2, "observation_id": "skip-a1", "target_id": "t1",
                "task_id": "a1", "capability_id": "calculation", "task_type": "calculation",
                "outcome": "skipped", "assistance": {"levels_revealed": []}, "error_tags": [],
                "diagnostic_confidence": "medium", "source_refs": [], "assessment_id": "a1",
            }
            proposal_path = root / "skipped.json"
            proposal_path.write_text(json.dumps(skipped), encoding="utf-8")
            self._call(root, "record-observation", str(proposal_path))

            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["--workspace", str(root), "reveal-answer", "a1"])
            self.assertEqual(1, code)
            self.assertEqual("attempt_required", json.loads(output.getvalue())["status"])

            self._call(root, "reveal-answer", "a1", "--exposure")
            event = StudyStore.for_exam_prep(root).read_complete_observations()[-1]
            self.assertEqual("solution_seen", event["outcome"])

    def test_answer_stays_released_after_recorded_exposure(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._call(root, "init")
            assessment = {
                "assessment_id": "a1", "target_id": "t1", "capability_id": "calculation",
                "prompt": "Compute x", "rubric": {}, "expected_evidence": [], "source_refs": [],
                "difficulty": 0.5, "question_version": 1, "rubric_version": 1,
            }
            assessment_path = root / "assessment.json"
            assessment_path.write_text(json.dumps(assessment), encoding="utf-8")
            self._call(root, "freeze-assessment", str(assessment_path))
            self._call(root, "reveal-answer", "a1", "--exposure")
            again = self._call(root, "reveal-answer", "a1")
            self.assertEqual("answer_revealed", again["status"])
            outcomes = [e["outcome"] for e in StudyStore.for_exam_prep(root).read_complete_observations()]
            self.assertEqual(["solution_seen"], outcomes)

    @staticmethod
    def _call(root: Path, *args: str) -> dict:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--workspace", str(root), *args])
        if code:
            raise AssertionError(output.getvalue())
        return json.loads(output.getvalue())


if __name__ == "__main__":
    unittest.main()
