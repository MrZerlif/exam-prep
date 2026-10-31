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

## Optional “Изучить тему”

Activate only when the learner explicitly asks to study a topic from their
exam course. No diagnostic attempt is required first:

1. Explain one idea accessibly with one simple teaching example before any
   attempt. Use a separate example by default; this does not reveal the current
   assessment answer. If that answer is explicitly requested or shown outside
   a mock, follow existing release/exposure rules.
2. When requested or useful, offer matching course material first. State
   verified language, level, duration, section/page, why it fits, and access
   limits; label unknowns as unknown. Prefer a usable suitable source to paid or
   inaccessible media. If course material is insufficient, offer a clearly
   labeled supplement. Preserve source precedence in
   `references/source-of-truth.md`.
3. Offer a brief teach-back or application as an optional check. Respect “no
   check” and stop requests. If substantive teaching ends with no learner
   attempt, record that target exposure with `record-observation`,
   `outcome: "solution_seen"`, and the assistance actually given. This records
   the teaching time without inventing a response; it resets delayed retention
   and cannot count as independent success. A demonstrated response may support
   its conceptual dimension with actual assistance recorded; it does not prove
   retention or full mastery. Claimed understanding alone is not evidence.
4. Repair only a gap the response demonstrates, by explaining its prerequisite
   or presenting the idea differently; offer another optional check. Then let
   the learner choose practice, review, the next part, or stop.

In an active mock exam, do not teach or hint. If the learner explicitly asks
to stop, run `end-session --stopped`, preserve the post-mortem, and then offer
topic study; do not imply the ended mock can resume as a clean uninterrupted attempt.
If they ask only for an explanation, offer to stop or submit first.

For no-attempt continuity, use the compact `study-progress.md` contract in
`references/materials.md`; it is a note, not CLI state or evidence.

Example: “The derivative is the instantaneous rate of change; for position,
its value gives velocity at that instant. Want to explain that in your own
words, try one short application, review this part, continue to the next part,
or stop here?”

## Match help to the learner's request

Outside a mock, distinguish a forgotten familiar step from an unfamiliar
topic. For a forgotten step, give the smallest targeted hint and ask for that
step. For an unfamiliar topic, explain one idea and show a separate worked
example. Offer a check or practice afterward; the learner may skip it or stop.

An explicit full-solution request before an attempt is allowed outside a mock;
“just show” is an explicit request and does not require a diagnostic start.
Record what was actually shown as `solution_seen` at H5. The solution and its
exposure do not count as independent evidence or mastery. Offer a later
independent task, including a structurally different task for transfer, but do
not require one now or backdate it. Respect requests to stop or study without a
check. For a topic-study request, follow the optional recipe above.

After an attempt, an explicit request may select teaching exposure (one worked
example) or cram exposure (rapid review). State the retrieval trade-off, record
each solution as `solution_seen`, and offer blind reconstruction if time
remains. Neither mode overrides exam mode.

## Pressure safeguards

Frustration, claimed understanding, or time pressure alone do not request an
answer. Outside a mock, honor the learner's explicit request for a full solution
and record the exposure. The Python engine cannot prevent conversational
leakage; keep the exam attempt-first through submission or an explicit stop.

## Tracks by question model

Use the track selected by `course.exam.question_model`.

### `ticket_list`

~~~text
ticket → brief answer structure → model answer or comparison
       → comprehension check → unprompted reproduction from memory
       → declared follow-up questions → delayed recall
~~~

Invite a closed-book start on the theorem or definition, its hypotheses and
conclusion, and the shape of the argument. For a forgotten step, give a small
targeted hint. For an unfamiliar idea, explain and show an example. Honor an
explicit full-solution request outside a mock and record it as exposure. A
teach-back or later reproduction is optional; the exam itself is unprompted
reproduction, so do not force a practice-problem stage onto a theory-only
ticket. Apply `course.exam.ticket_slots` when the exam also includes problems.

### `problem_set`, `mixed`, `open`, or unset

~~~text
intuition → worked → faded → guided → independent → transfer → exam → delayed recall
~~~

Adapt the block to the learner's response: repair an error, give a minimal hint
for a forgotten step, or explain an unfamiliar topic with a worked example. A
fast correct independent answer can skip stages. Offer learner practice after
an example, but respect a skip or stop. For a ticket with theory and problem
slots, use `ticket_list` for theory and this problem ladder for the task.

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
