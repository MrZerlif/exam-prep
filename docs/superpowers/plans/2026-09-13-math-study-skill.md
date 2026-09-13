# Math Study Agent Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a portable, restart-safe Agent Skill and stdlib-only state engine that maximizes first-year mathematical-analysis exam performance from persistent evidence, adaptive practice, and time-aware prioritization.

**Architecture:** The LLM tutor emits only validated observation proposals and follows the teaching contract in `SKILL.md`; deterministic Python code enriches events, appends them to `state/observations.jsonl`, reduces evidence into revisioned snapshots, and computes review/priority state. The package separates canonical course/syllabus inputs, canonical learning evidence, rebuildable derived learning state, and protected learner/session snapshots. One CLI exposes every deterministic operation.

**Tech Stack:** Python 3.11+ standard library only for runtime and tests; JSON and JSONL; `unittest`; `ast`-restricted expression evaluation; optional dynamically detected CAS adapter with no mandatory dependency.

**Spec:** `docs/superpowers/specs/2026-09-13-math-study-design.md`

## Global Constraints

- No YAML; machine-readable course/state files use JSON and evidence uses JSONL.
- No external JSON Schema validator; validation uses a small standard-library validator.
- The LLM produces structured observations; the deterministic state engine calculates and persists mastery, review, priority, and recovery state.
- `observations.jsonl` is append-only canonical learning evidence; all evidence-derived state rebuilds from canonical course/syllabus inputs plus this log.
- Multi-file writes are revisioned and recoverable; do not claim that the entire multi-file update is atomic.
- Do not add a database, full FSRS implementation, mandatory CAS/SymPy dependency, web service, background scheduler, or LMS integration.
- Core derivative and antiderivative checks are numerical finite-difference verification; symbolic differentiation is isolated in an optional CAS backend.
- Assistance is stored once; independence is derived from structured assistance data.
- Diagnostic confidence and learner self-confidence are separate fields and neither is task correctness.
- Priority is contextual and recomputed for current exam horizon, budget, due status, prerequisites, and mastery; it is not a permanent concept property.
- Concept-local recurring mistakes are separate from promoted cross-concept learner patterns.
- Teacher materials, official exam lists, lectures, and assigned problem sets outrank generic model knowledge; conflicts are surfaced.
- Runtime state is relative to the active study workspace, while package examples are inert fixtures.
- Every implementation task starts with a failing test or an explicit RED behavior check and ends with a focused test run and commit.

## File Map

Create the following focused units:

- `SKILL.md` — concise activation, resume, tutoring, evidence, exam-mode, and persistence contract; delegates detailed protocols to references.
- `README.md` — installation, initialization, natural-language commands, CLI examples, syllabus loading, state location, and recovery behavior.
- `references/pedagogy.md` — fading stages, hint ladder, anti-illusion rules, debugging dialogue, interleaving, and adaptive difficulty.
- `references/exam-optimizer.md` — exam-cram scheduling, priority inputs, time budgets, triage, mock exams, and post-mortem.
- `references/math-verification.md` — safe numerical checks, finite-difference limitations, and optional CAS boundary.
- `references/source-of-truth.md` — source precedence, provenance, conflicts, and syllabus ingestion rules.
- `schemas/*.schema.json` — human-readable JSON schema documents for course, syllabus, learner, session, observation proposal/event, derived concepts, review queue, and revisions.
- `config/config.template.json` — JSON-only policy defaults, time budgets, mastery thresholds, scheduler limits, and verification tolerances.
- `syllabus/example-syllabus.json` — small source-backed calculus dependency graph fixture.
- `state/templates/*.json` — inert course, learner, session, current-pointer, and review templates; no generated user state in the package.
- `examples/*.json*` — observation, mock exam, and session examples.
- `scripts/math_study.py` — single CLI entry point and argument parsing.
- `scripts/math_study_lib/schema_validation.py` — stdlib schema/type/range/enum validation.
- `scripts/math_study_lib/storage.py` — append-only log, idempotency, fsync, revision manifests, pointer, recovery, and workspace paths.
- `scripts/math_study_lib/reducer.py` — assistance derivation, multidimensional mastery, recurring errors, statuses, and rebuild.
- `scripts/math_study_lib/scheduler.py` — exam-cram reviews, contextual priority, interleaving candidates, and cache invalidation.
- `scripts/math_study_lib/verifier.py` — restricted numeric parser/evaluator, derivative checks, antiderivative finite differences, and sanity checks.
- `scripts/math_study_lib/symbolic_backend.py` — optional CAS protocol with explicit unavailable/inconclusive results.
- `tests/test_*.py` — deterministic unit/integration tests using only `unittest`.
- `tests/scenarios/*.md` and `tests/scenarios/*.json` — synthetic learner and pressure scenarios used for fresh-context behavior checks.

