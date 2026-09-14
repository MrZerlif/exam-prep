import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep import main  # noqa: E402


SYLLABUS = {
    "schema_version": 2,
    "learning_targets": [
        {
            "target_id": "tickets-course",
            "title": "Ticket topics",
            "prerequisites": [],
            "importance": 0.9,
            "frequency": 0.8,
            "expected_points": 10,
            "estimated_learning_minutes": 25,
            "source_refs": ["teacher:worksheet-1"],
        }
    ],
}


def spec(assessment_id, prompt):
    return {
        "assessment_id": assessment_id,
        "target_id": "tickets-course",
        "capability_id": "delayed_recall",
        "prompt": prompt,
        "rubric": {"correct": 1},
        "expected_evidence": ["independent_work"],
        "source_refs": [
            {"source_id": "teacher:tickets", "authority": "teacher_material", "locator": "ticket list"}
        ],
        "difficulty": 0.4,
        "question_version": 1,
        "rubric_version": 1,
        "purpose": "mock",
    }


def observation(observation_id, assessment_id, outcome="correct"):
    return {
        "schema_version": 2,
        "observation_id": observation_id,
        "target_id": "tickets-course",
        "task_id": observation_id,
        "capability_id": "delayed_recall",
        "task_type": "delayed_recall",
        "outcome": outcome,
        "assistance": {"levels_revealed": []},
        "error_tags": [],
        "diagnostic_confidence": "high",
        "source_refs": [],
        "assessment_id": assessment_id,
    }


class MockExamBlueprintTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--workspace", str(self.root), *args])
        self.assertEqual(code, 0, output.getvalue())
        return json.loads(output.getvalue())

    def write(self, name, payload):
        path = self.root / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def ready_with_ticket_pool(self, pool_size=3):
        syllabus_path = self.write("syllabus.json", SYLLABUS)
        self.cli("init")
        self.cli("load-syllabus", str(syllabus_path))
        batch = {
            "assessments": [
                spec(f"ticket-{i}", f"State theorem number {i}.") for i in range(1, pool_size + 1)
            ]
        }
        batch_path = self.write("batch.json", batch)
        self.cli("mint-assessments", str(batch_path))

    def set_exam_blueprint(self, **patch):
        patch_path = self.write("exam-patch.json", patch)
        self.cli("update-exam-blueprint", str(patch_path))

    def test_exam_assembles_a_ticket_list_not_a_mixed_task_set(self):
        self.ready_with_ticket_pool(pool_size=3)
        self.set_exam_blueprint(
            question_model="ticket_list",
            delivery="oral",
            question_count=2,
            time_limit_minutes=20,
            follow_up_questions=True,
            grading_criteria=["states the theorem precisely", "gives the correct conditions"],
        )
        result = self.cli("exam")

        self.assertEqual(2, len(result["tickets"]))
        ids = [t["assessment_id"] for t in result["tickets"]]
        # 9.2: a sample from the pool, not a sorted truncation - only
        # membership and count are guaranteed, not which two or their order.
        self.assertLessEqual(set(ids), {"ticket-1", "ticket-2", "ticket-3"})
        self.assertEqual(2, len(set(ids)))
        for ticket in result["tickets"]:
            self.assertIn("prompt", ticket)
            self.assertIn("target_id", ticket)
            self.assertEqual(10.0, ticket["time_limit_minutes"])
        self.assertEqual("oral", result["delivery"])
        self.assertEqual("ticket_list", result["question_model"])
        self.assertTrue(result["follow_up_questions"])
        self.assertEqual(
            ["states the theorem precisely", "gives the correct conditions"],
            result["grading_criteria"],
        )
        self.assertTrue(result["no_unsolicited_hints"])
        self.assertTrue(result["minimal_feedback_until_submission"])
        self.assertEqual(20, result["budget_minutes"])

        status = self.cli("status")
        self.assertEqual(ids, status["session"]["mock_assessment_ids"])

    def test_per_question_minutes_overrides_the_even_split(self):
        self.ready_with_ticket_pool(pool_size=2)
        self.set_exam_blueprint(question_count=2, time_limit_minutes=100, per_question_minutes=3)
        result = self.cli("exam")
        self.assertTrue(all(t["time_limit_minutes"] == 3.0 for t in result["tickets"]))

    def test_exam_without_a_mock_pool_falls_back_to_budget_only_mode(self):
        # No assessments minted at all - must behave exactly as before 3.2
        # (a plain budgeted mock, not an error and not a fabricated ticket
        # list).
        syllabus_path = self.write("syllabus.json", SYLLABUS)
        self.cli("init")
        self.cli("load-syllabus", str(syllabus_path))
        result = self.cli("exam", "--minutes", "20")
        self.assertEqual([], result["tickets"])
        self.assertEqual(20, result["budget_minutes"])
        self.assertEqual("exam", result["mode"])

    def test_post_mortem_reports_per_question_outcomes_after_submission(self):
        self.ready_with_ticket_pool(pool_size=3)
        self.set_exam_blueprint(question_count=3, time_limit_minutes=30)
        self.cli("exam")

        self.cli("record-observation", str(self.write("obs-1.json", observation("obs-1", "ticket-1", "correct"))))
        self.cli("record-observation", str(self.write("obs-2.json", observation("obs-2", "ticket-2", "incorrect"))))
        # ticket-3 left unattempted.

        result = self.cli("end-session")
        post_mortem = result["summary"]["post_mortem"]
        self.assertEqual(3, post_mortem["total_questions"])
        self.assertEqual(2, post_mortem["attempted"])
        self.assertEqual(1, post_mortem["correct_independent"])
        self.assertAlmostEqual(1 / 3, post_mortem["score"], places=4)

        by_id = {q["assessment_id"]: q for q in post_mortem["questions"]}
        self.assertTrue(by_id["ticket-1"]["attempted"])
        self.assertEqual("correct", by_id["ticket-1"]["outcome"])
        self.assertEqual("independent", by_id["ticket-1"]["assistance_band"])
        self.assertTrue(by_id["ticket-2"]["attempted"])
        self.assertEqual("incorrect", by_id["ticket-2"]["outcome"])
        self.assertFalse(by_id["ticket-3"]["attempted"])
        self.assertIsNone(by_id["ticket-3"]["outcome"])

    def test_study_session_end_has_no_post_mortem(self):
        syllabus_path = self.write("syllabus.json", SYLLABUS)
        self.cli("init")
        self.cli("load-syllabus", str(syllabus_path))
        self.cli("start")
        result = self.cli("end-session")
        self.assertNotIn("post_mortem", result["summary"])

    def test_repeated_mock_in_the_same_session_is_identical(self):
        # 9.2: deterministic given a fixed seed (session_id) - not a
        # coincidence, the same active session must reproduce the exact
        # same ticket list on a second call.
        self.ready_with_ticket_pool(pool_size=20)
        self.set_exam_blueprint(question_count=5)
        first = [t["assessment_id"] for t in self.cli("exam")["tickets"]]
        second = [t["assessment_id"] for t in self.cli("exam")["tickets"]]
        self.assertEqual(first, second)

    def test_different_sessions_sample_different_sets_from_the_pool(self):
        # The literal 9.2 acceptance scenario: pool size 2x question_count
        # is deliberately loose evidence, so this uses a bigger pool
        # (C(20,5) = 15504 possible subsets) to make an accidental
        # collision between two independent session seeds negligible
        # rather than merely unlikely.
        self.ready_with_ticket_pool(pool_size=20)
        self.set_exam_blueprint(question_count=5)
        first_ids = {t["assessment_id"] for t in self.cli("exam")["tickets"]}
        self.cli("end-session")
        self.cli("start")
        second_ids = {t["assessment_id"] for t in self.cli("exam")["tickets"]}
        self.assertNotEqual(first_ids, second_ids)

    def test_mock_order_is_not_the_assessment_id_sort_order(self):
        # A held-out pool is drawn like a real exam - a ticket is pulled,
        # not read off in id order.
        self.ready_with_ticket_pool(pool_size=20)
        self.set_exam_blueprint(question_count=20)
        result = self.cli("exam")
        ids = [t["assessment_id"] for t in result["tickets"]]
        self.assertEqual(20, len(ids))
        self.assertEqual({f"ticket-{i}" for i in range(1, 21)}, set(ids))
        self.assertNotEqual(sorted(ids), ids)


if __name__ == "__main__":
    unittest.main()
