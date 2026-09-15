# Exam Prep

An interactive tutor for preparing for one specific exam by one specific date,
built as an Agent Skill over a local state directory. It works from the
learner's own materials and official question list, keeps every attempt as
durable local evidence, and plans each session against the time the learner
actually has.

## How it works

The skill splits one job between two parties that are bad at different things.
The language model runs the conversation: it asks for an attempt, reads what
the learner produced, finds the first invalid step, and classifies the error.
It then emits a single structured observation. A deterministic Python engine
takes that observation and does all the arithmetic — mastery per dimension,
the review queue, prerequisite availability, priority under a time budget — and
persists the result.

The point of that split is what the model *cannot* do. Mastery is not something
the tutor asserts; it is computed from recorded evidence. Saying "I understand"
does not move it. Reading an explanation does not move it. Viewing a full
solution is recorded as exposure (`solution_seen`) and explicitly does not raise
independent mastery — the engine counts an independent success only when an
attempt succeeded with no assistance revealed. A tutor that has been talked into
agreeing that a topic is learned still cannot write that agreement into the
learner's state. `skill/exam-prep/SKILL.md` states the contract; the
anti-illusion rules and the H0–H5 assistance ladder are in
`skill/exam-prep/references/pedagogy.md`.

Canonical evidence is an append-only log, `.exam-prep/observations.jsonl`.
Everything else — mastery, the review queue, priorities — is a derived snapshot
that can be recomputed from that log with `rebuild`.

## What this actually buys you

An audit run against this skill compared it with plain Claude using generic
file tools and no skill loaded, across five scenarios and 28 graded
assertions. The headline is 100% (28/28) with the skill against 76%
(21/28) without it, but that number on its own is misleading and the audit says
so: **21 of the 28 assertions passed identically in both configurations**, and
one entire scenario — resuming after a week away — was a 5/5 tie. Seven
assertions actually discriminated.

The useful finding is in the failures. In two of the five scenarios the
baseline found the `.exam-prep/` directory, explicitly declined to open it —
citing no documented protocol for the format in one case, treating it as opaque
in the other — and then guessed at the learner's level instead. The skill read
local state in all five.

So the honest claim is not that this unlocks a capability a capable model
lacks. It is that it makes reading and using the learner's real recorded
history reliable rather than occasional, and that it gives the state somewhere
durable to live. The audit also measures the cost: roughly 2.2x wall time and
1.4x tokens against the baseline. The raw transcripts and per-run grading are
kept outside this repository, as local working material.

## Exam formats

The teaching track is selected from the exam blueprint stored in
`.exam-prep/course.json`, not hardcoded. `question_model` accepts
`ticket_list`, `problem_set`, `mixed`, or `open`; `delivery` accepts `written`,
`oral`, or `mixed`.

That choice changes the pedagogy. A `ticket_list` exam — a fixed list of oral
questions on theory — runs ticket recitation stages: brief answer structure
first as its own checkpoint, then the model answer, comprehension check,
unprompted reproduction from memory, and delayed recall. A `problem_set` exam
runs the intuition-to-transfer ladder instead. A syllabus with no problems on
the exam never gets a practice-problem stage forced onto it.

The blueprint also carries `question_count`, `time_limit_minutes` or
`per_question_minutes`, `grading_criteria`, `expected_total_points`, and
`follow_up_questions` — the last of which adds a follow-up stage to the
ticket_list track and is surfaced when a mock exam is assembled. The schema
additionally accepts a `verbatim_definitions` boolean, but nothing in the
engine or the tutoring references currently reads it; it is stored and
otherwise inert.

Editing the blueprint through `update-exam-blueprint` advances
`exam.revision` automatically whenever the content really changed, so evidence
recorded under an older blueprint stays distinguishable.

## Quick start

The package is `skill/exam-prep/`. It is self-contained: copy that one
directory into a skills folder and it runs with nothing else from this
repository. State goes to `.exam-prep/` inside the active workspace, resolved
from `--workspace`, then `EXAM_PREP_WORKSPACE`, then the git root, then the
current directory.

Run the CLI from the package's `scripts/` directory. A path from raw materials
to a scored mock exam looks like this:

~~~bash
python3 exam_prep.py --workspace ~/calculus init
python3 exam_prep.py --workspace ~/calculus validate-curriculum proposal.json
python3 exam_prep.py --workspace ~/calculus apply-curriculum proposal.json
python3 exam_prep.py --workspace ~/calculus update-exam-blueprint blueprint.json
python3 exam_prep.py --workspace ~/calculus mint-assessments mock-pool.json
python3 exam_prep.py --workspace ~/calculus start
python3 exam_prep.py --workspace ~/calculus exam --minutes 30
python3 exam_prep.py --workspace ~/calculus end-session
~~~

In practice the learner does not hand-author those JSON files. They give the
tutor their lecture notes and the official ticket list in chat; the tutor
drafts the curriculum proposal and the assessment batch, and runs the commands.
`validate-curriculum` is a dry run that reports identifier problems,
prerequisite cycles, capability mapping errors, and source coverage gaps before
anything is written; `apply-curriculum` is idempotent.

During a session the everyday commands are `status` (add `--compact` when you
only need the inputs for picking the next action rather than a full diagnostic
dump), `next --minutes N`, `review-due`, `mistakes`, and `roadmap`. Learner
evidence enters only through `record-observation`; the derived files are never
hand-edited. `exam` assembles a mock from a minted `purpose=mock` pool, sized
and timed by the blueprint, drawn with a session-seeded shuffle rather than a
sorted truncation, and `end-session` closes it with a per-question post-mortem.
An attempt only reaches that post-mortem if its observation carries the
ticket's `assessment_id`; without it the attempt is recorded as ordinary
evidence and the ticket grades as unattempted, which the CLI now says at the
time of recording rather than at the end.

