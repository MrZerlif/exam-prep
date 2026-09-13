import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXAM_PREP = ROOT / "skill" / "exam-prep"


class ExamPrepPackageTests(unittest.TestCase):
    def test_exam_prep_package_is_self_contained_and_uses_new_entrypoint(self):
        self.assertTrue((EXAM_PREP / "scripts" / "exam_prep.py").exists())
        self.assertTrue((EXAM_PREP / "scripts" / "exam_prep_lib").is_dir())
        skill_text = (EXAM_PREP / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("exam-prep", skill_text)
        self.assertIn("NotebookLM MCP", skill_text)
        self.assertIn("attempt-first", skill_text)

    def test_exam_prep_activation_is_subject_agnostic(self):
        skill_text = (EXAM_PREP / "SKILL.md").read_text(encoding="utf-8").casefold()
        self.assertIn("any academic or technical subject", skill_text)
        self.assertIn("learning targets", skill_text)
        self.assertNotIn("mathematical analysis study", skill_text)

    def test_migration_flag_names_the_legacy_math_study_source(self):
        sys.path.insert(0, str(EXAM_PREP / "scripts"))
        from exam_prep import _parser

        args = _parser().parse_args(["migrate", "--from-math-study", "legacy-workspace"])
        self.assertEqual("legacy-workspace", args.from_math_study)

    def test_exam_prep_entrypoint_runs_without_repository_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "install"
            import shutil

            shutil.copytree(EXAM_PREP, install)
            completed = subprocess.run(
                [sys.executable, "scripts/exam_prep.py", "init"],
                cwd=install,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertTrue((install / ".exam-prep" / "course.json").exists())


if __name__ == "__main__":
    unittest.main()
