import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.evaluation import summarize_evaluation  # noqa: E402


class EvaluationTests(unittest.TestCase):
    def test_optional_metadata_is_aggregated_without_mutating_events(self):
        events = [
            {
                "observation_id": "one",
                "recorded_at": "2026-09-13T12:00:00+00:00",
                "session_id": "s",
                "task_id": "task",
                "outcome": "incorrect",
                "elapsed_seconds": 30,
                "assistance": {"levels_revealed": ["H1"]},
                "learner_self_confidence": "high",
                "assessment_result": {"score": 2, "max_score": 10},
                "evaluation_context": {"stage": "mock", "protocol_id": "p1"},
                "error_tags": ["method_selection_error"],
            },
            {
                "observation_id": "two",
                "recorded_at": "2026-09-13T12:02:00+00:00",
                "session_id": "s",
                "task_id": "task",
                "outcome": "correct",
                "elapsed_seconds": 40,
                "assistance": {"levels_revealed": []},
                "learner_self_confidence": "medium",
                "assessment_result": {"score": 8, "max_score": 10},
                "evaluation_context": {"stage": "transfer"},
                "error_tags": ["method_selection_error"],
            },
            {
                "observation_id": "three",
                "recorded_at": "2026-09-13T12:10:00+00:00",
                "session_id": "s",
                "task_id": "delayed",
                "outcome": "correct",
                "elapsed_seconds": 20,
                "assistance": {"levels_revealed": []},
                "assessment_result": {"score": 9, "max_score": 10},
                "evaluation_context": {"stage": "delayed"},
            },
        ]
        before = [dict(event) for event in events]
        result = summarize_evaluation(events)
        self.assertEqual(90, result["active_study_seconds"])
        self.assertEqual(0.7, result["score_gain"])
        self.assertEqual(1, result["hints"])
        self.assertEqual(0, result["full_solution_exposure"])
        self.assertEqual(1, result["retries"])
        self.assertEqual(0.9, result["delayed_score"])
        self.assertEqual(0.8, result["transfer_score"])
        self.assertEqual(0.2, result["mock_score"])
        self.assertEqual(before, events)

    def test_missing_scores_are_reported_as_none(self):
        result = summarize_evaluation([{"observation_id": "old", "outcome": "correct"}])
        self.assertIsNone(result["score_gain"])
        self.assertIsNone(result["delayed_score"])
        self.assertEqual(0, result["active_study_seconds"])
