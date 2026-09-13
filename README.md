# Exam Prep Agent Skill

Exam Prep is an interactive, exam-first subject-neutral tutor for a
first-year student. It keeps compact persistent evidence in a local workspace,
lets a deterministic state engine calculate mastery/reviews/priority, and lets
the LLM focus on teaching, debugging, and asking for independent work.

## Install

`skill/exam-prep/` is the entire, self-contained Agent Skill package: SKILL.md,
references, scripts, schemas, config template, example syllabus, state
templates, and examples all live inside that one directory. Copy or enable
*only* `skill/exam-prep/` anywhere — a clean temporary directory, another
machine, a skills folder with no access to this repository's root — and it
runs unmodified; nothing outside that directory is required. The repository
root additionally keeps development tests and design docs that are not part
of the installed package. Runtime study state is relative to the active study
workspace (by default, the current working directory when the CLI runs).
Python 3.11+ is required; the runtime uses only the standard library. No YAML
runtime configuration, database, full FSRS, or mandatory CAS is needed.

## Start

From the active workspace (inside the installed `exam-prep/` directory, or
any workspace pointed at it with `--workspace`/`EXAM_PREP_WORKSPACE`):

~~~text
python scripts/exam_prep.py init
python scripts/exam_prep.py load-syllabus examples/example-syllabus.json
python scripts/exam_prep.py start
~~~

Then write “Continue studying.” to the tutor with skill/exam-prep/ enabled. It reads the compact local state,
shows due work, and resumes the pending action without requiring a transcript.

Normally give the tutor materials, exam questions, or source references. The
agent or a SourceProvider analyzes them into a v2 CurriculumProposal; the
deterministic validator produces LearningTargets, validates the prerequisite
graph and exam mappings, reports capability warnings and source coverage gaps,
and persists the syllabus. New users should not hand-author concepts JSON.
Teacher materials and official exam questions outrank generic references; source
conflicts are surfaced.

## Everyday commands

~~~text
python scripts/exam_prep.py status
python scripts/exam_prep.py next --minutes 25
python scripts/exam_prep.py review-due
python scripts/exam_prep.py mistakes
python scripts/exam_prep.py roadmap
python scripts/exam_prep.py validate
python scripts/exam_prep.py end-session
~~~

Natural language is preferred: “Что у меня самое слабое?”, “У меня 25 минут”
and “Давай повторим пределы.” The tutor maps these requests to the CLI and
records one structured observation after each assessable attempt.

## Exam preparation

Set the exam date in `.exam-prep/course.json` after init. Use next with the real budget;
priority is recomputed for exam horizon, due state, prerequisites, mastery gap,
expected points, and estimated improvement time. Use:

~~~text
python scripts/exam_prep.py exam --minutes 45
~~~

Exam mode is the mock exam workflow: it uses mixed tasks, no unsolicited hints,
and minimal feedback until submission or stop. The post-mortem classifies conceptual, method, algebra,
formula, notation, speed, and careless errors.

## Verification

Use verify with a JSON request to run safe numerical checks:

~~~text
python scripts/exam_prep.py verify request.json
~~~

Core derivative and antiderivative checking is numerical finite-difference
consistency evidence. Symbolic differentiation belongs only to an optional CAS
backend and is never required for the tutor.

## Repository layout

~~~text
skill/exam-prep/            <- the entire installable, self-contained package
├── SKILL.md
├── references/
├── scripts/
│   ├── exam_prep.py
│   └── exam_prep_lib/
├── schemas/
├── config/
├── templates/
└── examples/
tests/                        <- development test suite (not installed)
docs/                         <- design/plan docs (not installed)
README.md
~~~

## State and recovery

The active workspace stores:

~~~text
.exam-prep/course.json
.exam-prep/syllabus.json
.exam-prep/observations.jsonl
.exam-prep/sessions.jsonl
.exam-prep/targets.json
.exam-prep/assessments.jsonl
.exam-prep/source_evidence.jsonl
.exam-prep/review_queue.json
.exam-prep/learner.json
.exam-prep/session.json
.exam-prep/current.json
.exam-prep/revisions/
.exam-prep/recovery/
~~~

observations.jsonl is append-only canonical learning evidence; sessions.jsonl
is an append-only log of closed-session summaries (studied/improved/weak
targets, recurring mistakes, due reviews, next action). targets.json and
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
the process crashed in between, a syllabus edit that changed the target-id
set, or course.json/syllabus.json content changing at all (exam date,
scheduler policy, prerequisites, importance, expected_points - tracked via a
canonicalized-JSON fingerprint stored in the revision manifest, so an edit
with no observed effect on the hash, e.g. pure re-indentation, does not
trigger a needless rebuild) - it replays/recomputes from the canonical
inputs and commits a fresh revision before returning. None of them read the
convenience JSON copies (targets.json, review_queue.json, etc.) directly,
so a corrupted or deleted convenience file never breaks a normal command.

A session is active only while `phase` is `study` or `exam`; `end-session`
always returns it to `idle` and appends a summary to sessions.jsonl, so the
next `start` always opens a new session_id instead of resuming the closed
one. `status` surfaces the most recent closed-session summary as
`last_session_summary` so a fresh AI context ("Continue studying.") has
continuity without needing the old chat transcript.

## Migration from math-study

The new CLI never treats `<workspace>/state/` as its target. When legacy state
is detected, migrate it explicitly:

~~~text
python skill/exam-prep/scripts/exam_prep.py migrate --from-math-study C:\path\to\math-study
~~~

Migration reads `<workspace>\state\`, writes `<workspace>\.exam-prep\`, keeps
the legacy source untouched, fingerprints the source, rebuilds targets and the
review queue, and records legacy evidence as `assessment_integrity:
legacy_unfrozen`. Repeating the command for the same unchanged source is
idempotent; a different source or an occupied unrelated target is rejected.

`validate` deliberately does *not* go through the safe-loading path above -
it reads course.json/syllabus.json itself, defensively, so a corrupt
canonical file is reported as one row in the checklist instead of crashing
the whole command before diagnostics even start. It runs a full sweep (both
canonical files' readability and schema, schema versions, observation-id
uniqueness/conflicts, revision manifests and hashes, the current pointer,
derived-state-vs-log consistency, session lifecycle, source_refs,
review-queue timestamps, and observation target-id references), returns a
checklist report (`valid`/`status`/`checks`/`error_count`/`warning_count`),
and exits non-zero when any check reports an error.
