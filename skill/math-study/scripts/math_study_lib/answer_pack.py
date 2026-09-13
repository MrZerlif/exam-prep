"""Portable, provenance-preserving answer packs for exam review."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from .assessment import FrozenAssessment
from .provenance import normalize_source_refs


PACK_HASH_FIELDS = (
    "assessment_id",
    "assessment_spec_hash",
    "target_id",
    "capability_id",
    "prompt",
    "learner_response",
    "rubric",
    "source_refs",
    "verification",
    "feedback",
)


def _pack_hash(value: Mapping[str, Any]) -> str:
    payload = {field: value.get(field) for field in PACK_HASH_FIELDS}
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class ExamAnswerPack:
    assessment_id: str
    assessment_spec_hash: str
    target_id: str
    capability_id: str
    prompt: str
    learner_response: str
    rubric: Any
    source_refs: tuple[dict[str, Any], ...]
    verification: dict[str, Any]
    feedback: str | None
    pack_hash: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ExamAnswerPack":
        required = (
            "assessment_id",
            "assessment_spec_hash",
            "target_id",
            "capability_id",
            "prompt",
            "learner_response",
            "rubric",
            "source_refs",
            "verification",
        )
        missing = [field for field in required if field not in value]
        if missing:
            raise ValueError(f"answer pack is missing required fields: {', '.join(missing)}")
        normalized = dict(value)
        normalized["source_refs"] = normalize_source_refs(value["source_refs"])
        calculated = _pack_hash(normalized)
        if value.get("pack_hash") is not None and value["pack_hash"] != calculated:
            raise ValueError("answer pack hash does not match its contents")
        return cls(
            assessment_id=str(value["assessment_id"]),
            assessment_spec_hash=str(value["assessment_spec_hash"]),
            target_id=str(value["target_id"]),
            capability_id=str(value["capability_id"]),
            prompt=str(value["prompt"]),
            learner_response=str(value["learner_response"]),
            rubric=value["rubric"],
            source_refs=tuple(normalized["source_refs"]),
            verification=dict(value["verification"]),
            feedback=value.get("feedback"),
            pack_hash=calculated,
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "assessment_spec_hash": self.assessment_spec_hash,
            "target_id": self.target_id,
            "capability_id": self.capability_id,
            "prompt": self.prompt,
            "learner_response": self.learner_response,
            "rubric": self.rubric,
            "source_refs": list(self.source_refs),
            "verification": self.verification,
            "feedback": self.feedback,
            "pack_hash": self.pack_hash,
        }


def build_exam_answer_pack(
    assessment: FrozenAssessment,
    *,
    learner_response: str,
    verification: Mapping[str, Any] | None = None,
    feedback: str | None = None,
) -> ExamAnswerPack:
    return ExamAnswerPack.from_mapping(
        {
            "assessment_id": assessment.assessment_id,
            "assessment_spec_hash": assessment.spec_hash,
            "target_id": assessment.target_id,
            "capability_id": assessment.capability_id,
            "prompt": assessment.prompt,
            "learner_response": learner_response,
            "rubric": assessment.rubric,
            "source_refs": list(assessment.source_refs),
            "verification": dict(verification or {"status": "not_run"}),
            "feedback": feedback,
        }
    )
