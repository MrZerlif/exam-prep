# exam-prep

This package provides a self-contained, deterministic exam-preparation engine
for any academic or technical subject.
Run python scripts/exam_prep.py init once, then use status, next,
record-observation, validate-curriculum, and apply-curriculum.

Runtime state always lives in .exam-prep/, including the trusted source
manifest at .exam-prep/sources.json. The legacy math-study/state/ layout
is not auto-migrated; run the explicit migration command when needed. Legacy
CLI/env/event aliases remain compatibility shims while old workspaces are
being migrated.

NotebookLM MCP is an optional P2 agent-host integration. When present, the host
normalizes its returned evidence into a SourceEvidenceEnvelope and passes that
data to the CLI. The Python core has no NotebookLM transport or SDK dependency.

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
