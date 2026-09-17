# Skill audit notes

Date: 2026-09-17

Scope: every repository `SKILL.md` and directly related local material. Method: local inspection using Superpowers `using-superpowers`, `writing-skills`, and required `test-driven-development`. No network or branch creation.

## Inventory and verification

- Exactly one skill: `skill/exam-prep/SKILL.md`; no repository `AGENTS.md`.
- `SKILL.md`: 48 lines, 699 whitespace-delimited words.
- `python -m unittest discover -s tests -t .`: **337 tests passed**.
- Branch before the audit: `main`; worktree was clean.
- Passing deterministic tests verify the Python engine, not the agent contract or fresh-context behavior.

## Ranked findings

### 1. High — Core JSON-writing workflow is not executable from the instructions

- `SKILL.md:37` asks for “task … explanation”, but neither is a schema field.
- `schemas/observation-proposal-v2.schema.json:5` instead requires `schema_version`, `observation_id`, `target_id`, `task_id`, `capability_id`, `task_type`, and other fields omitted from the instruction.
- `SKILL.md:41` claims `references/commands.md` contains package formats, but `commands.md:25-28` does not link the observation schema/example.
- The same gap affects curriculum creation: `SKILL.md:16` asks for `proposal.json`, while `schemas/curriculum-proposal.schema.json:6` requires six top-level fields not documented or linked by `commands.md:73-80`.
- Search found no `examples/` or `schemas/` link in `SKILL.md` or its command reference.

Impact: the central LLM-proposal-to-engine loop can fail before persistence. Link the canonical schema and one valid example for every agent-authored payload; use exact field names.

### 2. High — Resume flow contains an unreachable/incorrect branch

- `SKILL.md:25`: “If no course exists … `load-syllabus` and `start`.”
- `SKILL.md:20` and `scripts/exam_prep.py:471-476` forbid `load-syllabus` before initialization.
- Fresh-workspace reproduction: before `init`, `load-syllabus` returned `workspace_not_initialized`; after `init`, both `course.json` and `syllabus.json` existed.

Impact: the branch cannot succeed when its condition is true. Branch first on initialization, then on empty/missing syllabus or targets.

### 3. High — The documented `status` response shape is false

- `SKILL.md:24,29` says status contains `syllabus` and `mistakes`, then forbids confirming via files or `mistakes`/`roadmap`.
- Actual clean `status --compact` keys: `course`, `last_session_summary`, `resume_point`, `review_queue`, `session`, `targets`.
- `scripts/exam_prep.py:712-733` confirms there is no `syllabus` or top-level `mistakes`; recurring mistakes may be nested under targets.

Impact: the agent is told to rely on nonexistent fields and avoid commands that could provide missing detail. Document the exact JSON shape.

### 4. High — The skill never gives an executable CLI invocation

- Instructions use bare `status`, `init`, and other subcommands.
- Literal `status` fails because there is no such executable.
- The entrypoint is `python scripts/exam_prep.py [--workspace ...] <subcommand>`; only the unlinked package `README.md:91-103` explains it.

Impact: a newly activated agent has no self-contained way to invoke the engine. Add one canonical invocation template and define paths relative to the skill root.

### 5. High — The published behavioral-evaluation command is broken

- `tests/scenarios/baseline-prompts.md:24` requests IDs `premature_solution_pressure`, `short_time_budget`, and `resume_pending_action`.
- None exists in `pressure-cases.json`; current equivalents are `one_mistake_show_answer`, `fifteen_minute_budget`, and `restart`.
- Reproduction exits 2 with `unknown case: premature_solution_pressure`.

Impact: fresh-context verification cannot run as documented. Generate documentation from the manifest or test the exact documented command.

### 6. High — Release gating covers only 4 of 17 pressure cases

- The manifest has 17 cases; only 4 are release-gated.
- `evaluate_transcripts.py:30-34` hard-requires exactly four, and `test_pressure_runner.py:167-186` enforces exclusion of new cases from the default gate.
- Excluded behavior includes exam mode, retry/idempotency, solution exposure, frustration, worked examples, cram mode, reconstruction, transfer, and ticket-list pedagogy.

