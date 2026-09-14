"""Immutable assessment contracts and deterministic specification hashes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from .provenance import normalize_source_refs


ASSESSMENT_HASH_FIELDS = (
    "assessment_id",
    "target_id",
    "capability_id",
    "prompt",
    "rubric",
    "expected_evidence",
    "source_refs",
    "difficulty",
    "question_version",
    "rubric_version",
)


def assessment_spec_hash(value: Mapping[str, Any]) -> str:
    payload = {field: value.get(field) for field in ASSESSMENT_HASH_FIELDS}
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


# The question's content identity, independent of assessment_id, purpose,
# difficulty, and version numbers - unlike spec_hash (which bakes
# assessment_id, question_version and rubric_version in, and so can never
# match across two differently-id'd or re-versioned assessments), this is
# what pool-isolation compares: the same question re-frozen under a new id,
# or with a bumped version number, must still be recognized as the same
# content - otherwise either one would be a way to launder trained-on
# material into the exam pool. Named question_hash rather than content_hash
# because content_hash is already a source-ref.schema.json field with
# different semantics (a source document's fingerprint, not a question's).
#
# Deliberately excludes rubric, expected_evidence, and source_refs, on top
# of the assessment_id/purpose/difficulty/version fields already excluded
# above: the learner is only ever shown the prompt (and target/capability
# implicitly, via what task they were given) - rubric, expected_evidence
# and source_refs are grading/provenance bookkeeping the learner never
# sees. Hashing them would let an author re-launder already-practiced
# content into the exam pool with a purely cosmetic rubric or citation
# edit, exactly the same loophole version numbers were closed for.
QUESTION_HASH_FIELDS = (
    "target_id",
    "capability_id",
    "prompt",
)


def _normalize_prompt_for_hashing(prompt: Any) -> Any:
    """Collapse incidental whitespace differences (leading/trailing space,
    a trailing newline, doubled internal spaces) so they cannot be used to
    dodge pool isolation while reading as the same question to a learner."""

    if isinstance(prompt, str):
        return " ".join(prompt.split())
    return prompt


def question_content_hash(value: Mapping[str, Any]) -> str:
    payload = {field: value.get(field) for field in QUESTION_HASH_FIELDS}
    payload["prompt"] = _normalize_prompt_for_hashing(payload.get("prompt"))
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


ASSESSMENT_PURPOSES = ("practice", "retest", "held_out", "mock")


@dataclass(frozen=True)
class FrozenAssessment:
    assessment_id: str
    target_id: str
    capability_id: str
    prompt: str
    rubric: Any
    expected_evidence: tuple[Any, ...]
    source_refs: tuple[dict[str, Any], ...]
    difficulty: int | float
    question_version: int
    rubric_version: int
    spec_hash: str
    question_hash: str
    purpose: str = "practice"

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "FrozenAssessment":
        required = (
            "assessment_id",
            "target_id",
            "capability_id",
            "prompt",
            "rubric",
            "expected_evidence",
            "source_refs",
            "difficulty",
            "question_version",
            "rubric_version",
        )
        missing = [field for field in required if field not in value]
        if missing:
            raise ValueError(f"assessment is missing required fields: {', '.join(missing)}")
        purpose = str(value.get("purpose", "practice"))
        if purpose not in ASSESSMENT_PURPOSES:
            raise ValueError(
                f"assessment purpose must be one of {ASSESSMENT_PURPOSES}, got {purpose!r}"
            )
        normalized = dict(value)
        normalized["source_refs"] = normalize_source_refs(value["source_refs"])
        calculated_hash = assessment_spec_hash(normalized)
        supplied_hash = value.get("spec_hash")
        if supplied_hash is not None and supplied_hash != calculated_hash:
            raise ValueError("assessment spec_hash does not match the frozen contract")
        calculated_question_hash = question_content_hash(normalized)
        supplied_question_hash = value.get("question_hash")
        if supplied_question_hash is not None and supplied_question_hash != calculated_question_hash:
            raise ValueError("assessment question_hash does not match the frozen contract")
        return cls(
            assessment_id=str(value["assessment_id"]),
            target_id=str(value["target_id"]),
            capability_id=str(value["capability_id"]),
            prompt=str(value["prompt"]),
            rubric=value["rubric"],
            expected_evidence=tuple(value["expected_evidence"]),
            source_refs=tuple(normalized["source_refs"]),
            difficulty=value["difficulty"],
            question_version=int(value["question_version"]),
            rubric_version=int(value["rubric_version"]),
            spec_hash=calculated_hash,
            question_hash=calculated_question_hash,
            purpose=purpose,
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "target_id": self.target_id,
            "capability_id": self.capability_id,
            "prompt": self.prompt,
            "rubric": self.rubric,
            "expected_evidence": list(self.expected_evidence),
            "source_refs": list(self.source_refs),
            "difficulty": self.difficulty,
            "question_version": self.question_version,
            "rubric_version": self.rubric_version,
            "spec_hash": self.spec_hash,
            "question_hash": self.question_hash,
            "purpose": self.purpose,
        }

