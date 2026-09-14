import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, "skill/exam-prep/scripts")

from exam_prep import main  # noqa: E402


class InitializationLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def invoke(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--workspace", str(self.root), *args])
        return code, json.loads(output.getvalue()) if output.getvalue() else None

    def test_status_before_init_is_read_only(self):
        code, result = self.invoke("status")
        self.assertEqual(0, code)
        self.assertEqual("uninitialized", result["status"])
        self.assertFalse(result["initialized"])
        self.assertFalse((self.root / ".exam-prep").exists())

    def test_second_init_preserves_canonical_files(self):
        code, _ = self.invoke("init")
        self.assertEqual(0, code)
        course_path = self.root / ".exam-prep" / "course.json"
        syllabus_path = self.root / ".exam-prep" / "syllabus.json"
        course = json.loads(course_path.read_text(encoding="utf-8"))
        course["title"] = "Sentinel title"
        course_path.write_text(json.dumps(course), encoding="utf-8")
        before_course = course_path.read_bytes()
        before_syllabus = syllabus_path.read_bytes()

        code, result = self.invoke("init")

        self.assertEqual(0, code)
        self.assertEqual("already_initialized", result["status"])
        self.assertEqual(before_course, course_path.read_bytes())
        self.assertEqual(before_syllabus, syllabus_path.read_bytes())

    def test_partial_canonical_state_is_reported_without_overwrite(self):
        state = self.root / ".exam-prep"
        state.mkdir(parents=True)
        (state / "course.json").write_text("{}", encoding="utf-8")
        code, result = self.invoke("status")
        self.assertEqual(0, code)
        self.assertEqual("incomplete_workspace", result["status"])
        self.assertFalse(result["initialized"])
        self.assertEqual(["syllabus.json"], result["missing_files"])

    def test_stateful_command_before_init_is_structured(self):
        code, result = self.invoke("start")
        self.assertEqual(0, code)
        self.assertEqual("workspace_not_initialized", result["status"])
        self.assertFalse((self.root / ".exam-prep").exists())

    def test_pre_init_validate_curriculum_is_read_only(self):
        proposal_path = self.root / "proposal.json"
        proposal_path.write_text("{}", encoding="utf-8")

        code, _ = self.invoke("validate-curriculum", str(proposal_path))

        self.assertEqual(0, code)
        self.assertFalse((self.root / ".exam-prep").exists())

    def test_pre_init_apply_curriculum_is_explicitly_rejected_without_state_change(self):
        proposal_path = self.root / "proposal.json"
        proposal_path.write_text("{}", encoding="utf-8")
        before_proposal = proposal_path.read_bytes()

        code, result = self.invoke("apply-curriculum", str(proposal_path))

        self.assertEqual(0, code)
        self.assertEqual("workspace_not_initialized", result["status"])
        self.assertFalse(result["initialized"])
        self.assertEqual(["course.json", "syllabus.json"], result["missing_files"])
        self.assertFalse((self.root / ".exam-prep").exists())
        self.assertEqual(before_proposal, proposal_path.read_bytes())

    def test_validate_empty_workspace_reports_one_initialization_error(self):
        code, result = self.invoke("validate")
        self.assertEqual(1, code)
        self.assertEqual("issues_found", result["status"])
        self.assertEqual(1, result["error_count"])
        self.assertEqual("workspace_initialized", result["checks"][0]["name"])

    def test_validate_incomplete_workspace_checks_existing_logs_without_suggesting_init(self):
        state = self.root / ".exam-prep"
        state.mkdir(parents=True)
        (state / "observations.jsonl").write_text("{}\n", encoding="utf-8")

        code, result = self.invoke("validate")

        self.assertEqual(1, code)
        checks = {item["name"]: item for item in result["checks"]}
        self.assertEqual("error", checks["course_json_readable"]["status"])
        self.assertEqual("error", checks["syllabus_json_readable"]["status"])
        self.assertIn("observations_jsonl_readable", checks)
        self.assertNotIn("workspace_initialized", checks)
        self.assertNotIn("run init", " ".join(str(item.get("detail")) for item in result["checks"]))



if __name__ == "__main__":
    unittest.main()
