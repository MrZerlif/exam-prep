# Command catalog

Every `scripts/exam_prep.py` subcommand. Adding a new command means adding
one entry here - `SKILL.md` should not need to change.

## Invocation

Every command below is a subcommand of one script:

~~~bash
python <skill-dir>/scripts/exam_prep.py [--workspace PATH] <command> [args]
~~~

`<skill-dir>` is this package's own directory - the one holding
`SKILL.md`. Python puts the script's own directory on `sys.path`, so an
absolute path works from any working directory and `exam_prep_lib` is
found beside the script. There is nothing to install and nothing on
`PATH`.

The workspace is a separate thing from the skill directory: it is where
`.exam-prep/` lives, and it is resolved in this order:

1. `--workspace PATH`
2. `EXAM_PREP_WORKSPACE`, then the legacy `MATH_STUDY_WORKSPACE`, then
   `EXAM_PREP_PROJECT_ROOT`
3. the nearest ancestor directory containing `.git`
4. the current working directory

Generic host variables `PROJECT_ROOT` and `WORKSPACE_ROOT` are ignored on
purpose. Pass `--workspace` explicitly whenever the learner's course and
the current directory might differ: a wrong workspace does not fail, it
reports `uninitialized` and invites you to start a second, empty course.

## Before initialization

Only `status`, `init`, `validate`, and `validate-curriculum` run on a
workspace that has no `.exam-prep/` yet. Every other command returns
`workspace_not_initialized` with the missing canonical files named, and
creates nothing - it is a normal refusal, not a failure, and the repair is
`init` (or `validate` when files are partially present), not a retry.

## Lifecycle

- `init` - create the workspace once; repeating it is a safe no-op that
  preserves canonical files.
- `load-syllabus <path>` - load or replace the syllabus.
- `start` - open the active session, or resume the one already open.
- `status` - snapshot: course, session, targets, review queue, recurring
  mistakes, pending action, capability/blueprint diagnostics, and resume point.
  It does not return the syllabus document or full target titles; use `roadmap`
  when full target metadata is needed.
  `--compact` trims each target to availability/mastery_status/
  recurring_mistakes, review_queue to due items only, and drops empty
  diagnostics - use it once you already know what you're looking for and
  just need the next-action inputs, not a full diagnostic dump (default
  output is unchanged).
- `validate` - deep diagnostic report on the whole workspace; never blocks
  on its own, only describes what it finds.
- `validate --readiness` - add a `blocked`, `usable_with_gaps`, or `ready`
  verdict without changing the ordinary validate payload. `--format text`
  prints an ASCII summary.
- `ingest-materials <materials-dir> [--mode lightweight|full] [--dry-run]` -
  build the derived material index; full mode hydrates every extracted page.
- `hydrate-source <source-id> [<source-id> ...] --materials-dir <dir>` -
  hydrate selected pages into the append-only source evidence log. Repeating
  the command is idempotent.
- `draft-assessments <materials-dir> --out <path>
  [--include-unclassified] [--include-lecture-exercises]` - extract questions
  into a target-unassigned `AssessmentDraft`. Lecture and notes sources are
  skipped unless `--include-lecture-exercises` is given, and then only their
  unambiguous `accept` candidates are taken; each is marked with an
  informational issue naming the source it came from, and lands as `practice`,
  never in the mock pool.
- `finalize-assessment-draft <draft> --target-map <path> --out <path>` -
  require a complete question-to-target map before minting.
- `apply-lexicon <path> [--dry-run]` - merge a learned lexicon overlay into
  the workspace. Besides `slots`, an overlay may declare `word_boundaries`
  and `normalization`, which is how a language with no bundled lexicon - Thai,
  Khmer, Lao - says it is written without spaces between words. Where a
  bundled lexicon exists, its own rules win and the overlay contributes only
  words; across merges the newest declaration wins.
- `extract-figures <materials-dir> [--pages <relative-path>:<page>]
  [--scale 2.0]` / `figure <relative-path> <page> [--crop x0,y0,x1,y1]
  [--out <path>]` - derive hash-named prompt, answer, and reference assets.
- `reveal-answer <assessment-id> [--exposure]` - return answer assets only
  after an attempt, or after explicit exposure that records `solution_seen`.
- `cheatsheet`, `last-minute-review`, and `plan` - deterministic derived
  review artifacts; `plan --days N --minutes-per-day M` is a forecast and
  never changes the exam date.
- State-changing and overview commands accept opt-in `--include-next-hint`;
  no hint is emitted without the flag.
