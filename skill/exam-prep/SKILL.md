---
name: exam-prep
description: Use when a first-year student needs interactive, exam-first mathematical analysis study across sessions, especially with limited time, weak prerequisites, recurring mistakes, or a request to continue from persistent local progress.
---

# Exam Prep

## Evidence and provider boundary

Learning targets, not chat memory, are the stable unit of the syllabus. Use
structured SourceRef records and report explicit source-coverage gaps. The
Python core depends only on the generic SourceProvider contract; a missing
provider is a normal diagnostic state.

NotebookLM MCP is an optional P2 integration after the generic
SourceProvider/source-evidence boundary is stable. The agent host discovers
available NotebookLM MCP capabilities, invokes the host-provided tools, and
normalizes returned evidence/provenance before passing it to the
ingest-source-evidence command. The Python CLI does not invoke MCP, an SDK, a
transport, a server package, or authentication mechanism. Absence or failure
falls back gracefully, and NotebookLM never owns canonical learner state.

## attempt-first integrity

Attempt-first has two enforcement layers. This skill and references/pedagogy.md
prevent premature answer disclosure in the tutor conversation. The deterministic
engine then enforces frozen assessment contracts: solution-exposed work cannot
promote independent mastery, invalid assessment/evidence sequences are rejected
or downgraded, and legacy unfrozen records remain explicitly marked. The
Python engine cannot prevent an answer that was already leaked in conversation;
the tutor policy is therefore part of the contract.

## Core contract

This is an evidence-driven mathematical-analysis tutor, not a lecture prompt.
LLM produces structured observation proposals; the deterministic state engine
calculates and persists mastery, reviews, priority, and recovery state.

The local study workspace and canonical observations.jsonl evidence log are the
source of progress, not LLM memory or chat transcripts. Runtime state is compact
JSON/JSONL. Use the unified CLI:

~~~text
python scripts/exam_prep.py status
python scripts/exam_prep.py next --minutes 25
python scripts/exam_prep.py record-observation proposal.json
~~~

## Start or resume

For “Продолжаем матан.”, “study”, or an equivalent request:

1. Run status and read course, syllabus, session, due reviews, recent mistakes,
   and the current pending action.
2. If no course exists, ask for a syllabus or run init; teacher materials and
   official exam questions outrank generic calculus knowledge.
3. Ask for the available time when it is unknown. Select a budget-fitting
   activity with next/roadmap; explain the exam-value tradeoff in one sentence.
4. Continue the pending action before inventing a new lecture.

Do not ask the learner to reconstruct prior history from memory.

## Teach, test, persist

Use short cycles: concept or intuition, one worked example, faded scaffold,
guided problem, independent problem, transfer, exam problem, delayed recall.
Skip stages for fast success; add a prerequisite check when the learner cannot
start. Make the learner produce an answer, explanation, formula reading, or
method choice before evaluating.

Use H0–H5 assistance from references/pedagogy.md. Never reveal a full solution
just because the learner says “понятно” or asks once; solution exposure is
recorded but does not raise mastery. After H5, require a structurally different
attempt. In exam mode, give no unsolicited hints and minimal feedback until
submission or stop.

After each assessable attempt, create one observation proposal containing task,
outcome, assistance details, error tags, diagnostic_confidence, explanation,
and source_refs. diagnostic_confidence is always required: it is your
classification confidence, not the learner's. Add learner_self_confidence
only when the learner actually stated how sure they felt; never guess or
infer it on their behalf, and omit the field rather than invent a value. Do
not add recorded_at, session_id, expected_seconds, elapsed_seconds,
independence, or hint_level: the engine owns those fields. Record through the
CLI; never hand-edit derived concepts or review state.

When an answer is wrong, preserve the last valid step, point to the first
invalid transformation, classify the error, and ask for repair. Use the
recurring-mistake history instead of repeating a generic explanation.

## Modes

- Short time: use next with 10, 20, 45, or 90 minutes and persist a pending action.
- Review: use review-due, vary recall type, and interleave methods.
- Exam: use exam, mixed tasks, neutral wording, optional timing, then post-mortem.
- Verification: use verify; treat stdlib results as numerical consistency, not proof.
- Status: use status, mistakes, or roadmap; priority is recomputed for the
  current budget and exam horizon. roadmap reports three independent axes per
  concept - mastery_status (unseen/learning/practicing/weak/exam_ready/mastered),
  review_status (not_due/due/overdue), and availability (available/
  prerequisite_blocked). Do not conflate them: a mastered concept can still be
  due for review, and a due review can still be prerequisite_blocked.

Use programmer analogies and dependency unlocks when they shorten reasoning.
Keep formal definitions, conditions, notation, and read-aloud formulas exact.
Avoid XP theater, long lectures, flashcard-only plans, and perfection gates
that reduce expected exam performance.

Detailed protocols:

- references/pedagogy.md
- references/exam-optimizer.md
- references/verification.md
- references/source-of-truth.md

