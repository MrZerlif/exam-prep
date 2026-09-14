"""Explicit, non-destructive migration from the exam-prep v1 runtime."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .provenance import normalize_source_refs
from .defaults import default_course, default_learner, default_session
from .reducer import reduce_learning_state
from .scheduler import build_review_queue
from .storage import StudyStore


class MigrationError(ValueError):
    """The legacy workspace cannot be migrated safely."""


@dataclass(frozen=True)
class MigrationResult:
    migrated: bool
    source_root: str
    destination_root: str
    id_map: dict[str, str]
    observation_count: int
    legacy_unfrozen_count: int
    source_fingerprint: str

    def to_mapping(self) -> dict[str, Any]:
        return {
            "migrated": self.migrated,
            "source_root": self.source_root,
            "destination_root": self.destination_root,
            "id_map": self.id_map,
            "observation_count": self.observation_count,
            "legacy_unfrozen_count": self.legacy_unfrozen_count,
            "source_fingerprint": self.source_fingerprint,
        }


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise MigrationError(f"cannot read legacy JSON: {path}") from exc


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_bytes().splitlines(keepends=True):
        if not line.strip() or not line.endswith((b"\n", b"\r")):
            continue
        try:
            record = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
            raise MigrationError(f"cannot read legacy JSONL: {path}") from exc
        if not isinstance(record, dict):
            raise MigrationError(f"legacy JSONL record is not an object: {path}")
        records.append(record)
    return records


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.migration-tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _legacy_workspace(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    return resolved.parent if resolved.name == "state" else resolved


def _source_fingerprint(source: Path) -> str:
    entries: list[dict[str, str]] = []
    for path in sorted((item for item in source.rglob("*") if item.is_file())):
        entries.append(
            {
                "path": path.relative_to(source).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    payload = {"source_root": str(source.resolve()), "files": entries}
    return StudyStore.hash_document(payload)


def _legacy_revision_metadata(source: Path) -> dict[str, Any]:
    # Keep source revision metadata as history without copying revisions one-for-one.
    pointer = _read_json(source / "current.json", None)
    manifests: list[dict[str, Any]] = []
    revisions = source / "revisions"
    if revisions.is_dir():
        for revision_dir in sorted(
            (path for path in revisions.iterdir() if path.is_dir() and path.name.isdigit()),
            key=lambda path: int(path.name),
        ):
            manifest = _read_json(revision_dir / "manifest.json", None)
            if isinstance(manifest, dict):
                manifests.append(
                    {
                        "revision_directory": revision_dir.name,
                        "manifest": manifest,
                    }
                )
    return {
        "source_current_pointer": pointer,
        "source_revision_manifests": manifests,
    }


def _existing_migration(marker: Path, source: Path, destination: Path) -> MigrationResult:
    existing = _read_json(marker, {})
    fingerprint = existing.get("source_fingerprint")
    current = _source_fingerprint(source)
    if fingerprint != current:
        raise MigrationError(
            "migration source fingerprint differs from the existing migration marker"
        )
    return MigrationResult(
        migrated=False,
        source_root=str(source),
        destination_root=str(destination),
        id_map=dict(existing.get("id_map", {})),
        observation_count=int(existing.get("observation_count", 0)),
        legacy_unfrozen_count=int(existing.get("legacy_unfrozen_count", 0)),
        source_fingerprint=str(fingerprint),
    )


def migrate_legacy_workspace(legacy_workspace: str | Path) -> MigrationResult:
    """Convert old state into .exam-prep without mutating the source tree."""

    workspace = _legacy_workspace(Path(legacy_workspace))
    source = workspace / "state"
    if not source.exists():
        raise MigrationError(f"legacy state directory does not exist: {source}")
    destination = workspace / ".exam-prep"
    marker = destination / "migration.json"
    if marker.exists():
        return _existing_migration(marker, source, destination)
    if destination.exists():
        try:
            occupied = any(destination.iterdir())
        except OSError as exc:
            raise MigrationError(f"cannot inspect migration target: {destination}") from exc
        if occupied:
            raise MigrationError(
                f"refusing to overwrite existing unrelated target: {destination}"
            )
        destination.rmdir()

    source_fingerprint = _source_fingerprint(source)

    old_syllabus = _read_json(source / "syllabus.json", {"concepts": {}})
    old_concepts = old_syllabus.get("concepts", {})
    if not isinstance(old_concepts, dict):
        raise MigrationError("legacy syllabus.concepts must be an object")
    id_map = {
        str(old_id): f"legacy:math-study:{old_id}"
        for old_id in old_concepts
    }
    learning_targets: list[dict[str, Any]] = []
    for old_id, value in old_concepts.items():
        if not isinstance(value, dict):
            raise MigrationError(f"legacy concept {old_id!r} must be an object")
        new_id = id_map[str(old_id)]
        target = dict(value)
        target["target_id"] = new_id
        target["legacy_concept_id"] = str(old_id)
        target["prerequisites"] = [
            id_map.get(str(prerequisite), f"legacy:math-study:{prerequisite}")
            for prerequisite in value.get("prerequisites", [])
        ]
        target["source_refs"] = normalize_source_refs(value.get("source_refs", []))
        learning_targets.append(dict(target))

    migrated_syllabus = {
        key: value
        for key, value in old_syllabus.items()
        if key not in {"concepts", "targets", "learning_targets"}
    }
    migrated_syllabus["schema_version"] = 2
    migrated_syllabus["learning_targets"] = learning_targets
    migrated_syllabus["target_aliases"] = id_map
    migrated_syllabus["legacy_metadata"] = {
        "source_schema_version": old_syllabus.get("schema_version", 1),
        "source_kind": "math-study",
    }

    old_events = _read_jsonl(source / "observations.jsonl")
    migrated_events: list[dict[str, Any]] = []
    for old_event in old_events:
        # Build the v2 event from an explicit compatibility allowlist. Legacy
        # records may contain implementation-specific fields (for example a
        # "timestamp" alias); carrying those through would make the resulting
        # strict v2 event invalid. Required historical values are retained,
        # while unknown legacy extensions are intentionally not promoted into
        # canonical learner evidence.
        event = {
            key: old_event[key]
            for key in (
                "observation_id",
                "recorded_at",
                "session_id",
                "expected_seconds",
                "elapsed_seconds",
                "task_id",
                "task_type",
                "outcome",
                "assistance",
                "error_tags",
                "diagnostic_confidence",
                "learner_self_confidence",
                "learner_explanation",
                "source_refs",
                "assessment_id",
                "assessment_spec_id",
                "activity_id",
                "explicit_exposure_reason",
                "solution_exposed",
                "exposure_metadata",
                "evidence_facets",
                "evaluation_context",
                "assessment_result",
                "evaluation_metadata",
                "legacy_schema_version",
            )
            if key in old_event
        }
        event["legacy_schema_version"] = event.get("schema_version", 1)
        event["schema_version"] = 2
        old_target = old_event.get("target_id", old_event.get("concept_id"))
        if old_target is not None:
            old_target = str(old_target)
            new_target = id_map.get(old_target, f"legacy:math-study:{old_target}")
            event["target_id"] = new_target
            event["legacy_concept_id"] = old_target
        else:
            event["target_id"] = "legacy:math-study:unassigned"
            event["legacy_concept_id"] = None
        event.pop("concept_id", None)
        event.setdefault("capability_id", event.get("task_type", "legacy_unclassified"))
        event.setdefault("task_id", f"legacy-task:{event.get('observation_id', len(migrated_events))}")
        event["recorded_at"] = event.get("recorded_at", old_event.get("timestamp"))
        event["session_id"] = event.get("session_id")
        event["expected_seconds"] = event.get("expected_seconds")
        event["elapsed_seconds"] = event.get("elapsed_seconds")
        event["source_refs"] = normalize_source_refs(event.get("source_refs", []))
        for field in ("spec_hash", "assessment_spec_hash", "canonical_assessment_hash", "rubric"):
            event.pop(field, None)
        event["assessment_integrity"] = "legacy_unfrozen"
        migrated_events.append(event)

    course = dict(_read_json(source / "course.json", {}))
    course["schema_version"] = 2
    course.setdefault("course_id", "migrated-math-study")
    course.setdefault("title", "Migrated exam preparation")
    runtime_course = default_course()
    course.setdefault("exam", runtime_course["exam"])
    course.setdefault("time_budget", runtime_course["time_budget"])
    course.setdefault("source_policy", runtime_course["source_policy"])
    course.setdefault("scheduler", runtime_course["scheduler"])
    learner = dict(_read_json(source / "learner.json", {}))
    learner_defaults = default_learner(datetime.now(timezone.utc).isoformat())
    learner.setdefault("schema_version", learner_defaults["schema_version"])
    if not isinstance(learner.get("updated_at"), str):
        learner["updated_at"] = learner_defaults["updated_at"]
    preferences = dict(learner.get("preferences", learner_defaults["preferences"]))
    if "learning_style" in preferences:
        preferences["legacy_learning_style"] = preferences.pop("learning_style")
    learner["preferences"] = preferences
    learner.setdefault("stable_patterns", learner_defaults["stable_patterns"])
    session = dict(_read_json(source / "session.json", {}))
    session_defaults = default_session()
    old_current_concept = session.pop("current_concept", None)
    if session.get("current_target_id") is None and old_current_concept is not None:
        session["current_target_id"] = id_map.get(
            str(old_current_concept), f"legacy:math-study:{old_current_concept}"
        )
        session["legacy_current_concept"] = str(old_current_concept)
    session.setdefault("schema_version", session_defaults["schema_version"])
    if not isinstance(session.get("session_id"), str):
        session["session_id"] = ""
    if session.get("phase") not in {"idle", "study", "exam"}:
        session["phase"] = session_defaults["phase"]
    if not isinstance(session.get("pending_action"), str):
        session["pending_action"] = session_defaults["pending_action"]
    session.setdefault("current_target_id", session_defaults["current_target_id"])
    session.setdefault("current_task", session_defaults["current_task"])
    if not isinstance(session.get("time_budget_minutes"), int) or session["time_budget_minutes"] < 0:
        session["time_budget_minutes"] = session_defaults["time_budget_minutes"]
    source_revision_metadata = _legacy_revision_metadata(source)

    staging_root = Path(tempfile.mkdtemp(prefix=".exam-prep-migration-", dir=workspace))
    try:
        flat_store = StudyStore.for_exam_prep(staging_root)
        flat_store.initialize()
        _write_json(flat_store.state_path / "course.json", course)
        _write_json(flat_store.state_path / "syllabus.json", migrated_syllabus)
        _write_json(flat_store.state_path / "learner.json", learner)
        _write_json(flat_store.state_path / "session.json", session)
        for event in migrated_events:
            flat_store._append_jsonl(flat_store.observations_path, event)
        for summary in _read_jsonl(source / "sessions.jsonl"):
            flat_store._append_jsonl(flat_store.sessions_log_path, summary)
        for evidence in _read_jsonl(source / "source_evidence.jsonl"):
            flat_store._append_jsonl(flat_store.source_evidence_path, evidence)

        derived = reduce_learning_state(
            course, migrated_syllabus, migrated_events, {"revision": 0}
        )
        reviews = build_review_queue(
            migrated_events,
            derived.get("targets", {}),
            course,
            datetime.now(timezone.utc),
            migrated_syllabus,
        )
        reviews["derived_from_revision"] = 1
        flat_store.commit_revision(
            derived, session, learner, reviews, course, migrated_syllabus
        )
        result = MigrationResult(
            migrated=True,
            source_root=str(source),
            destination_root=str(destination),
            id_map=id_map,
            observation_count=len(migrated_events),
            legacy_unfrozen_count=len(migrated_events),
            source_fingerprint=source_fingerprint,
        )
        _write_json(
            flat_store.state_path / "migration.json",
            {
                "schema_version": 1,
                "mode": "from-math-study",
                "source_revision_metadata": source_revision_metadata,
                **result.to_mapping(),
            },
        )
        os.replace(flat_store.state_path, destination)
    except Exception:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise
    else:
        shutil.rmtree(staging_root, ignore_errors=True)
    return result

