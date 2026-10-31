"""Regression checks from the independent adaptive-training review."""

import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tests.test_adaptive_training import (
    COURSE, SYLLABUS, event, frozen_assessment,
)
from tests import test_adaptive_training as adaptive_fixtures
from tests import test_mock_exam_blueprint as mock_fixtures
from tests.test_mock_exam_blueprint import observation, spec
from exam_prep_lib.assessment_integrity import assess_attempt_evidence
from exam_prep_lib.readiness import blueprint_hash, build_learner_exam_readiness, rederive_mock_attempts
from exam_prep_lib.reducer import reduce_learning_state
from exam_prep_lib.scheduler import build_review_queue
from exam_prep_lib.storage import StudyStore


class MockCompletenessRegressionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = mock_fixtures.MockExamBlueprintTests()
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.tearDown()

    def test_cli_undersized_mock_is_not_a_full_attempt(self):
        fixture = self.fixture
        fixture.ready_with_ticket_pool(pool_size=2)
        fixture.set_exam_blueprint(question_count=10, time_limit_minutes=20)
        started = fixture.cli("exam")
        self.assertEqual(2, len(started["tickets"]))
        for index, ticket in enumerate(started["tickets"]):
            path = fixture.write(f"answer-{index}.json", observation(
                f"answer-{index}", ticket["assessment_id"],
                assessment_result={"score": 1, "max_score": 1},
            ))
            fixture.cli("record-observation", str(path))
        attempt = fixture.cli("end-session")["summary"]["learner_mock_attempt"]
        self.assertFalse(attempt["valid"])
        self.assertFalse(started["blueprint_coverage"]["complete"])
        self.assertEqual(10, started["blueprint_coverage"]["required_questions"])

    def test_corrected_mock_grade_is_one_attempt_at_submission_and_replay(self):
        fixture = self.fixture
        fixture.ready_with_ticket_pool(pool_size=1)
        fixture.set_exam_blueprint(question_count=1, time_limit_minutes=20)
        fixture.cli("exam")
        bad = observation("bad", "ticket-1", "incorrect", {"score": 0, "max_score": 1})
        fixed = observation("fixed", "ticket-1", "correct", {"score": 1, "max_score": 1})
        fixed["supersedes_observation_id"] = "bad"
        fixture.cli("record-observation", str(fixture.write("bad.json", bad)))
        fixture.cli("record-observation", str(fixture.write("fixed.json", fixed)))
        submitted = fixture.cli("end-session")["summary"]["learner_mock_attempt"]
        store = StudyStore.for_exam_prep(fixture.root)
        course = json.loads((store.state_path / "course.json").read_text())
        syllabus = json.loads((store.state_path / "syllabus.json").read_text())
        replayed = rederive_mock_attempts(
            [submitted], store.read_complete_observations(), course, syllabus,
        )[0]
        for attempt in (submitted, replayed):
            self.assertTrue(attempt["valid"])
            self.assertEqual(1, attempt["questions"][0]["attempt_count"])
            self.assertEqual(1, attempt["score_fraction"])
        self.assertEqual(2, len(store.read_complete_observations()))

    def test_two_actual_mock_attempts_remain_invalid_without_a_grade_correction(self):
        fixture = self.fixture
        fixture.ready_with_ticket_pool(pool_size=1)
        fixture.set_exam_blueprint(question_count=1, time_limit_minutes=20)
        fixture.cli("exam")
        for observation_id in ("first", "second"):
            answer = observation(observation_id, "ticket-1", "correct", {"score": 1, "max_score": 1})
            fixture.cli("record-observation", str(fixture.write(f"{observation_id}.json", answer)))
        attempt = fixture.cli("end-session")["summary"]["learner_mock_attempt"]
        self.assertFalse(attempt["valid"])
        self.assertEqual(2, attempt["questions"][0]["attempt_count"])

    def test_rederived_readiness_rejects_short_old_snapshots(self):
        fixture = adaptive_fixtures.LearnerReadinessTests()
        fixture.setUp()
        fixture.course["exam"]["question_count"] = 10
        current_hash = blueprint_hash(fixture.course["exam"])
        for attempt in fixture.attempts:
            attempt["blueprint_hash"] = current_hash
        for record in fixture.events:
            record["exam_hash"] = current_hash
        result = build_learner_exam_readiness(
            fixture.course, fixture.syllabus, fixture.derived,
            fixture.attempts, fixture.events,
        )
        self.assertNotEqual("ready", result["status"])

    def test_rederived_readiness_rejects_missing_problem_slot(self):
        fixture = adaptive_fixtures.LearnerReadinessTests()
        fixture.setUp()
        fixture.course["exam"].update({
            "question_count": 2,
            "ticket_slots": [{"kind": "theory", "count": 1}, {"kind": "problem", "count": 1}],
        })
        current_hash = blueprint_hash(fixture.course["exam"])
        for attempt in fixture.attempts:
            attempt["blueprint_hash"] = current_hash
        for record in fixture.events:
            record["exam_hash"] = current_hash
        result = build_learner_exam_readiness(
            fixture.course, fixture.syllabus, fixture.derived,
            fixture.attempts, fixture.events,
        )
        self.assertNotEqual("ready", result["status"])

    def test_status_recomputes_snapshots_from_the_previous_evidence_policy(self):
        fixture = self.fixture
        fixture.ready_with_ticket_pool(pool_size=1)
        fixture.cli("status")
        store = StudyStore.for_exam_prep(fixture.root)
        recovered = store.try_recover()
        stale = copy.deepcopy(recovered.derived)
        stale["evidence_policy_revision"] = 0
        stale["targets"]["tickets-course"]["evidence"]["independent_successes"] = 99
        import json
        course = json.loads((store.state_path / "course.json").read_text())
        syllabus = json.loads((store.state_path / "syllabus.json").read_text())
        store.commit_revision(stale, recovered.session, recovered.learner,
                              recovered.review_queue, course, syllabus)
        records_before = store.read_complete_observations()
        state = fixture.cli("status")["targets"]["targets"]["tickets-course"]
        self.assertEqual(0, state["evidence"]["independent_successes"])
        self.assertEqual(records_before, store.read_complete_observations())


