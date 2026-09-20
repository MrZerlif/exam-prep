"""Build and finalize extracted assessment drafts without minting them early."""

from __future__ import annotations

from dataclasses import asdict
from math import ceil
from typing import Any, Iterable, Mapping, Sequence

from .assessment import question_content_hash
from .capabilities import CapabilityRegistry
from .defaults import VERB_SLOT_TO_CAPABILITY
from .lexicon import Lexicon, load
from .semantics import best_slot


class DraftValidationError(ValueError):
    """The draft cannot be safely converted into a mint package."""


def _source_path(source_id: str) -> str:
    return source_id.split("#", 1)[0]


def _capability(question: Any, language: str = "ru", *, lexicon: Lexicon | None = None) -> str:
    if question.kind == "exam":
        return "exam_problem"
    found = best_slot("verb.", question.prompt, lexicon or load(language))
    return VERB_SLOT_TO_CAPABILITY.get(found.slot, "independent_problem") if found else "independent_problem"


def _purpose(question: Any, held_out: set[str]) -> str:
    if question.kind == "homework":
        return "practice"
    return "held_out" if _source_path(question.source_ref.get("source_id", "")) in held_out else "practice"


def build_draft(
    questions: Iterable[Any],
    *,
    target_map: Mapping[str, str] | None = None,
    reserve_for_mock: Sequence[str] = (),
    holdout_ratio: float = 0.2,
    origin: str = "extracted",
    language: str = "ru",
    lexicon: Lexicon | None = None,
) -> dict[str, Any]:
    if origin not in {"extracted", "authored", "model_generated"}:
        raise DraftValidationError(f"unknown origin: {origin!r}")
    materialized = tuple(questions)
    if not 0 <= float(holdout_ratio) <= 1:
        raise DraftValidationError("holdout_ratio must be between 0 and 1")
    exam_sources = sorted({_source_path(str(q.source_ref.get("source_id", ""))) for q in materialized if q.kind == "exam"})
    held_out = set(reserve_for_mock)
    if not held_out and exam_sources and holdout_ratio > 0:
        count = max(1, min(len(exam_sources), ceil(len(exam_sources) * float(holdout_ratio))))
        held_out.update(exam_sources[-count:])
    max_points = max((q.points or 0 for q in materialized), default=0)
    assessments: list[dict[str, Any]] = []
    for question in materialized:
        source_refs = [dict(question.source_ref)]
        draft = {
            "question_id": question.question_id,
            "target_id": (target_map or {}).get(question.question_id),
            "capability_id": _capability(question, language, lexicon=lexicon),
            "prompt": question.prompt,
            "rubric": {"reference_answer": question.reference_answer} if question.reference_answer else {},
            "expected_evidence": question.expected_evidence,
            "source_refs": source_refs,
            "difficulty": round((question.points / max_points) if max_points and question.points else 0.5, 4),
            "question_version": 1,
            "rubric_version": 1,
            "origin": origin,
            "purpose": _purpose(question, held_out),
            "options": list(question.options),
            "points": question.points,
            "question_hash": None,
            "issues": [issue.to_mapping() for issue in question.issues],
        }
        if origin == "model_generated":
            draft["source_refs"] = []
        draft["question_hash"] = question_content_hash({**draft, "target_id": draft["target_id"] or "unmapped"})
        assessments.append(draft)
    return {"schema_version": 1, "assessments": assessments, "issues": [issue for item in assessments for issue in item["issues"]]}


def _normalize_target_map(target_map: Mapping[str, Any]) -> dict[str, str]:
    if "targets" in target_map and isinstance(target_map["targets"], list):
        return {
            str(item["question_id"]): str(item["target_id"])
            for item in target_map["targets"]
            if isinstance(item, Mapping) and item.get("question_id") and item.get("target_id")
        }
    return {str(key): str(value) for key, value in target_map.items() if value is not None}


def finalize_draft(draft: Mapping[str, Any], target_map: Mapping[str, Any]) -> dict[str, Any]:
    entries = draft.get("assessments")
    if not isinstance(entries, list) or not entries:
        raise DraftValidationError("draft must contain a non-empty assessments array")
    mapping = _normalize_target_map(target_map)
    missing = [str(entry.get("question_id")) for entry in entries if not mapping.get(str(entry.get("question_id")))]
    if missing:
        raise DraftValidationError("missing target mapping for: " + ", ".join(missing))
    finalized: list[dict[str, Any]] = []
    for raw in entries:
        entry = dict(raw)
        entry["target_id"] = mapping[str(entry["question_id"])]
        entry["assessment_id"] = f"extracted-{entry['question_id']}"
        entry.pop("question_id", None)
        entry.pop("issues", None)
        entry.pop("options", None)
        entry.pop("points", None)
        entry.pop("question_hash", None)
        finalized.append(entry)
    return {"purpose": "practice", "assessments": finalized}


def assessment_drafts_from_materials(questions: Iterable[Any], **kwargs: Any) -> dict[str, Any]:
    return build_draft(questions, **kwargs)
