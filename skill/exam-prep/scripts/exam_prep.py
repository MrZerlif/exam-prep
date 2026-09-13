"""Unified command-line entry point for the exam-prep skill."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from exam_prep_lib.diagnostics import run_validation
from exam_prep_lib.reducer import reduce_learning_state
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
from exam_prep_lib.verifier import verify_antiderivative, verify_derivative
from exam_prep_lib.workspace import discover_git_root, resolve_workspace


DEFAULT_COURSE = {
    "schema_version": 2,
    "course_id": "exam-prep-course",
    "title": "Exam preparation",
    "exam": {
        "date": None,
        "timezone": "UTC",
        "format": "mixed",
        "expected_total_points": 100,
        "revision": 1,
    },
    "time_budget": {"default_minutes": 25, "available_minutes_by_day": {}},
    "source_policy": {
        "priority_order": [
            "teacher_material",
            "official_exam_list",
            "lecture_notes",
            "problem_sets",
            "general_reference",
        ],
        "conflicts": "flag_for_user",
    },
    "scheduler": {
        "mode": "exam_cram",
        "max_review_interval_hours": 72,
        "review_warmup_limit": 3,
        # A mistake is not "recurring" after a single occurrence. It becomes
        # recurring once it repeats min_count times, or shows up in
        # min_sessions distinct sessions, whichever comes first. It resolves
        # after resolve_after_clean_successes independent correct attempts on
        # the same concept without the mistake reappearing.
        "recurring_mistake_policy": {
            "min_count": 3,
            "min_sessions": 2,
            "resolve_after_clean_successes": 3,
        },
    },
}
DEFAULT_SYLLABUS = {
    "schema_version": 2,
    "course_id": "exam-prep-course",
    "source_refs": [],
    "learning_targets": [],
    "assessment_capabilities": {},
    "exam_questions": [],
}
DEFAULT_LEARNER = {
    "schema_version": 1,
    "updated_at": None,
    "preferences": {
        "interaction_preferences": ["interactive"],
        "explanation_preferences": ["concise", "use_analogies_when_helpful"],
        "preferred_practice_modes": ["problem_solving"],
        "explanation_length": "concise",
        "solution_policy": "delay_full_solution",
    },
    "stable_patterns": [],
}
DEFAULT_SESSION = {
    "schema_version": 2,
    "session_id": "",
    "phase": "idle",
    "pending_action": "load a syllabus and start a session",
    "current_target_id": None,
    "current_task": None,
    "time_budget_minutes": 25,
}


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
    store.initialize()
    return store


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
    course = _read_json(store.state_path / "course.json", DEFAULT_COURSE.copy())
    syllabus = _read_json(store.state_path / "syllabus.json", DEFAULT_SYLLABUS.copy())
    events = store.read_complete_observations()
    current_id = events[-1]["observation_id"] if events else None

    recovered = store.try_recover()
    if recovered is None:
        learner = dict(DEFAULT_LEARNER)
        learner["updated_at"] = _now()
        session = dict(DEFAULT_SESSION)
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
    instead of resuming the closed one."""
    if session.get("phase") not in ("study", "exam"):
        activated = dict(session)
        activated.update(
            {
                "session_id": _new_session_id(),
                "phase": "study",
                "pending_action": "choose the next budget-fitting activity",
                "current_target_id": None,
                "current_task": None,
            }
        )
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


def _result(value: object) -> int:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "migrate":
        result = migrate_legacy_workspace(args.from_math_study)
        return _result(result.to_mapping())
    store = _store(args.workspace)

    if args.command == "ingest-source-evidence":
        envelope = json.loads(Path(args.path).read_text(encoding="utf-8"))
        result = ingest_source_evidence(store, envelope)
        return _result(result.to_mapping())

    if args.command == "validate-curriculum":
        proposal = json.loads(Path(args.path).read_text(encoding="utf-8"))
        try:
            validated = validate_curriculum_proposal(proposal)
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

    if args.command == "init":
        now = _now()
        course = dict(DEFAULT_COURSE)
        syllabus = dict(DEFAULT_SYLLABUS)
        learner = dict(DEFAULT_LEARNER)
        learner["updated_at"] = now
        session = dict(DEFAULT_SESSION)
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
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
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
        )
        session = dict(session)
        target_id = proposal.get("target_id", proposal.get("concept_id"))
        session.update(
            {
                "current_target_id": target_id,
                "current_task": proposal["task_id"],
                "pending_action": f"continue {target_id} with an independent check",
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
        session, _changed = _activate_session(session)
        session = dict(session)
        session.update(
            {
                "phase": "exam",
                "time_budget_minutes": args.minutes,
                "pending_action": "submit or stop the mixed mock exam for post-mortem",
            }
        )
        _persist_learning(store, course, syllabus, learner, session)
        return _result(
            {
                "mode": "exam",
                "budget_minutes": args.minutes,
                "no_unsolicited_hints": True,
                "minimal_feedback_until_submission": True,
                "session_id": session.get("session_id"),
            }
        )

    if args.command == "verify":
        request = json.loads(Path(args.path).read_text(encoding="utf-8"))
        samples = request.get("samples", [0.5, 1.0, 1.5])
        tolerance = float(request.get("tolerance", 1e-4))
        if request.get("kind") == "antiderivative":
            result = verify_antiderivative(
                request["integrand"],
                request["antiderivative"],
                request.get("variable", "x"),
                samples,
                tolerance,
            )
        else:
            result = verify_derivative(
                request["expression"],
                request["derivative"],
                request.get("variable", "x"),
                samples,
                tolerance,
            )
        return _result(asdict(result))

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
            store.append_session_summary(summary)
        session = dict(session)
        session.update(
            {
                "phase": "idle",
                "pending_action": "resume with start",
                "current_target_id": None,
                "current_task": None,
            }
        )
        concepts, reviews, _manifest = _persist_learning(store, course, syllabus, learner, session)
        return _result({"status": "session_ended", "session": session, "summary": summary})

    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SchemaError, ValueError, FileNotFoundError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)

