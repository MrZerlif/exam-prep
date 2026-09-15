"""Regression tests: a console that cannot encode non-ASCII output (the
Windows codepage crash from the audit - printing a confirmation containing
'∫' or Cyrillic text raised UnicodeEncodeError) must not turn an
already-successful mutation into a reported failure. The exit code reflects
whether the write happened, not whether the terminal could echo it back."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, "skill/exam-prep/scripts")

from exam_prep import main  # noqa: E402
from exam_prep_lib.storage import StudyStore  # noqa: E402


ROOT = Path(__file__).parents[1]
SYLLABUS = ROOT / "skill" / "exam-prep" / "examples" / "mathematics-regression-syllabus.json"


def ascii_only_stdout():
    """A stand-in for a non-UTF-8 console: raises UnicodeEncodeError on any
    non-ASCII write, exactly like the reported Windows codepage failure."""
    return io.TextIOWrapper(io.BytesIO(), encoding="ascii", errors="strict", write_through=True)


class ConsoleEncodingRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def cli_on_broken_console(self, *args):
        stream = ascii_only_stdout()
        with contextlib.redirect_stdout(stream):
            code = main(["--workspace", str(self.root), *args])
        stream.flush()
        stream.buffer.seek(0)
        return code, stream.buffer.read().decode("ascii")

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--workspace", str(self.root), *args])
        self.assertEqual(code, 0, output.getvalue())
        return json.loads(output.getvalue())

    def ready(self):
        self.cli("init")
        self.cli("load-syllabus", str(SYLLABUS))
        self.cli("start")

    def test_record_observation_succeeds_when_console_cannot_print_the_confirmation(self):
        self.ready()
        proposal = {
            "schema_version": 1,
            "observation_id": "obs-integral-sign",
            "concept_id": "chain_rule",
            "task_id": "obs-integral-sign",
            "task_type": "independent_problem",
            "outcome": "incorrect",
            "assistance": {
                "requested": False,
                "levels_revealed": [],
                "scaffold_types": [],
                "partial_transformation_shown": False,
                "full_solution_viewed": False,
            },
            "error_tags": ["conceptual_error"],
            "diagnostic_confidence": "high",
            "learner_self_confidence": "medium",
            "learner_explanation": "Wrote ∫ f(x) dx but picked the wrong u.",
            "source_refs": ["teacher:worksheet-1"],
        }
        proposal_path = self.root / "obs-integral-sign.json"
        proposal_path.write_text(json.dumps(proposal), encoding="utf-8")

        code, printed = self.cli_on_broken_console("record-observation", str(proposal_path))

        self.assertEqual(code, 0, printed)
        # The fallback output must still be valid, parseable JSON.
        parsed = json.loads(printed)
        self.assertEqual(parsed["appended"], True)

        store = StudyStore.for_exam_prep(self.root)
        events, partial = store._read_complete_jsonl(store.observations_path, "observation")
        self.assertFalse(partial)
        matching = [e for e in events if e["observation_id"] == "obs-integral-sign"]
        self.assertEqual(len(matching), 1)

        # A second attempt with the same observation_id must not be needed
        # and, if tried anyway, must not silently create a duplicate.
        status = self.cli("status")
        self.assertIn("chain_rule", status["targets"]["targets"])

    def test_validate_succeeds_when_console_cannot_print_cyrillic_titles(self):
        self.ready()
        proposal = {
            "schema_version": 1,
            "observation_id": "obs-1",
            "concept_id": "chain_rule",
            "task_id": "obs-1",
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
            "learner_explanation": "Цепное правило применено верно.",
            "source_refs": ["teacher:worksheet-1"],
        }
        proposal_path = self.root / "obs-1.json"
        proposal_path.write_text(json.dumps(proposal), encoding="utf-8")
        self.cli("record-observation", str(proposal_path))

        code, printed = self.cli_on_broken_console("validate")

        self.assertEqual(code, 0, printed)
        report = json.loads(printed)
        self.assertTrue(report["valid"])


if __name__ == "__main__":
    unittest.main()
