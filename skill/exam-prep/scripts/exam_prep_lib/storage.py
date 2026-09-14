"""Append-only evidence storage and revision-based recovery."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .assessment import FrozenAssessment
from .assessment_integrity import assess_attempt_evidence
from .schema_validation import (
    load_schema,
    validate_document,
    validate_observation_event,
    validate_observation_proposal,
)


class ObservationConflict(ValueError):
    """The same observation id was submitted with a different payload."""


class AssessmentConflict(ValueError):
    """The same assessment id was submitted with a different frozen contract."""


@dataclass(frozen=True)
class AppendResult:
    observation_id: str
    canonical_event: dict[str, Any]
    appended: bool
    revision_created: int | None = None


@dataclass(frozen=True)
class AssessmentAppendResult:
    assessment_id: str
    contract: dict[str, Any]
    appended: bool


@dataclass(frozen=True)
class RevisionManifest:
    revision: int
    data: dict[str, Any]


@dataclass(frozen=True)
class RecoveryResult:
    manifest: RevisionManifest
    revision_path: Path
    derived: dict[str, Any]
    session: dict[str, Any]
    learner: dict[str, Any]
    review_queue: dict[str, Any] | None = None


class StudyStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self._set_runtime_path(self.root / "state")

    @classmethod
    def for_exam_prep(cls, workspace: Path) -> "StudyStore":
        """Create a store using the flat .exam-prep runtime directory."""

        store = cls(Path(workspace))
        store._set_runtime_path(store.root / ".exam-prep")
        return store

    def _set_runtime_path(self, runtime_path: Path) -> None:
        self.state_path = Path(runtime_path)
        self.observations_path = self.state_path / "observations.jsonl"
        self.assessments_path = self.state_path / "assessments.jsonl"
        self.source_evidence_path = self.state_path / "source_evidence.jsonl"
        self.source_manifest_path = self.state_path / "sources.json"
        self.sessions_log_path = self.state_path / "sessions.jsonl"
        self.revisions_path = self.state_path / "revisions"
        self.recovery_path = self.state_path / "recovery"
        self.current_path = self.state_path / "current.json"
        self._log_diagnostics = {"partial_final_line": False, "sessions_log_partial_final_line": False}

    def initialization_state(self) -> tuple[str, list[str]]:
        """Classify canonical state without creating or overwriting files."""
        required = ("course.json", "syllabus.json")
        missing = [
            name
            for name in required
            if not (self.state_path / name).exists()
        ]
        if not missing:
            return "initialized", []

        meaningful_logs = (
            self.observations_path,
            self.assessments_path,
            self.source_evidence_path,
            self.sessions_log_path,
        )
        has_events = any(path.exists() and path.stat().st_size > 0 for path in meaningful_logs)
        if len(missing) == len(required) and not has_events:
            return "uninitialized", missing
        return "incomplete", missing


    def initialize(self) -> None:
        for path in (self.root, self.state_path, self.revisions_path, self.recovery_path):
            path.mkdir(parents=True, exist_ok=True)
        self.observations_path.touch(exist_ok=True)
        self.assessments_path.touch(exist_ok=True)
        self.source_evidence_path.touch(exist_ok=True)
        self.sessions_log_path.touch(exist_ok=True)

    @staticmethod
    def _dump(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        path.write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _read_complete_jsonl(path: Path, label: str) -> tuple[list[dict[str, Any]], bool]:
        """Read an append-only JSONL log, tolerating a torn final line left by
        a crash mid-write. Returns (complete records, partial_final_line)."""
        raw = path.read_bytes()
        lines = raw.splitlines(keepends=True)
        records: list[dict[str, Any]] = []
        partial_final_line = False
        for index, line in enumerate(lines):
            if not line.strip():
                continue
            if index == len(lines) - 1 and not line.endswith((b"\n", b"\r")):
                partial_final_line = True
                continue
            try:
                record = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid complete {label} line {index + 1}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"{label} line {index + 1} is not an object")
            records.append(record)
        return records, partial_final_line

    @staticmethod
    def _append_jsonl(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = (StudyStore._dump(value) + "\n").encode("utf-8")
        with path.open("ab") as handle:
            handle.write(line)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass

    def read_complete_observations(self) -> list[dict[str, Any]]:
        self.initialize()
        events, partial = self._read_complete_jsonl(self.observations_path, "observation")
        self._log_diagnostics["partial_final_line"] = partial
        return events

    def read_session_summaries(self) -> list[dict[str, Any]]:
        self.initialize()
        summaries, partial = self._read_complete_jsonl(self.sessions_log_path, "session summary")
        self._log_diagnostics["sessions_log_partial_final_line"] = partial
        return summaries

    def read_assessments(self) -> list[dict[str, Any]]:
        self.initialize()
        assessments, _partial = self._read_complete_jsonl(
            self.assessments_path, "assessment"
        )
        return assessments

    def append_assessment(
        self, assessment: FrozenAssessment | dict[str, Any]
    ) -> AssessmentAppendResult:
        frozen = (
            assessment
            if isinstance(assessment, FrozenAssessment)
            else FrozenAssessment.from_mapping(assessment)
        )
        canonical = frozen.to_mapping()
        validate_document(canonical, load_schema("assessment.schema.json"))
        existing = {
            item["assessment_id"]: item
            for item in self.read_assessments()
            if "assessment_id" in item
        }
        assessment_id = frozen.assessment_id
        if assessment_id in existing:
            if existing[assessment_id] == canonical:
                return AssessmentAppendResult(assessment_id, existing[assessment_id], False)
            raise AssessmentConflict(
                f"assessment_id {assessment_id!r} already has a different frozen contract"
            )
        self._append_jsonl(self.assessments_path, canonical)
        return AssessmentAppendResult(assessment_id, canonical, True)

    def read_source_evidence(self) -> list[dict[str, Any]]:
        self.initialize()
        evidence, _partial = self._read_complete_jsonl(
            self.source_evidence_path, "source evidence"
        )
        return evidence

    def append_source_evidence(self, evidence: dict[str, Any]) -> None:
        self.initialize()
        self._append_jsonl(self.source_evidence_path, evidence)

    def append_session_summary(self, summary: dict[str, Any]) -> None:
        self.initialize()
        self._append_jsonl(self.sessions_log_path, summary)

    def read_log_diagnostics(self) -> dict[str, bool]:
        self.read_complete_observations()
        self.read_session_summaries()
        return dict(self._log_diagnostics)

    def append_observation(
        self,
        proposal: dict[str, Any],
        session_id: str,
        recorded_at: str,
        expected_seconds: int | None,
        elapsed_seconds: int | None,
    ) -> AppendResult:
        validate_observation_proposal(proposal)
        assessment_id = proposal.get("assessment_id")
        integrity_decision = None
        frozen = None
        if assessment_id is not None:
            frozen_by_id = {
                item["assessment_id"]: FrozenAssessment.from_mapping(item)
                for item in self.read_assessments()
                if "assessment_id" in item
            }
            frozen = frozen_by_id.get(assessment_id)
            if frozen is None:
                raise AssessmentConflict(
                    f"observation references unknown assessment_id {assessment_id!r}"
                )
            integrity_decision = assess_attempt_evidence(
                proposal,
                frozen,
                prior_events=self.read_complete_observations(),
            )
        canonical = dict(proposal)
        canonical.update(
            {
                "recorded_at": recorded_at,
                "session_id": session_id,
                "expected_seconds": expected_seconds,
                "elapsed_seconds": elapsed_seconds,
            }
        )
        if integrity_decision is not None:
            canonical["assessment_spec_hash"] = frozen.spec_hash
            canonical["assessment_integrity"] = integrity_decision.integrity
        elif canonical.get("schema_version") == 2:
            canonical["assessment_integrity"] = "not_assessment"
        validate_observation_event(canonical)
        existing = {
            event["observation_id"]: event
            for event in self.read_complete_observations()
            if "observation_id" in event
        }
        observation_id = proposal["observation_id"]
        if observation_id in existing:
            engine_fields = {
                "recorded_at",
                "session_id",
                "timestamp",
                "expected_seconds",
                "elapsed_seconds",
                "assessment_spec_hash",
                "assessment_integrity",
            }
            learner_payload = {
                key: value
                for key, value in existing[observation_id].items()
                if key not in engine_fields
            }
            if learner_payload == proposal:
                return AppendResult(observation_id, existing[observation_id], False)
            raise ObservationConflict(
                f"observation_id {observation_id!r} already has a different payload"
            )

        self._append_jsonl(self.observations_path, canonical)
        return AppendResult(observation_id, canonical, True)

    def _next_revision(self) -> int:
        revisions = [
            int(path.name)
            for path in self.revisions_path.iterdir()
            if path.is_dir() and path.name.isdigit()
        ]
        return max(revisions, default=0) + 1

    def next_revision(self) -> int:
        """Return the next revision number without changing state."""
        self.initialize()
        return self._next_revision()

    @staticmethod
    def _hash_file(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def hash_document(value: Any) -> str:
        """Deterministic, formatting-independent fingerprint of a JSON-able
        document (canonicalized key order and separators before hashing), so
        two documents that differ only in whitespace/key order hash equal."""
        return hashlib.sha256(StudyStore._dump(value).encode("utf-8")).hexdigest()

    @staticmethod
    def _derived_filename(derived: dict[str, Any]) -> str:
        """Use target snapshots for v2 and read/write concepts only for v1."""

        return "targets.json" if derived.get("schema_version") == 2 else "concepts.json"

    @staticmethod
    def _derived_items(derived: dict[str, Any]) -> dict[str, Any]:
        items = derived.get("targets")
        if isinstance(items, dict):
            return items
        items = derived.get("concepts", {})
        return items if isinstance(items, dict) else {}

    def canonical_input_fingerprints(
        self,
        course: dict[str, Any] | None = None,
        syllabus: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        "The stable fingerprints used to decide whether a revision is stale."

        events = self.read_complete_observations()
        assessments = self.read_assessments()
        source_evidence = self.read_source_evidence()
        sessions = self.read_session_summaries()
        return {
            "course_hash": self.hash_document(course) if course is not None else None,
            "syllabus_hash": self.hash_document(syllabus) if syllabus is not None else None,
            "observations_hash": self.hash_document(events),
            "assessments_hash": self.hash_document(assessments),
            "source_evidence_hash": self.hash_document(source_evidence),
            "sessions_hash": self.hash_document(sessions),
            "source_manifest_hash": (
                self._hash_file(self.source_manifest_path)
                if self.source_manifest_path.exists()
                else None
            ),
            "observation_count": len(events),
            "assessment_count": len(assessments),
            "source_evidence_count": len(source_evidence),
        }

    def commit_revision(
        self,
        derived: dict[str, Any],
        session: dict[str, Any],
        learner: dict[str, Any],
        review_queue: dict[str, Any] | None = None,
        course: dict[str, Any] | None = None,
        syllabus: dict[str, Any] | None = None,
    ) -> RevisionManifest:
        self.initialize()
        revision = self._next_revision()
        with tempfile.TemporaryDirectory(dir=self.revisions_path, prefix=".revision-") as temp_name:
            temp_path = Path(temp_name)
            derived_name = self._derived_filename(derived)
            self._write_json(temp_path / derived_name, derived)
            self._write_json(temp_path / "session.json", session)
            self._write_json(temp_path / "learner.json", learner)
            revision_files = [derived_name, "session.json", "learner.json"]
            if review_queue is not None:
                self._write_json(temp_path / "review_queue.json", review_queue)
                revision_files.append("review_queue.json")
            events = self.read_complete_observations()
            log_offset = self.observations_path.stat().st_size
            canonical_inputs = self.canonical_input_fingerprints(course, syllabus)
            schema_versions = {
                "course": course.get("schema_version") if course else None,
                "syllabus": syllabus.get("schema_version") if syllabus else None,
                "derived": derived.get("schema_version"),
                "observations": sorted(
                    {event.get("schema_version") for event in events}
                    - {None}
                ),
                "assessments": sorted(
                    {item.get("schema_version") for item in self.read_assessments()}
                    - {None}
                ),
            }
            manifest_data = {
                "schema_version": 2,
                "revision": revision,
                "last_complete_observation_id": events[-1]["observation_id"] if events else None,
                "last_complete_observation_line": len(events),
                "log_byte_offset": log_offset,
                # Fingerprints of the canonical inputs this revision was
                # derived from. A later load compares current course.json/
                # syllabus.json against these to detect that a canonical
                # input changed (e.g. exam date, scheduler policy, syllabus
                # prerequisites/importance) even when the concept-id set and
                # the observation log did not - which alone would otherwise
                # look "not stale" and keep serving derived state computed
                # against the old inputs.
                "course_hash": self.hash_document(course) if course is not None else None,
                "syllabus_hash": self.hash_document(syllabus) if syllabus is not None else None,
                "canonical_inputs": canonical_inputs,
            "schema_versions": schema_versions,
                "derived_snapshot_hash": self._hash_file(temp_path / derived_name),
                "derived_hashes": {
                    name: self._hash_file(temp_path / name)
                    for name in revision_files
                },
            }
            self._write_json(temp_path / "manifest.json", manifest_data)
            revision_path = self.revisions_path / f"{revision:06d}"
            os.replace(temp_path, revision_path)

        pointer = {"schema_version": 2, "revision": revision}
        pointer_temp = self.state_path / ".current.json.tmp"
        self._write_json(pointer_temp, pointer)
        os.replace(pointer_temp, self.current_path)
        for name, value in (
            (self._derived_filename(derived), derived),
            ("session.json", session),
            ("learner.json", learner),
        ):
            self._write_json(self.state_path / name, value)
        if review_queue is not None:
            self._write_json(self.state_path / "review_queue.json", review_queue)
        return RevisionManifest(revision, manifest_data)

    def _load_revision(self, revision_path: Path) -> RecoveryResult | None:
        manifest_path = revision_path / "manifest.json"
        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            validate_document(manifest_data, load_schema("revision-manifest.schema.json"))
            if int(manifest_data["revision"]) != int(revision_path.name):
                return None
            for name, expected_hash in manifest_data["derived_hashes"].items():
                if self._hash_file(revision_path / name) != expected_hash:
                    return None
            derived_name = (
                "targets.json"
                if (revision_path / "targets.json").exists()
                else "concepts.json"
            )
            derived = json.loads((revision_path / derived_name).read_text(encoding="utf-8"))
            session = json.loads((revision_path / "session.json").read_text(encoding="utf-8"))
            learner = json.loads((revision_path / "learner.json").read_text(encoding="utf-8"))
            review_path = revision_path / "review_queue.json"
            review_queue = (
                json.loads(review_path.read_text(encoding="utf-8"))
                if review_path.exists()
                else None
            )
            return RecoveryResult(
                RevisionManifest(int(manifest_data["revision"]), manifest_data),
                revision_path,
                derived,
                session,
                learner,
                review_queue,
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def recover(self) -> RecoveryResult:
        self.initialize()
        candidates: list[Path] = []
        try:
            pointer = json.loads(self.current_path.read_text(encoding="utf-8"))
            validate_document(pointer, load_schema("current.schema.json"))
            candidates.append(self.revisions_path / f"{int(pointer['revision']):06d}")
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            pass
        candidates.extend(
            sorted(
                (
                    path
                    for path in self.revisions_path.iterdir()
                    if path.is_dir() and path.name.isdigit()
                ),
                reverse=True,
            )
        )
        seen: set[Path] = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            result = self._load_revision(candidate)
            if result is not None:
                return result
        raise FileNotFoundError("no valid revision is available for recovery")

    def try_recover(self) -> RecoveryResult | None:
        """Like recover(), but returns None instead of raising when no
        revision exists yet (a brand-new or fully-corrupted workspace)."""
        try:
            return self.recover()
        except FileNotFoundError:
            return None

    def rebuild_from_log(self) -> dict[str, Any]:
        self.initialize()
        def read_optional(name: str) -> dict[str, Any] | None:
            path = self.state_path / name
            if not path.exists():
                return None
            return json.loads(path.read_text(encoding="utf-8"))

        return {
            "course": read_optional("course.json"),
            "syllabus": read_optional("syllabus.json"),
            "observations": self.read_complete_observations(),
        }

