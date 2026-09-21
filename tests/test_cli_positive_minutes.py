from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "skill" / "exam-prep" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import exam_prep  # noqa: E402


class PositiveMinutesTests(unittest.TestCase):
    def test_next_rejects_non_positive_minutes(self) -> None:
        parser = exam_prep._parser()
        for value in ("0", "-5"):
            with self.subTest(value=value):
                with redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        parser.parse_args(["next", "--minutes", value])
                self.assertEqual(raised.exception.code, 2)

    def test_exam_rejects_non_positive_minutes(self) -> None:
        parser = exam_prep._parser()
        for value in ("0", "-5"):
            with self.subTest(value=value):
                with redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        parser.parse_args(["exam", "--minutes", value])
                self.assertEqual(raised.exception.code, 2)

    def test_positive_minutes_are_accepted(self) -> None:
        parser = exam_prep._parser()
        self.assertEqual(parser.parse_args(["next", "--minutes", "1"]).minutes, 1)
        self.assertEqual(parser.parse_args(["exam", "--minutes", "1"]).minutes, 1)


if __name__ == "__main__":
    unittest.main()