- `next --minutes N` - pick one budget-fitting activity.
- `roadmap` - full target list with mastery, review, and availability.
- `review-due` - concepts with a due or overdue review.
- `mistakes` - recurring, unresolved error patterns.
- `record-observation <path>` - the only way learner evidence enters the
  system; never hand-edit `observations.jsonl` or derived state. When the
  attempt answers a frozen assessment, the proposal must carry
  `assessment_id` (see below).
- `end-session` - close the session; produces a summary, and a
  per-question post-mortem when the session was an `exam`.
- `rebuild` - recompute derived state from the canonical observation log.
- `verify <path>` - derivative/antiderivative answer check
  (`references/verification.md`); unsupported kinds return `unavailable`.

### Linking an attempt to a frozen assessment

`assessment_id` is what binds an observation to a `FrozenAssessment`. It is an
optional proposal field - ordinary practice that answers no frozen assessment
omits it - but it is the *only* key that binds. `task_id` is required on every
proposal and never binds: it names the activity, not the assessment, and an
`exam` ticket answered with `task_id` alone is recorded as ordinary evidence
with `assessment_integrity: "not_assessment"`.

Omitting it on a mock ticket is silent and costly. `end-session`'s post-mortem
pairs `session.mock_assessment_ids` against events by `assessment_id`, so every
unlinked ticket stays `attempted: false` and `score` is computed over a sample
that never fills - the exam is graded as if nothing had been answered.

When the attempt answers a ticket that `exam` handed out, copy that ticket's
`assessment_id` into the proposal verbatim, alongside the `target_id` and
`capability_id` the same ticket carries. The engine cross-checks all three and
refuses the write when they disagree (`AssessmentIntegrityError`) or when the
`assessment_id` is unknown (`AssessmentConflict`), so a mistyped link fails
loudly rather than recording detached evidence. A `mock` assessment also
requires the session to be in `phase: exam`.

Forgetting the link is diagnosed, not punished. An attempt recorded during
`phase: exam` on a target this session holds an unlinked ticket for, with no
`assessment_id`, comes back with a `diagnostics` entry
(`exam_attempt_not_linked_to_ticket`) naming the tickets still available to
link - reported while the next attempt can still be recorded correctly, rather
than at end-session when the mock is over. The observation is recorded either
way and the event stays in the canonical log; losing evidence to enforce a link
would be worse than an unlinked attempt. `end-session` repeats the total as
`post_mortem.unlinked_attempts`. Nothing is reported outside an exam phase, for
a target the mock does not cover, or once every ticket for that target is
already linked.

`score` is the share of *independently* correct tickets, not of correct ones:
a ticket answered correctly after H1/H2 hints lands in `correct` but its
assistance band is `guided`, and only `independent` counts. Two correct
answers, one of them hinted, score 0.5.

### Observation proposal payload

`record-observation` validates the file before anything is written, and
`additionalProperties: false` means an unknown key is an error, not a
warning. Build the proposal from
`schemas/observation-proposal-v2.schema.json`;
`examples/observation-proposal.json` is a valid instance to copy the shape
from, rather than reconstructing the field list from prose.

Required on every v2 proposal:

`schema_version` (the integer `2`), `observation_id`, `target_id`,
`task_id`, `capability_id`, `task_type`, `outcome`, `assistance`,
`error_tags`, `diagnostic_confidence`, `source_refs`.

Tutor-supplied optional fields: `learner_self_confidence` (only when the
learner states it), `learner_explanation`, `assessment_id` (above),
`solution_exposed`, `explicit_exposure_reason`, `activity_id`. The schema
is the complete list; anything outside it is rejected.

A proposal carrying any of these engine-owned fields at its own top level
is rejected with `engine-owned field is not accepted from LLM`: `recorded_at`,
`session_id`, `timestamp`, `expected_seconds`, `elapsed_seconds`,
`assessment_integrity`, `assessment_spec_hash`,
`canonical_assessment_hash`, `derived_evidence_maturity`, `independence`,
`exposure_classification`, `verifier_result`. The engine owns the clock,
session binding, timing, and independence/exposure classification; it derives
them from `assistance` and `outcome`. Only top-level keys are checked: the
optional `assessment` sub-object carries its own `spec_hash` and
`assessment_spec_hash`, and those are accepted.

A proposal whose `schema_version` is not `2` is validated against the v1
schema (`concept_id` instead of `target_id`); that path exists for legacy
workspaces only. Write `2`.

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
