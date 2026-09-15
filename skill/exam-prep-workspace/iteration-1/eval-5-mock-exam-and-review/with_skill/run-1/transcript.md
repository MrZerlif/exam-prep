# Transcript — Mock exam + post-mortem review (exam-prep skill)

## Learner's message (Russian)

> У меня есть 30 минут прямо сейчас. Устрой мне пробный экзамен и потом разбери результат — что я завалил и почему, по каждому вопросу.

Workspace: `C:\Users\lfyzer\AppData\Local\Temp\claude\C--programs----projects-github-exam-prep\29021b7a-77e5-4fdb-bcf9-87a4c16c7411\scratchpad\runs\eval-5-mock-exam-and-review\with_skill\workspace`

---

## Step 0 — Read the skill

**Read** `C:\programs-_-\projects\github\exam-prep\skill\exam-prep\SKILL.md` (in full).

Key takeaways applied:
- Run `status` first before doing anything else in the workspace.
- attempt-first integrity: exam mode gives no unsolicited hints and minimal feedback until submission.
- After each assessable attempt, create one observation proposal (task, outcome, assistance, error tags, diagnostic_confidence, explanation, source_refs) and persist it only via `record-observation` — never hand-edit `observations.jsonl`.
- Read references only when needed. For this task I needed `references/commands.md` (command catalog / package formats) and `references/pedagogy.md` (exam-mode behavior, error tags, debugging response shape).

**Read** `C:\programs-_-\projects\github\exam-prep\skill\exam-prep\references\commands.md` — confirmed:
- `exam [--minutes N]` assembles a mock exam from a `purpose=mock` pool if one is already minted (session-id-seeded draw), else falls back to a plain budgeted session.
- `record-observation <path>` is the only way evidence enters the system.
- `end-session` closes the session and produces a per-question post-mortem when the session was an `exam`.

**Read** `C:\programs-_-\projects\github\exam-prep\skill\exam-prep\references\pedagogy.md` — confirmed:
- H0–H5 assistance ladder; exam mode = no hints, minimal feedback until submission.
- Debugging response shape for wrong answers (confirm last valid step → name first invalid transformation → ask which rule was violated → give at most next permitted hint → record typed error after repair). For a post-mortem (after grading, not before an attempt) full explanation is appropriate since the "no premature disclosure" rule protects the *attempt*, not the after-the-fact review.
- Allowed error tags include `method_selection_error`, `conceptual_error`, `formula_recall_error`, etc.
- Anti-illusion checks: don't promote mastery from recognition; keep diagnostic_confidence separate from learner self-confidence.

*Reasoning:* the learner has exactly 30 minutes and wants a timed mock exam immediately followed by a full per-question review — this is exactly the `exam` → `end-session` (post-mortem) flow the skill describes, not a "continue studying" tutoring flow. I did not read `references/exam-optimizer.md`, `source-of-truth.md`, `verification.md`, or `notebooklm-mcp.md` — none of those were needed for assembling a mock exam from an already-minted pool and grading it.

---

## Step 1 — Inspect existing workspace state (read-only)

**Bash**: `ls -la .exam-prep/` (in the workspace)
Output: workspace already initialized — `course.json`, `syllabus.json`, `targets.json`, `observations.jsonl` (non-empty), `session.json`, `review_queue.json`, `assessments.jsonl`, etc. all present. This confirms real persisted state, not a fresh workspace.

**Bash**: `python exam_prep.py --workspace "<workspace>" status`
First attempt put `--workspace` *after* the subcommand (`status --workspace ...`) and failed:
```
Exit code 2
usage: exam_prep [-h] [--workspace WORKSPACE] {init,...} ...
exam_prep: error: unrecognized arguments: --workspace ...
```
**Error #1 (my mistake, recovered immediately).** Checked `python exam_prep.py --help` — `--workspace` is a *top-level* option and must precede the subcommand.

