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

    def test_reattempt_after_exposure_is_recorded_as_post_exposure(self):
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
            correct = {
                "schema_version": 2, "observation_id": "after-exposure-a1", "target_id": "t1",
                "task_id": "a1", "capability_id": "calculation", "task_type": "calculation",
                "outcome": "correct", "assistance": {"levels_revealed": []}, "error_tags": [],
                "diagnostic_confidence": "high", "source_refs": [], "assessment_id": "a1",
            }
            proposal_path = root / "correct.json"
            proposal_path.write_text(json.dumps(correct), encoding="utf-8")
            recorded = self._call(root, "record-observation", str(proposal_path))
            self.assertEqual("post_exposure_attempt", recorded["event"]["assessment_integrity"])

    def test_reveal_after_attempt_records_exposure(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._freeze_a1(root)
            self._record(root, "incorrect", "first-a1")
            revealed = self._call(root, "reveal-answer", "a1")
            self.assertEqual("answer_revealed", revealed["status"])
            self.assertEqual(["incorrect", "solution_seen"], self._outcomes(root))
            exposure = StudyStore.for_exam_prep(root).read_complete_observations()[-1]
            self.assertEqual("answer revealed after an attempt", exposure["explicit_exposure_reason"])
            recorded = self._record(root, "correct", "retry-a1")
            self.assertEqual("post_exposure_attempt", recorded["event"]["assessment_integrity"])

    def test_reveal_with_exposure_flag_after_attempt_records_exposure(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._freeze_a1(root)
            self._record(root, "incorrect", "first-a1")
            revealed = self._call(root, "reveal-answer", "a1", "--exposure")
            self.assertEqual("answer_revealed", revealed["status"])
            self.assertEqual(["incorrect", "solution_seen"], self._outcomes(root))
            exposure = StudyStore.for_exam_prep(root).read_complete_observations()[-1]
            self.assertEqual("user requested --exposure", exposure["explicit_exposure_reason"])
            recorded = self._record(root, "correct", "retry-a1")
            self.assertEqual("post_exposure_attempt", recorded["event"]["assessment_integrity"])

    def test_correct_attempt_after_exposure_does_not_finish_the_task(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._freeze_a1(root)
            self._call(root, "reveal-answer", "a1", "--exposure")
            recorded = self._record(root, "correct", "after-exposure-a1")
            self.assertEqual("post_exposure_attempt", recorded["event"]["assessment_integrity"])
            self.assertFalse(recorded["session"]["current_task_done"])
            self.assertNotEqual(
                "choose the next budget-fitting activity",
                recorded["session"]["pending_action"],
            )

    def _freeze_a1(self, root: Path) -> None:
        self._call(root, "init")
        assessment = {
            "assessment_id": "a1", "target_id": "t1", "capability_id": "calculation",
            "prompt": "Compute x", "rubric": {}, "expected_evidence": [], "source_refs": [],
            "difficulty": 0.5, "question_version": 1, "rubric_version": 1,
        }
        assessment_path = root / "assessment.json"
        assessment_path.write_text(json.dumps(assessment), encoding="utf-8")
        self._call(root, "freeze-assessment", str(assessment_path))

    def _record(self, root: Path, outcome: str, observation_id: str) -> dict:
        proposal = {
            "schema_version": 2, "observation_id": observation_id, "target_id": "t1",
            "task_id": "a1", "capability_id": "calculation", "task_type": "calculation",
            "outcome": outcome, "assistance": {"levels_revealed": []}, "error_tags": [],
            "diagnostic_confidence": "high", "source_refs": [], "assessment_id": "a1",
        }
        proposal_path = root / f"{observation_id}.json"
        proposal_path.write_text(json.dumps(proposal), encoding="utf-8")
        return self._call(root, "record-observation", str(proposal_path))

    @staticmethod
    def _outcomes(root: Path) -> list[str]:
        return [e["outcome"] for e in StudyStore.for_exam_prep(root).read_complete_observations()]

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