class ExposureContentRegressionTests(unittest.TestCase):
    def history(self):
        original = frozen_assessment("original", "Solve x + 2 = 5", "delayed_transfer")
        clone = frozen_assessment("clone", "Solve x + 2 = 5", "delayed_transfer")
        novel = frozen_assessment("novel", "Solve 2*x + 3 = 9", "delayed_transfer")
        records = []
        for index, (assessment, timestamp) in enumerate((
            (original, "2026-10-01T00:00:00+00:00"),
            (clone, "2026-10-01T08:00:00+00:00"),
            (novel, "2026-10-02T08:00:00+00:00"),
        )):
            records.append(event(
                f"answer-{index}", timestamp,
                capability_id=assessment.capability_id, task_type=assessment.capability_id,
                assessment_id=assessment.assessment_id,
                assessment_spec_hash=assessment.spec_hash,
                assessment_question_hash=assessment.question_hash,
                assessment_integrity="frozen_attempt",
            ))
        records[0].update({
            "outcome": "solution_seen", "assessment_integrity": "explicit_exposure",
            "assistance": {"levels_revealed": ["H5"], "full_solution_viewed": True},
        })
        return records, clone

    def test_new_id_does_not_hide_prior_content_exposure(self):
        records, clone = self.history()
        decision = assess_attempt_evidence(records[1], clone, prior_events=records[:1])
        self.assertEqual("post_exposure_attempt", decision.integrity)
        self.assertFalse(decision.mastery_eligible)

    def test_rebuild_downgrades_an_already_recorded_exposed_clone(self):
        records, _clone = self.history()
        before = copy.deepcopy(records)
        state = reduce_learning_state(COURSE, SYLLABUS, records, {})["concepts"]["topic"]
        self.assertEqual(1, state["evidence"]["independent_successes"])
        self.assertEqual(1, state["delayed_confirmations"]["valid_checks"])
        self.assertEqual(before, records)

    def test_first_delayed_problem_must_differ_from_preparation(self):
        records, _clone = self.history()
        records[0].update({
            "outcome": "correct", "assessment_integrity": "frozen_attempt",
            "assistance": {"levels_revealed": []},
        })
        state = reduce_learning_state(COURSE, SYLLABUS, records[:2], {})["concepts"]["topic"]
        self.assertEqual(0, state["delayed_confirmations"]["valid_checks"])

    def test_superseded_exposure_does_not_contaminate_new_attempt(self):
        records, clone = self.history()
        correction = {**records[0], "observation_id": "corrected",
                      "supersedes_observation_id": records[0]["observation_id"],
                      "outcome": "unclear", "assistance": {"levels_revealed": []},
                      "assessment_integrity": "frozen_attempt"}
        decision = assess_attempt_evidence(
            records[1], clone, prior_events=[records[0], correction],
        )
        self.assertEqual("frozen_attempt", decision.integrity)

    def test_fresh_theory_recall_after_teaching_can_confirm_retention(self):
        records, _clone = self.history()
        for record in records:
            record.update(capability_id="delayed_recall", task_type="delayed_recall")
        course = {**COURSE, "exam": {"question_model": "ticket_list"}}
        state = reduce_learning_state(course, SYLLABUS, records, {})["concepts"]["topic"]
        self.assertEqual(2, state["delayed_confirmations"]["valid_checks"])

    def test_theory_exception_does_not_clean_exposed_mock_material(self):
        records, _clone = self.history()
        for record in records:
            record.update(capability_id="delayed_recall", task_type="delayed_recall", assessment_purpose="mock")
        course = {**COURSE, "exam": {"question_model": "ticket_list"}}
        state = reduce_learning_state(course, SYLLABUS, records, {})["concepts"]["topic"]
        self.assertEqual(1, state["evidence"]["independent_successes"])

    def test_cli_theory_mock_cannot_use_the_training_exception(self):
        fixture = mock_fixtures.MockExamBlueprintTests()
        fixture.setUp()
        try:
            fixture.ready_with_ticket_pool(pool_size=1)
            fixture.set_exam_blueprint(question_model="ticket_list", question_count=1, time_limit_minutes=20)
            pool = {"assessments": [spec("clone", "State theorem number 1.")]}
            fixture.cli("mint-assessments", str(fixture.write("clone-pool.json", pool)))
            fixture.cli("exam")
            shown = observation("shown", "ticket-1", outcome="solution_seen")
            shown.update({"assistance": {"levels_revealed": ["H5"], "full_solution_viewed": True},
                          "explicit_exposure_reason": "learner requested a solution"})
            fixture.cli("record-observation", str(fixture.write("shown.json", shown)))
            fixture.cli("record-observation", str(fixture.write("answer.json", observation("answer", "clone"))))
            records = StudyStore.for_exam_prep(fixture.root).read_complete_observations()
            self.assertEqual("post_exposure_attempt", records[-1]["assessment_integrity"])
        finally:
            fixture.tearDown()

    def test_cli_clone_after_solution_is_not_independent(self):
        fixture = mock_fixtures.MockExamBlueprintTests()
        fixture.setUp()
        try:
            fixture.cli("init")
            from tests.test_mock_exam_blueprint import SYLLABUS as syllabus
            fixture.cli("load-syllabus", str(fixture.write("syllabus.json", syllabus)))
            pool = {"assessments": [
                {**spec("original", "Solve x + 2 = 5", purpose="practice"), "capability_id": "delayed_transfer"},
                {**spec("clone", "Solve x + 2 = 5", purpose="practice"), "capability_id": "delayed_transfer"},
            ]}
            fixture.cli("mint-assessments", str(fixture.write("pool.json", pool)))
            shown = observation("shown", "original", outcome="solution_seen")
            shown.update({"assistance": {"levels_revealed": ["H5"], "full_solution_viewed": True},
                          "capability_id": "delayed_transfer", "task_type": "delayed_transfer",
                          "explicit_exposure_reason": "learner requested a solution"})
            fixture.cli("record-observation", str(fixture.write("shown.json", shown)))
            answer = {**observation("answer", "clone"),
                      "capability_id": "delayed_transfer", "task_type": "delayed_transfer"}
            fixture.cli("record-observation", str(fixture.write("answer.json", answer)))
            records = StudyStore.for_exam_prep(fixture.root).read_complete_observations()
            self.assertEqual("post_exposure_attempt", records[-1]["assessment_integrity"])
            state = fixture.cli("status")["targets"]["targets"]["tickets-course"]
            self.assertEqual(0, state["evidence"]["independent_successes"])
        finally:
            fixture.tearDown()

    def test_old_hashless_journal_is_replayed_without_crediting_exposed_clones(self):
        fixture = mock_fixtures.MockExamBlueprintTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        fixture.cli("init")
        fixture.cli("load-syllabus", str(fixture.write("syllabus.json", mock_fixtures.SYLLABUS)))
        pool = {"assessments": [
            {**spec("original", "Solve x + 2 = 5", purpose="practice"), "capability_id": "delayed_transfer"},
            {**spec("clone", "Solve x + 2 = 5", purpose="practice"), "capability_id": "delayed_transfer"},
        ]}
        fixture.cli("mint-assessments", str(fixture.write("pool.json", pool)))
        shown = observation("shown", "original", "solution_seen")
        shown.update({
            "assistance": {"levels_revealed": ["H5"], "full_solution_viewed": True},
            "capability_id": "delayed_transfer", "task_type": "delayed_transfer",
            "explicit_exposure_reason": "learner requested a solution",
        })
        fixture.cli("record-observation", str(fixture.write("shown.json", shown)))
        answer = {**observation("answer", "clone"),
                  "capability_id": "delayed_transfer", "task_type": "delayed_transfer"}
        fixture.cli("record-observation", str(fixture.write("answer.json", answer)))
        store = StudyStore.for_exam_prep(fixture.root)
        # Model the pre-upgrade journal and its fully materialized snapshot.
        legacy_events = store.read_complete_observations()
        for record in legacy_events:
            record.pop("assessment_question_hash")
        legacy_events[-1]["assessment_integrity"] = "frozen_attempt"
        store.observations_path.write_text(
            "".join(json.dumps(record) + "\n" for record in legacy_events), encoding="utf-8",
        )
        recovered = store.try_recover()
        stale = copy.deepcopy(recovered.derived)
        stale["evidence_policy_revision"] = 1
        stale["targets"]["tickets-course"]["evidence"]["independent_successes"] = 1
        course = json.loads((store.state_path / "course.json").read_text())
        syllabus = json.loads((store.state_path / "syllabus.json").read_text())
        store.commit_revision(stale, recovered.session, recovered.learner,
                              recovered.review_queue, course, syllabus)
        journal_before = store.observations_path.read_bytes()
        for command in ("status", "rebuild"):
            with self.subTest(command=command):
                result = fixture.cli(command)
                state = result["targets"]["targets"]["tickets-course"]
                self.assertEqual(0, state["evidence"]["independent_successes"])
                self.assertEqual(journal_before, store.observations_path.read_bytes())
        proposal = {
            "schema_version": 2,
            "proposal_id": "add-another-topic",
            "source_refs": [],
            "learning_targets": [{"target_id": "another-topic", "title": "Another topic",
                                  "prerequisites": [], "source_refs": []}],
            "assessment_capabilities": [],
            "exam_questions": [],
        }
        fixture.cli("apply-curriculum", str(fixture.write("curriculum.json", proposal)))
        state = fixture.cli("status")["targets"]["targets"]["tickets-course"]
        self.assertEqual(0, state["evidence"]["independent_successes"])
        self.assertEqual(journal_before, store.observations_path.read_bytes())
        retry = fixture.cli("record-observation", str(fixture.write("retry.json", answer)))
        self.assertFalse(retry["appended"])

    def test_definition_retention_can_reuse_content_in_a_problem_course(self):
        for model in ("problem_set", "mixed", "open", None):
            with self.subTest(question_model=model):
                records = [event(
                    "prep", "2026-10-01T00:00:00+00:00",
                    capability_id="definition_recall", task_type="definition_recall",
                )]
                for index, timestamp in ((1, "2026-10-01T08:00:00+00:00"),
                                         (2, "2026-10-02T08:00:00+00:00")):
                    assessment = frozen_assessment(f"definition-{index}", "State the definition of derivative.")
                    records.append(event(
                        f"check-{index}", timestamp, assessment_id=assessment.assessment_id,
                        assessment_question_hash=assessment.question_hash,
                        assessment_integrity="frozen_attempt", assessment_purpose="practice",
                    ))
                course = {**COURSE, "exam": {"question_model": model}}
                state = reduce_learning_state(course, SYLLABUS, records, {})["concepts"]["topic"]
                self.assertEqual(2, state["delayed_confirmations"]["valid_checks"])