The runtime library is importable from the CLI directory without third-party packages. Tests set up a temporary workspace for every case and never mutate package fixtures.

---

### Task 1: Establish RED pressure scenarios and test harness

**Files:**
- Create: `tests/scenarios/pressure-cases.json`
- Create: `tests/scenarios/baseline-prompts.md`
- Create: `tests/test_skill_contract.py`
- Create: `tests/__init__.py`

**Interfaces:**
- Consumes: approved spec and learner profile requirements.
- Produces: executable scenario manifest and a RED gate proving the skill package is not yet present.

- [ ] **Step 1: Write the failing contract test**

Create a test that asserts the package contract is currently absent:

~~~python
from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class SkillContractRedTest(unittest.TestCase):
    def test_skill_entrypoint_is_not_implemented_before_green_phase(self):
        self.assertFalse((ROOT / "SKILL.md").exists())


if __name__ == "__main__":
    unittest.main()
~~~

- [ ] **Step 2: Write the pressure scenario manifest**

Put six cases in `tests/scenarios/pressure-cases.json` with ids `beginner_limits`, `chain_rule_recurrence`, `twenty_four_hour_triage`, `restart`, `solution_view`, and `exam_mode`. Each case must contain a fresh-context prompt, learner facts, forbidden tutor behavior, and observable pass criteria. Include an additional crash-retry case with duplicate `observation_id` and a conflicting retry.

- [ ] **Step 3: Record the baseline behavior check**

Use the prompts in `tests/scenarios/baseline-prompts.md` with a clean tutor context that has no `SKILL.md`. Record the minimum failures expected from an unstructured tutor: no durable resume, premature full solution, coarse mastery, no exam-budget triage, or no recurring-error persistence. Keep this as a behavior baseline, not as runtime state.

- [ ] **Step 4: Run the RED check**

Run:

~~~text
python -m unittest tests.test_skill_contract -v
~~~

Expected: PASS for the intentional RED assertion that `SKILL.md` does not exist. If it fails because an implementation file already exists, replace the assertion with a behavior test that the required protocol marker is absent and keep this task's baseline before the GREEN phase.

- [ ] **Step 5: Commit the baseline**

~~~text
git add tests
git commit -m "test: add math study pressure scenarios"
~~~

### Task 2: Define JSON documents and stdlib validation

**Files:**
- Create: `schemas/course.schema.json`
- Create: `schemas/syllabus.schema.json`
- Create: `schemas/observation-proposal.schema.json`
- Create: `schemas/observation-event.schema.json`
- Create: `schemas/concepts.schema.json`
- Create: `schemas/review-queue.schema.json`
- Create: `schemas/learner.schema.json`
- Create: `schemas/session.schema.json`
- Create: `schemas/revision-manifest.schema.json`
- Create: `scripts/math_study_lib/__init__.py`
- Create: `scripts/math_study_lib/schema_validation.py`
- Create: `tests/test_schema_validation.py`

**Interfaces:**
- Consumes: JSON schema documents and the field ownership rules in Section 4.1 of the spec.
- Produces: `validate_document(document: object, schema: dict) -> None`, `validate_observation_proposal(document: dict) -> None`, and `validate_state_bundle(bundle: dict) -> None`. Validation errors use a custom `SchemaError(ValueError)` carrying a JSON path.

- [ ] **Step 1: Write failing validator tests**

