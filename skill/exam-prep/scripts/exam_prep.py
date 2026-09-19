"""Unified command-line entry point for the exam-prep skill."""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from exam_prep_lib.capabilities import CapabilityRegistry, capability_dimension_issues
from exam_prep_lib.defaults import default_course, default_learner, default_session, default_syllabus
from exam_prep_lib.diagnostics import (
    blueprint_revision_diagnostics,
    run_validation,
    unlinked_exam_attempt_diagnostic,
    unlinked_exam_attempts,
)
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
from exam_prep_lib.readiness import build_readiness
from exam_prep_lib.planner import build_cheatsheet, forecast_plan, last_minute_review
from exam_prep_adapters.local_materials.material_index import hydrate_sources, ingest_materials
from exam_prep_adapters.local_materials.extractor import extract_sources
from exam_prep_adapters.local_materials.questions import extract_questions
from exam_prep_adapters.local_materials.figures import extract_figures
from exam_prep_lib.assessment_draft import build_draft, finalize_draft

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


def _compact_status(result: dict) -> dict:
    """Trim `status --compact` down to what picking the next action needs:
    each target's availability/mastery_status/recurring_mistakes (dropping
    confidence, evidence counters, evidence_maturity, and numeric mastery
    dimensions - available in full via plain `status` or `roadmap`),
    review_queue narrowed to items actually due, and diagnostics fields
    dropped when empty rather than printed as null/[]/false. session,
    resume_point, course, and last_session_summary are already small and
    are passed through unchanged."""

    compact = dict(result)
    targets_key = "targets" if "targets" in result else "concepts"
    derived = result.get(targets_key)
    if isinstance(derived, dict) and isinstance(derived.get("targets"), dict):
        trimmed_targets = {}
        for target_id, state in derived["targets"].items():
            entry = {
                "availability": state.get("availability"),
                "mastery_status": state.get("mastery_status"),
            }
            if state.get("recurring_mistakes"):
                entry["recurring_mistakes"] = state["recurring_mistakes"]
            trimmed_targets[target_id] = entry
        compact[targets_key] = {**derived, "targets": trimmed_targets}

    review_queue = result.get("review_queue")
    if isinstance(review_queue, dict) and isinstance(review_queue.get("items"), dict):
        due_items = {
            target_id: {"review_status": item.get("review_status"), "reason": item.get("reason")}
            for target_id, item in review_queue["items"].items()
            if item.get("review_status") == "due"
        }
        compact["review_queue"] = {**review_queue, "items": due_items}

    if not compact.get("capability_diagnostics"):
        compact.pop("capability_diagnostics", None)
    if not compact.get("blueprint_diagnostics"):
        compact.pop("blueprint_diagnostics", None)
    log_diagnostics = compact.get("log_diagnostics")
    if isinstance(log_diagnostics, dict) and not any(log_diagnostics.values()):
        compact.pop("log_diagnostics", None)

    return compact


