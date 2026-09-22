# Mathematics-specific verification protocol

The verifier is a second-pass guard against tutor arithmetic mistakes. It is
not a substitute for checking assumptions or explaining a proof.

## Core stdlib checks

Use scripts/exam_prep.py verify for:

- restricted safe expression parsing: numbers, the request's variable, `pi`,
  `e`, `+ - * / **`, and one-argument `sin`, `cos`, `tan`, `exp`, `log`,
  `sqrt`, `fabs`, `abs`, nested at most 100 levels deep;
- sample skipping: a sample is dropped when either side is undefined there
  (division by zero, a `log`/`sqrt` domain error, a complex intermediate such
  as a fractional power of a negative number, or a non-finite result);
- derivative finite-difference comparison with local slopes;
- antiderivative finite-difference comparison of the proposed antiderivative's
  numerical derivative with the integrand.

Omitted `samples` default to `-2, -1, -0.5, 0.5, 1, 2`; omitted `tolerance`
defaults to a relative `1e-4`. Invalid samples, tolerance, or missing
expression fields are rejected as an error rather than reported as a failed
check.

An antiderivative finite-difference pass is numerical consistency evidence, not
a symbolic proof. Report failed or inconclusive checks rather than inventing
certainty. If no safe sample remains, ask for domain information or mark the
check inconclusive.

## Optional CAS

Symbolic differentiation, exact simplification, algebraic equivalence, and
exact domain reasoning belong only to the optional CAS adapter. A missing CAS
returns unavailable and never blocks the stdlib tutor. Even a symbolic pass
does not remove the need to state domain and validity conditions.

