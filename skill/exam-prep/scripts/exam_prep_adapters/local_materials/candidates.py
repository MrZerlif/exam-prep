"""Deterministic scoring and bucketing of structurally labelled segments."""

from __future__ import annotations

from dataclasses import dataclass
import re
from statistics import pvariance
from typing import Any, Mapping, Sequence

from exam_prep_lib.defaults import (
    EXTRACTION_SCORE_ACCEPT,
    EXTRACTION_SCORE_REVIEW,
    EXTRACTION_SCORE_WEIGHTS,
)
from exam_prep_lib.lexicon import Lexicon
from exam_prep_lib.semantics import best_slot

from .labels import Segment, option_run_quality
from .points import extract as extract_points


@dataclass(frozen=True)
class Candidate:
    segment: Segment
    score: float
    bucket: str
    signals: dict[str, float]


_POINTS_SHAPE_RE = re.compile(r"\(\s*\d+\s+[^)]*\)", re.UNICODE)


_SECTION_CONTEXT_LOOKBACK = 10


def _section_context(index: int, segments: Sequence[Segment], lexicon: Lexicon) -> bool:
    """Whether the nearest heading above `index` falls into kind.homework/exam.

    Walks backward and stops at the first segment whose body hits *any*
    kind.* slot - not just homework/exam - so an older heading such as
    "kind.lecture" is not silently overridden by a homework word appearing
    further down in ordinary prose. The walk is bounded so a heading near
    the top of a long document cannot promote everything below it.
    """

    start = max(0, index - _SECTION_CONTEXT_LOOKBACK)
    for item in reversed(segments[start:index]):
        found = best_slot("kind.", item.body, lexicon)
        if found is None:
            continue
        return found.slot in {"kind.homework", "kind.exam"}
    return False


def _source_kind(source: Any) -> str:
    if isinstance(source, Mapping):
        return str(source.get("kind", ""))
    return str(getattr(source, "kind", ""))


def _solution_labels(source: Any, solutions_by_file: Mapping[str, Any] | None) -> set[str]:
    values: Any = solutions_by_file
    if values is None:
        values = getattr(source, "solutions_by_file", None)
    if isinstance(values, Mapping):
        values = values.get(getattr(source, "relative_path", ""), values)
    if isinstance(values, Mapping):
        return {str(key).casefold() for key in values}
    if isinstance(values, (set, frozenset, list, tuple)):
        return {str(key).casefold() for key in values}
    return set()


def _has_points(body: str, lexicon: Lexicon) -> bool:
    return any(best_slot("unit.points", match.group(0), lexicon) is not None for match in _POINTS_SHAPE_RE.finditer(body))


def _has_options(body: str) -> float:
    return option_run_quality(body)


def _global_hierarchy(segments: Sequence[Segment]) -> bool:
    labels = [segment.label for segment in segments if segment.label is not None]
    if len(labels) < 3:
        return False
    nested = sum(len(label.parts) > 1 for label in labels)
    monotonic = all(left.parts <= right.parts for left, right in zip(labels, labels[1:]))
    return nested / len(labels) >= 0.6 and monotonic


def _dense_run(index: int, labels: Sequence[Segment]) -> bool:
    current = labels[index].label
    if current is None or not current.parts:
        return False
    for neighbor in (index - 1, index + 1):
        if not 0 <= neighbor < len(labels):
            continue
        other = labels[neighbor].label
        if other is not None and other.kind == current.kind and other.parts[:-1] == current.parts[:-1] and abs(other.parts[-1] - current.parts[-1]) == 1:
            return True
    return False


def _sibling_uniformity(index: int, segments: Sequence[Segment]) -> bool:
    lengths = [len(segments[pos].body) for pos in (index - 1, index, index + 1) if 0 <= pos < len(segments) and segments[pos].label is not None]
    return len(lengths) >= 2 and pvariance(lengths) <= max(400.0, (sum(lengths) / len(lengths)) ** 2)


def _heading_shape(index: int, segments: Sequence[Segment]) -> bool:
    current = segments[index]
    if current.label is not None and len(current.label.parts) > 1 and len(current.body) < 80:
        return True
    if len(current.body) >= 80 or index + 1 >= len(segments):
        return False
    return len(segments[index + 1].body) >= max(160, len(current.body) * 3)


def question_candidate_score(
    segment: Segment,
    *,
    source: Any,
    lexicon: Lexicon,
    weights: Mapping[str, float] | None = None,
    segments: Sequence[Segment] = (),
    index: int = 0,
    solutions_by_file: Mapping[str, Any] | None = None,
    global_hierarchy: bool | None = None,
    points_token: str | None = None,
    points_weight: float = 1.0,
) -> Candidate:
    active_weights = {**EXTRACTION_SCORE_WEIGHTS, **dict(weights or {})}
    all_segments = tuple(segments) or (segment,)
    labeled = [item for item in all_segments if item.label is not None]
    label = segment.label
    raw_signals = {
        "solution_pair": bool(label and str(label.raw).casefold() in _solution_labels(source, solutions_by_file)),
        "has_points": (1.0 if _has_points(segment.body, lexicon) or extract_points(segment.body, token=points_token, lexicon=lexicon) is not None else 0.0) * points_weight,
        "has_options": _has_options(segment.body),
        "source_kind": _source_kind(source) in {"exam", "homework"},
        "flat_label": bool(label and len(label.parts) == 1),
        "sibling_uniformity": _sibling_uniformity(index, all_segments),
        "lexicon_hit": best_slot("verb.", segment.body, lexicon) is not None or best_slot("kind.", segment.body, lexicon) is not None,
        "dense_run": _dense_run(index, all_segments),
        "section_context": _section_context(index, all_segments, lexicon),
        "heading_shape": _heading_shape(index, all_segments),
        "global_hierarchy": _global_hierarchy(all_segments) if global_hierarchy is None else global_hierarchy,
    }
    signals = {
        key: float(active_weights[key]) * (float(value) if isinstance(value, (int, float)) else (1.0 if value else 0.0))
        for key, value in raw_signals.items()
    }
    total = round(sum(signals.values()), 4)
    if total >= EXTRACTION_SCORE_ACCEPT:
        bucket = "accept"
    elif total >= EXTRACTION_SCORE_REVIEW:
        bucket = "review"
    else:
        bucket = "reject"
    return Candidate(segment, total, bucket, signals)


def score(
    segments: Sequence[Segment],
    *,
    source: Any,
    lexicon: Lexicon,
    weights: Mapping[str, float] | None = None,
    solutions_by_file: Mapping[str, Any] | None = None,
    points_token: str | None = None,
    points_weight: float = 1.0,
) -> tuple[Candidate, ...]:
    materialized = tuple(segments)
    labeled = tuple(item for item in materialized if item.label is not None)
    hierarchy = _global_hierarchy(materialized)
    result: list[Candidate] = []
    for index, item in enumerate(materialized):
        if item.label is None or item.label.kind == "letter":
            continue
        result.append(
            question_candidate_score(
                item,
                source=source,
                lexicon=lexicon,
                weights=weights,
                segments=materialized,
                index=index,
                solutions_by_file=solutions_by_file,
                global_hierarchy=hierarchy,
                points_token=points_token,
                points_weight=points_weight,
            )
        )
    return tuple(result)
