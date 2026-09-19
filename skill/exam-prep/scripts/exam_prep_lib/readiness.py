"""Readiness verdicts layered on the existing validation diagnostics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .storage import StudyStore


def _read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except (OSError, ValueError, json.JSONDecodeError):
        return default


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
    try:
        recovered = store.try_recover()
        reviews = recovered.review_queue if recovered else None
        if isinstance(reviews, dict) and any(item.get("review_status") in {"due", "overdue"} for item in reviews.get("items", {}).values()):
            reasons.append("overdue reviews remain")
    except Exception:
        pass
    if blocking or not validation.get("valid"):
        verdict = "blocked"
    elif reasons:
        verdict = "usable_with_gaps"
    else:
        verdict = "ready"
    return {
        "verdict": verdict,
        "reasons": reasons,
        "coverage_gap": not bool(evidence),
        "source_evidence_count": len(evidence),
        "mock_pool_count": len(mock),
        "required_mock_count": required,
        "notebooklm": {"available": False, "optional": True},
    }
