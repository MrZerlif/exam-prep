"""Shared test helpers."""

import contextlib
import io


@contextlib.contextmanager
def quiet():
    """Capture stdout for the duration of the block, and hand it over.

    Deliberately a capture rather than a mute: several tests assert on what
    the CLI prints, so they need the buffer, not silence.
    """

    with contextlib.redirect_stdout(io.StringIO()) as buffer:
        yield buffer
