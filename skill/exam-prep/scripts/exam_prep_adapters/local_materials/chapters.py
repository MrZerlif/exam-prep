"""Deterministic chapter hints for local material pages."""

# Portions adapted from ZeKaiNie/universal-examprep-skill (MIT), see vendor/exam-cram-coach/LICENSE

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Any

from exam_prep_lib.lexicon import Lexicon, load
from exam_prep_lib.semantics import match

_CHAPTER_NUMBER_RE = re.compile(r"(?<!\w)([0-9]{1,3}|[IVXLCDM]+)(?!\w)", re.IGNORECASE)


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


def number_from_name(value: str, language: str = "ru", *, lexicon: Lexicon | None = None) -> int | None:
    found = match("struct.chapter", value, lexicon or load(language))
    if found is None:
        return None
    normalized = value.casefold()
    token = found.token.casefold()
    start = normalized.find(token)
    suffix = normalized[start + len(token):] if start >= 0 else normalized
    number_match = _CHAPTER_NUMBER_RE.search(suffix)
    if number_match is None:
        return None
    token = number_match.group(1)
    return int(token) if token.isdigit() else _roman(token)


def guess_title(value: str) -> str:
    first = next((line.strip() for line in value.splitlines() if line.strip()), "")
    return first.lstrip("# ")[:200] or "Untitled"


def build_chapters(items: Iterable[Any], language: str = "ru", *, lexicon: Lexicon | None = None) -> tuple[Chapter, ...]:
    grouped: dict[int, dict[str, Any]] = {}
    for item in items:
        if isinstance(item, tuple) and len(item) == 2:
            source_id, page = item
            text = getattr(page, "text", str(page))
            number = number_from_name(text, language, lexicon=lexicon) or number_from_name(str(source_id), language, lexicon=lexicon)
            page_number = getattr(page, "number", None)
        else:
            source_id = getattr(item, "relative_path", "")
            pages = getattr(item, "pages", ())
            text = "\n".join(getattr(page, "text", "") for page in pages)
            number = number_from_name(text, language, lexicon=lexicon) or number_from_name(str(source_id), language, lexicon=lexicon)
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
