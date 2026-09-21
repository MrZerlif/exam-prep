import argparse
import io
import json
import shlex
import sys
import unittest
from datetime import datetime, timezone
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep import _next_hint, _parser, main


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


    def test_naive_exam_date_with_named_timezone_does_not_crash(self):
        now = datetime(2026, 9, 13, 12, tzinfo=timezone.utc)
        result = _next_hint(
            {"exam": {"date": "2026-09-14T12:00:00", "timezone": "Europe/Moscow"}},
            {},
            {},
            now=now,
        )
        self.assertEqual(1, result["exam_in_days"])

    def test_aware_exam_date_still_works(self):
        now = datetime(2026, 9, 13, 12, tzinfo=timezone.utc)
        result = _next_hint(
            {"exam": {"date": "2026-09-14T12:00:00+03:00"}},
            {},
            {},
            now=now,
        )
        self.assertEqual(1, result["exam_in_days"])

    def test_missing_exam_date_preserves_none(self):
        now = datetime(2026, 9, 13, 12, tzinfo=timezone.utc)
        result = _next_hint({"exam": {"date": None}}, {}, {}, now=now)
        self.assertIsNone(result["exam_in_days"])

    def test_provided_now_makes_next_hint_deterministic(self):
        course = {"exam": {"date": "2026-09-20T12:00:00", "timezone": "Europe/Moscow"}}
        now = datetime(2026, 9, 13, 12, tzinfo=timezone.utc)
        self.assertEqual(
            _next_hint(course, {}, {}, now=now),
            _next_hint(course, {}, {}, now=now),
        )
if __name__ == "__main__":
    unittest.main()
