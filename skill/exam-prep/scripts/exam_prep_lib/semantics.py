"""The single language-aware matching boundary for the exam-prep parser."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .lexicon import Lexicon
from .text_normalize import canonical_key, loose_key


@dataclass(frozen=True)
class Match:
    slot: str
    token: str
    weight: float
    exact: bool


def _contains(text: str, token: str, word_boundaries: bool) -> bool:
    if not token:
        return False
    if not word_boundaries:
        return token in text
    return re.search(rf"(?<!\w){re.escape(token)}(?!\w)", text, re.UNICODE) is not None


def match(slot: str, text: str, lexicon: Lexicon) -> Match | None:
    entries = lexicon.by_slot.get(slot, ())
    canonical = canonical_key(text)
    for entry in sorted(entries, key=lambda item: (-item.weight, -len(item.canonical), item.token)):
        if _contains(canonical, entry.canonical, lexicon.word_boundaries):
            return Match(slot, entry.token, entry.weight, True)
    loose = loose_key(text, lexicon.fold) if lexicon.strip_marks else canonical
    for entry in sorted(entries, key=lambda item: (-item.weight, -len(item.loose), item.token)):
        if _contains(loose, entry.loose, lexicon.word_boundaries):
            return Match(slot, entry.token, entry.weight * 0.8, False)
    return None


def best_slot(prefix: str, text: str, lexicon: Lexicon) -> Match | None:
    matches: list[tuple[int, Match]] = []
    for index, slot in enumerate(lexicon.by_slot):
        if slot.startswith(prefix):
            found = match(slot, text, lexicon)
            if found is not None:
                matches.append((index, found))
    if not matches:
        return None
    return max(
        matches,
        key=lambda item: (item[1].weight, item[1].exact, len(item[1].token), -item[0]),
    )[1]
