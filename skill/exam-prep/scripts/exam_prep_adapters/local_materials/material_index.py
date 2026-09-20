"""Derived material index and explicit hydration workflow."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path
import re
from typing import Mapping, Any

from exam_prep_lib.source_evidence import ingest_source_evidence
from exam_prep_lib.storage import StudyStore
from exam_prep_lib.workspace import runtime_paths
from exam_prep_lib.ingest_issues import IngestIssue
from exam_prep_lib.language_detect import detect
from exam_prep_lib.lexicon import available, learned_languages, load, load_learned, Lexicon

from .chapters import number_from_name
from .extractor import EXTRACTOR_VERSION, MAX_FILE_BYTES, ExtractedSource, classify, extract_sources
from .ingest import build_envelope
from .labels import segment
from .points import extract as extract_points, infer_token
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


_UNIT_CANDIDATE_RE = re.compile(r"\(\s*\d+\s+([^)]*)\)", re.UNICODE)
_UNCLASSIFIED_LIMIT = 20
_UNCLASSIFIED_TEXT_LIMIT = 160


def _points_summary(
    sources: tuple[ExtractedSource, ...],
    source_lexicons: Mapping[str, Lexicon],
    default_lexicon: Lexicon,
) -> dict[str, Any]:
    """Record the point total each graded source declares.

    `validate` has no access to the materials directory, so the inferred
    total has to be written down here if it is ever to be compared against
    the course's expected_total_points.
    """

    summary: dict[str, Any] = {}
    for source in sources:
        if source.kind not in {"exam", "homework"}:
            continue
        lexicon = source_lexicons.get(source.relative_path, default_lexicon)
        token = infer_token(source.pages, lexicon=lexicon)
        if token is None:
            continue
        values = [
            extract_points(block.body, token=token, lexicon=lexicon)
            for page in source.pages
            for block in segment(page.text)
        ]
        found = [value for value in values if value is not None]
        if found:
            summary[source.relative_path] = {"token": token, "total": sum(found)}
    return summary


def _unclassified_summary(
    sources: tuple[ExtractedSource, ...],
    *,
    source_languages: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, Any] | None:
    unclassified = tuple(source for source in sources if source.kind == "other")
    if not unclassified:
        return None
    file_stems = sorted({Path(source.relative_path).stem[:_UNCLASSIFIED_TEXT_LIMIT] for source in unclassified})
    head_counts: Counter[str] = Counter()
    unit_counts: Counter[str] = Counter()
    for source in unclassified:
        for page in source.pages:
            lines = [line.strip()[:_UNCLASSIFIED_TEXT_LIMIT] for line in page.text.splitlines() if line.strip()]
            head_counts.update(lines[:3])
            for match in _UNIT_CANDIDATE_RE.finditer(page.text):
                token = match.group(1).strip().split()[0] if match.group(1).strip() else ""
                if token:
                    unit_counts[token[:_UNCLASSIFIED_TEXT_LIMIT]] += 1
    repeated_heads = sorted(
        (head for head, count in head_counts.items() if count >= 2),
        key=lambda value: (-head_counts[value], value),
    )[:_UNCLASSIFIED_LIMIT]
    unit_candidates = sorted(unit_counts, key=lambda value: (-unit_counts[value], value))[:_UNCLASSIFIED_LIMIT]
    slots_needed = ["kind.exam", "kind.solution"]
    if unit_candidates:
        slots_needed.append("unit.points")
    languages = {
        metadata.get("language")
        for source in unclassified
        for metadata in ((source_languages or {}).get(source.relative_path, {}),)
        if metadata.get("language")
    }
    return {
        "language": next(iter(languages)) if len(languages) == 1 else None,
        "file_stems": file_stems[:_UNCLASSIFIED_LIMIT],
        "repeated_heads": repeated_heads,
        "unit_candidates": unit_candidates,
        "slots_needed": slots_needed,
    }


def _localized_sources(
    materials_dir: str | Path,
    *,
    default_language: str,
    default_lexicon: Lexicon,
    default_metadata: Mapping[str, Any] | None,
    lexicons: Mapping[str, Lexicon],
    max_file_bytes: int = MAX_FILE_BYTES,
) -> tuple[tuple[ExtractedSource, ...], dict[str, dict[str, Any]], dict[str, Lexicon]]:
    initial = extract_sources(
        materials_dir,
        max_file_bytes=max_file_bytes,
        language=default_language,
        lexicon=default_lexicon,
    )
    source_languages: dict[str, dict[str, Any]] = {}
    source_lexicons: dict[str, Lexicon] = {}
    localized: list[ExtractedSource] = []
    candidates = tuple(lexicons)
    for source in initial:
        text = "\n".join(page.text for page in source.pages)[:20_000]
        detected = detect(text, candidates=candidates) if text else None
        if detected is not None and detected[0] in lexicons:
            source_language, confidence = detected
            metadata = {"language": source_language, "language_source": "detected", "language_confidence": confidence}
        elif (default_metadata or {}).get("value"):
            source_language = default_language
            metadata = {
                "language": source_language,
                "language_source": str((default_metadata or {}).get("source", "configured")),
                "language_confidence": (default_metadata or {}).get("confidence"),
            }
        else:
            source_language = default_language
            metadata = {"language": None, "language_source": "unknown", "language_confidence": None}
        source_lexicon = lexicons.get(source_language, default_lexicon)
        kind = classify(source.relative_path, text, source_language, lexicon=source_lexicon)
        issues = list(source.issues)
        if metadata["language"] is None:
            issues.append(
                IngestIssue(
                    "unsupported_language",
                    source.relative_path,
                    "language detection confidence was below 0.6",
                    "gap",
                )
            )
        localized.append(replace(source, kind=kind, issues=tuple(issues)))
        source_languages[source.relative_path] = metadata
        source_lexicons[source.relative_path] = source_lexicon
    return tuple(localized), source_languages, source_lexicons


def localize_materials(
    materials_dir: str | Path,
    *,
    default_language: str,
    default_lexicon: Lexicon,
    default_metadata: Mapping[str, Any] | None,
    lexicons: Mapping[str, Lexicon],
    max_file_bytes: int = MAX_FILE_BYTES,
) -> tuple[tuple[ExtractedSource, ...], dict[str, dict[str, Any]], dict[str, Lexicon]]:
    """Extract materials and attach the language/lexicon selected per source."""

    return _localized_sources(
        materials_dir,
        default_language=default_language,
        default_lexicon=default_lexicon,
        default_metadata=default_metadata,
        lexicons=lexicons,
        max_file_bytes=max_file_bytes,
    )


def workspace_lexicons(workspace: str | Path) -> dict[str, Lexicon]:
    """Load bundled and learned lexicons available to a workspace."""

    languages = sorted(set(available()) | set(learned_languages(workspace)))
    return {
        language: load(language, extra=load_learned(language, workspace))
        for language in languages
    }


def build_material_index(
    materials_dir: str | Path,
    *,
    max_file_bytes: int = MAX_FILE_BYTES,
    language: str = "ru",
    language_metadata: Mapping[str, Any] | None = None,
    lexicon: Lexicon | None = None,
    lexicons: Mapping[str, Lexicon] | None = None,
) -> dict[str, Any]:
    semantic_lexicon = lexicon or load(language)
    available_lexicons = dict(lexicons or {language: semantic_lexicon})
    available_lexicons.setdefault(language, semantic_lexicon)
    sources, source_languages, source_lexicons = _localized_sources(
        materials_dir,
        default_language=language,
        default_lexicon=semantic_lexicon,
        default_metadata=language_metadata,
        lexicons=available_lexicons,
        max_file_bytes=max_file_bytes,
    )
    entries: list[dict[str, Any]] = []
    configuration_hash = _configuration_hash(max_file_bytes, language)
    for source in sources:
        source_metadata = source_languages.get(source.relative_path, {"language": language, "language_source": "configured", "language_confidence": 1.0})
        source_language = str(source_metadata.get("language") or language)
        source_lexicon = source_lexicons.get(source.relative_path, semantic_lexicon)
        chapter = number_from_name(source.relative_path, source_language, lexicon=source_lexicon)
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
                    "issues": [
                        issue.to_mapping()
                        for issue in tuple(source.issues)
                        + source_question_issues(source, source_language, lexicon=source_lexicon)
                    ],
                    "language": source_metadata.get("language"),
                    "language_source": source_metadata.get("language_source"),
                    "language_confidence": source_metadata.get("language_confidence"),
                }
            )
    result: dict[str, Any] = {
        "schema_version": 2,
        "extractor": "local-materials",
        "extractor_version": EXTRACTOR_VERSION,
        "configuration_hash": configuration_hash,
        "entries": entries,
    }
    points = _points_summary(sources, source_lexicons, semantic_lexicon)
    if points:
        result["points"] = points
    unclassified = _unclassified_summary(sources, source_languages=source_languages)
    if unclassified is not None:
        result["unclassified"] = unclassified
    return result


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
    *,
    persist: bool = True,
) -> tuple[str, dict[str, object], IngestIssue | None]:
    if requested:
        if requested not in available() and requested not in learned_languages(store.state_path):
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
        if configured not in available() and configured not in learned_languages(store.state_path):
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
    if persist:
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
    language: str | None = None,
    language_metadata: Mapping[str, Any] | None = None,
    lexicon: Lexicon | None = None,
    lexicons: Mapping[str, Lexicon] | None = None,
) -> dict[str, Any]:
    if language is None:
        language, detected_metadata, _language_issue = _course_language(
            materials_dir,
            store,
            None,
            persist=False,
        )
        language_metadata = language_metadata or detected_metadata
    available_lexicons = dict(lexicons or workspace_lexicons(store.state_path))
    semantic_lexicon = lexicon or available_lexicons.get(language)
    if semantic_lexicon is None:
        semantic_lexicon = load(language, extra=load_learned(language, store.state_path))
    available_lexicons.setdefault(language, semantic_lexicon)
    localized, source_languages, source_lexicons = _localized_sources(
        materials_dir,
        default_language=language,
        default_lexicon=semantic_lexicon,
        default_metadata=language_metadata,
        lexicons=available_lexicons,
    )
    sources = _source_ids(localized, set(source_ids or ()))
    envelope = build_envelope(
        sources,
        authority_map=authority_map,
        max_excerpt_chars=max_excerpt_chars,
        extraction_mode=extraction_mode,
        language=language,
        lexicon=semantic_lexicon,
        lexicon_by_source=source_lexicons,
        language_by_source=source_languages,
    )
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
    active_language, language_metadata, language_issue = _course_language(
        materials_dir,
        store,
        language,
        persist=not dry_run,
    )
    lexicons = workspace_lexicons(store.state_path)
    semantic_lexicon = lexicons[active_language]
    index = build_material_index(
        materials_dir,
        max_file_bytes=max_file_bytes,
        language=active_language,
        language_metadata=language_metadata,
        lexicon=semantic_lexicon,
        lexicons=lexicons,
    )
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
            hydrated = hydrate_sources(
                materials_dir,
                store,
                authority_map=authority_map,
                max_excerpt_chars=max_excerpt_chars,
                extraction_mode=extraction_mode,
                language=active_language,
                language_metadata=language_metadata,
                lexicon=semantic_lexicon,
                lexicons=lexicons,
            )
            result.update({"appended": hydrated["appended"], "diagnostics": hydrated["diagnostics"]})
    return result
