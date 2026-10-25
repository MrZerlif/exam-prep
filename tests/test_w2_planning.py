import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.optimizer import rank_source_aware_targets  # noqa: E402
from exam_prep_lib.planner import forecast_plan  # noqa: E402
from exam_prep_lib.scheduler import select_next_activity  # noqa: E402


NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)
SYLLABUS = {
    "schema_version": 2,
    "learning_targets": [
        {"target_id": "z-syllabus-first", "prerequisites": [], "estimated_learning_minutes": 20},
        {"target_id": "a-id-first", "prerequisites": [], "estimated_learning_minutes": 20},
    ],
}
COURSE = {"exam": {}, "scheduler": {"mode": "exam_cram"}}


class W2PlanningTests(unittest.TestCase):
    def test_scheduler_breaks_equal_scores_by_syllabus_order(self):
        selected = select_next_activity(SYLLABUS, {}, {}, COURSE, NOW, 25)

        self.assertEqual("z-syllabus-first", selected["concept_id"])

    def test_triage_rating_breaks_ties_only_for_targets_without_evidence(self):
        selected = select_next_activity(
            SYLLABUS,
            {},
            {},
            COURSE,
            NOW,
            25,
            self_ratings={"z-syllabus-first": 2, "a-id-first": 0},
        )

        self.assertEqual("a-id-first", selected["concept_id"])

    def test_optimizer_preserves_syllabus_order_for_equal_scores(self):
        ranked = rank_source_aware_targets(SYLLABUS, {}, {}, COURSE, NOW, 25)

        self.assertEqual(
            ["z-syllabus-first", "a-id-first"],
            [item["target_id"] for item in ranked],
        )

    def test_forecast_reports_coverage_and_budget_pace(self):
        syllabus = {
            "schema_version": 2,
            "learning_targets": [
                {"target_id": "t1", "prerequisites": [], "estimated_learning_minutes": 40},
                {"target_id": "t2", "prerequisites": [], "estimated_learning_minutes": 40},
            ],
        }
        concepts = {
            "t1": {"mastery_status": "practicing", "evidence": {"failures": 1}},
            "t2": {"mastery_status": "unseen", "evidence": {"failures": 0}},
        }

        result = forecast_plan(syllabus, concepts, {}, COURSE, NOW, days=1, minutes_per_day=30)

        self.assertEqual(
            {
                "total_targets": 2,
                "targets_touched": 1,
                "targets_without_evidence": 1,
                "available_minutes": 30,
                "budget_dates": ["2026-10-26"],
                "minutes_per_target": 15,
                "required_targets_per_hour": 4.0,
                "pace_at_risk": True,
            },
            result["coverage"],
        )

    def test_course_budget_only_counts_dates_from_today_through_exam(self):
        course = {
            **COURSE,
            "exam": {"date": "2026-10-30", "timezone": "Europe/Moscow"},
            "time_budget": {
                "available_minutes_by_day": {
                    "2026-10-24": 120,
                    "2026-10-25": 120,
                    "2026-10-26": 300,
                    "2026-10-27": 300,
                    "2026-10-28": 300,
                    "2026-10-29": 300,
                    "2026-10-30": 300,
                    "2026-10-31": 300,
                }
            },
        }
        fixed_now = datetime(2026, 10, 26, 0, tzinfo=timezone.utc)

        result = forecast_plan(SYLLABUS, {}, {}, course, fixed_now)

        self.assertEqual(1500, result["coverage"]["available_minutes"])
        self.assertEqual(
            ["2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30"],
            result["coverage"]["budget_dates"],
        )

    def test_planning_timezone_sets_budget_start_date_when_exam_timezone_is_absent(self):
        course = {
            **COURSE,
            "planning": {"timezone": "America/Los_Angeles"},
            "time_budget": {
                "available_minutes_by_day": {
                    "2026-10-24": 100,
                    "2026-10-25": 100,
                    "2026-10-26": 100,
                }
            },
        }

        result = forecast_plan(SYLLABUS, {}, {}, course, NOW)

        self.assertEqual(200, result["coverage"]["available_minutes"])
        self.assertEqual(["2026-10-25", "2026-10-26"], result["coverage"]["budget_dates"])


if __name__ == "__main__":
    unittest.main()