Cover valid proposal acceptance, missing `observation_id`, invalid enum, out-of-range confidence, engine-owned fields in an LLM proposal, malformed assistance, and a state bundle with non-numeric mastery. Use `unittest` and assert the error path.

~~~python
def test_llm_proposal_rejects_engine_owned_timing(self):
    proposal = valid_proposal()
    proposal["elapsed_seconds"] = 12
    with self.assertRaisesRegex(SchemaError, "elapsed_seconds"):
        validate_observation_proposal(proposal)
~~~

- [ ] **Step 2: Run the validator tests to verify failure**

Run:

~~~text
python -m unittest tests.test_schema_validation -v
~~~

Expected: FAIL because the validator module and schema fixtures are not implemented.

- [ ] **Step 3: Implement minimal JSON schema documents**

Define object properties, required fields, additional-property policy, enums, and numeric ranges. Observation proposals contain only learner/task evidence fields; canonical event schemas separately require engine-enriched `recorded_at`, `session_id`, `expected_seconds`, and nullable `elapsed_seconds`. Do not add stored `independence` or `hint_level`.

- [ ] **Step 4: Implement the stdlib validator**

Implement recursive checks for object, array, string, number, boolean, null, required, enum, minimum/maximum, and additional properties. Load schemas with `json.load`; do not import a validation package. Add helpers that reject LLM-owned timing/session metadata before storage.

- [ ] **Step 5: Run tests to verify green**

Run:

~~~text
python -m unittest tests.test_schema_validation -v
~~~

Expected: PASS.

- [ ] **Step 6: Commit schema contract**

~~~text
git add schemas scripts/math_study_lib/schema_validation.py tests/test_schema_validation.py
git commit -m "feat: add stdlib JSON schema validation"
~~~

### Task 3: Implement append-only evidence and revision recovery

**Files:**
- Create: `scripts/math_study_lib/storage.py`
- Create: `tests/test_storage_recovery.py`

**Interfaces:**
- Consumes: validated proposals, active session id, task metadata, measured elapsed time, and a workspace path.
- Produces: `StudyStore(root: Path)`; `append_observation(proposal: dict, session_id: str, recorded_at: str, expected_seconds: int | None, elapsed_seconds: int | None) -> AppendResult`; `read_complete_observations() -> list[dict]`; `commit_revision(derived: dict, session: dict, learner: dict) -> RevisionManifest`; `recover() -> RecoveryResult`; and `rebuild_from_log() -> DerivedStateInput`.

- [ ] **Step 1: Write failing storage tests**

Test append-first ordering, engine enrichment, duplicate identical retry as no-op, duplicate divergent retry as conflict, fsync-safe line ending, revision manifest hashes, corrupt pointer recovery, highest-valid-revision selection, and ignored partial final JSONL line.

~~~python
def test_identical_observation_retry_is_idempotent(self):
    first = store.append_observation(proposal, "session-1", now, 90, 22)
    second = store.append_observation(proposal, "session-1", now, 90, 22)
    self.assertEqual(first.observation_id, second.observation_id)
    self.assertEqual(store.read_complete_observations(), [first.canonical_event])
    self.assertEqual(first.revision_created, second.revision_created)
~~~

- [ ] **Step 2: Run tests to verify failure**

Run:

~~~text
python -m unittest tests.test_storage_recovery -v
~~~

Expected: FAIL because `StudyStore` does not exist.

- [ ] **Step 3: Implement workspace paths and append idempotency**

Create state directories with `Path.mkdir`. Validate before mutation. Enrich the proposal only in the engine, use the supplied engine clock/session/task metadata, serialize one compact JSON object per line, flush, and call `os.fsync` where supported. Retry lookup compares canonical payload by `observation_id`; equal payload returns no-op and divergent payload raises a conflict.

- [ ] **Step 4: Implement revisioned snapshots**

Write derived JSON, `learner.json`, and `session.json` into a new numbered revision directory. Write `manifest.json` with revision number, last complete observation id/line, byte offset, and hashes. Validate the directory before atomically replacing only `current.json`. Materialized convenience copies are written after the pointer.

- [ ] **Step 5: Implement recovery and rebuild inputs**

