import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, "skill/exam-prep/scripts")

from exam_prep import main  # noqa: E402


SYLLABUS = {
    "schema_version": 2,
    "course_id": "evaluation-course",
    "source_refs": [],
    "learning_targets": [
        {
            "target_id": "limits",
            "title": "Limits",
            "prerequisites": [],
            "capability_ids": ["independent_problem"],
        }
    ],
    "assessment_capabilities": {},
    "exam_questions": [],
}


def proposal(observation_id, *, score=None):
    result = {
        "schema_version": 2,
        "observation_id": observation_id,
        "target_id": "limits",
        "task_id": observation_id,
        "capability_id": "independent_problem",
        "task_type": "independent_problem",
        "outcome": "correct",
        "assistance": {
            "requested": False,
            "levels_revealed": [],
            "scaffold_types": [],
            "partial_transformation_shown": False,
            "full_solution_viewed": False,
        },
        "error_tags": [],
        "diagnostic_confidence": "high",
        "learner_self_confidence": "high",
        "source_refs": [],
    }
    if score is not None:
        result["assessment_result"] = {"score": score, "max_score": 10}
    return result


class EvaluationSurfacedTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.syllabus_path = self.root / "syllabus.json"
        self.syllabus_path.write_text(json.dumps(SYLLABUS), encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--workspace", str(self.root), *args])
        return code, json.loads(output.getvalue())

    def ready(self):
        self.assertEqual(0, self.run_cli("init")[0])
        self.assertEqual(0, self.run_cli("load-syllabus", str(self.syllabus_path))[0])
        self.assertEqual(0, self.run_cli("start")[0])

    def record(self, item):
        path = self.root / f"{item['observation_id']}.json"
        path.write_text(json.dumps(item), encoding="utf-8")
        code, payload = self.run_cli("record-observation", str(path))
        self.assertEqual(0, code, payload)
        return payload

    def test_session_end_persists_evaluation_and_status_surfaces_calibration(self):
        self.ready()
        self.record(proposal("obs-no-score"))
        code, ended = self.run_cli("end-session")
        self.assertEqual(0, code, ended)
        evaluation = ended["summary"]["evaluation"]
        self.assertEqual(0, evaluation["active_study_seconds"])
        self.assertIsNone(evaluation["confidence_calibration"]["mean_absolute_error"])
        self.assertEqual(0, evaluation["confidence_calibration"]["sample_count"])

        stored = [
            json.loads(line)
            for line in (self.root / ".exam-prep" / "sessions.jsonl").read_text().splitlines()
        ]
        self.assertEqual(evaluation, stored[-1]["evaluation"])

        code, full = self.run_cli("status")
        self.assertEqual(0, code)
        self.assertIn("course_wide_calibration", full)
        self.assertEqual(0, full["course_wide_calibration"]["sample_count"])
        code, compact = self.run_cli("status", "--compact")
        self.assertEqual(0, code)
        self.assertNotIn("course_wide_calibration", compact)

    def test_scored_assessment_increases_calibration_sample_count(self):
        self.ready()
        self.record(proposal("obs-scored", score=8))
        code, ended = self.run_cli("end-session")
        self.assertEqual(0, code, ended)
        self.assertEqual(1, ended["summary"]["evaluation"]["confidence_calibration"]["sample_count"])

    def test_repeated_end_session_in_idle_returns_null_summary(self):
        self.ready()
        self.assertEqual(0, self.run_cli("end-session")[0])
        code, payload = self.run_cli("end-session")
        self.assertEqual(0, code, payload)
        self.assertIsNone(payload["summary"])


if __name__ == "__main__":
    unittest.main()
