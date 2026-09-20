"""Derived material index and explicit hydration workflow."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping, Any

from exam_prep_lib.source_evidence import ingest_source_evidence
from exam_prep_lib.storage import StudyStore
from exam_prep_lib.workspace import runtime_paths
from exam_prep_lib.ingest_issues import IngestIssue
from exam_prep_lib.language_detect import detect
from exam_prep_lib.lexicon import available

from .chapters import number_from_name
from .extractor import EXTRACTOR_VERSION, MAX_FILE_BYTES, ExtractedSource, extract_sources
from .ingest import build_envelope
from .questions import source_question_issues


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def _configuration_hash(max_file_bytes: int, language: str) -> str:
    value = json.dumps(
        {"extractor": EXTRACTOR_VERSION, "max_file_bytes": max_file_bytes, "language": language},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_material_index(materials_dir: str | Path, *, max_file_bytes: int = MAX_FILE_BYTES, language: str = "ru") -> dict[str, Any]:
    sources = extract_sources(materials_dir, max_file_bytes=max_file_bytes, language=language)
    entries: list[dict[str, Any]] = []
    configuration_hash = _configuration_hash(max_file_bytes, language)
    for source in sources:
        chapter = number_from_name(source.relative_path, language)
        for page in source.pages or (None,):
            entries.append(
                {
                    "relative_path": source.relative_path,
                    "page": page.number if page is not None else None,
                    "content_hash": hashlib.sha256((page.text if page is not None else "").encode("utf-8")).hexdigest(),
                    "short_preview": (page.text if page is not None else "")[:200],
                    "chapter_hint": chapter,
                    "kind": source.kind,
                    "extractor": "local-materials",
                    "extractor_version": EXTRACTOR_VERSION,
                    "backend": source.backend,
                    "backend_version": source.backend_version,
                    "configuration_hash": configuration_hash,
                    "issues": [issue.to_mapping() for issue in tuple(source.issues) + source_question_issues(source, language)],
                }
            )
    return {"schema_version": 1, "extractor": "local-materials", "extractor_version": EXTRACTOR_VERSION, "configuration_hash": configuration_hash, "entries": entries}


def load_material_index(runtime_root: str | Path) -> dict[str, Any]:
    root = Path(runtime_root)
    path = root / "material_index.json" if root.name != ".exam-prep" else root / "material_index.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _source_ids(sources: tuple[ExtractedSource, ...], selected: set[str] | None) -> tuple[ExtractedSource, ...]:
    if not selected:
        return sources
    result = []
    for source in sources:
        pages = tuple(page for page in source.pages if f"{source.relative_path}#p{page.number}" in selected or source.relative_path in selected)
        if pages:
            result.append(ExtractedSource(source.relative_path, source.kind, pages, source.content_hash, source.backend, source.backend_version, source.issues))
    return tuple(result)


def _course_language(
    materials_dir: str | Path,
    store: StudyStore,
    requested: str | None,
) -> tuple[str, dict[str, object], IngestIssue | None]:
    if requested:
        if requested not in available():
            raise ValueError(f"unknown language lexicon: {requested}")
        return requested, {"value": requested, "source": "configured", "confidence": 1.0}, None
    course_path = runtime_paths(store.root).course
    if not course_path.exists():
        return "ru", {"value": None, "source": "unknown", "confidence": None}, None
    try:
        course = json.loads(course_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return "ru", {"value": None, "source": "unknown", "confidence": None}, None
    configured = course.get("language")
    if configured:
        if configured not in available():
            issue = IngestIssue("unsupported_language", None, f"no lexicon is available for configured language {configured!r}", "gap")
            return "ru", {"value": configured, "source": "configured", "confidence": None}, issue
        return str(configured), {"value": configured, "source": course.get("language_source", "configured"), "confidence": course.get("language_confidence", 1.0)}, None
    if course.get("language_detection_attempted"):
        return "ru", {"value": None, "source": "unknown", "confidence": None}, IngestIssue("unsupported_language", None, "language detection confidence was below 0.6", "gap")
    sources = extract_sources(materials_dir)
    text = "\n".join(page.text for source in sources for page in source.pages)
    detected = detect(text, candidates=available())
    updated = dict(course)
    updated["language_detection_attempted"] = True
    issue: IngestIssue | None = None
    if detected is None:
        updated.update({"language": None, "language_source": "unknown", "language_confidence": None})
        metadata = {"value": None, "source": "unknown", "confidence": None}
        issue = IngestIssue("unsupported_language", None, "language detection confidence was below 0.6", "gap")
        active = "ru"
    else:
        language, confidence = detected
        updated.update({"language": language, "language_source": "detected", "language_confidence": confidence})
        metadata = {"value": language, "source": "detected", "confidence": confidence}
        active = language
    _write_json(course_path, updated)
    return active, metadata, issue


def hydrate_sources(
    materials_dir: str | Path,
    store: StudyStore,
    source_ids: list[str] | tuple[str, ...] | None = None,
    *,
    authority_map: Mapping[str, str] | None = None,
    max_excerpt_chars: int = 1200,
    extraction_mode: str = "scored",
    language: str = "ru",
) -> dict[str, Any]:
    sources = _source_ids(tuple(extract_sources(materials_dir, language=language)), set(source_ids or ()))
    envelope = build_envelope(sources, authority_map=authority_map, max_excerpt_chars=max_excerpt_chars, extraction_mode=extraction_mode, language=language)
    result = ingest_source_evidence(store, envelope)
    return {**result.to_mapping(), "source_ids": [item.source_ref.source_id for item in envelope.evidence]}


def ingest_materials(
    materials_dir: str | Path,
    store: StudyStore,
    *,
    mode: str = "lightweight",
    dry_run: bool = False,
    authority_map: Mapping[str, str] | None = None,
    max_excerpt_chars: int = 1200,
    max_file_bytes: int = MAX_FILE_BYTES,
    include_unclassified: bool = False,
    extraction_mode: str = "scored",
    language: str | None = None,
) -> dict[str, Any]:
    if mode not in {"lightweight", "full"}:
        raise ValueError("mode must be lightweight or full")
    active_language, language_metadata, language_issue = _course_language(materials_dir, store, language)
    index = build_material_index(materials_dir, max_file_bytes=max_file_bytes, language=active_language)
    if language_issue is not None and index["entries"]:
        index["entries"][0]["issues"].append(language_issue.to_mapping())
    if not dry_run:
        _write_json(runtime_paths(store.root).material_index, index)
        _write_json(
            runtime_paths(store.root).ingest_issues,
            {"schema_version": 1, "issues": [issue for entry in index["entries"] for issue in entry.get("issues", [])] + ([] if language_issue is None or index["entries"] else [language_issue.to_mapping()])},
        )
    result: dict[str, Any] = {"status": "dry_run" if dry_run else "indexed", "mode": mode, "language": language_metadata, "index": index}
    if mode == "full":
        if dry_run:
            result["appended"] = 0
        else:
            hydrated = hydrate_sources(materials_dir, store, authority_map=authority_map, max_excerpt_chars=max_excerpt_chars, extraction_mode=extraction_mode, language=active_language)
            result.update({"appended": hydrated["appended"], "diagnostics": hydrated["diagnostics"]})
    return result
