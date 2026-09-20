import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, "skill/exam-prep/scripts")

from exam_prep import main  # noqa: E402
from exam_prep_lib.storage import StudyStore  # noqa: E402


SYLLABUS = {
    "schema_version": 2,
    "course_id": "activity-course",
    "source_refs": [],
    "learning_targets": [
        {
            "target_id": "limits",
            "title": "Limits",
            "prerequisites": [],
            "capability_ids": ["independent_problem"],
        }
    ],
    "assessment_capabilities": {},
    "exam_questions": [],
}
T0 = "2026-09-21T10:00:00+00:00"
T17 = "2026-09-21T10:00:17+00:00"
T18 = "2026-09-21T10:00:18+00:00"


def v2_proposal(observation_id, activity_id=None):
    result = {
        "schema_version": 2,
        "observation_id": observation_id,
        "target_id": "limits",
        "task_id": observation_id,
        "capability_id": "independent_problem",
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
        "source_refs": [],
    }
    if activity_id is not None:
        result["activity_id"] = activity_id
    return result


def v1_proposal(observation_id):
    return {
        "schema_version": 1,
        "observation_id": observation_id,
        "concept_id": "limits",
        "task_id": observation_id,
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
        "source_refs": [],
    }


class ActivityLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.syllabus_path = self.root / "syllabus.json"
        self.syllabus_path.write_text(json.dumps(SYLLABUS), encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--workspace", str(self.root), *args])
        return code, json.loads(output.getvalue())

    def ok(self, *args):
        code, payload = self.run_cli(*args)
        self.assertEqual(0, code, payload)
        return payload

    def at(self, timestamp, *args):
        with patch("exam_prep._now", return_value=timestamp):
            return self.run_cli(*args)

    def ready(self):
        self.ok("init")
        self.ok("load-syllabus", str(self.syllabus_path))
        self.ok("start")

    def write_proposal(self, item):
        path = self.root / f"{item['observation_id']}.json"
        path.write_text(json.dumps(item), encoding="utf-8")
        return path

    def record_at(self, timestamp, item):
        code, payload = self.at(timestamp, "record-observation", str(self.write_proposal(item)))
        self.assertEqual(0, code, payload)
        return payload

    def replace_session(self, **updates):
        store = StudyStore.for_exam_prep(self.root)
        recovered = store.try_recover()
        self.assertIsNotNone(recovered)
        corrupt = dict(recovered.session)
        corrupt.update(updates)
        course = json.loads((store.state_path / "course.json").read_text(encoding="utf-8"))
        syllabus = json.loads((store.state_path / "syllabus.json").read_text(encoding="utf-8"))
        store.commit_revision(
            recovered.derived,
            corrupt,
            recovered.learner,
            recovered.review_queue,
            course,
            syllabus,
        )

    def test_help_contains_all_activity_commands(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as raised:
                main(["--help"])
        self.assertEqual(0, raised.exception.code)
        for command in ("start-activity", "finish-activity", "discard-activity", "activity-status"):
            self.assertIn(command, output.getvalue())

    def test_start_finish_and_status_forms(self):
        self.ready()
        self.assertEqual({"status": "idle"}, self.ok("activity-status"))
        started = self.at(T0, "start-activity", "task-1")[1]
        self.assertEqual("activity_started", started["status"])
        self.assertEqual("active", self.ok("activity-status")["status"])
        finished = self.at(T17, "finish-activity")[1]
        self.assertEqual(17, finished["elapsed_seconds"])
        self.assertEqual({"status": "pending", "activity_id": "task-1", "elapsed_seconds": 17}, self.ok("activity-status"))

    def test_start_idempotence_conflicts_and_pending_block(self):
        self.ready()
        first = self.at(T0, "start-activity", "task-1")[1]
        second = self.at(T18, "start-activity", "task-1")[1]
        self.assertEqual(first, second)
        code, conflict = self.at(T18, "start-activity", "task-2")
        self.assertEqual(1, code)
        self.assertEqual("activity_already_in_progress", conflict["status"])
        self.ok("discard-activity")
        self.at(T0, "start-activity", "task-1")
        self.at(T17, "finish-activity")
        code, pending = self.at(T18, "start-activity", "task-2")
        self.assertEqual(1, code)
        self.assertEqual("pending_activity_not_consumed", pending["status"])

    def test_finish_without_activity_and_discard_modes(self):
        self.ready()
        code, payload = self.at(T0, "finish-activity")
        self.assertEqual(1, code)
        self.assertEqual("no_activity_in_progress", payload["status"])
        self.assertEqual("no_activity", self.ok("discard-activity")["status"])
        self.at(T0, "start-activity", "task-1")
        self.assertEqual("active", self.ok("discard-activity")["previous_state"])
        self.at(T0, "start-activity", "task-1")
        self.at(T17, "finish-activity")
        discarded = self.ok("discard-activity")
        self.assertEqual("pending", discarded["previous_state"])
        self.assertEqual(17, discarded["discarded_elapsed_seconds"])

    def test_discard_recovers_corrupt_timestamp(self):
        self.ready()
        self.at(T0, "start-activity", "task-1")
        self.replace_session(active_activity_started_at="not-a-timestamp")
        code, payload = self.run_cli("discard-activity")
        self.assertEqual(0, code, payload)
        self.assertEqual("active", payload["previous_state"])
        self.assertIsNone(self.ok("activity-status").get("activity_id"))

    def test_invalid_activity_state_is_a_json_error(self):
        self.ready()
        self.replace_session(
            active_activity_id="task-1",
            active_activity_started_at=T0,
            pending_activity_id="task-2",
            pending_activity_elapsed_seconds=3,
        )
        code, payload = self.run_cli("activity-status")
        self.assertEqual(1, code)
        self.assertEqual("invalid_activity_state", payload["status"])

    def test_v2_activity_timing_is_engine_owned_and_speed_stays_unknown(self):
        self.ready()
        self.at(T0, "start-activity", "task-1")
        result = self.record_at(T17, v2_proposal("obs-1", "task-1"))
        self.assertEqual(17, result["event"]["elapsed_seconds"])
        self.assertIsNone(result["event"]["expected_seconds"])
        self.assertIsNone(result["targets"]["targets"]["limits"]["mastery"]["speed"])
        self.assertEqual("idle", self.ok("activity-status")["status"])

    def test_v2_without_or_with_other_activity_does_not_consume_time(self):
        self.ready()
        self.at(T0, "start-activity", "task-1")
        no_activity = self.record_at(T17, v2_proposal("obs-no-activity"))
        self.assertIsNone(no_activity["event"]["elapsed_seconds"])
        other = self.record_at(T18, v2_proposal("obs-other", "task-2"))
        self.assertIsNone(other["event"]["elapsed_seconds"])
        self.assertEqual("active", self.ok("activity-status")["status"])

    def test_v1_observation_does_not_close_activity_or_receive_timing(self):
        self.ready()
        self.at(T0, "start-activity", "task-1")
        result = self.record_at(T17, v1_proposal("obs-v1"))
        self.assertIsNone(result["event"]["elapsed_seconds"])
        self.assertIsNone(result["event"]["expected_seconds"])
        status = self.ok("activity-status")
        self.assertEqual("active", status["status"])
        self.assertEqual("task-1", status["activity_id"])

    def test_consumed_activity_cannot_time_a_second_observation(self):
        self.ready()
        self.at(T0, "start-activity", "task-1")
        first = self.record_at(T17, v2_proposal("obs-first", "task-1"))
        second = self.record_at(T18, v2_proposal("obs-second", "task-1"))
        self.assertEqual(17, first["event"]["elapsed_seconds"])
        self.assertIsNone(second["event"]["elapsed_seconds"])

    def test_end_session_discards_active_and_pending_activity(self):
        self.ready()
        self.at(T0, "start-activity", "task-active")
        ended = self.ok("end-session")
        self.assertEqual("active", ended["discarded_activity"]["previous_state"])
        self.assertIsNone(ended["discarded_activity"]["discarded_elapsed_seconds"])
        self.assertIsNone(ended["session"]["active_activity_id"])
        self.ok("start")
        self.at(T0, "start-activity", "task-pending")
        self.at(T17, "finish-activity")
        ended = self.ok("end-session")
        self.assertEqual("pending", ended["discarded_activity"]["previous_state"])
        self.assertEqual(17, ended["discarded_activity"]["discarded_elapsed_seconds"])

    def test_end_session_summary_attributes_elapsed_study_time(self):
        self.ready()
        self.at(T0, "start-activity", "task-1")
        ended = self.record_at(T17, v2_proposal("obs-summary", "task-1"))
        self.assertEqual(17, ended["event"]["elapsed_seconds"])
        session_end = self.ok("end-session")
        self.assertEqual(17, session_end["summary"]["evaluation"]["active_study_seconds"])

    def test_new_session_does_not_link_old_activity(self):
        self.ready()
        self.at(T0, "start-activity", "task-old")
        self.ok("end-session")
        self.ok("start")
        result = self.record_at(T17, v2_proposal("obs-new", "task-old"))
        self.assertIsNone(result["event"]["elapsed_seconds"])

    def test_reveal_answer_unknown_assessment_keeps_existing_behavior(self):
        self.ready()
        code, payload = self.run_cli("reveal-answer", "missing-assessment")
        self.assertEqual(0, code, payload)
        self.assertEqual("unknown_assessment", payload["status"])

    def test_append_crash_is_recovered_by_idempotent_retry(self):
        self.ready()
        self.at(T0, "start-activity", "task-1")
        path = self.write_proposal(v2_proposal("obs-crash", "task-1"))
        with patch("exam_prep._persist_learning", side_effect=RuntimeError("simulated crash")):
            with self.assertRaises(RuntimeError):
                self.at(T17, "record-observation", str(path))
        store = StudyStore.for_exam_prep(self.root)
        events = store.read_complete_observations()
        self.assertEqual(1, len(events))
        self.assertEqual(17, events[0]["elapsed_seconds"])
        code, retry = self.at(T17, "record-observation", str(path))
        self.assertEqual(0, code, retry)
        self.assertFalse(retry["appended"])
        self.assertEqual(17, retry["event"]["elapsed_seconds"])
        self.assertEqual(1, len(store.read_complete_observations()))
        self.assertEqual("idle", self.ok("activity-status")["status"])


if __name__ == "__main__":
    unittest.main()
