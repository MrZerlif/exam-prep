"""Deterministic integrity checks for assessment-linked evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .assessment import FrozenAssessment


class AssessmentIntegrityError(ValueError):
    """An assessment event would violate the frozen attempt contract."""


@dataclass(frozen=True)
class AttemptEvidenceDecision:
    accepted: bool
    mastery_eligible: bool
    diagnostic: str | None = None


def _is_attempt(event: dict[str, Any]) -> bool:
    return event.get("outcome") in {"correct", "partial", "incorrect"}


def _exposes_solution(event: dict[str, Any]) -> bool:
    assistance = event.get("assistance") or {}
    return bool(
        event.get("outcome") == "solution_seen"
        or assistance.get("full_solution_viewed")
        or event.get("solution_exposed")
    )


def assess_attempt_evidence(
    event: dict[str, Any],
    assessment: FrozenAssessment,
    *,
    prior_events: Iterable[dict[str, Any]],
) -> AttemptEvidenceDecision:
    if event.get("assessment_id") != assessment.assessment_id:
        raise AssessmentIntegrityError("event assessment_id does not match frozen assessment")

    previous = [
        prior
        for prior in prior_events
        if prior.get("assessment_id") == assessment.assessment_id
    ]
    attempted_before = any(_is_attempt(prior) for prior in previous)
    exposes_solution = _exposes_solution(event)
    explicit_reason = event.get("explicit_exposure_reason")

    if exposes_solution and not attempted_before and not explicit_reason:
        raise AssessmentIntegrityError(
            "assessment-linked solution exposure before attempt requires an explicit reason"
        )
    if exposes_solution:
        return AttemptEvidenceDecision(
            accepted=True,
            mastery_eligible=False,
            diagnostic="solution_exposure_downgraded",
        )
    return AttemptEvidenceDecision(accepted=True, mastery_eligible=True)

