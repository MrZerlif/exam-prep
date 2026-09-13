import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, "skill/math-study/scripts")

from math_study import main  # noqa: E402
from math_study_lib.storage import ObservationConflict, StudyStore  # noqa: E402


ROOT = Path(__file__).parents[1]
SYLLABUS = ROOT / "skill" / "math-study" / "syllabus" / "example-syllabus.json"


def proposal(observation_id, outcome="correct", task_type="independent_problem", errors=None):
    return {
        "schema_version": 1,
        "observation_id": observation_id,
        "concept_id": "chain_rule",
        "task_id": observation_id,
        "task_type": task_type,
        "outcome": outcome,
        "assistance": {
            "requested": False,
            "levels_revealed": [],
            "scaffold_types": [],
            "partial_transformation_shown": False,
            "full_solution_viewed": outcome == "solution_seen",
        },
        "error_tags": errors or [],
        "diagnostic_confidence": "high",
        "learner_self_confidence": "medium",
        "learner_explanation": "Проверил решение.",
        "source_refs": ["official-exam-list:q5"],
    }


class SyntheticScenarioTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.syllabus_copy = self.root / "syllabus.json"
        shutil.copyfile(SYLLABUS, self.syllabus_copy)

    def tearDown(self):
        self.temp_dir.cleanup()

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--workspace", str(self.root), *args])
        self.assertEqual(code, 0, output.getvalue())
        return json.loads(output.getvalue())

    def ready(self):
        self.cli("init")
        self.cli("load-syllabus", str(self.syllabus_copy))
        self.cli("start")

    def record(self, item):
        path = self.root / f"{item['observation_id']}.json"
        path.write_text(json.dumps(item), encoding="utf-8")
        return self.cli("record-observation", str(path))

    def test_restart_rebuilds_learning_state_and_preserves_pending_cursor(self):
        self.ready()
        self.record(proposal("obs-restart"))
        status = self.cli("status")
        rebuilt = self.cli("rebuild")
        self.assertIn("pending_action", status["session"])
        self.assertEqual(rebuilt["concepts"], status["concepts"])
        store = StudyStore(self.root)
        store.current_path.write_text("{broken", encoding="utf-8")
        recovered = store.recover()
        self.assertEqual(recovered.derived, status["concepts"])
        with store.observations_path.open("ab") as handle:
            handle.write(b'{"observation_id":"partial"')
        self.assertTrue(store.read_log_diagnostics()["partial_final_line"])

    def test_three_conceptual_errors_become_recurring(self):
        self.ready()
        for index in range(3):
            result = self.record(
                proposal(
                    f"obs-error-{index}",
                    outcome="incorrect",
                    errors=["conceptual_error"],
                )
            )
        mistakes = result["concepts"]["concepts"]["chain_rule"]["recurring_mistakes"]
        self.assertEqual(mistakes[0]["count"], 3)
        self.assertEqual(mistakes[0]["sessions_seen"], 1)

    def test_solution_seen_does_not_promote_mastery(self):
        self.ready()
        result = self.record(proposal("obs-solution", outcome="solution_seen", task_type="worked_example"))
        state = result["concepts"]["concepts"]["chain_rule"]
        self.assertEqual(state["mastery"]["conceptual"], 0.0)
        self.assertEqual(state["evidence"]["solution_views"], 1)

    def test_duplicate_and_conflicting_retry_are_distinct(self):
        self.ready()
        item = proposal("obs-retry")
        first = self.record(item)
        second = self.record(item)
        self.assertTrue(first["appended"])
        self.assertFalse(second["appended"])
        store = StudyStore(self.root)
        with self.assertRaises(ObservationConflict):
            store.append_observation(
                proposal("obs-retry", outcome="incorrect"),
                first["session"]["session_id"],
                first["event"]["recorded_at"],
                None,
                None,
            )

    def test_exam_mode_post_mortem_keeps_typed_evidence(self):
        self.ready()
        exam = self.cli("exam", "--minutes", "20")
        self.assertTrue(exam["no_unsolicited_hints"])
        result = self.record(
            proposal(
                "obs-exam-error",
                outcome="incorrect",
                task_type="exam_problem",
                errors=["method_selection_error", "algebra_error"],
            )
        )
        self.assertEqual(result["session"]["phase"], "exam")
        self.assertEqual(
            result["concepts"]["concepts"]["chain_rule"]["evidence"]["failures"], 1
        )


if __name__ == "__main__":
    unittest.main()
