"""Open assessment-capability registry with a safe unknown fallback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class AssessmentCapability:
    capability_id: str
    affected_dimensions: tuple[str, ...]
    response_type: str
    review_kind: str
    evidence_requirements: tuple[str, ...]
    verifier_id: str | None = None
    is_registered: bool = True

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
    def __init__(self, capabilities: Mapping[str, AssessmentCapability] | None = None):
        self._capabilities = dict(capabilities or {})

    @classmethod
    def with_defaults(cls) -> "CapabilityRegistry":
        dimensions = {
            "definition_recall": ("conceptual", "recall"),
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
            "delayed_recall": ("recall", "transfer"),
        }
        return cls(
            {
                task_type: AssessmentCapability(
                    capability_id=task_type,
                    affected_dimensions=affected_dimensions,
                    response_type="structured_observation",
                    review_kind=task_type,
                    evidence_requirements=("independent",),
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
            registry.register(
                AssessmentCapability(
                    capability_id=str(descriptor.get("capability_id") or key),
                    affected_dimensions=tuple(
                        str(value) for value in descriptor.get("affected_dimensions", ())
                    ),
                    response_type=str(descriptor.get("response_type", "structured_observation")),
                    review_kind=str(descriptor.get("review_kind", "custom_assessment")),
                    evidence_requirements=tuple(
                        str(value) for value in descriptor.get("evidence_requirements", ())
                    ),
                    verifier_id=descriptor.get("verifier_id"),
                )
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

