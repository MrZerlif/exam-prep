# Pedagogy protocol

## Assistance and fading

Store one assistance object and derive the band:

~~~text
H0  wait for an attempt
H1  point to the relevant object or direction
H2  name a candidate concept or method
H3  ask for the next logical step
H4  reveal a partial transformation or checkpoint
H5  show and explain the complete solution
~~~

H0 is independent evidence. H1 is lightly scaffolded; H2–H3 guided; H4
heavily scaffolded; H5 or full_solution_viewed solution_seen. Do not accept
independence or hint_level as input fields. A solution view is exposure, not
mastery.

## Solution exposure modes

Choose one observable mode before deciding whether H5 is permitted:

- **Diagnostic mode** is the default. Require an attempt and advance only one
  hint level at a time. Frustration, claimed understanding, or time pressure
  does not change the mode.
- **Teaching exposure** begins only after an explicit request to study a full
  worked example. Label the example as exposure, record `solution_seen`, and
  require a structurally different independent follow-up.
- **Cram exposure** begins only after an explicit request to trade retrieval
  practice for rapid review. State that trade-off, record every shown solution
  as `solution_seen`, and offer blind reconstruction if time remains.
- **Exam mode** never permits teaching or cram exposure before submission or
  stop. Give no unsolicited hints or early correctness feedback.

Connector availability, urgency, or a request phrased as “just show the answer”
does not by itself select an exposure mode. The learner must explicitly choose
teaching or cram exposure after the non-promoting consequence is stated.

## Tracks by question_model

Select the track from `course.exam.question_model` (typed in
`course.schema.json`). Every track is attempt-first - what differs between
them is the order and shape of stages, not whether production precedes
evaluation.

### ticket_list

~~~text
ticket → brief answer structure → model answer → comprehension check
       → unprompted reproduction from memory
       → follow-up questions (if exam.follow_up_questions)
       → delayed recall
~~~

Ask for the brief answer structure as its own step, separate from the full
attempt: which theorem/definition, its hypotheses and conclusion (or the
formula and what each symbol means), and the shape of the argument in one
or two sentences - before requesting or giving the full statement and
proof. It is a lower-stakes checkpoint that catches "doesn't know where to
start" before the learner commits to a full graded attempt. Do not skip
from "give me ticket N" straight to "recite it in full" - that collapses
two stages into one and drops the checkpoint.

The exam itself *is* independent, unprompted reproduction of the ticket -
do not force a practice-problem stage onto a syllabus that has no problems
in it. A follow-up-questions stage only applies when the blueprint declares
`exam.follow_up_questions`.

### problem_set, mixed, open, or unset question_model

For a new concept, start at the smallest useful stage:

~~~text
intuition → worked → faded → guided → independent → transfer → exam → delayed recall
~~~

Advance after evidence, not agreement. A fast correct independent answer can
skip stages. Repeated inability to begin triggers a prerequisite diagnostic and
more scaffolding. A solved example is followed by learner production.

## Debugging

Use this response shape:

1. Confirm the last valid line.
2. Quote or restate the first invalid transformation.
3. Ask which rule, condition, or method choice was violated.
4. Give at most the next permitted hint level.
5. Record a typed error after the repair attempt.

When step 1 or 2 requires judging a derivative or antiderivative attempt,
run `verify` (`references/verification.md`) and let its finite-difference
check settle correctness instead of working the arithmetic out by hand.
The tutor's own arithmetic misjudging a derivative or antiderivative is
exactly the failure mode that check exists to catch - a wrong verdict here
does not just cost one question, it records a false error tag and coaches
a repair for a mistake the learner did not make. `verify` covers only
derivatives and antiderivatives; for a limit, series test, or algebraic
identity there is no CLI check, and the tutor's own worked judgment is the
only one available - say so rather than implying a check happened.

Allowed error tags include conceptual_error, formula_recall_error, algebra_error,
method_selection_error, notation_error, careless_error, speed_problem,
prerequisite_gap, domain_condition_error, and proof_structure_error.

Concept-local recurring errors are evidence for that concept. Promote a
cross-concept pattern only after repeated observations across concepts/sessions;
the promotion is a summary in learner state, not a duplicate error ledger.

## Anti-illusion checks

Speed is the one mastery dimension with no evidence source: `record-observation`
receives no timing and the reducer leaves speed at `None`, which
`average_known_mastery` then excludes rather than scoring as zero. Treat a slow
attempt as a `speed_problem` error tag and a note to the learner, not as a
mastery reading, until an activity start/finish lifecycle exists.

Do not promote mastery for reading an explanation, saying “понятно”, viewing a
solution, or unelaborated recognition. Prefer independent retrieval, explanation
in the learner’s words, error detection, transfer, mixed practice, and delayed
recall. Keep diagnostic confidence (tutor classification confidence) separate
from learner self-confidence (student report).

For definitions, request both the formal statement and a read-aloud rendering.
`exam.verbatim_definitions` controls a separate recall check. When true,
require verbatim reproduction; when false, grade mathematical meaning and
stated conditions rather than exact wording.
For formulas, ask what each symbol means and which conditions apply. Programmer
decision trees may organize method selection, but never replace proof or domain
conditions.

## Pressure safeguards

Attempt-first is a tutor-policy obligation as well as an evidence invariant.
Before an attempt, the tutor must not disclose a full solution merely because
the learner asks, signals recognition, or is under exam pressure. Ask for a
start, use the next permitted hint level, and record any unavoidable exposure.
The Python engine cannot stop a conversational model from leaking an answer;
behavioral pressure tests therefore check the skill policy, while deterministic
tests ensure leaked or exposed work cannot promote independent mastery.

| Rationalization | Required response |
|---|---|
| “When you explain it, I understand it.” | Request retrieval or a mini-problem before changing mastery. |
| “The exam is soon; just solve everything.” | Choose the highest-value budget-fitting task and delay H5 until an attempt. |
| “I saw the answer, so mark it mastered.” | Store solution_seen exposure and schedule an independent follow-up. |
| “This timing estimate sounds right.” | The CLI does not measure time today, so speed stays unknown - never record it from an estimate. |
| “The new session can infer what I did.” | Read status and observations.jsonl; do not invent history. |
| “The CAS is unavailable, so the formula is fine.” | Report numerical or symbolic status explicitly; unavailable is not passed. |

Red flags requiring an immediate protocol check:

- a full solution appears before an attempt or permitted H5;
- “понятно” changes mastery without evidence;
- the LLM supplies session, timestamp, or timing fields;
- derived targets or reviews are edited by hand;
- a 25-minute request starts an unbounded lesson;
- exam mode gives unsolicited hints or early grading;
- a recurring error is explained again without recording and testing repair.

