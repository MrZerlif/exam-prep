---
name: exam-prep
description: Use when a learner is preparing for an exam by a fixed date, needs a plan from their own materials, has limited time or weak prerequisites, repeats mistakes, asks to study an exam-course topic, or asks to resume persistent local progress.
license: MIT
metadata:
  version: "1.2.0"
---

# Exam Prep

For any academic or technical subject. LLM produces structured observation proposals; deterministic state engine validates them.

## Turn recipe

1. For “Изучить тему,” teach an idea and separate example; offer an optional
   check, next task, or practice/review/continue/stop choice. Otherwise give
   the answer/explanation and next task before commands. Follow release rules;
   familiar work uses 3–8-task blocks.
2. On continuation, read `status --compact`: `course`, `session`,
   `last_session_summary`, `targets`, `review_queue`, `resume_point`. Use
   `roadmap` for full metadata and `init` for an uninitialized workspace.
   `status` is read-only; `next --minutes` assumes 25.
3. Triage is optional; use `triage` for partial ratings or skip. Unknown stays
   unknown. `plan` separates questions and topics started; refresh `coverage`
   after a block or budget change.
4. Follow `course.exam.question_model`: `ticket_list` uses theory tickets;
   `problem_set`, `mixed`, `open`, or unset use the problem ladder.
   `course.exam.ticket_slots` routes theory and problem slots.
5. In mock exam mode, stay attempt-first through submission; teach only after
   submission or stop. Mark early stops with `end-session --stopped`; even a
   completed stopped attempt is ineligible as a full mock.
   Record no-attempt teaching as `solution_seen`, never success. For a forgotten step, give a small hint
   and ask for that step;
   for an unfamiliar topic, teach one idea and show a worked example. Outside a
   mock, an explicit request can receive a full solution through the exposure
   pathway; record the exposure and offer a later independent task, with skip
   and stop allowed.
   Give no unsolicited exam hints or early feedback. See `references/pedagogy.md`
   for typed, voice, photo answers, and assessment handling.
6. Record one observation per block or target with `record-observation` or
   `record-batch --compact`; time only when timing matters. Report topics started, independent correct work,
   delayed confirmation, exam-ready topics, and question count separately.
   Learner exam readiness differs from workspace readiness and stays unknown
   without a score threshold, exam time limit, and complete mock scores.
   Delayed checks default to versioned 8-hour then 24-hour intervals; labels and
   facets cannot replace evidence. Ticket attempts require `assessment_id` to bind them.
   Save/read `study-progress.md` on continuation; it is not CLI evidence. Close
   sessions with `end-session`.

Run `python <skill-dir>/scripts/exam_prep.py [--workspace PATH] <command>`.
Learning targets and the workspace are stable. `observations.jsonl` is canonical; never edit derived state. Prefer teacher
materials and official exam lists; surface conflicts. Change curricula with
`validate-curriculum` and `apply-curriculum`. Follow
`schemas/observation-proposal-v2.schema.json` and
`examples/observation-proposal.json`; record actual assistance and let the
engine derive timing and independence. Keep mastery, review, and prerequisites
distinct. Derivative/antiderivative checks: `references/verification.md`.

## References

- Read `references/pedagogy.md` before teaching or the first attempt.

Optional NotebookLM MCP agent host; normalizes SourceEvidenceEnvelope, not canonical learner state.

- Commands: `references/commands.md`
- Tutoring and exposure: `references/pedagogy.md`
- Budgets and exam mode: `references/exam-optimizer.md`
- Materials and answer assets: `references/materials.md`
- Source authority: `references/source-of-truth.md`
- Verification: `references/verification.md`
- Optional NotebookLM: `references/notebooklm-mcp.md`
