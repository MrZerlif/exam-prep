# exam-prep

This package provides a self-contained, deterministic exam-preparation engine.
Run python scripts/exam_prep.py init once, then use status, next,
record-observation, validate-curriculum, and apply-curriculum.

Runtime state lives in .exam-prep/. The legacy math-study/state/ layout is
not auto-migrated; run migrate --from-math-study PATH explicitly when needed.
The legacy package path remains a temporary compatibility alias during the
transition.

NotebookLM MCP is an optional P2 agent-host integration. When present, the host
normalizes its returned evidence into a SourceEvidenceEnvelope and passes that
data to the CLI. The Python core has no NotebookLM transport or SDK dependency.