class ReviewSchedulingRegressionTests(unittest.TestCase):
    now = datetime(2026, 10, 1, 10, tzinfo=timezone.utc)

    def queue(self, records, syllabus=SYLLABUS):
        return build_review_queue(records, {}, COURSE, self.now, syllabus)["items"]

    def test_unclear_and_skipped_do_not_move_the_last_review(self):
        bad = event("bad", "2026-10-01T08:00:00+00:00", outcome="incorrect")
        expected = self.queue([bad])["topic"]
        for outcome in ("unclear", "skipped"):
            with self.subTest(outcome=outcome):
                ungraded = event(outcome, "2026-10-01T09:00:00+00:00", outcome=outcome)
                self.assertEqual(expected, self.queue([bad, ungraded])["topic"])

    def test_unknown_correct_capability_does_not_erase_error_pressure(self):
        records = [
            event("bad", "2026-10-01T08:00:00+00:00", outcome="incorrect"),
            event("unknown", "2026-10-01T09:00:00+00:00",
                  capability_id="unknown", task_type="unknown"),
        ]
        item = self.queue(records)["topic"]
        self.assertEqual(1, item["error_load"])
        self.assertNotIn("base 24h", item["reason"])
        self.assertEqual(self.queue(records[:1])["topic"], item)

    def test_correction_to_another_target_removes_old_error_globally(self):
        syllabus = {"concepts": {"topic": {}, "other": {}}}
        records = [
            event("bad", "2026-10-01T08:00:00+00:00", outcome="incorrect"),
            event("fixed", "2026-10-01T09:00:00+00:00", target_id="other",
                  supersedes_observation_id="bad"),
        ]
        self.assertNotIn("topic", self.queue(records, syllabus))

    def test_only_ungraded_events_leave_target_without_review_evidence(self):
        self.assertNotIn("topic", self.queue([
            event("unclear", "2026-10-01T09:00:00+00:00", outcome="unclear"),
        ]))


