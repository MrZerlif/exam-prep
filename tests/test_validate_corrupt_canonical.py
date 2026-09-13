"""Regression tests: `validate` must diagnose broken canonical/derived JSON
as a structured report, not die with a generic top-level JSON parse error
before it even reaches the diagnostic layer."""

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, "skill/exam-prep/scripts")

from exam_prep import main  # noqa: E402
from exam_prep_lib.storage import StudyStore  # noqa: E402


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "skill" / "exam-prep" / "scripts" / "exam_prep.py"
SYLLABUS = ROOT / "skill" / "exam-prep" / "examples" / "example-syllabus.json"


class ValidateCorruptCanonicalTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def cli_ok(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--workspace", str(self.root), *args])
        self.assertEqual(code, 0, output.getvalue())
        return json.loads(output.getvalue())

    def ready(self):
        self.cli_ok("init")
        self.cli_ok("load-syllabus", str(SYLLABUS))
        self.cli_ok("start")

    def run_validate_subprocess(self):
        """Run validate as a real subprocess so we observe the actual exit
        code and stdout, the same way an operator/CI would."""
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--workspace", str(self.root), "validate"],
            capture_output=True,
            text=True,
        )
        return completed

    def test_corrupt_course_json_is_diagnosed_not_a_crash(self):
        self.ready()
        (self.root / ".exam-prep" / "course.json").write_text("{not-json", encoding="utf-8")

        completed = self.run_validate_subprocess()
        self.assertNotEqual(completed.returncode, 0)
        report = json.loads(completed.stdout)
        self.assertFalse(report.get("valid", report.get("status") == "valid"))
        paths = [issue.get("path") for issue in report.get("checks", report.get("issues", []))]
        self.assertTrue(any("course.json" in str(p) for p in paths))

    def test_corrupt_syllabus_json_is_diagnosed_not_a_crash(self):
        self.ready()
        (self.root / ".exam-prep" / "syllabus.json").write_text("[[[", encoding="utf-8")

        completed = self.run_validate_subprocess()
        self.assertNotEqual(completed.returncode, 0)
        report = json.loads(completed.stdout)
        paths = [issue.get("path") for issue in report.get("checks", report.get("issues", []))]
        self.assertTrue(any("syllabus.json" in str(p) for p in paths))

    def test_corrupt_current_pointer_still_yields_a_report(self):
        self.ready()
        (self.root / ".exam-prep" / "current.json").write_text("{broken", encoding="utf-8")

        completed = self.run_validate_subprocess()
        report = json.loads(completed.stdout)
        self.assertIn("checks", report)

    def test_corrupt_derived_snapshot_still_yields_a_report(self):
        self.ready()
        store = StudyStore.for_exam_prep(self.root)
        latest = sorted(store.revisions_path.iterdir())[-1]
        (latest / "concepts.json").write_text("{not-json-either", encoding="utf-8")

        completed = self.run_validate_subprocess()
        report = json.loads(completed.stdout)
        self.assertIn("checks", report)

    def test_corrupt_new_revision_manifest_field_is_diagnosed(self):
        self.ready()
        store = StudyStore.for_exam_prep(self.root)
        latest = sorted(store.revisions_path.iterdir())[-1]
        manifest_path = latest / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["canonical_inputs"]["unexpected"] = "corrupt"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        completed = self.run_validate_subprocess()
        self.assertEqual(completed.returncode, 0)
        report = json.loads(completed.stdout)
        revision_check = next(
            item for item in report["checks"] if item["name"] == "revision_manifests_and_hashes"
        )
        self.assertEqual("warning", revision_check["status"])

    def test_healthy_workspace_validate_still_exits_zero(self):
        self.ready()
        completed = self.run_validate_subprocess()
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
