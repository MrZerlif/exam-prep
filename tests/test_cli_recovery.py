"""Regression tests: normal CLI commands must go through the recovery path,
not read potentially-corrupt convenience JSON directly."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, "skill/exam-prep/scripts")

from exam_prep import main  # noqa: E402
from exam_prep_lib.storage import StudyStore  # noqa: E402


ROOT = Path(__file__).parents[1]
SYLLABUS = ROOT / "skill" / "exam-prep" / "examples" / "mathematics-regression-syllabus.json"


def proposal(observation_id, outcome="correct"):
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
        "error_tags": [],
        "diagnostic_confidence": "high",
        "learner_self_confidence": "medium",
        "source_refs": ["teacher:worksheet-1"],
    }


class CliRecoveryTests(unittest.TestCase):
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

    def test_status_survives_corrupt_convenience_concepts_json(self):
        self.ready()
        self.record(proposal("obs-1"))
        (self.root / ".exam-prep" / "targets.json").write_text("{not-json", encoding="utf-8")
        status = self.cli("status")
        self.assertIn("chain_rule", status["targets"]["targets"])

    def test_status_survives_missing_convenience_files(self):
        self.ready()
        self.record(proposal("obs-1"))
        for name in ("targets.json", "review_queue.json", "session.json", "learner.json"):
            (self.root / ".exam-prep" / name).unlink()
        status = self.cli("status")
        self.assertIn("chain_rule", status["targets"]["targets"])
        self.assertTrue(status["session"]["session_id"])

    def test_status_survives_corrupt_current_pointer(self):
        self.ready()
        self.record(proposal("obs-1"))
        (self.root / ".exam-prep" / "current.json").write_text("{broken", encoding="utf-8")
        status = self.cli("status")
        self.assertIn("chain_rule", status["targets"]["targets"])

    def test_status_survives_incomplete_revision_directory(self):
        self.ready()
        self.record(proposal("obs-1"))
        store = StudyStore.for_exam_prep(self.root)
        latest = sorted(store.revisions_path.iterdir())[-1]
        (latest / "manifest.json").unlink()
        status = self.cli("status")
        self.assertIn("chain_rule", status["targets"]["targets"])

    def test_status_survives_hash_mismatch_in_latest_revision(self):
        self.ready()
        self.record(proposal("obs-1"))
        store = StudyStore.for_exam_prep(self.root)
        latest = sorted(store.revisions_path.iterdir())[-1]
        (latest / "targets.json").write_text(
            json.dumps({"schema_version": 2, "derived_from_revision": 1, "targets": {}, "aliases": {}}),
            encoding="utf-8",
        )
        status = self.cli("status")
        self.assertIn("chain_rule", status["targets"]["targets"])

    def test_unapplied_observation_after_crash_is_replayed_exactly_once(self):
        """Simulate: observation fsynced to the log, process died before the
        derived revision (and convenience concepts.json) were written."""
        self.ready()
        store = StudyStore.for_exam_prep(self.root)
        crash_proposal = proposal("obs-crash")
        store.append_observation(crash_proposal, "session-x", "2026-09-13T10:00:00+00:00", None, None)
        # No commit_revision call happened: targets.json is still stale relative
        # to observations.jsonl (still empty targets, revision 1).
        status = self.cli("status")
        state = status["targets"]["targets"]["chain_rule"]
        self.assertEqual(state["evidence"]["independent_successes"], 1)
        # Replaying again must not double-count (idempotent materialization).
        status_again = self.cli("status")
        self.assertEqual(
            status_again["targets"]["targets"]["chain_rule"]["evidence"]["independent_successes"],
            1,
        )

    def test_mistakes_and_roadmap_and_review_due_use_recovery_path_too(self):
        self.ready()
        self.record(proposal("obs-1", outcome="incorrect"))
        (self.root / ".exam-prep" / "targets.json").write_text("{not-json", encoding="utf-8")
        (self.root / ".exam-prep" / "review_queue.json").write_text("{not-json", encoding="utf-8")
        mistakes = self.cli("mistakes")
        self.assertIsInstance(mistakes, dict)
        roadmap = self.cli("roadmap")
        self.assertTrue(any(item["target_id"] == "chain_rule" for item in roadmap["roadmap"]))
        due = self.cli("review-due")
        self.assertIsInstance(due["due"], dict)


if __name__ == "__main__":
    unittest.main()
