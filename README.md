# Math Study Agent Skill

Math Study is an interactive, exam-first mathematical-analysis tutor for a
first-year student. It keeps compact persistent evidence in a local workspace,
lets a deterministic state engine calculate mastery/reviews/priority, and lets
the LLM focus on teaching, debugging, and asking for independent work.

## Install

Copy or enable this directory as an Agent Skill package. Runtime data is
relative to the active study workspace. Python 3.11+ is required; the runtime
uses only the standard library. No YAML runtime configuration, database, full
FSRS, or mandatory CAS is needed.

## Start

From the active workspace:

~~~text
python scripts/math_study.py init
python scripts/math_study.py load-syllabus syllabus/example-syllabus.json
python scripts/math_study.py start
~~~

Then write “Продолжаем матан.” to the tutor. It reads the compact local state,
shows due work, and resumes the pending action without requiring a transcript.

For a teacher syllabus, export or prepare JSON with a concepts object. Each
concept can include prerequisites, source_refs, importance, frequency, expected
points, estimated learning minutes, definitions, notation, and exam questions.
Teacher materials and official exam questions outrank generic references; source
conflicts are surfaced.

## Everyday commands

~~~text
python scripts/math_study.py status
python scripts/math_study.py next --minutes 25
python scripts/math_study.py review-due
python scripts/math_study.py mistakes
python scripts/math_study.py roadmap
python scripts/math_study.py end-session
~~~

Natural language is preferred: “Что у меня самое слабое?”, “У меня 25 минут”
and “Давай повторим пределы.” The tutor maps these requests to the CLI and
records one structured observation after each assessable attempt.

## Exam preparation

Set the exam date in state/course.json after init. Use next with the real budget;
priority is recomputed for exam horizon, due state, prerequisites, mastery gap,
expected points, and estimated improvement time. Use:

~~~text
python scripts/math_study.py exam --minutes 45
~~~

Exam mode is the mock exam workflow: it uses mixed tasks, no unsolicited hints,
and minimal feedback until submission or stop. The post-mortem classifies conceptual, method, algebra,
formula, notation, speed, and careless errors.

## Verification

Use verify with a JSON request to run safe numerical checks:

~~~text
python scripts/math_study.py verify request.json
~~~

Core derivative and antiderivative checking is numerical finite-difference
consistency evidence. Symbolic differentiation belongs only to an optional CAS
backend and is never required for the tutor.

## State and recovery

The active workspace stores:

~~~text
state/course.json
state/syllabus.json
state/observations.jsonl
state/concepts.json
state/review_queue.json
state/learner.json
state/session.json
state/current.json
state/revisions/
state/recovery/
~~~

observations.jsonl is append-only canonical learning evidence. concepts.json and
review_queue.json are derived snapshots rebuildable from course/syllabus plus the
log. learner.json and session.json are protected revision snapshots because
profile/runtime details are not present in every observation. Multi-file writes
use revision manifests and recovery; the system does not claim whole-directory
atomicity. Duplicate observation ids with identical payloads are no-ops, while
divergent retries are conflicts.