Scan valid manifests when `current.json` is missing or corrupt, quarantine hash-mismatched revisions under `state/recovery`, ignore and diagnose an incomplete final JSONL line, and return canonical course/syllabus plus complete evidence to the reducer. Do not reconstruct learner preferences or pending session state from evidence.

- [ ] **Step 6: Run focused tests and commit**

Run:

~~~text
python -m unittest tests.test_storage_recovery -v
~~~

Expected: PASS.

~~~text
git add scripts/math_study_lib/storage.py tests/test_storage_recovery.py
git commit -m "feat: add append-only evidence and revision recovery"
~~~

### Task 4: Build deterministic mastery reduction and error ownership

**Files:**
- Create: `scripts/math_study_lib/reducer.py`
- Create: `tests/test_reducer.py`

**Interfaces:**
- Consumes: canonical course/syllabus data and complete canonical events.
- Produces: `derive_assistance_band(assistance: dict) -> str` and `reduce_learning_state(course: dict, syllabus: dict, events: list[dict], policy: dict) -> dict` returning concepts, evidence counters, mastery dimensions, confidences, statuses, and concept-local recurring mistakes.

- [ ] **Step 1: Write failing reducer tests**

Cover H0 independent evidence, H1 light scaffold, H2/H3 guided evidence, H4 heavy scaffold, H5/full-solution non-promotion, separate diagnostic versus learner confidence, task-to-dimension updates, speed only from engine timing, one repeated concept error becoming recurring, and no global duplicate error ledger.

~~~python
def test_solution_view_does_not_promote_mastery(self):
    before = concept_state(events=[])
    after = concept_state(events=[event(outcome="solution_seen",
                                        full_solution_viewed=True)])
    self.assertEqual(before["mastery"], after["mastery"])
~~~

- [ ] **Step 2: Run tests to verify failure**

Run:

~~~text
python -m unittest tests.test_reducer -v
~~~

Expected: FAIL because reducer functions do not exist.

- [ ] **Step 3: Implement assistance and evidence mapping**

Derive the assistance band from requested levels, scaffold types, partial transformation, and full-solution exposure. Map task types to relevant mastery dimensions. Apply bounded configurable evidence weights by outcome and assistance band. Treat low diagnostic confidence as provisional evidence and preserve learner self-confidence independently.

- [ ] **Step 4: Implement mastery, status, and recurring-error reduction**

Update conceptual, procedural, recall, transfer, and speed dimensions with clamped deterministic values. Require recent independent evidence plus transfer/exam evidence for `exam_ready`. Record concrete recurring mistakes under the affected concept. Promote cross-concept patterns only as summaries after the configured multi-concept/multi-session threshold; never copy a second canonical error list into `learner.json`.

- [ ] **Step 5: Run tests and commit**

Run:

~~~text
python -m unittest tests.test_reducer -v
~~~

Expected: PASS.

~~~text
git add scripts/math_study_lib/reducer.py tests/test_reducer.py
git commit -m "feat: reduce multidimensional learning evidence"
~~~

### Task 5: Add exam-cram review scheduling, priority, and interleaving

**Files:**
- Create: `scripts/math_study_lib/scheduler.py`
- Create: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: course policy, syllabus graph, derived concept state, canonical events, current time, exam revision, and requested budget.
- Produces: `compute_priority(concept_id: str, syllabus: dict, concepts: dict, reviews: dict, course: dict, now: datetime, budget_minutes: int) -> dict`; `build_review_queue(events: list[dict], concepts: dict, course: dict, now: datetime) -> dict`; and `select_next_activity(...) -> dict`.

- [ ] **Step 1: Write failing scheduler tests**

Test due weak concepts outrank low-yield perfection, prerequisite readiness, exam urgency, expected points/frequency, improvement time, 10/20/45/90-minute fit, interval shortening after failures, interval extension after independent recall, interleaving neighboring methods, and contextual cache invalidation after budget/exam revision/mastery change.

