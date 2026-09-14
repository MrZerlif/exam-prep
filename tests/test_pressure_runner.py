import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCENARIOS = ROOT / "tests" / "scenarios"
sys.path.insert(0, str(SCENARIOS))

from evaluate_transcripts import EvaluationError, summarize_scores  # noqa: E402
from run_scenarios import build_prompt_packet, emit_evaluation_set, load_case, main as run_scenarios  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
