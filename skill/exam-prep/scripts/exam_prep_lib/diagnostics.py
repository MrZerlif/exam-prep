"""Deep, best-effort diagnostics for the `validate` command.

Every check is isolated: one failing check reports itself as an error/warning
row and the rest still run, so a single corrupt file yields a useful report
instead of a stack trace. This is a diagnostic tool, not a gate - it never
raises for data problems it can describe.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .capabilities import capability_dimension_issues
from .schema_validation import (
    load_schema,
    validate_document,
    validate_observation_event,
    validate_state_bundle,
)
from .storage import StudyStore
from .target_normalization import normalize_event, normalize_syllabus
from .assessment import FrozenAssessment
from .provenance import source_ref_from_mapping
from .scheduler import _exam_time


def blueprint_revision_diagnostics(
    course: dict[str, Any], events: Iterable[dict[str, Any]]
) -> dict[str, Any] | None:
    """Compare the course's current exam blueprint against what each v2
    observation event was tagged with when recorded (see
    StudyStore.append_observation). Evidence is never discarded or
    reinterpreted when the blueprint changes mid-prep - this only makes the
    mismatch visible instead of silent, per invariant 3.

    Keys on exam_hash (a content hash of the whole exam sub-object), not
    only the manually-maintained exam_revision integer (1.4): revision is a
    human label an author can forget to bump, and a forgotten bump must not
    silently defeat this diagnostic - a hash comparison can't be forgotten.
    An event is flagged as stale if either its recorded exam_revision or its
    recorded exam_hash disagrees with the current one; either signal alone
    is enough (an old event may only have the pre-1.4 exam_revision tag).
    Returns None when nothing is flagged (including no events tagged at
    all: legacy/v1 evidence, or a course with no explicit exam.revision)."""

    exam = course.get("exam") or {}
    current_revision = exam.get("revision")
    if current_revision is None:
        return None
    current_hash = StudyStore.hash_document(exam)
    stale_counts: dict[tuple[int | None, str | None], int] = {}
    for event in events:
        recorded_revision = event.get("exam_revision")
        recorded_hash = event.get("exam_hash")
        if recorded_revision is None and recorded_hash is None:
            continue
        revision_stale = recorded_revision is not None and recorded_revision != current_revision
        hash_stale = recorded_hash is not None and recorded_hash != current_hash
        if not (revision_stale or hash_stale):
            continue
        key = (recorded_revision, recorded_hash)
        stale_counts[key] = stale_counts.get(key, 0) + 1
    if not stale_counts:
        return None
    return {
        "current_exam_revision": current_revision,
        "current_exam_hash": current_hash,
        "stale_revisions": [
            {"exam_revision": revision, "exam_hash": exam_hash, "observation_count": count}
            for (revision, exam_hash), count in sorted(
                stale_counts.items(), key=lambda item: (item[0][0] is None, item[0][0] or 0, item[0][1] or "")
            )
        ],
    }


def _mock_tickets_by_target(
    session: Mapping[str, Any], assessments: Iterable[Mapping[str, Any]]
) -> dict[str, list[str]]:
    """The tickets this exam session handed out, grouped by target_id."""

    handed_out = list(session.get("mock_assessment_ids") or [])
    if not handed_out:
        return {}
    wanted = set(handed_out)
    by_target: dict[str, list[str]] = {}
    for item in assessments:
        assessment_id = item.get("assessment_id")
        target_id = item.get("target_id")
        if assessment_id not in wanted or not target_id:
            continue
        by_target.setdefault(target_id, []).append(assessment_id)
    for assessment_ids in by_target.values():
        assessment_ids.sort(key=handed_out.index)
    return by_target


def unlinked_exam_attempt_diagnostic(
    proposal: Mapping[str, Any],
    session: Mapping[str, Any],
    assessments: Iterable[Mapping[str, Any]],
    prior_events: Iterable[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Flag an exam-phase observation that answers a target this session has
    a ticket for but carries no assessment_id, so it binds to no ticket.

    Only assessment_id binds an attempt to a FrozenAssessment (see
    StudyStore.append_observation); without it the event is recorded as
    ordinary evidence with assessment_integrity 'not_assessment' and
    end-session's post-mortem leaves the ticket attempted: false. That is
    correct engine behavior, but silent - and silent at the worst moment,
    since the cost only becomes visible when the mock is already over and
    the attempt cannot be re-linked. Per invariant 3 this makes the gap
    speak at the point the next attempt can still be recorded correctly.

    Diagnostic only: the caller records the observation either way. Losing
    evidence to enforce a link would be worse than an unlinked attempt.

    Returns None outside an exam phase, for an already-linked proposal, and
    when every ticket for that target is already linked to an attempt - in
    that last case there is nothing left to link and naming a ticket would
    be advice to double-record. A tutor recording a genuine side observation
    mid-exam on a ticket's target is flagged too; that false positive costs
    one ignorable field, while the miss it guards against costs the
    post-mortem."""

    if proposal.get("assessment_id") is not None:
        return None
    if session.get("phase") != "exam":
        return None
    target_id = proposal.get("target_id", proposal.get("concept_id"))
    if not target_id:
        return None
    candidates = _mock_tickets_by_target(session, assessments).get(target_id)
    if not candidates:
        return None
    already_linked = {
        event.get("assessment_id")
        for event in prior_events
        if event.get("session_id") == session.get("session_id")
        and event.get("assessment_id")
    }
    unlinked = [
        assessment_id for assessment_id in candidates if assessment_id not in already_linked
    ]
    if not unlinked:
        return None
    return {
        "code": "exam_attempt_not_linked_to_ticket",
        "target_id": target_id,
        "observation_id": proposal.get("observation_id"),
        "candidate_assessment_ids": unlinked,
        "detail": (
            f"recorded during an exam on target {target_id!r} with no assessment_id, "
            f"so it is linked to no ticket and will not appear in the post-mortem; "
            f"tickets still unlinked for this target: {', '.join(unlinked)}"
        ),
    }