~~~python
def test_priority_changes_with_budget_context(self):
    short = compute_priority("chain_rule", fixture.syllabus, fixture.concepts,
                             fixture.reviews, fixture.course, now, 20)
    long = compute_priority("chain_rule", fixture.syllabus, fixture.concepts,
                            fixture.reviews, fixture.course, now, 90)
    self.assertNotEqual(short["computed_for"]["budget_minutes"],
                        long["computed_for"]["budget_minutes"])
~~~

- [ ] **Step 2: Run tests to verify failure**

Run:

~~~text
python -m unittest tests.test_scheduler -v
~~~

Expected: FAIL because scheduler functions do not exist.

- [ ] **Step 3: Implement review intervals**

Use a compact exam-cram scheduler, not full FSRS. Derive due time from outcome, assistance band, recurrence, recall task type, exam horizon, and configurable maximum interval. Keep review evidence types varied: definition, read-aloud, method recognition, error detection, mini-problem, transfer, and delayed recall.

- [ ] **Step 4: Implement contextual priority and interleaving**

Compute exam value, mastery gap, urgency, prerequisite readiness, improvement potential, and estimated learning time. Return a score plus an explanation and a `computed_for` context containing budget and exam revision. Mix neighboring concepts and method-selection tasks after initial learning. Never persist priority as an unconditional concept field.

- [ ] **Step 5: Run tests and commit**

Run:

~~~text
python -m unittest tests.test_scheduler -v
~~~

Expected: PASS.

~~~text
git add scripts/math_study_lib/scheduler.py tests/test_scheduler.py
git commit -m "feat: add exam-cram review scheduler"
~~~

### Task 6: Add core numerical verification and optional CAS boundary

**Files:**
- Create: `scripts/math_study_lib/verifier.py`
- Create: `scripts/math_study_lib/symbolic_backend.py`
- Create: `tests/test_verifier.py`

**Interfaces:**
- Consumes: restricted expression strings, variable/value samples, proposed derivative or antiderivative expression, domain exclusions, and tolerances.
- Produces: `verify_derivative(expression: str, derivative: str, variable: str, samples: list[float], tolerance: float) -> VerificationResult`; `verify_antiderivative(integrand: str, antiderivative: str, variable: str, samples: list[float], tolerance: float) -> VerificationResult`; and `symbolic_backend.verify(request: dict) -> dict` with statuses `passed`, `failed`, `inconclusive`, or `unavailable`.

- [ ] **Step 1: Write failing verification tests**

Test safe arithmetic, rejection of calls/attributes/imports, derivative finite-difference pass/fail, antiderivative finite-difference pass/fail, singular-point avoidance, reverse substitution, numerical sanity checks, and CAS absence without importing SymPy.

~~~python
def test_antiderivative_uses_finite_difference(self):
    result = verify_antiderivative("2*x", "x**2", "x", [0.5, 1.5], 1e-4)
    self.assertTrue(result.passed)
    self.assertIn("finite_difference", result.checks)
~~~

- [ ] **Step 2: Run tests to verify failure**

Run:

~~~text
python -m unittest tests.test_verifier -v
~~~

Expected: FAIL because the verifier modules do not exist.

- [ ] **Step 3: Implement restricted numeric evaluation**

Parse with `ast.parse(..., mode="eval")` and allow only numeric constants, the configured variable, approved arithmetic operators, and a small whitelist of math functions. Sample away from poles and domain exclusions. Return structured evidence and inconclusive when no safe sample remains.

- [ ] **Step 4: Implement finite-difference checks**

Compare a proposed derivative against local central slopes. For an antiderivative, numerically differentiate the proposed antiderivative and compare with the integrand. Label the result numerical consistency evidence, never symbolic proof. Add reverse substitution and denominator/domain checks where applicable.

- [ ] **Step 5: Implement optional symbolic adapter**

Expose a protocol that detects an explicitly configured CAS only at call time. Do not import it in the core verifier. When absent, return `unavailable` with an actionable message; symbolic differentiation and exact simplification remain isolated from stdlib behavior.

- [ ] **Step 6: Run tests and commit**

Run:

~~~text
python -m unittest tests.test_verifier -v
~~~

Expected: PASS.

