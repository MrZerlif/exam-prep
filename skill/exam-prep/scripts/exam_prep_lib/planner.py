"""Small deterministic UX projections over the existing state and scheduler."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping

from .provenance import provenance_label
from .scheduler import compute_priority, select_next_activity
from .target_normalization import normalize_syllabus


def build_cheatsheet(
    syllabus: Mapping[str, Any],
    concepts: Mapping[str, Any],
    reviews: Mapping[str, Any],
    source_evidence: Iterable[Mapping[str, Any]],
    *,
    target_ids: Iterable[str] | None = None,
) -> str:
    normalized = normalize_syllabus(dict(syllabus))
    wanted = set(target_ids or normalized.targets)
    lines = ["# Exam prep cheatsheet", "", "## High exam-value targets", ""]
    targets = sorted(
        ((target_id, metadata) for target_id, metadata in normalized.targets.items() if target_id in wanted),
        key=lambda item: (-float(item[1].get("importance", 0)) * float(item[1].get("frequency", 0)), item[0]),
    )
    for target_id, metadata in targets:
        state = concepts.get(target_id, {})
        lines.append(f"- {target_id}: {metadata.get('title', target_id)} (mastery={state.get('mastery_status', 'unseen')})")
    lines.extend(["", "## Source excerpts", ""])
    for item in source_evidence:
        ref = item.get("source_ref", item)
        excerpt = item.get("excerpt") or ref.get("excerpt")
        if not excerpt or ref.get("source_id") not in wanted and target_ids:
            continue
        locator = ref.get("locator") or ref.get("source_id")
        lines.append(f"- {provenance_label(source_refs=[ref])} {locator}: {str(excerpt).strip()}")
    lines.extend(["", "## Weak targets", ""])
    for target_id, state in concepts.items():
        if state.get("mastery_status") in {"weak", "learning", "unstable"}:
            lines.append(f"- {target_id}")
    lines.extend(["", "## Last repetition", "", "- Derived from the current review queue."])
    return "\n".join(lines).rstrip() + "\n"


def last_minute_review(
    syllabus: Mapping[str, Any],
    concepts: Mapping[str, Any],
    reviews: Mapping[str, Any],
    course: Mapping[str, Any],
    now: datetime,
    minutes: int,
) -> list[dict[str, Any]]:
    items = []
    for target_id in normalize_syllabus(dict(syllabus)).targets:
        priority = compute_priority(target_id, dict(syllabus), dict(concepts), dict(reviews), dict(course), now, minutes)
        items.append({"target_id": target_id, **priority})
    return sorted(items, key=lambda item: (-item["score"], item["target_id"]))


def forecast_plan(
    syllabus: Mapping[str, Any],
    concepts: Mapping[str, Any],
    reviews: Mapping[str, Any],
    course: Mapping[str, Any],
    now: datetime,
    *,
    days: int = 1,
    minutes_per_day: int = 120,
) -> dict[str, Any]:
    if days < 1 or minutes_per_day < 1:
        raise ValueError("days and minutes_per_day must be positive")
    normalized = normalize_syllabus(dict(syllabus))
    result: list[dict[str, Any]] = []
    recent: list[str] = []
    for offset in range(days):
        remaining = int(minutes_per_day)
        activities: list[dict[str, Any]] = []
        while remaining > 0 and normalized.targets:
            selected = select_next_activity(dict(syllabus), dict(concepts), dict(reviews), dict(course), now + timedelta(days=offset), remaining, recent)
            target_id = selected.get("concept_id", selected.get("target_id"))
            estimated = max(1, int(normalized.targets.get(target_id, {}).get("estimated_learning_minutes", min(25, remaining))))
            allocated = min(estimated, remaining)
            activities.append({"target_id": target_id, "activity_type": selected.get("activity_type"), "minutes": allocated, "priority": selected.get("score"), "reason": selected.get("reason")})
            remaining -= allocated
            recent = [target_id]
            if allocated <= 0:
                break
            if len(activities) >= len(normalized.targets):
                break
        result.append({"day": offset + 1, "minutes": minutes_per_day - remaining, "activities": activities})
    return {"days": result, "minutes_per_day": minutes_per_day, "horizon_days": days}