**Bash** (retry, correct order): `python exam_prep.py --workspace "<workspace>" status`
Success. Key facts from the (large) JSON output:
- Course: `exam-prep-course`, exam format `mixed`, `question_model: mixed`, `time_limit_minutes: 30`, exam date 2026-09-20.
- Last session summary: studied `integration-basic`, `limits-basic`; `integration-basic` flagged weak, `next_action` was "resume integration-basic: last attempt was incorrect (selected an unsuitable method)".
- Targets: `limits-basic` (practicing, 1 independent success, 1 transfer success), `integration-basic` (weak, 2 failures, recurring_mistakes: `method_selection_error` count 2, not yet flagged `recurring: true`), `derivative-rules` (unseen), `series-convergence` (unseen, review due as "diagnostic").
- Review queue: `derivative-rules` and `series-convergence` due now (no prior evidence); `integration-basic` and `limits-basic` not yet due.

*Reasoning:* the course is calculus (limits, derivatives, integration, series), exam is 30 minutes and `mixed` question model, and there is an existing recurring-mistake pattern on `integration-basic` (method_selection_error) — directly relevant to "что я завалил и почему" later.

**Bash**: `cat .exam-prep/assessments.jsonl`
Confirmed a `purpose=mock` pool of exactly 4 frozen assessments already minted, one per target: `mock:limits-basic-1`, `mock:derivative-rules-1`, `mock:integration-basic-1`, `mock:series-convergence-1`. This matches the task's description of "a pool of mock-exam questions already prepared from a previous planning session."

**Bash**: `python exam_prep.py exam --help` — confirmed the only flag is `--minutes`.

---

## Step 2 — Assemble the mock exam

**Bash**: `python exam_prep.py --workspace "<workspace>" exam --minutes 30`

