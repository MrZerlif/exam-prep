"""Optional CAS boundary; the core package never depends on a CAS."""

from __future__ import annotations

from typing import Any


def verify(request: dict[str, Any]) -> dict[str, Any]:
    del request
    return {
        "status": "unavailable",
        "backend": "optional-cas",
        "message": "No optional symbolic backend is configured; use numerical finite differences.",
    }

