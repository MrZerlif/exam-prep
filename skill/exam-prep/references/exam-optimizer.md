# Exam optimizer protocol

## Decision rule

For the current budget, rank unlocked learning targets with:

~~~text
exam value × mastery gap × urgency × prerequisite readiness
× improvement potential ÷ estimated learning minutes
~~~

Exam value uses teacher/official importance, frequency, and expected points.
Urgency uses exam horizon and due reviews. Improvement potential discounts work
that cannot become useful inside the available budget. Priority is contextual:
recompute it when time, exam revision, mastery, due state, or budget changes.

Explain the selected tradeoff briefly. It is valid to defer low-yield perfection
and repair only the prerequisite needed for a high-value task. Never require
complete topic mastery before touching a higher-yield topic.

## Session budgets

Fit the activity to whatever number of minutes the learner actually has - 10,
15, 20, 45, 90, or any other value, not just the round examples. Reserve a
persistence point: after a problem, a review item, or a short recall. A
15-minute or 25-minute request must not start a two-hour lesson, and must not
be rounded up to a larger budget than the learner said they have.

## Reviews and interleaving

Use due reviews, then vary evidence type: definition, formula read-aloud,
method recognition, validity conditions, error detection, mini-problem, transfer,
and delayed recall. After initial learning, mix neighboring methods and ask the
learner to choose the method before calculating. Avoid long homogeneous runs.

## Exam mode and post-mortem

`exam` is stateful and blueprint-driven: it assembles tickets from the
`mock`-purpose assessment pool (see "Authoring: freeze-assessment and
mint-assessments" below), sized and timed by `course.exam` -
`question_count`, `time_limit_minutes` or `per_question_minutes`,
`delivery`, `follow_up_questions`, `grading_criteria`. With no mock pool
minted yet it falls back to a plain budgeted session, not an error.

- no unsolicited hints;
- neutral wording;
- minimal feedback until submission or stop;
- grade against `grading_criteria` when the blueprint states them.

`end-session` reports a post-mortem: each ticket's outcome (attempted,
correct, independent or hinted) and an aggregate score. Separate conceptual,
method-selection, algebra, formula, notation, speed, and careless causes for
ordinary study-mode mistakes too. Post-mortem updates the normal plan but
cannot overwrite or erase the original exam evidence.

## Authoring: freeze-assessment and mint-assessments

Both take a `FrozenAssessment`-shaped spec: `assessment_id`, `target_id`,
`capability_id`, `prompt`, `rubric`, `expected_evidence`, `source_refs`,
`difficulty`, `question_version`, `rubric_version`, and an optional
`purpose` (`practice`, `retest`, `held_out`, or `mock`; defaults to
`practice`). `freeze-assessment` takes one spec as the whole file.

`mint-assessments` takes a batch:

~~~json
{
  "purpose": "mock",
  "assessments": [
    {"assessment_id": "...", "target_id": "...", "capability_id": "...",
     "prompt": "...", "rubric": {}, "expected_evidence": [],
     "source_refs": [], "difficulty": 0.4,
     "question_version": 1, "rubric_version": 1}
  ]
}
~~~

The top-level `purpose` is the default for entries that omit their own.
Each entry runs through the same validation and pool-isolation guard as
`freeze-assessment` (content already on the practice side cannot be
minted as `held_out`/`mock`, and vice versa); a colliding or invalid entry
is rejected individually, named in the response, without aborting the
rest of the batch. Re-running the same batch is a no-op.

`update-exam-blueprint` merges a JSON patch into `course.exam` (any of the
fields above) and advances `exam.revision` automatically on real change;
setting `revision` in the patch is rejected.

