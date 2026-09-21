import multiprocessing
import queue
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.storage import StudyStore  # noqa: E402
from exam_prep_lib.workspace_lock import workspace_lock  # noqa: E402


NOW = "2026-09-21T12:00:00+00:00"


def _proposal() -> dict:
    return {
        "schema_version": 1,
        "observation_id": "obs-concurrent",
        "concept_id": "chain_rule",
        "task_id": "task-1",
        "task_type": "transfer",
        "outcome": "correct",
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
        "learner_explanation": "Independent answer.",
        "source_refs": ["teacher:q1"],
    }


def _append_worker(root: str, start, result_queue) -> None:
    start.wait(timeout=5)
    try:
        result = StudyStore.for_exam_prep(Path(root)).append_observation(
            _proposal(),
            "session-1",
            NOW,
            None,
            None,
        )
        result_queue.put(("ok", result.appended))
    except Exception as exc:  # pragma: no cover - asserted by parent
        result_queue.put(("error", type(exc).__name__, str(exc)))


def _revision_worker(root: str, marker: str, start, result_queue) -> None:
    start.wait(timeout=5)
    store = StudyStore.for_exam_prep(Path(root))
    try:
        manifest = store.commit_revision(
            {
                "schema_version": 1,
                "derived_from_revision": 0,
                "concepts": {marker: {}},
            },
            {
                "schema_version": 1,
                "session_id": marker,
                "phase": "study",
                "pending_action": "continue",
            },
            {
                "schema_version": 1,
                "updated_at": NOW,
                "preferences": {},
                "stable_patterns": [],
            },
        )
        result_queue.put(("ok", manifest.revision))
    except Exception as exc:  # pragma: no cover - asserted by parent
        result_queue.put(("error", type(exc).__name__, str(exc)))


class StorageConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.store = StudyStore.for_exam_prep(self.root)
        self.store.initialize()
        self.context = multiprocessing.get_context("spawn")

    def tearDown(self):
        self.temp_dir.cleanup()

    def _process(self, target, *args):
        process = self.context.Process(target=target, args=args)
        process.start()
        return process

    def test_append_observation_waits_for_workspace_lock(self):
        start = self.context.Event()
        result_queue = self.context.Queue()

        with workspace_lock(self.store.state_path / "workspace.lock"):
            process = self._process(
                _append_worker,
                str(self.root),
                start,
                result_queue,
            )
            start.set()
            with self.assertRaises(queue.Empty):
                result_queue.get(timeout=0.25)

        self.assertEqual(("ok", True), result_queue.get(timeout=3))
        process.join(timeout=3)
        self.assertEqual(0, process.exitcode)

    def test_concurrent_identical_observations_append_once(self):
        start = self.context.Event()
        result_queue = self.context.Queue()
        processes = [
            self._process(_append_worker, str(self.root), start, result_queue)
            for _ in range(2)
        ]
        start.set()
        results = [result_queue.get(timeout=5) for _ in processes]
        for process in processes:
            process.join(timeout=3)
            self.assertEqual(0, process.exitcode)

        self.assertEqual([False, True], sorted(result[1] for result in results))
        self.assertTrue(all(result[0] == "ok" for result in results))
        self.assertEqual(1, len(self.store.read_complete_observations()))

    def test_concurrent_revision_commits_get_unique_numbers(self):
        start = self.context.Event()
        result_queue = self.context.Queue()
        processes = [
            self._process(
                _revision_worker,
                str(self.root),
                marker,
                start,
                result_queue,
            )
            for marker in ("worker-a", "worker-b")
        ]
        start.set()
        results = [result_queue.get(timeout=5) for _ in processes]
        for process in processes:
            process.join(timeout=3)
            self.assertEqual(0, process.exitcode)

        self.assertTrue(all(result[0] == "ok" for result in results), results)
        self.assertEqual([1, 2], sorted(result[1] for result in results))
        self.assertEqual(["000001", "000002"], sorted(
            path.name
            for path in self.store.revisions_path.iterdir()
            if path.is_dir() and path.name.isdigit()
        ))
        self.assertEqual(2, self.store.recover().manifest.revision)


if __name__ == "__main__":
    unittest.main()
