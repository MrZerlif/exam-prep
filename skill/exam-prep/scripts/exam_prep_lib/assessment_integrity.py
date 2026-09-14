"""Deterministic integrity checks for assessment-linked evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .assessment import FrozenAssessment


class AssessmentIntegrityError(ValueError):
    """An assessment event would violate the frozen attempt contract."""


# Which session phase an assessment's purpose may be attempted under.
# practice/retest are ordinary training and belong in study sessions; mock is
# the live exam simulation and belongs in an exam session. held_out is a
# reserved candidate pool rather than an in-progress mock, so it carries no
# phase requirement of its own - its protection is the content-hash pool
# isolation check below, not a phase gate.
PURPOSE_REQUIRED_PHASE = {
    "practice": "study",
    "retest": "study",
    "mock": "exam",
}

# The two content pools that must never share a question_hash (see
# question_hashes_with_purpose/assert_pool_isolation below). Membership
# alone is what is compared, in both directions - not whether either side
# has actually been attempted yet.
TRAINING_PURPOSES = ("practice", "retest")
EXAM_POOL_PURPOSES = ("held_out", "mock")


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
    session_phase: str = "study",
) -> AttemptEvidenceDecision:
    if event.get("assessment_id") != assessment.assessment_id:
        raise AssessmentIntegrityError("event assessment_id does not match frozen assessment")
    required_phase = PURPOSE_REQUIRED_PHASE.get(assessment.purpose)
    if required_phase is not None and session_phase != required_phase:
        raise AssessmentIntegrityError(
            f"assessment {assessment.assessment_id!r} has purpose {assessment.purpose!r}, "
            f"which requires session phase {required_phase!r}, but the session is in "
            f"phase {session_phase!r}"
        )
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


def question_hashes_with_purpose(
    assessments: Iterable[FrozenAssessment],
    purposes: Iterable[str],
) -> set[str]:
    """question_hash values already frozen under any of `purposes` -
    membership is by content, not assessment_id, so the same question
    re-frozen under a new id is still recognized as already in the pool."""

    wanted = set(purposes)
    return {
        assessment.question_hash
        for assessment in assessments
        if assessment.purpose in wanted
    }


def assert_pool_isolation(
    assessment: FrozenAssessment,
    *,
    existing_assessments: Iterable[FrozenAssessment],
) -> None:
    """Refuse to freeze an assessment whose content (question_hash) is
    already frozen on the opposite side of the practice/retest vs
    held_out/mock divide, in either direction:

    - held_out/mock must not reuse content already frozen as practice/retest
      (that would leak trained-on material into the exam pool);
    - practice/retest must not reuse content already frozen as held_out/mock
      (that would expose exam-pool material through ordinary practice).

    This is checked on mere freezing, not on whether either side has been
    attempted yet - requiring an attempt first leaves a window where a
    freshly-frozen-but-unattempted item's content could still cross pools.
    """

    if assessment.purpose in TRAINING_PURPOSES:
        opposing_purposes = EXAM_POOL_PURPOSES
    elif assessment.purpose in EXAM_POOL_PURPOSES:
        opposing_purposes = TRAINING_PURPOSES
    else:
        return
    opposing_hashes = question_hashes_with_purpose(existing_assessments, opposing_purposes)
    if assessment.question_hash in opposing_hashes:
        raise AssessmentIntegrityError(
            f"assessment {assessment.assessment_id!r} has purpose {assessment.purpose!r}, "
            f"but its question_hash {assessment.question_hash!r} is already frozen under "
            f"purpose in {opposing_purposes!r}; practice/retest content and held_out/mock "
            "content must not overlap"
        )

