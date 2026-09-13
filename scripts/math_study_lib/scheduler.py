"""Compact exam-cram review scheduling and contextual prioritization."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable


def _parse_time(value: str | None, fallback: datetime) -> datetime:
    if not value:
        return fallback
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None and fallback.tzinfo is not None:
        parsed = parsed.replace(tzinfo=fallback.tzinfo)
    return parsed


def _average_mastery(state: dict[str, Any]) -> float:
    mastery = state.get("mastery", {})
    values = [float(mastery.get(key, 0.0)) for key in ("conceptual", "procedural", "recall", "transfer", "speed")]
    return sum(values) / len(values)


def _event_band(event: dict[str, Any]) -> str:
    levels = set(event.get("assistance", {}).get("levels_revealed", []))
    assistance = event.get("assistance", {})
    if assistance.get("full_solution_viewed") or "H5" in levels:
        return "solution_seen"
    if assistance.get("partial_transformation_shown") or "H4" in levels:
        return "heavily_scaffolded"
    if levels.intersection({"H2", "H3"}):
        return "guided"
    if "H1" in levels:
        return "lightly_scaffolded"
    return "independent"


def _review_kind(task_type: str) -> str:
    return {
        "definition_recall": "definition_recall",
        "formula_reading": "formula_reading",
        "recognition": "method_recognition",
        "error_detection": "error_detection",
        "transfer": "transfer",
        "delayed_recall": "delayed_recall",
    }.get(task_type, "targeted_problem")


def build_review_queue(
    events: list[dict[str, Any]],
    concepts: dict[str, Any],
    course: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        grouped.setdefault(event.get("concept_id", ""), []).append(event)
    cap = int(course.get("scheduler", {}).get("max_review_interval_hours", 72))
    items: dict[str, dict[str, Any]] = {}
    for concept_id, concept_events in grouped.items():
        if not concept_id:
            continue
        last = concept_events[-1]
        outcome = last.get("outcome")
        band = _event_band(last)
        if outcome == "solution_seen" or band == "solution_seen":
            interval = 2
        elif outcome == "incorrect":
            interval = 4
        elif outcome == "partial":
            interval = 8
        elif outcome == "correct" and last.get("task_type") == "delayed_recall":
            interval = 48
        elif outcome == "correct" and band == "independent":
            interval = 24
        else:
            interval = 12
        interval = max(1, min(cap, interval))
        lapses = sum(item.get("outcome") in {"incorrect", "partial"} for item in concept_events)
        last_time = _parse_time(last.get("recorded_at"), now)
        items[concept_id] = {
            "due_at": (last_time + timedelta(hours=interval)).isoformat(),
            "last_review_at": last_time.isoformat(),
            "interval_hours": interval,
            "lapses": lapses,
            "last_outcome": outcome,
            "review_kind": _review_kind(last.get("task_type", "")),
        }
    for concept_id in concepts:
        items.setdefault(
            concept_id,
            {
                "due_at": now.isoformat(),
                "last_review_at": None,
                "interval_hours": 0,
                "lapses": 0,
                "last_outcome": None,
                "review_kind": "diagnostic",
            },
        )
    return {"schema_version": 1, "derived_from_revision": 0, "items": items}


def compute_priority(
    concept_id: str,
    syllabus: dict[str, Any],
    concepts: dict[str, Any],
    reviews: dict[str, Any],
    course: dict[str, Any],
    now: datetime,
    budget_minutes: int,
) -> dict[str, Any]:
    metadata = syllabus.get("concepts", {}).get(concept_id, {})
    state = concepts.get(concept_id, {})
    average = _average_mastery(state)
    gap = max(0.0, 1.0 - average)
    exam = course.get("exam", {})
    exam_time = _parse_time(exam.get("date"), now + timedelta(days=7))
    days_left = max(0.0, (exam_time - now).total_seconds() / 86400)
    urgency = 1.0 + max(0.0, (7.0 - days_left) / 7.0)
    exam_value = (
        float(metadata.get("importance", 0.5))
        * float(metadata.get("frequency", 0.5))
        * max(1.0, float(metadata.get("expected_points", 1.0)))
    )
    prerequisites = metadata.get("prerequisites", [])
    prerequisite_values = [_average_mastery(concepts.get(item, {})) for item in prerequisites]
    prerequisite_readiness = (
        1.0 if not prerequisite_values else 0.5 + 0.5 * (sum(prerequisite_values) / len(prerequisite_values))
    )
    estimated = max(1.0, float(metadata.get("estimated_learning_minutes", 30)))
    time_fit = 1.0 if estimated <= budget_minutes else max(0.1, budget_minutes / estimated)
    review = reviews.get(concept_id, reviews.get("items", {}).get(concept_id, {}))
    due = bool(review and review.get("due_at") and _parse_time(review["due_at"], now) <= now)
    due_multiplier = 1.25 if due else 1.0
    improvement = max(0.1, gap * time_fit)
    raw_score = exam_value * gap * urgency * prerequisite_readiness * improvement / estimated
    score = round(raw_score * due_multiplier, 6)
    prereq_text = "no prerequisites" if not prerequisites else f"prerequisite readiness {prerequisite_readiness:.2f}"
    reason = (
        f"exam value {exam_value:.2f}, mastery gap {gap:.2f}, "
        f"{prereq_text}, time fit {time_fit:.2f}"
    )
    exam_revision = int(exam.get("revision", course.get("exam_revision", 1)))
    return {
        "concept_id": concept_id,
        "score": score,
        "reason": reason,
        "computed_for": {
            "computed_at": now.isoformat(),
            "budget_minutes": int(budget_minutes),
            "exam_revision": exam_revision,
        },
    }


def select_next_activity(
    syllabus: dict[str, Any],
    concepts: dict[str, Any],
    reviews: dict[str, Any],
    course: dict[str, Any],
    now: datetime,
    budget_minutes: int,
    recent_concept_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    recent = set(recent_concept_ids or [])
    candidates = [
        compute_priority(
            concept_id, syllabus, concepts, reviews, course, now, budget_minutes
        )
        for concept_id in syllabus.get("concepts", {})
    ]
    if not candidates:
        raise ValueError("syllabus has no concepts")
    non_recent = [
        candidate
        for candidate in candidates
        if candidate["concept_id"] not in recent
        and concepts.get(candidate["concept_id"], {}).get("status") != "locked"
    ]
    pool = non_recent or candidates
    selected = max(pool, key=lambda item: (item["score"], item["concept_id"]))
    if selected["concept_id"] not in recent and recent:
        selected["reason"] += "; interleaved with a non-recent concept"
    selected["activity_type"] = (
        "review"
        if selected["concept_id"] in reviews and reviews[selected["concept_id"]].get("due_at")
        else "targeted_learning"
    )
    return selected
