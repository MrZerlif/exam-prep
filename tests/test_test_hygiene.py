"""Contract: the suite itself must not print to stdout.

`python -m unittest discover` interleaves any stray CLI output with the
progress dots, and a real failure in CI is then easy to lose in the noise.
Checked statically, in the style of test_skill_contract, so the guard costs
nothing at run time.
"""

import re
import unittest
from pathlib import Path

TESTS = Path(__file__).parent
CLI_CALL_RE = re.compile(r"\bmain\(\s*\[")
CAPTURES_RE = re.compile(r"redirect_stdout|\bquiet\(")


class TestHygieneTests(unittest.TestCase):
    def test_modules_invoking_the_cli_capture_its_output(self):
        offenders = []
        for path in sorted(TESTS.glob("test_*.py")):
            source = path.read_text(encoding="utf-8")
            if CLI_CALL_RE.search(source) and not CAPTURES_RE.search(source):
                offenders.append(path.name)
        self.assertEqual(
            [],
            offenders,
            "these modules call the CLI without capturing stdout; "
            "wrap the call in tests.quiet() or contextlib.redirect_stdout",
        )


if __name__ == "__main__":
    unittest.main()
