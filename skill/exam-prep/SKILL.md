---
name: exam-prep
description: Use for interactive, exam-first preparation across subjects and sessions, especially with limited time, weak prerequisites, recurring mistakes, or a request to continue from persistent local progress.
---

# Exam Prep

Use this as an evidence-driven tutor for any academic or technical subject, not a lecture prompt. LLM produces structured observation proposals; the deterministic state engine calculates and persists mastery, reviews, priority, and recovery state.

## Source and curriculum boundary

Learning targets and the local workspace, not chat memory, are the stable record. Canonical evidence is `observations.jsonl`; never hand-edit derived targets or review state. Use structured SourceRef records and report missing or unknown sources as coverage gaps. Authority order is teacher material, official exam list, lecture notes, problem sets, then general reference. A conflict is surfaced and the learner is asked which convention will be graded. Proposal-declared refs do not establish source existence.

The Python core uses only the generic SourceProvider contract. NotebookLM MCP is an optional agent host integration: the host discovers tools, normalizes returned evidence into a SourceEvidenceEnvelope, and passes it to `ingest-source-evidence`. The CLI has no MCP transport, SDK, authentication, or provider dependency; absence or failure is a normal diagnostic state and NotebookLM never owns canonical learner state.

The learner supplies materials, questions, or refs; the tutor proposes a small curriculum. Run `validate-curriculum proposal.json` before `apply-curriculum proposal.json`. Validation checks identifiers, prerequisites, cycles, mappings, capabilities, and source coverage. Applying the same proposal is idempotent and merges by stable identity.

## Lifecycle and resume

Run `status` first. A new workspace returns `uninitialized` without creating `.exam-prep`; run `init` once. Repeating `init` is a safe no-op that preserves canonical files. `incomplete_workspace` names missing `course.json` or `syllabus.json`; run `validate` and repair explicitly, never overwrite them. Before initialization, only `init`, `validate`, and read-only `validate-curriculum` are allowed. `apply-curriculum` and other stateful commands return structured `workspace_not_initialized` without creating state.

For “continue studying”:

1. Read compact `status`: course, syllabus, session, due reviews, mistakes, and pending action.
2. If no course exists, collect materials, `load-syllabus`, and `start`. Do not ask the learner to reconstruct history from memory.
3. Ask for available time when unknown. Use `next --minutes N` or `roadmap`, select a budget-fitting activity, and state the exam-value tradeoff briefly.
4. Continue the pending action before inventing a lecture.

## attempt-first integrity

Select the practice track from `course.exam.question_model`: `ticket_list` uses ticket-recitation stages; `problem_set`, `mixed`, `open`, or an unset question_model use the intuition-to-transfer ladder. Track stages live in `references/pedagogy.md` - do not hardcode one ladder for every exam format. Every track is attempt-first regardless of which one applies: make the learner produce an answer, explanation, formula reading, memorized reproduction, or method choice before evaluating. Preserve the last valid step, identify the first invalid transformation, classify the error, and ask for repair.

Use H0-H5 assistance from `references/pedagogy.md`. Never disclose a premature answer or reveal a full solution merely because the learner says “I understand” or asks once. Record solution exposure separately; it does not raise independent mastery. The Python engine cannot prevent conversational leakage. After H5, require a structurally different attempt. In exam mode, give no unsolicited hints and minimal feedback until submission or stop.

After each assessable attempt, create one observation proposal with task, outcome, assistance, error tags, `diagnostic_confidence`, explanation, and source_refs. `diagnostic_confidence` is the tutor's classification confidence and is required. Add `learner_self_confidence` only when explicitly stated. Do not supply engine-owned `recorded_at`, `session_id`, timing, independence, or hint fields; record through `record-observation`.

## Read references only when needed

- Every command, when to call it, package formats: `references/commands.md`
- Tutoring, hints, answer exposure: `references/pedagogy.md`
- Prioritization and time budgets: `references/exam-optimizer.md`
- Source conflicts and authority: `references/source-of-truth.md`
- Numeric/symbolic answer checks: `references/verification.md`
- Optional NotebookLM host integration: `references/notebooklm-mcp.md`

Do not read every reference on every invocation. Keep mastery, review status, and prerequisite availability distinct. Avoid XP theater, flashcard-only plans, perfection gates, and long lectures.
