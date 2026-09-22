import sys
import unittest


sys.path.insert(0, "skill/exam-prep/scripts")

from exam_prep_lib import symbolic_backend  # noqa: E402
from exam_prep_lib.verifier import (  # noqa: E402
    DEFAULT_SAMPLES,
    DEFAULT_TOLERANCE,
    MAX_EXPRESSION_DEPTH,
    UnsafeExpression,
    verify_antiderivative,
    verify_derivative,
)


class VerifierTests(unittest.TestCase):
    def test_derivative_finite_difference_passes(self):
        result = verify_derivative("x**2", "2*x", "x", [0.5, 1.5], 1e-4)
        self.assertTrue(result.passed)
        self.assertIn("finite_difference", result.checks)

    def test_derivative_finite_difference_rejects_wrong_answer(self):
        result = verify_derivative("x**2", "x", "x", [0.5, 1.5], 1e-4)
        self.assertFalse(result.passed)
        self.assertEqual(result.status, "failed")

    def test_antiderivative_uses_finite_difference(self):
        result = verify_antiderivative("2*x", "x**2", "x", [0.5, 1.5], 1e-4)
        self.assertTrue(result.passed)
        self.assertIn("finite_difference", result.checks)

    def test_antiderivative_finite_difference_rejects_wrong_answer(self):
        result = verify_antiderivative("2*x", "x**3", "x", [0.5, 1.5], 1e-4)
        self.assertFalse(result.passed)

    def test_unsafe_expression_is_rejected(self):
        with self.assertRaises(UnsafeExpression):
            verify_derivative("__import__('os').system('whoami')", "0", "x", [1.0], 1e-4)

    def test_no_safe_sample_is_inconclusive(self):
        result = verify_derivative("1/x", "-1/x**2", "x", [0.0], 1e-4)
        self.assertFalse(result.passed)
        self.assertEqual(result.status, "inconclusive")

    def test_symbolic_backend_is_optional(self):
        result = symbolic_backend.verify({"kind": "derivative", "expression": "x**2"})
        self.assertIn(result["status"], {"unavailable", "passed", "failed", "inconclusive"})
        self.assertNotIn("sympy", result.get("backend", "").lower())

    def test_fractional_power_of_negative_sample_is_skipped(self):
        result = verify_derivative("x**(1/3)", "(1/3)*x**(-2/3)", "x", [-1.0, 1.0], 1e-4)
        self.assertTrue(result.passed)
        self.assertEqual(1, result.checks["finite_difference"]["samples"])

    def test_complex_intermediate_never_reaches_abs(self):
        result = verify_derivative("abs(x**0.5)", "0.5*abs(x)**(-0.5)", "x", [-4.0, -1.0], 1e-4)
        self.assertEqual("inconclusive", result.status)

    def test_invalid_samples_or_tolerance_raise_value_error(self):
        cases = (
            ([1.0], "abc"),
            ([1.0], 0),
            ([1.0], float("nan")),
            (["a"], 1e-4),
            ("1.0", 1e-4),
            ([True], 1e-4),
        )
        for samples, tolerance in cases:
            with self.subTest(samples=samples, tolerance=tolerance):
                with self.assertRaises(ValueError):
                    verify_derivative("x**2", "2*x", "x", samples, tolerance)

    def test_deeply_nested_expression_is_unsafe(self):
        for depth in (150, 1500, 5000):
            with self.subTest(depth=depth):
                with self.assertRaises(UnsafeExpression):
                    verify_derivative("-" * depth + "x", "1", "x", [1.0], 1e-4)

    def test_ordinary_nesting_is_still_accepted(self):
        self.assertLess(40, MAX_EXPRESSION_DEPTH)
        result = verify_derivative("-" * 40 + "x", "1", "x", [1.0, 2.0], 1e-4)
        self.assertEqual("passed", result.status)
        result = verify_derivative(
            "sin(cos(exp(x)))",
            "-cos(cos(exp(x)))*sin(exp(x))*exp(x)",
            "x",
            [0.1, 0.5],
            1e-4,
        )
        self.assertEqual("passed", result.status)

    def test_default_samples_include_negative_inputs(self):
        self.assertTrue(any(sample < 0 for sample in DEFAULT_SAMPLES))
        result = verify_derivative("abs(x)", "1", "x", list(DEFAULT_SAMPLES), DEFAULT_TOLERANCE)
        self.assertEqual("failed", result.status)


if __name__ == "__main__":
    unittest.main()
