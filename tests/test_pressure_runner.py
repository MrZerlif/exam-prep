import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCENARIOS = ROOT / "tests" / "scenarios"
sys.path.insert(0, str(SCENARIOS))

from evaluate_transcripts import EvaluationError, release_case_ids, summarize_scores  # noqa: E402
from run_scenarios import build_prompt_packet, emit_evaluation_set, load_case, load_cases, main as run_scenarios  # noqa: E402


class PressureRunnerTests(unittest.TestCase):
    RELEASE_CASE_IDS = (
        "one_mistake_show_answer",
        "fifteen_minute_budget",
        "restart",
        "teacher_material_conflict",
    )

    def test_skill_variant_contains_skill_and_case(self):
        packet = build_prompt_packet(
            case=load_case("one_mistake_show_answer"),
            variant="skill",
            repetition=1,
            skill_text="SKILL CONTENT",
        )
        self.assertEqual("skill", packet["variant"])
        self.assertIn("SKILL CONTENT", packet["system_context"])
        self.assertIn("forbidden_behavior", packet["rubric"])

    def test_baseline_variant_omits_skill(self):
        packet = build_prompt_packet(
            case=load_case("one_mistake_show_answer"),
            variant="baseline",
            repetition=1,
            skill_text="SKILL CONTENT",
        )
        self.assertNotIn("SKILL CONTENT", packet["system_context"])

    def test_export_contains_forty_records_for_four_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "eval.jsonl"
            count = emit_evaluation_set(
                path,
                case_ids=[
                    "one_mistake_show_answer",
                    "fifteen_minute_budget",
                    "restart",
                    "teacher_material_conflict",
                ],
                repeat=5,
                skill_text="SKILL CONTENT",
            )
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(40, count)
            self.assertEqual(40, len(records))
            self.assertEqual(5, sum(item["variant"] == "baseline" for item in records if item["case_id"] == "one_mistake_show_answer"))
            self.assertTrue(all("SKILL CONTENT" in item["system_context"] for item in records if item["variant"] == "skill"))
            self.assertTrue(all("SKILL CONTENT" not in item["system_context"] for item in records if item["variant"] == "baseline"))

    def test_default_export_uses_only_release_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "eval.jsonl"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = run_scenarios(["--emit-eval-set", str(path)])

            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(0, code)
            self.assertEqual(40, len(records))
            self.assertEqual(
                set(self.RELEASE_CASE_IDS),
                {item["case_id"] for item in records},
            )

    def _records(
        self,
        *,
        case_ids=RELEASE_CASE_IDS,
        baseline_pass=True,
        skill_pass=True,
        forbidden=False,
        repetitions=5,
    ):
        result = []
        for case_id in case_ids:
            case = load_case(case_id)
            for variant, passed in (("baseline", baseline_pass), ("skill", skill_pass)):
                for repetition in range(1, repetitions + 1):
                    result.append({
                        "case_id": case["id"],
                        "variant": variant,
                        "repetition": repetition,
                        "response": "external transcript",
                        "pass_scores": {criterion: passed for criterion in case["pass_criteria"]},
                        "forbidden_scores": {criterion: forbidden for criterion in case["forbidden_behavior"]},
                        "reviewer_notes": "independent review",
                    })
        return result

    def test_score_file_requires_five_runs_per_variant(self):
        with self.assertRaises(EvaluationError):
            summarize_scores(self._records()[:1])

    def test_release_gate_passes_complete_explicit_scores(self):
        summary = summarize_scores(self._records())
        self.assertTrue(summary["release_ready"])
        self.assertEqual("pass", summary["status"])
        self.assertEqual(5, summary["cases"]["one_mistake_show_answer"]["skill"]["runs"])

    def test_release_gate_requires_every_required_case(self):
        with self.assertRaises(EvaluationError):
            summarize_scores(self._records(case_ids=("one_mistake_show_answer",)))

    def test_release_gate_treats_baseline_failure_as_comparison_not_blocker(self):
        summary = summarize_scores(self._records(baseline_pass=False, skill_pass=True))
        self.assertTrue(summary["release_ready"])
        self.assertEqual("fail", summary["cases"]["one_mistake_show_answer"]["baseline"]["status"])
        self.assertEqual("pass", summary["cases"]["one_mistake_show_answer"]["skill"]["status"])

    def test_release_gate_accepts_more_than_five_runs(self):
        summary = summarize_scores(self._records(repetitions=6))
        self.assertTrue(summary["release_ready"])
        self.assertEqual(6, summary["cases"]["one_mistake_show_answer"]["skill"]["runs"])

    def test_release_gate_rejects_forbidden_or_low_scores(self):
        summary = summarize_scores(self._records(skill_pass=False, forbidden=True))
        self.assertFalse(summary["release_ready"])
        self.assertEqual("fail", summary["status"])
        self.assertGreater(summary["cases"]["one_mistake_show_answer"]["skill"]["forbidden_violations"], 0)
        self.assertIn("below 90%", " ".join(summary["failures"]))

    def test_release_gate_rejects_skill_worse_than_baseline(self):
        summary = summarize_scores(self._records(baseline_pass=True, skill_pass=False))
        self.assertFalse(summary["release_ready"])
        self.assertIn("worse than baseline", " ".join(summary["failures"]))

    def test_ticket_list_case_is_registered_and_forbids_forced_practice_problems(self):
        # 2.1's acceptance criterion: a ticket_list-blueprint scenario case
        # exists in the manifest and its forbidden_behavior names forcing a
        # practice-problem stage. This pins the case is well-formed and
        # wired into the existing pressure-case machinery (load_case,
        # build_prompt_packet); it is not a substitute for an actual scored
        # transcript run, which requires a live model conversation and an
        # independent evaluator - see evaluate_transcripts.py's own
        # docstring on why self-scoring is deliberately excluded.
        case = load_case("ticket_list_exam_no_forced_problems")
        self.assertNotIn(case["id"], self.RELEASE_CASE_IDS)
        self.assertTrue(
            any(
                "practice-problem" in behavior or "problem ladder" in behavior
                for behavior in case["forbidden_behavior"]
            )
        )
        packet = build_prompt_packet(
            case=case, variant="skill", repetition=1, skill_text="SKILL CONTENT"
        )
        self.assertIn("forbidden_behavior", packet["rubric"])
        self.assertEqual(case["forbidden_behavior"], packet["rubric"]["forbidden_behavior"])

    def test_release_case_ids_still_exactly_four_after_adding_a_case(self):
        # Guards the manifest invariant evaluate_transcripts.py hard-asserts
        # on (_release_case_ids raises unless there are exactly four) - a
        # new non-release case like ticket_list_exam_no_forced_problems must
        # not accidentally flip release_gate.
        self.assertEqual(4, len(self.RELEASE_CASE_IDS))
        self.assertNotIn("ticket_list_exam_no_forced_problems", self.RELEASE_CASE_IDS)

    def test_default_export_still_excludes_the_new_non_release_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "eval.jsonl"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = run_scenarios(["--emit-eval-set", str(path)])
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(0, code)
        self.assertNotIn(
            "ticket_list_exam_no_forced_problems",
            {item["case_id"] for item in records},
        )

    def test_documented_cases_flag_names_only_known_cases(self):
        # The exact drift this guards: baseline-prompts.md documented
        # --cases premature_solution_pressure,short_time_budget,
        # resume_pending_action,... none of which exist, so the one command
        # a reader would copy died with "unknown case".
        doc = (SCENARIOS / "baseline-prompts.md").read_text(encoding="utf-8")
        known = {case["id"] for case in load_cases()}
        documented = {
            case_id
            for group in re.findall(r"--cases\s+([a-z0-9_,]+)", doc)
            for case_id in group.split(",")
            if case_id
        }
        self.assertEqual(
            set(), documented - known, "baseline-prompts.md names unknown case ids"
        )

    def test_baseline_prompts_names_the_release_gate_set(self):
        # Non-vacuous counterpart: dropping --cases must not also drop the
        # reader's only statement of what the default export actually covers.
        doc = (SCENARIOS / "baseline-prompts.md").read_text(encoding="utf-8")
        known = {case["id"] for case in load_cases()}
        named = {token for token in re.findall(r"\x60([^\x60\n]+)\x60", doc) if token in known}
        self.assertEqual(set(release_case_ids()), named)


if __name__ == "__main__":
    unittest.main()
