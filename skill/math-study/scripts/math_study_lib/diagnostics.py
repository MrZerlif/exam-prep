"""Deep, best-effort diagnostics for the `validate` command.

Every check is isolated: one failing check reports itself as an error/warning
row and the rest still run, so a single corrupt file yields a useful report
instead of a stack trace. This is a diagnostic tool, not a gate - it never
raises for data problems it can describe.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .schema_validation import load_schema, validate_document
from .storage import StudyStore


def _check(name: str, fn: Callable[[], tuple[str, str] | None], path: str | None = None) -> dict[str, Any]:
    """Run one check. fn returns (status, detail) for warning/error, or None
    for ok. Any exception is captured as an error row, never propagated -
    this is what makes `validate` safe to run against a broken workspace:
    one bad file yields one error row, not a crash that stops every other
    check from running."""
    try:
        result = fn()
    except Exception as exc:  # noqa: BLE001 - diagnostics must not crash on bad data
        row = {"name": name, "status": "error", "detail": f"check raised {exc!r}"}
    else:
        if result is None:
            row = {"name": name, "status": "ok", "detail": None}
        else:
            status, detail = result
            row = {"name": name, "status": status, "detail": detail}
    if path is not None:
        row["path"] = path
    return row


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _safe_read_canonical_json(path: Path) -> tuple[dict[str, Any], str | None]:
    """Read+parse a canonical JSON file defensively. Returns (document,
    issue) - document is {} and issue is a short category+message string
    when the file is missing, unreadable, not valid JSON, or not an object.
    Never raises: this is exactly the file that might be corrupt, and
    `validate` must still produce a report when it is."""
    if not path.exists():
        return {}, None  # legitimately absent pre-init; not itself an error
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {}, f"unreadable_file: {exc}"
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return {}, f"invalid_json: {exc}"
    if not isinstance(data, dict):
        return {}, f"invalid_json: expected a JSON object, got {type(data).__name__}"
    return data, None


def run_validation(store: StudyStore) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, fn: Callable[[], tuple[str, str] | None], path: str | None = None) -> None:
        checks.append(_check(name, fn, path))

    # --- canonical inputs -------------------------------------------------
    # Read course.json/syllabus.json ourselves, defensively: `validate` must
    # keep working (and keep checking everything else) even when one of
    # these is corrupt, which is precisely the scenario it exists to catch.
    course_path = store.state_path / "course.json"
    syllabus_path = store.state_path / "syllabus.json"
    course, course_issue = _safe_read_canonical_json(course_path)
    syllabus, syllabus_issue = _safe_read_canonical_json(syllabus_path)

    def check_course_readable():
        if course_issue:
            return "error", course_issue
        return None

    add("course_json_readable", check_course_readable, path=str(course_path))

    def check_syllabus_readable():
        if syllabus_issue:
            return "error", syllabus_issue
        return None

    add("syllabus_json_readable", check_syllabus_readable, path=str(syllabus_path))

    def check_course_schema():
        if course_issue:
            return "warning", "skipped: course.json could not be parsed"
        validate_document(course, load_schema("course.schema.json"))
        return None

    add("course_schema", check_course_schema, path=str(course_path))

    def check_syllabus_schema():
        if syllabus_issue:
            return "warning", "skipped: syllabus.json could not be parsed"
        validate_document(syllabus, load_schema("syllabus.schema.json"))
        return None

    add("syllabus_schema", check_syllabus_schema, path=str(syllabus_path))

    def check_schema_versions():
        bad = [
            name
            for name, doc in (("course", course), ("syllabus", syllabus))
            if doc.get("schema_version") != 1
        ]
        if bad:
            return "error", f"unexpected schema_version in: {', '.join(bad)}"
        return None

    add("schema_versions", check_schema_versions)

    def check_source_refs():
        missing = [
            concept_id
            for concept_id, metadata in syllabus.get("concepts", {}).items()
            if not metadata.get("source_refs")
        ]
        if missing:
            return "warning", f"concepts without source_refs: {', '.join(sorted(missing))}"
        return None

    add("syllabus_source_refs", check_source_refs)

    # --- observation log ----------------------------------------------------
    events: list[dict[str, Any]] = []

    def check_observations_readable():
        nonlocal events
        events = store.read_complete_observations()
        diagnostics = store.read_log_diagnostics()
        if diagnostics.get("partial_final_line"):
            return "warning", "observations.jsonl has a torn final line (ignored, likely a mid-write crash)"
        return None

    add("observations_jsonl_readable", check_observations_readable, path=str(store.observations_path))

    def check_sessions_log_readable():
        store.read_session_summaries()
        diagnostics = store.read_log_diagnostics()
        if diagnostics.get("sessions_log_partial_final_line"):
            return "warning", "sessions.jsonl has a torn final line (ignored, likely a mid-write crash)"
        return None

    add("sessions_jsonl_readable", check_sessions_log_readable)

    def check_observation_id_uniqueness():
        seen: dict[str, dict[str, Any]] = {}
        duplicates: list[str] = []
        conflicts: list[str] = []
        for event in events:
            observation_id = event.get("observation_id")
            if observation_id is None:
                continue
            if observation_id in seen:
                duplicates.append(observation_id)
                if seen[observation_id] != event:
                    conflicts.append(observation_id)
            else:
                seen[observation_id] = event
        if conflicts:
            return "error", f"observation_id present with divergent payloads: {', '.join(sorted(set(conflicts)))}"
        if duplicates:
            return "warning", f"observation_id repeated (identical payload) in log: {', '.join(sorted(set(duplicates)))}"
        return None

    add("observation_id_uniqueness", check_observation_id_uniqueness)

    def check_observation_concept_refs():
        known = set(syllabus.get("concepts", {}).keys())
        orphaned = sorted({event.get("concept_id") for event in events if event.get("concept_id") not in known})
        if orphaned:
            return "warning", f"observations reference concept_ids not in the current syllabus: {', '.join(orphaned)}"
        return None

    add("observation_concept_ids_known", check_observation_concept_refs)

    # --- revisions, manifests, hashes, current pointer ----------------------
    def check_current_pointer():
        if not store.current_path.exists():
            return "warning", "current.json is missing (no committed revision yet)"
        try:
            pointer = json.loads(store.current_path.read_text(encoding="utf-8"))
            int(pointer["revision"])
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return "warning", f"current.json is corrupt, recovery will scan revisions/ instead: {exc}"
        return None

    add("current_pointer", check_current_pointer, path=str(store.current_path))

    def check_revisions():
        if not store.revisions_path.exists():
            return "warning", "no revisions/ directory yet"
        revision_dirs = sorted(p for p in store.revisions_path.iterdir() if p.is_dir() and p.name.isdigit())
        if not revision_dirs:
            return "warning", "no committed revisions yet"
        broken: list[str] = []
        for revision_dir in revision_dirs:
            manifest_path = revision_dir / "manifest.json"
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                for filename, expected_hash in manifest["derived_hashes"].items():
                    actual = StudyStore._hash_file(revision_dir / filename)
                    if actual != expected_hash:
                        raise ValueError(f"hash mismatch for {filename}")
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                broken.append(f"{revision_dir.name} ({exc})")
        if broken:
            return "warning", (
                "revisions failing manifest/hash validation (recovery will fall back past "
                f"these): {', '.join(broken)}"
            )
        return None

    add("revision_manifests_and_hashes", check_revisions, path=str(store.revisions_path))

    def check_derived_revision_consistency():
        try:
            recovered = store.recover()
        except FileNotFoundError:
            return "warning", "no valid revision to check derived-state consistency against"
        applied_line = recovered.manifest.data.get("last_complete_observation_line", 0)
        applied_id = recovered.manifest.data.get("last_complete_observation_id")
        current_id = events[-1]["observation_id"] if events else None
        if applied_line != len(events) or applied_id != current_id:
            return "warning", (
                "the latest recovered revision is behind observations.jsonl; the next normal "
                "command will replay and re-commit automatically"
            )
        return None

    add("derived_revision_matches_log", check_derived_revision_consistency)

    # --- session lifecycle ---------------------------------------------------
    def check_session_lifecycle():
        try:
            recovered = store.recover()
        except FileNotFoundError:
            return None
        session = recovered.session
        phase = session.get("phase")
        if phase not in ("idle", "study", "exam"):
            return "error", f"session.phase has an unrecognized value: {phase!r}"
        if phase in ("study", "exam") and not session.get("session_id"):
            return "error", "session is active (phase=%r) but session_id is empty" % phase
        return None

    add("session_lifecycle", check_session_lifecycle)

    # --- review queue ----------------------------------------------------
    def check_review_queue_timestamps():
        try:
            recovered = store.recover()
        except FileNotFoundError:
            return None
        items = (recovered.review_queue or {}).get("items", {})
        exam_raw = course.get("exam", {}).get("date")
        exam_at = None
        if exam_raw:
            try:
                exam_at = _parse_iso(exam_raw)
            except ValueError:
                pass
        bad: list[str] = []
        for concept_id, item in items.items():
            due_raw = item.get("due_at")
            last_raw = item.get("last_review_at")
            try:
                due_at = _parse_iso(due_raw) if due_raw else None
                last_at = _parse_iso(last_raw) if last_raw else None
            except ValueError:
                bad.append(f"{concept_id} (unparseable timestamp)")
                continue
            if due_at and last_at and due_at < last_at:
                bad.append(f"{concept_id} (due_at before last_review_at)")
            if due_at and exam_at and exam_at.tzinfo and due_at.tzinfo and exam_at > datetime.now(exam_at.tzinfo) and due_at > exam_at:
                bad.append(f"{concept_id} (due_at scheduled after the exam)")
        if bad:
            return "error", f"review_queue timestamp problems: {', '.join(bad)}"
        return None

    add("review_queue_timestamps", check_review_queue_timestamps)

    errors = [c for c in checks if c["status"] == "error"]
    warnings = [c for c in checks if c["status"] == "warning"]
    return {
        "status": "valid" if not errors else "issues_found",
        "valid": not errors,
        "checks": checks,
        "error_count": len(errors),
        "warning_count": len(warnings),
    }
