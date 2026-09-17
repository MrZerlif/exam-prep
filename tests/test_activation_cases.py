import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCENARIOS = ROOT / "tests" / "scenarios"
sys.path.insert(0, str(SCENARIOS))

from run_scenarios import emit_activation_set, load_activation_cases  # noqa: E402


class ActivationCaseTests(unittest.TestCase):
    def test_activation_manifest_has_positive_and_negative_cases(self):
        path = SCENARIOS / "activation-cases.json"
        self.assertTrue(path.exists(), "activation-cases.json is required")
        data = json.loads(path.read_text(encoding="utf-8"))
        cases = data["cases"]
        self.assertGreaterEqual(len(cases), 6)
        self.assertGreaterEqual(sum(case["should_activate"] is True for case in cases), 3)
        self.assertGreaterEqual(sum(case["should_activate"] is False for case in cases), 3)
        self.assertEqual(len(cases), len({case["id"] for case in cases}))
        for case in cases:
            self.assertIsInstance(case["prompt"], str)
            self.assertTrue(case["prompt"].strip())

    def test_activation_cases_cover_resume_time_pressure_and_near_misses(self):
        data = json.loads(
            (SCENARIOS / "activation-cases.json").read_text(encoding="utf-8")
        )
        ids = {case["id"] for case in data["cases"]}
        self.assertTrue(
            {
                "exam_with_deadline",
                "resume_local_progress",
                "limited_time_weak_prerequisites",
                "generic_learning_question",
                "non_exam_project_planning",
                "generic_flashcards",
            }.issubset(ids)
        )

    def test_activation_export_is_ready_for_fresh_host_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "activation.jsonl"
            count = emit_activation_set(path)
            records = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
            ]
        self.assertEqual(len(load_activation_cases()), count)
        self.assertEqual(count, len(records))
        self.assertTrue(all("should_activate" in record for record in records))
        self.assertTrue(all("user_prompt" in record for record in records))
        self.assertTrue(
            all("normal skill discovery" in record["system_context"] for record in records)
        )

    def test_activation_export_command_is_documented(self):
        doc = (SCENARIOS / "baseline-prompts.md").read_text(encoding="utf-8")
        self.assertIn("--emit-activation-set", doc)
        self.assertIn("positive and negative", doc)


if __name__ == "__main__":
    unittest.main()
