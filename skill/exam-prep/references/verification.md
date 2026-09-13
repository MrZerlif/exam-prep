# Mathematical verification protocol

The verifier is a second-pass guard against tutor arithmetic mistakes. It is
not a substitute for checking assumptions or explaining a proof.

## Core stdlib checks

Use scripts/exam_prep.py verify for:

- restricted safe expression parsing;
- numeric samples away from singularities;
- substitution and arithmetic recomputation;
- denominator/domain checks;
- derivative finite-difference comparison with local slopes;
- antiderivative finite-difference comparison of the proposed antiderivative's
  numerical derivative with the integrand;
- numerical sanity checks.

An antiderivative finite-difference pass is numerical consistency evidence, not
a symbolic proof. Report failed or inconclusive checks rather than inventing
certainty. If no safe sample remains, ask for domain information or mark the
check inconclusive.

## Optional CAS

Symbolic differentiation, exact simplification, algebraic equivalence, and
exact domain reasoning belong only to the optional CAS adapter. A missing CAS
returns unavailable and never blocks the stdlib tutor. Even a symbolic pass
does not remove the need to state domain and validity conditions.

