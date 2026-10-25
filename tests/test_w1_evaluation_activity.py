import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.activity import consume_activity, finish_activity, start_activity  # noqa: E402
from exam_prep_lib.defaults import default_session  # noqa: E402
from exam_prep_lib.evaluation import summarize_evaluation  # noqa: E402


START = "2026-10-25T10:00:00+00:00"


def event(observation_id, **updates):
    value = {
        "observation_id": observation_id,
        "recorded_at": START,
        "task_id": observation_id,
        "outcome": "correct",
        "elapsed_seconds": 0,
        "assistance": {"levels_revealed": []},
        "error_tags": [],
    }
    value.update(updates)
    return value


class EvaluationAssistanceTests(unittest.TestCase):
    def test_h0_is_independent_and_not_counted_as_hint(self):
        events = [
            event("h0", outcome="incorrect", recorded_at="2026-10-25T10:00:00+00:00", assistance={"levels_revealed": ["H0"]}),
            event("h1", recorded_at="2026-10-25T10:01:00+00:00", assistance={"levels_revealed": ["H1"]}),
            event("after-exposure", recorded_at="2026-10-25T10:02:00+00:00", assessment_integrity="post_exposure_attempt"),
            event("independent", recorded_at="2026-10-25T10:10:00+00:00", assistance={"levels_revealed": ["H0"]}),
        ]

        result = summarize_evaluation(events)

        self.assertEqual(2, result["hints"])
        self.assertEqual(600, result["time_to_independent_success"])

    def test_late_recording_time_is_reported_outside_active_study_time(self):
        result = summarize_evaluation(
            [
                event("finished", elapsed_seconds=30),
                event(
                    "late-recording",
                    elapsed_seconds=200,
                    elapsed_includes_recording_delay=True,
                ),
            ]
        )

        self.assertEqual(30, result["active_study_seconds"])
        self.assertEqual(200, result["recording_delay_seconds"])
        self.assertEqual(1, result["recording_delay_event_count"])

    def test_superseded_event_is_absent_from_evaluation_aggregates(self):
        result = summarize_evaluation(
            [
                event("old", outcome="incorrect", task_id="same", error_tags=["algebra_error"]),
                event(
                    "new",
                    task_id="same",
                    supersedes_observation_id="old",
                    assessment_result={"score": 1, "max_score": 1},
                ),
            ]
        )

        self.assertEqual(0, result["retries"])
        self.assertEqual({}, result["recurring_errors"])
        self.assertEqual(0, result["time_to_independent_success"])


class ActivityRecordingDelayTests(unittest.TestCase):
    def test_consuming_active_timer_marks_recording_delay(self):
        active = start_activity(default_session(), "task-1", START)
        consumed = consume_activity(active.session, "task-1", "2026-10-25T10:00:17+00:00")

        self.assertEqual(17, consumed.elapsed_seconds)
        self.assertTrue(consumed.elapsed_includes_recording_delay)

    def test_consuming_finished_timer_does_not_mark_recording_delay(self):
        active = start_activity(default_session(), "task-1", START)
        finished = finish_activity(active.session, "2026-10-25T10:00:17+00:00")
        consumed = consume_activity(finished.session, "task-1", "2026-10-25T10:10:00+00:00")

        self.assertEqual(17, consumed.elapsed_seconds)
        self.assertFalse(consumed.elapsed_includes_recording_delay)


if __name__ == "__main__":
    unittest.main()
