import contextlib
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "exam-prep" / "scripts"))

import exam_prep  # noqa: E402
from exam_prep import main  # noqa: E402
from exam_prep_lib.defaults import default_course  # noqa: E402
from exam_prep_lib.schema_validation import load_schema, validate_document  # noqa: E402


SYLLABUS = {
    "schema_version": 2,
    "learning_targets": [
        {
            "target_id": "z-first",
            "title": "First by syllabus",
            "prerequisites": [],
            "estimated_learning_minutes": 25,
        },
        {
            "target_id": "a-second",
            "title": "Second by syllabus",
            "prerequisites": [],
            "estimated_learning_minutes": 25,
        },
        {
            "target_id": "middle",
            "title": "Third by syllabus",
            "prerequisites": [],
            "estimated_learning_minutes": 35,
        },
    ],
}


def proposal(observation_id, target_id):
    return {
        "schema_version": 2,
        "observation_id": observation_id,
        "target_id": target_id,
        "task_id": f"task-{observation_id}",
        "capability_id": "definition_recall",
        "task_type": "definition_recall",
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
        "source_refs": [],
    }


class W2CliTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.syllabus_path = self.root / "syllabus.json"
        self.syllabus_path.write_text(json.dumps(SYLLABUS), encoding="utf-8")
        self.cli("init")
        self.cli("load-syllabus", str(self.syllabus_path))

    def tearDown(self):
        self.temp_dir.cleanup()

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            try:
                code = main(["--workspace", str(self.root), *args])
            except SystemExit as exc:
                self.fail(f"CLI rejected {args!r}: {exc}; {output.getvalue()}")
        self.assertEqual(0, code, output.getvalue())
        return json.loads(output.getvalue())

    def write_proposal(self, item):
        path = self.root / f"{item['observation_id']}.json"
        path.write_text(json.dumps(item), encoding="utf-8")
        return path

    def observations(self):
        path = self.root / ".exam-prep" / "observations.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def revision_count(self):
        return len(list((self.root / ".exam-prep" / "revisions").iterdir()))

    def test_record_observation_compact_returns_only_the_compact_receipt(self):
        path = self.write_proposal(proposal("compact-1", "z-first"))

        result = self.cli("record-observation", str(path), "--compact")

        self.assertEqual(
            {
                "status",
                "observation_id",
                "target_id",
                "assistance_band",
                "mastery_status",
                "diagnostics",
            },
            set(result),
        )
        self.assertEqual("recorded", result["status"])
        self.assertEqual("compact-1", result["observation_id"])
        self.assertEqual("z-first", result["target_id"])
        self.assertEqual("independent", result["assistance_band"])
        self.assertEqual("learning", result["mastery_status"])
        self.assertEqual([], result["diagnostics"])

    def test_record_batch_isolates_bad_lines_and_persists_one_revision(self):
        first = proposal("batch-1", "z-first")
        second = proposal("batch-2", "a-second")
        path = self.root / "proposals.jsonl"
        path.write_text(
            json.dumps(first) + "\nnot-json\n" + json.dumps(second) + "\n",
            encoding="utf-8",
        )
        self.cli("status")
        before = self.revision_count()

        result = self.cli("record-batch", str(path))

        self.assertEqual("batch_recorded", result["status"])
        self.assertEqual(3, len(result["results"]))
        self.assertEqual("recorded", result["results"][0]["status"])
        self.assertEqual("error", result["results"][1]["status"])
        self.assertEqual(2, result["results"][1]["line"])
        self.assertTrue(result["results"][1]["error"])
        self.assertEqual("recorded", result["results"][2]["status"])
        self.assertEqual(2, len(self.observations()))
        self.assertEqual(before + 1, self.revision_count())

    def test_record_batch_repeat_is_idempotent(self):
        items = [proposal("same-1", "z-first"), proposal("same-2", "a-second")]
        path = self.root / "retry.jsonl"
        path.write_text("\n".join(json.dumps(item) for item in items) + "\n", encoding="utf-8")

        first = self.cli("record-batch", str(path))
        second = self.cli("record-batch", str(path))

        self.assertEqual(2, len(self.observations()))
        self.assertEqual([True, True], [row["appended"] for row in first["results"]])
        self.assertEqual([False, False], [row["appended"] for row in second["results"]])

    def test_record_batch_replay_preserves_newer_resume_point_and_activity(self):
        first = proposal("replayed-activity", "z-first")
        first["activity_id"] = "reused"
        path = self.root / "replayed.jsonl"
        path.write_text(json.dumps(first) + "\n", encoding="utf-8")

        self.cli("start-activity", "reused")
        self.cli("record-batch", str(path))
        newer = self.write_proposal(proposal("newer-resume", "a-second"))
        self.cli("record-observation", str(newer))
        self.cli("start-activity", "reused")

        replay = self.cli("record-batch", str(path))
        session = self.cli("start")["session"]

        self.assertFalse(replay["results"][0]["appended"])
        self.assertEqual("active", self.cli("activity-status")["status"])
        self.assertEqual("a-second", session["current_target_id"])
        self.assertEqual("task-newer-resume", session["current_task"])

    def test_record_batch_retry_restores_resume_point_after_append_crash(self):
        item = proposal("crashed-batch", "z-first")
        path = self.root / "crashed.jsonl"
        path.write_text(json.dumps(item) + "\n", encoding="utf-8")

        persist_learning = exam_prep._persist_learning

        def crash_after_append(store, *args, **kwargs):
            appended = any(
                event.get("observation_id") == item["observation_id"]
                for event in store.read_complete_observations()
            )
            if appended:
                raise RuntimeError("simulated crash")
            return persist_learning(store, *args, **kwargs)

        with patch("exam_prep._persist_learning", side_effect=crash_after_append):
            with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                self.cli("record-batch", str(path))

        retry = self.cli("record-batch", str(path))
        session = self.cli("start")["session"]

        self.assertFalse(retry["results"][0]["appended"])
        self.assertEqual("z-first", session["current_target_id"])
        self.assertEqual("task-crashed-batch", session["current_task"])
        self.assertTrue(session["current_task_done"])

    def test_record_batch_retry_recovers_pending_activity_after_append_crash(self):
        previous = proposal("prior-pending-cursor", "z-first")
        previous["task_id"] = "repeated-task"
        self.cli("record-observation", str(self.write_proposal(previous)))
        self.cli("start-activity", "pending-recovery")
        self.cli("finish-activity")
        item = proposal("crashed-pending", "z-first")
        item["task_id"] = "repeated-task"
        item["activity_id"] = "pending-recovery"
        path = self.root / "crashed-pending.jsonl"
        path.write_text(json.dumps(item) + "\n", encoding="utf-8")

        persist_learning = exam_prep._persist_learning

        def crash_after_append(store, *args, **kwargs):
            appended = any(
                event.get("observation_id") == item["observation_id"]
                for event in store.read_complete_observations()
            )
            if appended:
                raise RuntimeError("simulated crash")
            return persist_learning(store, *args, **kwargs)

        with patch("exam_prep._persist_learning", side_effect=crash_after_append):
            with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                self.cli("record-batch", str(path))

        retry = self.cli("record-batch", str(path))

        self.assertFalse(retry["results"][0]["appended"])
        self.assertEqual("idle", self.cli("activity-status")["status"])

    def test_record_batch_replay_preserves_newer_pending_activity_with_reused_id(self):
        item = proposal("pending-replay", "z-first")
        item["activity_id"] = "reused-pending"
        path = self.root / "pending-replay.jsonl"
        path.write_text(json.dumps(item) + "\n", encoding="utf-8")

        with patch("exam_prep._now", return_value="2026-01-01T00:00:00+00:00"):
            self.cli("start-activity", "reused-pending")
        with patch("exam_prep._now", return_value="2026-01-01T00:00:00.500000+00:00"):
            self.cli("finish-activity")
        with patch("exam_prep._now", return_value="2026-01-01T00:00:01+00:00"):
            self.cli("record-batch", str(path))

        with patch("exam_prep._now", return_value="2026-01-01T00:00:02+00:00"):
            self.cli("start-activity", "reused-pending")
        with patch("exam_prep._now", return_value="2026-01-01T00:00:02.500000+00:00"):
            self.cli("finish-activity")

        replay = self.cli("record-batch", str(path))

        self.assertFalse(replay["results"][0]["appended"])
        self.assertEqual("pending", self.cli("activity-status")["status"])

    def test_record_batch_compact_returns_small_receipts_and_keeps_line_errors(self):
        item = proposal("compact-batch-1", "z-first")
        path = self.root / "compact.jsonl"
        path.write_text(json.dumps(item) + "\nnot-json\n", encoding="utf-8")

        result = self.cli("record-batch", str(path), "--compact")

        self.assertEqual(2, len(result["results"]))
        self.assertEqual(
            {
                "line",
                "status",
                "observation_id",
                "target_id",
                "assistance_band",
                "mastery_status",
                "diagnostics",
            },
            set(result["results"][0]),
        )
        self.assertEqual(1, result["results"][0]["line"])
        self.assertEqual("compact-batch-1", result["results"][0]["observation_id"])
        self.assertNotIn("event", result["results"][0])
        self.assertEqual("error", result["results"][1]["status"])
        self.assertEqual(2, result["results"][1]["line"])

    def test_record_batch_returns_failure_exit_when_every_line_is_rejected(self):
        path = self.root / "invalid.jsonl"
        path.write_text("not-json\n", encoding="utf-8")
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            code = main(["--workspace", str(self.root), "record-batch", str(path)])

        self.assertEqual(1, code)
        result = json.loads(output.getvalue())
        self.assertEqual("batch_failed", result["status"])
        self.assertEqual(1, result["results"][0]["line"])
        self.assertEqual("error", result["results"][0]["status"])

    def test_triage_persists_self_ratings_without_creating_evidence(self):
        path = self.root / "triage.json"
        path.write_text(
            json.dumps({"ratings": {"a-second": 0, "z-first": 2}}),
            encoding="utf-8",
        )

        result = self.cli("triage", str(path))
        learner = json.loads((self.root / ".exam-prep" / "learner.json").read_text(encoding="utf-8"))
        status = self.cli("status")

        self.assertEqual("triage_recorded", result["status"])
        self.assertEqual({"a-second": 0, "z-first": 2}, learner["self_rating"])
        self.assertEqual([], self.observations())
        self.assertTrue(
            all(
                item["mastery_status"] == "unseen"
                for item in status["targets"]["targets"].values()
            )
        )
        self.assertEqual("a-second", self.cli("next")["target_id"])

    def test_plan_reports_coverage_and_uses_course_budget(self):
        observation = self.write_proposal(proposal("coverage-1", "z-first"))
        self.cli("record-observation", str(observation))
        course_path = self.root / ".exam-prep" / "course.json"
        course = json.loads(course_path.read_text(encoding="utf-8"))
        today = datetime.now(timezone.utc).date()
        course["time_budget"]["available_minutes_by_day"] = {
            today.isoformat(): 60,
            (today + timedelta(days=1)).isoformat(): 60,
        }
        course_path.write_text(json.dumps(course), encoding="utf-8")

        result = self.cli("plan", "--days", "2", "--minutes-per-day", "30")

        self.assertEqual(
            {
                "total_targets": 3,
                "targets_touched": 1,
                "targets_without_evidence": 2,
                "available_minutes": 120,
                "budget_dates": [today.isoformat(), (today + timedelta(days=1)).isoformat()],
                "minutes_per_target": 40,
                "required_targets_per_hour": 1.5,
                "pace_at_risk": False,
            },
            result["coverage"],
        )

    def test_course_ticket_slots_validate_and_appear_in_status(self):
        course = default_course()
        course["exam"]["ticket_slots"] = [
            {"kind": "theory", "count": 2},
            {"kind": "problem", "count": 1},
        ]
        validate_document(course, load_schema("course.schema.json"))
        course_path = self.root / ".exam-prep" / "course.json"
        course_path.write_text(json.dumps(course), encoding="utf-8")

        status = self.cli("status")

        self.assertEqual(course["exam"]["ticket_slots"], status["course"]["exam"]["ticket_slots"])

    def test_course_schema_rejects_unknown_ticket_slot_kind(self):
        course = default_course()
        course["exam"]["ticket_slots"] = [{"kind": "essay", "count": 1}]

        with self.assertRaises(ValueError):
            validate_document(course, load_schema("course.schema.json"))


if __name__ == "__main__":
    unittest.main()
