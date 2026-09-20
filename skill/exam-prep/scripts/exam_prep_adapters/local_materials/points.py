"""Document-local point-unit inference and validation."""

from __future__ import annotations

import re
from typing import Iterable, Any

from exam_prep_lib.lexicon import Lexicon
from exam_prep_lib.semantics import best_slot, match

from .labels import segment


_POINT_SHAPE_RE = re.compile(r"\(\s*(?P<value>\d+)\s+(?P<token>[^()\d]+?)\s*\)", re.UNICODE)
_NON_POINT_UNITS = frozenset(
    {"m", "cm", "mm", "km", "kg", "g", "s", "sec", "second", "seconds", "min", "minute", "minutes", "h", "hour", "hours"}
)


def _page_text(page: Any) -> str:
    return str(getattr(page, "text", page))


def _candidate_bodies(pages: Iterable[Any]) -> tuple[str, ...]:
    return tuple(
        segment_body.body
        for page in pages
        for segment_body in segment(_page_text(page))
        if segment_body.label is not None
    )


def _occurrences(body: str) -> list[tuple[str, int, str]]:
    return [
        (item.group("token").strip(), int(item.group("value")), item.group(0))
        for item in _POINT_SHAPE_RE.finditer(body)
    ]


def _lexicon_token(body: str, lexicon: Lexicon) -> str | None:
    found = best_slot("unit.points", body, lexicon)
    return found.token if found is not None else None


def infer_token(pages: Iterable[Any], *, lexicon: Lexicon) -> str | None:
    bodies = _candidate_bodies(pages)
    total_candidates = len(bodies)
    if not total_candidates:
        return None
    for body in bodies:
        known = best_slot("unit.points", body, lexicon)
        if known is not None:
            return known.token
    observed: dict[str, list[tuple[int, str]]] = {}
    for body in bodies:
        first_two = [line for line in body.splitlines() if line.strip()][:2]
        for line in first_two:
            for token, value, raw in _occurrences(line):
                key = token.casefold()
                if key in _NON_POINT_UNITS:
                    continue
                observed.setdefault(key, []).append((value, raw))
    eligible = [
        (key, values)
        for key, values in observed.items()
        if len(values) >= 3
        and len(values) * 2 >= total_candidates
        and len({raw for _value, raw in values}) == 1
    ]
    if not eligible:
        return None
    eligible.sort(key=lambda item: (-len(item[1]), item[0]))
    return eligible[0][1][0][1].split(maxsplit=1)[1].rstrip(")").strip()


def extract(body: str, *, token: str | None, lexicon: Lexicon) -> int | None:
    if token is None:
        token = _lexicon_token(body, lexicon)
    if token is None:
        return None
    for raw_token, value, raw in _occurrences(body):
        if raw_token.casefold() != str(token).casefold() and match("unit.points", raw, lexicon) is None:
            continue
        return value
    return None


def verify_total(values: Iterable[int | None], expected_total: float | int | None) -> bool | None:
    if expected_total is None:
        return None
    normalized = [int(value) for value in values if value is not None]
    return bool(normalized) and sum(normalized) == float(expected_total)
