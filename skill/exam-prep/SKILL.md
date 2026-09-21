---
name: exam-prep
description: Use when a learner is preparing for an exam by a fixed date, needs a plan from their own materials, has limited time or weak prerequisites, repeats mistakes, or asks to resume persistent local progress. Local material extraction supports 12 languages with configurable and per-source detection.
license: MIT
metadata:
  version: "1.0.1"
---

# Exam Prep

Evidence-driven tutoring for any academic or technical subject with a
deterministic state engine. LLM produces structured observation proposals; the
engine validates evidence and persists mastery, reviews, priorities, and
recovery state.

Local material extraction supports `en`, `ru`, `de`, `fr`, `es`, `it`, `pt`,
`pl`, `tr`, `uk`, `zh`, and `ja`. A course may configure its language, or the
engine detects it once during the first `ingest-materials` run and records the
result in `course.json`.

## Sources and lifecycle

Learning targets and the workspace are the stable record. `observations.jsonl`
is canonical; never hand-edit derived state. Prefer teacher material and
official exam lists, and surface conflicts.

Run:
`python <skill-dir>/scripts/exam_prep.py [--workspace PATH] <command>`.
Start with `status`; `uninitialized` is read-only, so run `init` once.
Materials use `ingest-materials` and `hydrate-source`, which create a
SourceEvidenceEnvelope without network access. NotebookLM MCP is an optional
agent host; it normalizes a SourceEvidenceEnvelope and never owns canonical learner state.
If `ingest-materials` returns `unclassified`, map its repeated labels to slots
and apply them with `apply-lexicon`.
Use `validate-curriculum` and `apply-curriculum` for
idempotent curriculum changes.

For continuation, read `status --compact`: `course`, `session`,
`last_session_summary`, `targets`, `review_queue`, and `resume_point`. Use
`roadmap` for full target metadata; close with `end-session`. `next
--minutes` assumes 25 when omitted.

Figures are derived assets. Open a prompt image before explaining it and show
answer assets only after `reveal-answer`; the behavioral
`answer_asset_leak` case is the safety gate.

## attempt-first policy

Select the track from `course.exam.question_model`: `ticket_list` uses ticket
recitation; `problem_set`, `mixed`, `open`, or unset use the problem ladder.
Every track requires learner production before evaluation. Preserve the last
valid step, identify the first invalid transformation, and ask for repair.

Use H0-H5 assistance. Diagnostic mode never reveals a premature answer or
full solution merely because the learner asks once. Teaching or cram exposure
requires an explicit request, records `solution_seen`, does not raise
independent mastery, and is followed by a structurally different attempt.
Exam mode gives no unsolicited hints or early feedback. The Python engine cannot prevent conversational leakage; tutor policy must.

After each assessable attempt, write one proposal from
`schemas/observation-proposal-v2.schema.json` through `record-observation`;
`examples/observation-proposal.json` is valid. For exam tickets,
`assessment_id` binds the attempt; `task_id` does not. Do not supply
engine-owned timing, session, independence, or hint fields.

## Pressure and verification

Attempt-first safeguards cover premature answer requests and pressure. Teaching
or cram exposure is explicit and records `solution_seen`.
Derivative/antiderivative checks belong to `references/verification.md`;
do not imply broader numeric or
symbolic answer checking.

## References

Read `references/pedagogy.md` before the first attempt of a session.

- Commands: `references/commands.md`
- Tutoring and exposure: `references/pedagogy.md`
- Budgets and exam mode: `references/exam-optimizer.md`
- Source authority: `references/source-of-truth.md`
- Verification: `references/verification.md`
- Optional NotebookLM: `references/notebooklm-mcp.md`

Keep mastery, review status, and prerequisite availability distinct.
