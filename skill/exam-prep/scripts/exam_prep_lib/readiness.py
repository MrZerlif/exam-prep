"""Readiness verdicts layered on the existing validation diagnostics."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .reducer import effective_learning_events, event_assistance_band, reduce_learning_state
from .capabilities import CapabilityRegistry
from .evidence_maturity import non_superseded_events
from .storage import StudyStore
from .target_normalization import normalize_syllabus


def _read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except (OSError, ValueError, json.JSONDecodeError):
        return default


def _parse_aware(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None


def blueprint_hash(exam: dict[str, Any]) -> str:
    # Keep this byte-for-byte aligned with the canonical event writer.
    return StudyStore.hash_document(exam)


def mock_blueprint_coverage(
    exam: dict[str, Any], questions: list[dict[str, Any]], syllabus: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Check the delivered set, rather than just whether its items were answered."""
    required = exam.get("question_count")
    delivered = len(questions)
    complete = required is None or delivered == required
    registry = CapabilityRegistry.from_syllabus(syllabus or {})
    counts = {"theory": 0, "problem": 0}
    for question in questions:
        capability = registry.resolve(question.get("capability_id") or "").capability
        if not capability.is_registered:
            continue
        dimensions = set(capability.affected_dimensions)
        if dimensions & {"procedural", "transfer"}:
            counts["problem"] += 1
        elif dimensions & {"conceptual", "recall"}:
            counts["theory"] += 1
    required_slots = {"theory": 0, "problem": 0}
    for slot in exam.get("ticket_slots") or []:
        required_slots[slot["kind"]] += slot["count"]
    complete = complete and all(counts[kind] >= count for kind, count in required_slots.items())
    return {
        "complete": bool(complete),
        "required_questions": required,
        "delivered_questions": delivered,
        "required_slots": required_slots,
        "delivered_slots": counts,
    }


