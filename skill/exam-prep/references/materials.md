# Materials and provenance

Local files enter through `ingest-materials`. Lightweight mode writes only the
derived `.exam-prep/material_index.json`; it is a preview, not evidence. Use
`hydrate-source` to read selected pages fully and append immutable records via
`SourceEvidenceEnvelope`. Repeating hydration is idempotent because the
evidence hash includes the excerpt.

The local extractor handles DOCX, PPTX, Markdown, text, RST, HTML, and optional
PDF backends. It records extractor/backend versions and a configuration hash.
Missing optional PDF support is an `unsupported_page` gap, not a fatal import.

Authority and provenance are independent. File names do not establish
`official_exam_list` or `teacher_material`; use an explicit override or trusted
manifest. Content labels are `[SOURCE]`, `[SUPPLEMENT]`, and `[GENERATED]`.
Generated questions use `origin=model_generated` and remain practice-only.

Answer assets live under `.exam-prep/assets/{prompt,answer,reference}` with
hash-based names. Normal delivery never returns answer-role assets; they are
released only through `reveal-answer <assessment_id>`: after an attempt, or
before one with `--exposure`. Every release not already covered by a recorded
exposure records `solution_seen`, so a later retry of that assessment is a
`post_exposure_attempt`. Direct file reads remain outside the Python gate and
are covered by the behavioral release case.
