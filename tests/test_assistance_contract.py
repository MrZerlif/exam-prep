"""The v2 assistance object is the only thing standing between an LLM-built
proposal and a mastery claim, and it shipped as a bare `{"type": "object"}`.

Two consequences, both reproduced before this module existed:

1. `{"levels_revealed": null}` passed validation, was appended to the canonical
   log, and only then crashed the band derivation - leaving a record that
   `status` and `rebuild` could no longer read. `validate` called that
   workspace healthy, so the documented repair path pointed nowhere and the
   only way out was hand-editing an append-only log every doc forbids touching.
2. `{}` derived as `independent` - the strongest evidence the model can claim,
   available by omitting fields rather than by asserting anything.

The contract is therefore: nothing invalid reaches the log (schema), and
nothing already in a log can brick a read (total derivation), with anything
unverifiable treated as assisted rather than independent.
"""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SKILL_ROOT = ROOT / "skill" / "exam-prep"
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from exam_prep import main  # noqa: E402
from exam_prep_lib.reducer import derive_assistance_band  # noqa: E402
from exam_prep_lib.schema_validation import SchemaError  # noqa: E402


SYLLABUS = SKILL_ROOT / "examples" / "mathematics-regression-syllabus.json"
TARGET_ID = "functions"
CAPABILITY_ID = "independent_problem"


def _proposal(observation_id: str, assistance: object) -> dict:
    return {
        "schema_version": 2,
        "observation_id": observation_id,
        "target_id": TARGET_ID,
        "task_id": "task-1",
        "capability_id": CAPABILITY_ID,
        "task_type": "independent_problem",
        "outcome": "correct",
        "assistance": assistance,
        "error_tags": [],
        "diagnostic_confidence": "high",
        "source_refs": [],
    }


class AssistanceContractTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.log = self.root / ".exam-prep" / "observations.jsonl"
        self.cli("init")
        self.cli("load-syllabus", str(SYLLABUS))
        self.cli("start")

    def tearDown(self):
        self.temp_dir.cleanup()

    def cli(self, *args, expect: int = 0):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--workspace", str(self.root), *args])
        self.assertEqual(code, expect, output.getvalue())
        return output.getvalue()

    def write_proposal(self, name: str, assistance: object) -> str:
        path = self.root / f"{name}.json"
        path.write_text(
            json.dumps(_proposal(name, assistance)), encoding="utf-8"
        )
        return str(path)

    def log_lines(self) -> list[str]:
        if not self.log.exists():
            return []
        return [line for line in self.log.read_text(encoding="utf-8").splitlines() if line]

    def assert_rejected_without_touching_the_log(self, assistance: object, name: str):
        # main() raises rather than returning a code for a schema failure -
        # the same contract tests/test_cli.py already relies on. The exit code
        # a shell sees is covered separately by the subprocess test below.
        before = self.log_lines()
        path = self.write_proposal(name, assistance)
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SchemaError, msg=f"{name} was accepted"):
                main(["--workspace", str(self.root), "record-observation", path])
        self.assertEqual(
            before,
            self.log_lines(),
            f"{name} was appended to the canonical log before being rejected",
        )
        # The workspace must still be readable - the original defect was not
        # the rejection but what the rejection left behind.
        self.cli("status", "--compact")
        self.cli("rebuild")

    def test_null_levels_revealed_never_reaches_the_canonical_log(self):
        self.assert_rejected_without_touching_the_log({"levels_revealed": None}, "null-levels")

    def test_assistance_without_levels_revealed_is_not_silent_independence(self):
        # {} derived as independent. Claiming no hints is now something the
        # proposal has to state, not something it gets by leaving a field out.
        self.assert_rejected_without_touching_the_log({}, "empty-assistance")

    def test_unknown_assistance_key_is_rejected(self):
        self.assert_rejected_without_touching_the_log(
            {"levels_revealed": [], "hint_level": 2}, "unknown-key"
        )

    def test_hint_levels_outside_the_h0_h5_ladder_are_rejected(self):
        self.assert_rejected_without_touching_the_log(
            {"levels_revealed": ["H7"]}, "bad-ladder"
        )

    def test_assistance_that_is_not_an_object_is_rejected(self):
        self.assert_rejected_without_touching_the_log(["H1"], "not-an-object")

    def test_an_explicit_empty_ladder_is_still_independent_evidence(self):
        path = self.write_proposal("clean", {"levels_revealed": []})
        payload = json.loads(self.cli("record-observation", path))
        self.assertTrue(payload["appended"])
        self.assertEqual(1, len(self.log_lines()))

    def test_band_derivation_is_total_and_never_grants_independence_it_cannot_verify(self):
        self.assertEqual("independent", derive_assistance_band({"levels_revealed": []}))
        self.assertEqual("guided", derive_assistance_band({"levels_revealed": ["H2"]}))
        self.assertEqual("solution_seen", derive_assistance_band({"full_solution_viewed": True}))
        for unverifiable in ({"levels_revealed": None}, {}, {"levels_revealed": "H1"}, None, []):
            with self.subTest(assistance=unverifiable):
                band = derive_assistance_band(unverifiable)
                self.assertNotEqual(
                    "independent",
                    band,
                    "an assistance object that cannot be read must not promote "
                    "independent mastery",
                )

    def test_the_shell_sees_a_failing_exit_code_and_a_structured_error(self):
        # The defect this module exists for was reproduced from a shell, so the
        # shell-visible contract is worth pinning: a rejected proposal reports
        # JSON, not a traceback, and does not exit 0.
        import subprocess

        path = self.write_proposal("shell-null", {"levels_revealed": None})
        completed = subprocess.run(
            [
                sys.executable,
                str(SKILL_ROOT / "scripts" / "exam_prep.py"),
                "--workspace",
                str(self.root),
                "record-observation",
                path,
            ],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(0, completed.returncode)
        self.assertIn("levels_revealed", completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)
        self.assertEqual([], self.log_lines())

    def test_a_workspace_poisoned_before_this_fix_can_still_be_rebuilt(self):
        # Logs written while the schema was permissive still exist. Recovery
        # has to work on them, because rebuild is the documented repair and
        # the log itself must never be hand-edited.
        path = self.write_proposal("legacy", {"levels_revealed": []})
        self.cli("record-observation", path)
        event = json.loads(self.log_lines()[0])
        event["assistance"] = {"levels_revealed": None}
        self.log.write_text(json.dumps(event, sort_keys=True) + "\n", encoding="utf-8")
        self.cli("rebuild")
        self.cli("status", "--compact")


class CurriculumExitCodeTests(unittest.TestCase):
    """`validate-curriculum` is the gate SKILL.md puts in front of
    `apply-curriculum`. Reporting "valid": false on stdout while exiting 0 makes
    that gate invisible to every caller that checks the exit code, agent or CI -
    plain `validate` already returns 1 in the same situation."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_validate_curriculum_exits_nonzero_when_the_proposal_is_invalid(self):
        proposal = self.root / "proposal.json"
        proposal.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "proposal_id": "p1",
                    "learning_targets": [
                        {
                            "target_id": "a",
                            "title": "A",
                            "prerequisites": ["missing-target"],
                            "capability_ids": ["calculation"],
                            "exam_question_ids": [],
                            "source_refs": [],
                        }
                    ],
                    "exam_questions": [],
                    "assessment_capabilities": [],
                    "source_refs": [],
                }
            ),
            encoding="utf-8",
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--workspace", str(self.root), "validate-curriculum", str(proposal)])
        payload = json.loads(output.getvalue())
        self.assertFalse(payload["valid"])
        self.assertEqual(1, code, "an invalid proposal must not exit 0")

    def test_validate_curriculum_still_exits_zero_for_a_valid_proposal(self):
        proposal = self.root / "ok.json"
        proposal.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "proposal_id": "p2",
                    "learning_targets": [
                        {
                            "target_id": "a",
                            "title": "A",
                            "prerequisites": [],
                            "capability_ids": ["calculation"],
                            "exam_question_ids": [],
                            "source_refs": [],
                        }
                    ],
                    "exam_questions": [],
                    "assessment_capabilities": [],
                    "source_refs": [],
                }
            ),
            encoding="utf-8",
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--workspace", str(self.root), "validate-curriculum", str(proposal)])
        self.assertTrue(json.loads(output.getvalue())["valid"])
        self.assertEqual(0, code)


if __name__ == "__main__":
    unittest.main()
