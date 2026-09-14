"""Optional verifier registry resolved by capability descriptors."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .capabilities import CapabilityRegistry


class VerifierRegistry:
    def __init__(self):
        self._verifiers: dict[str, Callable[[dict[str, Any]], Any]] = {}

    @classmethod
    def with_defaults(cls) -> "VerifierRegistry":
        from dataclasses import asdict

        from .verifier import verify_antiderivative, verify_derivative

        def numerical(request: dict[str, Any]) -> dict[str, Any]:
            kind = request.get("kind", "derivative")
            if kind == "antiderivative":
                result = verify_antiderivative(
                    request["integrand"],
                    request["antiderivative"],
                    request.get("variable", "x"),
                    request.get("samples", [-2.0, -1.0, 1.0, 2.0]),
                    request.get("tolerance", 1e-3),
                )
            elif kind == "derivative":
                result = verify_derivative(
                    request["expression"],
                    request["derivative"],
                    request.get("variable", "x"),
                    request.get("samples", [-2.0, -1.0, 1.0, 2.0]),
                    request.get("tolerance", 1e-3),
                )
            else:
                return {
                    "status": "unavailable",
                    "reason": f"unsupported numerical verification kind: {kind}",
                }
            return asdict(result)

        registry = cls()
        registry.register("math.numerical", numerical)
        registry.register(
            "derivative", lambda request: numerical({**request, "kind": "derivative"})
        )
        registry.register(
            "antiderivative",
            lambda request: numerical({**request, "kind": "antiderivative"}),
        )
        return registry

    def register(self, verifier_id: str, verifier: Callable[[dict[str, Any]], Any]) -> None:
        if not verifier_id:
            raise ValueError("verifier_id must not be empty")
        self._verifiers[verifier_id] = verifier

    def resolve(self, verifier_id: str | None) -> Callable[[dict[str, Any]], Any] | None:
        return self._verifiers.get(verifier_id) if verifier_id else None

    def verify(self, verifier_id: str | None, request: dict[str, Any]) -> Any:
        verifier = self.resolve(verifier_id)
        if verifier is None:
            return {"status": "unavailable", "reason": "no verifier registered"}
        return verifier(request)


def verify_request(
    request: Mapping[str, Any],
    *,
    capability_registry: CapabilityRegistry | None = None,
    verifier_registry: VerifierRegistry | None = None,
) -> dict[str, Any]:
    """Verify through a capability descriptor, with legacy kind adapters."""

    normalized = dict(request)
    registry = verifier_registry or VerifierRegistry.with_defaults()
    capability_id = normalized.get("capability_id")
    if capability_id is not None:
        if capability_registry is None:
            raw_syllabus = normalized.get("syllabus")
            if not isinstance(raw_syllabus, Mapping):
                raw_syllabus = (
                    normalized
                    if isinstance(normalized.get("assessment_capabilities"), Mapping)
                    else {}
                )
            capability_registry = (
                CapabilityRegistry.from_syllabus(raw_syllabus)
                if raw_syllabus
                else CapabilityRegistry.with_defaults()
            )
        resolution = capability_registry.resolve(str(capability_id))
        if not resolution.capability.is_registered:
            return {
                "status": "unavailable",
                "reason": resolution.warning or "unregistered assessment capability",
            }
        verifier_id = resolution.capability.verifier_id
    else:
        verifier_id = normalized.get("verifier_id")
        if verifier_id is None and normalized.get("kind") in {
            "derivative",
            "antiderivative",
        }:
            verifier_id = normalized["kind"]
    return registry.verify(verifier_id, normalized)
