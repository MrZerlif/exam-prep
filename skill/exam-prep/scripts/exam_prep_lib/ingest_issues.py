"""Structured, persisted diagnostics produced while ingesting materials."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

IssueKind = Literal[
    "missing_answer",
    "missing_figure",
    "bad_pdf_extraction",
    "ambiguous_crop",
    "source_conflict",
    "unsupported_page",
    "insufficient_evidence",
    "extraction_anomaly",
    "no_questions_extracted",
    "unclassified_source",
    "unsupported_language",
    "low_confidence_question",
]
IssueSeverity = Literal["blocking", "gap", "info"]

ISSUE_KINDS = frozenset(
    {
        "missing_answer",
        "missing_figure",
        "bad_pdf_extraction",
        "ambiguous_crop",
        "source_conflict",
        "unsupported_page",
        "insufficient_evidence",
        "extraction_anomaly",
        "no_questions_extracted",
        "unclassified_source",
        "unsupported_language",
        "low_confidence_question",
    }
)
ISSUE_SEVERITIES = frozenset({"blocking", "gap", "info"})


@dataclass(frozen=True)
class IngestIssue:
    kind: IssueKind | str
    source_id: str | None
    detail: str
    severity: IssueSeverity | str

    def __post_init__(self) -> None:
        if self.kind not in ISSUE_KINDS:
            raise ValueError(f"unknown ingest issue kind: {self.kind!r}")
        if self.severity not in ISSUE_SEVERITIES:
            raise ValueError(f"unknown ingest issue severity: {self.severity!r}")
        if not isinstance(self.detail, str) or not self.detail.strip():
            raise ValueError("ingest issue detail must be a non-empty string")

    def to_mapping(self) -> dict[str, str | None]:
        return {
            "kind": str(self.kind),
            "source_id": self.source_id,
            "detail": self.detail,
            "severity": str(self.severity),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "IngestIssue":
        return cls(
            str(value.get("kind", "")),
            value.get("source_id") if value.get("source_id") is None else str(value["source_id"]),
            str(value.get("detail", "")),
            str(value.get("severity", "")),
        )
