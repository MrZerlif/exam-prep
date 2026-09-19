"""Deterministic chapter hints for local material pages."""

# Portions adapted from ZeKaiNie/universal-examprep-skill (MIT), see vendor/exam-cram-coach/LICENSE

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Any


_HEADING_RE = re.compile(
    r"(?:глава|тема|лекция|раздел|занятие|chapter|topic|lecture|section)\s*\.?\s*([0-9]{1,3}|[IVXLCDM]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Chapter:
    number: int
    title: str
    source_ids: tuple[str, ...] = ()
    pages: tuple[int, ...] = ()


def _roman(value: str) -> int | None:
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    previous = 0
    for char in reversed(value.upper()):
        current = values.get(char)
        if current is None:
            return None
        if current < previous:
            total -= current
        else:
            total += current
            previous = current
    return total or None


def number_from_name(value: str) -> int | None:
    match = _HEADING_RE.search(value)
    if not match:
        return None
    token = match.group(1)
    return int(token) if token.isdigit() else _roman(token)


def guess_title(value: str) -> str:
    first = next((line.strip() for line in value.splitlines() if line.strip()), "")
    return first.lstrip("# ")[:200] or "Untitled"


def build_chapters(items: Iterable[Any]) -> tuple[Chapter, ...]:
    grouped: dict[int, dict[str, Any]] = {}
    for item in items:
        if isinstance(item, tuple) and len(item) == 2:
            source_id, page = item
            text = getattr(page, "text", str(page))
            number = number_from_name(text) or number_from_name(str(source_id))
            page_number = getattr(page, "number", None)
        else:
            source_id = getattr(item, "relative_path", "")
            pages = getattr(item, "pages", ())
            text = "\n".join(getattr(page, "text", "") for page in pages)
            number = number_from_name(text) or number_from_name(str(source_id))
            page_number = getattr(pages[0], "number", None) if pages else None
        if number is None:
            continue
        record = grouped.setdefault(number, {"title": guess_title(text), "sources": set(), "pages": set()})
        record["sources"].add(str(source_id))
        if page_number is not None:
            record["pages"].add(int(page_number))
    return tuple(
        Chapter(number, grouped[number]["title"], tuple(sorted(grouped[number]["sources"])), tuple(sorted(grouped[number]["pages"])))
        for number in sorted(grouped)
    )
