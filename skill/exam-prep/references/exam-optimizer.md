# Exam and budget protocol

## Start with the whole course

At course start, ask the learner to rate all targets in one message, then
submit `triage <path.json>` with
`{"ratings": {"target-001": 0, "target-002": 1, "target-003": 2}}`:
`0` do not know, `1` remember vaguely, or `2` know. Store these as
`self_rating`; they are not evidence and do not change mastery. Use ratings
only to order targets that have no evidence. Break ties by syllabus order,
then respect prerequisites and source importance.

Run `plan` with the current budget and read its `coverage` block. It reports
total targets, targets with evidence, targets without evidence, available
minutes, minutes per target, required targets per hour, and `pace_at_risk`.
At the start, after the first practice block, and whenever the budget changes,
refresh the plan and show the learner total questions on the exam, completed
questions, remaining coverage, available time, and required pace in questions
per hour. Use the course's `available_minutes_by_day` when present; otherwise
use the stated plan arguments. Name a pace risk as soon as `pace_at_risk` is
true, then explain the highest-value budget-fitting choice.

## Prioritize useful work

For the current budget, rank unlocked targets by:

~~~text
exam value × mastery gap × urgency × prerequisite readiness
× improvement potential ÷ estimated learning minutes
~~~

Use teacher or official importance, frequency, expected points, exam horizon,
due reviews, and the improvement possible inside the remaining budget. Recompute
when mastery, due state, exam details, time, or budget changes. It is valid to
defer low-yield perfection and repair only a prerequisite needed for a
higher-value task. Do not require complete prerequisite mastery before starting
useful exam work.

Fit each activity to the minutes the learner actually has and leave a
persistence point for a problem, review, or short recall. Never round a budget
up or start work that cannot reach a useful stopping point.

## Mixed-format tickets

`course.exam.ticket_slots` describes the theory and problem counts in a ticket.
For example: `[{"kind": "theory", "count": 2}, {"kind": "problem", "count": 1}]`.
Route theory slots through `ticket_list` recitation. Route each problem slot
through the problem ladder in `references/pedagogy.md`. Keep the actual exam
track and study practice distinct: do not add practice problems to a
theory-only ticket.

## Review and exam mode

Use due reviews, then vary evidence type: definition, formula read-aloud,
method recognition, validity conditions, error detection, mini-problem,
transfer, and delayed recall. After initial learning, mix neighboring methods
and ask the learner to choose the method before calculating.

`exam` is stateful and blueprint-driven. Use its `question_count`,
`time_limit_minutes` or `per_question_minutes`, `delivery`,
`follow_up_questions`, and `grading_criteria`. Give no unsolicited hints and
minimal feedback until submission or stop. At the end, grade against the
blueprint and report each ticket's attempt and result. Keep exam evidence and
the post-mortem; do not replace them with study exposure.
