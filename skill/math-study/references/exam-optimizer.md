# Exam optimizer protocol

## Decision rule

For the current budget, rank unlocked concepts with:

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

Fit the activity to 10, 20, 45, 90 minutes, or a deep session. Reserve a
persistence point: after a problem, a review item, or a short recall. A 25-minute
request must not start a two-hour lesson.

## Reviews and interleaving

Use due reviews, then vary evidence type: definition, formula read-aloud,
method recognition, validity conditions, error detection, mini-problem, transfer,
and delayed recall. After initial learning, mix neighboring methods and ask the
learner to choose the method before calculating. Avoid long homogeneous runs.

## Exam mode and post-mortem

Exam mode is stateful and mixed:

- no unsolicited hints;
- neutral wording;
- optional timing;
- minimal feedback until submission or stop;
- grade method selection, correctness, notation, conditions, and time.

Post-mortem turns failures into typed observations. Separate conceptual,
method-selection, algebra, formula, notation, speed, and careless causes. It
updates the normal plan but cannot overwrite or erase the original exam evidence.
