"""Deterministic validation and persistence for generated curriculum proposals."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .capabilities import CapabilityRegistry
from .provenance import SourceRef, normalize_source_refs
from .reducer import reduce_learning_state
from .scheduler import build_review_queue
from .source_provider import (
    build_runtime_source_catalog,
    build_verified_source_catalog,
    compute_source_coverage,
)
from .storage import StudyStore


@dataclass(frozen=True)
class CurriculumValidationReport:
    errors: list[str]
    warnings: list[str]
    coverage_gaps: list[str]

    @property
    def valid(self) -> bool:
        return not self.errors

    def to_mapping(self) -> dict[str, list[str]]:
        return {
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "coverage_gaps": list(self.coverage_gaps),
        }


class CurriculumValidationError(ValueError):
    def __init__(
        self,
        issues: list[str],
        *,
        warnings: list[str] | None = None,
        coverage_gaps: list[str] | None = None,
    ):
        self.issues = issues
        self.warnings = list(warnings or [])
        self.coverage_gaps = list(coverage_gaps or [])
        self.report = CurriculumValidationReport(
            list(issues), self.warnings, self.coverage_gaps
        )
        super().__init__("curriculum proposal is invalid: " + "; ".join(issues))


@dataclass(frozen=True)
class CurriculumApplyResult:
    changed: bool
    syllabus: dict[str, Any]
    proposal_id: str
    report: CurriculumValidationReport

    def to_mapping(self) -> dict[str, Any]:
        return {
            "changed": self.changed,
            "proposal_id": self.proposal_id,
            "syllabus": self.syllabus,
            "validation": self.report.to_mapping(),
        }


def _source_id(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        raw = value.get("source_id")
        return str(raw) if raw is not None else None
    return None


def _declared_source_map(
    proposal: Mapping[str, Any], source_refs: Iterable[Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Collect proposal references without treating them as verified sources."""

    declared: dict[str, dict[str, Any]] = {}

    def add(value: Any) -> None:
        try:
            normalized = normalize_source_refs([value])
        except (TypeError, ValueError):
            return
        for ref in normalized:
            declared.setdefault(str(ref["source_id"]), ref)

    for ref in source_refs:
        add(ref)
    for target in _target_list(proposal):
        refs = target.get("source_refs", [])
        if isinstance(refs, list):
            for ref in refs:
                add(ref)
    for question in _question_list(proposal):
        refs = question.get("source_refs", [])
        if isinstance(refs, list):
            for ref in refs:
                add(ref)
    return declared


def _effective_source_ref(
    value: Mapping[str, Any], verified_catalog: Mapping[str, SourceRef]
) -> dict[str, Any]:
    source_id = str(value["source_id"])
    trusted = verified_catalog.get(source_id)
    if trusted is not None:
        return trusted.to_mapping()
    # Preserve the reference for diagnostics and later resolution, but never
    # persist proposal-supplied authority as if it were verified metadata.
    unresolved = dict(value)
    unresolved["authority"] = "unknown"
    unresolved["provider_id"] = "unknown"
    return unresolved


def _read_runtime_json(store: StudyStore, name: str, default: dict[str, Any]) -> dict[str, Any]:
    path = store.state_path / name
    if not path.exists():
        return dict(default)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise CurriculumValidationError([f"existing {name} is not valid JSON"]) from exc
    return dict(value) if isinstance(value, Mapping) else dict(default)


def _default_course() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "course_id": "exam-prep-course",
        "title": "Exam preparation",
        "exam": {
            "date": None,
            "timezone": "UTC",
            "format": "mixed",
            "expected_total_points": 100,
            "revision": 1,
        },
        "time_budget": {"default_minutes": 25, "available_minutes_by_day": {}},
        "source_policy": {
            "priority_order": [
                "teacher_material",
                "official_exam_list",
                "lecture_notes",
                "problem_sets",
                "general_reference",
            ],
            "conflicts": "flag_for_user",
        },
        "scheduler": {
            "mode": "exam_cram",
            "max_review_interval_hours": 72,
            "review_warmup_limit": 3,
            "recurring_mistake_policy": {
                "min_count": 3,
                "min_sessions": 2,
                "resolve_after_clean_successes": 3,
            },
        },
    }


