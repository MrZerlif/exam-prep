"""Safe numerical consistency checks for elementary calculus expressions."""

from __future__ import annotations

import ast
import math
import operator
from dataclasses import dataclass
from typing import Any


class UnsafeExpression(ValueError):
    """Expression contains syntax outside the numeric whitelist."""


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    status: str
    checks: dict[str, Any]
    message: str = ""


FUNCTIONS = {
    name: getattr(math, name)
    for name in ("sin", "cos", "tan", "exp", "log", "sqrt", "fabs")
}
FUNCTIONS["abs"] = abs
OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}

DEFAULT_SAMPLES: tuple[float, ...] = (-2.0, -1.0, -0.5, 0.5, 1.0, 2.0)
DEFAULT_TOLERANCE = 1e-4
MAX_EXPRESSION_DEPTH = 100


def _checked_samples(samples: Any) -> list[float]:
    if not isinstance(samples, (list, tuple)):
        raise ValueError("samples must be a list of numbers")
    checked: list[float] = []
    for sample in samples:
        if (
            isinstance(sample, bool)
            or not isinstance(sample, (int, float))
            or not math.isfinite(sample)
        ):
            raise ValueError(f"sample {sample!r} is not a finite number")
        checked.append(float(sample))
    return checked


def _checked_tolerance(tolerance: Any) -> float:
    if (
        isinstance(tolerance, bool)
        or not isinstance(tolerance, (int, float))
        or not math.isfinite(tolerance)
        or tolerance <= 0
    ):
        raise ValueError(f"tolerance {tolerance!r} must be a positive finite number")
    return float(tolerance)


def _tree_depth(tree: ast.Expression) -> int:
    max_depth = 0
    stack: list[tuple[ast.AST, int]] = [(tree, 1)]
    while stack:
        node, depth = stack.pop()
        if depth > max_depth:
            max_depth = depth
        for child in ast.iter_child_nodes(node):
            stack.append((child, depth + 1))
    return max_depth


def _tree(expression: str) -> ast.Expression:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise UnsafeExpression("invalid expression syntax") from exc
    except (RecursionError, MemoryError) as exc:
        raise UnsafeExpression("expression is nested too deeply") from exc
    if _tree_depth(tree) > MAX_EXPRESSION_DEPTH:
        raise UnsafeExpression("expression is nested too deeply")
    return tree


def _evaluate(node: ast.AST, variable: str, value: float) -> float:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body, variable, value)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        raise UnsafeExpression("only numeric constants are allowed")
    if isinstance(node, ast.Name):
        if node.id == variable:
            return float(value)
        if node.id == "pi":
            return math.pi
        if node.id == "e":
            return math.e
        raise UnsafeExpression(f"name {node.id!r} is not allowed")
    if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY_OPERATORS:
        return UNARY_OPERATORS[type(node.op)](_evaluate(node.operand, variable, value))
    if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
        left = _evaluate(node.left, variable, value)
        right = _evaluate(node.right, variable, value)
        result = OPERATORS[type(node.op)](left, right)
        if isinstance(result, complex):
            raise ValueError("expression leaves the real domain at this sample")
        return result
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id not in FUNCTIONS or node.keywords:
            raise UnsafeExpression("function or keyword is not allowed")
        if len(node.args) != 1:
            raise UnsafeExpression("only one-argument math functions are allowed")
        return FUNCTIONS[node.func.id](_evaluate(node.args[0], variable, value))
    raise UnsafeExpression(f"syntax node {type(node).__name__} is not allowed")


def _safe_value(tree: ast.Expression, variable: str, value: float) -> float:
    result = _evaluate(tree, variable, value)
    if not math.isfinite(result):
        raise ValueError("non-finite numeric result")
    return result


def _result(errors: list[float], tolerance: float) -> VerificationResult:
    if not errors:
        return VerificationResult(
            False,
            "inconclusive",
            {"finite_difference": {"passed": False, "samples": 0}},
            "no safe numeric samples were available",
        )
    passed = all(error <= tolerance for error in errors)
    return VerificationResult(
        passed,
        "passed" if passed else "failed",
        {
            "finite_difference": {
                "passed": passed,
                "samples": len(errors),
                "max_absolute_error": max(errors),
                "tolerance": tolerance,
            }
        },
    )


def _finite_difference(
    left_expression: str,
    right_expression: str,
    variable: str,
    samples: list[float],
    tolerance: float,
) -> VerificationResult:
    samples = _checked_samples(samples)
    tolerance = _checked_tolerance(tolerance)
    left_tree = _tree(left_expression)
    right_tree = _tree(right_expression)
    errors: list[float] = []
    for sample in samples:
        x = float(sample)
        h = max(1e-6, abs(x) * 1e-5)
        try:
            slope = (
                _safe_value(left_tree, variable, x + h)
                - _safe_value(left_tree, variable, x - h)
            ) / (2.0 * h)
            proposed = _safe_value(right_tree, variable, x)
            errors.append(abs(slope - proposed) / max(1.0, abs(slope), abs(proposed)))
        except UnsafeExpression:
            raise
        except (ArithmeticError, ValueError, OverflowError):
            continue
    return _result(errors, tolerance)


def verify_derivative(
    expression: str,
    derivative: str,
    variable: str,
    samples: list[float],
    tolerance: float,
) -> VerificationResult:
    return _finite_difference(expression, derivative, variable, samples, tolerance)


def verify_antiderivative(
    integrand: str,
    antiderivative: str,
    variable: str,
    samples: list[float],
    tolerance: float,
) -> VerificationResult:
    return _finite_difference(antiderivative, integrand, variable, samples, tolerance)

