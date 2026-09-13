"""Regression tests: editing course.json or syllabus.json directly (the
documented way to set the exam date / adjust scheduler policy / edit the
syllabus) must invalidate derived state even when neither the observation
log nor the syllabus's concept-id set changed."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


sys.path.insert(0, "skill/exam-prep/scripts")

from exam_prep import main  # noqa: E402


ROOT = Path(__file__).parents[1]
SYLLABUS = ROOT / "skill" / "exam-prep" / "examples" / "example-syllabus.json"


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


class CanonicalInvalidationTests(unittest.TestCase):
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

    def ready(self):
        self.cli("init")
        self.cli("load-syllabus", str(SYLLABUS))
        self.cli("start")

    def edit_course(self, mutate):
        path = self.root / "state" / "course.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        mutate(data)
        path.write_text(json.dumps(data), encoding="utf-8")

    def edit_syllabus(self, mutate):
        path = self.root / "state" / "syllabus.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        mutate(data)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_exam_date_change_recomputes_review_queue(self):
        self.ready()
        self.record(proposal("obs-1"))
        before = self.cli("status")["review_queue"]["items"]["functions"]["interval_hours"]

        near_exam = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        self.edit_course(lambda d: d["exam"].__setitem__("date", near_exam))

        after = self.cli("status")["review_queue"]["items"]["functions"]["interval_hours"]
        self.assertLess(after, before)

    def test_scheduler_policy_change_recomputes_review_queue(self):
        self.ready()
        self.record(proposal("obs-1", outcome="correct"))
        before = self.cli("status")["review_queue"]["items"]["functions"]["interval_hours"]

        self.edit_course(lambda d: d["scheduler"].__setitem__("max_review_interval_hours", 1))

        after = self.cli("status")["review_queue"]["items"]["functions"]["interval_hours"]
        self.assertLessEqual(after, 1)
        self.assertLess(after, before)

    def test_syllabus_prerequisite_change_recomputes_availability(self):
        self.ready()
        before = self.cli("status")["concepts"]["concepts"]["chain_rule"]["availability"]

        self.edit_syllabus(lambda d: d["concepts"]["chain_rule"].__setitem__("prerequisites", []))

        after = self.cli("status")["concepts"]["concepts"]["chain_rule"]["availability"]
        self.assertNotEqual(before, after)
        self.assertEqual(after, "available")

    def test_syllabus_importance_change_recomputes_priority(self):
        # Unlike concepts.json/review_queue.json, priority/score is computed
        # live from the syllabus on every `next` call rather than cached in
        # a revision, so this was never actually stale - this test guards
        # that property (a naive fix could regress it, e.g. by materializing
        # priority into a cached snapshot).
        self.ready()
        before = self.cli("next", "--minutes", "25")
        before_score = before["score"] if before["concept_id"] == "functions" else None

        self.edit_syllabus(lambda d: d["concepts"]["functions"].__setitem__("importance", 0.99))
        self.edit_syllabus(lambda d: d["concepts"]["functions"].__setitem__("expected_points", 40))

        after = self.cli("next", "--minutes", "25")
        self.assertEqual(after["concept_id"], "functions")
        self.assertNotEqual(after["score"], before_score)


if __name__ == "__main__":
    unittest.main()
