"""Append-only evidence storage and revision-based recovery."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schema_validation import validate_observation_proposal


class ObservationConflict(ValueError):
    """The same observation id was submitted with a different payload."""


@dataclass(frozen=True)
class AppendResult:
    observation_id: str
    canonical_event: dict[str, Any]
    appended: bool
    revision_created: int | None = None


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
        self.state_path = self.root / "state"
        self.observations_path = self.state_path / "observations.jsonl"
        self.revisions_path = self.state_path / "revisions"
        self.recovery_path = self.state_path / "recovery"
        self.current_path = self.state_path / "current.json"
        self._log_diagnostics = {"partial_final_line": False}

    def initialize(self) -> None:
        for path in (self.root, self.state_path, self.revisions_path, self.recovery_path):
            path.mkdir(parents=True, exist_ok=True)
        self.observations_path.touch(exist_ok=True)

    @staticmethod
    def _dump(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        path.write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    def read_complete_observations(self) -> list[dict[str, Any]]:
        self.initialize()
        raw = self.observations_path.read_bytes()
        lines = raw.splitlines(keepends=True)
        events: list[dict[str, Any]] = []
        self._log_diagnostics = {"partial_final_line": False}
        for index, line in enumerate(lines):
            if not line.strip():
                continue
            if index == len(lines) - 1 and not line.endswith((b"\n", b"\r")):
                self._log_diagnostics["partial_final_line"] = True
                continue
            try:
                event = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid complete observation line {index + 1}") from exc
            if not isinstance(event, dict):
                raise ValueError(f"observation line {index + 1} is not an object")
            events.append(event)
        return events

    def read_log_diagnostics(self) -> dict[str, bool]:
        self.read_complete_observations()
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
        canonical = dict(proposal)
        canonical.update(
            {
                "recorded_at": recorded_at,
                "session_id": session_id,
                "expected_seconds": expected_seconds,
                "elapsed_seconds": elapsed_seconds,
            }
        )
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

        self.observations_path.parent.mkdir(parents=True, exist_ok=True)
        line = (self._dump(canonical) + "\n").encode("utf-8")
        with self.observations_path.open("ab") as handle:
            handle.write(line)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
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

    def commit_revision(
        self,
        derived: dict[str, Any],
        session: dict[str, Any],
        learner: dict[str, Any],
        review_queue: dict[str, Any] | None = None,
    ) -> RevisionManifest:
        self.initialize()
        revision = self._next_revision()
        with tempfile.TemporaryDirectory(dir=self.revisions_path, prefix=".revision-") as temp_name:
            temp_path = Path(temp_name)
            self._write_json(temp_path / "concepts.json", derived)
            self._write_json(temp_path / "session.json", session)
            self._write_json(temp_path / "learner.json", learner)
            revision_files = ["concepts.json", "session.json", "learner.json"]
            if review_queue is not None:
                self._write_json(temp_path / "review_queue.json", review_queue)
                revision_files.append("review_queue.json")
            events = self.read_complete_observations()
            log_offset = self.observations_path.stat().st_size
            manifest_data = {
                "schema_version": 1,
                "revision": revision,
                "last_complete_observation_id": events[-1]["observation_id"] if events else None,
                "last_complete_observation_line": len(events),
                "log_byte_offset": log_offset,
                "derived_hashes": {
                    name: self._hash_file(temp_path / name)
                    for name in revision_files
                },
            }
            self._write_json(temp_path / "manifest.json", manifest_data)
            revision_path = self.revisions_path / f"{revision:06d}"
            os.replace(temp_path, revision_path)

        pointer = {"schema_version": 1, "revision": revision}
        pointer_temp = self.state_path / ".current.json.tmp"
        self._write_json(pointer_temp, pointer)
        os.replace(pointer_temp, self.current_path)
        for name, value in (
            ("concepts.json", derived),
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
            for name, expected_hash in manifest_data["derived_hashes"].items():
                if self._hash_file(revision_path / name) != expected_hash:
                    return None
            derived = json.loads((revision_path / "concepts.json").read_text(encoding="utf-8"))
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
