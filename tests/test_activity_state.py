import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.activity import (  # noqa: E402
    ActivityStateError,
    activity_status,
    consume_activity,
    discard_activity,
    elapsed_seconds,
    finish_activity,
    start_activity,
)
from exam_prep_lib.defaults import default_session  # noqa: E402
from exam_prep_lib.schema_validation import load_schema, validate_document  # noqa: E402


STARTED = "2026-09-21T10:00:00+00:00"
FINISHED = "2026-09-21T10:00:17Z"


def session(**updates):
    result = default_session()
    result.update(updates)
    return result


class ActivityStateTests(unittest.TestCase):
    def assert_valid_session(self, value):
        validate_document(value, load_schema("session.schema.json"))

    def test_idle_status(self):
        self.assertEqual({"status": "idle"}, activity_status(session()))

    def test_start_from_idle(self):
        transition = start_activity(session(), "task-1", STARTED)
        self.assertEqual(0, transition.exit_code)
        self.assertTrue(transition.changed)
        self.assertEqual(
            {
                "status": "activity_started",
                "activity_id": "task-1",
                "started_at": STARTED,
            },
            transition.payload,
        )
        self.assertEqual("active", activity_status(transition.session)["status"])
        self.assert_valid_session(transition.session)

    def test_start_same_id_is_idempotent(self):
        first = start_activity(session(), "task-1", STARTED)
        second = start_activity(first.session, "task-1", "2026-09-21T11:00:00+00:00")
        self.assertEqual(0, second.exit_code)
        self.assertFalse(second.changed)
        self.assertEqual(first.session, second.session)
        self.assertEqual(first.payload, second.payload)

    def test_start_other_id_returns_conflict(self):
        first = start_activity(session(), "task-1", STARTED)
        result = start_activity(first.session, "task-2", FINISHED)
        self.assertEqual(1, result.exit_code)
        self.assertFalse(result.changed)
        self.assertEqual("activity_already_in_progress", result.payload["status"])
        self.assertEqual("task-2", result.payload["requested_activity_id"])

    def test_finish_moves_active_to_pending(self):
        active = start_activity(session(), "task-1", STARTED)
        result = finish_activity(active.session, FINISHED)
        self.assertEqual(0, result.exit_code)
        self.assertTrue(result.changed)
        self.assertEqual(17, result.payload["elapsed_seconds"])
        self.assertEqual({"status": "pending", "activity_id": "task-1", "elapsed_seconds": 17}, activity_status(result.session))
        self.assert_valid_session(result.session)

    def test_finish_pending_is_idempotent(self):
        active = start_activity(session(), "task-1", STARTED)
        pending = finish_activity(active.session, FINISHED)
        result = finish_activity(pending.session, "2026-09-21T11:00:00+00:00")
        self.assertEqual(0, result.exit_code)
        self.assertFalse(result.changed)
        self.assertEqual(pending.session, result.session)
        self.assertEqual("activity_already_finished", result.payload["status"])

    def test_finish_idle_returns_error(self):
        result = finish_activity(session(), FINISHED)
        self.assertEqual(1, result.exit_code)
        self.assertFalse(result.changed)
        self.assertEqual("no_activity_in_progress", result.payload["status"])

    def test_pending_blocks_new_start(self):
        active = start_activity(session(), "task-1", STARTED)
        pending = finish_activity(active.session, FINISHED)
        result = start_activity(pending.session, "task-2", FINISHED)
        self.assertEqual(1, result.exit_code)
        self.assertFalse(result.changed)
        self.assertEqual("pending_activity_not_consumed", result.payload["status"])

    def test_consume_active(self):
        active = start_activity(session(), "task-1", STARTED)
        result = consume_activity(active.session, "task-1", FINISHED)
        self.assertTrue(result.matched)
        self.assertEqual(17, result.elapsed_seconds)
        self.assertEqual({"status": "idle"}, activity_status(result.session))
        self.assert_valid_session(result.session)

    def test_consume_pending(self):
        active = start_activity(session(), "task-1", STARTED)
        pending = finish_activity(active.session, FINISHED)
        result = consume_activity(pending.session, "task-1", "not-used")
        self.assertTrue(result.matched)
        self.assertEqual(17, result.elapsed_seconds)
        self.assertEqual({"status": "idle"}, activity_status(result.session))

    def test_consume_mismatch_and_missing_id_do_not_change_state(self):
        active = start_activity(session(), "task-1", STARTED)
        mismatch = consume_activity(active.session, "task-2", FINISHED)
        missing = consume_activity(active.session, None, FINISHED)
        self.assertFalse(mismatch.matched)
        self.assertIsNone(mismatch.elapsed_seconds)
        self.assertEqual(active.session, mismatch.session)
        self.assertFalse(missing.matched)
        self.assertEqual(active.session, missing.session)

    def test_discard_active_does_not_parse_timestamp(self):
        corrupted = session(active_activity_id="task-1", active_activity_started_at="not-a-timestamp")
        result = discard_activity(corrupted)
        self.assertEqual(0, result.exit_code)
        self.assertTrue(result.changed)
        self.assertEqual("active", result.payload["previous_state"])
        self.assertIsNone(result.payload["discarded_elapsed_seconds"])
        self.assertEqual({"status": "idle"}, activity_status(result.session))

    def test_discard_pending(self):
        pending = session(pending_activity_id="task-1", pending_activity_elapsed_seconds=17)
        result = discard_activity(pending)
        self.assertEqual(0, result.exit_code)
        self.assertEqual(17, result.payload["discarded_elapsed_seconds"])
        self.assertEqual({"status": "idle"}, activity_status(result.session))

    def test_discard_idle(self):
        result = discard_activity(session())
        self.assertEqual(0, result.exit_code)
        self.assertFalse(result.changed)
        self.assertEqual({"status": "no_activity"}, result.payload)

    def test_discard_clears_invalid_combination(self):
        corrupted = session(
            active_activity_id="task-1",
            active_activity_started_at=STARTED,
            pending_activity_id="task-2",
            pending_activity_elapsed_seconds=4,
        )
        result = discard_activity(corrupted)
        self.assertEqual(0, result.exit_code)
        self.assertTrue(result.changed)
        self.assertEqual("invalid", result.payload["previous_state"])
        self.assertIsNone(result.payload["activity_id"])
        self.assertEqual({"status": "idle"}, activity_status(result.session))

    def test_invalid_state_combinations_raise(self):
        with self.assertRaises(ActivityStateError):
            activity_status(session(active_activity_id="task-1"))
        with self.assertRaises(ActivityStateError):
            activity_status(session(active_activity_id="task-1", active_activity_started_at=STARTED, pending_activity_id="task-2", pending_activity_elapsed_seconds=4))
        with self.assertRaises(ActivityStateError):
            start_activity(session(), "", STARTED)

    def test_timestamp_validation_and_negative_elapsed(self):
        with self.assertRaises(ActivityStateError):
            elapsed_seconds("2026-09-21T10:00:00", FINISHED)
        with self.assertRaises(ActivityStateError):
            elapsed_seconds("not-a-timestamp", FINISHED)
        self.assertEqual(0, elapsed_seconds(FINISHED, STARTED))

    def test_activity_fields_are_consistently_cleared(self):
        active = start_activity(session(), "task-1", STARTED)
        pending = finish_activity(active.session, FINISHED)
        consumed = consume_activity(pending.session, "task-1", FINISHED)
        for field in (
            "active_activity_id",
            "active_activity_started_at",
            "pending_activity_id",
            "pending_activity_elapsed_seconds",
        ):
            self.assertIsNone(consumed.session[field])

    def test_defaults_and_template_have_same_activity_fields(self):
        template = json.loads((ROOT / "skill" / "exam-prep" / "templates" / "session.json").read_text(encoding="utf-8"))
        fields = {
            "active_activity_id",
            "active_activity_started_at",
            "pending_activity_id",
            "pending_activity_elapsed_seconds",
        }
        self.assertEqual(fields, fields & default_session().keys())
        self.assertEqual(fields, fields & template.keys())
        self.assertEqual({field: None for field in fields}, {field: default_session()[field] for field in fields})
        self.assertEqual({field: None for field in fields}, {field: template[field] for field in fields})


if __name__ == "__main__":
    unittest.main()
