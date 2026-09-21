# exam-prep

This package provides a self-contained, deterministic exam-preparation engine
for any academic or technical subject.
Run `python scripts/exam_prep.py status` first. A new workspace reports
`uninitialized` without creating `.exam-prep`; run `init` once, then use
`status`, `next`, `record-observation`, `validate-curriculum`, and
`apply-curriculum`. Repeating `init` is a safe no-op that preserves canonical
files. If status reports `incomplete_workspace`, run `validate` and repair the
missing canonical input explicitly; initialization never overwrites it.

Runtime state always lives in .exam-prep/, including the trusted source
manifest at .exam-prep/sources.json. The legacy math-study/state/ layout
is not auto-migrated; run the explicit migration command when needed. Legacy
CLI/env/event aliases remain compatibility shims while old workspaces are
being migrated. Workspace discovery accepts only `EXAM_PREP_WORKSPACE`, legacy
`MATH_STUDY_WORKSPACE`, and `EXAM_PREP_PROJECT_ROOT`; generic host variables
`PROJECT_ROOT` and `WORKSPACE_ROOT` are ignored. `config/config.template.json`
is illustrative documentation only; the runtime does not load it automatically.

For engine-owned activity timing, call `start-activity ACTIVITY_ID`, optionally
`finish-activity`, and then record a v2 observation with the same
`activity_id`. Use `activity-status` to inspect an interrupted workflow and
`discard-activity` when no observation will be recorded. The engine records
only `elapsed_seconds`: `expected_seconds` remains `None`, so timing does not
update the `speed` mastery dimension in this release. `end-session` persists an
evaluation summary, while full `status` exposes `course_wide_calibration` and
`status --compact` omits it. `next --minutes` and `exam --minutes` accept only
positive integers.

NotebookLM MCP is an optional P2 agent-host integration. When present, the host
normalizes its returned evidence into a SourceEvidenceEnvelope and passes that
data to the CLI. Connector availability is not consent: installation,
authentication, material transfer, and every external write require explicit
user confirmation naming the material and destination. The Python core has no
NotebookLM transport or SDK dependency.

The test suite is not part of this package. It lives in the source repository
(this directory is `skill/exam-prep/` there), and every command below is run
from that repository's root, not from an installed copy:

~~~bash
python -m unittest discover -s tests -t .
python tests/scenarios/run_scenarios.py --deterministic
~~~

Deterministic engine tests check runtime behavior and persistence only.
Fresh-context behavioral evaluation is a separate host-level/manual step:
export prompts with `run_scenarios.py --emit-eval-set ...`, run each packet in
the chosen host, then submit explicit independent scores to
`tests/scenarios/evaluate_transcripts.py`. Passing deterministic tests alone
does not claim behavioral compliance. Discovery has a separate
positive/negative packet export: `run_scenarios.py --emit-activation-set ...`.
The primary package examples are subject-neutral. The separate
examples/mathematics-regression-syllabus.json is retained only for
mathematics-specific regression coverage.

## Implementation roadmap

| Priority | Scope |
| --- | --- |
| P0 | Structured SourceRef, provenance and authority semantics, generic SourceProvider contract, minimal local fallback, and explicit coverage gaps. |
| P1 | Richer local source manifest/retrieval, automatic curriculum proposal and validation, ExamAnswerPack, and source-aware optimizer improvements. |
| P2 | Optional NotebookLM MCP through the agent host, additional external SourceProviders, OCR/rich ingestion where needed, and richer provider artifacts/research capabilities. |

The normal workflow is materials/sources -> host or SourceProvider analysis ->
CurriculumProposal -> deterministic validation -> LearningTargets, prerequisite
graph, exam-question mapping, capabilities, coverage report -> persisted
syllabus. P2 integrations are additive. Core operation and canonical learner
state remain local and deterministic when a provider is absent or fails.

The deterministic engine, CLI, schemas, and persistence behavior are the v1.0
baseline. Fatigue detection, workload-aware activity selection, and trusted
expected-time evidence are not implemented yet.
