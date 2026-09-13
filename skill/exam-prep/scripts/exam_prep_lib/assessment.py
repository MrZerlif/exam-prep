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
        normalized = dict(value)
        normalized["source_refs"] = normalize_source_refs(value["source_refs"])
        calculated_hash = assessment_spec_hash(normalized)
        supplied_hash = value.get("spec_hash")
        if supplied_hash is not None and supplied_hash != calculated_hash:
            raise ValueError("assessment spec_hash does not match the frozen contract")
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
        }

