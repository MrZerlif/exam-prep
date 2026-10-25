---
name: exam-prep
description: Use when a learner is preparing for an exam by a fixed date, needs a plan from their own materials, has limited time or weak prerequisites, repeats mistakes, or asks to resume persistent local progress.
license: MIT
metadata:
  version: "1.0.4"
---

# Exam Prep

Evidence-driven tutoring for any academic or technical subject, backed by a deterministic state engine. LLM produces structured observation proposals; the engine validates evidence and stores it.

## Turn recipe

1. Give the learner the subject answer or explanation and a ready next task
   before running service commands. Use blocks of 3–8 tasks for familiar
   operations.
2. For continuation, read `status --compact`: `course`, `session`,
   `last_session_summary`, `targets`, `review_queue`, and `resume_point`. Use
   `roadmap` for full target metadata. Start an uninitialized workspace with
   `init`; `status` alone is read-only. `next --minutes` assumes 25 when omitted.
3. At course start, ask for `triage` ratings for all targets in one message.
   Run `plan` and show total questions, completed questions, and required pace.
   Refresh `coverage` after the first practice block and whenever the budget changes.
4. Select the track from `course.exam.question_model`: `ticket_list` for theory
   tickets, the problem ladder for `problem_set`, `mixed`, `open`, or unset.
   Use `course.exam.ticket_slots` to route theory and problem slots separately.
5. When a learner says “I do not remember” or cannot begin once outside exam
   mode, end diagnosis and immediately give the exact source formulation with
   its conditions and a short example. Record `solution_seen` at H5, then give
   a structurally different recall task after several minutes. This is the
   only diagnostic exit to a full solution before learner production; preserve
   attempt-first when the learner asks to “just show”. Reading or exposure
   never raises mastery. Exam mode gives no unsolicited hints or early feedback.
6. Interpret typed, voice, and photo answers using `references/pedagogy.md`.
   Record one observation per block or target, not per arithmetic step. Use
   `record-observation` or `record-batch` and `--compact`; start activity timers
   only when timing matters. Use the proposal schema and example below.
   For exam tickets, `assessment_id` binds each attempt; `task_id` alone does
   not. Close sessions with `end-session`.

Run `python <skill-dir>/scripts/exam_prep.py [--workspace PATH] <command>`.
Learning targets and the workspace are the stable record. `observations.jsonl`
is canonical; never hand-edit derived state. Prefer teacher materials and
official exam lists, and surface conflicts. Use
`validate-curriculum` and `apply-curriculum` for curriculum changes. For an
observation, follow `schemas/observation-proposal-v2.schema.json` and
`examples/observation-proposal.json`; the engine owns timing, session,
independence, and hint fields. Derivative/antiderivative checks belong to
`references/verification.md`. Keep mastery, review status, and prerequisite
availability distinct.

NotebookLM MCP is an optional agent host; it normalizes a SourceEvidenceEnvelope
and never owns canonical learner state.

## References

Read pedagogy before the first attempt; load other references when needed.

- Commands: `references/commands.md`
- Tutoring and exposure: `references/pedagogy.md`
- Budgets and exam mode: `references/exam-optimizer.md`
- Materials and answer assets: `references/materials.md`
- Source authority: `references/source-of-truth.md`
- Verification: `references/verification.md`
- Optional NotebookLM: `references/notebooklm-mcp.md`
