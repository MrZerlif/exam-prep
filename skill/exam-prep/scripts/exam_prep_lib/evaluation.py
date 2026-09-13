"""Small read-only summaries for later evaluation and benchmarking."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Iterable, Mapping


CONFIDENCE_VALUES = {"low": 0.25, "medium": 0.55, "high": 0.9}


def _score(event: Mapping[str, Any]) -> float | None:
    result = event.get("assessment_result")
    if not isinstance(result, Mapping):
        return None
    score, maximum = result.get("score"), result.get("max_score")
    if not isinstance(score, (int, float)) or not isinstance(maximum, (int, float)) or maximum <= 0:
        return None
    return float(score) / float(maximum)


def _stage_score(events: list[Mapping[str, Any]], stages: set[str]) -> float | None:
    values = [
        score
        for event in events
        if isinstance(event.get("evaluation_context"), Mapping)
        and str(event["evaluation_context"].get("stage", "")).casefold() in stages
        for score in [_score(event)]
        if score is not None
    ]
    return values[-1] if values else None


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def summarize_evaluation(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate optional evaluation metadata without changing canonical events."""

    records = [event for event in events if isinstance(event, Mapping)]
    active_time = sum(
        float(event["elapsed_seconds"])
        for event in records
        if isinstance(event.get("elapsed_seconds"), (int, float))
        and event["elapsed_seconds"] >= 0
    )
    scores = [score for event in records if (score := _score(event)) is not None]
    task_counts = Counter(str(event["task_id"]) for event in records if event.get("task_id"))
    errors = Counter(
        str(tag)
        for event in records
        for tag in event.get("error_tags", [])
        if isinstance(event.get("error_tags", []), list)
    )
    hints = sum(
        bool((event.get("assistance") or {}).get("levels_revealed"))
        or bool((event.get("assistance") or {}).get("requested"))
        for event in records
    )
    exposures = sum(
        event.get("outcome") == "solution_seen"
        or event.get("solution_exposed")
        or event.get("assessment_integrity") == "explicit_exposure"
        or bool((event.get("assistance") or {}).get("full_solution_viewed"))
        for event in records
    )
    independent_success = next(
        (
            event
            for event in records
            if event.get("outcome") == "correct"
            and not (event.get("assistance") or {}).get("levels_revealed")
            and not event.get("solution_exposed")
            and event.get("assessment_integrity") != "explicit_exposure"
        ),
        None,
    )
    first_at = _timestamp(records[0].get("recorded_at")) if records else None
    success_at = _timestamp(independent_success.get("recorded_at")) if independent_success else None
    calibration = [
        abs(float(CONFIDENCE_VALUES[str(event["learner_self_confidence"])]) - score)
        for event in records
        if str(event.get("learner_self_confidence")) in CONFIDENCE_VALUES
        for score in [_score(event)]
        if score is not None
    ]
    return {
        "active_study_seconds": (
            int(active_time) if float(active_time).is_integer() else active_time
        ),
        "score_gain": round(scores[-1] - scores[0], 4) if len(scores) >= 2 else None,
        "time_to_independent_success": (
            (success_at - first_at).total_seconds()
            if first_at is not None and success_at is not None
            else None
        ),
        "hints": hints,
        "full_solution_exposure": exposures,
        "retries": sum(max(0, count - 1) for count in task_counts.values()),
        "recurring_errors": {
            tag: count for tag, count in sorted(errors.items()) if count >= 2
        },
        "delayed_score": _stage_score(records, {"delayed", "delayed_recall", "retention"}),
        "transfer_score": _stage_score(records, {"transfer"}),
        "mock_score": _stage_score(records, {"mock", "exam", "mock_exam"}),
        "confidence_calibration": {
            "mean_absolute_error": round(sum(calibration) / len(calibration), 4)
            if calibration
            else None,
            "sample_count": len(calibration),
        },
    }
