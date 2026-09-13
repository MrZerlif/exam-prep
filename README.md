# Math Study Agent Skill

Math Study is an interactive, exam-first mathematical-analysis tutor for a
first-year student. It keeps compact persistent evidence in a local workspace,
lets a deterministic state engine calculate mastery/reviews/priority, and lets
the LLM focus on teaching, debugging, and asking for independent work.

## Install

`skill/math-study/` is the entire, self-contained Agent Skill package: SKILL.md,
references, scripts, schemas, config template, example syllabus, state
templates, and examples all live inside that one directory. Copy or enable
*only* `skill/math-study/` anywhere — a clean temporary directory, another
machine, a skills folder with no access to this repository's root — and it
runs unmodified; nothing outside that directory is required. The repository
root additionally keeps development tests and design docs that are not part
of the installed package. Runtime study state is relative to the active study
workspace (by default, the current working directory when the CLI runs).
Python 3.11+ is required; the runtime uses only the standard library. No YAML
runtime configuration, database, full FSRS, or mandatory CAS is needed.

## Start

From the active workspace (inside the installed `math-study/` directory, or
any workspace pointed at it with `--workspace`/`MATH_STUDY_WORKSPACE`):

~~~text
python scripts/math_study.py init
python scripts/math_study.py load-syllabus syllabus/example-syllabus.json
python scripts/math_study.py start
~~~

Then write “Продолжаем матан.” to the tutor with skill/math-study/ enabled. It reads the compact local state,
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
python scripts/math_study.py validate
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

## Repository layout

~~~text
skill/math-study/            <- the entire installable, self-contained package
├── SKILL.md
├── references/
├── scripts/
│   ├── math_study.py
│   └── math_study_lib/
├── schemas/
├── config/
├── syllabus/
├── state/templates/
└── examples/
tests/                        <- development test suite (not installed)
docs/                         <- design/plan docs (not installed)
README.md
~~~

## State and recovery

The active workspace stores:

~~~text
state/course.json
state/syllabus.json
state/observations.jsonl
state/sessions.jsonl
state/concepts.json
state/review_queue.json
state/learner.json
state/session.json
state/current.json
state/revisions/
state/recovery/
~~~

observations.jsonl is append-only canonical learning evidence; sessions.jsonl
is an append-only log of closed-session summaries (studied/improved/weak
concepts, recurring mistakes, due reviews, next action). concepts.json and
review_queue.json are derived snapshots rebuildable from course/syllabus plus
observations.jsonl. learner.json and session.json are protected revision
snapshots because profile/runtime details are not present in every
observation. Multi-file writes use revision manifests and recovery; the
system does not claim whole-directory atomicity. Duplicate observation ids
with identical payloads are no-ops, while divergent retries are conflicts.

Every command that needs state (status, start, next, review-due, mistakes,
roadmap, record-observation, exam, end-session) goes through one safe-loading
path: it recovers the latest valid revision (falling back through
corrupt/incomplete/hash-mismatched revisions and a corrupt current.json
pointer), and if that revision is stale relative to the canonical inputs -
an observation fsynced to the log but never given a derived revision because
the process crashed in between, a syllabus edit that changed the concept-id
set, or course.json/syllabus.json content changing at all (exam date,
scheduler policy, prerequisites, importance, expected_points - tracked via a
canonicalized-JSON fingerprint stored in the revision manifest, so an edit
with no observed effect on the hash, e.g. pure re-indentation, does not
trigger a needless rebuild) - it replays/recomputes from the canonical
inputs and commits a fresh revision before returning. None of them read the
convenience JSON copies (concepts.json, review_queue.json, etc.) directly,
so a corrupted or deleted convenience file never breaks a normal command.

A session is active only while `phase` is `study` or `exam`; `end-session`
always returns it to `idle` and appends a summary to sessions.jsonl, so the
next `start` always opens a new session_id instead of resuming the closed
one. `status` surfaces the most recent closed-session summary as
`last_session_summary` so a fresh AI context ("Продолжаем матан.") has
continuity without needing the old chat transcript.

`validate` deliberately does *not* go through the safe-loading path above -
it reads course.json/syllabus.json itself, defensively, so a corrupt
canonical file is reported as one row in the checklist instead of crashing
the whole command before diagnostics even start. It runs a full sweep (both
canonical files' readability and schema, schema versions, observation-id
uniqueness/conflicts, revision manifests and hashes, the current pointer,
derived-state-vs-log consistency, session lifecycle, source_refs,
review-queue timestamps, and observation concept-id references), returns a
checklist report (`valid`/`status`/`checks`/`error_count`/`warning_count`),
and exits non-zero when any check reports an error.
