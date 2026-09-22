"""Deterministic reduction from canonical evidence to learner state."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .capabilities import CapabilityRegistry, MASTERY_DIMENSIONS
from .defaults import DEFAULT_RECURRING_MISTAKE_POLICY
from .evidence_maturity import add_event_to_maturity, empty_evidence_maturity
from .target_normalization import normalize_event, normalize_syllabus

DIMENSIONS = MASTERY_DIMENSIONS
# Every dimension except speed always starts at a known 0.0 (every scored task
# updates at least one of conceptual/procedural/recall/transfer). speed is the
# odd one out: only a minority of task types touch it, and only when the CLI
# has actually measured elapsed/expected time - which today it never does.
# Absence of timing evidence is not evidence of zero speed, so speed starts
# (and stays) unknown/None until real timing evidence exists, and unknown
# dimensions are excluded from averaging rather than dragged to the floor.
SCORED_AT_START = tuple(dimension for dimension in DIMENSIONS if dimension != "speed")
CONFIDENCE_VALUES = {"low": 0.25, "medium": 0.55, "high": 0.9}
ASSISTANCE_WEIGHTS = {
    "independent": 1.0,
    "lightly_scaffolded": 0.8,
    "guided": 0.55,
    "heavily_scaffolded": 0.25,
    "solution_seen": 0.0,
}
TASK_DIMENSIONS = {
    "definition_recall": ("conceptual", "recall"),
    "formula_reading": ("recall",),
    "recognition": ("conceptual", "recall"),
    "explanation": ("conceptual",),
    "error_detection": ("conceptual", "procedural"),
    "worked_example": ("conceptual", "procedural"),
    "faded_example": ("procedural",),
    "guided_problem": ("procedural",),
    "independent_problem": ("procedural",),
    "transfer": ("procedural", "transfer"),
    "exam_problem": ("procedural", "transfer"),
    # delayed_recall is recall under delay, not novel transfer - crediting
    # transfer here overstated readiness for exactly the ticket-memorization
    # scenario this dimension exists to measure. Transfer credit for a
    # delayed task is opt-in via delayed_transfer instead. Keep this in sync
    # with CapabilityRegistry.with_defaults() in capabilities.py - both
    # define the same mapping for the v1/v2 task-type lookup, and
    # test_capabilities.py's test_task_dimensions_and_default_capability_
    # registry_agree fails if they drift apart.
    "delayed_recall": ("recall",),
    "delayed_transfer": ("recall", "transfer"),
}
MISTAKE_SUMMARIES = {
    "conceptual_error": "misunderstanding the governing concept",
    "formula_recall_error": "cannot retrieve the needed formula",
    "algebra_error": "algebraic transformation error",
    "method_selection_error": "selected an unsuitable method",
    "notation_error": "notation or expression-format error",
    "careless_error": "careless execution error",
    "speed_problem": "execution is too slow",
    "prerequisite_gap": "missing prerequisite knowledge",
    "domain_condition_error": "missed a domain or validity condition",
    "proof_structure_error": "proof structure is incomplete",
}
def derive_assistance_band(assistance: Any) -> str:
    """Total by construction, and conservative when it cannot tell.

    Proposals are schema-checked before they are appended, but logs written
    while the v2 assistance object was a bare `{"type": "object"}` can still
    hold `null`, `{}`, or a string where the ladder belongs. This function has
    to read those without raising: `rebuild` is the documented repair for such
    a workspace, and the canonical log must never be hand-edited.

    Unreadable assistance falls back to `guided`, not `independent`. An empty
    ladder is an explicit claim that no hint was given; a missing or malformed
    one is the absence of a claim, and independence is the strongest evidence
    in the model - it is never granted to an attempt that cannot show it.
    """
    if not isinstance(assistance, dict):
        return "guided"
    raw_levels = assistance.get("levels_revealed")
    stated = isinstance(raw_levels, (list, tuple, set))
    levels = set(raw_levels) if stated else set()
    if assistance.get("full_solution_viewed") or "H5" in levels:
        return "solution_seen"
    if assistance.get("partial_transformation_shown") or "H4" in levels:
        return "heavily_scaffolded"
    if levels.intersection({"H2", "H3"}):
        return "guided"
    if "H1" in levels:
        return "lightly_scaffolded"
    return "independent" if stated else "guided"


BAND_ORDER = ("independent", "lightly_scaffolded", "guided", "heavily_scaffolded", "solution_seen")
POST_EXPOSURE_MAX_BAND = "heavily_scaffolded"


def _effective_assistance(event: dict[str, Any]) -> Any:
    assistance = event.get("assistance") or {}
    if (
        event.get("solution_exposed")
        or event.get("assessment_integrity") == "explicit_exposure"
    ):
        assistance = {**assistance, "full_solution_viewed": True}
    return assistance


def event_assistance_band(event: dict[str, Any]) -> str:
    """The band one canonical event is credited at.

    A post_exposure_attempt reproduces a solution the learner has already
    seen, so it never scores above heavily_scaffolded."""

    band = derive_assistance_band(_effective_assistance(event))
    if (
        event.get("assessment_integrity") == "post_exposure_attempt"
        and BAND_ORDER.index(band) < BAND_ORDER.index(POST_EXPOSURE_MAX_BAND)
    ):
        return POST_EXPOSURE_MAX_BAND
    return band


def average_known_mastery(mastery: dict[str, Any]) -> float:
    """Average mastery over dimensions with actual evidence, excluding any
    dimension (currently only speed) that is still None/unknown."""
    known = [float(value) for value in mastery.values() if value is not None]
    if not known:
        return 0.0
    return sum(known) / len(known)


def _empty_concept() -> dict[str, Any]:
    return {
        "mastery": {
            **{dimension: 0.0 for dimension in SCORED_AT_START},
            "speed": None,
        },
        "confidence": {"diagnostic": 0.0, "learner_self_report": 0.0},
        "evidence": {
            "independent_successes": 0,
            "hinted_successes": 0,
            "failures": 0,
            "solution_views": 0,
            "delayed_recall_successes": 0,
            "transfer_successes": 0,
            "exam_successes": 0,
        },
        "evidence_maturity": empty_evidence_maturity(),
        "mastery_status": "unseen",
        "availability": "available",
        "last_tested": None,
        "recurring_mistakes": [],
    }


def _update(prior: float, signal: float, alpha: float) -> float:
    return round(max(0.0, min(1.0, prior + alpha * (signal - prior))), 4)


def _outcome_signal(outcome: str) -> float | None:
    return {"correct": 1.0, "partial": 0.5, "incorrect": 0.0}.get(outcome)


def _mastery_status(
    state: dict[str, Any],
    required_dimensions: tuple[str, ...] | None = None,
    requires_transfer: bool = True,
) -> str:
    evidence = state["evidence"]
    if not any(evidence.values()):
        return "unseen"
    dimensions = required_dimensions or SCORED_AT_START
    values = [
        state["mastery"].get(dimension)
        for dimension in dimensions
        if state["mastery"].get(dimension) is not None
    ]
    average = sum(values) / len(values) if values else 0.0
    transfer_evidence = evidence["transfer_successes"] + evidence["exam_successes"]
    if evidence["solution_views"] and not evidence["independent_successes"]:
        return "learning"
    if (
        average >= 0.85
        and evidence["independent_successes"] >= 3
        and (not requires_transfer or evidence["transfer_successes"] >= 2)
    ):
        return "mastered"
    if (
        average >= 0.55
        and evidence["independent_successes"] >= 2
        and (not requires_transfer or transfer_evidence >= 1)
    ):
        return "exam_ready"
    if evidence["failures"] and average < 0.45:
        return "weak"
    if evidence["independent_successes"] or evidence["hinted_successes"]:
        return "practicing"
    return "learning"


def _target_capability_semantics(
    target: dict[str, Any], capability_registry: CapabilityRegistry
) -> tuple[tuple[str, ...] | None, bool]:
    raw_ids = target.get("capability_ids", [])
    if isinstance(raw_ids, str):
        raw_ids = [raw_ids]
    if not isinstance(raw_ids, (list, tuple)):
        raw_ids = []
    if not raw_ids:
        return None, True
    dimensions: set[str] = set()
    requires_transfer = False
    for capability_id in raw_ids:
        capability = capability_registry.resolve(capability_id).capability
        if not capability.is_registered:
            continue
        dimensions.update(
            dimension
            for dimension in capability.affected_dimensions
            if dimension in DIMENSIONS
        )
        requires_transfer = requires_transfer or capability.demonstrates_transfer()
    if not dimensions:
        return None, requires_transfer
    return tuple(dimension for dimension in DIMENSIONS if dimension in dimensions), requires_transfer


def reduce_learning_state(
    course: dict[str, Any],
    syllabus: dict[str, Any],
    events: list[dict[str, Any]],
    policy: dict[str, Any],
) -> dict[str, Any]:
    question_model = (course.get("exam") or {}).get("question_model")
    mistake_policy = {**DEFAULT_RECURRING_MISTAKE_POLICY, **(policy.get("recurring_mistake") or {})}
    normalized_syllabus = normalize_syllabus(syllabus)
    capability_registry = CapabilityRegistry.from_syllabus(syllabus)
    unmapped_capability_events: list[str] = []
    concepts: dict[str, dict[str, Any]] = {
        concept_id: _empty_concept()
        for concept_id in normalized_syllabus.targets
    }
    mistake_sessions: dict[tuple[str, str], set[str]] = defaultdict(set)
    for raw_event in events:
        event = normalize_event(raw_event, normalized_syllabus)
        concept_id = event.get("target_id")
        if concept_id not in concepts:
            continue
        state = concepts[concept_id]
        capability_id = (
            event.get("capability_id")
            if event.get("capability_id") is not None
            else event.get("task_type")
        )
        capability_resolution = capability_registry.resolve(capability_id)
        capability = capability_resolution.capability
        legacy_task_semantics = (
            event.get("schema_version", 1) != 2
            or event.get("capability_id") is None
        )
        add_event_to_maturity(state["evidence_maturity"], event, capability)
        if capability_resolution.warning and capability.capability_id not in unmapped_capability_events:
            unmapped_capability_events.append(capability.capability_id)
        assistance = _effective_assistance(event)
        assistance_band = event_assistance_band(event)
        outcome = event.get("outcome", "skipped")
        signal = _outcome_signal(outcome)
        tags = event.get("error_tags", [])
        if outcome == "solution_seen" or event.get("solution_exposed") or assistance.get("full_solution_viewed"):
            state["evidence"]["solution_views"] += 1
        if outcome in {"incorrect", "partial"}:
            state["evidence"]["failures"] += 1
        if outcome == "correct":
            if capability.is_registered and assistance_band == "independent":
                state["evidence"]["independent_successes"] += 1
            elif capability.is_registered and assistance_band != "solution_seen":
                state["evidence"]["hinted_successes"] += 1
            retention_success = (
                capability.capability_id == "delayed_recall"
                if legacy_task_semantics
                else capability.demonstrates_retention()
            )
            transfer_success = (
                capability.capability_id == "transfer"
                if legacy_task_semantics
                else capability.demonstrates_transfer()
            )
            exam_success = (
                capability.capability_id == "exam_problem"
                if legacy_task_semantics
                else capability.counts_as_exam_success(question_model)
            )
            if retention_success and assistance_band == "independent":
                state["evidence"]["delayed_recall_successes"] += 1
            if transfer_success and assistance_band == "independent":
                state["evidence"]["transfer_successes"] += 1
            if exam_success and assistance_band == "independent":
                state["evidence"]["exam_successes"] += 1

        if (
            signal is not None
            and capability.is_registered
            and assistance_band != "solution_seen"
        ):
            alpha = 0.22 * ASSISTANCE_WEIGHTS[assistance_band]
            for dimension in capability.affected_dimensions:
                if dimension not in DIMENSIONS:
                    continue
                state["mastery"][dimension] = _update(
                    state["mastery"][dimension], signal, alpha
                )
            elapsed = event.get("elapsed_seconds")
            expected = event.get("expected_seconds")
            if outcome == "correct" and isinstance(elapsed, (int, float)) and isinstance(
                expected, (int, float)
            ) and expected > 0:
                prior_speed = state["mastery"]["speed"]
                speed_signal = max(0.0, min(1.0, expected / max(elapsed, 1)))
                state["mastery"]["speed"] = _update(
                    prior_speed if prior_speed is not None else 0.0, speed_signal, alpha
                )

        for confidence_key, output_key in (
            ("diagnostic_confidence", "diagnostic"),
            ("learner_self_confidence", "learner_self_report"),
        ):
            confidence_value = CONFIDENCE_VALUES.get(event.get(confidence_key))
            if confidence_value is not None:
                state["confidence"][output_key] = _update(
                    state["confidence"][output_key], confidence_value, 0.3
                )

        if event.get("recorded_at"):
            if state["last_tested"] is None or event["recorded_at"] > state["last_tested"]:
                state["last_tested"] = event["recorded_at"]

        # A clean independent success is evidence against every mistake this
        # concept has accumulated so far (not just ones matching this task's
        # tags): it must run before this event's own tags are folded in below,
        # so a mistake that reoccurs in the same event it would have been
        # resolved by is correctly kept open, not resolved and reopened.
        if outcome == "correct" and assistance_band == "independent":
            for mistake in state["recurring_mistakes"]:
                if mistake["resolved"] or mistake["tag"] in tags:
                    continue
                mistake["clean_streak"] += 1
                if mistake["clean_streak"] >= mistake_policy["resolve_after_clean_successes"]:
                    mistake["resolved"] = True

        for tag in tags:
            key = (concept_id, tag)
            mistake_sessions[key].add(event.get("session_id", "unknown"))
            existing = next(
                (item for item in state["recurring_mistakes"] if item["tag"] == tag),
                None,
            )
            if existing is None:
                existing = {
                    "tag": tag,
                    "summary": MISTAKE_SUMMARIES.get(tag, tag),
                    "count": 0,
                    "sessions_seen": 0,
                    "recurring": False,
                    "resolved": False,
                    "clean_streak": 0,
                }
                state["recurring_mistakes"].append(existing)
            existing["count"] += 1
            existing["sessions_seen"] = len(mistake_sessions[key])
            existing["clean_streak"] = 0
            existing["resolved"] = False
            existing["recurring"] = (
                existing["count"] >= mistake_policy["min_count"]
                or existing["sessions_seen"] >= mistake_policy["min_sessions"]
            )

    for concept_id, state in concepts.items():
        target = normalized_syllabus.targets.get(concept_id, {})
        required_dimensions, requires_transfer = _target_capability_semantics(
            target, capability_registry
        )
        state["mastery_status"] = _mastery_status(
            state, required_dimensions, requires_transfer
        )
        state["recurring_mistakes"].sort(key=lambda item: (-item["count"], item["tag"]))

    for concept_id, state in concepts.items():
        prerequisites = normalized_syllabus.targets.get(concept_id, {}).get("prerequisites", [])
        blocked = any(
            concepts[prereq]["mastery_status"] == "unseen"
            for prereq in prerequisites
            if prereq in concepts
        )
        state["availability"] = "prerequisite_blocked" if blocked else "available"

    if normalized_syllabus.schema_version >= 2:
        result = {
            "schema_version": 2,
            "derived_from_revision": int(policy.get("revision", 0)),
            "targets": concepts,
            "aliases": dict(normalized_syllabus.aliases),
        }
    else:
        result = {
            "schema_version": 1,
            "derived_from_revision": int(policy.get("revision", 0)),
            "concepts": concepts,
        }
    if unmapped_capability_events:
        result["unmapped_capability_events"] = unmapped_capability_events
    return result

