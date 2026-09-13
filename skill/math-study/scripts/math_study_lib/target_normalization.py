"""Compatibility normalization from concept-oriented v1 data to targets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass
class NormalizedSyllabus:
    schema_version: int
    targets: dict[str, dict[str, Any]]
    aliases: dict[str, str]
    capabilities: dict[str, Any]


def _as_target_items(raw: Any) -> list[tuple[str | None, Mapping[str, Any]]]:
    if isinstance(raw, Mapping):
        return [
            (str(key), value if isinstance(value, Mapping) else {})
            for key, value in raw.items()
        ]
    if isinstance(raw, list):
        return [
            (
                str(item.get("target_id") or item.get("id"))
                if isinstance(item, Mapping) and (item.get("target_id") or item.get("id"))
                else None,
                item if isinstance(item, Mapping) else {},
            )
            for item in raw
        ]
    return []


def normalize_syllabus(syllabus: Mapping[str, Any]) -> NormalizedSyllabus:
    """Normalize v1 concepts or v2 target collections without losing IDs."""

    raw_collection = syllabus.get("learning_targets")
    if raw_collection is None:
        raw_collection = syllabus.get("targets")
    if raw_collection is None:
        raw_collection = syllabus.get("concepts", {})

    targets: dict[str, dict[str, Any]] = {}
    aliases: dict[str, str] = {}
    for item_key, raw_item in _as_target_items(raw_collection):
        target_id = str(raw_item.get("target_id") or raw_item.get("id") or item_key or "")
        if not target_id:
            continue
        target = dict(raw_item)
        target.pop("id", None)
        target["target_id"] = target_id
        prerequisites = target.get("prerequisites")
        if prerequisites is None:
            prerequisites = target.get("prerequisite_target_ids", [])
        target["prerequisites"] = [str(value) for value in prerequisites]
        targets[target_id] = target
        if item_key:
            aliases[str(item_key)] = target_id
        aliases[target_id] = target_id
        for alias in target.get("aliases", []):
            aliases[str(alias)] = target_id

    for target in targets.values():
        target["prerequisites"] = [
            aliases.get(prerequisite, prerequisite)
            for prerequisite in target.get("prerequisites", [])
        ]

    capabilities = syllabus.get("assessment_capabilities", syllabus.get("capabilities", {}))
    if not isinstance(capabilities, Mapping):
        capabilities = {}
    return NormalizedSyllabus(
        schema_version=int(syllabus.get("schema_version", 1)),
        targets=targets,
        aliases=aliases,
        capabilities=dict(capabilities),
    )


def normalize_event(
    event: Mapping[str, Any], syllabus: NormalizedSyllabus
) -> dict[str, Any]:
    """Return an event using target_id while retaining diagnostic context."""

    normalized = dict(event)
    raw_target_id = normalized.pop("target_id", None)
    legacy_target_id = normalized.pop("concept_id", None)
    selected = raw_target_id if raw_target_id is not None else legacy_target_id
    target_id = str(selected) if selected is not None else ""
    canonical_target_id = syllabus.aliases.get(target_id, target_id)
    normalized["target_id"] = canonical_target_id
    if legacy_target_id is not None and str(legacy_target_id) != canonical_target_id:
        normalized["legacy_concept_id"] = str(legacy_target_id)

    diagnostics = list(normalized.get("diagnostics", []))
    if canonical_target_id not in syllabus.targets:
        if "unknown_target_id" not in diagnostics:
            diagnostics.append("unknown_target_id")
    if diagnostics:
        normalized["diagnostics"] = diagnostics
    else:
        normalized.pop("diagnostics", None)
    return normalized
