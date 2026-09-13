"""Generic source-provider boundary and deterministic local fallback."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

from .provenance import SourceRef, source_ref_from_mapping


@dataclass(frozen=True)
class ProviderStatus:
    provider_id: str
    available: bool
    message: str | None = None


@dataclass(frozen=True)
class SourceEvidence:
    source_ref: SourceRef
    excerpt: str | None = None
    evidence_id: str | None = None
    relevance: float | None = None

    def to_mapping(self) -> dict[str, Any]:
        result = {
            "source_ref": self.source_ref.to_mapping(),
            "excerpt": self.excerpt,
        }
        if self.evidence_id is not None:
            result["evidence_id"] = self.evidence_id
        if self.relevance is not None:
            result["relevance"] = self.relevance
        return result


@dataclass
class SourceEvidenceEnvelope:
    provider_id: str
    status: str
    evidence: list[SourceEvidence]
    diagnostics: list[str]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "status": self.status,
            "evidence": [item.to_mapping() for item in self.evidence],
            "diagnostics": list(self.diagnostics),
        }


class SourceProvider(Protocol):
    provider_id: str

    def health(self) -> ProviderStatus:
        ...

    def list_sources(self) -> list[SourceRef]:
        ...

    def retrieve(self, query: str, *, target_id: str | None = None) -> list[SourceEvidence]:
        ...

    def provenance(self, source_id: str) -> SourceRef | None:
        ...


class LocalSourceProvider:
    """A manifest-backed fallback; document parsing remains outside the core."""

    provider_id = "local"

    def __init__(self, workspace: str | Path, manifest_path: str | Path | None = None):
        self.workspace = Path(workspace).expanduser().resolve()
        self.manifest_path = (
            Path(manifest_path).expanduser().resolve()
            if manifest_path is not None
            else self.workspace / "sources.json"
        )

    def _entries(self) -> list[dict[str, Any]]:
        if not self.manifest_path.exists():
            return []
        try:
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return []
        entries = raw.get("sources", []) if isinstance(raw, Mapping) else []
        return [dict(item) for item in entries if isinstance(item, Mapping)]

    def health(self) -> ProviderStatus:
        return ProviderStatus(self.provider_id, True)

    def list_sources(self) -> list[SourceRef]:
        result: list[SourceRef] = []
        for entry in self._entries():
            try:
                result.append(source_ref_from_mapping(entry))
            except ValueError:
                continue
        return result

    def retrieve(
        self, query: str, *, target_id: str | None = None
    ) -> list[SourceEvidence]:
        needle = query.casefold()
        result: list[SourceEvidence] = []
        for entry in self._entries():
            tags = [str(value) for value in entry.get("tags", [])]
            haystack = " ".join(
                [str(entry.get("source_id", "")), str(entry.get("title", "")), *tags]
            ).casefold()
            if needle and needle not in haystack:
                continue
            if target_id is not None and target_id not in tags:
                continue
            try:
                ref = source_ref_from_mapping(entry)
            except ValueError:
                continue
            result.append(
                SourceEvidence(
                    source_ref=ref,
                    excerpt=entry.get("excerpt"),
                    evidence_id=entry.get("evidence_id"),
                    relevance=entry.get("relevance"),
                )
            )
        return result

    def provenance(self, source_id: str) -> SourceRef | None:
        return next(
            (ref for ref in self.list_sources() if ref.source_id == source_id),
            None,
        )


def normalize_source_evidence(value: Mapping[str, Any]) -> SourceEvidenceEnvelope:
    provider_id = str(value.get("provider_id", "unknown"))
    status = str(value.get("status", "failed"))
    diagnostics = [str(item) for item in value.get("diagnostics", [])]
    evidence: list[SourceEvidence] = []
    for item in value.get("evidence", []):
        if not isinstance(item, Mapping):
            diagnostics.append("ignored non-object source evidence")
            continue
        raw_ref = item.get("source_ref", item)
        if isinstance(raw_ref, str):
            raw_ref = {
                "source_id": raw_ref,
                "authority": "unknown",
                "locator": "",
            }
        try:
            ref = source_ref_from_mapping(raw_ref)
        except (TypeError, ValueError):
            diagnostics.append("ignored source evidence without valid SourceRef")
            continue
        evidence.append(
            SourceEvidence(
                source_ref=ref,
                excerpt=item.get("excerpt"),
                evidence_id=item.get("evidence_id"),
                relevance=item.get("relevance"),
            )
        )
    return SourceEvidenceEnvelope(provider_id, status, evidence, diagnostics)


def _target_items(syllabus: Mapping[str, Any]) -> Iterable[tuple[str, Mapping[str, Any]]]:
    raw = syllabus.get("learning_targets", syllabus.get("concepts", {}))
    if isinstance(raw, Mapping):
        for key, value in raw.items():
            if isinstance(value, Mapping):
                yield str(value.get("target_id", key)), value
    elif isinstance(raw, list):
        for value in raw:
            if isinstance(value, Mapping) and value.get("target_id"):
                yield str(value["target_id"]), value


def compute_source_coverage(
    syllabus: Mapping[str, Any], *, available_source_ids: set[str] | None = None
) -> dict[str, list[str]]:
    available = available_source_ids
    targets_without_sources: list[str] = []
    unknown_source_refs: list[str] = []
    for target_id, target in _target_items(syllabus):
        refs = target.get("source_refs", [])
        if not refs:
            targets_without_sources.append(target_id)
            continue
        for raw_ref in refs:
            source_id = (
                raw_ref
                if isinstance(raw_ref, str)
                else raw_ref.get("source_id")
                if isinstance(raw_ref, Mapping)
                else None
            )
            if available is not None and source_id not in available and source_id not in unknown_source_refs:
                unknown_source_refs.append(str(source_id))
    return {
        "targets_without_sources": targets_without_sources,
        "unknown_source_refs": unknown_source_refs,
    }
