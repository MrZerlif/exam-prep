"""Stable comparison keys for language-aware matching."""

from __future__ import annotations

import re
import unicodedata
from typing import Mapping


FoldRules = Mapping[str, str]
_HYPHENS = re.compile(r"[-‐‑‒–—−]+")
_SPACES = re.compile(r"\s+")
_VIETNAMESE_DISTINCTIVE_LETTERS = frozenset(
    "ăâđêôơưắằẳẵặấầẩẫậếềểễệốồổỗộớờởỡợứừửữự"
)


def canonical_key(value: str) -> str:
    """Return a case-insensitive key without changing semantic marks."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = _HYPHENS.sub(" ", normalized)
    return _SPACES.sub(" ", normalized).strip()


def _apply_fold(value: str, fold: FoldRules) -> str:
    result = value
    for source, target in sorted(fold.items(), key=lambda item: len(item[0]), reverse=True):
        result = result.replace(source, target)
    return result


def _script(char: str) -> str | None:
    name = unicodedata.name(char, "")
    if "LATIN" in name:
        return "latin"
    if "CYRILLIC" in name:
        return "cyrillic"
    if "GREEK" in name:
        return "greek"
    return None


def _strip_latin_cyrillic_marks(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    result: list[str] = []
    script: str | None = None
    for char in decomposed:
        current = _script(char)
        if current is not None:
            script = current
        if unicodedata.category(char) == "Mn" and script in {"latin", "cyrillic"}:
            continue
        result.append(char)
    return unicodedata.normalize("NFC", "".join(result))


def loose_key(value: str, fold: FoldRules = {}) -> str:
    """Return the fallback key, stripping marks only where it is safe."""

    canonical = _apply_fold(canonical_key(value), fold)
    if not canonical:
        return ""
    if any(char in _VIETNAMESE_DISTINCTIVE_LETTERS for char in canonical):
        return canonical
    result = _strip_latin_cyrillic_marks(canonical)
    return result.replace("ß", "ss").replace("ё", "е")


def keys(value: str, fold: FoldRules = {}) -> tuple[str, str]:
    return canonical_key(value), loose_key(value, fold)
