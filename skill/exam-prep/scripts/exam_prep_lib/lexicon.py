"""Validated, cached language lexicons used by material semantics."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from typing import Any, Mapping

from .text_normalize import canonical_key, loose_key


LEXICON_SLOTS = (
    "kind.solution",
    "kind.homework",
    "kind.exam",
    "kind.lecture",
    "kind.notes",
    "struct.chapter",
    "verb.definition",
    "verb.proof",
    "verb.calculation",
    "unit.points",
)


@dataclass(frozen=True)
class Entry:
    token: str
    weight: float
    canonical: str
    loose: str


@dataclass(frozen=True)
class Lexicon:
    language: str
    word_boundaries: bool
    fold: Mapping[str, str]
    by_slot: Mapping[str, tuple[Entry, ...]]
    strip_marks: bool = True
    stopwords: tuple[str, ...] = ()


def _schema_error(message: str) -> ValueError:
    return ValueError(f"invalid lexicon: {message}")


def validate(raw: Mapping[str, Any]) -> list[str]:
    if not isinstance(raw, Mapping):
        raise _schema_error("root must be an object")
    if raw.get("schema_version") != 1:
        raise _schema_error("schema_version must be 1")
    language = raw.get("language")
    if not isinstance(language, str) or len(language) < 2:
        raise _schema_error("language must be a non-empty language code")
    if not isinstance(raw.get("word_boundaries"), bool):
        raise _schema_error("word_boundaries must be boolean")
    normalization = raw.get("normalization")
    if not isinstance(normalization, Mapping):
        raise _schema_error("normalization must be an object")
    fold = normalization.get("fold")
    if not isinstance(fold, Mapping) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in fold.items()):
        raise _schema_error("normalization.fold must map strings to strings")
    if not isinstance(normalization.get("strip_marks"), bool):
        raise _schema_error("normalization.strip_marks must be boolean")
    slots = raw.get("slots")
    if not isinstance(slots, Mapping) or set(slots) != set(LEXICON_SLOTS):
        raise _schema_error("slots must contain exactly the declared slot names")

    normalized_tokens: dict[str, list[tuple[str, bool]]] = {}
    for slot in LEXICON_SLOTS:
        entries = slots[slot]
        if not isinstance(entries, list) or not entries:
            raise _schema_error(f"slot {slot!r} must be a non-empty array")
        for raw_entry in entries:
            explicit_weight = isinstance(raw_entry, Mapping) and "weight" in raw_entry
            if isinstance(raw_entry, str):
                token = raw_entry
            elif isinstance(raw_entry, Mapping):
                token = raw_entry.get("token")
                weight = raw_entry.get("weight", 1.0)
                if not isinstance(token, str) or not token.strip():
                    raise _schema_error(f"slot {slot!r} contains an invalid token")
                if not isinstance(weight, (int, float)) or isinstance(weight, bool) or weight <= 0:
                    raise _schema_error(f"slot {slot!r} contains an invalid weight")
                unknown = set(raw_entry) - {"token", "weight"}
                if unknown:
                    raise _schema_error(f"slot {slot!r} contains unknown fields: {sorted(unknown)}")
            else:
                raise _schema_error(f"slot {slot!r} contains a non-string entry")
            if not token.strip():
                raise _schema_error(f"slot {slot!r} contains an empty token")
            key = canonical_key(token)
            normalized_tokens.setdefault(key, []).append((slot, explicit_weight))

    warnings: list[str] = []
    for token, occurrences in normalized_tokens.items():
        slots_seen = {slot for slot, _explicit in occurrences}
        if len(slots_seen) <= 1:
            continue
        if not all(explicit for _slot, explicit in occurrences):
            raise _schema_error(f"ambiguous lexicon token without explicit weights: {token!r}")
        warnings.append(f"ambiguous_lexicon_token: {token}")
    stopwords = raw.get("stopwords", [])
    if not isinstance(stopwords, list) or any(not isinstance(item, str) or not item.strip() for item in stopwords):
        raise _schema_error("stopwords must be an array of non-empty strings")
    return warnings


def _lexicon_root() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "lexicons"


def _entry(raw_entry: str | Mapping[str, Any], fold: Mapping[str, str], strip_marks: bool) -> Entry:
    if isinstance(raw_entry, str):
        token, weight = raw_entry, 1.0
    else:
        token, weight = str(raw_entry["token"]), float(raw_entry.get("weight", 1.0))
    return Entry(
        token=token,
        weight=weight,
        canonical=canonical_key(token),
        loose=loose_key(token, fold) if strip_marks else canonical_key(token),
    )


def _build(raw: Mapping[str, Any]) -> Lexicon:
    validate(raw)
    normalization = raw["normalization"]
    fold = {str(key): str(value) for key, value in normalization["fold"].items()}
    strip_marks = bool(normalization["strip_marks"])
    return Lexicon(
        language=str(raw["language"]),
        word_boundaries=bool(raw["word_boundaries"]),
        fold=fold,
        by_slot={
            slot: tuple(_entry(entry, fold, strip_marks) for entry in raw["slots"][slot])
            for slot in LEXICON_SLOTS
        },
        strip_marks=strip_marks,
        stopwords=tuple(str(item) for item in raw.get("stopwords", [])),
    )


@lru_cache(maxsize=None)
def _load_cached(language: str) -> Lexicon:
    path = _lexicon_root() / f"{language}.json"
    if not path.exists():
        raise ValueError(f"unknown lexicon language: {language}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return _build(raw)


def load(language: str, *, extra: Lexicon | None = None) -> Lexicon:
    base = _load_cached(str(language))
    if extra is None:
        return base
    if extra.language != base.language:
        raise ValueError("extra lexicon language must match the base language")
    return Lexicon(
        language=base.language,
        word_boundaries=base.word_boundaries,
        fold=base.fold,
        by_slot={slot: base.by_slot[slot] + extra.by_slot.get(slot, ()) for slot in LEXICON_SLOTS},
        strip_marks=base.strip_marks,
        stopwords=base.stopwords + extra.stopwords,
    )


def available() -> tuple[str, ...]:
    return tuple(sorted(path.stem for path in _lexicon_root().glob("*.json")))
