import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep import main


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


if __name__ == "__main__":
    unittest.main()
