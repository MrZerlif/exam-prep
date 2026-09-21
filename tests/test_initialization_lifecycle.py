import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, "skill/exam-prep/scripts")

from exam_prep import (
    PRE_INIT_WORKSPACE_COMMANDS,
    WORKSPACE_INDEPENDENT_COMMANDS,
    WORKSPACE_REQUIRES_INIT_COMMANDS,
    _parser,
    main,
)  # noqa: E402


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

        # `{}` is an invalid proposal, and an invalid proposal now exits 1 so
        # that a caller checking only the exit code cannot walk into
        # apply-curriculum. What this test is actually about is unchanged:
        # validating before init must not create the workspace.
        self.assertEqual(1, code)
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



    @staticmethod
    def snapshot_tree(root):
        return {
            path.relative_to(root): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }

    def test_workspace_commands_before_init_are_read_only_and_init_still_works(self):
        command_cases = (
            ("ingest-materials", lambda root, materials, lexicon: [
                "ingest-materials", str(materials), "--mode", "full",
            ]),
            ("hydrate-source", lambda root, materials, lexicon: [
                "hydrate-source", "lecture.md#p1", "--materials-dir", str(materials),
            ]),
            ("extract-figures", lambda root, materials, lexicon: [
                "extract-figures", str(materials),
            ]),
            ("figure", lambda root, materials, lexicon: [
                "figure", "lecture.pdf", "1", "--materials-dir", str(materials),
            ]),
            ("apply-lexicon", lambda root, materials, lexicon: [
                "apply-lexicon", str(lexicon),
            ]),
        )
        for name, build_args in command_cases:
            with self.subTest(command=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                materials = root / "materials"
                materials.mkdir()
                (materials / "lecture.md").write_text("Topic\\nDefinition", encoding="utf-8")
                (materials / "lecture.pdf").write_bytes(b"not a real PDF")
                lexicon = root / "lexicon.json"
                lexicon.write_text(json.dumps({"language": "ru", "entries": {}}), encoding="utf-8")
                before = self.snapshot_tree(root)

                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = main(["--workspace", str(root), *build_args(root, materials, lexicon)])
                result = json.loads(output.getvalue())

                self.assertEqual(0, code)
                self.assertEqual("workspace_not_initialized", result["status"])
                self.assertEqual(before, self.snapshot_tree(root))
                self.assertFalse((root / ".exam-prep").exists())

                init_code, init_result = self.invoke_at(root, "init")
                self.assertEqual(0, init_code)
                self.assertEqual("initialized", init_result["status"])

    def test_every_parser_subcommand_has_exactly_one_lifecycle_category(self):
        parser = _parser()
        commands = set(parser._subparsers._group_actions[0].choices)
        categories = (
            PRE_INIT_WORKSPACE_COMMANDS,
            WORKSPACE_INDEPENDENT_COMMANDS,
            WORKSPACE_REQUIRES_INIT_COMMANDS,
        )
        self.assertEqual(commands, set().union(*categories))
        self.assertTrue(all(len([category for category in categories if command in category]) == 1 for command in commands))

    def test_standalone_commands_are_not_blocked_before_workspace_init(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            materials = root / "materials"
            materials.mkdir()
            (materials / "hw2.md").write_text("\u0417\u0430\u0434\u0430\u0447\u0430 1\nCompute x", encoding="utf-8")
            (materials / "hw2_resheniya.md").write_text("\u0420\u0435\u0448\u0435\u043d\u0438\u0435 1\nx=2", encoding="utf-8")
            draft = root / "draft.json"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(["--workspace", str(root), "draft-assessments", str(materials), "--out", str(draft)])
            self.assertEqual(0, code)
            self.assertNotEqual("workspace_not_initialized", json.loads(output.getvalue())["status"])
            target_map = root / "targets.json"
            draft_data = json.loads(draft.read_text(encoding="utf-8"))
            target_map.write_text(json.dumps({draft_data["assessments"][0]["question_id"]: "target-x"}), encoding="utf-8")
            final = root / "final.json"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main([
                    "--workspace", str(root), "finalize-assessment-draft", str(draft),
                    "--target-map", str(target_map), "--out", str(final),
                ])
            self.assertEqual(0, code)
            self.assertNotEqual("workspace_not_initialized", json.loads(output.getvalue())["status"])

    @staticmethod
    def invoke_at(root, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--workspace", str(root), *args])
        return code, json.loads(output.getvalue()) if output.getvalue() else None

if __name__ == "__main__":
    unittest.main()
