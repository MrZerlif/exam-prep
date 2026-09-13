import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "math-study" / "scripts"))

from math_study_lib.workspace import resolve_workspace, runtime_paths


class WorkspaceResolutionTests(unittest.TestCase):
    def test_explicit_workspace_has_highest_precedence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            explicit = root / "explicit"
            resolved = resolve_workspace(
                str(explicit),
                environment={
                    "EXAM_PREP_WORKSPACE": str(root / "env"),
                    "WORKSPACE_ROOT": str(root / "project"),
                },
                git_root=root / "git",
                cwd=root / "cwd",
            )
            self.assertEqual(explicit.resolve(), resolved)

    def test_environment_project_root_precedes_git_root_and_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_root = root / "env"
            resolved = resolve_workspace(
                None,
                environment={"EXAM_PREP_WORKSPACE": str(env_root)},
                git_root=root / "git",
                cwd=root / "cwd",
            )
            self.assertEqual(env_root.resolve(), resolved)

    def test_git_root_precedes_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resolved = resolve_workspace(
                None,
                environment={},
                git_root=root / "git",
                cwd=root / "cwd",
            )
            self.assertEqual((root / "git").resolve(), resolved)

    def test_runtime_paths_use_flat_exam_prep_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = runtime_paths(Path(tmp))
            self.assertEqual((Path(tmp) / ".exam-prep").resolve(), paths.root)
            self.assertEqual(paths.root / "course.json", paths.course)
            self.assertEqual(paths.root / "observations.jsonl", paths.observations)


if __name__ == "__main__":
    unittest.main()
