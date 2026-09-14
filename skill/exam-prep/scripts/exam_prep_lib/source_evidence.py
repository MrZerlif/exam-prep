"""Persistence for normalized provider evidence, separate from learner state."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from .source_provider import SourceEvidenceEnvelope, normalize_source_evidence
from .schema_validation import SchemaError, load_schema, validate_document
from .storage import StudyStore


@dataclass(frozen=True)
class SourceEvidenceIngestResult:
    provider_id: str
    status: str
    appended: int
    diagnostics: list[str]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "status": self.status,
            "appended": self.appended,
            "diagnostics": list(self.diagnostics),
        }


def _evidence_id(provider_id: str, evidence: Mapping[str, Any]) -> str:
    payload = json.dumps(
        {"provider_id": provider_id, **evidence},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def ingest_source_evidence(
    store: StudyStore, value: Mapping[str, Any] | SourceEvidenceEnvelope
) -> SourceEvidenceIngestResult:
    envelope = (
        value if isinstance(value, SourceEvidenceEnvelope) else normalize_source_evidence(value)
    )
    try:
        validate_document(envelope.to_mapping(), load_schema("source-evidence.schema.json"))
    except SchemaError as exc:
        return SourceEvidenceIngestResult(
            envelope.provider_id,
            "failed",
            0,
            [*envelope.diagnostics, f"invalid normalized source evidence envelope: {exc}"],
        )
    if envelope.status != "ok":
        return SourceEvidenceIngestResult(
            envelope.provider_id, envelope.status, 0, list(envelope.diagnostics)
        )

    existing = {
        str(item.get("evidence_id"))
        for item in store.read_source_evidence()
        if item.get("evidence_id")
    }
    appended = 0
    for evidence in envelope.evidence:
        normalized = evidence.to_mapping()
        evidence_id = evidence.evidence_id or _evidence_id(envelope.provider_id, normalized)
        if evidence_id in existing:
            continue
        store.append_source_evidence(
            {
                "evidence_id": evidence_id,
                "provider_id": envelope.provider_id,
                "status": envelope.status,
                **{
                    key: value
                    for key, value in (
                        ("envelope_id", envelope.envelope_id),
                        ("retrieved_at", envelope.retrieved_at),
                        ("capabilities_used", envelope.capabilities_used),
                        ("retrieval_id", envelope.retrieval_id),
                    )
                    if value is not None
                },
                **normalized,
            }
        )
        existing.add(evidence_id)
        appended += 1
    return SourceEvidenceIngestResult(
        envelope.provider_id, envelope.status, appended, list(envelope.diagnostics)
    )

