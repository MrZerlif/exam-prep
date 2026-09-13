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
    integrity: str = "frozen_attempt"


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
    if event.get("target_id") != assessment.target_id:
        raise AssessmentIntegrityError("event target_id does not match frozen assessment")
    if event.get("capability_id") != assessment.capability_id:
        raise AssessmentIntegrityError("event capability_id does not match frozen assessment")
    linked_contract = event.get("assessment")
    if linked_contract is not None:
        if not isinstance(linked_contract, dict):
            raise AssessmentIntegrityError("event assessment linkage must be an object")
        if (
            linked_contract.get("assessment_id") is not None
            and linked_contract.get("assessment_id") != assessment.assessment_id
        ):
            raise AssessmentIntegrityError("linked assessment_id does not match frozen assessment")
        if linked_contract.get("target_id") != assessment.target_id:
            raise AssessmentIntegrityError("linked assessment target_id does not match frozen assessment")
        if linked_contract.get("capability_id") != assessment.capability_id:
            raise AssessmentIntegrityError("linked assessment capability_id does not match frozen assessment")
        linked_hash = linked_contract.get("spec_hash", linked_contract.get("assessment_spec_hash"))
        if linked_hash is not None and linked_hash != assessment.spec_hash:
            raise AssessmentIntegrityError("linked assessment spec hash does not match frozen assessment")
    supplied_hash = event.get("assessment_spec_hash", event.get("spec_hash"))
    if supplied_hash is not None and supplied_hash != assessment.spec_hash:
        raise AssessmentIntegrityError("event assessment spec hash does not match frozen assessment")

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
            integrity="explicit_exposure",
        )
    return AttemptEvidenceDecision(
        accepted=True, mastery_eligible=True, integrity="frozen_attempt"
    )

