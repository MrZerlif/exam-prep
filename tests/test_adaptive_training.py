"""Behavior contracts for variant-3 adaptive training policy."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, "skill/exam-prep/scripts")

from exam_prep_lib.reducer import reduce_learning_state  # noqa: E402
from exam_prep_lib.assessment import FrozenAssessment  # noqa: E402
from exam_prep_lib.scheduler import build_review_queue  # noqa: E402
from exam_prep_lib.readiness import blueprint_hash, build_learner_exam_readiness  # noqa: E402
from exam_prep_lib.planner import build_adaptive_guidance  # noqa: E402
from exam_prep import main  # noqa: E402


SYLLABUS = {
    "schema_version": 1,
    "concepts": {
        "topic": {
            "title": "Topic",
            "prerequisites": [],
            "importance": 0.5,
            "frequency": 0.5,
            "expected_points": 1,
            "estimated_learning_minutes": 10,
        }
    },
}
COURSE = {"schema_version": 2, "scheduler": {"mode": "normal"}}
BASE = {
    "schema_version": 2,
    "target_id": "topic",
    "capability_id": "delayed_recall",
    "task_type": "delayed_recall",
    "outcome": "correct",
    "assistance": {"levels_revealed": []},
    "error_tags": [],
    "diagnostic_confidence": "high",
    "source_refs": [],
    "assessment_integrity": "not_assessment",
}


def event(obs_id, timestamp, **overrides):
    return {
        **BASE,
        "observation_id": obs_id,
        "task_id": obs_id,
        "recorded_at": timestamp,
        "session_id": obs_id,
        **overrides,
    }


def frozen_assessment(assessment_id, prompt, capability_id="delayed_recall"):
    return FrozenAssessment.from_mapping({
        "assessment_id": assessment_id,
        "target_id": "topic",
        "capability_id": capability_id,
        "prompt": prompt,
        "rubric": {"correct": True},
        "expected_evidence": ["independent_work"],
        "source_refs": [],
        "difficulty": 0.5,
        "question_version": 1,
        "rubric_version": 1,
    })


class RetentionSeriesTests(unittest.TestCase):
    def test_two_spaced_independent_checks_are_required_for_mastered(self):
        history = []
        start = __import__("datetime").datetime.fromisoformat("2026-10-01T00:00:00+00:00")
        for index in range(20):
            at = (start + __import__("datetime").timedelta(minutes=index)).isoformat()
            history.append(event(f"problem-{index}", at, capability_id="independent_problem", task_type="independent_problem", session_id=f"prep-{index}"))
            history.append(event(f"transfer-{index}", at, capability_id="transfer", task_type="transfer", session_id=f"prep-{index}"))
            history.append(event(f"recall-{index}", at, capability_id="definition_recall", task_type="definition_recall", session_id=f"prep-{index}"))
        history.extend([
            event("first", "2026-10-01T08:20:00+00:00", session_id="check-1"),
            event("second", "2026-10-02T08:20:00+00:00", session_id="check-2"),
        ])
        result = reduce_learning_state(COURSE, SYLLABUS, history, {})
        state = result["concepts"]["topic"]
        self.assertEqual("mastered", state["mastery_status"])
        self.assertEqual(2, state["delayed_confirmations"]["valid_checks"])
        self.assertEqual("2026-10-02T08:20:00+00:00", state["evidence_maturity"]["retained"]["last_at"])
        self.assertAlmostEqual(8.0167, state["delayed_confirmations"]["first_check_delay_hours"], places=4)
        self.assertEqual(24.0, state["delayed_confirmations"]["second_check_delay_hours"])
        self.assertEqual(24.0, state["delayed_confirmations"]["last_interval_hours"])

    def test_equal_timestamp_block_attempts_cannot_forge_delayed_confirmation(self):
        result = reduce_learning_state(
            COURSE,
            SYLLABUS,
            [
                event("one", "2026-10-01T08:00:00+00:00", session_id="same"),
                event("two", "2026-10-01T08:00:00+00:00", session_id="same", task_id="two"),
            ],
            {},
        )
        state = result["concepts"]["topic"]
        self.assertEqual(0, state["delayed_confirmations"]["valid_checks"])

    def test_real_elapsed_time_is_not_rejected_for_reused_session_id(self):
        result = reduce_learning_state(
            COURSE,
            SYLLABUS,
            [
                event("prep", "2026-10-01T00:00:00+00:00", capability_id="independent_problem", task_type="independent_problem", session_id="still-open"),
                event("first", "2026-10-01T08:00:00+00:00", session_id="still-open"),
                event("second", "2026-10-02T08:00:00+00:00", session_id="still-open"),
            ],
            {},
        )
        state = result["concepts"]["topic"]
        self.assertEqual(2, state["delayed_confirmations"]["valid_checks"])

    def test_new_assessment_id_with_same_problem_hash_is_not_independent(self):
        first = frozen_assessment("assessment-1", "Use the same theorem.", "delayed_transfer")
        second = frozen_assessment("assessment-2", "Use the same theorem.", "delayed_transfer")
        self.assertNotEqual(first.spec_hash, second.spec_hash)
        self.assertEqual(first.question_hash, second.question_hash)
        events = [
            event("prep", "2026-10-01T00:00:00+00:00", capability_id="independent_problem", task_type="independent_problem"),
            event("one", "2026-10-01T08:00:00+00:00", capability_id="delayed_transfer", task_type="delayed_transfer", assessment_id=first.assessment_id, assessment_spec_hash=first.spec_hash, assessment_question_hash=first.question_hash, assessment_integrity="frozen_attempt"),
            event("two", "2026-10-02T08:00:00+00:00", capability_id="delayed_transfer", task_type="delayed_transfer", assessment_id=second.assessment_id, assessment_spec_hash=second.spec_hash, assessment_question_hash=second.question_hash, assessment_integrity="frozen_attempt"),
        ]
        result = reduce_learning_state(COURSE, SYLLABUS, events, {})
        self.assertEqual(1, result["concepts"]["topic"]["delayed_confirmations"]["valid_checks"])

    def test_theory_ticket_allows_closed_reproduction_of_same_content(self):
        course = {**COURSE, "exam": {"question_model": "ticket_list"}}
        first = frozen_assessment("ticket-1", "State the same theorem.")
        second = frozen_assessment("ticket-2", "State the same theorem.")
        events = [
            event("prep", "2026-10-01T00:00:00+00:00", capability_id="independent_problem", task_type="independent_problem"),
            event("one", "2026-10-01T08:00:00+00:00", assessment_id="ticket-1", assessment_spec_hash=first.spec_hash, assessment_question_hash=first.question_hash, assessment_integrity="frozen_attempt"),
            event("two", "2026-10-02T08:00:00+00:00", assessment_id="ticket-2", assessment_spec_hash=second.spec_hash, assessment_question_hash=second.question_hash, assessment_integrity="frozen_attempt"),
        ]
        result = reduce_learning_state(course, SYLLABUS, events, {})
        self.assertEqual(2, result["concepts"]["topic"]["delayed_confirmations"]["valid_checks"])

    def test_mixed_ticket_slots_classify_theory_recall_and_problem_novelty_separately(self):
        mixed = {
            **COURSE,
            "exam": {
                "question_model": "mixed",
                "ticket_slots": [
                    {"kind": "theory", "count": 1},
                    {"kind": "problem", "count": 1},
                ],
            },
        }
        theory_events = [
            event("prep", "2026-10-01T00:00:00+00:00", capability_id="definition_recall", task_type="definition_recall"),
            event("one", "2026-10-01T08:00:00+00:00", capability_id="delayed_recall", task_type="delayed_recall", assessment_id="ticket-1", assessment_question_hash=frozen_assessment("ticket-1", "State one theorem.").question_hash, assessment_integrity="frozen_attempt"),
            event("two", "2026-10-02T08:00:00+00:00", capability_id="delayed_recall", task_type="delayed_recall", assessment_id="ticket-2", assessment_question_hash=frozen_assessment("ticket-2", "State one theorem.").question_hash, assessment_integrity="frozen_attempt"),
        ]
        theory = reduce_learning_state(mixed, SYLLABUS, theory_events, {})
        self.assertEqual(2, theory["concepts"]["topic"]["delayed_confirmations"]["valid_checks"])

        problem_events = [
            event("prep-p", "2026-10-01T00:00:00+00:00", capability_id="independent_problem", task_type="independent_problem"),
            event("one-p", "2026-10-01T08:00:00+00:00", capability_id="delayed_transfer", task_type="delayed_transfer", assessment_id="problem-1", assessment_question_hash=frozen_assessment("problem-1", "Solve the same problem.", "delayed_transfer").question_hash, assessment_integrity="frozen_attempt"),
            event("two-p", "2026-10-02T08:00:00+00:00", capability_id="delayed_transfer", task_type="delayed_transfer", assessment_id="problem-2", assessment_question_hash=frozen_assessment("problem-2", "Solve the same problem.", "delayed_transfer").question_hash, assessment_integrity="frozen_attempt"),
        ]
        problem = reduce_learning_state(mixed, SYLLABUS, problem_events, {})
        self.assertEqual(1, problem["concepts"]["topic"]["delayed_confirmations"]["valid_checks"])

    def test_timing_override_and_exposure_cannot_create_retained_evidence(self):
        result = reduce_learning_state(
            COURSE,
            SYLLABUS,
            [
                event("prep", "2026-10-01T00:00:00+00:00", capability_id="independent_problem", task_type="independent_problem"),
                event("first", "2026-10-01T08:00:00+00:00"),
                event(
                    "second",
                    "2026-10-02T08:00:00+00:00",
                    outcome="solution_seen",
                    evidence_facets=["retained"],
                    assistance={"requested": True, "levels_revealed": ["H5"], "scaffold_types": ["full_solution"], "partial_transformation_shown": True, "full_solution_viewed": True},
                ),
            ],
            {},
        )
        state = result["concepts"]["topic"]
        self.assertEqual(0, state["delayed_confirmations"]["valid_checks"])
        self.assertNotEqual("mastered", state["mastery_status"])

    def test_first_confirmation_requires_full_eight_hours(self):
        result = reduce_learning_state(
            COURSE,
            SYLLABUS,
            [
                event("prep", "2026-10-01T00:00:00+00:00", capability_id="independent_problem", task_type="independent_problem"),
                event("too-soon", "2026-10-01T07:59:00+00:00"),
            ],
            {},
        )
        self.assertEqual(0, result["concepts"]["topic"]["delayed_confirmations"]["valid_checks"])

    def test_unknown_time_cannot_confirm_retention_even_with_claimed_facet(self):
        result = reduce_learning_state(
            COURSE,
            SYLLABUS,
            [event("unknown", None, evidence_facets=["retained"])],
            {},
        )
        state = result["concepts"]["topic"]
        self.assertEqual(0, state["delayed_confirmations"]["valid_checks"])
        self.assertEqual(0, state["evidence_maturity"]["retained"]["count"])

    def test_second_confirmation_requires_full_twenty_four_hours_from_latest_work(self):
        for elapsed, expected in ((23, 1), (24, 2)):
            result = reduce_learning_state(
                COURSE,
                SYLLABUS,
                [
                    event("prep", "2026-10-01T00:00:00+00:00", capability_id="independent_problem", task_type="independent_problem"),
                    event("first", "2026-10-01T08:00:00+00:00"),
                    event("between", "2026-10-02T08:00:00+00:00", capability_id="calculation", task_type="calculation"),
                    event("second", "2026-10-03T07:59:00+00:00" if elapsed == 23 else "2026-10-03T08:00:00+00:00"),
                ],
                {},
            )
            self.assertEqual(expected, result["concepts"]["topic"]["delayed_confirmations"]["valid_checks"])

    def test_course_rejects_invalid_retention_policy_instead_of_weakening_it(self):
        with self.assertRaisesRegex(ValueError, "positive numbers"):
            reduce_learning_state(
                {**COURSE, "retention_policy": {"version": 1, "first_check_after_hours": 0, "subsequent_check_after_hours": 24}},
                SYLLABUS,
                [],
                {},
            )

    def test_substantive_failure_resets_current_confirmation_series(self):
        result = reduce_learning_state(
            COURSE,
            SYLLABUS,
            [
                event("first", "2026-10-01T08:00:00+00:00"),
                event("fail", "2026-10-02T08:00:00+00:00", outcome="incorrect"),
                event("second", "2026-10-04T08:00:00+00:00"),
            ],
            {},
        )
        state = result["concepts"]["topic"]
        self.assertEqual(1, state["delayed_confirmations"]["valid_checks"])


class RecoverableErrorLoadTests(unittest.TestCase):
    def test_independent_successes_recover_old_error_load(self):
        events = [
            event("bad", "2026-10-01T08:00:00+00:00", outcome="incorrect", capability_id="calculation", task_type="calculation"),
            event("good-1", "2026-10-01T09:00:00+00:00", capability_id="calculation", task_type="calculation"),
            event("good-2", "2026-10-01T10:00:00+00:00", capability_id="calculation", task_type="calculation"),
        ]
        queue = build_review_queue(events, {}, COURSE, __import__("datetime").datetime.fromisoformat("2026-10-01T10:01:00+00:00"), SYLLABUS)
        self.assertEqual(0, queue["items"]["topic"]["error_load"])


class LearnerReadinessTests(unittest.TestCase):
    def test_blueprint_hash_matches_canonical_unicode_document_hash(self):
        from exam_prep_lib.storage import StudyStore
        exam = {"title": "Экзамен", "revision": 2}
        self.assertEqual(StudyStore.hash_document(exam), blueprint_hash(exam))

    def setUp(self):
        self.course = {
            "exam": {
                "revision": 3,
                "time_limit_minutes": 90,
                "question_model": "problem_set",
            },
            "readiness_policy": {"version": 1, "target_score_fraction": 0.75},
        }
        self.syllabus = {
            "schema_version": 2,
            "learning_targets": [{"target_id": "topic", "prerequisites": []}],
        }
        self.derived = {
            "targets": {
                "topic": {
                    "progress": {
                        "exam_ready": True,
                        "confirmed_after_break": True,
                    }
                }
            }
        }
        current_hash = blueprint_hash(self.course["exam"])
        self.attempts = [
            {
                "session_id": session_id,
                "disposition": "submitted",
                "started_at": f"{day}T11:00:00+00:00",
                "ended_at": f"{day}T12:00:00+00:00",
                "time_limit_minutes": 90,
                "blueprint_revision": 3,
                "blueprint_hash": current_hash,
                "assessment_ids": ids,
                "assessment_hashes": [],
            }
            for session_id, day, ids in (
                ("mock-a", "2026-10-30", ["a", "b"]),
                ("mock-b", "2026-10-31", ["a", "c"]),
            )
        ]
        self.events = []
        for attempt in self.attempts:
            for assessment_id in attempt["assessment_ids"]:
                self.events.append({
                    "observation_id": f"{attempt['session_id']}-{assessment_id}",
                    "session_id": attempt["session_id"],
                    "recorded_at": attempt["started_at"].replace("11:00", "11:30"),
                    "target_id": "topic",
                    "capability_id": "delayed_recall",
                    "task_id": assessment_id,
                    "assessment_id": assessment_id,
                    "assessment_spec_hash": f"hash-{assessment_id}",
                    "assessment_question_hash": f"question-{assessment_id}",
                    "assessment_integrity": "frozen_attempt",
                    "exam_revision": 3,
                    "exam_hash": current_hash,
                    "outcome": "correct",
                    "assessment_result": ({"score": 4, "max_score": 5} if assessment_id == "a" and attempt["session_id"] == "mock-a" else ({"score": 0.5, "max_score": 1} if attempt["session_id"] == "mock-a" else ({"score": 9, "max_score": 10} if assessment_id == "a" else {"score": 1, "max_score": 1}))),
                    "assistance": {"levels_revealed": []},
                })

    def test_two_latest_full_distinct_mocks_and_ready_targets_confirm_exam_readiness(self):
        result = build_learner_exam_readiness(
            self.course, self.syllabus, self.derived, self.attempts, self.events
        )
        self.assertEqual("ready", result["status"])
        self.assertEqual([0.75, 0.9091], result["mock_scores"])

    def test_unicode_blueprint_hash_matches_store_canonicalization(self):
        from exam_prep_lib.storage import StudyStore
        exam = {"title": "Курс: теория", "revision": 1}
        self.assertEqual(StudyStore.hash_document(exam), blueprint_hash(exam))

    def test_no_targets_cannot_produce_overall_exam_readiness(self):
        result = build_learner_exam_readiness(
            self.course, {"learning_targets": []}, {"targets": {}}, self.attempts, self.events
        )
        self.assertEqual("unknown", result["status"])

    def test_missing_target_threshold_keeps_learner_readiness_unknown(self):
        course = {"exam": {"time_limit_minutes": 90}, "readiness_policy": {"version": 1, "target_score_fraction": None}}
        result = build_learner_exam_readiness(
            course, self.syllabus, self.derived, self.attempts, self.events
        )
        self.assertEqual("unknown", result["status"])
        self.assertIsNone(result["target_score_fraction"])

    def test_latest_low_mock_score_requires_a_full_mock_retake(self):
        low = next(item for item in self.events if item["session_id"] == "mock-b" and item["assessment_id"] == "c")
        low["outcome"] = "incorrect"
        low["assessment_result"] = {"score": 0, "max_score": 1}
        next(item for item in self.events if item["session_id"] == "mock-b" and item["assessment_id"] == "a")["assessment_result"] = {"score": 0, "max_score": 10}
        result = build_learner_exam_readiness(
            self.course, self.syllabus, self.derived, self.attempts, self.events
        )
        self.assertEqual("not_ready", result["status"])
        self.assertIn("below", result["reason"])

    def test_same_mock_set_twice_does_not_confirm_exam_readiness(self):
        self.attempts[1]["assessment_ids"] = self.attempts[0]["assessment_ids"]
        self.events.append({
            **self.events[-1],
            "observation_id": "mock-b-b",
            "session_id": "mock-b",
            "assessment_id": "b",
            "assessment_spec_hash": "hash-b",
        })
        result = build_learner_exam_readiness(
            self.course, self.syllabus, self.derived, self.attempts, self.events
        )
        self.assertEqual("unknown", result["status"])
        self.assertIn("distinct", result["reason"])

    def test_stopped_complete_mock_is_rederived_as_invalid(self):
        attempts = [dict(item) for item in self.attempts]
        attempts[-1]["disposition"] = "stopped"
        attempts[-1]["valid"] = True  # stale frozen snapshot must not override disposition
        result = build_learner_exam_readiness(
            self.course, self.syllabus, self.derived, attempts, self.events
        )
        self.assertEqual("not_ready", result["status"])
        self.assertIn("invalid", result["reason"])

    def test_distinct_ids_with_identical_question_content_are_not_distinct_material(self):
        events = [dict(item) for item in self.events]
        for item in events:
            if item["assessment_id"] in {"b", "c"}:
                item["assessment_question_hash"] = "same-question"
        result = build_learner_exam_readiness(
            self.course, self.syllabus, self.derived, self.attempts, events
        )
        self.assertEqual("unknown", result["status"])
        self.assertIn("distinct assessment material", result["reason"])

    def test_superseded_mock_attempt_is_rederived_as_incomplete(self):
        original = self.events[-1]
        replacement = {
            **original,
            "observation_id": "mock-b-c-correction",
            "supersedes_observation_id": original["observation_id"],
            "outcome": "incorrect",
            "assessment_result": {"score": 0, "max_score": 1},
        }
        self.events.append(replacement)
        result = build_learner_exam_readiness(
            self.course, self.syllabus, self.derived, self.attempts, self.events
        )
        self.assertEqual("not_ready", result["status"])
        self.assertIn("repair", result["reason"])

    def test_missing_per_question_score_keeps_readiness_unknown(self):
        del self.events[-1]["assessment_result"]
        self.events[-1]["outcome"] = "partial"
        result = build_learner_exam_readiness(
            self.course, self.syllabus, self.derived, self.attempts, self.events
        )
        self.assertEqual("unknown", result["status"])
        self.assertIn("missing", result["reason"])

    def test_newest_incomplete_attempt_invalidates_old_readiness_pair(self):
        self.attempts.append({
            **self.attempts[-1],
            "session_id": "mock-c",
            "started_at": "2026-11-01T11:00:00+00:00",
            "ended_at": "2026-11-01T12:00:00+00:00",
            "assessment_ids": ["a", "d"],
        })
        result = build_learner_exam_readiness(
            self.course, self.syllabus, self.derived, self.attempts, self.events
        )
        self.assertEqual("not_ready", result["status"])
        self.assertIn("incomplete", result["reason"])

    def test_same_capability_independent_post_mock_repair_can_close_gap(self):
        self.course["readiness_policy"]["target_score_fraction"] = 0.5
        failed = next(item for item in self.events if item["session_id"] == "mock-b" and item["assessment_id"] == "c")
        failed["outcome"] = "incorrect"
        failed["assessment_result"] = {"score": 0, "max_score": 1}
        repair = {
            "observation_id": "valid-repair",
            "session_id": "study-after",
            "recorded_at": "2026-11-02T13:00:00+00:00",
            "target_id": "topic",
            "capability_id": "delayed_recall",
            "task_id": "repair",
            "assessment_integrity": "not_assessment",
            "outcome": "correct",
            "assistance": {"levels_revealed": []},
        }
        result = build_learner_exam_readiness(
            self.course, self.syllabus, self.derived, self.attempts, [*self.events, repair]
        )
        self.assertEqual("ready", result["status"])

    def test_superseded_repair_does_not_close_mock_gap(self):
        self.course["readiness_policy"]["target_score_fraction"] = 0.5
        failed = next(item for item in self.events if item["session_id"] == "mock-b" and item["assessment_id"] == "c")
        failed["outcome"] = "incorrect"
        failed["assessment_result"] = {"score": 0, "max_score": 1}
        repair = {
            "observation_id": "old-repair",
            "session_id": "study-after",
            "recorded_at": "2026-11-02T13:00:00+00:00",
            "target_id": "topic",
            "capability_id": "delayed_recall",
            "task_id": "repair",
            "assessment_integrity": "not_assessment",
            "outcome": "correct",
            "assistance": {"levels_revealed": []},
        }
        replacement = {**repair, "observation_id": "repair-correction", "supersedes_observation_id": "old-repair", "outcome": "incorrect"}
        result = build_learner_exam_readiness(
            self.course, self.syllabus, self.derived, self.attempts, [*self.events, repair, replacement]
        )
        self.assertEqual("not_ready", result["status"])
        self.assertIn("repair", result["reason"])

    def test_wrong_capability_does_not_repair_mock_gap(self):
        self.course["readiness_policy"]["target_score_fraction"] = 0.5
        attempt_event = next(item for item in self.events if item["session_id"] == "mock-b" and item["assessment_id"] == "c")
        attempt_event["outcome"] = "incorrect"
        repair = {
            "observation_id": "wrong-repair",
            "session_id": "study-after",
            "recorded_at": "2026-11-02T13:00:00+00:00",
            "target_id": "topic",
            "capability_id": "calculation",
            "task_id": "repair",
            "assessment_integrity": "not_assessment",
            "outcome": "correct",
            "assistance": {"levels_revealed": []},
        }
        result = build_learner_exam_readiness(
            self.course, self.syllabus, self.derived, self.attempts, [*self.events, repair]
        )
        self.assertEqual("not_ready", result["status"])
        self.assertIn("repair", result["reason"])


class RuntimeAdaptiveUxTests(unittest.TestCase):
    def cli(self, root, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--workspace", str(root), *args])
        return code, json.loads(output.getvalue())

    def test_empty_triage_file_is_an_explicit_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.cli(root, "init")
            syllabus_path = root / "syllabus.json"
            syllabus_path.write_text(json.dumps({"schema_version": 2, "learning_targets": [{"target_id": "topic", "prerequisites": []}]}), encoding="utf-8")
            self.cli(root, "load-syllabus", str(syllabus_path))
            triage_path = root / "triage.json"
            triage_path.write_text('{"ratings": {}}', encoding="utf-8")
            code, result = self.cli(root, "triage", str(triage_path))
            self.assertEqual(0, code)
            self.assertEqual("triage_skipped", result["status"])
            self.assertEqual({}, result["ratings"])

    def test_no_check_topic_teaching_is_canonical_exposure_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.cli(root, "init")
            syllabus_path = root / "syllabus.json"
            syllabus_path.write_text(json.dumps({
                "schema_version": 2,
                "learning_targets": [{"target_id": "topic", "prerequisites": []}],
            }), encoding="utf-8")
            self.cli(root, "load-syllabus", str(syllabus_path))
            lesson = {
                "schema_version": 2,
                "observation_id": "lesson-exposure",
                "target_id": "topic",
                "task_id": "worked-example-1",
                "capability_id": "worked_example",
                "task_type": "worked_example",
                "outcome": "solution_seen",
                "assistance": {
                    "requested": True,
                    "levels_revealed": ["H5"],
                    "scaffold_types": ["full_solution"],
                    "partial_transformation_shown": True,
                    "full_solution_viewed": True,
                },
                "error_tags": [],
                "diagnostic_confidence": "high",
                "source_refs": [],
            }
            lesson_path = root / "lesson.json"
            lesson_path.write_text(json.dumps(lesson), encoding="utf-8")
            code, _receipt = self.cli(root, "record-observation", str(lesson_path))
            self.assertEqual(0, code)
            from exam_prep_lib.storage import StudyStore
            event_record = StudyStore.for_exam_prep(root).read_complete_observations()[0]
            self.assertEqual("solution_seen", event_record["outcome"])
            status = self.cli(root, "status")[1]
            self.assertEqual(1, status["topic_progress"]["started"])
            self.assertEqual(0, status["topic_progress"]["independent_correct"])
            self.assertEqual(0, status["topic_progress"]["confirmed_after_break"])

    def test_next_cli_adapts_to_last_recorded_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.cli(root, "init")
            syllabus_path = root / "syllabus.json"
            syllabus_path.write_text(json.dumps({"schema_version": 2, "learning_targets": [{"target_id": "topic", "prerequisites": [], "estimated_learning_minutes": 20}]}), encoding="utf-8")
            self.cli(root, "load-syllabus", str(syllabus_path))
            first = self.cli(root, "next", "--minutes", "25")[1]
            self.assertEqual("brief_explanation_plus_example", first["transition"])
            proposal = {
                "schema_version": 2,
                "observation_id": "cli-failure",
                "target_id": "topic",
                "task_id": "problem-1",
                "capability_id": "calculation",
                "task_type": "calculation",
                "outcome": "incorrect",
                "assistance": {"levels_revealed": []},
                "error_tags": ["algebra_error"],
                "diagnostic_confidence": "high",
                "source_refs": [],
            }
            proposal_path = root / "failure.json"
            proposal_path.write_text(json.dumps(proposal), encoding="utf-8")
            code, _result = self.cli(root, "record-observation", str(proposal_path))
            self.assertEqual(0, code)
            next_activity = self.cli(root, "next", "--minutes", "25")[1]
            self.assertEqual("repair_first_error", next_activity["transition"])
            self.assertEqual(1, next_activity["recommended_block_size"])

    def test_cli_status_separates_all_four_topic_progress_measures(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.cli(root, "init")
            status = self.cli(root, "status")[1]
            self.assertEqual(
                {"started": 0, "independent_correct": 0, "confirmed_after_break": 0, "exam_ready": 0, "target_count": 0},
                status["topic_progress"],
            )
            self.assertEqual("unknown", status["learner_exam_readiness"]["status"])

    def test_transition_guidance_targets_one_item_after_failure_or_hint(self):
        failed = build_adaptive_guidance({"outcome": "incorrect"}, 25, 45)
        hinted = build_adaptive_guidance({"outcome": "correct", "assistance": {"levels_revealed": ["H1"]}}, 25, 45)
        self.assertEqual(1, failed["recommended_block_size"])
        self.assertEqual("repair_first_error", failed["transition"])
        self.assertEqual("parallel_without_hint", hinted["transition"])

    def test_transition_guidance_after_exposure_requires_fresh_independent_work(self):
        result = build_adaptive_guidance({"outcome": "correct", "assistance": {"levels_revealed": ["H5"], "full_solution_viewed": True}}, 25, 45)
        self.assertEqual("independent_after_exposure", result["transition"])

    def test_transition_guidance_returns_to_transfer_after_independent_success(self):
        result = build_adaptive_guidance({"outcome": "correct", "assistance": {"levels_revealed": []}}, 25, 45)
        self.assertEqual("method_or_transfer", result["transition"])


if __name__ == "__main__":
    unittest.main()