def rederive_mock_attempts(
    attempts: list[dict[str, Any]],
    events: list[dict[str, Any]],
    course: dict[str, Any] | None = None,
    syllabus: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Rebuild frozen mock validity/scores from active canonical events."""
    course, syllabus = course or {}, syllabus or {}
    active = effective_learning_events(events, course, syllabus)
    rebuilt: list[dict[str, Any]] = []
    for snapshot in attempts:
        if not isinstance(snapshot, dict):
            continue
        item = dict(snapshot)
        ids = list(item.get("assessment_ids", []))
        questions = []
        for assessment_id in ids:
            matching = [
                event for event in active
                if event.get("session_id") == item.get("session_id")
                and event.get("assessment_id") == assessment_id
            ]
            event = matching[-1] if len(matching) == 1 else None
            questions.append({
                "assessment_id": assessment_id,
                "target_id": event.get("target_id") if event else None,
                "capability_id": event.get("capability_id") if event else None,
                "outcome": event.get("outcome") if event else None,
                "assistance_band": event_assistance_band(event) if event else None,
                "assessment_integrity": event.get("assessment_integrity") if event else None,
                "assessment_spec_hash": event.get("assessment_spec_hash") if event else None,
                "assessment_question_hash": event.get("assessment_question_hash") if event else None,
                "assessment_result": event.get("assessment_result") if event else None,
                "exam_revision": event.get("exam_revision") if event else None,
                "exam_hash": event.get("exam_hash") if event else None,
                "attempt_count": len(matching),
            })
        started, ended = _parse_aware(item.get("started_at")), _parse_aware(item.get("ended_at"))
        elapsed = (ended - started).total_seconds() if started and ended else None
        limit = item.get("time_limit_minutes")
        timed = (
            isinstance(limit, (int, float)) and not isinstance(limit, bool) and limit > 0
            and elapsed is not None and 0 <= elapsed <= limit * 60
        )
        all_attempted = bool(ids) and all(question["attempt_count"] == 1 for question in questions)
        independent_frozen = all(
            question["outcome"] in {"correct", "partial", "incorrect"}
            and question["assistance_band"] == "independent"
            and question["assessment_integrity"] == "frozen_attempt"
            for question in questions
        )
        blueprint_matches = all(
            question["exam_revision"] == item.get("blueprint_revision")
            and question["exam_hash"] == item.get("blueprint_hash")
            for question in questions
        )
        point_pairs = []
        for question in questions:
            result = question.get("assessment_result")
            score = result.get("score") if isinstance(result, dict) else None
            maximum = result.get("max_score") if isinstance(result, dict) else None
            if (
                isinstance(score, (int, float)) and not isinstance(score, bool)
                and isinstance(maximum, (int, float)) and not isinstance(maximum, bool)
                and maximum > 0 and 0 <= score <= maximum
            ):
                point_pairs.append((float(score), float(maximum)))
        scoring_complete = len(point_pairs) == len(ids)
        item["questions"] = questions
        item["assessment_hashes"] = [
            question["assessment_question_hash"] for question in questions
            if question.get("assessment_question_hash")
        ]
        item["elapsed_seconds"] = elapsed
        item["score_fraction"] = (
            round(sum(score for score, _maximum in point_pairs) / sum(maximum for _score, maximum in point_pairs), 4)
            if scoring_complete and point_pairs else None
        )
        item["all_attempted"] = all_attempted
        item["scoring_complete"] = scoring_complete
        item["blueprint_coverage"] = mock_blueprint_coverage(course.get("exam") or {}, questions, syllabus)
        item["valid"] = bool(
            item.get("disposition") == "submitted"
            and all_attempted
            and independent_frozen
            and blueprint_matches
            and timed
            and scoring_complete
            and item["blueprint_coverage"]["complete"]
        )
        rebuilt.append(item)
    return rebuilt


def build_learner_exam_readiness(
    course: dict[str, Any],
    syllabus: dict[str, Any],
    derived: dict[str, Any],
    mock_attempts: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Judge learner evidence independently of workspace/material readiness."""
    exam = course.get("exam") if isinstance(course.get("exam"), dict) else {}
    readiness_policy = course.get("readiness_policy") if isinstance(course.get("readiness_policy"), dict) else {}
    target_score = readiness_policy.get("target_score_fraction")
    if isinstance(target_score, bool) or not isinstance(target_score, (int, float)) or not 0 < target_score <= 1:
        return {"status": "unknown", "reason": "learner score target is not configured", "target_score_fraction": None}
    time_limit = exam.get("time_limit_minutes")
    if isinstance(time_limit, bool) or not isinstance(time_limit, (int, float)) or time_limit <= 0:
        return {"status": "unknown", "reason": "exam time limit is not configured", "target_score_fraction": float(target_score)}

    current_hash = blueprint_hash(exam)
    current_attempts = [
        item for item in rederive_mock_attempts(mock_attempts, events, course, syllabus)
        if item.get("blueprint_hash") == current_hash
        and item.get("blueprint_revision") == exam.get("revision")
    ]
    matching = current_attempts
    matching.sort(key=lambda item: item.get("ended_at") or "")
    if len(matching) < 2:
        return {
            "status": "unknown",
            "reason": "two full, timed, current-blueprint mock attempts are not available",
            "target_score_fraction": float(target_score),
            "valid_mock_count": len(matching),
        }
    latest = matching[-2:]
    if any(item.get("valid") is not True for item in latest):
        incomplete = any(item.get("all_attempted") is not True for item in latest)
        missing_scores = any(item.get("scoring_complete") is not True for item in latest)
        return {
            "status": "not_ready" if incomplete else ("unknown" if missing_scores else "not_ready"),
            "reason": (
                "one of the two latest current-blueprint mock attempts is incomplete"
                if incomplete else "one of the two latest mock attempts is missing per-question scores"
                if missing_scores else "one of the two latest current-blueprint mock attempts is invalid"
            ),
            "target_score_fraction": float(target_score),
        }
    if latest[0].get("session_id") == latest[1].get("session_id"):
        return {"status": "unknown", "reason": "mock attempts must be from different sessions", "valid_mock_count": len(matching)}
    sets = [set(item.get("assessment_ids", [])) for item in latest]
    content_sets = [set(item.get("assessment_hashes", [])) for item in latest]
    if sets[0] == sets[1] or not (content_sets[0] - content_sets[1] or content_sets[1] - content_sets[0]):
        return {"status": "unknown", "reason": "two latest mock attempts do not contain distinct assessment material", "valid_mock_count": len(matching)}
    if any(float(item.get("score_fraction", -1)) < float(target_score) for item in latest):
        return {
            "status": "not_ready",
            "reason": "one of the two latest valid mock scores is below the configured target",
            "target_score_fraction": float(target_score),
            "mock_scores": [item.get("score_fraction") for item in latest],
        }

    concepts = derived.get("targets", derived.get("concepts", {}))
    metadata = normalize_syllabus(syllabus).targets
    if not metadata:
        return {"status": "unknown", "reason": "mandatory exam targets are not configured", "target_score_fraction": float(target_score)}
    required = {
        target_id for target_id, target in metadata.items()
        if target.get("exam_required", target.get("active", True)) is not False
    }
    if not required:
        return {"status": "unknown", "reason": "no active mandatory exam targets are configured", "target_score_fraction": float(target_score)}
    missing = [
        target_id for target_id in sorted(required)
        if not concepts.get(target_id, {}).get("progress", {}).get("exam_ready")
        or not concepts.get(target_id, {}).get("progress", {}).get("confirmed_after_break")
    ]
    if missing:
        return {
            "status": "not_ready",
            "reason": "mandatory targets need exam-ready evidence and a current delayed confirmation",
            "missing_targets": missing,
            "target_score_fraction": float(target_score),
            "mock_scores": [item.get("score_fraction") for item in latest],
        }

    # A material gap found by the latest mock needs a newer independent
    # targeted success. The delayed-confirmation target gate above also forces
    # the affected topic to rebuild its current retention series.
    unresolved = []
    active_events = effective_learning_events(events, course, syllabus)
    registry = CapabilityRegistry.from_syllabus(syllabus)
    for attempt in latest:
        attempt_end = _parse_aware(attempt.get("ended_at"))
        for question in attempt.get("questions", []):
            if question.get("outcome") not in {"incorrect", "partial"} or not question.get("target_id"):
                continue
            repaired = any(
                event.get("target_id") == question["target_id"]
                and event.get("capability_id") == question.get("capability_id")
                and registry.resolve(event.get("capability_id") or "").capability.is_registered
                and event.get("outcome") == "correct"
                and event_assistance_band(event) == "independent"
                and event.get("assessment_integrity") in {None, "not_assessment", "frozen_attempt"}
                and not event.get("solution_exposed")
                and not (event.get("assistance") or {}).get("full_solution_viewed")
                and attempt_end is not None
                and (_parse_aware(event.get("recorded_at")) is not None)
                and (_parse_aware(event.get("recorded_at")) > attempt_end)
                for event in active_events
            )
            if not repaired:
                unresolved.append(question["target_id"])
    if unresolved:
        return {
            "status": "not_ready",
            "reason": "significant mock gaps need independent targeted repair",
            "unresolved_targets": sorted(set(unresolved)),
            "target_score_fraction": float(target_score),
            "mock_scores": [item.get("score_fraction") for item in latest],
        }
    return {
        "status": "ready",
        "reason": "all mandatory targets and the two latest mock attempts meet current criteria",
        "target_score_fraction": float(target_score),
        "mock_scores": [item.get("score_fraction") for item in latest],
        "mock_session_ids": [item.get("session_id") for item in latest],
    }


def build_readiness(store: StudyStore, validation: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if not validation.get("valid"):
        reasons.append("workspace validation has blocking errors")
    course = _read(store.state_path / "course.json", {})
    syllabus = _read(store.state_path / "syllabus.json", {})
    if not isinstance(course, dict) or not isinstance(syllabus, dict):
        return {"verdict": "blocked", "reasons": reasons or ["canonical workspace is unreadable"], "coverage_gap": True}
    issues = _read(store.state_path / "ingest_issues.json", [])
    if isinstance(issues, dict):
        issues = issues.get("issues", [])
    blocking = [issue for issue in issues if isinstance(issue, dict) and issue.get("severity") == "blocking"]
    gaps = [issue for issue in issues if isinstance(issue, dict) and issue.get("severity") == "gap"]
    if blocking:
        reasons.append(f"{len(blocking)} blocking ingest issue(s)")
    targets = syllabus.get("learning_targets", [])
    evidence = store.read_source_evidence()
    if not evidence:
        reasons.append("coverage_gap: no hydrated source evidence")
    if not targets:
        reasons.append("no learning targets are loaded")
    assessments = store.read_assessments()
    mock = [item for item in assessments if item.get("purpose") == "mock"]
    required = int((course.get("exam") or {}).get("question_count") or 0)
    if not mock or len(mock) < required:
        reasons.append("mock pool is empty or smaller than the exam blueprint")
    if any(item.get("origin") == "model_generated" for item in mock):
        reasons.append("mock pool contains model-generated questions")
    if gaps:
        reasons.append(f"{len(gaps)} ingest gap(s) require attention")
    recovered = None
    try:
        recovered = store.try_recover()
        reviews = recovered.review_queue if recovered else None
        if isinstance(reviews, dict) and any(item.get("review_status") in {"due", "overdue"} for item in reviews.get("items", {}).values()):
            reasons.append("overdue reviews remain")
    except Exception as exc:
        reason = f"recovery check failed ({type(exc).__name__})"
        detail = str(exc).strip()
        if detail:
            reason += f": {detail}"
        reasons.append(reason)
    if blocking or not validation.get("valid"):
        verdict = "blocked"
    elif reasons:
        verdict = "usable_with_gaps"
    else:
        verdict = "ready"
    learner_readiness = {"status": "unknown", "reason": "workspace validation has blocking errors"}
    if validation.get("valid"):
        events = getattr(store, "read_learning_observations", lambda: [])()
        learner_readiness = build_learner_exam_readiness(
            course,
            syllabus,
            reduce_learning_state(course, syllabus, events, {}),
            [item.get("learner_mock_attempt") for item in getattr(store, "read_session_summaries", lambda: [])() if isinstance(item, dict) and item.get("learner_mock_attempt")],
            events,
        )
    return {
        "verdict": verdict,
        "reasons": reasons,
        "coverage_gap": not bool(evidence),
        "source_evidence_count": len(evidence),
        "mock_pool_count": len(mock),
        "required_mock_count": required,
        "learner_exam_readiness": learner_readiness,
        "notebooklm": {"available": False, "optional": True},
    }
