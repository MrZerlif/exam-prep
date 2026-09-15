"""Unified command-line entry point for the exam-prep skill."""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from exam_prep_lib.capabilities import CapabilityRegistry, capability_dimension_issues
from exam_prep_lib.defaults import default_course, default_learner, default_session, default_syllabus
from exam_prep_lib.diagnostics import blueprint_revision_diagnostics, run_validation
from exam_prep_lib.reducer import MISTAKE_SUMMARIES, derive_assistance_band, reduce_learning_state
from exam_prep_lib.migration import migrate_legacy_workspace
from exam_prep_lib.curriculum import (
    CurriculumValidationError,
    apply_curriculum_proposal,
    validate_curriculum_proposal,
)
from exam_prep_lib.assessment import FrozenAssessment
from exam_prep_lib.scheduler import (
    build_review_queue,
    compute_priority,
    select_next_activity,
)
from exam_prep_lib.schema_validation import (
    SchemaError,
    load_schema,
    validate_document,
)
from exam_prep_lib.source_evidence import ingest_source_evidence
from exam_prep_lib.storage import StudyStore
from exam_prep_lib.target_normalization import normalize_syllabus
from exam_prep_lib.verifier_registry import VerifierRegistry, verify_request
from exam_prep_lib.workspace import discover_git_root, resolve_workspace

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


class LegacyStateDetected(ValueError):
    """A legacy state tree needs an explicit migration before target runtime use."""


