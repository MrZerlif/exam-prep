"""Exam-ready answer artifacts and separate assessment feedback artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from .assessment import FrozenAssessment
from .provenance import normalize_source_refs


PACK_HASH_FIELDS = (
    "pack_id",
    "target_id",
    "assessment_id",
    "assessment_spec_hash",
    "definition_or_thesis",
    "key_points",
    "required_terminology",
    "answer_structure",
    "diagram_cues",
    "likely_examiner_follow_ups",
    "practice_prompt",
    "source_refs",
    "coverage",
    "confidence",
)
FEEDBACK_HASH_FIELDS = (
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
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        .encode("utf-8")
    ).hexdigest()


def _feedback_hash(value: Mapping[str, Any]) -> str:
    payload = {field: value.get(field) for field in FEEDBACK_HASH_FIELDS}
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _string_tuple(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"answer pack {field} must be an array")
    return tuple(str(item) for item in value)


@dataclass(frozen=True)
class ExamAnswerPack:
    pack_id: str
    target_id: str
    assessment_id: str | None
    assessment_spec_hash: str | None
    definition_or_thesis: str
    key_points: tuple[str, ...]
    required_terminology: tuple[str, ...]
    answer_structure: tuple[str, ...]
    diagram_cues: tuple[str, ...]
    likely_examiner_follow_ups: tuple[str, ...]
    practice_prompt: str
    source_refs: tuple[dict[str, Any], ...]
    coverage: dict[str, Any]
    confidence: float | str | None
    pack_hash: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ExamAnswerPack":
        required = (
            "pack_id",
            "target_id",
            "definition_or_thesis",
            "key_points",
            "required_terminology",
            "answer_structure",
            "likely_examiner_follow_ups",
            "practice_prompt",
            "source_refs",
            "coverage",
        )
        missing = [field for field in required if field not in value]
        if missing:
            raise ValueError(f"answer pack is missing required fields: {', '.join(missing)}")
        if not isinstance(value["coverage"], Mapping):
            raise ValueError("answer pack coverage must be an object")
        normalized = dict(value)
        normalized["source_refs"] = normalize_source_refs(value["source_refs"])
        normalized.setdefault("diagram_cues", [])
        normalized.setdefault("confidence", None)
        calculated = _pack_hash(normalized)
        if value.get("pack_hash") is not None and value["pack_hash"] != calculated:
            raise ValueError("answer pack hash does not match its contents")
        return cls(
            pack_id=str(value["pack_id"]),
            target_id=str(value["target_id"]),
            assessment_id=str(value["assessment_id"]) if value.get("assessment_id") is not None else None,
            assessment_spec_hash=str(value["assessment_spec_hash"]) if value.get("assessment_spec_hash") is not None else None,
            definition_or_thesis=str(value["definition_or_thesis"]),
            key_points=_string_tuple(value["key_points"], "key_points"),
            required_terminology=_string_tuple(value["required_terminology"], "required_terminology"),
            answer_structure=_string_tuple(value["answer_structure"], "answer_structure"),
            diagram_cues=_string_tuple(value["diagram_cues"], "diagram_cues"),
            likely_examiner_follow_ups=_string_tuple(
                value["likely_examiner_follow_ups"], "likely_examiner_follow_ups"
            ),
            practice_prompt=str(value["practice_prompt"]),
            source_refs=tuple(normalized["source_refs"]),
            coverage=dict(value["coverage"]),
            confidence=value.get("confidence"),
            pack_hash=calculated,
        )

    def to_mapping(self) -> dict[str, Any]:
        result = {
            "pack_id": self.pack_id,
            "target_id": self.target_id,
            "definition_or_thesis": self.definition_or_thesis,
            "key_points": list(self.key_points),
            "required_terminology": list(self.required_terminology),
            "answer_structure": list(self.answer_structure),
            "diagram_cues": list(self.diagram_cues),
            "likely_examiner_follow_ups": list(self.likely_examiner_follow_ups),
            "practice_prompt": self.practice_prompt,
            "source_refs": list(self.source_refs),
            "coverage": dict(self.coverage),
            "confidence": self.confidence,
            "pack_hash": self.pack_hash,
        }
        if self.assessment_id is not None:
            result["assessment_id"] = self.assessment_id
        if self.assessment_spec_hash is not None:
            result["assessment_spec_hash"] = self.assessment_spec_hash
        return result


@dataclass(frozen=True)
class AssessmentFeedbackPack:
    "Legacy-compatible response/rubric/verification artifact, distinct from ExamAnswerPack."

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
    def from_mapping(cls, value: Mapping[str, Any]) -> "AssessmentFeedbackPack":
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
            raise ValueError(
                f"assessment feedback pack is missing required fields: {', '.join(missing)}"
            )
        if not isinstance(value["verification"], Mapping):
            raise ValueError("assessment feedback verification must be an object")
        normalized = dict(value)
        normalized["source_refs"] = normalize_source_refs(value["source_refs"])
        calculated = _feedback_hash(normalized)
        if value.get("pack_hash") is not None and value["pack_hash"] != calculated:
            raise ValueError("assessment feedback pack hash does not match its contents")
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
            feedback=str(value["feedback"]) if value.get("feedback") is not None else None,
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
            "verification": dict(self.verification),
            "feedback": self.feedback,
            "pack_hash": self.pack_hash,
        }


def build_exam_answer_pack(
    *,
    target_id: str | None = None,
    pack_id: str | None = None,
    definition_or_thesis: str,
    key_points: list[str],
    required_terminology: list[str] | None = None,
    answer_structure: list[str] | None = None,
    diagram_cues: list[str] | None = None,
    likely_examiner_follow_ups: list[str] | None = None,
    practice_prompt: str,
    source_refs: list[Any] | None = None,
    coverage: Mapping[str, Any] | None = None,
    confidence: float | str | None = None,
    assessment: FrozenAssessment | None = None,
    attempt_made: bool = False,
    exposure_mode: str | None = None,
) -> ExamAnswerPack:
    """Build an exam artifact after an attempt, with explicit teaching/cram exception."""

    if assessment is not None:
        if not attempt_made and exposure_mode not in {"teaching", "cram"}:
            raise ValueError(
                "assessment-linked ExamAnswerPack requires an independent attempt first"
            )
        if target_id is not None and target_id != assessment.target_id:
            raise ValueError("ExamAnswerPack target_id does not match the assessment")
        target_id = target_id or assessment.target_id
        assessment_id = assessment.assessment_id
        assessment_spec_hash = assessment.spec_hash
    else:
        assessment_id = None
        assessment_spec_hash = None
    if not target_id:
        raise ValueError("target_id is required")
    return ExamAnswerPack.from_mapping(
        {
            "pack_id": pack_id or f"pack:{target_id}",
            "target_id": target_id,
            "assessment_id": assessment_id,
            "assessment_spec_hash": assessment_spec_hash,
            "definition_or_thesis": definition_or_thesis,
            "key_points": list(key_points),
            "required_terminology": list(required_terminology or []),
            "answer_structure": list(answer_structure or []),
            "diagram_cues": list(diagram_cues or []),
            "likely_examiner_follow_ups": list(likely_examiner_follow_ups or []),
            "practice_prompt": practice_prompt,
            "source_refs": list(source_refs or []),
            "coverage": dict(coverage or {}),
            "confidence": confidence,
        }
    )


def build_assessment_feedback_pack(
    assessment: FrozenAssessment,
    *,
    learner_response: str,
    verification: Mapping[str, Any] | None = None,
    feedback: str | None = None,
) -> AssessmentFeedbackPack:
    """Keep response/rubric review separate from the exam-ready answer artifact."""

    return AssessmentFeedbackPack.from_mapping(
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
