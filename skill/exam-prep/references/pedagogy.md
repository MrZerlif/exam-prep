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

Allowed error tags include conceptual_error, formula_recall_error, algebra_error,
method_selection_error, notation_error, careless_error, speed_problem,
prerequisite_gap, domain_condition_error, and proof_structure_error.

Concept-local recurring errors are evidence for that concept. Promote a
cross-concept pattern only after repeated observations across concepts/sessions;
the promotion is a summary in learner state, not a duplicate error ledger.

## Anti-illusion checks

Do not promote mastery for reading an explanation, saying “понятно”, viewing a
solution, or unelaborated recognition. Prefer independent retrieval, explanation
in the learner’s words, error detection, transfer, mixed practice, and delayed
recall. Keep diagnostic confidence (tutor classification confidence) separate
from learner self-confidence (student report).

For definitions, request both the formal statement and a read-aloud rendering.
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
| “This timing estimate sounds right.” | Use only engine-measured elapsed_seconds for speed evidence. |
| “The new session can infer what I did.” | Read status and observations.jsonl; do not invent history. |
| “The CAS is unavailable, so the formula is fine.” | Report numerical or symbolic status explicitly; unavailable is not passed. |

Red flags requiring an immediate protocol check:

- a full solution appears before an attempt or permitted H5;
- “понятно” changes mastery without evidence;
- the LLM supplies session, timestamp, or timing fields;
- derived concepts or reviews are edited by hand;
- a 25-minute request starts an unbounded lesson;
- exam mode gives unsolicited hints or early grading;
- a recurring error is explained again without recording and testing repair.

