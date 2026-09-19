import argparse
import io
import json
import shlex
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep import _parser, main


class NextHintTests(unittest.TestCase):
    def test_hint_is_opt_in_and_uses_same_parser(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.call(root, "init")
            plain = self.call(root, "status")
            hinted = self.call(root, "status", "--include-next-hint")
            self.assertNotIn("next", plain)
            self.assertIn("next", hinted)
            parsed = _parser().parse_args(shlex.split(hinted["next"]["command"]))
            self.assertEqual("next", parsed.command)

    @staticmethod
    def call(root: Path, *args: str) -> dict:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--workspace", str(root), *args])
        if code:
            raise AssertionError(output.getvalue())
        return json.loads(output.getvalue())


if __name__ == "__main__":
    unittest.main()
