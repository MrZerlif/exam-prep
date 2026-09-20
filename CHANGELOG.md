# Changelog

## Unreleased

- Material ingestion now excludes lecture and notes sources from question extraction by default, requires explicit opt-in for unclassified sources, and records extraction anomalies instead of silently accepting suspicious output.
- A learned lexicon overlay may now declare `word_boundaries` and `normalization`. The overlay exists for languages outside the twelve bundled ones, and Thai, Khmer and Lao are written without spaces between words, so the schema previously refused the one thing those languages need. Where a bundled lexicon exists its rules still win and the overlay only contributes words; `apply-lexicon` keeps a declaration across merges, with the newest proposal winning.
- `draft-assessments` accepts `--include-lecture-exercises`, which finally gives `OPT_IN_KINDS` its meaning: lecture and notes sources could not be extracted by any flag before, although the constant claimed otherwise. Only the unambiguous `accept` candidates are taken from them, so a heading or a table-of-contents line is not mistaken for an exercise; each resulting question carries an informational issue naming its source and is always `practice`, never mock. `--include-unclassified` is unchanged.
- `expected_total_points` now defaults to null instead of 100, in the course template, the built-in defaults, and the `extract_questions` signature. A course that never declared a point total no longer has every question flagged `low_confidence_question` for failing to add up to a number nobody chose. The draft command now passes the course's own value through, so the check verifies what the course actually declares; `validate` reports an informational `expected_total_points` row when a workspace still carries the template's 100 and its materials declare a different total. Existing workspaces are not migrated, since a stored 100 cannot be told apart from a deliberate one.
- The material index records the point total inferred per graded source under `points`, which is what lets `validate` compare against the course without reading the materials directory.
- The `extraction_anomaly` prose ratio is now measured over label segments instead of non-empty lines, and only marks `exam` and `homework` sources as blocking through the questions-per-page and hard-cap guards. Previously a problem set written one task per line scored a perfect ratio and was reported as blocking, which made `validate --readiness` return `blocked` for the most common exam-paper layout. Lecture, notes, and unclassified sources keep the ratio check unchanged.

## 0.4.0

- Added local material extraction, deterministic indexing, hydration, and source evidence.
- Added extracted-question drafts, target finalization, pool isolation, figures, and answer gates.
- Added readiness, scheduler modes, provenance labels, review projections, hints, and release workflows.