LEGACY_STATE_MARKERS = (
    "course.json",
    "syllabus.json",
    "observations.jsonl",
    "concepts.json",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _reduction_policy(course: dict, revision: int) -> dict:
    return {
        "revision": revision,
        "recurring_mistake": course.get("scheduler", {}).get("recurring_mistake_policy"),
    }


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(text, encoding="utf-8")
    os.replace(temp_path, path)


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _has_legacy_state(workspace: Path) -> bool:
    legacy_root = workspace / "state"
    return legacy_root.is_dir() and any(
        (legacy_root / marker).exists() for marker in LEGACY_STATE_MARKERS
    )


def _derived_items(derived: dict[str, object]) -> dict:
    """Return target/concept state for internal reducer and scheduler callers."""

    items = derived.get("targets")
    if isinstance(items, dict):
        return items
    items = derived.get("concepts", {})
    return items if isinstance(items, dict) else {}


def _is_v2_syllabus(syllabus: dict) -> bool:
    return normalize_syllabus(syllabus).schema_version >= 2


def _public_derived(syllabus: dict, derived: dict) -> dict:
    """Expose canonical v2 state under targets while preserving v1 output."""

    if not _is_v2_syllabus(syllabus):
        return derived
    result = {key: value for key, value in derived.items() if key != "concepts"}
    result["schema_version"] = 2
    result["targets"] = _derived_items(derived)
    return result


def _public_activity(syllabus: dict, selected: dict) -> dict:
    if not _is_v2_syllabus(syllabus):
        return selected
    result = dict(selected)
    target_id = result.pop("concept_id", None)
    if target_id is not None:
        result["target_id"] = target_id
    return result


def _attempt_is_done(proposal: dict) -> bool:
    """An attempt closes out its task when it succeeded without help - the
    same 'independent' band the reducer uses to count independent_successes.
    Anything else (hinted, partial, incorrect, solution seen) still needs a
    clean independent pass, so the task stays open to resume."""

    if proposal.get("outcome") != "correct":
        return False
    assistance = proposal.get("assistance") or {}
    return derive_assistance_band(assistance) == "independent"


def _pending_action_for_attempt(target_id: str, proposal: dict, *, done: bool) -> str:
    """A short, specific resumption cue for the just-recorded attempt -
    what `status` (via `_resume_point`) surfaces after a break instead of a
    generic reminder to pick something to do. Once the task is done there is
    nothing left to resume on it, so this reverts to the same prompt used
    before anything was attempted."""

    if done:
        return "choose the next budget-fitting activity"
    outcome = proposal.get("outcome")
    if outcome == "correct":
        return f"continue {target_id} with an independent check"
    tags = proposal.get("error_tags") or []
    summaries = ", ".join(MISTAKE_SUMMARIES.get(tag, tag) for tag in tags)
    detail = f" ({summaries})" if summaries else ""
    return f"resume {target_id}: last attempt was {outcome}{detail}"


def _resume_point(syllabus: dict, derived: dict, session: dict) -> dict | None:
    """Structured break-state pointer for `status`: where the learner
    stopped and what the last attempt there was, so a host can answer
    'where was I?' with a specific place instead of a general summary. Null
    once the last attempt on current_task finished it cleanly (see
    _attempt_is_done) - a completed task is not a place to resume, and
    without this check a finished session would still be offered up as
    unfinished business after end-session no longer clears the pointer."""

    target_id = session.get("current_target_id")
    if not target_id or session.get("current_task_done"):
        return None
    metadata = normalize_syllabus(syllabus).targets.get(target_id, {})
    state = _derived_items(derived).get(target_id, {})
    tags = session.get("last_attempt_error_tags") or []
    return {
        "target_id": target_id,
        "target_title": metadata.get("title"),
        "task_id": session.get("current_task"),
        "last_attempt_outcome": session.get("last_attempt_outcome"),
        "last_attempt_error_tags": list(tags),
        "last_attempt_error_summaries": [MISTAKE_SUMMARIES.get(tag, tag) for tag in tags],
        "mastery_status": state.get("mastery_status"),
        "pending_action": session.get("pending_action"),
    }


def _store(workspace: str | None) -> StudyStore:
    resolved_workspace = resolve_workspace(
        workspace,
        git_root=discover_git_root(),
    )
    store = StudyStore.for_exam_prep(resolved_workspace)
    if not store.state_path.exists() and _has_legacy_state(resolved_workspace):
        raise LegacyStateDetected(
            f"legacy state detected at {resolved_workspace / 'state'}; "
            "run migrate --from-math-study explicitly before using exam-prep"
        )
    return store


def _initialization_state(store: StudyStore) -> tuple[str, list[str]]:
    return store.initialization_state()


def load_state(store: StudyStore) -> tuple[dict, dict, dict, dict, dict, dict]:
    """The single safe-loading path for every command that needs state.

    Canonical inputs (course/syllabus) are read directly - they are primary
    source of truth, not derived. Everything else (learner/session snapshot,
    derived concepts/review_queue) comes from the revision/recovery chain,
    never from the convenience JSON copies directly: those copies are
    write-only debugging aids and may be missing or corrupt without harming
    a normal command. If the recovered revision is behind the append-only
    observation log (a crash between append and commit, or a syllabus change
    that added/removed concepts), derived state is recomputed from the full
    log and a fresh revision is committed before returning - so a crashed
    observation is replayed exactly once, and callers never see stale data.
    """
    course = _read_json(store.state_path / "course.json", default_course())
    syllabus = _read_json(store.state_path / "syllabus.json", default_syllabus())
    events = store.read_complete_observations()
    current_id = events[-1]["observation_id"] if events else None

    recovered = store.try_recover()
    if recovered is None:
        learner = default_learner(_now())
        session = default_session()
        needs_materialization = True
    else:
        learner = recovered.learner
        session = recovered.session
        if _is_v2_syllabus(syllabus) and "current_target_id" not in session:
            session = dict(session)
            if session.get("current_concept") is not None:
                session["legacy_current_concept"] = session.pop("current_concept")
            session["current_target_id"] = None
        manifest_data = recovered.manifest.data
        applied_line = manifest_data.get("last_complete_observation_line", 0)
        applied_id = manifest_data.get("last_complete_observation_id")
        concept_ids = set(_derived_items(recovered.derived).keys())
        syllabus_ids = set(normalize_syllabus(syllabus).targets)
        # Compare canonical-input fingerprints, not just the concept-id set:
        # editing course.json (exam date, scheduler policy) or syllabus.json
        # content (prerequisites, importance, expected_points) with the same
        # concept ids and no new observations would otherwise look identical
        # to the last committed revision and never trigger a recompute.
        course_changed = manifest_data.get("course_hash") != StudyStore.hash_document(course)
        syllabus_changed = manifest_data.get("syllabus_hash") != StudyStore.hash_document(syllabus)
        expected_inputs = manifest_data.get("canonical_inputs")
        if isinstance(expected_inputs, dict):
            current_inputs = store.canonical_input_fingerprints(course, syllabus)
            canonical_inputs_changed = any(
                expected_inputs.get(key) != current_inputs.get(key)
                for key in (
                    "course_hash",
                    "syllabus_hash",
                    "observations_hash",
                    "assessments_hash",
                    "source_evidence_hash",
                    "sessions_hash",
                    "source_manifest_hash",
                )
            )
        else:
            canonical_inputs_changed = False
        needs_materialization = (
            applied_line != len(events)
            or applied_id != current_id
            or concept_ids != syllabus_ids
            or course_changed
            or syllabus_changed
            or canonical_inputs_changed
        )

    if needs_materialization:
        concepts, reviews, _manifest = _persist_learning(store, course, syllabus, learner, session)
    else:
        concepts = recovered.derived
        reviews = recovered.review_queue
        if reviews is None:
            reviews = build_review_queue(
                events, _derived_items(concepts), course, datetime.now(timezone.utc), syllabus
            )
    return course, syllabus, learner, session, concepts, reviews


def _new_session_id() -> str:
    return f"session-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}"


def _activate_session(session: dict) -> tuple[dict, bool]:
    """Start a fresh session when there is no active one. A session is
    active only while phase is 'study' or 'exam'; end-session always sets
    phase back to 'idle', so the *next* start always gets a new session_id
    instead of resuming the closed one. The break-state pointer
    (current_target_id/current_task/last_attempt_*/pending_action) is left
    untouched across this transition so a session ended mid-task has a
    specific place to resume, not a blank slate - it is only replaced once
    the learner actually attempts something new."""
    if session.get("phase") not in ("study", "exam"):
        activated = dict(session)
        activated.update(
            {
                "session_id": _new_session_id(),
                "phase": "study",
            }
        )
        if activated.get("current_target_id") is None:
            activated["pending_action"] = "choose the next budget-fitting activity"
        return activated, True
    return session, False


def _persist_learning(
    store: StudyStore,
    course: dict,
    syllabus: dict,
    learner: dict,
    session: dict,
) -> tuple[dict, dict, object]:
    events = store.read_complete_observations()
    revision = store.next_revision()
    concepts = reduce_learning_state(course, syllabus, events, _reduction_policy(course, revision))
    now = datetime.now(timezone.utc)
    reviews = build_review_queue(events, _derived_items(concepts), course, now, syllabus)
    reviews["derived_from_revision"] = revision
    learner = dict(learner)
    learner["updated_at"] = now.isoformat()
    manifest = store.commit_revision(concepts, session, learner, reviews, course, syllabus)
    return concepts, reviews, manifest


def _print_json(value: object, *, file=None) -> None:
    # A Windows console with a non-UTF-8 codepage can raise UnicodeEncodeError
    # on non-ASCII output (Cyrillic, math symbols) even after the underlying
    # mutation already succeeded and was committed. Fall back to an ASCII-safe
    # \\uXXXX-escaped encoding rather than losing a successful result to a
    # display-only failure.
    try:
        print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2), file=file)
    except UnicodeEncodeError:
        print(json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2), file=file)