def _default_learner() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "preferences": {},
        "stable_patterns": [],
    }


def _default_session() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "session_id": "",
        "phase": "idle",
        "pending_action": "load a syllabus and start a session",
        "current_target_id": None,
        "current_task": None,
        "time_budget_minutes": 25,
    }


def _target_list(proposal: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = proposal.get("learning_targets", proposal.get("targets", []))
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def _raw_list(proposal: Mapping[str, Any], key: str) -> list[Any]:
    raw = proposal.get(key)
    return raw if isinstance(raw, list) else []


def _question_list(proposal: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = proposal.get("exam_questions", [])
    return [dict(item) for item in raw if isinstance(item, Mapping)] if isinstance(raw, list) else []


def _capability_descriptors(proposal: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = proposal.get("assessment_capabilities", proposal.get("capabilities", []))
    if isinstance(raw, Mapping):
        return [
            {"capability_id": key, **(dict(value) if isinstance(value, Mapping) else {})}
            for key, value in raw.items()
        ]
    return [dict(item) for item in raw if isinstance(item, Mapping)] if isinstance(raw, list) else []


def _find_cycles(targets: Mapping[str, Mapping[str, Any]]) -> list[str]:
    visiting: set[str] = set()
    visited: set[str] = set()
    cycles: list[str] = []

    def visit(target_id: str, trail: list[str]) -> None:
        if target_id in visiting:
            cycles.append(" -> ".join(trail + [target_id]))
            return
        if target_id in visited:
            return
        visiting.add(target_id)
        for prerequisite in targets[target_id].get("prerequisites", []):
            if prerequisite in targets:
                visit(prerequisite, trail + [target_id])
        visiting.remove(target_id)
        visited.add(target_id)

    for target_id in targets:
        visit(target_id, [])
    return cycles


def validate_curriculum_proposal(
    proposal: Mapping[str, Any],
    *,
    verified_source_catalog: (
        Iterable[SourceRef | Mapping[str, Any]] | Mapping[str, Any] | None
    ) = None,
) -> dict[str, Any]:
    """Validate the small proposal contract and return a normalized copy."""

    issues: list[str] = []
    warnings: list[str] = []
    coverage_gaps: list[str] = []
    if not isinstance(proposal, Mapping):
        raise CurriculumValidationError(["proposal must be an object"])
    if not isinstance(proposal.get("proposal_id"), str) or not proposal.get("proposal_id").strip():
        issues.append("proposal_id is required")
    if proposal.get("schema_version", 2) not in (1, 2):
        issues.append("schema_version must be 1 or 2")

    raw_targets = proposal.get("learning_targets", proposal.get("targets", []))
    if not isinstance(raw_targets, list):
        issues.append("learning_targets must be an array")
    elif any(not isinstance(item, Mapping) for item in raw_targets):
        issues.append("learning_targets must contain only objects")
    targets = _target_list(proposal)
    target_map: dict[str, dict[str, Any]] = {}
    for target in targets:
        target_id = target.get("target_id")
        if not target_id:
            issues.append("learning target is missing target_id")
            continue
        if not isinstance(target_id, str):
            issues.append("learning target target_id must be a string")
        target_id = str(target_id)
        if target_id in target_map:
            issues.append(f"duplicate learning target: {target_id}")
        target["target_id"] = target_id
        if not isinstance(target.get("prerequisites", []), list):
            issues.append(f"prerequisites for target {target_id!r} must be an array")
        if not isinstance(target.get("capability_ids", []), list):
            issues.append(f"capability_ids for target {target_id!r} must be an array")
        if not isinstance(target.get("exam_question_ids", []), list):
            issues.append(f"exam_question_ids for target {target_id!r} must be an array")
        if "title" not in target or not isinstance(target.get("title"), str) or not target["title"].strip():
            issues.append(f"title for target {target_id!r} must be a non-empty string")
        if not isinstance(target.get("source_refs", []), list):
            issues.append(f"source_refs for target {target_id!r} must be an array")
        target["prerequisites"] = [str(value) for value in target.get("prerequisites", [])] if isinstance(target.get("prerequisites", []), list) else []
        target["capability_ids"] = [str(value) for value in target.get("capability_ids", [])] if isinstance(target.get("capability_ids", []), list) else []
        target_map[target_id] = target

    for target_id, target in target_map.items():
        for prerequisite in target["prerequisites"]:
            if prerequisite not in target_map:
                issues.append(
                    f"unknown prerequisite {prerequisite!r} for target {target_id!r}"
                )
    for cycle in _find_cycles(target_map):
        issues.append(f"prerequisite cycle: {cycle}")

    source_values = proposal.get("source_refs", [])
    if not isinstance(source_values, list):
        issues.append("source_refs must be an array")
        source_values = []
    try:
        source_refs = normalize_source_refs(source_values)
    except (TypeError, ValueError) as exc:
        issues.append(f"source_refs are malformed: {exc}")
        source_refs = []
    verified_catalog = build_verified_source_catalog(verified_source_catalog)
    declared_sources = _declared_source_map(proposal, source_refs)
    for source_id, declared in declared_sources.items():
        trusted = verified_catalog.get(source_id)
        if trusted is None:
            coverage_gaps.append(
                f"unknown source ref {source_id!r} in curriculum proposal"
            )
        elif (
            declared.get("authority") not in (None, "unknown", trusted.authority)
        ):
            warnings.append(
                f"proposal authority for source {source_id!r} conflicts with verified catalog authority"
            )
    for target_id, target in target_map.items():
        refs = target.get("source_refs", [])
        if not refs:
            coverage_gaps.append(f"target {target_id!r} has no source refs")

    descriptors = _capability_descriptors(proposal)
    raw_descriptors = proposal.get("assessment_capabilities", proposal.get("capabilities", []))
    if isinstance(raw_descriptors, list) and any(
        not isinstance(item, Mapping) for item in raw_descriptors
    ):
        issues.append("assessment_capabilities must contain only objects")
    elif raw_descriptors is not None and not isinstance(raw_descriptors, (Mapping, list)):
        issues.append("assessment_capabilities must be an array or object")
    registry = CapabilityRegistry.from_syllabus(
        {"assessment_capabilities": descriptors}
    )
    raw_questions = proposal.get("exam_questions", [])
    if not isinstance(raw_questions, list):
        issues.append("exam_questions must be an array")
    elif any(not isinstance(item, Mapping) for item in raw_questions):
        issues.append("exam_questions must contain only objects")
    questions = _question_list(proposal)
    question_map: dict[str, dict[str, Any]] = {}
    for question in questions:
        question_id = question.get("question_id") or question.get("id")
        if not question_id:
            issues.append("exam question is missing question_id")
            continue
        question_id = str(question_id)
        question["question_id"] = question_id
        raw_target_ids = question.get("target_ids", question.get("target_id", []))
        if isinstance(raw_target_ids, list):
            question["target_ids"] = [str(value) for value in raw_target_ids]
        elif question.get("target_id"):
            question["target_ids"] = [str(question["target_id"])]
        else:
            issues.append(f"exam question {question_id!r} is missing target_ids")
            question["target_ids"] = []
        if question_id in question_map:
            issues.append(f"duplicate exam question: {question_id}")
        question_map[question_id] = question
        for target_id in question["target_ids"]:
            if target_id not in target_map:
                issues.append(
                    f"exam question {question_id!r} maps to unknown target {target_id!r}"
                )
        if not isinstance(question.get("capability_ids", []), list):
            issues.append(f"capability_ids for exam question {question_id!r} must be an array")
        if not isinstance(question.get("source_refs", []), list):
            issues.append(f"source_refs for exam question {question_id!r} must be an array")
        for capability_id in question.get("capability_ids", []) if isinstance(question.get("capability_ids", []), list) else []:
            if not registry.resolve(str(capability_id)).capability.is_registered:
                warnings.append(f"unknown capability {capability_id!r} in exam question {question_id!r}")

    for target_id, target in target_map.items():
        for question_id in target.get("exam_question_ids", []):
            if question_id not in question_map:
                issues.append(
                    f"exam question mapping for target {target_id!r} references unknown question {question_id!r}"
                )
            elif target_id not in question_map[question_id]["target_ids"]:
                issues.append(
                    f"exam question {question_id!r} does not map back to target {target_id!r}"
                )
        for capability_id in target["capability_ids"]:
            if not registry.resolve(capability_id).capability.is_registered:
                warnings.append(f"unknown capability {capability_id!r} for target {target_id!r}")

    removals = proposal.get("remove_target_ids", [])
    if not isinstance(removals, list) or any(not isinstance(item, str) for item in removals):
        issues.append("remove_target_ids must be an array of strings")

    if issues:
        raise CurriculumValidationError(
            sorted(set(issues)),
            warnings=sorted(set(warnings)),
            coverage_gaps=sorted(set(coverage_gaps)),
        )

    normalized = dict(proposal)
    normalized["schema_version"] = int(proposal.get("schema_version", 1))
    normalized["source_refs"] = source_refs
    normalized["learning_targets"] = targets
    normalized["assessment_capabilities"] = descriptors
    normalized["exam_questions"] = questions
    hash_input = {
        key: value
        for key, value in normalized.items()
        if key not in {"proposal_hash", "validation"}
    }
    calculated_hash = StudyStore.hash_document(hash_input)
    supplied_hash = proposal.get("proposal_hash")
    if supplied_hash is not None and supplied_hash != calculated_hash:
        raise CurriculumValidationError(["proposal_hash does not match normalized proposal"])
    normalized["proposal_hash"] = calculated_hash
    normalized["validation"] = CurriculumValidationReport(
        sorted(set(issues)), sorted(set(warnings)), sorted(set(coverage_gaps))
    ).to_mapping()
    return normalized


def build_syllabus_from_proposal(
    proposal: Mapping[str, Any],
    *,
    verified_source_catalog: (
        Iterable[SourceRef | Mapping[str, Any]] | Mapping[str, Any] | None
    ) = None,
) -> dict[str, Any]:
    verified_catalog = build_verified_source_catalog(verified_source_catalog)
    declared_sources = _declared_source_map(
        proposal, normalize_source_refs(proposal.get("source_refs", []))
    )
    source_by_id = {
        source_id: _effective_source_ref(ref, verified_catalog)
        for source_id, ref in declared_sources.items()
    }
    targets: list[dict[str, Any]] = []
    target_map: dict[str, dict[str, Any]] = {}
    for raw_target in _target_list(proposal):
        target = dict(raw_target)
        target_id = str(target["target_id"])
        target["source_refs"] = [
            source_by_id.get(str(_source_id(ref)), ref)
            for ref in target.get("source_refs", [])
        ]
        targets.append(target)
        target_map[target_id] = dict(target)
    capabilities = {
        str(item["capability_id"]): {
            key: value for key, value in item.items() if key != "capability_id"
        }
        for item in _capability_descriptors(proposal)
        if item.get("capability_id")
    }
    syllabus = {
        "schema_version": 2,
        "proposal_id": proposal.get("proposal_id"),
        "proposal_hash": proposal.get("proposal_hash"),
        "source_refs": list(source_by_id.values()),
        "learning_targets": targets,
        "target_aliases": {target_id: target_id for target_id in target_map},
        "assessment_capabilities": capabilities,
        "exam_questions": _question_list(proposal),
    }
    syllabus["source_coverage"] = compute_source_coverage(
        syllabus, available_source_ids=set(verified_catalog)
    )
    return syllabus


def _merge_proposals(
    current: Mapping[str, Any] | None, proposal: Mapping[str, Any]
) -> dict[str, Any]:
    current = current or {}
    current_targets: dict[str, dict[str, Any]] = {}
    for target in _target_list(current):
        current_targets[str(target["target_id"])] = dict(target)
    for key, value in (
        current.get("targets", {}).items()
        if isinstance(current.get("targets", {}), Mapping)
        else []
    ):
        if isinstance(value, Mapping) and str(key) not in current_targets:
            current_targets[str(key)] = dict(value)
    for target_id in proposal.get("remove_target_ids", []):
        current_targets.pop(str(target_id), None)
    for target in _target_list(proposal):
        current_targets[str(target["target_id"])] = dict(target)

    sources: dict[str, Any] = {}
    for ref in normalize_source_refs(current.get("source_refs", [])):
        sources[str(ref["source_id"])] = ref
    for target in current_targets.values():
        for ref in normalize_source_refs(target.get("source_refs", [])):
            sources[str(ref["source_id"])] = ref
    for ref in normalize_source_refs(proposal.get("source_refs", [])):
        sources[str(ref["source_id"])] = ref

    questions: dict[str, dict[str, Any]] = {}
    for question in _question_list(current) + _question_list(proposal):
        if question.get("question_id") or question.get("id"):
            question_id = str(question.get("question_id") or question.get("id"))
            question = dict(question)
            question["question_id"] = question_id
            questions[question_id] = question

    descriptors: dict[str, dict[str, Any]] = {}
    for item in _capability_descriptors(current) + _capability_descriptors(proposal):
        if item.get("capability_id"):
            descriptors[str(item["capability_id"])] = dict(item)
    return {
        "schema_version": 2,
        "proposal_id": proposal.get("proposal_id") or current.get("proposal_id"),
        "source_refs": list(sources.values()),
        "learning_targets": list(current_targets.values()),
        "assessment_capabilities": list(descriptors.values()),
        "exam_questions": list(questions.values()),
    }


def apply_curriculum_proposal(
    store: StudyStore, proposal: Mapping[str, Any]
) -> CurriculumApplyResult:
    store.initialize()
    current: dict[str, Any] | None = None
    syllabus_path = store.state_path / "syllabus.json"
    if syllabus_path.exists():
        try:
            loaded = json.loads(syllabus_path.read_text(encoding="utf-8"))
            current = loaded if isinstance(loaded, dict) else None
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise CurriculumValidationError(["existing syllabus is not valid JSON"]) from exc
    merged = _merge_proposals(current, proposal)
    verified_catalog = build_runtime_source_catalog(store)
    validated = validate_curriculum_proposal(
        merged, verified_source_catalog=verified_catalog
    )
    syllabus = build_syllabus_from_proposal(
        validated, verified_source_catalog=verified_catalog
    )
    changed = current is None or StudyStore.hash_document(current) != StudyStore.hash_document(syllabus)
    if changed:
        store._write_json(syllabus_path, syllabus)
        course = _read_runtime_json(store, "course.json", _default_course())
        learner = _read_runtime_json(store, "learner.json", _default_learner())
        session = _read_runtime_json(store, "session.json", _default_session())
        if not (store.state_path / "course.json").exists():
            store._write_json(store.state_path / "course.json", course)
        revision = store.next_revision()
        events = store.read_complete_observations()
        derived = reduce_learning_state(
            course, syllabus, events, {"revision": revision}
        )
        reviews = build_review_queue(
            events,
            derived.get("targets", derived.get("concepts", {})),
            course,
            datetime.now(timezone.utc),
            syllabus,
        )
        reviews["derived_from_revision"] = revision
        store.commit_revision(
            derived, session, learner, reviews, course, syllabus
        )
    report_data = validated.get("validation", {})
    report = CurriculumValidationReport(
        list(report_data.get("errors", [])),
        list(report_data.get("warnings", [])),
        list(report_data.get("coverage_gaps", [])),
    )
    return CurriculumApplyResult(changed, syllabus, str(validated["proposal_id"]), report)

