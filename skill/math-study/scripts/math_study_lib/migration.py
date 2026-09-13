"""Explicit, non-destructive migration from the math-study v1 runtime."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .provenance import normalize_source_refs
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

    def to_mapping(self) -> dict[str, Any]:
        return {
            "migrated": self.migrated,
            "source_root": self.source_root,
            "destination_root": self.destination_root,
            "id_map": self.id_map,
            "observation_count": self.observation_count,
            "legacy_unfrozen_count": self.legacy_unfrozen_count,
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


def migrate_legacy_workspace(legacy_workspace: str | Path) -> MigrationResult:
    """Convert old state into .exam-prep without mutating the source tree."""

    workspace = _legacy_workspace(Path(legacy_workspace))
    source = workspace / "state"
    if not source.exists():
        raise MigrationError(f"legacy state directory does not exist: {source}")
    destination = workspace / ".exam-prep"
    marker = destination / "migration.json"
    if marker.exists():
        existing = _read_json(marker, {})
        return MigrationResult(
            migrated=False,
            source_root=str(source),
            destination_root=str(destination),
            id_map=dict(existing.get("id_map", {})),
            observation_count=int(existing.get("observation_count", 0)),
            legacy_unfrozen_count=int(existing.get("legacy_unfrozen_count", 0)),
        )

    old_syllabus = _read_json(source / "syllabus.json", {"concepts": {}})
    old_concepts = old_syllabus.get("concepts", {})
    if not isinstance(old_concepts, dict):
        raise MigrationError("legacy syllabus.concepts must be an object")
    id_map = {
        str(old_id): f"legacy:math-study:{old_id}"
        for old_id in old_concepts
    }
    new_concepts: dict[str, dict[str, Any]] = {}
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
        new_concepts[new_id] = target
        learning_targets.append(dict(target))

    migrated_syllabus = dict(old_syllabus)
    migrated_syllabus["schema_version"] = 2
    migrated_syllabus["concepts"] = new_concepts
    migrated_syllabus["learning_targets"] = learning_targets
    migrated_syllabus["target_aliases"] = id_map

    old_events = _read_jsonl(source / "observations.jsonl")
    migrated_events: list[dict[str, Any]] = []
    for old_event in old_events:
        event = dict(old_event)
        old_target = event.get("target_id", event.get("concept_id"))
        if old_target is not None:
            old_target = str(old_target)
            new_target = id_map.get(old_target, f"legacy:math-study:{old_target}")
            event["target_id"] = new_target
            event["concept_id"] = new_target
            event["legacy_concept_id"] = old_target
        event["source_refs"] = normalize_source_refs(event.get("source_refs", []))
        event.pop("spec_hash", None)
        event.pop("rubric", None)
        event["assessment_integrity"] = "legacy_unfrozen"
        migrated_events.append(event)

    flat_store = StudyStore.for_exam_prep(workspace)
    flat_store.initialize()
    _write_json(
        flat_store.state_path / "course.json",
        {**_read_json(source / "course.json", {}), "schema_version": 2},
    )
    _write_json(flat_store.state_path / "syllabus.json", migrated_syllabus)
    _write_json(flat_store.state_path / "learner.json", _read_json(source / "learner.json", {}))
    _write_json(flat_store.state_path / "session.json", _read_json(source / "session.json", {}))
    _write_json(
        flat_store.state_path / "targets.json",
        {
            "schema_version": 2,
            "targets": new_concepts,
            "aliases": id_map,
        },
    )
    for event in migrated_events:
        flat_store._append_jsonl(flat_store.observations_path, event)
    for summary in _read_jsonl(source / "sessions.jsonl"):
        flat_store._append_jsonl(flat_store.sessions_log_path, summary)

    result = MigrationResult(
        migrated=True,
        source_root=str(source),
        destination_root=str(destination),
        id_map=id_map,
        observation_count=len(migrated_events),
        legacy_unfrozen_count=len(migrated_events),
    )
    _write_json(
        marker,
        {
            "schema_version": 1,
            "mode": "from-math-study",
            **result.to_mapping(),
        },
    )
    return result
