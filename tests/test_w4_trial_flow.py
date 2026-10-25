import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "skill" / "exam-prep" / "scripts" / "exam_prep.py"


class TrialFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def cli(self, *args):
        completed = subprocess.run(
            [sys.executable, str(CLI), "--workspace", str(self.root), *args],
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            0,
            completed.returncode,
            f"CLI {args!r} failed:\n{completed.stdout}\n{completed.stderr}",
        )
        return json.loads(completed.stdout)

    def write_json(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    @staticmethod
    def proposal(observation_id, target_id, outcome):
        return {
            "schema_version": 2,
            "observation_id": observation_id,
            "target_id": target_id,
            "task_id": f"task-{observation_id}",
            "capability_id": "definition_recall",
            "task_type": "definition_recall",
            "outcome": outcome,
            "assistance": {
                "requested": False,
                "levels_revealed": [],
                "scaffold_types": [],
                "partial_transformation_shown": False,
                "full_solution_viewed": False,
            },
            "error_tags": [],
            "diagnostic_confidence": "high",
            "source_refs": [],
        }

    def observations(self):
        path = self.root / ".exam-prep" / "observations.jsonl"
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]

    def test_w4_trial_flow_through_cli_rebuilds_identical_state(self):
        self.assertEqual("initialized", self.cli("init")["status"])

        target_ids = ["z-first", "a-second", "b-third", "c-fourth", "d-fifth"]
        curriculum = {
            "schema_version": 2,
            "proposal_id": "w4-trial-flow",
            "source_refs": [
                {
                    "source_id": "book:trial",
                    "authority": "teacher_material",
                    "locator": "book overview",
                }
            ],
            "learning_targets": [
                {
                    "target_id": target_id,
                    "title": f"Target {index}",
                    "prerequisites": [],
                    "capability_ids": ["definition_recall"],
                    "estimated_learning_minutes": 20,
                    "source_refs": [
                        {
                            "source_id": "book:trial",
                            "authority": "teacher_material",
                            "locator": f"page {index + 1}, section {index}",
                        }
                    ],
                }
                for index, target_id in enumerate(target_ids)
            ],
            "assessment_capabilities": [],
            "exam_questions": [],
        }
        self.write_json("curriculum.json", curriculum)
        applied = self.cli("apply-curriculum", "curriculum.json")
        self.assertEqual("w4-trial-flow", applied["proposal_id"])

        syllabus = json.loads(
            (self.root / ".exam-prep" / "syllabus.json").read_text(encoding="utf-8")
        )
        targets = {target["target_id"]: target for target in syllabus["learning_targets"]}
        self.assertEqual(
            [f"page {index + 1}, section {index}" for index in range(5)],
            [targets[target_id]["source_refs"][0]["locator"] for target_id in target_ids],
        )

        self.write_json(
            "triage.json",
            {"ratings": {"z-first": 0, "a-second": 0, "b-third": 1, "c-fourth": 2, "d-fifth": 2}},
        )
        self.cli("triage", "triage.json")
        plan = self.cli("plan", "--days", "1", "--minutes-per-day", "40")
        self.assertEqual(
            {
                "total_targets": 5,
                "targets_touched": 0,
                "targets_without_evidence": 5,
                "available_minutes": 40,
                "budget_dates": [datetime.now(timezone.utc).date().isoformat()],
                "minutes_per_target": 8,
                "required_targets_per_hour": 7.5,
                "pace_at_risk": True,
            },
            plan["coverage"],
        )
        self.assertEqual(
            ["z-first", "a-second"],
            [item["target_id"] for item in plan["days"][0]["activities"]],
        )
        self.assertEqual("z-first", self.cli("next")["target_id"])

        self.cli("start-activity", "trial-answer-block")
        unclear = self.proposal("obs-unclear", "b-third", "unclear")
        unclear["activity_id"] = "trial-answer-block"
        original = self.proposal("obs-original", "z-first", "incorrect")
        correction = self.proposal("obs-correction", "z-first", "correct")
        correction["supersedes_observation_id"] = "obs-original"
        independent_checks = [
            self.proposal(f"obs-clean-{index}", "z-first", "correct")
            for index in range(1, 4)
        ]
        self.write_jsonl(
            "answers.jsonl", [unclear, original, correction, *independent_checks]
        )
        batch = self.cli("record-batch", "answers.jsonl")
        self.assertEqual("batch_recorded", batch["status"])
        self.assertEqual(
            ["recorded"] * 6, [row["status"] for row in batch["results"]]
        )
        self.assertEqual("unclear", batch["results"][0]["event"]["outcome"])
        self.assertTrue(batch["results"][0]["event"]["elapsed_includes_recording_delay"])
        self.assertEqual(
            "obs-original",
            batch["results"][2]["event"]["supersedes_observation_id"],
        )

        single_correction = self.proposal(
            "obs-single-correction", "z-first", "correct"
        )
        single_correction["supersedes_observation_id"] = "obs-correction"
        self.write_json("single-correction.json", single_correction)
        recorded = self.cli("record-observation", "single-correction.json")
        self.assertEqual(
            "obs-correction", recorded["event"]["supersedes_observation_id"]
        )

        events = self.observations()
        self.assertEqual(
            [
                "obs-unclear",
                "obs-original",
                "obs-correction",
                "obs-clean-1",
                "obs-clean-2",
                "obs-clean-3",
                "obs-single-correction",
            ],
            [event["observation_id"] for event in events],
        )
        self.assertTrue(events[0]["elapsed_includes_recording_delay"])

        compact = self.cli("status", "--compact")
        compact_targets = compact["targets"]["targets"]
        self.assertEqual("unseen", compact_targets["b-third"]["mastery_status"])
        self.assertEqual("learning", compact_targets["z-first"]["mastery_status"])
        self.assertNotIn("exam_ready", {state["mastery_status"] for state in compact_targets.values()})

        full_status = self.cli("status")
        corrected_target = full_status["targets"]["targets"]["z-first"]
        self.assertGreaterEqual(
            corrected_target["evidence"]["independent_successes"], 2
        )
        self.assertGreaterEqual(corrected_target["mastery"]["recall"], 0.55)
        self.assertEqual(
            ["retained_or_transferred"],
            corrected_target["mastery_status_details"]["missing"],
        )
        self.assertEqual(0, corrected_target["evidence_maturity"]["retained"]["count"])
        self.assertEqual(0, corrected_target["evidence_maturity"]["transferred"]["count"])

        rebuilt = self.cli("rebuild")
        self.assertEqual(full_status["targets"], rebuilt["targets"])
        self.assertEqual(
            full_status["review_queue"]["items"]["z-first"],
            rebuilt["review_queue"]["items"]["z-first"],
        )

    def write_jsonl(self, name, rows):
        path = self.root / name
        path.write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )
        return path


if __name__ == "__main__":
    unittest.main()
