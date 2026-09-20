# Changelog

## Unreleased

- Material ingestion now excludes lecture and notes sources from question extraction by default, requires explicit opt-in for unclassified sources, and records extraction anomalies instead of silently accepting suspicious output.
- `expected_total_points` now defaults to null instead of 100, in the course template, the built-in defaults, and the `extract_questions` signature. A course that never declared a point total no longer has every question flagged `low_confidence_question` for failing to add up to a number nobody chose. The draft command now passes the course's own value through, so the check verifies what the course actually declares; `validate` reports an informational `expected_total_points` row when a workspace still carries the template's 100 and its materials declare a different total. Existing workspaces are not migrated, since a stored 100 cannot be told apart from a deliberate one.
- The material index records the point total inferred per graded source under `points`, which is what lets `validate` compare against the course without reading the materials directory.
- The `extraction_anomaly` prose ratio is now measured over label segments instead of non-empty lines, and only marks `exam` and `homework` sources as blocking through the questions-per-page and hard-cap guards. Previously a problem set written one task per line scored a perfect ratio and was reported as blocking, which made `validate --readiness` return `blocked` for the most common exam-paper layout. Lecture, notes, and unclassified sources keep the ratio check unchanged.

## 0.4.0

- Added local material extraction, deterministic indexing, hydration, and source evidence.
- Added extracted-question drafts, target finalization, pool isolation, figures, and answer gates.
- Added readiness, scheduler modes, provenance labels, review projections, hints, and release workflows.