~~~text
git add scripts/math_study_lib/verifier.py scripts/math_study_lib/symbolic_backend.py tests/test_verifier.py
git commit -m "feat: add numerical verification boundary"
~~~

### Task 7: Wire the unified CLI and restart-safe session lifecycle

**Files:**
- Create: `scripts/math_study.py`
- Create: `tests/test_cli.py`
- Modify: `scripts/math_study_lib/storage.py`
- Modify: `scripts/math_study_lib/reducer.py`
- Modify: `scripts/math_study_lib/scheduler.py`

**Interfaces:**
- Consumes: CLI argv and workspace-relative JSON inputs.
- Produces: `main(argv: list[str] | None = None) -> int` with subcommands `init`, `load-syllabus`, `start`, `status`, `next --minutes N`, `record-observation`, `review-due`, `mistakes`, `roadmap`, `exam`, `verify`, `rebuild`, `validate`, and `end-session`.

- [ ] **Step 1: Write failing CLI tests**

Test fresh `init` creates required JSON-only directories/files, `load-syllabus` rejects invalid source data, `record-observation` enriches and persists an event, `status` returns compact state, `next --minutes 25` fits its budget, `rebuild` reproduces derived state, and a new process resumes the pending action without transcript input.

~~~python
def test_new_process_status_reads_persisted_state(self):
    self.run_cli("init")
    self.run_cli("start")
    second_process = self.run_cli("status")
    self.assertIn("pending_action", second_process.stdout)
~~~

- [ ] **Step 2: Run tests to verify failure**

Run:

~~~text
python -m unittest tests.test_cli -v
~~~

Expected: FAIL because the unified entry point is absent.

- [ ] **Step 3: Implement CLI dispatch and JSON output**

Use `argparse` and explicit exit codes. Keep stdout compact and machine-readable where the command returns state; send diagnostics/conflicts to stderr. All state-changing commands pass through storage, validation, reducer, scheduler, and revision commit services.

- [ ] **Step 4: Implement lifecycle commands**

Implement init, syllabus loading with provenance/conflict flags, start/resume, status, next, review-due, mistakes, roadmap, exam, rebuild, validate, and end-session. Persist a concrete `pending_action` after each learning operation. `record-observation` accepts only a proposal and obtains engine metadata from current session/task policy.

- [ ] **Step 5: Implement exam-mode guardrails**

Persist exam-mode state, mixed task selection, optional timer metadata, neutral wording, no unsolicited hints, minimal feedback until submission/stop, and post-mortem observations classified by method, correctness, notation, conditions, time, and error type.

- [ ] **Step 6: Run CLI tests and commit**

Run:

~~~text
python -m unittest tests.test_cli -v
~~~

Expected: PASS.

~~~text
git add scripts/math_study.py scripts/math_study_lib tests/test_cli.py
git commit -m "feat: add unified math study CLI"
~~~

### Task 8: Package the tutoring skill and operational references

**Files:**
- Create: `SKILL.md`
- Create: `references/pedagogy.md`
- Create: `references/exam-optimizer.md`
- Create: `references/math-verification.md`
- Create: `references/source-of-truth.md`
- Modify: `tests/test_skill_contract.py`

**Interfaces:**
- Consumes: passing deterministic engine contract and pressure scenarios.
- Produces: a concise, valid Codex skill entrypoint that instructs the LLM to call the single CLI, emit structured observations, teach with bounded assistance, and resume from compact state.

- [ ] **Step 1: Write the post-GREEN contract tests**

Replace the intentional RED assertion with tests for valid frontmatter name/description, concise entrypoint size, required commands, explicit LLM/engine boundary, no premature full solutions, hint ladder, exam mode, source precedence, resume behavior, and references links.

~~~python
def test_skill_mentions_engine_owned_evidence_boundary(self):
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    self.assertIn("LLM produces structured observation", text)
    self.assertIn("deterministic state engine", text)
    self.assertIn("observations.jsonl", text)
~~~

- [ ] **Step 2: Run the post-GREEN test to verify failure**

Run:

~~~text
python -m unittest tests.test_skill_contract -v
~~~

Expected: FAIL because `SKILL.md` and references are absent.

