"""Deterministic reduction from canonical evidence to learner state."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .capabilities import CapabilityRegistry
from .evidence_maturity import add_event_to_maturity, empty_evidence_maturity
from .target_normalization import normalize_event, normalize_syllabus

DIMENSIONS = ("conceptual", "procedural", "recall", "transfer", "speed")
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
    "delayed_recall": ("recall", "transfer"),
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
# Configurable policy defaults for recurring-mistake classification and
# resolution. A single occurrence is just an occurrence, not yet a pattern;
# "recurring" requires it to show up again, either repeatedly in one session
# or across separate sessions. Resolution requires a real clean streak so a
# single lucky guess cannot erase the history immediately.
DEFAULT_RECURRING_MISTAKE_POLICY = {
    "min_count": 3,
    "min_sessions": 2,
    "resolve_after_clean_successes": 3,
}


def derive_assistance_band(assistance: dict[str, Any]) -> str:
    levels = set(assistance.get("levels_revealed", []))
    if assistance.get("full_solution_viewed") or "H5" in levels:
        return "solution_seen"
    if assistance.get("partial_transformation_shown") or "H4" in levels:
        return "heavily_scaffolded"
    if levels.intersection({"H2", "H3"}):
        return "guided"
    if "H1" in levels:
        return "lightly_scaffolded"
    return "independent"


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


def _mastery_status(state: dict[str, Any]) -> str:
    evidence = state["evidence"]
    if not any(evidence.values()):
        return "unseen"
    average = average_known_mastery(state["mastery"])
    if evidence["solution_views"] and not evidence["independent_successes"]:
        return "learning"
    if (
        average >= 0.85
        and evidence["independent_successes"] >= 3
        and evidence["transfer_successes"] >= 2
    ):
        return "mastered"
    if (
        average >= 0.55
        and evidence["independent_successes"] >= 2
        and evidence["transfer_successes"] + evidence["exam_successes"] >= 1
    ):
        return "exam_ready"
    if evidence["failures"] and average < 0.45:
        return "weak"
    if evidence["independent_successes"] or evidence["hinted_successes"]:
        return "practicing"
    return "learning"


def reduce_learning_state(
    course: dict[str, Any],
    syllabus: dict[str, Any],
    events: list[dict[str, Any]],
    policy: dict[str, Any],
) -> dict[str, Any]:
    del course
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
        add_event_to_maturity(state["evidence_maturity"], event)
        capability_id = (
            event.get("capability_id")
            if event.get("capability_id") is not None
            else event.get("task_type")
        )
        capability_resolution = capability_registry.resolve(capability_id)
        capability = capability_resolution.capability
        if capability_resolution.warning and capability.capability_id not in unmapped_capability_events:
            unmapped_capability_events.append(capability.capability_id)
        assistance = event.get("assistance") or {}
        if (
            event.get("solution_exposed")
            or event.get("assessment_integrity") == "explicit_exposure"
        ):
            assistance = {**assistance, "full_solution_viewed": True}
        assistance_band = derive_assistance_band(assistance)
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
            if capability.is_registered and capability.capability_id == "delayed_recall":
                state["evidence"]["delayed_recall_successes"] += 1
            if capability.is_registered and capability.capability_id == "transfer":
                state["evidence"]["transfer_successes"] += 1
            if capability.is_registered and capability.capability_id == "exam_problem":
                state["evidence"]["exam_successes"] += 1

        if (
            signal is not None
            and capability.is_registered
            and assistance_band != "solution_seen"
        ):
            alpha = 0.22 * ASSISTANCE_WEIGHTS[assistance_band]
            for dimension in capability.affected_dimensions:
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
        state["mastery_status"] = _mastery_status(state)
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

