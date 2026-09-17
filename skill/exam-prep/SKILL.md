---
name: exam-prep
description: Use when a learner is preparing for an exam by a fixed date, needs a plan from their own materials, has limited time or weak prerequisites, repeats mistakes, or asks to resume persistent local progress.
---

# Exam Prep

An evidence-driven tutor for any academic or technical subject. LLM produces structured observation proposals; the deterministic state engine validates evidence and persists mastery, reviews, priority, and recovery state.

## Evidence and sources

Learning targets and the workspace, not chat memory, are the stable record. `observations.jsonl` is canonical; never hand-edit derived targets or reviews. Prefer teacher material and official exam lists over general references; surface conflicts and ask which convention will be graded.

NotebookLM MCP is an optional agent host integration: the host normalizes evidence into a SourceEvidenceEnvelope for `ingest-source-evidence` and never owns canonical learner state. Installation, authentication, uploads, and external writes each require explicit user confirmation; see `references/notebooklm-mcp.md`.

A ready syllabus loads with `load-syllabus`. Learner materials go `ingest-source-evidence`, draft proposal, `validate-curriculum`, `apply-curriculum` (idempotent); only this path reports source-coverage gaps.

## Lifecycle and resume

Invoke `python <skill-dir>/scripts/exam_prep.py [--workspace PATH] <command>`. Run `status` first. `uninitialized` is read-only; run `init` once. If `incomplete_workspace`, run `validate` and repair missing files without overwriting them.

For continuation, read compact `status`: `course`, `session`, `last_session_summary`, `targets` (mistakes nest per target), `review_queue`, `resume_point`, and any non-empty `*_diagnostics`. If no targets exist, set up the course above, then `start`. Always pass the learner's stated time: `next` without `--minutes` assumes 25. Continue the pending action, then close with `end-session`: it writes the summary and post-mortem resume reads. Use `roadmap` for full target metadata.

## attempt-first integrity

Select the track from `course.exam.question_model`: `ticket_list` uses ticket recitation; `problem_set`, `mixed`, `open`, or unset use the problem ladder. Every track is attempt-first: require learner production before evaluation, preserve the last valid step, identify the first invalid transformation, and ask for repair.

Use H0-H5 assistance. In diagnostic mode, never reveal a premature answer or full solution merely because the learner asks once. Teaching or cram exposure requires an explicit request, records `solution_seen`, never raises independent mastery, and is followed by a structurally different attempt. In exam mode, give no unsolicited hints or early feedback.

The Python engine cannot prevent conversational leakage; the tutor policy must. Two failures need no reference: a full solution before an attempt, and a claim of understanding raising mastery. Answer both with retrieval.

After each assessable attempt, build one proposal from `schemas/observation-proposal-v2.schema.json`; `examples/observation-proposal.json` is valid. Do not supply engine-owned timing, session, independence, or hint fields; write through `record-observation`. For an exam ticket, `assessment_id` is the only field that binds the attempt.

## Read references only when needed

Read `references/pedagogy.md` before the first attempt of a session, not after the learner pushes back.

- Commands and payloads: `references/commands.md`
- Tutoring and exposure modes: `references/pedagogy.md`
- Budgets, exam mode, post-mortem: `references/exam-optimizer.md`
- Source authority: `references/source-of-truth.md`
- Derivative/antiderivative checks: `references/verification.md`
- Optional NotebookLM integration: `references/notebooklm-mcp.md`

Keep mastery, review status, and prerequisite availability distinct. Avoid XP theater, perfection gates, and flashcard-only plans.
