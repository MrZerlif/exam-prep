"""Deterministic reduction from canonical evidence to learner state."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


DIMENSIONS = ("conceptual", "procedural", "recall", "transfer", "speed")
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


def _empty_concept() -> dict[str, Any]:
    return {
        "mastery": {dimension: 0.0 for dimension in DIMENSIONS},
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
        "status": "unseen",
        "last_tested": None,
        "recurring_mistakes": [],
    }


def _update(prior: float, signal: float, alpha: float) -> float:
    return round(max(0.0, min(1.0, prior + alpha * (signal - prior))), 4)


def _outcome_signal(outcome: str) -> float | None:
    return {"correct": 1.0, "partial": 0.5, "incorrect": 0.0}.get(outcome)


def _status(state: dict[str, Any]) -> str:
    evidence = state["evidence"]
    average = sum(state["mastery"].values()) / len(DIMENSIONS)
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
    concepts: dict[str, dict[str, Any]] = {
        concept_id: _empty_concept()
        for concept_id in syllabus.get("concepts", {})
    }
    mistake_sessions: dict[tuple[str, str], set[str]] = defaultdict(set)
    for event in events:
        concept_id = event.get("concept_id")
        if concept_id not in concepts:
            continue
        state = concepts[concept_id]
        assistance_band = derive_assistance_band(event.get("assistance", {}))
        outcome = event.get("outcome", "skipped")
        signal = _outcome_signal(outcome)
        if outcome == "solution_seen" or event.get("assistance", {}).get("full_solution_viewed"):
            state["evidence"]["solution_views"] += 1
        if outcome in {"incorrect", "partial"}:
            state["evidence"]["failures"] += 1
        if outcome == "correct":
            if assistance_band == "independent":
                state["evidence"]["independent_successes"] += 1
            elif assistance_band != "solution_seen":
                state["evidence"]["hinted_successes"] += 1
            if event.get("task_type") == "delayed_recall":
                state["evidence"]["delayed_recall_successes"] += 1
            if event.get("task_type") == "transfer":
                state["evidence"]["transfer_successes"] += 1
            if event.get("task_type") == "exam_problem":
                state["evidence"]["exam_successes"] += 1

        if signal is not None and assistance_band != "solution_seen":
            alpha = 0.22 * ASSISTANCE_WEIGHTS[assistance_band]
            for dimension in TASK_DIMENSIONS.get(event.get("task_type"), ()):
                state["mastery"][dimension] = _update(
                    state["mastery"][dimension], signal, alpha
                )
            elapsed = event.get("elapsed_seconds")
            expected = event.get("expected_seconds")
            if outcome == "correct" and isinstance(elapsed, (int, float)) and isinstance(
                expected, (int, float)
            ) and expected > 0:
                speed_signal = max(0.0, min(1.0, expected / max(elapsed, 1)))
                state["mastery"]["speed"] = _update(
                    state["mastery"]["speed"], speed_signal, alpha
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

        for tag in event.get("error_tags", []):
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
                    "resolved": False,
                }
                state["recurring_mistakes"].append(existing)
            existing["count"] += 1
            existing["sessions_seen"] = len(mistake_sessions[key])

    for state in concepts.values():
        state["status"] = _status(state)
        state["recurring_mistakes"].sort(key=lambda item: (-item["count"], item["tag"]))

    return {
        "schema_version": 1,
        "derived_from_revision": int(policy.get("revision", 0)),
        "concepts": concepts,
    }
