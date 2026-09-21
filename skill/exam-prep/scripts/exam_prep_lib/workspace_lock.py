"""Cross-process exclusive locking for one exam-prep workspace."""

from __future__ import annotations

import errno
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator


if os.name == "nt":
    import msvcrt
elif os.name == "posix":
    import fcntl
else:  # pragma: no cover - supported runtimes are Windows and POSIX
    raise RuntimeError(f"workspace locking is unsupported on os.name={os.name!r}")


class WorkspaceBusy(RuntimeError):
    """The workspace is currently owned by another process."""


_thread_state = threading.local()


def _held_locks() -> dict[str, list[object]]:
    held = getattr(_thread_state, "held_locks", None)
    if held is None:
        held = {}
        _thread_state.held_locks = held
    return held


def _lock_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve(strict=False)))


def _try_acquire(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _release(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _is_busy_error(exc: OSError) -> bool:
    return (
        isinstance(exc, BlockingIOError)
        or exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}
        or getattr(exc, "winerror", None) in {33, 36}
    )


@contextmanager
def workspace_lock(
    lock_path: Path,
    *,
    timeout_seconds: float = 10.0,
) -> Iterator[None]:
    """Hold an exclusive workspace lock, reentrant within the current thread."""

    path = Path(lock_path)
    key = _lock_key(path)
    held = _held_locks()
    existing = held.get(key)
    if existing is not None:
        existing[1] = int(existing[1]) + 1
        try:
            yield
        finally:
            existing[1] = int(existing[1]) - 1
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b", buffering=0)
    if path.stat().st_size == 0:
        handle.write(b"\0")
        handle.flush()
        os.fsync(handle.fileno())

    deadline = time.monotonic() + max(0.0, float(timeout_seconds))
    while True:
        try:
            _try_acquire(handle)
            break
        except OSError as exc:
            if not _is_busy_error(exc):
                handle.close()
                raise
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                handle.close()
                raise WorkspaceBusy(f"workspace is busy: {path}") from exc
            time.sleep(min(0.05, remaining))

    held[key] = [handle, 1]
    try:
        yield
    finally:
        current = held.pop(key)
        locked_handle = current[0]
        try:
            _release(locked_handle)
        finally:
            locked_handle.close()
