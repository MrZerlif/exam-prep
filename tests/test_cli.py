import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, "scripts")

from math_study import main  # noqa: E402


SYLLABUS = {
    "schema_version": 1,
    "concepts": {
        "limits": {
            "title": "Limits",
            "prerequisites": [],
            "importance": 0.9,
            "frequency": 0.8,
            "expected_points": 10,
            "estimated_learning_minutes": 25,
        },
        "derivative_rules": {
            "title": "Derivative rules",
            "prerequisites": ["limits"],
            "importance": 0.8,
            "frequency": 0.8,
            "expected_points": 10,
            "estimated_learning_minutes": 30,
        },
    },
}


PROPOSAL = {
    "schema_version": 1,
    "observation_id": "obs-cli-1",
    "concept_id": "limits",
    "task_id": "independent-1",
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
    "learner_self_confidence": "medium",
    "learner_explanation": "Подставил и проверил область определения.",
    "source_refs": ["teacher:worksheet-1"],
}


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.syllabus_path = self.root / "syllabus.json"
        self.syllabus_path.write_text(json.dumps(SYLLABUS), encoding="utf-8")
        self.proposal_path = self.root / "proposal.json"
        self.proposal_path.write_text(json.dumps(PROPOSAL), encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--workspace", str(self.root), *args])
        self.assertEqual(code, 0, output.getvalue())
        return json.loads(output.getvalue())

    def test_init_creates_json_state_workspace(self):
        result = self.run_cli("init")
        self.assertEqual(result["status"], "initialized")
        self.assertTrue((self.root / "state" / "observations.jsonl").exists())
        self.assertTrue((self.root / "state" / "course.json").exists())

    def test_load_syllabus_and_record_observation(self):
        self.run_cli("init")
        self.run_cli("load-syllabus", str(self.syllabus_path))
        self.run_cli("start")
        result = self.run_cli("record-observation", str(self.proposal_path))
        event = result["event"]
        self.assertEqual(event["session_id"], result["session"]["session_id"])
        self.assertIn("recorded_at", event)
        self.assertNotIn("priority_score", result["concepts"]["concepts"]["limits"])

    def test_new_process_status_and_next_are_compact_and_budget_aware(self):
        self.run_cli("init")
        self.run_cli("load-syllabus", str(self.syllabus_path))
        self.run_cli("start")
        self.run_cli("record-observation", str(self.proposal_path))
        status = self.run_cli("status")
        self.assertIn("pending_action", status["session"])
        next_action = self.run_cli("next", "--minutes", "25")
        self.assertEqual(next_action["budget_minutes"], 25)
        self.assertIn("concept_id", next_action)

    def test_rebuild_matches_persisted_concepts(self):
        self.run_cli("init")
        self.run_cli("load-syllabus", str(self.syllabus_path))
        self.run_cli("start")
        self.run_cli("record-observation", str(self.proposal_path))
        rebuilt = self.run_cli("rebuild")
        status = self.run_cli("status")
        self.assertEqual(rebuilt["concepts"], status["concepts"])

    def test_exam_command_enters_stateful_exam_mode(self):
        self.run_cli("init")
        self.run_cli("load-syllabus", str(self.syllabus_path))
        result = self.run_cli("exam", "--minutes", "20")
        self.assertEqual(result["mode"], "exam")
        self.assertEqual(result["budget_minutes"], 20)
        self.assertTrue(result["no_unsolicited_hints"])


if __name__ == "__main__":
    unittest.main()