Impact: a passing release gate leaves most declared high-risk behaviors untested. Make the gate risk-based and extensible.

### 7. High — Full-solution policy conflicts with worked-example/cram expectations

- `SKILL.md:35` forbids a full solution merely because the learner asks once.
- H5 exists, but neither `SKILL.md` nor `pedagogy.md` defines an observable transition into explicit exposure mode.
- `pressure-cases.json:77-95` expects explicit worked-example and five-minute cram requests to allow exposure; neither case is release-gated.

Impact: compliant agents can choose opposite behaviors for the same request. Define explicit exposure-mode entry, recording, and independent follow-up rules.

### 8. High — Behavioral quality claims are not reproducible

- `skill/exam-prep/README.md:34-55` claims 100% (28/28) with the skill versus 76% (21/28) without it.
- Lines 54-55 say raw transcripts and grading are outside the repository; lines 169-170 say scenarios were sampled once.
- Current `evaluate_transcripts.py:105-111` requires five distinct runs, but no transcript/score artifacts are present.
- The evaluator accepts supplied response strings and booleans and intentionally does no semantic verification.

Impact: reviewers cannot tie the headline result to the current skill or current gate. Version anonymized evidence plus model/host/revision metadata, or remove quantitative claims.

### 9. Medium — NotebookLM has no explicit consent/data-boundary gate

- `SKILL.md:14` says the host discovers and invokes available NotebookLM capability.
- `references/notebooklm-mcp.md:28-63` includes install/login/setup, names `source_add`, and says authentication uses browser cookies plus undocumented endpoints with the authority of the user's account.
- No rule requires explicit opt-in before authentication, upload/external write, or sending course data; no read-only default is stated.

Impact: hosts without stronger global policy may externalize private material or initiate account-scoped setup. Require explicit consent for install/login and every upload/write.

### 10. Medium — Activation is unverified and metadata misses the prescribed trigger form

- `skill/exam-prep/README.md:159-163` admits trigger-rate evaluation never produced a valid result.
- `SKILL.md:3` starts with `Use for`; Superpowers `writing-skills` prescribes a concrete third-person `Use when...` trigger.

Impact: all guarantees are irrelevant when discovery fails, and that probability is unknown. Add positive/negative fresh-context trigger tests and tune from observed misses.

### 11. Medium — `verbatim_definitions` is public but inert

- `schemas/course.schema.json:23-25` accepts `exam.verbatim_definitions`.
- `skill/exam-prep/README.md:71-77` says the engine and tutoring references do not read it.
- Search found no runtime use outside schema validation tests.

Impact: a grading-relevant setting appears supported but has no effect. Implement it or reject/remove it until supported.

### 12. Medium — Verification is labeled more broadly than it works

- `SKILL.md:8,45` advertises any subject and “Numeric/symbolic answer checks”.
- `verifier_registry.py:19-54` supports only derivative and antiderivative; other kinds return `unavailable`.
- The limitation appears only deeper in pedagogy/README.

Impact: agents may expect algebra, limits, series, or general numeric verification and overstate unavailable results. Narrow the label or add capabilities.

### 13. Low — The skill has no margin under its size gate

- The skill is 699 words; `tests/test_skill_contract.py:31-46` permits at most 700.
- Superpowers `writing-skills` recommends under 500 words for ordinary skills and moving heavy detail into references.

Impact: a one-word clarification can break the contract test, encouraging compressed edits. Move detail into discoverable references after fixing their contracts.

## Checked and not reported as defects

- Every Markdown reference named by `SKILL.md` exists.
- Every argparse subcommand is at least named in the skill or a linked reference.
- Frontmatter name matches the directory and uses valid characters.
- `init` is idempotent; pre-init `status` is non-mutating.
- All 337 deterministic tests pass.
- Local `__pycache__`/`.pyc` files are ignored and not tracked.

## Audit integrity

- No network call was made.
- No branch was created or changed.
- No skill, reference, schema, source, or test file was modified.
- The only intended repository change is this audit note.
