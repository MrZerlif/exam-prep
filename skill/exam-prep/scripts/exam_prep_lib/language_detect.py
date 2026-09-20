"""Deterministic script and stop-word language detection."""

from __future__ import annotations

from collections import Counter
import re
import unicodedata
from typing import Sequence

from .lexicon import load
from .text_normalize import canonical_key


LANGUAGE_CONFIDENCE_THRESHOLD = 0.6
_WORD_RE = re.compile(r"[\w]+", re.UNICODE)
_LATIN_LANGUAGES = frozenset({"de", "en", "es", "fr", "it", "pl", "pt", "tr"})
_CYRILLIC_LANGUAGES = frozenset({"ru", "uk"})


def _script(char: str) -> str | None:
    name = unicodedata.name(char, "")
    for marker, script in (
        ("LATIN", "latin"),
        ("CYRILLIC", "cyrillic"),
        ("CJK", "cjk"),
        ("IDEOGRAPH", "cjk"),
        ("HIRAGANA", "kana"),
        ("KATAKANA", "kana"),
        ("ARABIC", "arabic"),
        ("GREEK", "greek"),
        ("HEBREW", "hebrew"),
        ("DEVANAGARI", "devanagari"),
    ):
        if marker in name:
            return script
    return None


def _histogram(text: str) -> Counter[str]:
    return Counter(script for char in text if (script := _script(char)) is not None)


def _script_score(language: str, histogram: Counter[str]) -> float:
    total = sum(histogram.values())
    if total == 0:
        return 0.0
    if language in _LATIN_LANGUAGES:
        return histogram["latin"] / total
    if language in _CYRILLIC_LANGUAGES:
        return histogram["cyrillic"] / total
    if language == "zh":
        return histogram["cjk"] / total if histogram["kana"] == 0 else 0.0
    if language == "ja":
        return (histogram["cjk"] + histogram["kana"]) / total if histogram["kana"] else 0.0
    return 0.0


def _stopword_score(text: str, language: str) -> float:
    words = [canonical_key(word) for word in _WORD_RE.findall(text)]
    if not words:
        return 0.0
    stopwords = {canonical_key(word) for word in load(language).stopwords}
    return sum(word in stopwords for word in words) / len(words)


def detect(text: str, *, candidates: Sequence[str]) -> tuple[str, float] | None:
    """Return a language and confidence, or None below the 0.6 threshold."""

    available = tuple(dict.fromkeys(str(item) for item in candidates))
    if not available or not text.strip():
        return None
    histogram = _histogram(text)
    scored: list[tuple[str, float]] = []
    for language in available:
        try:
            load(language)
        except ValueError:
            continue
        script_score = _script_score(language, histogram)
        stopword_score = _stopword_score(text, language)
        if language in {"zh", "ja"}:
            score = script_score
        else:
            score = 0.5 * script_score + 0.5 * min(1.0, stopword_score * 8.0)
        scored.append((language, score))
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[1], item[0]))
    winner, top = scored[0]
    if top <= 0:
        return None
    # The score already combines script compatibility and language-specific
    # stop-word coverage.  Comparing it with the runner-up would penalize
    # ordinary shared words such as German ``in`` appearing in the English
    # stop-word list, even when the winning language has a perfect score.
    confidence = top
    return (winner, round(confidence, 4)) if confidence >= LANGUAGE_CONFIDENCE_THRESHOLD else None