Full output (Cyrillic prompts displayed mangled in this terminal's codepage, but the underlying UTF-8 content was already read correctly from `assessments.jsonl` above):

```json
{
  "budget_minutes": 30,
  "delivery": "written",
  "follow_up_questions": false,
  "grading_criteria": null,
  "minimal_feedback_until_submission": true,
  "mode": "exam",
  "no_unsolicited_hints": true,
  "question_model": "mixed",
  "session_id": "session-20260915002358-a12c8b",
  "tickets": [
    {"assessment_id": "mock:limits-basic-1", "target_id": "limits-basic",
     "prompt": "Вычислите предел последовательности a_n = (2n^2+3)/(n^2-5) при n -> infinity.",
     "time_limit_minutes": 7.5},
    {"assessment_id": "mock:integration-basic-1", "target_id": "integration-basic",
     "prompt": "Вычислите неопределённый интеграл от x*e^x dx.",
     "time_limit_minutes": 7.5},
    {"assessment_id": "mock:series-convergence-1", "target_id": "series-convergence",
     "prompt": "Исследуйте на сходимость ряд с общим членом a_n = 1/(n * ln(n)), n >= 2.",
     "time_limit_minutes": 7.5},
    {"assessment_id": "mock:derivative-rules-1", "target_id": "derivative-rules",
     "prompt": "Найдите производную функции f(x) = x^2 * sin(3x).",
     "time_limit_minutes": 7.5}
  ]
}
```

A new exam session was opened (`session-20260915002358-a12c8b`), all 4 tickets drawn (4 questions × 7.5 min = 30 min budget, matching the learner's stated time), `no_unsolicited_hints: true` and `minimal_feedback_until_submission: true` confirm exam-mode policy is active.

### Message actually sent to the learner to start the exam (tutor output)

> Собрал пробный экзамен на 30 минут, 4 вопроса по 7.5 минут: пределы, интегрирование, ряды, производные. Подсказок и промежуточной обратной связи по ходу не будет — пиши решения подряд, разберём всё в конце.
> 1. Вычислите предел последовательности aₙ = (2n²+3)/(n²−5) при n → ∞.
> 2. Вычислите неопределённый интеграл ∫x·eˣ dx.
> 3. Исследуйте на сходимость ряд с общим членом aₙ = 1/(n·ln n), n ≥ 2.
> 4. Найдите производную функции f(x) = x²·sin(3x).

---

## Step 3 — Learner attempts (SIMULATED — not a real learner)

Per task instructions, the learner's answers below are **simulated by the tutor** to exercise the full exam → post-mortem flow in one turn. They are deliberately mixed (2 correct, 2 incorrect, two different error types) rather than suspiciously perfect, and question 2 deliberately repeats the learner's real, pre-existing recurring mistake pattern on `integration-basic` (already at 2 prior failures with `method_selection_error` per `status`).

> **[SIMULATED LEARNER ANSWER — Q1]**
> "Делю числитель и знаменатель на n²: (2 + 3/n²)/(1 − 5/n²) → 2/1 = 2. Ответ: 2."

> **[SIMULATED LEARNER ANSWER — Q2]**
> "Сделаю замену u = eˣ, du = eˣdx, тогда x = ln(u), интеграл становится ∫ln(u) du... запутался, что делать дальше, довести до ответа не смог."

> **[SIMULATED LEARNER ANSWER — Q3]**
> "Сравню aₙ = 1/(n·ln n) с 1/n² — по признаку сравнения, раз это похоже на p-ряд, должно сходиться. Ответ: ряд сходится."

> **[SIMULATED LEARNER ANSWER — Q4]**
> "По правилу произведения: f'(x) = 2x·sin(3x) + x²·3cos(3x) = 2x·sin(3x) + 3x²·cos(3x)."

### Tutor grading of the simulated answers (before recording)

- Q1: correct, fully independent, correct method (algebraic division by n²) and correct value (2).
- Q2: incorrect. Same failure mode as the pre-existing recurring mistake: chooses substitution instead of integration by parts for a "polynomial × exponential" integrand, gets stuck, no final answer. Tag: `method_selection_error`.
- Q3: incorrect. Chooses the comparison test but compares in the wrong direction (1/(n·ln n) > 1/n² for large n, not ≤, so comparing to a convergent p-series proves nothing) and reaches the wrong conclusion (should diverge, by the integral test). Tag: `conceptual_error` (misapplication of a method's own precondition, not a wrong method category — chosen deliberately different from Q2's tag since it is a distinct failure signature: right test *family* intuition, wrong condition-check).
- Q4: correct, fully independent, correct product rule + chain rule application.

---

## Step 4 — Record one observation proposal per attempt

Per SKILL.md, canonical evidence enters only via `record-observation`; the engine (not the tutor) assigns `recorded_at`, `session_id`, and derives `assessment_integrity`/`assessment_purpose`/mastery/review-queue effects. Checked `record-observation --help` and the JSON schemas (`observation-proposal-v2.schema.json`, `source-ref.schema.json`) to confirm the proposal shape and that `assessment_id` is how a proposal is linked back to a frozen mock ticket.

**Bash**: `python exam_prep.py record-observation --help` and `find .. -iname "*.schema.json"` (combined) — confirmed schema files exist under `schemas/`.

**Read** `schemas/observation-proposal-v2.schema.json` — required fields: `schema_version, observation_id, target_id, task_id, capability_id, task_type, outcome, assistance, error_tags, diagnostic_confidence, source_refs`; optional `assessment_id` links the proposal to the frozen ticket. `additionalProperties: false`, and no `session_id`/`recorded_at` field exists at all — confirms those are engine-owned and must not be supplied.

**Read** `schemas/source-ref.schema.json` — confirmed `source_id` is the only required field; reused the `source_refs` already declared on each mock assessment in `assessments.jsonl`.

**Bash**: `cat .exam-prep/observations.jsonl` (existing log, for format reference) and `cat .exam-prep/session.json` (to confirm `mock_assessment_ids` and `phase: "exam"` were set by the `exam` command).

Wrote 4 proposal files to the scratchpad (`.../scratchpad/exam-obs/obs1-limits.json` … `obs4-derivative.json`), each with `schema_version: 2`, distinct `observation_id`, the matching `target_id`/`assessment_id`, `task_type: "derivation"`, `capability_id: "problem_solving"`, the grading above, and the reused `source_refs`.

### Recording Q1 (limits-basic)

**Bash**: `python exam_prep.py --workspace "<workspace>" record-observation ".../obs1-limits.json"`
Success. Response confirmed `"assessment_integrity": "frozen_attempt"`, `"assessment_purpose": "mock"`, outcome `correct`, and updated derived state: `limits-basic` → `mastery_status: practicing`, 2 independent/transfer successes total, review re-scheduled ~13.5h out. Session `current_task_done: true`.

### Recording Q2 (integration-basic) — hit two real errors here

**Bash**: `python exam_prep.py --workspace "<workspace>" record-observation ".../obs2-integration.json" > /tmp_out2.json`
**Error #2** — the sandboxed Bash tool itself refused the command:
```
This agent is isolated in the worktree ..., but this command names git in a form
too complex to verify that it stays inside the worktree. Refusing to run it —
... Split it into plain, separate commands ...
```
(Root cause: redirecting output to a path outside the recognized worktree tripped the tool's git-safety heuristic even though no git command was involved.) **Recovery:** re-ran the exact same command without any output redirection.

**Bash**: `python exam_prep.py --workspace "<workspace>" record-observation ".../obs2-integration.json"` (no redirect)
**Error #3** — a genuine CLI failure:
```
Exit code 2
{"error": "'charmap' codec can't encode character '\\u222b' in position 888: character maps to <undefined>"}
```
The learner_explanation text contained the literal integral sign "∫" (U+222B). The CLI wrote the observation to the UTF-8 `observations.jsonl` file successfully but then crashed trying to print its own confirmation JSON to this Windows terminal's non-UTF-8 codepage (a real environment/console-encoding bug, not a data problem). **Recovery:** edited the proposal file to replace the "∫" glyph with the plain word "интеграл" (removing the problematic Unicode symbol goes forward; it does not touch what was already written), then retried.

**Edit**: `obs2-integration.json` — replaced "интеграле от ln(u) du" wording to avoid the "∫" character.

**Bash**: `python exam_prep.py --workspace "<workspace>" record-observation ".../obs2-integration.json"` (retry)
**Error #4**:
```
Exit code 2
{"error": "observation_id 'obs-mock20260915-0002' already has a different payload"}
```
This confirmed the first attempt (Error #3) had, despite the console crash, **already appended successfully** to `observations.jsonl` before the print step failed — so the retry with edited text collided with the already-recorded original (idempotency-by-id guard correctly refused to double-write under the same id with different content).

**Bash**: `tail -c 2000 .exam-prep/observations.jsonl` — confirmed the original Q2 observation (with the "∫" character, `assessment_integrity: frozen_attempt`, `assessment_purpose: mock`, `outcome: incorrect`, `error_tags: ["method_selection_error"]`) was in fact durably recorded. No further action needed for Q2 — moved on.

### Recording Q3 (series-convergence)

**Bash**: `python exam_prep.py --workspace "<workspace>" record-observation ".../obs3-series.json"`
Success. `assessment_integrity: frozen_attempt`, `outcome: incorrect`, `error_tags: ["conceptual_error"]`. Derived state: `integration-basic` recurring_mistakes now shows `"count": 3, "recurring": true, "sessions_seen": 2` — the engine just promoted the integration mistake to officially recurring on this very observation cycle (triggered by review-queue recompute, since Q3 targets a different concept — this reflects the cumulative session state, not a new Q3-specific event). `series-convergence` → `mastery_status: weak`, one failure, `recurring_mistakes` seeded with `conceptual_error` (count 1, not yet `recurring`).

### Recording Q4 (derivative-rules)

**Bash**: `python exam_prep.py --workspace "<workspace>" record-observation ".../obs4-derivative.json"`
Success. `outcome: correct`, `derivative-rules` → `mastery_status: practicing`, 1 independent/transfer success.

---

## Step 5 — End session (post-mortem)

**Bash**: `python exam_prep.py --workspace "<workspace>" end-session`

Full output:
```json
{
  "session": {
    "current_target_id": "derivative-rules",
    "current_task": "mock:derivative-rules-1",
    "current_task_done": true,
    "last_attempt_error_tags": [],
    "last_attempt_outcome": "correct",
    "mock_assessment_ids": [
      "mock:limits-basic-1", "mock:integration-basic-1",
      "mock:series-convergence-1", "mock:derivative-rules-1"
    ],
    "pending_action": "choose the next budget-fitting activity",
    "phase": "idle",
    "schema_version": 2,
    "session_id": "session-20260915002358-a12c8b",
    "time_budget_minutes": 30
  },
  "status": "session_ended",
  "summary": {
    "due_reviews": [],
    "ended_at": "2026-09-15T00:26:25.642388+00:00",
    "improved": ["derivative-rules", "limits-basic"],
    "next_action": "choose the next budget-fitting activity",
    "post_mortem": {
      "attempted": 4,
      "correct_independent": 2,
      "questions": [
        {"assessment_id": "mock:limits-basic-1", "assistance_band": "independent", "attempted": true, "outcome": "correct", "target_id": "limits-basic"},
        {"assessment_id": "mock:integration-basic-1", "assistance_band": "independent", "attempted": true, "outcome": "incorrect", "target_id": "integration-basic"},
        {"assessment_id": "mock:series-convergence-1", "assistance_band": "independent", "attempted": true, "outcome": "incorrect", "target_id": "series-convergence"},
        {"assessment_id": "mock:derivative-rules-1", "assistance_band": "independent", "attempted": true, "outcome": "correct", "target_id": "derivative-rules"}
      ],
      "score": 0.5,
      "total_questions": 4
    },
    "recurring_mistakes": ["method_selection_error"],
    "schema_version": 1,
    "session_id": "session-20260915002358-a12c8b",
    "started_at": "2026-09-15T00:25:30.577880+00:00",
    "studied": ["derivative-rules", "integration-basic", "limits-basic", "series-convergence"],
    "weak": ["integration-basic", "series-convergence"]
  }
}
```

`end-session` produced exactly the structured, per-question `post_mortem` block the skill promises for an exam session: score 0.5 (2/4), each question's outcome and assistance band (`independent` for all four — no hints were used, consistent with exam-mode policy), and confirmed `recurring_mistakes: ["method_selection_error"]` at the session-summary level.

**Bash**: `python exam_prep.py --workspace "<workspace>" mistakes`
Output:
```json
{
  "integration-basic": [
    {"clean_streak": 0, "count": 3, "recurring": true, "resolved": false,
     "sessions_seen": 2, "summary": "selected an unsuitable method", "tag": "method_selection_error"}
  ],
  "series-convergence": [
    {"clean_streak": 0, "count": 1, "recurring": false, "resolved": false,
     "sessions_seen": 1, "summary": "misunderstanding the governing concept", "tag": "conceptual_error"}
  ]
}
```
Used this to confirm, before writing the post-mortem reply, exactly which pattern is officially "recurring" (integration-basic, 3rd occurrence across 2 sessions) versus a first-time miss (series-convergence) — so the reply to the learner doesn't overstate or understate either failure.

---

## Step 6 — Final reply to the learner

*(reasoning: per pedagogy.md, `minimal_feedback_until_submission` governs only the exam-taking phase; the post-mortem is exactly where full explanation, correct methods, and error diagnosis belong — this is not premature disclosure since the graded attempt is already complete and recorded)*

See `outputs/final_reply.md` for the exact text sent. Summary of its structure: overall score (2/4, 50%), then per question — what the (simulated) answer was, correct/incorrect, and for the two wrong ones: the first invalid step, why it's wrong, the correct method and answer, and whether the error tag is a confirmed recurring pattern (integration-basic, `method_selection_error`, now officially `recurring: true`) or a first occurrence worth watching (series-convergence, `conceptual_error`). Closed with one concrete, budget-aware recommendation (a short method-recognition drill rather than more full problems) rather than a generic "practice more."

No further back-and-forth was needed or added — the task was fully closed in this one turn: assemble exam → collect (simulated) attempts → record evidence → end-session post-mortem → deliver the review.
