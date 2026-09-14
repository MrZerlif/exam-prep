import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep import main  # noqa: E402


def spec(assessment_id, prompt, target_id="ticket-target", **overrides):
    value = {
        "assessment_id": assessment_id,
        "target_id": target_id,
        "capability_id": "independent_problem",
        "prompt": prompt,
        "rubric": {"correct": 1},
        "expected_evidence": ["independent_work"],
        "source_refs": [
            {"source_id": "teacher:tickets", "authority": "teacher_material", "locator": "ticket list"}
        ],
        "difficulty": 0.4,
        "question_version": 1,
        "rubric_version": 1,
    }
    value.update(overrides)
    return value


class AssessmentMintingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--workspace", str(self.root), *args])
        self.assertEqual(code, 0, output.getvalue())
        return json.loads(output.getvalue())

    def mint(self, batch):
        path = self.root / "batch.json"
        path.write_text(json.dumps(batch), encoding="utf-8")
        return self.cli("mint-assessments", str(path))

    def test_batch_of_three_mints_in_one_command(self):
        self.cli("init")
        batch = {
            "purpose": "practice",
            "assessments": [
                spec("ticket-1", "State and prove the intermediate value theorem."),
                spec("ticket-2", "Derive the chain rule from first principles."),
                spec("ticket-3", "State the definition of continuity."),
            ],
        }
        result = self.mint(batch)
        self.assertEqual(3, result["minted_count"])
        self.assertEqual(0, result["already_existed_count"])
        self.assertEqual(0, result["rejected_count"])
        ids = {item["assessment_id"] for item in result["minted"]}
        self.assertEqual({"ticket-1", "ticket-2", "ticket-3"}, ids)
        self.assertTrue(all(item["purpose"] == "practice" for item in result["minted"]))

    def test_rerunning_the_same_batch_is_idempotent(self):
        self.cli("init")
        batch = {
            "purpose": "held_out",
            "assessments": [spec("ticket-4", "State the mean value theorem.")],
        }
        first = self.mint(batch)
        self.assertEqual(1, first["minted_count"])
        second = self.mint(batch)
        self.assertEqual(0, second["minted_count"])
        self.assertEqual(1, second["already_existed_count"])
        self.assertEqual(0, second["rejected_count"])

    def test_pool_isolation_violation_is_rejected_per_entry_not_whole_batch(self):
        self.cli("init")
        practiced = self.mint(
            {
                "purpose": "practice",
                "assessments": [spec("ticket-5-practiced", "State Rolle's theorem.")],
            }
        )
        self.assertEqual(1, practiced["minted_count"])

        # Second batch: one entry collides with already-practiced content
        # under a mock purpose (must be rejected), one entry is fresh (must
        # still mint) - the violation must not abort the whole batch.
        result = self.mint(
            {
                "assessments": [
                    spec(
                        "ticket-5-mock-collision",
                        "State Rolle's theorem.",
                        purpose="mock",
                    ),
                    spec("ticket-6-fresh", "State the squeeze theorem.", purpose="mock"),
                ]
            }
        )
        self.assertEqual(1, result["minted_count"])
        self.assertEqual(1, result["rejected_count"])
        self.assertEqual("ticket-6-fresh", result["minted"][0]["assessment_id"])
        rejection = result["rejected"][0]
        self.assertEqual("ticket-5-mock-collision", rejection["assessment_id"])
        self.assertIn("question_hash", rejection["error"])
        self.assertIn("practice", rejection["error"])

    def test_pool_isolation_catches_a_conflict_within_a_single_batch(self):
        # Task 3 verification finding: the existing pool-isolation test
        # above only exercises a conflict *across* two separate
        # mint-assessments calls. Whether the guard also catches two
        # colliding entries within the *same* call - where the second
        # entry's check must see the first entry's just-appended record -
        # was unverified. It works (append_assessment re-reads the store
        # fresh on every entry, including ones written earlier in this same
        # loop), but nothing proved it. Checks both directions in one call.
        self.cli("init")
        result = self.mint(
            {
                "assessments": [
                    spec("intra-practice", "Same content, one batch call.", purpose="practice"),
                    spec("intra-mock-collision", "Same content, one batch call.", purpose="mock"),
                    spec("intra-mock-first", "Reverse-order same content.", purpose="mock"),
                    spec("intra-practice-collision", "Reverse-order same content.", purpose="practice"),
                ]
            }
        )
        self.assertEqual(2, result["minted_count"])
        self.assertEqual(
            {"intra-practice", "intra-mock-first"},
            {item["assessment_id"] for item in result["minted"]},
        )
        self.assertEqual(2, result["rejected_count"])
        self.assertEqual(
            {"intra-mock-collision", "intra-practice-collision"},
            {item["assessment_id"] for item in result["rejected"]},
        )

    def test_rejected_entry_names_a_schema_problem_too(self):
        self.cli("init")
        broken = spec("ticket-7", "State the definition of a limit.")
        del broken["prompt"]
        result = self.mint({"assessments": [broken]})
        self.assertEqual(0, result["minted_count"])
        self.assertEqual(1, result["rejected_count"])
        self.assertEqual("ticket-7", result["rejected"][0]["assessment_id"])
        self.assertIn("prompt", result["rejected"][0]["error"])

    def test_default_purpose_applies_unless_entry_overrides_it(self):
        self.cli("init")
        result = self.mint(
            {
                "purpose": "held_out",
                "assessments": [
                    spec("ticket-8", "State Fermat's little theorem."),
                    spec("ticket-9", "State Bayes' theorem.", purpose="retest"),
                ],
            }
        )
        by_id = {item["assessment_id"]: item for item in result["minted"]}
        self.assertEqual("held_out", by_id["ticket-8"]["purpose"])
        self.assertEqual("retest", by_id["ticket-9"]["purpose"])

    def test_empty_batch_is_rejected(self):
        self.cli("init")
        path = self.root / "empty.json"
        path.write_text(json.dumps({"assessments": []}), encoding="utf-8")
        with self.assertRaises(ValueError):
            main(["--workspace", str(self.root), "mint-assessments", str(path)])

    def test_minted_assessments_are_readable_through_the_normal_store(self):
        self.cli("init")
        self.mint({"assessments": [spec("ticket-10", "State the fundamental theorem of calculus.")]})
        stored = json.loads(
            (self.root / ".exam-prep" / "assessments.jsonl").read_text(encoding="utf-8")
        )
        self.assertEqual("ticket-10", stored["assessment_id"])
        self.assertEqual("practice", stored["purpose"])


if __name__ == "__main__":
    unittest.main()