class AdaptiveGuidanceRegressionTests(unittest.TestCase):
    def test_ungraded_response_keeps_the_previous_error_repair_and_small_block(self):
        fixture = adaptive_fixtures.RuntimeAdaptiveUxTests()
        for outcome in ("unclear", "skipped"):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                fixture.cli(root, "init")
                syllabus_path = root / "syllabus.json"
                syllabus_path.write_text(json.dumps({
                    "schema_version": 2,
                    "learning_targets": [{"target_id": "topic", "prerequisites": [],
                                          "estimated_learning_minutes": 20}],
                }), encoding="utf-8")
                fixture.cli(root, "load-syllabus", str(syllabus_path))
                for observation_id, result in (("bad", "incorrect"), ("ungraded", outcome)):
                    proposal = event(observation_id, None, outcome=result)
                    for key in ("recorded_at", "session_id", "assessment_integrity"):
                        proposal.pop(key)
                    path = root / f"{observation_id}.json"
                    path.write_text(json.dumps(proposal), encoding="utf-8")
                    code, _receipt = fixture.cli(root, "record-observation", str(path))
                    self.assertEqual(0, code)
                code, activity = fixture.cli(root, "next", "--minutes", "25")
                self.assertEqual(0, code)
                self.assertEqual("repair_first_error", activity["transition"])
                self.assertEqual(1, activity["recommended_block_size"])


if __name__ == "__main__":
    unittest.main()
