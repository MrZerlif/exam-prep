import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, "skill/exam-prep/scripts")

from exam_prep import main  # noqa: E402


ROOT = Path(__file__).parents[1]
SYLLABUS = ROOT / "skill" / "exam-prep" / "examples" / "mathematics-regression-syllabus.json"


def proposal(observation_id, outcome="incorrect", errors=None, levels_revealed=None):
    return {
        "schema_version": 1,
        "observation_id": observation_id,
        "concept_id": "chain_rule",
        "task_id": observation_id,
        "task_type": "independent_problem",
        "outcome": outcome,
        "assistance": {
            "requested": bool(levels_revealed),
            "levels_revealed": levels_revealed or [],
            "scaffold_types": [],
            "partial_transformation_shown": False,
            "full_solution_viewed": False,
        },
        "error_tags": errors or [],
        "diagnostic_confidence": "high",
        "learner_self_confidence": "medium",
        "source_refs": ["teacher:worksheet-1"],
    }


class SessionLifecycleTests(unittest.TestCase):
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

    def record(self, item):
        path = self.root / f"{item['observation_id']}.json"
        path.write_text(json.dumps(item), encoding="utf-8")
        return self.cli("record-observation", str(path))

    def test_start_after_end_session_creates_a_new_session_id(self):
        self.cli("init")
        self.cli("load-syllabus", str(SYLLABUS))
        first = self.cli("start")
        session_a = first["session"]["session_id"]
        self.cli("end-session")
        second = self.cli("start")
        session_b = second["session"]["session_id"]
        self.assertNotEqual(session_a, session_b)
        self.assertEqual(second["session"]["phase"], "study")

    def test_start_without_end_session_resumes_the_same_active_session(self):
        self.cli("init")
        self.cli("load-syllabus", str(SYLLABUS))
        first = self.cli("start")
        second = self.cli("start")
        self.assertEqual(first["session"]["session_id"], second["session"]["session_id"])

    def test_end_session_mid_task_preserves_a_specific_resume_point(self):
        self.cli("init")
        self.cli("load-syllabus", str(SYLLABUS))
        self.cli("start")
        self.record(proposal("obs-mid-1", outcome="incorrect", errors=["proof_structure_error"]))
        self.cli("end-session")

        status = self.cli("status")
        resume = status["resume_point"]
        self.assertIsNotNone(resume)
        self.assertEqual("chain_rule", resume["target_id"])
        self.assertEqual("Chain rule", resume["target_title"])
        self.assertEqual("obs-mid-1", resume["task_id"])
        self.assertEqual("incorrect", resume["last_attempt_outcome"])
        self.assertEqual(["proof_structure_error"], resume["last_attempt_error_tags"])
        self.assertIn("proof structure is incomplete", resume["last_attempt_error_summaries"])

    def test_resume_point_survives_a_later_session_after_end_session(self):
        self.cli("init")
        self.cli("load-syllabus", str(SYLLABUS))
        self.cli("start")
        self.record(proposal("obs-mid-2", outcome="incorrect", errors=["proof_structure_error"]))
        self.cli("end-session")

        # An arbitrary amount of time later, the learner opens the skill
        # again; the break state must not have been wiped by the session
        # boundary in between.
        self.cli("start")
        status = self.cli("status")
        resume = status["resume_point"]
        self.assertIsNotNone(resume)
        self.assertEqual("chain_rule", resume["target_id"])
        self.assertEqual("obs-mid-2", resume["task_id"])

    def test_resume_point_is_absent_before_anything_is_attempted(self):
        self.cli("init")
        self.cli("load-syllabus", str(SYLLABUS))
        self.cli("start")
        status = self.cli("status")
        self.assertIsNone(status["resume_point"])

    def test_completed_task_has_no_resume_point_after_end_session(self):
        # 8.1a: a task finished cleanly (independent correct) before the
        # session ended must not be offered back up as "continue here" -
        # only a genuinely interrupted task should be.
        self.cli("init")
        self.cli("load-syllabus", str(SYLLABUS))
        self.cli("start")
        result = self.record(proposal("obs-done-1", outcome="correct"))
        self.assertTrue(result["session"]["current_task_done"])
        self.assertEqual(
            "choose the next budget-fitting activity", result["session"]["pending_action"]
        )
        self.cli("end-session")

        status = self.cli("status")
        self.assertIsNone(status["resume_point"])

    def test_hinted_correct_answer_still_has_a_resume_point(self):
        # A "correct" outcome alone is not enough to count as done - it must
        # have been independent. A hinted success still leaves the task open
        # (the learner has not yet demonstrated it unaided), so it must
        # still be resumable after a break.
        self.cli("init")
        self.cli("load-syllabus", str(SYLLABUS))
        self.cli("start")
        result = self.record(
            proposal("obs-hinted-1", outcome="correct", levels_revealed=["H1"])
        )
        self.assertFalse(result["session"]["current_task_done"])
        self.cli("end-session")

        status = self.cli("status")
        resume = status["resume_point"]
        self.assertIsNotNone(resume)
        self.assertEqual("obs-hinted-1", resume["task_id"])

    def test_recurring_mistake_sessions_seen_counts_distinct_sessions(self):
        self.cli("init")
        self.cli("load-syllabus", str(SYLLABUS))
        self.cli("start")
        self.record(proposal("obs-s1", errors=["conceptual_error"]))
        self.cli("end-session")

        self.cli("start")
        result = self.record(proposal("obs-s2", errors=["conceptual_error"]))
        self.cli("end-session")

        mistakes = result["targets"]["targets"]["chain_rule"]["recurring_mistakes"]
        self.assertEqual(mistakes[0]["sessions_seen"], 2)


if __name__ == "__main__":
    unittest.main()
