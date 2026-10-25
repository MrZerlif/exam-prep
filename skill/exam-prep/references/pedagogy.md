# Tutoring protocol

## Assistance and evidence

Use H0–H5 to describe the assistance actually given:

~~~text
H0 wait for an attempt
H1 point to the relevant object or direction
H2 name a candidate concept or method
H3 ask for the next logical step
H4 reveal a partial transformation or checkpoint
H5 show and explain the complete solution
~~~

H0 is independent evidence. H1 is lightly scaffolded; H2–H3 guided; H4
heavily scaffolded; H5 or a full solution view is `solution_seen`. Record the
assistance actually given; the engine derives the assistance band and
independence classification. Exposure does not raise mastery.

## Give the learner a useful turn

First write the subject response, then include a ready next task in the same
reply. For familiar operations, use a block of 3–8 tasks and review the block
as a whole. Record one observation per block or target, not per arithmetic
step. Use `record-batch <path.jsonl> --compact` when several results are ready;
use `record-observation <path> --compact` for one result. Start activity timers
only when elapsed time matters.

## Diagnostic exit and model answers

Outside exam mode, make one brief attempt to find the learner's starting point.
If they say “I do not remember” or make one failed start, stop diagnosis and
immediately show the model answer in full. Diagnostic mode ends on either
signal. Give the exact wording from the textbook or authoritative course
source, its hypotheses and conditions, and a short example when useful. Record the
exposure as `solution_seen` at H5 without asking the learner to choose a mode.
After several minutes, give a structurally different task for independent
recall. The model, reading, and exposure never count as mastery.

This is the only route to a full solution before learner production. A request
to “just show” does not end diagnosis: ask for a start or the brief answer
structure first. After an attempt, an explicit request may select teaching exposure
or cram exposure. Teaching exposure uses one worked example; cram exposure is
rapid review. State the retrieval trade-off, record each solution as
`solution_seen`, and offer blind reconstruction if time remains. Neither
exposure mode overrides exam mode.

## Pressure safeguards

Frustration, claimed understanding, and time pressure do not permit a premature answer by themselves. The Python engine cannot prevent conversational leakage;
follow this tutor policy and preserve attempt-first outside the diagnostic exit.

## Tracks by question model

Use the track selected by `course.exam.question_model`.

### `ticket_list`

~~~text
ticket → brief answer structure → model answer or comparison
       → comprehension check → unprompted reproduction from memory
       → declared follow-up questions → delayed recall
~~~

Ask for the theorem or definition, its hypotheses and conclusion, and the
shape of the argument in one or two sentences. If the learner says they do not
remember or cannot begin once, use the diagnostic exit above and continue with
the model answer. Keep the later reproduction as a separate closed-book task.
The exam itself is unprompted reproduction; do not force a practice-problem
stage onto a theory-only ticket. Apply ticket settings from
`course.exam.ticket_slots` when the exam also includes problems.

### `problem_set`, `mixed`, `open`, or unset

~~~text
intuition → worked → faded → guided → independent → transfer → exam → delayed recall
~~~

Use only the smallest useful diagnostic start, then move into the model-answer
rule above when the learner cannot begin. A fast correct independent answer
can skip stages. A solved example always leads to learner production. For a
ticket with theory and problem slots, use `ticket_list` for theory and this
problem ladder for the task.

## Voice, photos, and diagnosis

For voice input, evaluate the last explicit version after self-corrections.
Read the photo before evaluating it. If the final expression or working remains
ambiguous, record `outcome: "unclear"` and ask one focused clarification; do
not classify it as success or error, change mastery, or create error tags. Keep
the unclear event in the journal. If a clarification changes a recorded
interpretation, preserve the old event and set `supersedes_observation_id` on
the replacement proposal; the superseded interpretation no longer counts in
reducer or evaluation results.

Before naming an error cause, reconstruct the learner's steps. Confirm the last
valid line, restate the first invalid transformation, then explain the rule or
condition that failed. Ask only for missing work that changes the diagnosis.
After repair, record one typed error for the block or target. When judging a
derivative or antiderivative, use `verify` as described in
`references/verification.md`.

## Definitions and delayed recall

Ask for the formal statement and a natural read-aloud version. When true,
`exam.verbatim_definitions` requires exact reproduction; otherwise grade
meaning and stated conditions. For formulas, ask what each symbol means and
which conditions apply.

Use the formulations file described in `references/materials.md` as a compact
source-linked recall bank. Later ask the learner to reproduce each formulation
without looking. Reading does not count as retention; record only the later
independent response as evidence.

## Exam mode

In exam mode, give no unsolicited hints, model answers, or early correctness
feedback. Keep the exam attempt-first through submission or stop, then grade
against `grading_criteria` and report a post-mortem. Preserve exam evidence
separately from study exposure and practice.
