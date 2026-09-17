"""Acceptance test: the installed skill package must be self-contained.

Copies ONLY skill/exam-prep/ into a clean temporary directory, with no
access to the repository root (a separate CWD, and a subprocess PYTHONPATH
that does not include the repo), then drives the documented CLI lifecycle.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SKILL_SOURCE = ROOT / "skill" / "exam-prep"
# Inherit the OS environment (Windows needs SystemRoot etc. to start python.exe
# at all) but strip PYTHONPATH so nothing points back at the source repository.
ISOLATED_ENV = {key: value for key, value in os.environ.items() if key.upper() != "PYTHONPATH"}


class StandaloneInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.install_root = Path(self.temp_dir.name) / "exam-prep"
        shutil.copytree(
            SKILL_SOURCE,
            self.install_root,
            ignore=shutil.ignore_patterns("__pycache__"),
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_cli(self, *args):
        completed = subprocess.run(
            [sys.executable, "scripts/exam_prep.py", *args],
            cwd=self.install_root,
            env=ISOLATED_ENV,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            completed.returncode,
            0,
            f"stdout={completed.stdout!r} stderr={completed.stderr!r}",
        )
        return json.loads(completed.stdout)

    def test_standalone_copy_runs_the_documented_lifecycle(self):
        # No repository root on PYTHONPATH/sys.path: env={} above strips it,
        # and cwd is the copied package, not the source repository.
        self.assertFalse((self.install_root / ".git").exists())

        init_result = self.run_cli("init")
        self.assertEqual(init_result["status"], "initialized")

        syllabus_path = self.install_root / "examples" / "example-syllabus.json"
        self.run_cli("load-syllabus", str(syllabus_path))

        status_before = self.run_cli("status")
        self.assertIn("targets", status_before)

        start_result = self.run_cli("start")
        self.assertEqual(start_result["session"]["phase"], "study")

        target_id = next(iter(status_before["targets"]["targets"]))
        proposal = {
            "schema_version": 2,
            "observation_id": "obs-standalone-1",
            "target_id": target_id,
            "capability_id": "independent_problem",
            "task_id": "standalone-1",
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
            "source_refs": ["teacher:standalone-check"],
        }
        proposal_path = self.install_root / "proposal.json"
        proposal_path.write_text(json.dumps(proposal), encoding="utf-8")
        record_result = self.run_cli("record-observation", str(proposal_path))
        self.assertTrue(record_result["appended"])

        end_result = self.run_cli("end-session")
        self.assertEqual(end_result["status"], "session_ended")


    def test_package_readme_says_where_its_test_commands_run(self):
        """The package README is what a person reads *after* copying this
        directory into a skills folder, where `python tests/...` resolves to
        nothing. Naming paths is fine - leaving the reader to discover that
        they belong to the source repository is not. Each referenced path must
        also exist at the repository root, so the commands are real somewhere.
        """
        readme = (self.install_root / "README.md").read_text(encoding="utf-8")
        self.assertRegex(
            readme,
            r"(?i)test suite is not part of this package|from that repository's root",
            "package README runs tests/ commands without saying they are "
            "repository-root commands, not package ones",
        )
        referenced = sorted(set(re.findall(r"`?(tests/[\w./-]+\.py)", readme)))
        self.assertTrue(referenced, "README no longer references the test suite")
        missing = [path for path in referenced if not (ROOT / path).exists()]
        self.assertEqual([], missing, "README references test files that do not exist")

    def test_the_package_ships_no_empty_directories(self):
        """state/ and syllabus/ survived the math-study rename as empty
        leftovers. Git does not track empty directories, so they are invisible
        in `git status` but are copied into every install."""
        empty = [
            str(path.relative_to(self.install_root))
            for path in self.install_root.rglob("*")
            if path.is_dir() and not any(path.iterdir())
        ]
        self.assertEqual([], sorted(empty), "empty directories shipped in the package")


if __name__ == "__main__":
    unittest.main()