- [ ] **Step 3: Write concise SKILL.md**

Use valid frontmatter:

~~~text
---
name: math-study
description: Interactive exam-first mathematical analysis study with persistent evidence, adaptive practice, and restart-safe local state.
---
~~~

The body must prescribe: read compact state first; honor teacher sources; choose a time-fitting activity; ask the learner to work; use H0–H5 without storing duplicate independence; debug the first invalid step; emit one observation proposal after each assessable attempt; persist through the CLI; and show a compact resume summary. Link detailed pedagogy, exam, verification, and source rules instead of embedding a monolith.

- [ ] **Step 4: Write the detailed references and agent metadata**

Document worked/faded/guided/independent/transfer/exam/delayed progression, diagnostic versus self-confidence, mixed recall, exam triage, programmer analogies without replacing rigor, game states without XP theater, read-aloud formula practice, and post-mortem behavior. Keep the package machine-readable runtime configuration JSON-only; no agent metadata file is required for the MVP.

- [ ] **Step 5: Run skill validation and contract tests**

Run:

~~~text
python -m unittest tests.test_skill_contract -v
python C:/Users/lfyzer/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
~~~

Expected: PASS for both. If the validator path differs in the execution environment, use the bundled `skill-creator` validator path reported by the active skill catalog.

- [ ] **Step 6: Commit the skill contract**

~~~text
git add SKILL.md references tests/test_skill_contract.py
git commit -m "feat: add math study agent skill"
~~~

### Task 9: Add templates, examples, README, and source-backed fixture

**Files:**
- Create: `README.md`
- Create: `config/config.template.json`
- Create: `syllabus/example-syllabus.json`
- Create: `state/templates/course.json`
- Create: `state/templates/learner.json`
- Create: `state/templates/session.json`
- Create: `state/templates/current.json`
- Create: `examples/observation-proposal.json`
- Create: `examples/session-summary.json`
- Create: `examples/mock-exam.json`
- Create: `tests/test_fixtures.py`

**Interfaces:**
- Consumes: CLI commands and schema documents.
- Produces: a zero-friction package onboarding path and inert fixtures that exercise initialization, syllabus provenance, state templates, observation proposals, session summaries, and mock exams.

- [ ] **Step 1: Write failing fixture and README checks**

Test that every example parses as JSON, example syllabus has dependency edges and source refs, templates contain no runtime observations, config contains only JSON policy, and README includes install/start/syllabus/exam/status/review/state/recovery instructions.

- [ ] **Step 2: Run checks to verify failure**

Run:

~~~text
python -m unittest tests.test_fixtures -v
~~~

Expected: FAIL because fixtures and README are absent.

- [ ] **Step 3: Add JSON-only configuration and templates**

Include exam date/timezone, available minutes by day, source precedence, exam-cram interval cap, evidence weights, verifier tolerances, and time budgets. Keep the templates free of user-specific history.

- [ ] **Step 4: Add the example syllabus and examples**

Use a compact chain from functions to limits, continuity, derivative definition, derivative rules, chain rule, and function investigation. Include official-style importance/frequency/points and provenance fields. Make the observation example omit engine-owned fields and the session example show a pending action.

- [ ] **Step 5: Write README onboarding**

Explain installation as copying/enabling the package, running `python scripts/math_study.py init`, loading a teacher syllabus, setting exam metadata, writing “Продолжаем матан.”, using status/review/roadmap/exam, and locating state relative to the active workspace. Explain that derived state is rebuildable from course/syllabus plus `observations.jsonl` and that revision recovery does not claim whole-directory atomicity.

- [ ] **Step 6: Run checks and commit**

Run:

~~~text
python -m unittest tests.test_fixtures -v
~~~

Expected: PASS.

~~~text
git add README.md config syllabus state/templates examples tests/test_fixtures.py
git commit -m "docs: add math study onboarding and fixtures"
~~~

### Task 10: Exercise synthetic learners, restart, and pressure behavior

**Files:**
- Create: `tests/test_synthetic_scenarios.py`
- Modify: `tests/scenarios/pressure-cases.json`
- Create: `tests/scenarios/run_scenarios.py`

