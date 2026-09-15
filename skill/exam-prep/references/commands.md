# Command catalog

Every `scripts/exam_prep.py` subcommand. Adding a new command means adding
one entry here - `SKILL.md` should not need to change.

## Lifecycle

- `init` - create the workspace once; repeating it is a safe no-op that
  preserves canonical files.
- `load-syllabus <path>` - load or replace the syllabus.
- `start` - open the active session, or resume the one already open.
- `status` - snapshot: course, syllabus, session, review queue, mistakes,
  pending action, capability/blueprint diagnostics, resume point.
  `--compact` trims each target to availability/mastery_status/
  recurring_mistakes, review_queue to due items only, and drops empty
  diagnostics - use it once you already know what you're looking for and
  just need the next-action inputs, not a full diagnostic dump (default
  output is unchanged).
- `validate` - deep diagnostic report on the whole workspace; never blocks
  on its own, only describes what it finds.
- `next --minutes N` - pick one budget-fitting activity.
- `roadmap` - full target list with mastery, review, and availability.
- `review-due` - concepts with a due or overdue review.
- `mistakes` - recurring, unresolved error patterns.
- `record-observation <path>` - the only way learner evidence enters the
  system; never hand-edit `observations.jsonl` or derived state.
- `end-session` - close the session; produces a summary, and a
  per-question post-mortem when the session was an `exam`.
- `rebuild` - recompute derived state from the canonical observation log.
- `verify <path>` - numeric/symbolic answer check (`references/verification.md`).

## Curriculum

- `validate-curriculum <path>` - dry-run check of a curriculum proposal:
  identifiers, prerequisites, cycles, capability mappings, source coverage.
- `apply-curriculum <path>` - apply a validated proposal; idempotent,
  merges by stable identity.
- `ingest-source-evidence <path>` - accept a host-normalized
  SourceEvidenceEnvelope (`references/notebooklm-mcp.md`).

### Source coverage: what makes a source_id "known"

`validate-curriculum`/`apply-curriculum` flag `unknown source ref` against a
catalog built only from source evidence already persisted to this workspace
via a prior `ingest-source-evidence` call - never from the proposal being
validated. A `source_refs` entry inside the curriculum proposal or a
FrozenAssessment only *declares* a citation; it does not *register* one
(`SKILL.md`'s "Proposal-declared refs do not establish source existence"
is this same rule stated at the policy level). To clear a coverage gap,
`ingest-source-evidence` the source first, then re-run `validate-curriculum`.

### Capability IDs

`assessment_capabilities`/`capabilities` entries in a syllabus are not
drawn from a fixed enum. The engine ships 14 defaults (`definition_recall`,
`calculation`, `formula_reading`, `recognition`, `explanation`,
`error_detection`, `worked_example`, `faded_example`, `guided_problem`,
`independent_problem`, `transfer`, `exam_problem`, `delayed_recall`,
`delayed_transfer`), and a syllabus may additionally register its own
`capability_id` with a descriptor (`affected_dimensions`, `response_type`,
`review_kind`, `evidence_requirements`, optional `verifier_id`) - a custom
entry is accepted once its `affected_dimensions` are all valid mastery
dimensions (`conceptual`, `procedural`, `recall`, `transfer`, `speed`).
There is no separate allowlist to check a `capability_id` against beyond
this rule.

## Exam blueprint and assessments

- `update-exam-blueprint <path>` - merge a JSON patch into `course.exam`
  and advance `exam.revision` automatically on real change; setting
  `revision` in the patch is rejected.
- `freeze-assessment <path>` - create one `FrozenAssessment` (spec below).
- `mint-assessments <path>` - create a batch of `FrozenAssessment`s in one
  call (package format below).
- `exam [--minutes N]` - assemble a mock exam: with a `purpose=mock` pool
  minted, blueprint-sized and timed tickets sampled with a
  session-id-seeded draw (not a sorted truncation - a repeat within the
  same session reproduces the same tickets, a new session draws a
  different set); with no mock pool minted yet, a plain budgeted session.

### FrozenAssessment spec

Used by `freeze-assessment` (the whole file is one spec) and by each
entry of a `mint-assessments` batch:

`assessment_id`, `target_id`, `capability_id`, `prompt`, `rubric`,
`expected_evidence`, `source_refs`, `difficulty`, `question_version`,
`rubric_version`, and an optional `purpose` (`practice`, `retest`,
`held_out`, or `mock`; defaults to `practice`).

### mint-assessments package format

~~~json
{
  "purpose": "mock",
  "assessments": [
    {"assessment_id": "...", "target_id": "...", "capability_id": "...",
     "prompt": "...", "rubric": {}, "expected_evidence": [],
     "source_refs": [], "difficulty": 0.4,
     "question_version": 1, "rubric_version": 1}
  ]
}
~~~

The top-level `purpose` is the default for entries that omit their own.
Each entry runs through the same validation and pool-isolation guard as
`freeze-assessment` (content already on the practice side cannot be
minted as `held_out`/`mock`, and vice versa); a colliding or invalid entry
is rejected individually, named in the response, without aborting the
rest of the batch. Re-running the same batch is a no-op.

## Maintenance

- `migrate --from-math-study <path>` - one-time import from the legacy
  math-study skill; not part of routine use.
