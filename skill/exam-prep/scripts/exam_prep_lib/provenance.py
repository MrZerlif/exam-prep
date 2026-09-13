"""Structured source references and explicit authority semantics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


AUTHORITY_RANKS = {
    "teacher_material": 5,
    "official_exam_list": 5,
    "course_policy": 5,
    "lecture_notes": 4,
    "problem_sets": 3,
    "general_reference": 2,
    "learner_note": 1,
    "unknown": 0,
}


@dataclass(frozen=True)
class SourceRef:
    source_id: str
    authority: str
    locator: str = ""
    title: str | None = None
    excerpt: str | None = None
    content_hash: str | None = None
    provider_id: str = "local"
    artifact_id: str | None = None
    retrieved_at: str | None = None
    version: str | None = None
    location: dict[str, Any] | None = None
    raw_locator: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SourceRef":
        source_id = value.get("source_id")
        authority = value.get("authority")
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("source_ref.source_id must be a non-empty string")
        if not isinstance(authority, str) or not authority.strip():
            raise ValueError("source_ref.authority must be a non-empty string")
        return cls(
            source_id=source_id,
            authority=authority,
            locator=(
                str(value.get("locator"))
                if isinstance(value.get("locator"), str)
                else str(value.get("raw_locator", ""))
            ),
            title=value.get("title"),
            excerpt=value.get("excerpt"),
            content_hash=value.get("content_hash"),
            provider_id=str(value.get("provider_id", value.get("provider", "local"))),
            artifact_id=value.get("artifact_id"),
            retrieved_at=value.get("retrieved_at"),
            version=str(value["version"]) if value.get("version") is not None else None,
            location=dict(value["location"]) if isinstance(value.get("location"), Mapping) else None,
            raw_locator=str(value["raw_locator"]) if value.get("raw_locator") is not None else None,
        )

    @property
    def authority_rank(self) -> int:
        return AUTHORITY_RANKS.get(self.authority, 0)

    @property
    def provider(self) -> str:
        """Provider alias used by the product-neutral SourceRef contract."""

        return self.provider_id

    def to_mapping(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "source_id": self.source_id,
            "authority": self.authority,
            "locator": self.locator,
            "provider_id": self.provider_id,
        }
        for field in (
            "title",
            "excerpt",
            "content_hash",
            "artifact_id",
            "retrieved_at",
        ):
            value = getattr(self, field)
            if value is not None:
                result[field] = value
        if self.version is not None:
            result["version"] = self.version
        if self.location is not None:
            result["location"] = dict(self.location)
        if self.raw_locator is not None:
            result["raw_locator"] = self.raw_locator
        return result


def source_ref_from_mapping(value: Mapping[str, Any] | SourceRef) -> SourceRef:
    if isinstance(value, SourceRef):
        return value
    return SourceRef.from_mapping(value)


def normalize_source_refs(values: Any) -> list[dict[str, Any]]:
    """Normalize a source-ref collection, accepting legacy string IDs."""

    if not isinstance(values, list):
        return []
    normalized: list[dict[str, Any]] = []
    for value in values:
        if isinstance(value, str):
            normalized.append(
                SourceRef(
                    source_id=value,
                    authority="unknown",
                    locator="",
                ).to_mapping()
            )
        elif isinstance(value, Mapping):
            normalized.append(source_ref_from_mapping(value).to_mapping())
    return normalized

