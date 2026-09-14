"""Open assessment-capability registry with a safe unknown fallback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class AssessmentCapability:
    capability_id: str
    affected_dimensions: tuple[str, ...]
    response_type: str
    review_kind: str
    evidence_requirements: tuple[str, ...]
    verifier_id: str | None = None
    is_registered: bool = True

    def supports_dimension(self, dimension: str) -> bool:
        return self.is_registered and dimension in self.affected_dimensions

    def requires_evidence(self, evidence: str) -> bool:
        return self.is_registered and evidence in self.evidence_requirements

    def demonstrates_transfer(self) -> bool:
        return self.is_registered and (
            self.supports_dimension("transfer")
            or self.requires_evidence("transfer")
            or self.requires_evidence("transferred")
            or self.review_kind in {"transfer", "exam_problem"}
            or self.capability_id in {"transfer", "exam_problem"}
        )

    def demonstrates_retention(self) -> bool:
        return self.is_registered and (
            self.requires_evidence("retained")
            or self.requires_evidence("delayed_recall")
            or self.review_kind in {"delayed_recall", "delayed_transfer"}
            or self.capability_id in {"delayed_recall", "delayed_transfer"}
        )

    def counts_as_exam_success(self, question_model: str | None = None) -> bool:
        if not self.is_registered:
            return False
        if (
            self.requires_evidence("exam")
            or self.requires_evidence("exam_problem")
            or self.review_kind == "exam_problem"
            or self.capability_id == "exam_problem"
        ):
            return True
        # For a ticket_list exam, the exam itself *is* independently
        # reproducing a memorized ticket - the same act delayed_recall/
        # delayed_transfer already measure. Derived from the blueprint
        # rather than a hardcoded id set, per 2.3: a written problem_set
        # exam must not get this credit, since reciting a ticket from
        # memory is not what it tests.
        if question_model == "ticket_list" and self.capability_id in {
            "delayed_recall",
            "delayed_transfer",
        }:
            return True
        return False

    @classmethod
    def unknown(cls, capability_id: str) -> "AssessmentCapability":
        return cls(
            capability_id=capability_id,
            affected_dimensions=(),
            response_type="unclassified",
            review_kind="unmapped_assessment",
            evidence_requirements=(),
            verifier_id=None,
            is_registered=False,
        )


@dataclass(frozen=True)
class CapabilityResolution:
    capability: AssessmentCapability
    warning: str | None = None


class CapabilityRegistry:
    def __init__(
        self,
        capabilities: Mapping[str, AssessmentCapability] | None = None,
        *,
        rejected: Iterable[str] | None = None,
    ):
        self._capabilities = dict(capabilities or {})
        self._rejected_descriptors: tuple[str, ...] = tuple(rejected or ())

    def rejected_descriptors(self) -> tuple[str, ...]:
        """Descriptors dropped during `from_syllabus` registration - each a
        human-readable reason, e.g. an unknown affected dimension. Callers
        that build a registry from user-supplied data (status, validate)
        surface these instead of letting bad capabilities vanish silently."""
        return self._rejected_descriptors

    @classmethod
    def with_defaults(cls) -> "CapabilityRegistry":
        dimensions = {
            "definition_recall": ("conceptual", "recall"),
            "calculation": ("procedural",),
            "formula_reading": ("recall",),
            "recognition": ("conceptual", "recall"),
            "explanation": ("conceptual",),
            "error_detection": ("conceptual", "procedural"),
            "worked_example": ("conceptual", "procedural"),
            "faded_example": ("procedural",),
            "guided_problem": ("procedural",),
            "independent_problem": ("procedural",),
            "transfer": ("procedural", "transfer"),
            "exam_problem": ("procedural", "transfer"),
            # Keep in sync with reducer.TASK_DIMENSIONS - see the comment
            # there. test_capabilities.py's
            # test_task_dimensions_and_default_capability_registry_agree
            # fails if this drifts from that mapping.
            "delayed_recall": ("recall",),
            "delayed_transfer": ("recall", "transfer"),
        }
        return cls(
            {
                task_type: AssessmentCapability(
                    capability_id=task_type,
                    affected_dimensions=affected_dimensions,
                    response_type="structured_observation",
                    review_kind=task_type,
                    evidence_requirements=("independent",),
                    verifier_id="math.numerical" if task_type == "calculation" else None,
                )
                for task_type, affected_dimensions in dimensions.items()
            }
        )

    @classmethod
    def from_syllabus(cls, syllabus: Mapping[str, Any]) -> "CapabilityRegistry":
        registry = cls.with_defaults()
        raw = syllabus.get("assessment_capabilities", syllabus.get("capabilities", {}))
        if isinstance(raw, Mapping):
            entries = raw.items()
        elif isinstance(raw, list):
            entries = (
                (
                    item.get("capability_id") or item.get("id"),
                    item,
                )
                for item in raw
                if isinstance(item, Mapping)
            )
        else:
            entries = ()
        for key, descriptor in entries:
            if not key or not isinstance(descriptor, Mapping):
                continue
            raw_dimensions = descriptor.get("affected_dimensions", ())
            if not isinstance(raw_dimensions, (list, tuple)) or any(
                str(dimension) not in MASTERY_DIMENSIONS
                for dimension in raw_dimensions
            ):
                continue
            registry.register(
                AssessmentCapability(
                    capability_id=str(descriptor.get("capability_id") or key),
                    affected_dimensions=tuple(str(value) for value in raw_dimensions),
                    response_type=str(descriptor.get("response_type", "structured_observation")),
                    review_kind=str(descriptor.get("review_kind", "custom_assessment")),
                    evidence_requirements=tuple(
                        str(value) for value in descriptor.get("evidence_requirements", ())
                    ),
                    verifier_id=descriptor.get("verifier_id"),
                )
            )
        registry._rejected_descriptors = tuple(
            capability_dimension_issues({"assessment_capabilities": raw})
        )
        return registry

    def register(self, capability: AssessmentCapability) -> None:
        if not capability.capability_id:
            raise ValueError("capability_id must not be empty")
        self._capabilities[capability.capability_id] = capability

    def resolve(self, capability_id: str | None) -> CapabilityResolution:
        identifier = str(capability_id) if capability_id is not None else ""
        capability = self._capabilities.get(identifier)
        if capability is not None:
            return CapabilityResolution(capability=capability)
        unknown = AssessmentCapability.unknown(identifier)
        return CapabilityResolution(
            capability=unknown,
            warning=f"unregistered assessment capability: {identifier or '<missing>'}",
        )

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._capabilities))

MASTERY_DIMENSIONS = (
    "conceptual",
    "procedural",
    "recall",
    "transfer",
    "speed",
)


def capability_dimension_issues(document: Mapping[str, Any]) -> list[str]:
    raw = document.get("assessment_capabilities", document.get("capabilities", {}))
    if isinstance(raw, Mapping):
        descriptors = raw.items()
    elif isinstance(raw, list):
        descriptors = (
            (item.get("capability_id") or item.get("id"), item)
            for item in raw
            if isinstance(item, Mapping)
        )
    else:
        return []
    issues: list[str] = []
    for key, descriptor in descriptors:
        if not isinstance(descriptor, Mapping):
            continue
        capability_id = str(descriptor.get("capability_id") or descriptor.get("id") or key)
        raw_dimensions = descriptor.get("affected_dimensions", ())
        if not isinstance(raw_dimensions, (list, tuple)):
            issues.append(
                f"capability '{capability_id}' affected_dimensions must be an array"
            )
            continue
        for dimension in raw_dimensions:
            value = str(dimension)
            if value not in MASTERY_DIMENSIONS:
                issues.append(
                    f"capability '{capability_id}' has unknown affected dimension '{value}'"
                )
    return issues