def unlinked_exam_attempts(
    session: Mapping[str, Any],
    assessments: Iterable[Mapping[str, Any]],
    session_events: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """end-session's closing summary of attempts that answered a ticket's
    target without binding to a ticket - the same gap
    unlinked_exam_attempt_diagnostic reports per attempt, totalled once the
    mock is over. Secondary to that per-attempt signal: by this point the
    mock cannot be re-answered, so this explains an empty post-mortem rather
    than preventing one."""

    targets = _mock_tickets_by_target(session, assessments)
    if not targets:
        return []
    started_at = session.get("mock_started_at")
    return [
        {
            "observation_id": event.get("observation_id"),
            "target_id": event.get("target_id", event.get("concept_id")),
            "outcome": event.get("outcome"),
        }
        for event in session_events
        if not event.get("assessment_id")
        and event.get("target_id", event.get("concept_id")) in targets
        and not (
            started_at
            and event.get("recorded_at")
            and event["recorded_at"] < started_at
        )
    ]


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
        return {}, "missing_file"
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
    if (
        course_issue == "missing_file"
        and syllabus_issue == "missing_file"
        and store.initialization_state()[0] == "uninitialized"
    ):
        return {
            "status": "issues_found",
            "valid": False,
            "checks": [{
                "name": "workspace_initialized",
                "status": "error",
                "detail": "course.json and syllabus.json are missing; run init",
            }],
            "error_count": 1,
            "warning_count": 0,
        }

    def check_course_readable():
        if course_issue == "missing_file":
            return "error", "missing_file: restore course.json to repair the incomplete workspace"
        if course_issue:
            return "error", course_issue
        return None

    add("course_json_readable", check_course_readable, path=str(course_path))

    def check_syllabus_readable():
        if syllabus_issue == "missing_file":
            return "error", "missing_file: restore syllabus.json to repair the incomplete workspace"
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
        if syllabus.get("schema_version") == 2:
            target_schema = load_schema("learning-target.schema.json")
            for index, target in enumerate(syllabus.get("learning_targets", [])):
                validate_document(target, target_schema, f"$.learning_targets[{index}]")
        return None

    add("syllabus_schema", check_syllabus_schema, path=str(syllabus_path))

    def check_capability_dimensions():
        issues = capability_dimension_issues(syllabus)
        if issues:
            return "error", "; ".join(issues)
        return None

    add("capability_dimensions", check_capability_dimensions)
    def check_exam_datetime():
        if course_issue:
            return "warning", "skipped: course.json could not be parsed"
        _exam_time(course, datetime.now(timezone.utc))
        return None

    add("exam_datetime", check_exam_datetime)

    def check_schema_versions():
        bad = [
            name
            for name, doc, issue in (
                ("course", course, course_issue),
                ("syllabus", syllabus, syllabus_issue),
            )
            if issue is None and doc.get("schema_version") not in (1, 2)
        ]
        if bad:
            return "error", f"unexpected schema_version in: {', '.join(bad)}"
        return None

    add("schema_versions", check_schema_versions)

    def check_source_refs():
        missing = [
            concept_id
            for concept_id, metadata in normalize_syllabus(syllabus).targets.items()
            if not metadata.get("source_refs")
        ]
        if missing:
            return "warning", f"learning targets without source_refs: {', '.join(sorted(missing))}"
        return None

    add("syllabus_source_refs", check_source_refs)

    # --- observation log ----------------------------------------------------
    events: list[dict[str, Any]] = []

    def check_observations_readable():
        nonlocal events
        events = store.read_complete_observations()
        for event in events:
            validate_observation_event(event)
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
        normalized_syllabus = normalize_syllabus(syllabus)
        normalized_events = [normalize_event(event, normalized_syllabus) for event in events]
        known = set(normalized_syllabus.targets)
        orphaned = sorted(
            {
                event.get("target_id")
                for event in normalized_events
                if event.get("target_id") not in known
            }
        )
        if orphaned:
            return "warning", f"observations reference target_ids not in the current syllabus: {', '.join(orphaned)}"
        return None

    add("observation_concept_ids_known", check_observation_concept_refs)
    add("observation_target_ids_known", check_observation_concept_refs)

    def check_blueprint_revision():
        if course_issue:
            return "warning", "skipped: course.json could not be parsed"
        diagnostic = blueprint_revision_diagnostics(course, events)
        if diagnostic is None:
            return None
        stale = ", ".join(
            f"{item['observation_count']} at revision {item['exam_revision']}"
            for item in diagnostic["stale_revisions"]
        )
        return (
            "warning",
            f"evidence recorded under a prior exam blueprint revision ({stale}); "
            f"current exam.revision is {diagnostic['current_exam_revision']} - readiness "
            "still includes this evidence",
        )

    add("blueprint_revision_consistency", check_blueprint_revision)

    # --- assessments and source evidence -----------------------------------
    assessments: list[dict[str, Any]] = []

    def check_assessments_readable():
        nonlocal assessments
        assessments = store.read_assessments()
        for item in assessments:
            frozen = FrozenAssessment.from_mapping(item)
            validate_document(frozen.to_mapping(), load_schema("assessment.schema.json"))
        return None

    add("assessments_jsonl_readable", check_assessments_readable, path=str(store.assessments_path))

    source_evidence: list[dict[str, Any]] = []

    def check_source_evidence_readable():
        nonlocal source_evidence
        source_evidence = store.read_source_evidence()
        for item in source_evidence:
            ref = item.get("source_ref")
            if isinstance(ref, dict):
                source_ref_from_mapping(ref)
        return None

    add("source_evidence_jsonl_readable", check_source_evidence_readable, path=str(store.source_evidence_path))

    def check_source_manifest():
        paths = [store.source_manifest_path]
        for manifest_path in paths:
            if not manifest_path.exists():
                continue
            manifest, issue = _safe_read_canonical_json(manifest_path)
            if issue:
                return "error", f"{manifest_path.name}: {issue}"
            if not isinstance(manifest.get("sources", []), list):
                return "error", f"{manifest_path.name} sources must be an array"
            for index, source in enumerate(manifest["sources"]):
                if not isinstance(source, dict):
                    return "error", f"{manifest_path.name} source {index} must be an object"
                source_ref_from_mapping(source)
        return None

    add("source_manifest", check_source_manifest, path=str(store.source_manifest_path))

    # --- revisions, manifests, hashes, current pointer ----------------------
    def check_current_pointer():
        if not store.current_path.exists():
            return "warning", "current.json is missing (no committed revision yet)"
        try:
            pointer = json.loads(store.current_path.read_text(encoding="utf-8"))
            validate_document(pointer, load_schema("current.schema.json"))
            int(pointer["revision"])
            if not (store.revisions_path / f"{int(pointer['revision']):06d}").is_dir():
                return "warning", "current.json points to a revision directory that is missing"
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
                validate_document(
                    manifest,
                    load_schema("revision-manifest.schema.json"),
                )
                if int(manifest["revision"]) != int(revision_dir.name):
                    raise ValueError("revision number does not match its directory")
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

    def check_canonical_input_fingerprints():
        try:
            recovered = store.recover()
        except FileNotFoundError:
            return None
        expected = recovered.manifest.data.get("canonical_inputs")
        if not isinstance(expected, dict):
            return None
        current = store.canonical_input_fingerprints(course, syllabus)
        mismatched = [
            key
            for key in (
                "course_hash",
                "syllabus_hash",
                "observations_hash",
                "assessments_hash",
                "source_evidence_hash",
                "source_manifest_hash",
                "sessions_hash",
            )
            if expected.get(key) != current.get(key)
        ]
        if mismatched:
            return "warning", "canonical inputs changed since the latest revision: " + ", ".join(mismatched)
        return None

    add("canonical_input_fingerprints", check_canonical_input_fingerprints)

    def check_derived_snapshot():
        try:
            recovered = store.recover()
        except FileNotFoundError:
            return None
        validate_state_bundle(recovered.derived)
        return None

    add("derived_target_snapshot", check_derived_snapshot)

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

    def check_learner_snapshot():
        try:
            recovered = store.recover()
        except FileNotFoundError:
            return None
        validate_document(recovered.learner, load_schema("learner.schema.json"))
        return None

    add("learner_snapshot", check_learner_snapshot)

    def check_closed_session_summaries():
        for summary in store.read_session_summaries():
            if not summary.get("session_id"):
                return "error", "closed session summary has no session_id"
        return None

    add("closed_session_summaries", check_closed_session_summaries)

    def check_migration_metadata():
        path = store.state_path / "migration.json"
        if not path.exists():
            return None
        marker, issue = _safe_read_canonical_json(path)
        if issue:
            return "error", issue
        if marker.get("mode") != "from-math-study":
            return "error", "migration.json has an invalid mode"
        if not marker.get("source_fingerprint"):
            return "error", "migration.json has no source_fingerprint"
        return None

    add("migration_metadata", check_migration_metadata, path=str(store.state_path / "migration.json"))

    # --- review queue ----------------------------------------------------
    def check_review_queue_timestamps():
        try:
            recovered = store.recover()
        except FileNotFoundError:
            return None
        items = (recovered.review_queue or {}).get("items", {})
        validation_now = datetime.now(timezone.utc)
        try:
            exam_at = _exam_time(course, validation_now)
        except (TypeError, ValueError):
            # The named exam_datetime check reports the actionable error.
            exam_at = None
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
            if due_at and exam_at and exam_at.tzinfo and due_at.tzinfo and exam_at > validation_now and due_at > exam_at:
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

