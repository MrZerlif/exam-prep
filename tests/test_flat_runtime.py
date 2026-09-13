import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import os

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep import LegacyStateDetected, main  # noqa: E402
from exam_prep_lib.storage import StudyStore  # noqa: E402


class FlatRuntimeTests(unittest.TestCase):
    def test_exam_prep_store_uses_flat_runtime_without_touching_legacy_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = StudyStore.for_exam_prep(root)
            store.initialize()
            self.assertTrue((root / ".exam-prep" / "observations.jsonl").exists())
            self.assertFalse((root / "state" / "observations.jsonl").exists())

    def test_cli_without_explicit_workspace_uses_exam_prep_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict(os.environ, {"EXAM_PREP_WORKSPACE": str(root)}, clear=False):
                self.assertEqual(0, main(["init"]))
            self.assertTrue((root / ".exam-prep" / "course.json").exists())
            self.assertFalse((root / "state" / "course.json").exists())

    def test_cli_with_explicit_workspace_uses_exam_prep_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(0, main(["--workspace", str(root), "init"]))
            self.assertTrue((root / ".exam-prep" / "course.json").exists())
            self.assertFalse((root / "state" / "course.json").exists())

    def test_deprecated_workspace_environment_still_uses_exam_prep_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict(
                os.environ,
                {"MATH_STUDY_WORKSPACE": str(root)},
                clear=False,
            ):
                self.assertEqual(0, main(["init"]))
            self.assertTrue((root / ".exam-prep" / "course.json").exists())
            self.assertFalse((root / "state" / "course.json").exists())

    def test_legacy_state_requires_explicit_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = root / "state"
            legacy.mkdir()
            (legacy / "course.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(LegacyStateDetected):
                main(["--workspace", str(root), "status"])
            self.assertFalse((root / ".exam-prep").exists())


if __name__ == "__main__":
    unittest.main()