def _result(value: object) -> int:
    _print_json(value)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="exam_prep")
    parser.add_argument(
        "--workspace",
        default=None,
        help="active study workspace; defaults to environment, git root, or cwd",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    load = sub.add_parser("load-syllabus")
    load.add_argument("path")
    sub.add_parser("start")
    sub.add_parser("status")
    next_parser = sub.add_parser("next")
    next_parser.add_argument("--minutes", type=int, default=25)
    record = sub.add_parser("record-observation")
    record.add_argument("path")
    sub.add_parser("review-due")
    sub.add_parser("mistakes")
    sub.add_parser("roadmap")
    exam = sub.add_parser("exam")
    exam.add_argument("--minutes", type=int, default=45)
    verify = sub.add_parser("verify")
    verify.add_argument("path")
    sub.add_parser("rebuild")
    sub.add_parser("validate")
    sub.add_parser("end-session")
    migrate = sub.add_parser("migrate")
    migrate.add_argument("--from-math-study", required=True)
    ingest = sub.add_parser("ingest-source-evidence")
    ingest.add_argument("path")
    validate_curriculum = sub.add_parser("validate-curriculum")
    validate_curriculum.add_argument("path")
    apply_curriculum = sub.add_parser("apply-curriculum")
    apply_curriculum.add_argument("path")
    freeze = sub.add_parser("freeze-assessment")
    freeze.add_argument("path")
    mint = sub.add_parser("mint-assessments")
    mint.add_argument("path")
    update_exam = sub.add_parser("update-exam-blueprint")
    update_exam.add_argument("path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "migrate":
        result = migrate_legacy_workspace(args.from_math_study)
        return _result(result.to_mapping())
    store = _store(args.workspace)
    initialization_state, missing_files = _initialization_state(store)

    if args.command == "status" and initialization_state == "uninitialized":
        return _result({
            "status": "uninitialized",
            "initialized": False,
            "workspace": str(store.root),
        })

    if args.command == "status" and initialization_state == "incomplete":
        return _result({
            "status": "incomplete_workspace",
            "initialized": False,
            "workspace": str(store.root),
            "missing_files": missing_files,
        })

    if initialization_state != "initialized" and args.command not in {
        "init",
        "validate",
        "validate-curriculum",
        "status",
    }:
        return _result({
            "status": "workspace_not_initialized",
            "initialized": False,
            "workspace": str(store.root),
            "missing_files": missing_files,
        })

    if args.command == "ingest-source-evidence":
        envelope = json.loads(Path(args.path).read_text(encoding="utf-8"))
        result = ingest_source_evidence(store, envelope)
        return _result(result.to_mapping())

    if args.command == "validate-curriculum":
        proposal = json.loads(Path(args.path).read_text(encoding="utf-8"))
        try:
            from exam_prep_lib.source_provider import build_runtime_source_catalog

            # A fresh workspace has no trusted persisted evidence to read.
            # Keep pre-init curriculum validation non-mutating while retaining
            # the runtime catalog for initialized workspaces.
            verified_source_catalog = (
                build_runtime_source_catalog(store)
                if initialization_state == "initialized"
                else {}
            )
            validated = validate_curriculum_proposal(
                proposal,
                verified_source_catalog=verified_source_catalog,
            )
        except CurriculumValidationError as exc:
            return _result({
                "valid": False,
                "errors": exc.issues,
                "warnings": exc.warnings,
                "coverage_gaps": exc.coverage_gaps,
            })
        return _result({
            "valid": True,
            "proposal_id": validated["proposal_id"],
            "validation": validated.get("validation", {}),
        })

    if args.command == "apply-curriculum":
        proposal = json.loads(Path(args.path).read_text(encoding="utf-8"))
        try:
            result = apply_curriculum_proposal(store, proposal)
        except CurriculumValidationError as exc:
            return _result({
                "valid": False,
                "errors": exc.issues,
                "warnings": exc.warnings,
                "coverage_gaps": exc.coverage_gaps,
            })
        return _result(result.to_mapping())

    if args.command == "freeze-assessment":
        assessment = FrozenAssessment.from_mapping(
            json.loads(Path(args.path).read_text(encoding="utf-8"))
        )
        result = store.append_assessment(assessment)
        return _result(
            {
                "status": "assessment_frozen",
                "assessment_id": result.assessment_id,
                "spec_hash": assessment.spec_hash,
                "appended": result.appended,
            }
        )

    if args.command == "mint-assessments":
        # Separate from apply-curriculum by design (3.3): curriculum content
        # (targets/syllabus) and assessment artifacts have different
        # lifecycles, and exam_questions as currently typed (Phase 5, out of
        # scope here) carries no prompt/rubric/difficulty - not enough to
        # construct a FrozenAssessment. This takes its own batch of full
        # assessment specs instead of reading exam_questions.
        batch = json.loads(Path(args.path).read_text(encoding="utf-8"))
        if not isinstance(batch, dict):
            raise SchemaError("$", "assessment batch must be an object")
        default_purpose = batch.get("purpose", "practice")
        raw_assessments = batch.get("assessments")
        if not isinstance(raw_assessments, list) or not raw_assessments:
            raise SchemaError("$.assessments", "assessments must be a non-empty array")
        minted: list[dict[str, Any]] = []
        already_existed: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for index, raw_entry in enumerate(raw_assessments):
            if not isinstance(raw_entry, dict):
                rejected.append(
                    {"index": index, "assessment_id": None, "error": "assessment entry must be an object"}
                )
                continue
            entry = dict(raw_entry)
            entry.setdefault("purpose", default_purpose)
            assessment_id = entry.get("assessment_id")
            try:
                frozen = FrozenAssessment.from_mapping(entry)
                # append_assessment is the existing gate: JSON-schema
                # validation and assert_pool_isolation both run inside it -
                # this loop does not reimplement either, per "check before
                # adding" (invariant 6).
                append_result = store.append_assessment(frozen)
            except ValueError as exc:
                rejected.append(
                    {"index": index, "assessment_id": assessment_id, "error": str(exc)}
                )
                continue
            record = {
                "assessment_id": append_result.assessment_id,
                "spec_hash": frozen.spec_hash,
                "purpose": frozen.purpose,
            }
            (minted if append_result.appended else already_existed).append(record)
        return _result(
            {
                "status": "assessments_minted",
                "minted": minted,
                "already_existed": already_existed,
                "rejected": rejected,
                "minted_count": len(minted),
                "already_existed_count": len(already_existed),
                "rejected_count": len(rejected),
            }
        )

    if args.command == "update-exam-blueprint":
        patch = json.loads(Path(args.path).read_text(encoding="utf-8"))
        if not isinstance(patch, dict):
            raise SchemaError("$", "exam blueprint patch must be an object")
        if "revision" in patch:
            # revision is engine-owned (1.4): a human forgetting to bump it
            # is exactly the failure mode this command exists to remove, so
            # letting a patch set it directly would reopen that hole.
            raise SchemaError(
                "$.revision",
                "revision is engine-owned and advances automatically; do not set it directly",
            )
        course, syllabus, learner, session, _concepts, _reviews = load_state(store)
        current_exam = dict(course.get("exam") or {})
        updated_exam = {**current_exam, **patch}
        validate_document(updated_exam, load_schema("course.schema.json")["properties"]["exam"])
        changed = StudyStore.hash_document(updated_exam) != StudyStore.hash_document(current_exam)
        if changed:
            updated_exam["revision"] = int(current_exam.get("revision", 1)) + 1
        course = dict(course)
        course["exam"] = updated_exam
        _write_json(store.state_path / "course.json", course)
        if changed:
            # Commits a fresh revision so the new course_hash/exam_revision
            # land in the manifest immediately (1.4's "reflected in the
            # revision manifest"), not only on the next unrelated command.
            _persist_learning(store, course, syllabus, learner, session)
        return _result(
            {
                "status": "exam_blueprint_updated",
                "changed": changed,
                "course": course,
            }
        )

    if args.command == "init":
        initialization_state, missing_files = _initialization_state(store)
        if initialization_state == "initialized":
            return _result({
                "status": "already_initialized",
                "initialized": True,
                "workspace": str(store.root),
            })
        if initialization_state == "incomplete":
            return _result({
                "status": "initialization_conflict",
                "initialized": False,
                "workspace": str(store.root),
                "missing_files": missing_files,
            })
        store.initialize()
        now = _now()
        course = default_course()
        syllabus = default_syllabus()
        learner = default_learner(now)
        session = default_session()
        _write_json(store.state_path / "course.json", course)
        _write_json(store.state_path / "syllabus.json", syllabus)
        # Commit an initial revision immediately so the recovery chain has a
        # valid baseline from the first command onward (no window where
        # learner.json/session.json exist only as unrevisioned plain files).
        _persist_learning(store, course, syllabus, learner, session)
        return _result({"status": "initialized", "workspace": str(store.root)})

    if args.command == "load-syllabus":
        path = Path(args.path)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        validate_document(loaded, load_schema("syllabus.schema.json"))
        dimension_issues = capability_dimension_issues(loaded)
        if dimension_issues:
            raise SchemaError(
                "$.assessment_capabilities",
                "; ".join(dimension_issues),
            )
        _write_json(store.state_path / "syllabus.json", loaded)
        return _result(
            {
                "status": "syllabus_loaded",
                ("target_count" if int(loaded.get("schema_version", 1)) >= 2 else "concept_count"): len(normalize_syllabus(loaded).targets),
                "source": str(path.resolve()),
            }
        )

    if args.command == "validate":
        # Deliberately runs before load_state(): validate's whole job is to
        # diagnose a broken workspace, including a corrupt course.json or
        # syllabus.json - the exact files load_state() (correctly, for every
        # other command) reads eagerly and would raise on.
        report = run_validation(store)
        _print_json(report)
        return 0 if report["valid"] else 1

    course, syllabus, learner, session, concepts, reviews = load_state(store)

    if args.command == "start":
        session, changed = _activate_session(session)
        if changed:
            concepts, reviews, _manifest = _persist_learning(
                store, course, syllabus, learner, session
            )
        return _result(
            {
                "status": "resumed",
                "session": session,
                ("targets" if _is_v2_syllabus(syllabus) else "concepts"): _public_derived(
                    syllabus, concepts
                ),
            }
        )

    if args.command == "status":
        session_history = store.read_session_summaries()
        return _result(
            {
                "course": {
                    "course_id": course.get("course_id"),
                    "exam": course.get("exam"),
                },
                "session": session,
                "last_session_summary": session_history[-1] if session_history else None,
                ("targets" if _is_v2_syllabus(syllabus) else "concepts"): _public_derived(
                    syllabus, concepts
                ),
                "review_queue": reviews,
                "log_diagnostics": store.read_log_diagnostics(),
                "capability_diagnostics": list(
                    CapabilityRegistry.from_syllabus(syllabus).rejected_descriptors()
                ),
                "blueprint_diagnostics": blueprint_revision_diagnostics(
                    course, store.read_complete_observations()
                ),
                "resume_point": _resume_point(syllabus, concepts, session),
            }
        )

    if args.command == "next":
        selected = select_next_activity(
            syllabus,
            _derived_items(concepts),
            reviews.get("items", {}),
            course,
            datetime.now(timezone.utc),
            args.minutes,
        )
        return _result(
            {"budget_minutes": args.minutes, **_public_activity(syllabus, selected)}
        )

    if args.command == "record-observation":
        proposal = json.loads(Path(args.path).read_text(encoding="utf-8"))
        session, _changed = _activate_session(session)
        result = store.append_observation(
            proposal,
            session["session_id"],
            _now(),
            None,
            None,
            session_phase=session["phase"],
            exam_revision=int(course.get("exam", {}).get("revision", 1)),
            exam_hash=StudyStore.hash_document(course.get("exam") or {}),
        )
        session = dict(session)
        target_id = proposal.get("target_id", proposal.get("concept_id"))
        done = _attempt_is_done(proposal)
        session.update(
            {
                "current_target_id": target_id,
                "current_task": proposal["task_id"],
                "current_task_done": done,
                "last_attempt_outcome": proposal.get("outcome"),
                "last_attempt_error_tags": list(proposal.get("error_tags") or []),
                "pending_action": _pending_action_for_attempt(target_id, proposal, done=done),
            }
        )
        concepts, reviews, manifest = _persist_learning(
            store, course, syllabus, learner, session
        )
        return _result(
            {
                "event": result.canonical_event,
                "appended": result.appended,
                "revision": manifest.revision,
                "session": session,
                ("targets" if _is_v2_syllabus(syllabus) else "concepts"): _public_derived(
                    syllabus, concepts
                ),
                "review_queue": reviews,
            }
        )

    if args.command == "review-due":
        now = datetime.now(timezone.utc)
        due = {
            key: value
            for key, value in reviews.get("items", {}).items()
            if value.get("due_at") and datetime.fromisoformat(value["due_at"]) <= now
        }
        return _result({"due": due})

    if args.command == "mistakes":
        return _result(
            {
                concept_id: state.get("recurring_mistakes", [])
                for concept_id, state in _derived_items(concepts).items()
                if state.get("recurring_mistakes")
            }
        )

    if args.command == "roadmap":
        roadmap = [
            {
                ("target_id" if _is_v2_syllabus(syllabus) else "concept_id"): concept_id,
                "title": metadata.get("title"),
                "mastery_status": _derived_items(concepts)
                .get(concept_id, {})
                .get("mastery_status", "unseen"),
                "review_status": reviews.get("items", {})
                .get(concept_id, {})
                .get("review_status", "not_due"),
                "availability": _derived_items(concepts)
                .get(concept_id, {})
                .get("availability", "available"),
                "prerequisites": metadata.get("prerequisites", []),
            }
            for concept_id, metadata in normalize_syllabus(syllabus).targets.items()
        ]
        return _result({"roadmap": roadmap})

    if args.command == "exam":
        # 3.2: the mock is assembled from purpose="mock" assessments (see
        # mint-assessments, 3.3) sized and timed by the exam blueprint, not
        # a mixed grab-bag of practice tasks. Falls back to a plain budgeted
        # session (empty tickets) when no mock pool has been minted yet -
        # the pre-3.2 behavior, unchanged, rather than an error.
        exam_blueprint = course.get("exam") or {}
        # session_id-seeded sample, not a sorted-and-truncated prefix (9.2):
        # a prefix means every mock on this blueprint draws the same
        # question_count items in the same order forever, which is a
        # retest of familiar tickets, not a held-out exam - and anything
        # past the cutoff is never drawn at all. random.Random(str) hashes
        # the seed via sha512 (CPython, unaffected by PYTHONHASHSEED), so
        # this is reproducible across processes: the same session_id always
        # samples the same tickets in the same order, a different
        # session_id (almost certainly) samples differently.
        session, _changed = _activate_session(session)
        mock_pool = sorted(
            (
                FrozenAssessment.from_mapping(item)
                for item in store.read_assessments()
                if item.get("purpose") == "mock"
            ),
            key=lambda item: item.assessment_id,
        )
        question_count = exam_blueprint.get("question_count")
        pool_size = len(mock_pool) if question_count is None else min(int(question_count), len(mock_pool))
        if mock_pool:
            mock_pool = random.Random(session["session_id"]).sample(mock_pool, pool_size)

        tickets: list[dict[str, Any]] = []
        budget_minutes = args.minutes
        if mock_pool:
            per_question_minutes = exam_blueprint.get("per_question_minutes")
            time_limit_minutes = exam_blueprint.get("time_limit_minutes")
            if per_question_minutes:
                allotted = float(per_question_minutes)
            elif time_limit_minutes:
                allotted = float(time_limit_minutes) / len(mock_pool)
            else:
                allotted = float(args.minutes) / len(mock_pool)
            tickets = [
                {
                    "assessment_id": item.assessment_id,
                    "target_id": item.target_id,
                    "capability_id": item.capability_id,
                    "prompt": item.prompt,
                    "spec_hash": item.spec_hash,
                    "time_limit_minutes": round(allotted, 4),
                }
                for item in mock_pool
            ]
            budget_minutes = (
                int(time_limit_minutes)
                if time_limit_minutes
                else int(round(allotted * len(mock_pool)))
            )

        session = dict(session)
        session.update(
            {
                "phase": "exam",
                "time_budget_minutes": budget_minutes,
                "pending_action": "submit or stop the mock exam for post-mortem",
                "mock_assessment_ids": [ticket["assessment_id"] for ticket in tickets],
            }
        )
        _persist_learning(store, course, syllabus, learner, session)
        return _result(
            {
                "mode": "exam",
                "budget_minutes": budget_minutes,
                "delivery": exam_blueprint.get("delivery"),
                "question_model": exam_blueprint.get("question_model"),
                "follow_up_questions": bool(exam_blueprint.get("follow_up_questions", False)),
                "grading_criteria": exam_blueprint.get("grading_criteria"),
                "tickets": tickets,
                "no_unsolicited_hints": True,
                "minimal_feedback_until_submission": True,
                "session_id": session.get("session_id"),
            }
        )

    if args.command == "verify":
        request = json.loads(Path(args.path).read_text(encoding="utf-8"))
        request.setdefault("samples", [0.5, 1.0, 1.5])
        request.setdefault("tolerance", 1e-4)
        raw_syllabus = request.get("syllabus")
        if not isinstance(raw_syllabus, dict):
            raw_syllabus = (
                request
                if isinstance(request.get("assessment_capabilities"), dict)
                else {}
            )
        capability_registry = (
            CapabilityRegistry.from_syllabus(raw_syllabus)
            if raw_syllabus
            else CapabilityRegistry.with_defaults()
        )
        result = verify_request(
            request,
            capability_registry=capability_registry,
            verifier_registry=VerifierRegistry.with_defaults(),
        )
        return _result(result)

    if args.command == "rebuild":
        events = store.read_complete_observations()
        revision = store.next_revision() - 1
        rebuilt = reduce_learning_state(course, syllabus, events, _reduction_policy(course, revision))
        rebuilt_reviews = build_review_queue(
            events, _derived_items(rebuilt), course, datetime.now(timezone.utc), syllabus
        )
        rebuilt_reviews["derived_from_revision"] = revision
        return _result(
            {
                ("targets" if _is_v2_syllabus(syllabus) else "concepts"): _public_derived(
                    syllabus, rebuilt
                ),
                "review_queue": rebuilt_reviews,
            }
        )

    if args.command == "end-session":
        summary = None
        active_id = session.get("session_id")
        if session.get("phase") in ("study", "exam") and active_id:
            session_events = [
                event for event in store.read_complete_observations()
                if event.get("session_id") == active_id
            ]
            concept_ids = sorted(
                {
                    event.get("target_id", event.get("concept_id"))
                    for event in session_events
                    if event.get("target_id", event.get("concept_id"))
                }
            )
            summary = {
                "schema_version": 1,
                "session_id": active_id,
                "started_at": session_events[0]["recorded_at"] if session_events else _now(),
                "ended_at": _now(),
                "studied": concept_ids,
                "improved": sorted(
                    {
                        event.get("target_id", event.get("concept_id"))
                        for event in session_events
                        if event.get("outcome") == "correct"
                        and event.get("target_id", event.get("concept_id"))
                    }
                ),
                "weak": sorted(
                    concept_id
                    for concept_id in concept_ids
                    if _derived_items(concepts).get(concept_id, {}).get("mastery_status")
                    in ("weak", "learning")
                ),
                "recurring_mistakes": sorted(
                    {
                        mistake["tag"]
                        for concept_id in concept_ids
                        for mistake in _derived_items(concepts)
                        .get(concept_id, {})
                        .get("recurring_mistakes", [])
                        if mistake.get("recurring")
                    }
                ),
                "due_reviews": sorted(
                    concept_id
                    for concept_id in concept_ids
                    if reviews.get("items", {}).get(concept_id, {}).get("review_status")
                    in ("due", "overdue")
                ),
                "next_action": session.get("pending_action"),
            }
            mock_assessment_ids = session.get("mock_assessment_ids") or []
            if session.get("phase") == "exam" and mock_assessment_ids:
                # 3.2's post-mortem: a per-question breakdown of the mock
                # just submitted, not the same aggregate study summary a
                # regular session gets.
                questions = []
                for assessment_id in mock_assessment_ids:
                    matching = [
                        event for event in session_events
                        if event.get("assessment_id") == assessment_id
                    ]
                    last = matching[-1] if matching else None
                    questions.append(
                        {
                            "assessment_id": assessment_id,
                            "target_id": last.get("target_id") if last else None,
                            "attempted": last is not None,
                            "outcome": last.get("outcome") if last else None,
                            "assistance_band": (
                                derive_assistance_band(last.get("assistance") or {})
                                if last is not None
                                else None
                            ),
                        }
                    )
                correct_independent = sum(
                    1
                    for question in questions
                    if question["outcome"] == "correct"
                    and question["assistance_band"] == "independent"
                )
                summary["post_mortem"] = {
                    "total_questions": len(mock_assessment_ids),
                    "attempted": sum(1 for question in questions if question["attempted"]),
                    "correct_independent": correct_independent,
                    "score": (
                        round(correct_independent / len(mock_assessment_ids), 4)
                        if mock_assessment_ids
                        else None
                    ),
                    "questions": questions,
                }
            store.append_session_summary(summary)
        session = dict(session)
        # Deliberately leave current_target_id/current_task/last_attempt_*/
        # pending_action untouched: they are the break-state pointer status
        # uses to report a specific resume point after the session closes,
        # not just this session's aggregate summary.
        session.update({"phase": "idle"})
        concepts, reviews, _manifest = _persist_learning(store, course, syllabus, learner, session)
        return _result({"status": "session_ended", "session": session, "summary": summary})

    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SchemaError, ValueError, FileNotFoundError) as exc:
        _print_json({"error": str(exc)}, file=sys.stderr)
        raise SystemExit(2)

