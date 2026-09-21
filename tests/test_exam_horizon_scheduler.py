"""Regression tests: review intervals must compress as the exam approaches,
and must never be scheduled after the exam."""

import sys
import unittest
from datetime import datetime, timedelta, timezone


sys.path.insert(0, "skill/exam-prep/scripts")

from exam_prep_lib.scheduler import (  # noqa: E402
    _configured_timezone,
    exam_time,
    build_review_queue,
)


NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


def course_with_exam_in(**delta):
    exam_time = NOW + timedelta(**delta)
    return {
        "schema_version": 1,
        "exam": {"date": exam_time.isoformat()},
        "scheduler": {"mode": "exam_cram", "max_review_interval_hours": 72},
    }


def event(outcome="correct", task_type="independent_problem"):
    return {
        "observation_id": "obs-1",
        "concept_id": "chain_rule",
        "task_type": task_type,
        "outcome": outcome,
        "recorded_at": NOW.isoformat(),
        "session_id": "s1",
        "assistance": {
            "requested": False,
            "levels_revealed": [],
            "scaffold_types": [],
            "partial_transformation_shown": False,
            "full_solution_viewed": False,
        },
        "error_tags": [],
        "diagnostic_confidence": "high",
        "learner_self_confidence": "medium",
        "source_refs": [],
        "expected_seconds": None,
        "elapsed_seconds": None,
    }


class ExamHorizonSchedulerTests(unittest.TestCase):
    def test_naive_exam_date_uses_configured_fixed_offset(self):
        course = {
            "exam": {"date": "2026-09-14T10:00:00", "timezone": "+03:00"}
        }
        parsed = exam_time(course, NOW)
        self.assertEqual(
            datetime(2026, 9, 14, 7, 0, tzinfo=timezone.utc),
            parsed.astimezone(timezone.utc),
        )

    def test_exam_timezone_defaults_to_utc_and_preserves_aware_date(self):
        naive = exam_time({"exam": {"date": "2026-09-14T10:00:00"}}, NOW)
        self.assertEqual(timezone.utc, naive.tzinfo)
        aware = exam_time(
            {"exam": {"date": "2026-09-14T10:00:00-04:00", "timezone": "+03:00"}},
            NOW,
        )
        self.assertEqual(
            datetime(2026, 9, 14, 14, 0, tzinfo=timezone.utc),
            aware.astimezone(timezone.utc),
        )


    def test_aware_exam_date_does_not_require_configured_timezone(self):
        aware = exam_time(
            {"exam": {"date": "2026-09-14T10:00:00-04:00", "timezone": "Not/AZone"}},
            NOW,
        )
        self.assertEqual(
            datetime(2026, 9, 14, 14, 0, tzinfo=timezone.utc),
            aware.astimezone(timezone.utc),
        )

    def test_supported_timezone_forms_are_deterministic(self):
        self.assertEqual(timezone.utc, _configured_timezone("UTC"))
        self.assertEqual(timezone.utc, _configured_timezone("Z"))
        self.assertEqual(timedelta(hours=3), _configured_timezone("+03:00").utcoffset(NOW))
        self.assertEqual(timedelta(hours=-5, minutes=-30), _configured_timezone("-05:30").utcoffset(NOW))

    def test_invalid_timezone_is_rejected(self):
        with self.assertRaises(ValueError):
            exam_time(
                {"exam": {"date": "2026-09-14T10:00:00", "timezone": "+24:00"}},
                NOW,
            )
        with self.assertRaises(ValueError):
            exam_time(
                {"exam": {"date": "2026-09-14T10:00:00", "timezone": "Not/AZone"}},
                NOW,
            )
    def test_intervals_shrink_as_exam_approaches(self):
        interval_7_days = build_review_queue(
            [event()], {}, course_with_exam_in(days=7), NOW
        )["items"]["chain_rule"]["interval_hours"]
        interval_24_hours = build_review_queue(
            [event()], {}, course_with_exam_in(hours=24), NOW
        )["items"]["chain_rule"]["interval_hours"]
        interval_3_hours = build_review_queue(
            [event()], {}, course_with_exam_in(hours=3), NOW
        )["items"]["chain_rule"]["interval_hours"]
        self.assertGreater(interval_7_days, interval_24_hours)
        self.assertGreater(interval_24_hours, interval_3_hours)

    def test_due_at_never_lands_after_the_exam(self):
        for hours in (72, 24, 3, 0.5):
            course = course_with_exam_in(hours=hours)
            queue = build_review_queue([event()], {}, course, NOW)
            due_at = datetime.fromisoformat(queue["items"]["chain_rule"]["due_at"])
            exam_at = datetime.fromisoformat(course["exam"]["date"])
            with self.subTest(hours=hours):
                self.assertLessEqual(due_at, exam_at)

    def test_exam_already_passed_falls_back_to_normal_spacing(self):
        no_exam_course = {
            "schema_version": 1,
            "exam": {"date": None},
            "scheduler": {"mode": "exam_cram", "max_review_interval_hours": 72},
        }
        baseline = build_review_queue([event()], {}, no_exam_course, NOW)
        baseline_interval = baseline["items"]["chain_rule"]["interval_hours"]

        passed_course = course_with_exam_in(hours=-5)
        queue = build_review_queue([event()], {}, passed_course, NOW)
        # A passed exam gives no meaningful horizon to compress against, so
        # it must behave identically to having no exam date at all - not get
        # squeezed as if the (already-gone) exam were still imminent.
        self.assertEqual(queue["items"]["chain_rule"]["interval_hours"], baseline_interval)

    def test_missing_exam_date_falls_back_to_normal_spacing(self):
        course = {
            "schema_version": 1,
            "exam": {"date": None},
            "scheduler": {"mode": "exam_cram", "max_review_interval_hours": 72},
        }
        far_future_course = course_with_exam_in(days=365)
        queue = build_review_queue([event()], {}, course, NOW)
        far_future_queue = build_review_queue([event()], {}, far_future_course, NOW)
        # With no exam date at all, spacing should match a far-away exam
        # (no meaningful compression either way), not a close one.
        self.assertEqual(
            queue["items"]["chain_rule"]["interval_hours"],
            far_future_queue["items"]["chain_rule"]["interval_hours"],
        )

    def test_very_close_exam_still_yields_a_positive_interval(self):
        course = course_with_exam_in(minutes=20)
        queue = build_review_queue([event()], {}, course, NOW)
        self.assertGreater(queue["items"]["chain_rule"]["interval_hours"], 0)


if __name__ == "__main__":
    unittest.main()
