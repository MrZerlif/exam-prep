"""Source-aware prioritization built on the deterministic scheduler."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .provenance import source_ref_from_mapping
from .scheduler import compute_priority
from .target_normalization import normalize_syllabus


def rank_source_aware_targets(
    syllabus: dict[str, Any],
    concepts: dict[str, Any],
    reviews: dict[str, Any],
    course: dict[str, Any],
    now: datetime,
    budget_minutes: int,
    *,
    available_source_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    targets = normalize_syllabus(syllabus).targets
    for target_id in targets:
        priority = compute_priority(
            target_id, syllabus, concepts, reviews, course, now, budget_minutes
        )
        metadata = targets.get(target_id, {})
        refs = metadata.get("source_refs", [])
        coverage_gap = not refs or (
            available_source_ids is not None
            and any(
                (
                    ref if isinstance(ref, str) else ref.get("source_id")
                    if isinstance(ref, dict)
                    else None
                )
                not in available_source_ids
                for ref in refs
            )
        )
        authority_rank = max(
            (
                source_ref_from_mapping(ref).authority_rank
                for ref in refs
                if isinstance(ref, dict)
            ),
            default=0,
        )
        item = {
            **priority,
            "target_id": target_id,
            "coverage_gap": coverage_gap,
            "source_authority_rank": authority_rank,
            "source_refs": refs,
        }
        # A missing source is an actionable P1 gap, so it receives a bounded
        # tie-break bonus without replacing exam value or mastery gap.
        item["source_aware_score"] = round(
            priority["score"] + (1.0 if coverage_gap else 0.0), 6
        )
        ranked.append(item)
    ranked.sort(
        key=lambda item: (item["source_aware_score"], item["target_id"]),
        reverse=True,
    )
    return ranked
