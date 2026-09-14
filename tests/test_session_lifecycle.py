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


def proposal(observation_id, outcome="incorrect", errors=None):
    return {
        "schema_version": 1,
        "observation_id": observation_id,
        "concept_id": "chain_rule",
        "task_id": observation_id,
        "task_type": "independent_problem",
        "outcome": outcome,
        "assistance": {
            "requested": False,
            "levels_revealed": [],
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
