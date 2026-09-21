import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep import main
from exam_prep_lib.readiness import build_readiness


class ReadinessTests(unittest.TestCase):
    def call(self, root: Path, *args: str) -> tuple[int, dict]:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--workspace", str(root), *args])
        return code, json.loads(output.getvalue())

    def test_fresh_workspace_is_blocked(self):
        with TemporaryDirectory() as directory:
            code, result = self.call(Path(directory), "validate", "--readiness")
            self.assertEqual(1, code)
            self.assertEqual("blocked", result["readiness"]["verdict"])

    def test_initialized_workspace_without_materials_has_gaps(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.call(root, "init")
            code, result = self.call(root, "validate", "--readiness")
            self.assertEqual(0, code)
            self.assertEqual("usable_with_gaps", result["readiness"]["verdict"])
            self.assertTrue(result["readiness"]["reasons"])

    def test_recovery_failure_is_reported_instead_of_silently_ignored(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "course.json").write_text(
                json.dumps({"exam": {"question_count": 1}}), encoding="utf-8"
            )
            (root / "syllabus.json").write_text(
                json.dumps({"learning_targets": [{"target_id": "limits"}]}),
                encoding="utf-8",
            )

            class FailingRecoveryStore:
                state_path = root

                @staticmethod
                def read_source_evidence():
                    return [{"source_ref": "notes#p1"}]

                @staticmethod
                def read_assessments():
                    return [{"purpose": "mock", "origin": "curated"}]

                @staticmethod
                def try_recover():
                    raise RuntimeError("recovery boom")

            readiness = build_readiness(FailingRecoveryStore(), {"valid": True})
            self.assertEqual("usable_with_gaps", readiness["verdict"])
            self.assertEqual(
                ["recovery check failed (RuntimeError): recovery boom"],
                readiness["reasons"],
            )


if __name__ == "__main__":
    unittest.main()
