"""Unified command-line entry point for the math-study skill."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from math_study_lib.reducer import reduce_learning_state
from math_study_lib.scheduler import (
    build_review_queue,
    compute_priority,
    select_next_activity,
)
from math_study_lib.schema_validation import (
    SchemaError,
    load_schema,
    validate_document,
)
from math_study_lib.storage import StudyStore
from math_study_lib.verifier import verify_antiderivative, verify_derivative


DEFAULT_COURSE = {
    "schema_version": 1,
    "course_id": "calculus-1",
    "title": "Mathematical analysis",
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
    },
}
DEFAULT_SYLLABUS = {"schema_version": 1, "concepts": {}}
DEFAULT_LEARNER = {
    "schema_version": 1,
    "updated_at": None,
    "preferences": {
        "learning_style": ["interactive", "problem_solving", "programmer_analogies"],
        "explanation_length": "concise",
        "solution_policy": "delay_full_solution",
    },
    "stable_patterns": [],
}
DEFAULT_SESSION = {
    "schema_version": 1,
    "session_id": "",
    "phase": "idle",
    "pending_action": "load a syllabus and start a session",
    "current_concept": None,
    "current_task": None,
    "time_budget_minutes": 25,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _store(workspace: str) -> StudyStore:
    store = StudyStore(Path(workspace).resolve())
    store.initialize()
    return store


def _state(store: StudyStore) -> tuple[dict, dict, dict, dict, list[dict]]:
    course = _read_json(store.state_path / "course.json", DEFAULT_COURSE.copy())
    syllabus = _read_json(store.state_path / "syllabus.json", DEFAULT_SYLLABUS.copy())
    learner = _read_json(store.state_path / "learner.json", DEFAULT_LEARNER.copy())
    session = _read_json(store.state_path / "session.json", DEFAULT_SESSION.copy())
    concepts = _read_json(
        store.state_path / "concepts.json",
        reduce_learning_state(course, syllabus, [], {}),
    )
    reviews = _read_json(
        store.state_path / "review_queue.json",
        build_review_queue(
            store.read_complete_observations(),
            concepts.get("concepts", {}),
            course,
            datetime.now(timezone.utc),
        ),
    )
    return course, syllabus, learner, session, concepts, reviews


def _persist_learning(
    store: StudyStore,
    course: dict,
    syllabus: dict,
    learner: dict,
    session: dict,
) -> tuple[dict, dict, object]:
    events = store.read_complete_observations()
    revision = store.next_revision()
    concepts = reduce_learning_state(course, syllabus, events, {"revision": revision})
    now = datetime.now(timezone.utc)
    reviews = build_review_queue(events, concepts.get("concepts", {}), course, now)
    reviews["derived_from_revision"] = revision
    learner = dict(learner)
    learner["updated_at"] = now.isoformat()
    manifest = store.commit_revision(concepts, session, learner, reviews)
    return concepts, reviews, manifest


def _result(value: object) -> int:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="math_study")
    parser.add_argument(
        "--workspace",
        default=os.environ.get("MATH_STUDY_WORKSPACE", "."),
        help="active study workspace; defaults to the current directory",
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    store = _store(args.workspace)
    course, syllabus, learner, session, concepts, reviews = _state(store)

    if args.command == "init":
        now = _now()
        learner = dict(DEFAULT_LEARNER)
        learner["updated_at"] = now
        _write_json(store.state_path / "course.json", DEFAULT_COURSE)
        _write_json(store.state_path / "syllabus.json", DEFAULT_SYLLABUS)
        _write_json(store.state_path / "learner.json", learner)
        _write_json(store.state_path / "session.json", DEFAULT_SESSION)
        return _result({"status": "initialized", "workspace": str(store.root)})

    if args.command == "load-syllabus":
        path = Path(args.path)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        validate_document(loaded, load_schema("syllabus.schema.json"))
        _write_json(store.state_path / "syllabus.json", loaded)
        return _result(
            {
                "status": "syllabus_loaded",
                "concept_count": len(loaded.get("concepts", {})),
                "source": str(path.resolve()),
            }
        )

    if args.command == "start":
        if not session.get("session_id"):
            session = dict(session)
            session.update(
                {
                    "session_id": f"session-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}",
                    "phase": "study",
                    "pending_action": "choose the next budget-fitting activity",
                }
            )
            _write_json(store.state_path / "session.json", session)
        return _result({"status": "resumed", "session": session, "concepts": concepts})

    if args.command == "status":
        return _result(
            {
                "course": {
                    "course_id": course.get("course_id"),
                    "exam": course.get("exam"),
                },
                "session": session,
                "concepts": concepts,
                "review_queue": reviews,
                "log_diagnostics": store.read_log_diagnostics(),
            }
        )

    if args.command == "next":
        selected = select_next_activity(
            syllabus,
            concepts.get("concepts", {}),
            reviews.get("items", {}),
            course,
            datetime.now(timezone.utc),
            args.minutes,
        )
        return _result({"budget_minutes": args.minutes, **selected})

    if args.command == "record-observation":
        proposal = json.loads(Path(args.path).read_text(encoding="utf-8"))
        if not session.get("session_id"):
            session = dict(session)
            session["session_id"] = f"session-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
            session["phase"] = "study"
        result = store.append_observation(
            proposal,
            session["session_id"],
            _now(),
            None,
            None,
        )
        session = dict(session)
        session.update(
            {
                "current_concept": proposal["concept_id"],
                "current_task": proposal["task_id"],
                "pending_action": f"continue {proposal['concept_id']} with an independent check",
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
                "concepts": concepts,
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
                for concept_id, state in concepts.get("concepts", {}).items()
                if state.get("recurring_mistakes")
            }
        )

    if args.command == "roadmap":
        roadmap = [
            {
                "concept_id": concept_id,
                "title": metadata.get("title"),
                "status": concepts.get("concepts", {}).get(concept_id, {}).get("status", "unseen"),
                "prerequisites": metadata.get("prerequisites", []),
            }
            for concept_id, metadata in syllabus.get("concepts", {}).items()
        ]
        return _result({"roadmap": roadmap})

    if args.command == "exam":
        session = dict(session)
        session.update(
            {
                "phase": "exam",
                "time_budget_minutes": args.minutes,
                "pending_action": "submit or stop the mixed mock exam for post-mortem",
            }
        )
        _write_json(store.state_path / "session.json", session)
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
        rebuilt = reduce_learning_state(course, syllabus, events, {"revision": revision})
        rebuilt_reviews = build_review_queue(
            events, rebuilt.get("concepts", {}), course, datetime.now(timezone.utc)
        )
        rebuilt_reviews["derived_from_revision"] = revision
        return _result({"concepts": rebuilt, "review_queue": rebuilt_reviews})

    if args.command == "validate":
        validate_document(course, load_schema("course.schema.json"))
        validate_document(syllabus, load_schema("syllabus.schema.json"))
        return _result({"status": "valid"})

    if args.command == "end-session":
        session = dict(session)
        session["phase"] = "idle"
        session["pending_action"] = "resume with start"
        _write_json(store.state_path / "session.json", session)
        return _result({"status": "session_ended", "session": session})

    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SchemaError, ValueError, FileNotFoundError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
