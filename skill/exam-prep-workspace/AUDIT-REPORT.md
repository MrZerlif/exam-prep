# exam-prep skill audit: with_skill vs. without_skill

**Scope**: audit only. Nothing under `skill/exam-prep/` was changed (verified: `git diff --stat -- skill/exam-prep/` is empty). All artifacts live under `skill/exam-prep-workspace/`, on branch `exam-prep/audit-skill-vs-baseline`.

**Baseline**: `without_skill` = plain Claude (Sonnet 5), same generic tools (Bash/Read/Write/Edit/Glob/Grep), no skill loaded, no knowledge of the CLI or its protocol. Not a prior version of the skill. This is deliberate: the question is whether exam-prep beats an unassisted tutor, not whether one draft beats another.

**Executor/grader model**: claude-sonnet-5 throughout (this session's model), 1 run per (eval, configuration) cell — not 3. That matters for how to read the ± figures below (see "On variance").

---

## Headline result

| | with_skill | without_skill | delta |
|---|---|---|---|
| **Pass rate** (28 assertions total) | **100%** (28/28) | **76%** (21/28) | +24 pts |
| **Wall time** (mean) | 278.9s | 128.3s | +150.5s (2.2x) |
| **Tokens** (mean, real API usage) | 104,565 | 74,721 | +29,844 (1.4x) |

Source: [`iteration-1/benchmark.json`](iteration-1/benchmark.json) / [`iteration-1/benchmark.md`](iteration-1/benchmark.md), built with skill-creator's `aggregate_benchmark.py` from 10 independently graded runs, with the `tokens` field corrected to real API token counts (see "A data-quality fix" below).

**But the honest finding is underneath this number, not in it**: of the 28 assertions graded, **21 (75%) passed identically in both configurations**. The skill's measured edge in this sample is concentrated in exactly **7 assertions**, and **one whole scenario (eval-3, resume-after-a-break) tied 5/5 vs 5/5** — the skill added zero measurable behavioral difference there. See "Per-case breakdown."

---

## Per-case pass rates

| Eval | with_skill | without_skill | Real delta (assertions that actually differed) |
|---|---|---|---|
| 1. Oral ticket_list, no forced problems | 6/6 (100%) | 3/6 (50%) | 3 of 6: reads local state, ticket-track brief-structure step, engages with the real ticket-3 content |
| 2. Problem_set practical track | 6/6 (100%) | 4/6 (67%) | 2 of 6: reads local state, grounds the problem in the learner's actual syllabus target |
| 3. Resume after a break | 5/5 (100%) | **5/5 (100%)** | **0 of 5 — tie** |
| 4. Materials → minted tickets | 5/5 (100%) | 4/5 (80%) | 1 of 5: tickets end up as structured, individually-drawable records (baseline produced one prose file) |
| 5. Mock exam + review | 6/6 (100%) | 5/6 (83%) | 1 of 6: durable trace left on disk (baseline explicitly wrote nothing back) |

**Total real differentiators: 7 of 28 assertions (25%).**

### Why eval-3 tied
The without_skill run, with no protocol for the `.exam-prep/` folder, opened it anyway (`session.json`, `targets.json`, `syllabus.json`, `observations.jsonl`) on its own initiative, correctly identified the specific interrupted chain-rule attempt and its exact recorded error, and asked for a fresh attempt rather than assuming mastery — matching with_skill on every single assertion. This is the single most useful finding in the audit: the skill's "resume without reconstruction" behavior is not something a capable baseline categorically lacks; it's something the skill makes **reliable**, where the baseline is inconsistent (see next point).

### Why eval-1/eval-2 didn't tie
In these two cases the without_skill run discovered the same kind of `.exam-prep/` folder but **explicitly declined to open it**, citing "no documented protocol for the format" (eval-1) or treated it as "opaque" (eval-2), and guessed instead — in eval-2 the run's own `user_notes.md` admits "I guessed at an appropriate starting difficulty... that context was not incorporated." That is what drove the lower pass rate, not an inherent inability to read the files.

**Characterization that fits all 5 cases**: the skill's real, measured value in this sample looks less like "unlocks a capability the baseline doesn't have" and more like **"reliably ensures the local state gets read and used, every time"** — plain Claude sometimes does this on its own initiative (eval-3, eval-4, eval-5) and sometimes doesn't (eval-1, eval-2), while the skill did it in all 5/5.

### Non-discriminating assertions (passed in both configs — flagged explicitly, not hidden)
Per grading.json's `non_discriminating_assertions` field on every run:
- **eval-1**: "no forced practice problem," "attempt-first before revealing," "no fabricated progress" — a baseline tutor asked to quiz someone on a stated no-problems exam is unlikely to invent a problem anyway.
- **eval-2**: "gives a problem instead of solving it," "no premature solution," "no ticket-track leakage" (tautological for a baseline that's never heard of ticket_list), "no fabricated progress."
- **eval-3**: all 5 — genuine tie.
- **eval-4**: "reads both named files" (the prompt makes this nearly unavoidable), "explicit validation step before finalizing" (both runs' "validation" is narrated reasoning, not an independently-verifiable action, per the grader).
- **eval-5**: "bounded exam size," "grounded in the learner's own simulated answers" — since the same agent authors both the simulated answers and the review in one turn, referencing them back is close to free for any model.

---

## Time and tokens

| Eval | with_skill tokens | without_skill tokens | with_skill time | without_skill time |
|---|---|---|---|---|
| 1 | 86,081 | 65,274 | 166.3s | 82.9s |
| 2 | 83,148 | 67,860 | 160.2s | 105.1s |
| 3 | 88,746 | 72,394 | 192.4s | 99.6s |
| 4 | 141,554 | 77,201 | 477.3s | 185.7s |
| 5 | 123,295 | 90,875 | 398.2s | 168.3s |
| **mean ± stddev*** | **104,565 ± 26,313** | **74,721 ± 10,110** | **278.9s ± 148.2s** | **128.3s ± 45.6s** |

\* **On variance**: this ran 1 sample per (eval, configuration) cell, not 3. The ± figures above are the spread **across the 5 different scenarios**, not run-to-run flakiness of one repeated scenario — real flakiness was not measured in this pass and would need repeated sampling per cell. Don't read "eval-4 has high variance" from this table; read "eval-4 is the outlier scenario," which is true and is called out below.

**Time overhead is the most consistent signal**: with_skill was slower in **5 of 5** evals, from 1.4x (eval-2) to 2.6x (eval-4) — never faster, never comparable.

**Token overhead is smaller and eval-4-driven**: excluding eval-4, with_skill uses ~95k vs ~74k tokens (1.29x); eval-4 alone is 141,554 vs 77,201 (1.83x) and is the largest absolute outlier in both tokens and time. Eval-4 (build a curriculum from scratch + mint tickets) is inherently the most CLI-call-heavy scenario, so some overhead there is structural, not wasteful — but not all of it (see below).

**A data-quality fix worth flagging**: `aggregate_benchmark.py`'s generated `tokens` field defaults to `output_chars` (final-reply character count) as a "proxy for tokens" per its own schema comment, and only falls back to the real captured `total_tokens` when `time_seconds` happens to read as exactly `0.0` from `grading.json`. In practice this meant 9 of the 10 rows in the first auto-generated `benchmark.json` reported reply-length-in-characters (~1,000–10,000) instead of real API token usage (~65,000–142,000) under the `tokens` label — only eval-4/with_skill accidentally got the real number. I overrode all 10 with the real `total_tokens` values captured directly from each run's task-completion notification (saved to each run's `timing.json` immediately on completion, as instructed, since that's the only opportunity to capture it) before computing the table above. The original proxy values are preserved per-run under `result.tokens_proxy_output_chars` in `benchmark.json` for transparency.

---

## Where the skill spends more than necessary (transcript-level findings)

Full detail with quotes: [`iteration-1/transcript-efficiency-findings.md`](iteration-1/transcript-efficiency-findings.md), from a dedicated pass that read all 5 with_skill transcripts in full (plus the 5 without_skill ones for comparison) and cross-referenced SKILL.md and every reference file. Highlights:

1. **A recurring, independently-rediscovered workaround — this is the "same helper script" signal, in report form, not applied to code**: 3 of 5 with_skill runs (eval-3, eval-4, eval-5) hit the same friction point — the CLI's own JSON output is valid UTF-8, but this Windows console renders Cyrillic text as mojibake — and each one independently invented the identical fix: stop trusting the terminal, re-read the underlying `.exam-prep/*.json` file directly with the `Read` tool. None of the without_skill runs ever hit this, because they never shell out through the CLI in the first place; they `Read` the JSON files directly from the start. **This escalated to a real bug in eval-5**: `record-observation`, given `learner_explanation` text containing the literal character '∫' (U+222B), wrote the observation to `observations.jsonl` successfully but then crashed printing its own confirmation to the console (`'charmap' codec can't encode character '✗'`-class error). The agent, seeing a crash, edited the text and retried under the same `observation_id` — which then failed with an idempotency conflict, revealing the original write had actually gone through. No data was lost in this instance, but it took a `tail` of the raw log to confirm that, and a slightly different recovery choice (a new `observation_id`, or giving up on the question) could have produced duplicate or silently-dropped evidence. **This is a real CLI defect** (force UTF-8 stdout at the `exam_prep.py` entrypoint, e.g. wrap `sys.stdout`/`sys.stderr` in a UTF-8 `TextIOWrapper`, or set `PYTHONIOENCODING` internally) that belongs in `scripts/`, not something every future conversation should have to rediscover and work around per-turn.
2. **eval-3 (13 tool-call steps for a one-line "continue?" message)** re-confirms information `status` already returned in several places: `session.json` re-read right after `status` returned the identical block, and a `mistakes` call that re-confirmed data `targets.json` had already shown.
3. **eval-4 spent ~6 tool calls reading raw Python source** (`capabilities.py`, `curriculum.py`, `source_provider.py`) to reverse-engineer two mechanics — which capability IDs are valid, and how the "unknown source ref" coverage-gap check is actually satisfied — that neither `commands.md` nor `source-of-truth.md` spells out. Real, task-relevant discovery, but discovery the reference docs left the model to do from scratch; the grader on eval-4 independently reached the same conclusion, estimating this documentation gap costs "~10-12 tool calls" in a similar run.
4. **`references/verification.md` and its `verify` CLI command were never invoked in any of the 5 runs**, despite eval-2 and eval-5 both having the tutor hand-grade calculus (integration by parts; a series-convergence test) with no cross-check — exactly the scenario verification.md says the verifier exists to guard against.
5. Two one-off, self-corrected CLI mistakes (a Windows backslash path mangled by the bash tool in eval-1; a misplaced `--workspace` flag in eval-5) each cost one extra round-trip; not a pattern, but zero-equivalent overhead in the without_skill runs, which never shell out.

**Not a finding, but worth closing out**: a grader flagged what looked like a fixture inconsistency (eval-1's `.exam-prep` fixture description says "no session open yet," but the with_skill transcript shows an already-open session). Checked directly against the fixture-bootstrap log and the transcript: the fixture genuinely started idle (`session_id: ""`, `phase: idle`) as documented; the with_skill run's own `start` call (a normal, required step per SKILL.md's lifecycle) is what opened it, and the transcript's phrasing described the resulting state, not a pre-existing one. Not a bug.

---

## Description-optimization measurement: **BLOCKED**

Full detail: [`description-optimization/BLOCKER.md`](description-optimization/BLOCKER.md).

Generated a 20-query trigger eval set (`description-optimization/trigger-eval-set.json`: 9 should-trigger / 11 should-not-trigger, close-miss negatives as requested — flashcards with no exam framing, topic explanations with no session, a single homework problem, an explicit "no exam, just curious" case, etc.).

Running skill-creator's `run_loop.py` hit three real, fixable bugs in that tool on native Windows (subprocess path resolution for the npm `.cmd` shim, `select.select()` on a pipe instead of a socket, and a `write_text()` default-encoding crash on a non-ASCII character) — all three fixed directly in skill-creator's own vendored scripts (not in this repo; paths and diffs are in BLOCKER.md). With those fixed, the harness ran without crashing, but **every single query, positive or negative, returned `trigger_rate: 0.0`** — traced to the standalone `claude` CLI on this machine's PATH not being authenticated at all (`claude auth status` → `"loggedIn": false`), separate from whatever credentials power this Desktop session. Every nested `claude -p` probe call fails auth silently (no crash, `is_error: true`, `"Not logged in · Please run /login"`), which is indistinguishable from "never triggers" without checking the raw subprocess output directly, as I did.

**No `best_description` or real train/test score can be reported.** The would-be numbers are quarantined in `description-optimization/blocked-diagnostic-evidence/` and explicitly marked invalid rather than presented as results. Unblocking requires the user to run `claude /login` (or set `ANTHROPIC_API_KEY`) in a terminal on this machine — not something I attempted myself, since it's a credential/account action. **SKILL.md was not touched either way**, per instructions.

---

## Viewer

Static HTML (no display in this environment, generated with `--static` per instructions, not hand-written):

**[`iteration-1/review.html`](iteration-1/review.html)** — Outputs tab (all 10 runs, prompts, replies, transcripts, formal grades) and Benchmark tab (the tables above, per-eval breakdown, analyst notes).

---

## What was and wasn't done, against the brief

- ✅ 5 realistic prompts covering all 5 requested scenarios, run with_skill/without_skill in parallel, in one pass.
- ✅ `timing.json` captured immediately from each of the 10 completion notifications (the only opportunity, per instructions).
- ✅ Assertions graded by a dedicated grader agent per run (10 total), each also critiquing its own assertions (Step 6 of `agents/grader.md`) and explicitly flagging non-discriminating ones.
- ✅ Benchmark aggregated via skill-creator's own `aggregate_benchmark.py` (not hand-rolled), with one data-quality correction documented above.
- ✅ Analyst pass beyond the standard aggregate: a dedicated agent read all 10 full transcripts (not just outputs) for reference-read waste, repeated steps, unused SKILL.md content, and a recurring cross-run workaround pattern — findings folded into `benchmark.json`'s `notes` and detailed in `transcript-efficiency-findings.md`.
- ✅ The recurring-workaround signal reported (not applied to code): documented above and in the findings file, with the concrete fix (`scripts/` entrypoint should force UTF-8 stdout) named but not implemented.
- ✅ Static HTML viewer generated via `generate_review.py --static`, not hand-written.
- ✅ 20-query trigger eval set generated per the specified train/test-relevant mix (near-miss negatives, mixed case/language/typos).
- ⛔ `run_loop.py` best_description/score: blocked by missing CLI authentication in this environment (not a skill defect) — documented, not faked, not applied to SKILL.md.
- ✅ Nothing under `skill/exam-prep/` changed (SKILL.md, references, description all untouched — verified via `git diff --stat`).
- ✅ No assertion or pass criterion softened to produce a nicer number; every "would pass either way" case is named explicitly rather than dropped or hidden.

## Suggested next steps (not actioned)
1. If the user authenticates the standalone `claude` CLI, re-run the description-optimization loop (command in BLOCKER.md) to get real `best_description`/train-test numbers before deciding whether to apply anything to SKILL.md.
2. Consider a small `scripts/` fix for the Windows console UTF-8 crash (independently confirmed by 3/5 transcripts and one grader) — highest ratio of "found repeatedly, cheap to fix once."
3. Consider whether `commands.md`/`source-of-truth.md` should document the two mechanics eval-4 had to reverse-engineer from source (valid capability IDs; how the source-coverage-gap check is actually evaluated).
4. If a second audit round is done, sample each (eval, configuration) cell 3x to actually measure run-to-run variance/flakiness, which this pass could not do with n=1.