The full command catalog, with every flag and payload format, is
`skill/exam-prep/references/commands.md`. It is the source of truth; this
section is only a path through it.

## Optional NotebookLM MCP integration

If the agent host exposes a NotebookLM (now Gemini Notebook) MCP server, the
host can pull citations from course material and hand them to
`ingest-source-evidence` as a normalized envelope, which is what makes a
`source_id` count as registered rather than merely declared. The recommended
implementation is `jacob-bd/gemini-notebook-mcp-cli`.

Treat it as experimental. It was exercised in zero of the five audit scenarios,
so this path has no observed behavior on record. The upstream project reaches
internal, undocumented Google endpoints and warns they can change without
notice; it authenticates as the user's own Google account through browser
cookies rather than a scoped credential, with a cookie lifetime of roughly two
to four weeks; and usage is metered on a rolling window plus a weekly cap.

Without it, everything works. The Python core has no MCP transport, SDK, or
provider dependency, and an absent or failing provider is a normal diagnostic
state rather than an error. NotebookLM's own quizzes and flashcards are
deliberately not importable as assessments — they carry no `spec_hash`, no
hold-out guarantee, and no blueprint binding; generated questions have to go
through the normal curriculum and minting path. See
`skill/exam-prep/references/notebooklm-mcp.md`.

## What is not verified

Stated plainly, because these are the gaps a reviewer would otherwise find
after the claims above:

The NotebookLM branch has never run end to end. Zero of five audit scenarios
attached a provider host.

Whether the skill reliably *activates* on a real request has not been measured.
The trigger-rate evaluation was written but never produced a valid result — it
is blocked on an unauthenticated CLI in the test environment. A skill that does
not trigger is a skill that does not run, and that risk is currently
unquantified.

Working from photographs of handwritten work is architecturally possible, since
the tutor authors the observation from whatever it can read, but all five audit
scenarios used typed text. It has not been tested.

The audit sampled each scenario once. Run-to-run variance was not measured, so
the per-scenario figures describe single runs, not stable averages.

`verify` covers derivatives and antiderivatives only. Limits, series
convergence, and algebraic identities return `unavailable`, and the tutor's own
judgment is the only check available for them.

## What this deliberately does not do

There are no streaks, no XP, no badges, no missed-day counters, and no language
that frames a gap in studying as a personal failure. For a learner who is
already struggling to start, a counter that resets to zero is a reason to avoid
opening the tool at all, which is the opposite of the intended effect. The one
counter that exists, `clean_streak`, is internal bookkeeping for when a
recurring mistake can be considered resolved, and is never presented to the
learner as a score.

There is also no external service that owns learner state. The canonical log is
a local file. A provider integration can contribute citations as provenance
input; it can never own, overwrite, or become the source of the learner's
record.

## Requirements and maturity

Standard library only. The complete third-party dependency list is empty; the
package imports nothing outside `argparse`, `ast`, `collections`, `copy`,
`dataclasses`, `datetime`, `hashlib`, `json`, `math`, `operator`, `os`,
`pathlib`, `random`, `re`, `shutil`, `sys`, `tempfile`, `typing`, `uuid`, and
`zoneinfo`. No database, no YAML runtime config, no mandatory CAS.

Python 3.11 or newer is the intended floor, though the repository ships no
packaging metadata that enforces it — the oldest feature actually used is
`zoneinfo` (3.9). The suite is verified on Python 3.12.3: **337 tests, all
passing**, run with `python3 -m unittest discover -s tests -t .` from the
repository root.

Multi-file writes go through revision manifests with a recovery path; the
project does not claim whole-directory atomicity. Every stateful command loads
through one recovery path that falls back through corrupt, incomplete, or
hash-mismatched revisions and replays the canonical log when a derived snapshot
is stale, so a damaged convenience file does not break a normal command.

## Repository layout

~~~text
skill/exam-prep/              the installable, self-contained skill package
├── SKILL.md                  the skill contract the model loads
├── references/               6 protocol documents (commands, pedagogy,
│                             exam-optimizer, source-of-truth, verification,
│                             notebooklm-mcp)
├── scripts/                  exam_prep.py plus exam_prep_lib/
├── schemas/                  19 JSON schemas for every payload and state file
├── templates/                initial state files written by init
├── examples/                 example syllabus, curriculum proposal,
│                             observation proposal, mock exam, and others
└── config/                   config.template.json
tests/                        49 test modules plus tests/scenarios/
                              (not part of the installed package)
~~~

A workspace in use holds `course.json` and `syllabus.json` as canonical course
input, `observations.jsonl` and `sessions.jsonl` as append-only logs,
`assessments.jsonl` for frozen assessments, `source_evidence.jsonl` and
`sources.json` for registered sources, `targets.json` and `review_queue.json`
as rebuildable derived snapshots, `learner.json` and `session.json` as
protected snapshots, plus `current.json`, `revisions/`, and `recovery/`.

## Where to read more

`skill/exam-prep/SKILL.md` is the contract the model actually follows. Beneath
it, `references/commands.md` documents every command, `references/pedagogy.md`
the tracks and assistance ladder, `references/exam-optimizer.md` the
prioritization formula and exam mode, `references/source-of-truth.md` the
authority order between sources, `references/verification.md` the numeric
answer checks, and `references/notebooklm-mcp.md` the optional provider
integration.
