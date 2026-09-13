"""Optional verifier registry resolved by capability descriptors."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class VerifierRegistry:
    def __init__(self):
        self._verifiers: dict[str, Callable[[dict[str, Any]], Any]] = {}

    @classmethod
    def with_defaults(cls) -> "VerifierRegistry":
        from dataclasses import asdict

        from .verifier import verify_antiderivative, verify_derivative

        registry = cls()
        registry.register(
            "derivative",
            lambda request: asdict(
                verify_derivative(
                    request["expression"],
                    request["derivative"],
                    request.get("variable", "x"),
                    request.get("samples", [-2.0, -1.0, 1.0, 2.0]),
                    request.get("tolerance", 1e-3),
                )
            ),
        )
        registry.register(
            "antiderivative",
            lambda request: asdict(
                verify_antiderivative(
                    request["integrand"],
                    request["antiderivative"],
                    request.get("variable", "x"),
                    request.get("samples", [-2.0, -1.0, 1.0, 2.0]),
                    request.get("tolerance", 1e-3),
                )
            ),
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