**Interfaces:**
- Consumes: unified CLI, fixture syllabus, deterministic engine, and pressure manifest.
- Produces: repeatable acceptance evidence for scenarios A–F plus crash retry and exam post-mortem.

- [ ] **Step 1: Write failing scenario tests**

Use temporary workspaces and scripted proposals to assert:

~~~python
def test_restart_rebuilds_learning_state_but_preserves_pending_cursor(self):
    self.run_scenario("beginner_limits")
    self.simulate_new_process()
    status = self.cli("status").json
    self.assertIn("pending_action", status)
    self.assertEqual(self.cli("rebuild").json["concepts"],
                     self.cli("status").json["concepts"])
~~~

Add cases for chain-rule recurrence, 24-hour topic triage, full-solution non-promotion, three repeated conceptual errors, duplicate/conflicting retry, and exam-mode post-mortem.

- [ ] **Step 2: Run scenario tests to verify failure**

Run:

~~~text
python -m unittest tests.test_synthetic_scenarios -v
~~~

Expected: FAIL until the complete CLI/state contract is exercised.

- [ ] **Step 3: Implement scenario runner**

Load each JSON case, initialize an isolated workspace, submit only structured proposals, simulate a corrupt pointer and partial final line, restart in a fresh Python process, and compare rebuild output with the latest valid derived revision. Fail on any unexpected full solution, mastery promotion, missing recurring error, stale priority context, or lost pending action.

- [ ] **Step 4: Run all deterministic and scenario tests**

Run:

~~~text
python -m unittest discover -s tests -v
~~~

Expected: PASS, with no network or third-party imports.

- [ ] **Step 5: Run pressure checks with a fresh tutor context**

Run the pressure prompts once with no skill and once with the completed `SKILL.md` loaded. Confirm that urgency/frustration does not bypass hint limits, that “понятно” does not promote mastery, and that “у меня 25 минут” yields a bounded plan. Record outcomes in an untracked local report or a committed concise checklist under `tests/scenarios`.

- [ ] **Step 6: Commit scenario coverage**

~~~text
git add tests
git commit -m "test: cover restart and synthetic learners"
~~~

### Task 11: Final verification and review gate

**Files:**
- Modify: any implementation file only when a focused verification finds a defect.
- Test: all existing tests and package validation.

**Interfaces:**
- Consumes: all package files and committed scenario evidence.
- Produces: verified review-ready branch; no implementation beyond the approved scope.

- [ ] **Step 1: Run repository hygiene checks**

Run:

~~~text
git diff --check
rg -n "T[O]DO|T[B]D|FI[X]ME|p[r]iority_score|pers[i]stent_misconceptions" SKILL.md README.md references schemas scripts state config syllabus examples
~~~

Expected: no whitespace errors, no placeholder markers, and no forbidden legacy fields in the implementation contract.

- [ ] **Step 2: Run stdlib/import checks**

Run:

~~~text
python -m unittest discover -s tests -v
python -c "import sys; sys.path.insert(0, 'scripts'); import math_study_lib.schema_validation, math_study_lib.storage, math_study_lib.reducer, math_study_lib.scheduler, math_study_lib.verifier, math_study_lib.symbolic_backend"
~~~

Expected: all tests pass and imports succeed without external packages.

- [ ] **Step 3: Run skill validator**

Run:

~~~text
python C:/Users/lfyzer/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
~~~

Expected: PASS.

- [ ] **Step 4: Review the implementation against every spec section**

Check goal, reuse decisions, canonical ownership, proposal/event boundary, idempotency, reducer, recovery, pedagogy, exam priority, review/interleaving, numerical/CAS boundary, unified CLI, testing, and acceptance. Verify that all derived learning values come from the reducer and that session/profile are not falsely described as log-rebuildable.

- [ ] **Step 5: Commit only verified fixes**

~~~text
git status --short
git add the exact verified file paths reported by git status --short
git commit -m "fix: close math study verification gaps"
~~~

If no defect is found, create no empty commit. Stop at the planned review gate and report the exact test commands and commit ids.
