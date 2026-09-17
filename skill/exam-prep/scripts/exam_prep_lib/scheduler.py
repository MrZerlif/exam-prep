"""Compact exam-cram review scheduling and contextual prioritization."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any, Iterable

from .capabilities import AssessmentCapability, CapabilityRegistry
from .evidence_maturity import FACETS
from .reducer import DIMENSIONS, average_known_mastery, derive_assistance_band
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


def _configured_timezone(value: str | None) -> tzinfo:
    """Return the configured exam timezone without depending on host locale."""
    if value in (None, "", "UTC", "Z"):
        return timezone.utc
    if not isinstance(value, str):
        raise ValueError(f"invalid timezone: {value!r}")

    match = re.fullmatch(r"([+-])(\d{2}):(\d{2})", value)
    if match:
        sign = 1 if match.group(1) == "+" else -1
        hours = int(match.group(2))
        minutes = int(match.group(3))
        if hours > 23 or minutes > 59:
            raise ValueError(f"invalid timezone offset: {value}")
        return timezone(sign * timedelta(hours=hours, minutes=minutes))

    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(
            f"timezone {value!r} is unavailable; use an offset-aware exam date"
        ) from exc


def _exam_time(course: dict[str, Any], now: datetime) -> datetime | None:
    """Return the configured exam instant, or ``None`` when no date exists."""
    exam = course.get("exam", {})
    if not isinstance(exam, dict):
        raise ValueError("exam must be an object")
    raw = exam.get("date")
    if not raw:
        return None
    if not isinstance(raw, str):
        raise ValueError("exam.date must be an ISO datetime string")

    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid exam.date: {raw!r}") from exc
    if parsed.tzinfo is not None:
        return parsed
    configured_tz = _configured_timezone(exam.get("timezone"))
    return parsed.replace(tzinfo=configured_tz)


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
    """The reducer's ladder plus this scheduler's one extra signal.

    This used to be a hand-copied duplicate of derive_assistance_band, which
    is how a log the reducer could not read stayed unreadable here too:
    rebuild got past the reducer and then died on the same record in review
    scheduling. Delegating keeps one definition of what a band means, and
    inherits its totality for events written under the permissive schema.
    """
    if event.get("solution_exposed"):
        return "solution_seen"
    return derive_assistance_band(event.get("assistance"))


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


# ticket_list exams reward recall (verbatim/definition retrieval matters
# more than novel transfer); problem_set exams reward the opposite. These
# multiplicatively re-weight each dimension's contribution to the mastery
# gap (see _mastery_gap) rather than adding/removing dimensions from the
# required set - the target's own capabilities still decide *which*
# dimensions matter, the blueprint only decides how much each one counts.
QUESTION_MODEL_DIMENSION_WEIGHTS: dict[str, dict[str, float]] = {
    "ticket_list": {"recall": 1.5, "transfer": 0.5},
    "problem_set": {"recall": 0.5, "transfer": 1.5},
}

# Oral delivery is live, unprompted recitation - the same recall emphasis
# ticket_list gets, applied independently of question_model (an oral
# problem_set defense still rewards being able to state the setup from
# memory under live questioning). An earlier version of this function tried
# to express "oral" by adding "speed" to the required dimensions instead,
# but that is inert: the CLI never records elapsed/expected_seconds (see
# reducer.py's SCORED_AT_START comment and roadmap item 7.2), so
# mastery["speed"] is always None, and _mastery_gap drops None-valued
# dimensions from its weighted average before weights are ever applied -
# there is no live measurement for a weight to multiply. Recall weighting
# and the independence requirement below are what's actually measurable
# today; speed stays deferred to 7.2, where it belongs.
ORAL_RECALL_WEIGHT = 1.5


def _blueprint_dimension_weights(exam: dict[str, Any] | None) -> dict[str, float]:
    exam = exam or {}
    weights = dict(QUESTION_MODEL_DIMENSION_WEIGHTS.get(exam.get("question_model"), {}))
    if exam.get("delivery") == "oral":
        weights["recall"] = max(weights.get("recall", 1.0), ORAL_RECALL_WEIGHT)
    return weights


def _independence_pressure(state: dict[str, Any], exam: dict[str, Any] | None) -> float:
    """Oral delivery is judged live and unaided, so mastery built mostly on
    hinted attempts is not yet oral-ready even where the mastery *value*
    already looks solid (hinted attempts still move it, just more slowly -
    see reducer.py's ASSISTANCE_WEIGHTS). This keeps such a target under
    priority pressure until independent evidence catches up. A 1.0 (no-op)
    multiplier for any other delivery, and where there is no evidence yet
    to judge - gap/urgency alone decide in that case."""

    if (exam or {}).get("delivery") != "oral":
        return 1.0
    evidence = state.get("evidence", {})
    independent = float(evidence.get("independent_successes", 0))
    hinted = float(evidence.get("hinted_successes", 0))
    total = independent + hinted
    if total <= 0:
        return 1.0
    independent_ratio = independent / total
    return 1.0 + 0.5 * (1.0 - independent_ratio)


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
    state: dict[str, Any],
    required_dimensions: tuple[str, ...] | None,
    dimension_weights: dict[str, float] | None = None,
) -> float:
    if required_dimensions is None:
        return max(0.0, 1.0 - _average_mastery(state))
    weights = dimension_weights or {}
    entries = [
        (1.0 - float(value), weights.get(dimension, 1.0))
        for dimension in required_dimensions
        for value in (state.get("mastery", {}).get(dimension),)
        if value is not None
    ]
    if not entries:
        return max(0.0, 1.0 - _average_mastery(state))
    total_weight = sum(weight for _, weight in entries)
    if total_weight <= 0:
        return max(0.0, 1.0 - _average_mastery(state))
    return max(0.0, sum(gap * weight for gap, weight in entries) / total_weight)


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
    exam = course.get("exam", {})
    required_dimensions = _required_mastery_dimensions(metadata, syllabus)
    gap = _mastery_gap(state, required_dimensions, _blueprint_dimension_weights(exam))
    exam_time = _exam_time(course, now)
    if exam_time is None:
        exam_time = now + timedelta(days=7)
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
    independence_pressure = _independence_pressure(state, exam)
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
        * independence_pressure
    )
    score = round(raw_score * due_multiplier, 6)
    required_text = (
        "all evidence-backed dimensions"
        if required_dimensions is None
        else "required dimensions " + "/".join(required_dimensions)
    )
    prereq_text = "no prerequisites" if not prerequisites else f"prerequisite readiness {prerequisite_readiness:.2f}"
    due_text = ", due review 1.25x" if due else ""
    independence_text = (
        f", independence pressure {independence_pressure:.2f}x"
        if independence_pressure != 1.0
        else ""
    )
    reason = (
        f"exam value {exam_value:.2f}, mastery gap {gap:.2f} ({required_text}), "
        f"{prereq_text}, unlock value {prerequisite_unlock_value:.2f}, "
        f"evidence factor {evidence_factor:.2f}, time fit {time_fit:.2f}"
        f"{due_text}{independence_text}"
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

