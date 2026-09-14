"""Compact exam-cram review scheduling and contextual prioritization."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable

from .capabilities import AssessmentCapability, CapabilityRegistry
from .evidence_maturity import FACETS
from .reducer import DIMENSIONS, average_known_mastery
from .target_normalization import normalize_event, normalize_syllabus

# Minimum interval floor so a review is never scheduled instantly/negatively
# even when the exam is minutes away.
MIN_INTERVAL_HOURS = 1 / 6  # 10 minutes


def _parse_time(value: str | None, fallback: datetime) -> datetime | None:
    if not value:
        return fallback
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return fallback
    if parsed.tzinfo is None and fallback is not None and fallback.tzinfo is not None:
        parsed = parsed.replace(tzinfo=fallback.tzinfo)
    return parsed


def _exam_time(course: dict[str, Any], now: datetime) -> datetime | None:
    """The exam datetime if course.exam.date is set and parseable, else None
    (missing exam date - no horizon to compress reviews against)."""
    raw = course.get("exam", {}).get("date")
    if not raw:
        return None
    return _parse_time(raw, now)


def _urgency_cap_hours(remaining_hours: float) -> float:
    """Cap a review interval to a fraction of the remaining study horizon so
    multiple reviews still fit before the exam. Smaller fraction the closer
    the exam is - a small, explainable heuristic, not FSRS."""
    if remaining_hours <= 3:
        fraction = 0.15
    elif remaining_hours <= 24:
        fraction = 0.25
    elif remaining_hours <= 72:
        fraction = 0.4
    elif remaining_hours <= 24 * 7:
        fraction = 0.6
    else:
        fraction = 1.0
    return max(MIN_INTERVAL_HOURS, remaining_hours * fraction)


def _average_mastery(state: dict[str, Any]) -> float:
    return average_known_mastery(state.get("mastery", {}))


def _event_band(event: dict[str, Any]) -> str:
    levels = set(event.get("assistance", {}).get("levels_revealed", []))
    assistance = event.get("assistance", {})
    if event.get("solution_exposed") or assistance.get("full_solution_viewed") or "H5" in levels:
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


def _event_review_kind(
    event: dict[str, Any], capability_registry: CapabilityRegistry
) -> str:
    schema_version = event.get("schema_version", 1)
    capability_id = event.get("capability_id")
    if schema_version == 2 and capability_id is not None:
        return capability_registry.resolve(str(capability_id)).capability.review_kind
    return _review_kind(event.get("task_type", ""))


def _review_status(due_at: datetime, now: datetime, interval_hours: float) -> str:
    if due_at > now:
        return "not_due"
    overdue_hours = (now - due_at).total_seconds() / 3600
    grace = max(interval_hours, 1.0)
    return "overdue" if overdue_hours > grace else "due"


def build_review_queue(
    events: list[dict[str, Any]],
    concepts: dict[str, Any],
    course: dict[str, Any],
    now: datetime,
    syllabus: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_syllabus = normalize_syllabus(syllabus or {})
    capability_registry = CapabilityRegistry.from_syllabus(syllabus or {})
    grouped: dict[str, list[dict[str, Any]]] = {}
    for raw_event in events:
        event = normalize_event(raw_event, normalized_syllabus)
        grouped.setdefault(event.get("target_id", event.get("concept_id", "")), []).append(event)
    cap = int(course.get("scheduler", {}).get("max_review_interval_hours", 72))
    exam_time = _exam_time(course, now)
    has_valid_exam_horizon = exam_time is not None and exam_time > now
    concept_metadata = normalized_syllabus.targets
    items: dict[str, dict[str, Any]] = {}
    for concept_id, concept_events in grouped.items():
        if not concept_id:
            continue
        last = concept_events[-1]
        outcome = last.get("outcome")
        band = _event_band(last)
        review_kind = _event_review_kind(last, capability_registry)
        if outcome == "solution_seen" or band == "solution_seen":
            base_interval = 2
        elif outcome == "incorrect":
            base_interval = 4
        elif outcome == "partial":
            base_interval = 8
        elif outcome == "correct" and review_kind == "delayed_recall":
            base_interval = 48
        elif outcome == "correct" and band == "independent":
            base_interval = 24
        else:
            base_interval = 12

        lapses = sum(item.get("outcome") in {"incorrect", "partial"} for item in concept_events)
        average_mastery = _average_mastery(concepts.get(concept_id, {}))
        mastery_factor = 0.5 + 0.5 * average_mastery
        lapses_factor = max(0.4, 1.0 - 0.1 * lapses)
        importance = float(concept_metadata.get(concept_id, {}).get("importance", 0.5))
        importance_factor = min(1.15, max(0.85, 1.15 - 0.3 * importance))
        interval = base_interval * mastery_factor * lapses_factor * importance_factor
        interval = max(MIN_INTERVAL_HOURS, min(cap, interval))

        reason_parts = [
            f"base {base_interval}h for last outcome '{outcome}'",
            f"mastery {average_mastery:.2f}",
            f"{lapses} lapse(s)",
            f"importance {importance:.2f}",
        ]

        last_time = _parse_time(last.get("recorded_at"), now)
        if has_valid_exam_horizon:
            remaining_hours = max(0.0, (exam_time - now).total_seconds() / 3600)
            urgency_cap = _urgency_cap_hours(remaining_hours)
            if urgency_cap < interval:
                interval = max(MIN_INTERVAL_HOURS, urgency_cap)
                reason_parts.append(f"compressed for {remaining_hours:.1f}h exam horizon")
            due_at = min(last_time + timedelta(hours=interval), exam_time)
        else:
            due_at = last_time + timedelta(hours=interval)

        items[concept_id] = {
            "due_at": due_at.isoformat(),
            "last_review_at": last_time.isoformat(),
            "interval_hours": round(interval, 4),
            "lapses": lapses,
            "last_outcome": outcome,
            "review_kind": review_kind,
            "review_status": _review_status(due_at, now, interval),
            "reason": ", ".join(reason_parts),
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
                "review_status": "due",
                "reason": "no prior evidence for this concept",
            },
        )
    return {"schema_version": 1, "derived_from_revision": 0, "items": items}


def _target_capabilities(
    metadata: dict[str, Any], syllabus: dict[str, Any]
) -> list[AssessmentCapability]:
    raw_ids = metadata.get("capability_ids", [])
    if isinstance(raw_ids, str):
        raw_ids = [raw_ids]
    if not isinstance(raw_ids, (list, tuple)):
        raw_ids = []
    registry = CapabilityRegistry.from_syllabus(syllabus)
    return [
        registry.resolve(capability_id).capability
        for capability_id in raw_ids
        if registry.resolve(capability_id).capability.is_registered
    ]


def _required_mastery_dimensions(
    metadata: dict[str, Any], syllabus: dict[str, Any]
) -> tuple[str, ...] | None:
    dimensions = {
        dimension
        for capability in _target_capabilities(metadata, syllabus)
        for dimension in capability.affected_dimensions
        if dimension in DIMENSIONS
    }
    if not dimensions:
        return None
    return tuple(dimension for dimension in DIMENSIONS if dimension in dimensions)


def _capability_evidence_facets(
    metadata: dict[str, Any], syllabus: dict[str, Any]
) -> set[str]:
    capabilities = _target_capabilities(metadata, syllabus)
    facets = {"demonstrated"}
    for capability in capabilities:
        if capability.demonstrates_retention():
            facets.add("retained")
        if capability.demonstrates_transfer():
            facets.add("transferred")
    return facets


def _evidence_confidence(
    state: dict[str, Any], required_facets: set[str]
) -> tuple[dict[str, float], float]:
    maturity = state.get("evidence_maturity", {})
    confidence = {
        facet: min(
            1.0,
            max(0.0, float((maturity.get(facet) or {}).get("count", 0))) / 2.0,
        )
        for facet in FACETS
    }
    relevant = [confidence[facet] for facet in required_facets]
    factor = 0.85 + 0.15 * (sum(relevant) / len(relevant) if relevant else 0.0)
    return confidence, factor


def _exam_value(metadata: dict[str, Any]) -> float:
    return (
        float(metadata.get("importance", 0.5))
        * float(metadata.get("frequency", 0.5))
        * max(1.0, float(metadata.get("expected_points", 1.0)))
    )


def _prerequisite_unlock_value(
    concept_id: str,
    targets: dict[str, dict[str, Any]],
    concepts: dict[str, Any],
) -> float:
    downstream_value = 0.0
    for target_id, metadata in targets.items():
        if concept_id not in metadata.get("prerequisites", []):
            continue
        downstream_gap = max(0.0, 1.0 - _average_mastery(concepts.get(target_id, {})))
        downstream_value += _exam_value(metadata) * downstream_gap
    return 1.0 + min(0.5, downstream_value / 20.0)


def _mastery_gap(
    state: dict[str, Any], required_dimensions: tuple[str, ...] | None
) -> float:
    if required_dimensions is None:
        return max(0.0, 1.0 - _average_mastery(state))
    values = [
        state.get("mastery", {}).get(dimension)
        for dimension in required_dimensions
        if state.get("mastery", {}).get(dimension) is not None
    ]
    if not values:
        return max(0.0, 1.0 - _average_mastery(state))
    return max(0.0, sum(1.0 - float(value) for value in values) / len(values))


def compute_priority(
    concept_id: str,
    syllabus: dict[str, Any],
    concepts: dict[str, Any],
    reviews: dict[str, Any],
    course: dict[str, Any],
    now: datetime,
    budget_minutes: int,
) -> dict[str, Any]:
    normalized_syllabus = normalize_syllabus(syllabus)
    targets = normalized_syllabus.targets
    metadata = targets.get(concept_id, {})
    state = concepts.get(concept_id, {})
    required_dimensions = _required_mastery_dimensions(metadata, syllabus)
    gap = _mastery_gap(state, required_dimensions)
    exam = course.get("exam", {})
    exam_time = _parse_time(exam.get("date"), now + timedelta(days=7))
    days_left = max(0.0, (exam_time - now).total_seconds() / 86400)
    urgency = 1.0 + max(0.0, (7.0 - days_left) / 7.0)
    exam_value = _exam_value(metadata)
    prerequisites = metadata.get("prerequisites", [])
    prerequisite_values = [_average_mastery(concepts.get(item, {})) for item in prerequisites]
    prerequisite_readiness = (
        1.0 if not prerequisite_values else 0.5 + 0.5 * (sum(prerequisite_values) / len(prerequisite_values))
    )
    prerequisite_unlock_value = _prerequisite_unlock_value(
        concept_id, targets, concepts
    )
    evidence_confidence, evidence_factor = _evidence_confidence(
        state, _capability_evidence_facets(metadata, syllabus)
    )
    estimated = max(1.0, float(metadata.get("estimated_learning_minutes", 30)))
    time_fit = 1.0 if estimated <= budget_minutes else max(0.1, budget_minutes / estimated)
    review = reviews.get(concept_id, reviews.get("items", {}).get(concept_id, {}))
    due = bool(review and review.get("due_at") and _parse_time(review["due_at"], now) <= now)
    due_multiplier = 1.25 if due else 1.0
    improvement = max(0.1, gap * time_fit)
    raw_score = (
        exam_value
        * gap
        * urgency
        * prerequisite_readiness
        * prerequisite_unlock_value
        * evidence_factor
        * improvement
        / estimated
    )
    score = round(raw_score * due_multiplier, 6)
    required_text = (
        "all evidence-backed dimensions"
        if required_dimensions is None
        else "required dimensions " + "/".join(required_dimensions)
    )
    prereq_text = "no prerequisites" if not prerequisites else f"prerequisite readiness {prerequisite_readiness:.2f}"
    due_text = ", due review 1.25x" if due else ""
    reason = (
        f"exam value {exam_value:.2f}, mastery gap {gap:.2f} ({required_text}), "
        f"{prereq_text}, unlock value {prerequisite_unlock_value:.2f}, "
        f"evidence factor {evidence_factor:.2f}, time fit {time_fit:.2f}{due_text}"
    )
    exam_revision = int(exam.get("revision", course.get("exam_revision", 1)))
    return {
        "concept_id": concept_id,
        "score": score,
        "mastery_gap": round(gap, 6),
        "required_mastery_dimensions": (
            list(required_dimensions) if required_dimensions is not None else []
        ),
        "prerequisite_unlock_value": round(prerequisite_unlock_value, 6),
        "evidence_confidence": evidence_confidence,
        "evidence_factor": round(evidence_factor, 6),
        "reason": reason,
        "computed_for": {
            "computed_at": now.isoformat(),
            "budget_minutes": int(budget_minutes),
            "exam_revision": exam_revision,
        },
    }


def _classify_activity(concept_state: dict[str, Any], review_item: dict[str, Any]) -> str:
    """Pedagogical activity type for the selected concept. A review_queue
    entry existing (with a due_at) is not by itself evidence of a review:
    build_review_queue gives every concept a 'diagnostic' fallback entry
    with due_at=now even when it has never been attempted."""
    mastery_status = concept_state.get("mastery_status", "unseen")
    has_prior_evidence = bool(review_item) and review_item.get("review_kind") != "diagnostic"
    if mastery_status == "unseen" or not has_prior_evidence:
        return "new_learning"
    review_status = review_item.get("review_status", "not_due")
    if review_status not in ("due", "overdue"):
        return "targeted_learning"
    if mastery_status in ("weak", "learning"):
        return "targeted_review"
    return "review"


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
    target_ids = normalize_syllabus(syllabus).targets
    candidates = [
        compute_priority(
            concept_id, syllabus, concepts, reviews, course, now, budget_minutes
        )
        for concept_id in target_ids
    ]
    if not candidates:
        raise ValueError("syllabus has no concepts")
    non_recent = [
        candidate
        for candidate in candidates
        if candidate["concept_id"] not in recent
        and concepts.get(candidate["concept_id"], {}).get("availability") != "prerequisite_blocked"
    ]
    pool = non_recent or candidates
    selected = max(pool, key=lambda item: (item["score"], item["concept_id"]))
    if selected["concept_id"] not in recent and recent:
        selected["reason"] += "; interleaved with a non-recent concept"
    selected["activity_type"] = _classify_activity(
        concepts.get(selected["concept_id"], {}),
        reviews.get(selected["concept_id"], {}),
    )
    return selected

