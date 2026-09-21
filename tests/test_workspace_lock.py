import multiprocessing
import os
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))


def _lock_api():
    try:
        from exam_prep_lib.workspace_lock import WorkspaceBusy, workspace_lock
    except ModuleNotFoundError as exc:
        raise AssertionError("workspace lock API is missing") from exc
    return WorkspaceBusy, workspace_lock


def _timeout_worker(lock_path: str, result_queue) -> None:
    WorkspaceBusy, workspace_lock = _lock_api()
    try:
        with workspace_lock(Path(lock_path), timeout_seconds=0.2):
            result_queue.put("acquired")
    except WorkspaceBusy:
        result_queue.put("busy")


def _waiting_worker(lock_path: str, started, acquired) -> None:
    _WorkspaceBusy, workspace_lock = _lock_api()
    started.set()
    with workspace_lock(Path(lock_path), timeout_seconds=2.0):
        acquired.set()


def _crashing_worker(lock_path: str, acquired) -> None:
    _WorkspaceBusy, workspace_lock = _lock_api()
    with workspace_lock(Path(lock_path), timeout_seconds=2.0):
        acquired.set()
        os._exit(0)


class WorkspaceLockTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.lock_path = Path(self.temp_dir.name) / ".exam-prep" / "workspace.lock"
        self.context = multiprocessing.get_context("spawn")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_lock_is_reentrant_in_the_same_thread(self):
        _WorkspaceBusy, workspace_lock = _lock_api()

        with workspace_lock(self.lock_path, timeout_seconds=0.2):
            with workspace_lock(self.lock_path, timeout_seconds=0.2):
                self.assertTrue(self.lock_path.exists())

    def test_second_process_times_out_while_lock_is_held(self):
        _WorkspaceBusy, workspace_lock = _lock_api()
        result_queue = self.context.Queue()

        with workspace_lock(self.lock_path, timeout_seconds=0.2):
            process = self.context.Process(
                target=_timeout_worker,
                args=(str(self.lock_path), result_queue),
            )
            process.start()
            self.assertEqual("busy", result_queue.get(timeout=3))
            process.join(timeout=3)

        self.assertEqual(0, process.exitcode)

    def test_waiting_process_acquires_after_release(self):
        _WorkspaceBusy, workspace_lock = _lock_api()
        started = self.context.Event()
        acquired = self.context.Event()

        with workspace_lock(self.lock_path, timeout_seconds=0.2):
            process = self.context.Process(
                target=_waiting_worker,
                args=(str(self.lock_path), started, acquired),
            )
            process.start()
            self.assertTrue(started.wait(timeout=3))
            self.assertFalse(acquired.wait(timeout=0.2))

        self.assertTrue(acquired.wait(timeout=3))
        process.join(timeout=3)
        self.assertEqual(0, process.exitcode)

    def test_process_exit_releases_lock(self):
        _WorkspaceBusy, workspace_lock = _lock_api()
        acquired = self.context.Event()
        process = self.context.Process(
            target=_crashing_worker,
            args=(str(self.lock_path), acquired),
        )
        process.start()
        self.assertTrue(acquired.wait(timeout=3))
        process.join(timeout=3)
        self.assertEqual(0, process.exitcode)

        with workspace_lock(self.lock_path, timeout_seconds=0.5):
            self.assertTrue(self.lock_path.exists())


if __name__ == "__main__":
    unittest.main()
