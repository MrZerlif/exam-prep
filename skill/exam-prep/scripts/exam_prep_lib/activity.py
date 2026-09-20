"""Pure state transitions for engine-owned study activity timing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping


class ActivityStateError(ValueError):
    """Current session contains an impossible or unreadable activity state."""


@dataclass(frozen=True)
class ActivityTransition:
    session: dict[str, Any]
    payload: dict[str, Any]
    exit_code: int
    changed: bool


@dataclass(frozen=True)
class ActivityConsumption:
    session: dict[str, Any]
    elapsed_seconds: int | None
    matched: bool


_ACTIVITY_FIELDS = (
    "active_activity_id",
    "active_activity_started_at",
    "pending_activity_id",
    "pending_activity_elapsed_seconds",
)


def _parse_timestamp(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ActivityStateError(f"{label} must be a non-empty timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ActivityStateError(f"{label} is not a valid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ActivityStateError(f"{label} must be timezone-aware")
    return parsed


def elapsed_seconds(started_at: str, ended_at: str) -> int:
    start = _parse_timestamp(started_at, "started_at")
    end = _parse_timestamp(ended_at, "ended_at")
    return max(0, int((end - start).total_seconds()))


def _clear_activity(session: dict[str, Any]) -> None:
    for field in _ACTIVITY_FIELDS:
        session[field] = None


def _validated_state(session: Mapping[str, Any]) -> tuple[str, str | None, str | None, int | None]:
    active_id = session.get("active_activity_id")
    started_at = session.get("active_activity_started_at")
    pending_id = session.get("pending_activity_id")
    pending_elapsed = session.get("pending_activity_elapsed_seconds")
    active_any = active_id is not None or started_at is not None
    pending_any = pending_id is not None or pending_elapsed is not None
    if active_any and (not isinstance(active_id, str) or not active_id or not isinstance(started_at, str) or not started_at):
        raise ActivityStateError("active activity fields must be a non-empty ID and timestamp pair")
    if pending_any and (not isinstance(pending_id, str) or not pending_id or not isinstance(pending_elapsed, int) or isinstance(pending_elapsed, bool) or pending_elapsed < 0):
        raise ActivityStateError("pending activity fields must be a non-empty ID and non-negative integer pair")
    if active_any and pending_any:
        raise ActivityStateError("active and pending activity cannot coexist")
    if active_any:
        _parse_timestamp(started_at, "active_activity_started_at")
        return "active", active_id, started_at, None
    if pending_any:
        return "pending", pending_id, None, pending_elapsed
    return "idle", None, None, None


def _raw_state(session: Mapping[str, Any]) -> tuple[str, str | None, int | None]:
    active_id = session.get("active_activity_id")
    started_at = session.get("active_activity_started_at")
    pending_id = session.get("pending_activity_id")
    pending_elapsed = session.get("pending_activity_elapsed_seconds")
    active_valid = (
        isinstance(active_id, str)
        and bool(active_id)
        and isinstance(started_at, str)
        and bool(started_at)
    )
    pending_valid = (
        isinstance(pending_id, str)
        and bool(pending_id)
        and isinstance(pending_elapsed, int)
        and not isinstance(pending_elapsed, bool)
        and pending_elapsed >= 0
    )
    if active_id is None and started_at is None and pending_id is None and pending_elapsed is None:
        return "idle", None, None
    if active_valid and pending_id is None and pending_elapsed is None:
        return "active", active_id, None
    if pending_valid and active_id is None and started_at is None:
        return "pending", pending_id, pending_elapsed
    return "invalid", None, None


def _require_activity_id(activity_id: str) -> None:
    if not isinstance(activity_id, str) or not activity_id:
        raise ActivityStateError("activity_id must be a non-empty string")


def activity_status(session: Mapping[str, Any]) -> dict[str, Any]:
    state, activity_id, started_at, pending_elapsed = _validated_state(session)
    if state == "idle":
        return {"status": "idle"}
    if state == "active":
        return {"status": "active", "activity_id": activity_id, "started_at": started_at}
    return {"status": "pending", "activity_id": activity_id, "elapsed_seconds": pending_elapsed}


def start_activity(session: Mapping[str, Any], activity_id: str, recorded_at: str) -> ActivityTransition:
    result = dict(session)
    _require_activity_id(activity_id)
    _parse_timestamp(recorded_at, "recorded_at")
    state, current_id, started_at, pending_elapsed = _validated_state(session)
    if state == "idle":
        result["active_activity_id"] = activity_id
        result["active_activity_started_at"] = recorded_at
        result["pending_activity_id"] = None
        result["pending_activity_elapsed_seconds"] = None
        return ActivityTransition(result, {"status": "activity_started", "activity_id": activity_id, "started_at": recorded_at}, 0, True)
    if state == "active":
        if current_id == activity_id:
            return ActivityTransition(result, {"status": "activity_started", "activity_id": current_id, "started_at": started_at}, 0, False)
        return ActivityTransition(result, {"status": "activity_already_in_progress", "activity_id": current_id, "requested_activity_id": activity_id}, 1, False)
    return ActivityTransition(result, {"status": "pending_activity_not_consumed", "activity_id": current_id, "elapsed_seconds": pending_elapsed}, 1, False)


def finish_activity(session: Mapping[str, Any], recorded_at: str) -> ActivityTransition:
    result = dict(session)
    state, activity_id, started_at, pending_elapsed = _validated_state(session)
    if state == "pending":
        return ActivityTransition(result, {"status": "activity_already_finished", "activity_id": activity_id, "elapsed_seconds": pending_elapsed}, 0, False)
    if state == "idle":
        return ActivityTransition(result, {"status": "no_activity_in_progress"}, 1, False)
    elapsed = elapsed_seconds(started_at, recorded_at)
    _clear_activity(result)
    result["pending_activity_id"] = activity_id
    result["pending_activity_elapsed_seconds"] = elapsed
    return ActivityTransition(result, {"status": "activity_finished", "activity_id": activity_id, "elapsed_seconds": elapsed}, 0, True)


def discard_activity(session: Mapping[str, Any]) -> ActivityTransition:
    result = dict(session)
    state, activity_id, pending_elapsed = _raw_state(session)
    if state == "idle":
        return ActivityTransition(result, {"status": "no_activity"}, 0, False)
    if state == "invalid":
        _clear_activity(result)
        return ActivityTransition(result, {"status": "activity_discarded", "activity_id": None, "previous_state": "invalid", "discarded_elapsed_seconds": None}, 0, True)
    _clear_activity(result)
    return ActivityTransition(result, {"status": "activity_discarded", "activity_id": activity_id, "previous_state": state, "discarded_elapsed_seconds": pending_elapsed if state == "pending" else None}, 0, True)


def consume_activity(session: Mapping[str, Any], activity_id: str | None, recorded_at: str) -> ActivityConsumption:
    result = dict(session)
    state, current_id, started_at, pending_elapsed = _validated_state(session)
    if activity_id is None or state == "idle" or activity_id != current_id:
        return ActivityConsumption(result, None, False)
    if state == "active":
        elapsed = elapsed_seconds(started_at, recorded_at)
    else:
        elapsed = pending_elapsed
    _clear_activity(result)
    return ActivityConsumption(result, elapsed, True)
