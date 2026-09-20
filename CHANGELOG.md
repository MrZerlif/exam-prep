# Changelog

## Unreleased

- Material ingestion now excludes lecture and notes sources from question extraction by default, requires explicit opt-in for unclassified sources, and records extraction anomalies instead of silently accepting suspicious output.
- The `extraction_anomaly` prose ratio is now measured over label segments instead of non-empty lines, and only marks `exam` and `homework` sources as blocking through the questions-per-page and hard-cap guards. Previously a problem set written one task per line scored a perfect ratio and was reported as blocking, which made `validate --readiness` return `blocked` for the most common exam-paper layout. Lecture, notes, and unclassified sources keep the ratio check unchanged.

## 0.4.0

- Added local material extraction, deterministic indexing, hydration, and source evidence.
- Added extracted-question drafts, target finalization, pool isolation, figures, and answer gates.
- Added readiness, scheduler modes, provenance labels, review projections, hints, and release workflows.
