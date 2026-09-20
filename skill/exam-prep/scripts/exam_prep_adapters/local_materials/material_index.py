"""Derived material index and explicit hydration workflow."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping, Any

from exam_prep_lib.source_evidence import ingest_source_evidence
from exam_prep_lib.storage import StudyStore
from exam_prep_lib.workspace import runtime_paths

from .chapters import number_from_name
from .extractor import EXTRACTOR_VERSION, MAX_FILE_BYTES, ExtractedSource, extract_sources
from .ingest import build_envelope
from .questions import source_question_issues


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def _configuration_hash(max_file_bytes: int) -> str:
    value = json.dumps({"extractor": EXTRACTOR_VERSION, "max_file_bytes": max_file_bytes}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_material_index(materials_dir: str | Path, *, max_file_bytes: int = MAX_FILE_BYTES) -> dict[str, Any]:
    sources = extract_sources(materials_dir, max_file_bytes=max_file_bytes)
    entries: list[dict[str, Any]] = []
    configuration_hash = _configuration_hash(max_file_bytes)
    for source in sources:
        chapter = number_from_name(source.relative_path)
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
                    "issues": [issue.to_mapping() for issue in tuple(source.issues) + source_question_issues(source)],
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


def hydrate_sources(
    materials_dir: str | Path,
    store: StudyStore,
    source_ids: list[str] | tuple[str, ...] | None = None,
    *,
    authority_map: Mapping[str, str] | None = None,
    max_excerpt_chars: int = 1200,
    extraction_mode: str = "scored",
) -> dict[str, Any]:
    sources = _source_ids(tuple(extract_sources(materials_dir)), set(source_ids or ()))
    envelope = build_envelope(sources, authority_map=authority_map, max_excerpt_chars=max_excerpt_chars, extraction_mode=extraction_mode)
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
) -> dict[str, Any]:
    if mode not in {"lightweight", "full"}:
        raise ValueError("mode must be lightweight or full")
    index = build_material_index(materials_dir, max_file_bytes=max_file_bytes)
    if not dry_run:
        _write_json(runtime_paths(store.root).material_index, index)
        _write_json(
            runtime_paths(store.root).ingest_issues,
            {"schema_version": 1, "issues": [issue for entry in index["entries"] for issue in entry.get("issues", [])]},
        )
    result: dict[str, Any] = {"status": "dry_run" if dry_run else "indexed", "mode": mode, "index": index}
    if mode == "full":
        if dry_run:
            result["appended"] = 0
        else:
            hydrated = hydrate_sources(materials_dir, store, authority_map=authority_map, max_excerpt_chars=max_excerpt_chars, extraction_mode=extraction_mode)
            result.update({"appended": hydrated["appended"], "diagnostics": hydrated["diagnostics"]})
    return result
