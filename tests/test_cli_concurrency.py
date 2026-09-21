import contextlib
import io
import json
import multiprocessing
import queue
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep import main  # noqa: E402
from exam_prep_lib.workspace_lock import workspace_lock  # noqa: E402


def _status_worker(
    root: str,
    start,
    result_queue,
    timeout_seconds: float,
) -> None:
    start.wait(timeout=5)
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output):
            code = main(
                ["--workspace", root, "status"],
                _workspace_lock_timeout_seconds=timeout_seconds,
            )
    except Exception as exc:  # pragma: no cover - asserted by parent
        result_queue.put(("error", {"type": type(exc).__name__, "detail": str(exc)}))
        return
    result_queue.put((code, json.loads(output.getvalue())))


class CliConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.context = multiprocessing.get_context("spawn")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--workspace", str(self.root), "init"])
        self.assertEqual(0, code, output.getvalue())
        self.lock_path = self.root / ".exam-prep" / "workspace.lock"

    def tearDown(self):
        self.temp_dir.cleanup()

    def _status_process(self, timeout_seconds: float):
        start = self.context.Event()
        result_queue = self.context.Queue()
        process = self.context.Process(
            target=_status_worker,
            args=(str(self.root), start, result_queue, timeout_seconds),
        )
        process.start()
        start.set()
        # The event has to outlive this helper: on POSIX its semaphore is
        # unlinked as soon as the creating process drops the last reference,
        # and the spawned child then cannot reopen it.
        return process, start, result_queue

    def test_initialized_status_waits_for_workspace_transaction(self):
        with workspace_lock(self.lock_path):
            process, _start, result_queue = self._status_process(timeout_seconds=2.0)
            with self.assertRaises(queue.Empty):
                result_queue.get(timeout=0.25)

        code, payload = result_queue.get(timeout=3)
        process.join(timeout=3)
        self.assertEqual(0, process.exitcode)
        self.assertEqual(0, code)
        self.assertIn("course", payload)

    def test_lock_timeout_returns_workspace_busy(self):
        with workspace_lock(self.lock_path):
            process, _start, result_queue = self._status_process(timeout_seconds=0.2)
            code, payload = result_queue.get(timeout=3)

        process.join(timeout=3)
        self.assertEqual(0, process.exitcode)
        self.assertEqual(1, code)
        self.assertEqual("workspace_busy", payload["status"])
        self.assertEqual(str(self.root), payload["workspace"])


if __name__ == "__main__":
    unittest.main()
