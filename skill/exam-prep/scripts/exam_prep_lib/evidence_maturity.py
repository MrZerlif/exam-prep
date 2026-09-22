"""Orthogonal evidence maturity facets, independent of mastery dimensions."""

from __future__ import annotations

from typing import Any, Iterable

from .capabilities import AssessmentCapability


FACETS = ("demonstrated", "retained", "transferred")


def empty_evidence_maturity() -> dict[str, dict[str, Any]]:
    return {
        facet: {"count": 0, "first_at": None, "last_at": None}
        for facet in FACETS
    }


def _event_facets(
    event: dict[str, Any],
    capability: AssessmentCapability | None = None,
) -> set[str]:
    if event.get("outcome") != "correct":
        return set()
    assistance = event.get("assistance") or {}
    if (
        event.get("outcome") == "solution_seen"
        or event.get("solution_exposed")
        or event.get("assessment_integrity") in {"explicit_exposure", "post_exposure_attempt"}
        or assistance.get("full_solution_viewed")
    ):
        return set()
    if capability is not None and not capability.is_registered:
        return set()
    explicit = event.get("evidence_facets")
    if isinstance(explicit, list):
        return {str(facet) for facet in explicit if str(facet) in FACETS}

    facets = {"demonstrated"}
    if capability is None:
        task_type = event.get("task_type")
        transfer_evidence = task_type in {"transfer", "exam_problem"}
        retention_evidence = task_type == "delayed_recall"
    else:
        transfer_evidence = capability.demonstrates_transfer()
        retention_evidence = capability.demonstrates_retention()
    if retention_evidence:
        facets.add("retained")
    if transfer_evidence:
        facets.add("transferred")
    return facets


def add_event_to_maturity(
    maturity: dict[str, dict[str, Any]],
    event: dict[str, Any],
    capability: AssessmentCapability | None = None,
) -> dict[str, dict[str, Any]]:
    recorded_at = event.get("recorded_at")
    for facet in _event_facets(event, capability):
        item = maturity[facet]
        item["count"] += 1
        if recorded_at is not None:
            if item["first_at"] is None or recorded_at < item["first_at"]:
                item["first_at"] = recorded_at
            if item["last_at"] is None or recorded_at > item["last_at"]:
                item["last_at"] = recorded_at
    return maturity


def derive_evidence_maturity(events: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    maturity = empty_evidence_maturity()
    for event in events:
        add_event_to_maturity(maturity, event)
    return maturity