def _next_hint(course: dict, session: dict, reviews: dict) -> dict[str, object]:
    due = sum(
        1
        for item in reviews.get("items", {}).values()
        if item.get("review_status") in {"due", "overdue"}
    )
    exam_in_days = None
    raw_exam = (course.get("exam") or {}).get("date")
    if isinstance(raw_exam, str):
        try:
            exam_in_days = max(
                0,
                round(
                    (
                        datetime.fromisoformat(raw_exam.replace("Z", "+00:00"))
                        - datetime.now(timezone.utc)
                    ).total_seconds()
                    / 86400
                ),
            )
        except ValueError:
            pass
    return {
        "command": "next --minutes 25",
        "why": f"review_due={due}, session {session.get('phase', 'idle')}",
        "exam_in_days": exam_in_days,
    }


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
    status_parser = sub.add_parser("status")
    status_parser.add_argument(
        "--compact",
        action="store_true",
        help=(
            "trim each target down to availability/mastery_status/"
            "recurring_mistakes, review_queue down to due items, and drop "
            "empty diagnostics - full form (the default) is unchanged"
        ),
    )
    status_parser.add_argument("--include-next-hint", action="store_true")
    next_parser = sub.add_parser("next")
    next_parser.add_argument("--minutes", type=int, default=25)
    record = sub.add_parser("record-observation")
    record.add_argument("path")
    record.add_argument("--include-next-hint", action="store_true")
    review_due_parser = sub.add_parser("review-due")
    review_due_parser.add_argument("--include-next-hint", action="store_true")
    sub.add_parser("mistakes")
    roadmap_parser = sub.add_parser("roadmap")
    roadmap_parser.add_argument("--include-next-hint", action="store_true")
    exam = sub.add_parser("exam")
    exam.add_argument("--minutes", type=int, default=45)
    verify = sub.add_parser("verify")
    verify.add_argument("path")
    sub.add_parser("rebuild")
    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--readiness", action="store_true")
    validate_parser.add_argument("--format", choices=("json", "text"), default="json")
    validate_parser.add_argument("--include-next-hint", action="store_true")
    end_session_parser = sub.add_parser("end-session")
    end_session_parser.add_argument("--include-next-hint", action="store_true")
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
    ingest_materials_parser = sub.add_parser("ingest-materials")
    ingest_materials_parser.add_argument("materials_dir")
    ingest_materials_parser.add_argument("--mode", choices=("lightweight", "full"), default="lightweight")
    ingest_materials_parser.add_argument("--dry-run", action="store_true")
    ingest_materials_parser.add_argument("--authority-override", action="append", default=[])
    ingest_materials_parser.add_argument("--max-excerpt-chars", type=int, default=1200)
    hydrate_parser = sub.add_parser("hydrate-source")
    hydrate_parser.add_argument("source_id", nargs="+")
    hydrate_parser.add_argument("--materials-dir", default=None)
    hydrate_parser.add_argument("--authority-override", action="append", default=[])
    hydrate_parser.add_argument("--max-excerpt-chars", type=int, default=1200)
    draft_parser = sub.add_parser("draft-assessments")
    draft_parser.add_argument("materials_dir")
    draft_parser.add_argument("--out", required=True)
    draft_parser.add_argument("--reserve-for-mock", action="append", default=[])
    draft_parser.add_argument("--holdout-ratio", type=float, default=0.2)
    finalize_parser = sub.add_parser("finalize-assessment-draft")
    finalize_parser.add_argument("draft")
    finalize_parser.add_argument("--target-map", required=True)
    finalize_parser.add_argument("--out", required=True)
    figures_parser = sub.add_parser("extract-figures")
    figures_parser.add_argument("materials_dir")
    figures_parser.add_argument("--pages", default=None)
    figures_parser.add_argument("--scale", type=float, default=2.0)
    figure_parser = sub.add_parser("figure")
    figure_parser.add_argument("relative_path")
    figure_parser.add_argument("page", type=int)
    figure_parser.add_argument("--crop", default=None)
    figure_parser.add_argument("--out", default=None)
    figure_parser.add_argument("--materials-dir", default=None)
    reveal = sub.add_parser("reveal-answer")
    reveal.add_argument("assessment_id")
    reveal.add_argument("--exposure", action="store_true")
    cheatsheet = sub.add_parser("cheatsheet")
    cheatsheet.add_argument("--out", default=None)
    cheatsheet.add_argument("--targets", default=None)
    last_review_parser = sub.add_parser("last-minute-review")
    last_review_parser.add_argument("--include-next-hint", action="store_true")
    forecast = sub.add_parser("plan")
    forecast.add_argument("--days", type=int, default=1)
    forecast.add_argument("--minutes-per-day", type=int, default=120)
    forecast.add_argument("--include-next-hint", action="store_true")
    return parser


