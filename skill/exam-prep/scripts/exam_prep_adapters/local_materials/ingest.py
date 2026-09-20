"""Convert extracted local pages into the shared SourceEvidenceEnvelope."""

from __future__ import annotations

import hashlib
import json
from typing import Iterable, Mapping

from exam_prep_lib.provenance import AUTHORITY_RANKS, SourceRef
from exam_prep_lib.source_provider import SourceEvidence, SourceEvidenceEnvelope
from exam_prep_lib.schema_validation import load_schema, validate_document

from .extractor import EXTRACTOR_VERSION, ExtractedSource
from .candidates import score
from .labels import segment
from exam_prep_lib.lexicon import load


def _configuration_hash(max_excerpt_chars: int, extraction_mode: str, language: str) -> str:
    payload = json.dumps(
        {
            "extractor": EXTRACTOR_VERSION,
            "max_excerpt_chars": int(max_excerpt_chars),
            "extraction_mode": extraction_mode,
            "language": language,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _default_authority(kind: str) -> str:
    return {
        "lecture": "lecture_notes",
        "notes": "lecture_notes",
        "homework": "problem_sets",
        "exam": "general_reference",
        "solution": "general_reference",
        "other": "general_reference",
    }.get(kind, "general_reference")


def build_envelope(
    sources: Iterable[ExtractedSource],
    *,
    provider_id: str = "local-materials",
    authority_map: Mapping[str, str] | None = None,
    max_excerpt_chars: int = 1200,
    extraction_mode: str = "scored",
    language: str = "ru",
) -> SourceEvidenceEnvelope:
    if extraction_mode not in {"legacy", "scored"}:
        raise ValueError("extraction_mode must be legacy or scored")
    materialized = tuple(sources)
    authority_map = dict(authority_map or {})
    configuration_hash = _configuration_hash(max_excerpt_chars, extraction_mode, language)
    evidence: list[SourceEvidence] = []
    diagnostics: list[str] = []
    for source in materialized:
        diagnostics.extend(f"{issue.kind}: {issue.detail}" for issue in source.issues)
        authority = authority_map.get(source.relative_path, _default_authority(source.kind))
        if authority not in AUTHORITY_RANKS:
            diagnostics.append(f"unknown authority {authority!r} for {source.relative_path}")
            authority = "general_reference"
        for page in source.pages:
            text = page.text.strip()
            page_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            source_id = f"{source.relative_path}#p{page.number}"
            ref = SourceRef(
                source_id=source_id,
                authority=authority,
                locator=f"{source.relative_path} p.{page.number}",
                title=source.relative_path,
                excerpt=text[:max_excerpt_chars] or None,
                content_hash=page_hash,
                provider_id=provider_id,
                artifact_id=source_id,
                retrieved_at=None,
                version=EXTRACTOR_VERSION,
                location={
                    "page": page.number,
                    "slide": page.number if source.relative_path.casefold().endswith(".pptx") else None,
                    "extractor": "local-materials",
                    "extractor_version": EXTRACTOR_VERSION,
                    "backend": source.backend,
                    "backend_version": source.backend_version,
                    "configuration_hash": configuration_hash,
                    "extraction": {
                        "mode": extraction_mode,
                        "candidates": [
                            {
                                "label": candidate.segment.label.raw,
                                "score": candidate.score,
                                "bucket": candidate.bucket,
                                "signals": candidate.signals,
                            }
                            for candidate in (
                                score(segment(text), source=source, lexicon=load(language))
                                if extraction_mode == "scored"
                                else ()
                            )
                        ],
                    },
                },
            )
            evidence.append(SourceEvidence(source_ref=ref, excerpt=text[:max_excerpt_chars]))
    status = "ok" if evidence else ("unavailable" if materialized else "unavailable")
    envelope = SourceEvidenceEnvelope(
        provider_id=provider_id,
        status=status,
        evidence=evidence,
        diagnostics=diagnostics,
        envelope_id=hashlib.sha256(
            json.dumps([item.to_mapping() for item in evidence], sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest(),
        retrieved_at=None,
        capabilities_used=["local-materials", "deterministic-extraction"],
    )
    validate_document(envelope.to_mapping(), load_schema("source-evidence.schema.json"))
    return envelope
