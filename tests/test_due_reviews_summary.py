"""Regression test: end-session's `due_reviews` must mean actually due
(due_at <= now), not merely "has a due_at at all" (every touched concept
gets one, including ones scheduled for tomorrow)."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, "skill/math-study/scripts")

from math_study import main  # noqa: E402
from math_study_lib.storage import StudyStore  # noqa: E402


ROOT = Path(__file__).parents[1]
SYLLABUS = ROOT / "skill" / "math-study" / "syllabus" / "example-syllabus.json"


def proposal(observation_id, concept_id="functions", outcome="correct"):
    return {
        "schema_version": 1,
        "observation_id": observation_id,
        "concept_id": concept_id,
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
        "error_tags": [],
        "diagnostic_confidence": "high",
        "source_refs": ["teacher:worksheet-1"],
    }


class DueReviewsSummaryTests(unittest.TestCase):
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

    def test_review_scheduled_for_tomorrow_is_not_in_due_reviews(self):
        self.cli("init")
        self.cli("load-syllabus", str(SYLLABUS))
        self.cli("start")
        # A correct, independent, non-delayed-recall answer schedules the
        # next review roughly a day out (well beyond "now").
        self.record(proposal("obs-1", outcome="correct"))
        store = StudyStore(self.root)
        item = store.recover().review_queue["items"]["functions"]
        self.assertEqual(item["review_status"], "not_due")

        result = self.cli("end-session")
        self.assertNotIn("functions", result["summary"]["due_reviews"])

    def test_overdue_review_is_in_due_reviews(self):
        self.cli("init")
        self.cli("load-syllabus", str(SYLLABUS))
        self.cli("start")
        # Append directly through the storage API with a backdated
        # recorded_at (the engine-owned clock field a CLI/LLM call can never
        # set itself) so the computed review interval has genuinely, legally
        # elapsed by "now" - not hand-editing an already-committed line.
        store = StudyStore(self.root)
        store.append_observation(
            proposal("obs-1", outcome="incorrect"),
            self.cli("status")["session"]["session_id"],
            "2020-01-01T00:00:00+00:00",
            None,
            None,
        )

        result = self.cli("end-session")
        self.assertIn("functions", result["summary"]["due_reviews"])


if __name__ == "__main__":
    unittest.main()