def _authority_overrides(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in values:
        if "=" not in raw:
            raise ValueError("--authority-override must use <relative-path>=<authority>")
        path, authority = raw.split("=", 1)
        if not path or not authority:
            raise ValueError("--authority-override must use <relative-path>=<authority>")
        result[path] = authority
    return result


def _crop_values(value: str | None) -> tuple[float, float, float, float] | None:
    if not value:
        return None
    parts = tuple(float(item.strip()) for item in value.split(","))
    if len(parts) != 4 or parts[2] <= parts[0] or parts[3] <= parts[1]:
        raise ValueError("--crop must be x0,y0,x1,y1 with positive width and height")
    return parts


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "migrate":
        result = migrate_legacy_workspace(args.from_math_study)
        return _result(result.to_mapping())
    if args.command == "draft-assessments":
        questions = extract_questions(extract_sources(args.materials_dir))
        draft = build_draft(questions, reserve_for_mock=args.reserve_for_mock, holdout_ratio=args.holdout_ratio)
        _write_json(Path(args.out), draft)
        return _result({"status": "draft_written", "out": str(Path(args.out).resolve()), "count": len(draft["assessments"])})
    if args.command == "finalize-assessment-draft":
        draft = json.loads(Path(args.draft).read_text(encoding="utf-8"))
        target_map = json.loads(Path(args.target_map).read_text(encoding="utf-8"))
        package = finalize_draft(draft, target_map)
        _write_json(Path(args.out), package)
        return _result({"status": "mint_package_written", "out": str(Path(args.out).resolve()), "count": len(package["assessments"])})
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
        "ingest-materials",
        "hydrate-source",
        "extract-figures",
        "figure",
    }:
        return _result({
            "status": "workspace_not_initialized",
            "initialized": False,
            "workspace": str(store.root),
            "missing_files": missing_files,
        })

    if args.command == "ingest-materials":
        result = ingest_materials(
            args.materials_dir,
            store,
            mode=args.mode,
            dry_run=args.dry_run,
            authority_map=_authority_overrides(args.authority_override),
            max_excerpt_chars=args.max_excerpt_chars,
        )
        return _result(result)

    if args.command == "extract-figures":
        store.initialize()
        selected = args.pages.split(",") if args.pages else None
        result = extract_figures(args.materials_dir, store.state_path / "assets", pages=selected, scale=args.scale)
        return _result(result)

    if args.command == "figure":
        store.initialize()
        materials_dir = Path(args.materials_dir or store.root / "materials")
        result = extract_figures(
            materials_dir,
            store.state_path / "assets",
            pages=[f"{args.relative_path}:{args.page}"],
            crop=_crop_values(args.crop),
        )
        if args.out and result.get("assets"):
            source = Path(result["assets"][0]["path"])
            destination = Path(args.out)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            result["path"] = str(destination.resolve())
        return _result(result)

    if args.command == "hydrate-source":
        materials_dir = args.materials_dir or str(Path(store.root) / "materials")
        result = hydrate_sources(
            materials_dir,
            store,
            args.source_id,
            authority_map=_authority_overrides(args.authority_override),
            max_excerpt_chars=args.max_excerpt_chars,
        )
        return _result(result)

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
            # SKILL.md puts validate-curriculum in front of apply-curriculum,
            # so a rejected proposal has to reach a caller that only checks the
            # exit code - agent or CI. Plain `validate` already returns 1 in
            # the same situation; these two were the outliers.
            _print_json({
                "valid": False,
                "errors": exc.issues,
                "warnings": exc.warnings,
                "coverage_gaps": exc.coverage_gaps,
            })
            return 1
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
            # SKILL.md puts validate-curriculum in front of apply-curriculum,
            # so a rejected proposal has to reach a caller that only checks the
            # exit code - agent or CI. Plain `validate` already returns 1 in
            # the same situation; these two were the outliers.
            _print_json({
                "valid": False,
                "errors": exc.issues,
                "warnings": exc.warnings,
                "coverage_gaps": exc.coverage_gaps,
            })
            return 1
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
        if args.readiness:
            report = {**report, "readiness": build_readiness(store, report)}
        if args.include_next_hint:
            report = {**report, "next": _next_hint({}, {}, {})}
        if args.format == "text":
            readiness = report.get("readiness")
            if readiness:
                print(f"verdict: {readiness['verdict']}")
                for reason in readiness.get("reasons", []):
                    print(f"reason: {reason.encode('ascii', 'backslashreplace').decode('ascii')}")
            else:
                print("valid: " + ("yes" if report.get("valid") else "no"))
        else:
            _print_json(report)
        return 0 if report["valid"] else 1

    course, syllabus, learner, session, concepts, reviews = load_state(store)

    if args.command == "reveal-answer":
        assessments = {
            item["assessment_id"]: FrozenAssessment.from_mapping(item)
            for item in store.read_assessments()
            if item.get("assessment_id")
        }
        assessment = assessments.get(args.assessment_id)
        if assessment is None:
            return _result({"status": "unknown_assessment", "assessment_id": args.assessment_id})
        if session.get("phase") == "exam":
            return _result({"status": "exam_reveal_forbidden", "assessment_id": args.assessment_id})
        events = [event for event in store.read_complete_observations() if event.get("assessment_id") == args.assessment_id]
        if not events and not args.exposure:
            _print_json({"status": "attempt_required", "assessment_id": args.assessment_id})
            return 1
        if not events and args.exposure:
            session, _changed = _activate_session(session)
            proposal = {
                "schema_version": 2,
                "observation_id": f"solution-exposure-{uuid4()}",
                "target_id": assessment.target_id,
                "task_id": assessment.assessment_id,
                "capability_id": assessment.capability_id,
                "task_type": assessment.capability_id,
                "outcome": "solution_seen",
                "assistance": {"requested": True, "levels_revealed": ["H5"], "full_solution_viewed": True},
                "error_tags": [],
                "diagnostic_confidence": "high",
                "source_refs": list(assessment.source_refs),
                "assessment_id": assessment.assessment_id,
                "solution_exposed": True,
                "explicit_exposure_reason": "user requested --exposure",
            }
            store.append_observation(proposal, session["session_id"], _now(), None, None, session_phase=session["phase"])
            _persist_learning(store, course, syllabus, learner, session)
        index_path = store.state_path / "assets" / "index.json"
        index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {"assets": []}
        assets = [asset for asset in index.get("assets", []) if asset.get("assessment_id") == args.assessment_id and asset.get("role") == "answer"]
        return _result({"status": "answer_revealed", "assessment_id": args.assessment_id, "assets": assets})

    if args.command == "cheatsheet":
        target_ids = args.targets.split(",") if args.targets else None
        text = build_cheatsheet(syllabus, _derived_items(concepts), reviews, store.read_source_evidence(), target_ids=target_ids)
        output_path = Path(args.out) if args.out else store.state_path / "cheatsheet.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
        return _result({"status": "cheatsheet_written", "path": str(output_path.resolve())})

    if args.command == "last-minute-review":
        payload = {"items": last_minute_review(syllabus, _derived_items(concepts), reviews, course, datetime.now(timezone.utc), 25)}
        if args.include_next_hint:
            payload["next"] = _next_hint(course, session, reviews)
        return _result(payload)

    if args.command == "plan":
        payload = forecast_plan(syllabus, _derived_items(concepts), reviews, course, datetime.now(timezone.utc), days=args.days, minutes_per_day=args.minutes_per_day)
        if args.include_next_hint:
            payload["next"] = _next_hint(course, session, reviews)
        return _result(payload)

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
        full = {
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
        if args.include_next_hint:
            full["next"] = _next_hint(course, session, reviews)
        return _result(_compact_status(full) if args.compact else full)

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
        # Computed before the append so "already linked" means the state this
        # attempt arrived into. Never gates the write - see the function's
        # docstring on why an unlinked attempt is still recorded.
        unlinked_diagnostic = unlinked_exam_attempt_diagnostic(
            proposal,
            session,
            store.read_assessments(),
            store.read_complete_observations(),
        )
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
        payload = {
            "event": result.canonical_event,
            "appended": result.appended,
            "revision": manifest.revision,
            "session": session,
            ("targets" if _is_v2_syllabus(syllabus) else "concepts"): _public_derived(
                syllabus, concepts
            ),
            "review_queue": reviews,
        }
        if unlinked_diagnostic is not None:
            payload["diagnostics"] = [unlinked_diagnostic]
        if args.include_next_hint:
            payload["next"] = _next_hint(course, session, reviews)
        return _result(payload)

    if args.command == "review-due":
        now = datetime.now(timezone.utc)
        due = {
            key: value
            for key, value in reviews.get("items", {}).items()
            if value.get("due_at") and datetime.fromisoformat(value["due_at"]) <= now
        }
        payload = {"due": due}
        if args.include_next_hint:
            payload["next"] = _next_hint(course, session, reviews)
        return _result(payload)

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
        payload = {"roadmap": roadmap}
        if args.include_next_hint:
            payload["next"] = _next_hint(course, session, reviews)
        return _result(payload)

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

        was_in_exam = session.get("phase") == "exam"
        session = dict(session)
        session.update(
            {
                "phase": "exam",
                "time_budget_minutes": budget_minutes,
                "pending_action": "submit or stop the mock exam for post-mortem",
                "mock_assessment_ids": [ticket["assessment_id"] for ticket in tickets],
            }
        )
        # Anchors which of this session's observations belong to the mock, so
        # end-session's unlinked summary does not report study-phase work that
        # happened earlier in the same session. Re-running `exam` within an
        # exam already in progress keeps the original anchor (the repeat draws
        # the same tickets), while end-session's return to idle clears it.
        if not was_in_exam or not session.get("mock_started_at"):
            session["mock_started_at"] = _now()
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
                    "unlinked_attempts": unlinked_exam_attempts(
                        session, store.read_assessments(), session_events
                    ),
                }
            store.append_session_summary(summary)
        session = dict(session)
        # Deliberately leave current_target_id/current_task/last_attempt_*/
        # pending_action untouched: they are the break-state pointer status
        # uses to report a specific resume point after the session closes,
        # not just this session's aggregate summary.
        session.update({"phase": "idle", "mock_started_at": None})
        concepts, reviews, _manifest = _persist_learning(store, course, syllabus, learner, session)
        payload = {"status": "session_ended", "session": session, "summary": summary}
        if args.include_next_hint:
            payload["next"] = _next_hint(course, session, reviews)
        return _result(payload)

    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SchemaError, ValueError, FileNotFoundError) as exc:
        _print_json({"error": str(exc)}, file=sys.stderr)
        raise SystemExit(2)

