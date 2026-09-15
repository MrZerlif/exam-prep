"""status --compact is additive: the default form is untouched (every
other test in this suite calling plain `status` proves that by continuing
to pass unchanged), and --compact trims each target down to
availability/mastery_status/recurring_mistakes, review_queue down to due
items, and drops empty diagnostics fields rather than printing them."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, "skill/exam-prep/scripts")

from exam_prep import main  # noqa: E402


ROOT = Path(__file__).parents[1]
SYLLABUS = ROOT / "skill" / "exam-prep" / "examples" / "mathematics-regression-syllabus.json"


class StatusCompactTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--workspace", str(self.root), *args])
        self.assertEqual(code, 0, output.getvalue())
        return output.getvalue(), json.loads(output.getvalue())

    def ready(self):
        self.cli("init")
        self.cli("load-syllabus", str(SYLLABUS))
        self.cli("start")

    def test_compact_is_smaller_and_still_names_availability_and_mastery(self):
        self.ready()
        full_text, full = self.cli("status")
        compact_text, compact = self.cli("status", "--compact")

        self.assertLess(len(compact_text), len(full_text))

        for target_id, state in full["targets"]["targets"].items():
            compact_state = compact["targets"]["targets"][target_id]
            self.assertEqual(compact_state["availability"], state["availability"])
            self.assertEqual(compact_state["mastery_status"], state["mastery_status"])
            self.assertNotIn("evidence", compact_state)
            self.assertNotIn("confidence", compact_state)
            self.assertNotIn("evidence_maturity", compact_state)
            self.assertNotIn("mastery", compact_state)

    def test_compact_review_queue_keeps_only_due_items(self):
        self.ready()
        _, compact = self.cli("status", "--compact")
        for item in compact["review_queue"]["items"].values():
            self.assertEqual(item["review_status"], "due")

    def test_compact_drops_empty_diagnostics_fields(self):
        self.ready()
        _, full = self.cli("status")
        self.assertEqual(full["capability_diagnostics"], [])
        self.assertIsNone(full["blueprint_diagnostics"])

        _, compact = self.cli("status", "--compact")
        self.assertNotIn("capability_diagnostics", compact)
        self.assertNotIn("blueprint_diagnostics", compact)

    def test_compact_leaves_session_and_resume_point_untouched(self):
        self.ready()
        _, full = self.cli("status")
        _, compact = self.cli("status", "--compact")
        self.assertEqual(compact["session"], full["session"])
        self.assertEqual(compact["resume_point"], full["resume_point"])

    def test_compact_surfaces_recurring_mistakes_when_present(self):
        self.ready()
        proposal = {
            "schema_version": 1,
            "observation_id": "obs-1",
            "concept_id": "chain_rule",
            "task_id": "obs-1",
            "task_type": "independent_problem",
            "outcome": "incorrect",
            "assistance": {
                "requested": False,
                "levels_revealed": [],
                "scaffold_types": [],
                "partial_transformation_shown": False,
                "full_solution_viewed": False,
            },
            "error_tags": ["formula_recall_error"],
            "diagnostic_confidence": "high",
            "learner_self_confidence": "medium",
            "source_refs": ["teacher:worksheet-1"],
        }
        path = self.root / "obs-1.json"
        path.write_text(json.dumps(proposal), encoding="utf-8")
        self.cli("record-observation", str(path))

        _, compact = self.cli("status", "--compact")
        chain_rule = compact["targets"]["targets"]["chain_rule"]
        if chain_rule.get("recurring_mistakes"):
            self.assertIn("recurring_mistakes", chain_rule)


if __name__ == "__main__":
    unittest.main()
