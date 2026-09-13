import sys
import unittest


sys.path.insert(0, "scripts")

from math_study_lib import symbolic_backend  # noqa: E402
from math_study_lib.verifier import (  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
