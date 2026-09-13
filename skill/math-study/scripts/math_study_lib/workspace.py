"""Workspace and runtime-path resolution for the exam-prep engine."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class RuntimePaths:
    """Canonical flat runtime layout.

    The package keeps the old StudyStore implementation available during
    migration, while new callers can use this stable, product-neutral layout.
    """

    workspace: Path
    root: Path

    @property
    def course(self) -> Path:
        return self.root / "course.json"

    @property
    def syllabus(self) -> Path:
        return self.root / "syllabus.json"

    @property
    def sources(self) -> Path:
        return self.root / "sources.json"

    @property
    def observations(self) -> Path:
        return self.root / "observations.jsonl"

    @property
    def assessments(self) -> Path:
        return self.root / "assessments.jsonl"

    @property
    def sessions(self) -> Path:
        return self.root / "sessions.jsonl"

    @property
    def targets(self) -> Path:
        return self.root / "targets.json"

    @property
    def review_queue(self) -> Path:
        return self.root / "review_queue.json"

    @property
    def learner(self) -> Path:
        return self.root / "learner.json"

    @property
    def session(self) -> Path:
        return self.root / "session.json"

    @property
    def current(self) -> Path:
        return self.root / "current.json"

    @property
    def migration(self) -> Path:
        return self.root / "migration.json"

    @property
    def revisions(self) -> Path:
        return self.root / "revisions"

    @property
    def recovery(self) -> Path:
        return self.root / "recovery"


def discover_git_root(cwd: str | Path | None = None) -> Path | None:
    """Return the nearest directory containing .git, if one exists."""

    candidate = Path(cwd or Path.cwd()).expanduser().resolve()
    if candidate.is_file():
        candidate = candidate.parent
    for parent in (candidate, *candidate.parents):
        if (parent / ".git").exists():
            return parent
    return None


def resolve_workspace(
    explicit: str | Path | None = None,
    *,
    environment: Mapping[str, str] | None = None,
    git_root: str | Path | None = None,
    cwd: str | Path | None = None,
) -> Path:
    """Resolve workspace with explicit, environment, git-root, cwd precedence."""

    if explicit:
        return Path(explicit).expanduser().resolve()

    env = os.environ if environment is None else environment
    for name in (
        "EXAM_PREP_WORKSPACE",
        "MATH_STUDY_WORKSPACE",
        "EXAM_PREP_PROJECT_ROOT",
        "PROJECT_ROOT",
        "WORKSPACE_ROOT",
    ):
        value = env.get(name)
        if value:
            return Path(value).expanduser().resolve()

    if git_root:
        return Path(git_root).expanduser().resolve()
    return (Path(cwd) if cwd is not None else Path.cwd()).expanduser().resolve()


def runtime_paths(workspace: str | Path) -> RuntimePaths:
    workspace_path = Path(workspace).expanduser().resolve()
    return RuntimePaths(workspace=workspace_path, root=workspace_path / ".exam-prep")
