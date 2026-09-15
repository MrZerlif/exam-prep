# Transcript efficiency audit — exam-prep skill (iteration-1, with_skill vs without_skill)

Scope: observation only, no correctness grading, no skill edits. Covers the 5
`with_skill` transcripts (eval-1..eval-5) and the corresponding
`without_skill` transcripts read for comparison context, plus `SKILL.md` and
its six `references/*.md` files.

---

## 1. Redundant reference reads

Overall the skill's "read references only when needed" instruction is
followed reasonably well — no transcript reads all six references, and each
run states which ones it skipped and why (e.g. eval-1: *"exam-optimizer.md,
source-of-truth.md, verification.md, notebooklm-mcp.md were not read
because nothing in this turn touches prioritization math, source conflicts,
numeric verification, or NotebookLM"*). Two softer cases stood out:

- **eval-4 — `references/source-of-truth.md` read for a situation that
  turned out to be a coverage gap, not the "two sources disagree" case the
  file is written for.** Step 7 reads it "to fix the shape of the assessment
  capabilities" and confirm authority order, but the actual issue
  encountered later (Step 14) was `"unknown source ref"` — a *missing*
  source registration, resolved by `ingest-source-evidence`, not the
  conflict-arbitration workflow source-of-truth.md actually describes
  ("If two high-priority sources disagree, show the conflict and ask which
  convention the instructor will grade"). The authority-order fact it did
  use (teacher > official > lecture > problem sets > general) was already
  visible for free in the default `course.json` read one step earlier
  (Step 6: *"source_policy.priority_order already matches the skill's
  authority order"*), so the reference read added little beyond
  confirmation.

- **`references/verification.md` and `references/notebooklm-mcp.md` are
  never read in any of the 5 with_skill runs.** This isn't "redundant" in
  the sense of a wasted read, but it is the mirror problem worth flagging
  under finding 3 below: eval-2 and eval-5 both involve grading calculus
  answers (integration by parts, a series convergence test) entirely by the
  tutor's own arithmetic, with no `verify` CLI call — exactly the scenario
  verification.md says the verifier exists to guard against ("a second-pass
  guard against tutor arithmetic mistakes... not a substitute for checking
  assumptions").

No instance was found of a reference being read and then contradicted or
ignored by the reply — when references were read, their content was
generally load-bearing.

---

## 2. Repeated/duplicate steps

- **eval-2, Steps 5 and 7 — `status` called twice back-to-back with only a
  read-only `next` call in between**, solely to confirm `next` didn't mutate
  session state:
  > "Run to confirm whether `next` (a read-only ranking query) had mutated
  > session state. Output was byte-for-byte the same session block as Step
  > 5... This means no CLI call exists to formally mark the task as
  > started."
  Nothing in `commands.md` suggests `next` is stateful, so this is a full
  extra `status` round-trip (a ~180-line JSON payload) spent verifying a
  property the docs already imply.

- **eval-3, Step 9 — `session.json` read directly, immediately after
  `status` (Step 3) already returned the same session block.** The
  transcript's own output summary says so explicitly: *"Output summary:
  Mirrors the status session block: current target chain-rule, current task
  chain-rule-task-1, current_task_done: false, pending_action unchanged,
  time_budget_minutes: 25..."* — a same-turn, no-state-change re-read of
  information already in hand.

- **eval-3, Step 13 — `mistakes` CLI call as a "cheap confirmation check"**
  after `targets.json` (Step 5) had already shown the one existing mistake
  entry (`chain-rule`, `formula_recall_error`, `recurring: false`) and no
  other target had any mistake data. The `mistakes` output added no new
  fact (*"Only the one chain-rule entry... No other concepts have mistakes
  on file"*) — it re-confirmed what Step 5 already established.

- **eval-4, Step 18 — `syllabus.json` re-read (first 20 lines) purely to
  rule out corruption** after `apply-curriculum`'s console output showed
  mojibake — see finding 4 below; this is the same workaround pattern
  applied a second time within one transcript, on top of the three other
  transcripts that also hit it.

- **eval-3 overall shows the heaviest redundancy relative to its trigger.**
  For a one-line "continue?" message, the run performs 13 tool-call steps
  reading `status`, then separately `targets.json`, `syllabus.json`,
  `observations.jsonl`, `sessions.jsonl`, `session.json`, `assessments.jsonl`,
  plus a `mistakes` call and a `start` call — even though `commands.md`
  defines `status` itself as exactly "compact snapshot: course, syllabus,
  session, review queue, mistakes, pending action, capability/blueprint
  diagnostics, resume point." Most of the follow-up reads were driven by
  the console-mojibake workaround (finding 4) or by fetching the one piece
  `status` genuinely omits (human-readable Cyrillic titles, the full
  `learner_explanation` text) — but `session.json` and the `mistakes`
  re-check were not required by either of those needs.

---

## 3. Unused SKILL.md content

Looking across all 5 with_skill runs for SKILL.md clauses that never
appeared to shape behavior:

- **The NotebookLM MCP paragraph** ("NotebookLM MCP is an optional agent
  host integration...") is never triggered or referenced as load-bearing in
  any of the 5 runs — no run has a NotebookLM host available, and none call
  `references/notebooklm-mcp.md`. Reasonable given the eval setup (no MCP
  host attached), but across this whole 5-run sample this entire clause,
  and its dedicated reference file, did zero work.

- **`references/verification.md` / the `verify` CLI command are never
  invoked**, despite two runs (eval-2, eval-5) grading calculus by hand.
  eval-5's grading step is explicit self-graded arithmetic with no
  cross-check: *"Q3: incorrect. Chooses the comparison test but compares in
  the wrong direction... Tag: conceptual_error"* — a judgment the `verify`
  command's "numeric samples away from singularities" / "derivative
  finite-difference comparison" machinery exists specifically to
  double-check, per verification.md's own framing as a guard against "tutor
  arithmetic mistakes." Across 5 runs this documented safety mechanism is
  never exercised.

- **The source-conflict-arbitration clause** in SKILL.md ("A conflict is
  surfaced and the learner is asked which convention will be graded") is
  never actually exercised as a *conflict* in any transcript — eval-4 comes
  closest but the situation it hits is a coverage *gap* (missing source),
  handled by `ingest-source-evidence`, not two disagreeing high-priority
  sources. So this specific clause's distinguishing behavior (asking the
  learner to arbitrate between two sources) is present in the doc but
  unexercised in the sample.

- **`learner_self_confidence`** ("Add `learner_self_confidence` only when
  explicitly stated") is mentioned in SKILL.md but no transcript's recorded
  observation (only eval-5 records any) shows this field being included or
  deliberately omitted with reasoning — its handling is invisible in every
  run, so it can't be confirmed as load-bearing from the transcripts alone.

- **`migrate --from-math-study`** (mentioned only in commands.md, not
  SKILL.md itself) is never invoked — expected, since it's explicitly
  flagged as "not part of routine use."

Everything else in SKILL.md's body — the lifecycle/`status`-first rule, the
attempt-first integrity paragraph, the ticket_list vs. problem_set track
selection, the H0–H5/no-premature-disclosure rule, and the
"report missing or unknown sources as coverage gaps" line — is visibly
load-bearing in at least one run (often several), with the transcripts
explicitly citing the clause as the reason for a specific action.

---

## 4. Recurring workaround: Windows console Cyrillic mojibake → re-read the JSON file directly

This exact pattern — the CLI's own JSON output is correct UTF-8, but the
Bash/PowerShell terminal echoes Cyrillic text as mojibake, so the model
distrusts the terminal and re-reads the underlying `.exam-prep/*.json` file
directly with the `Read` tool to recover the real text — was independently
hit and independently worked around in **3 of the 5 with_skill runs**
(eval-3, eval-4, eval-5):

- **eval-3, Step 3:** *"Note on console encoding: the `target_title` field
  for chain-rule printed as mojibake (`???` / replacement-looking bytes) in
  the Bash/PowerShell terminal output — a Windows console codepage issue,
  not a CLI error. The command itself succeeded and returned valid JSON;
  the readable Cyrillic title was recovered directly from the workspace
  JSON files instead of the terminal echo (see Steps 5–6)."* This directly
  motivates the Step 5 (`targets.json`) and Step 6 (`syllabus.json`) reads.
  Restated in the closing notes: *"Terminal/console mojibake on Cyrillic
  `target_title` text in the `status`/`start` JSON output... was worked
  around by reading the underlying JSON files directly with the Read tool
  rather than trusting the terminal echo."*

- **eval-4, Step 16:** after `ingest-source-evidence`, *"the second
  diagnostic string printed as mojibake in the Bash console — a Windows
  console-codepage rendering issue, not data corruption. `appended: 2` and
  `status: "ok"` confirm the write succeeded; the underlying JSON file and
  workspace state are UTF-8 correct (verified in Step 18)."* Step 18 then
  performs the actual verification: *"The Bash console again rendered
  Cyrillic text as mojibake in this call's output (same codepage artifact
  as Step 16). To rule out actual corruption, I read `.exam-prep/syllabus.
  json` directly with the Read tool — confirmed the file on disk is proper
  UTF-8 with intact Cyrillic; the garbling was confined to that one
  terminal echo."*

- **eval-5, Step 2:** *"Full output (Cyrillic prompts displayed mangled in
  this terminal's codepage, but the underlying UTF-8 content was already
  read correctly from `assessments.jsonl` above)."* Here the workaround was
  applied proactively (the file had already been read before the mangled
  console call), rather than reactively, but it's the same root cause and
  the same fix (trust the file, not the terminal).

  eval-5 also surfaces a **more severe variant of the same root cause**: a
  genuine CLI crash, not just display garbling. Step 4 (recording Q2):
  ```
  {"error": "'charmap' codec can't encode character '\\u222b' in position 888: character maps to <undefined>"}
  ```
  *"The learner_explanation text contained the literal integral sign '∫'
  (U+222B). The CLI wrote the observation to the UTF-8
  `observations.jsonl` file successfully but then crashed trying to print
  its own confirmation JSON to this Windows terminal's non-UTF-8
  codepage."* The fix required editing the proposal JSON to remove the
  Unicode glyph and retry — which then collided with the idempotency guard
  because the original (unedited) write had, despite the crash, already
  succeeded: *"`observation_id 'obs-mock20260915-0002' already has a
  different payload`"* — requiring a third step (`tail -c 2000
  observations.jsonl`) just to confirm the original data was safely
  persisted and move on.

eval-1 and eval-2 do not explicitly flag mojibake, though eval-1's Step 7
read of `syllabus.json` "to get the actual title... rather than just saying
'ticket 3'" is consistent with the same underlying gap (status alone
doesn't surface clean Cyrillic titles) without being labeled as an encoding
workaround.

**Baseline comparison:** none of the `without_skill` transcripts hit this
issue at all, for eval-3/4/5 alike — because the baseline never invokes the
Python CLI through Bash in the first place. It reads the same
`.exam-prep/*.json` files directly with the `Read` tool from the start
(e.g. without_skill eval-3: *"Read on `.exam-prep/session.json`,
`learner.json`, `course.json`..."*), so the console-codepage round trip
never happens. This is overhead that is specific to the skill's
CLI-first workflow and has no counterpart in the plain-baseline condition
doing the equivalent task.

---

## 5. Other busywork

- **eval-4's source-code archaeology to understand undocumented
  `validate-curriculum` mechanics.** Steps 11 and 15 grep and read directly
  into the Python implementation (`capabilities.py`, `curriculum.py`,
  `source_provider.py`, `exam_prep.py`) to answer two questions neither
  `commands.md` nor `source-of-truth.md` spells out: (a) which capability
  ids are "real" for exam-success purposes
  (`grep -n "AssessmentCapability(" scripts/exam_prep_lib/capabilities.py`,
  then reading 80 lines of it), and (b) how the `"unknown source ref"`
  coverage-gap check is actually satisfied (`grep -n "unknown source
  ref\|coverage_gap\|known_source\|source_evidence"
  scripts/exam_prep_lib/curriculum.py`, then reading
  `curriculum.py:255-295`, `source_provider.py:175-220`, and
  `exam_prep.py:395-435`). This is six extra tool calls spent reverse
  engineering behavior that a one- or two-line note in
  `source-of-truth.md` or `commands.md` (e.g. "coverage gaps are checked
  against ingested source evidence, not the proposal's own declared
  refs") would have made unnecessary. It is real, task-relevant discovery
  (not idle exploration), but it is discovery the skill's own reference
  docs left the model to do from scratch.

- **Self-inflicted CLI invocation errors, each costing one extra
  round-trip, with different causes in different runs (not the same
  recurring pattern, but part of the same overall friction profile):**
  eval-1's first `status` call fails because Windows-style backslash paths
  get mangled by the POSIX/Git-Bash tool (`scripts\exam_prep.py` →
  `scriptsexam_prep.py`), fixed by switching to forward slashes; eval-5's
  first `status` call fails because `--workspace` was placed after the
  subcommand instead of before it (`status --workspace ...` →
  `unrecognized arguments`), fixed by checking `--help`. Both are one-shot,
  quickly self-corrected mistakes rather than a shared workaround, but each
  adds a full failed round trip that the without_skill baseline (which
  never shells out to the CLI) never risks.

- **eval-5's sandbox/tool-harness false-positive**, unrelated to the skill
  itself: redirecting `record-observation` output to a file outside the
  recognized worktree tripped a git-safety heuristic even though no git
  command was involved (*"this command names git in a form too complex to
  verify that it stays inside the worktree"*), costing one wasted call
  before retrying without the redirect. Noted for completeness since it's
  overhead present in the with_skill run with no equivalent in the
  without_skill run (which never redirects CLI output at all).

- **eval-4's schema/example spelunking (Steps 8–10, 19)** — reading
  `curriculum-proposal.schema.json`, `course.schema.json`,
  `learning-target.schema.json`, `assessment.schema.json`,
  `source-ref.schema.json`, plus three example JSON files, on top of the
  `commands.md` package-format description — is arguably necessary given
  the task requires hand-authoring a `FrozenAssessment`/curriculum-proposal
  payload from scratch and `commands.md` only sketches the shape at a high
  level. It borders on busywork only in that it duplicates information
  `commands.md` already partially states (e.g. the `FrozenAssessment`
  field list is given in commands.md but re-derived from the schema file
  anyway) — a minor, not major, overlap.

---

## Overall verdict

Relative to the without_skill baseline, the skill's overhead is concentrated
in two places: (1) a fixed per-turn cost of reading `SKILL.md` plus
1–3 reference files (roughly 50–250 lines of instructional text) that the
baseline pays nothing for, and (2) a CLI-mediated I/O path (`Bash` →
Windows console → JSON) that, unlike the baseline's direct `Read` of the
same `.exam-prep/*.json` files, is vulnerable to a Windows console-codepage
bug that independently cost extra tool calls in 3 of 5 runs (and a genuine
crash-and-recover sequence in one of them). For a single short exchange
(eval-1, eval-2) this overhead is modest and mostly proportionate — the
reference reads are selectively made and visibly change the reply (forcing
the "brief structure" checkpoint, surfacing the priority-engine tradeoff).
For the from-scratch curriculum build (eval-4) and the resume-after-a-week
case (eval-3), the overhead is considerably larger and only partly
justified: eval-3's 13-step read fan-out reconfirms information `status`
already compactly provides more than it needed to, and eval-4's several
rounds of grepping into the Python implementation exist to compensate for
gaps in the reference docs rather than to serve the learner's request
directly. None of this overhead changed what was ultimately told to the
learner in any of the 5 runs — the final replies are comparable in
substance to what the without_skill baseline produced for the same turns
(where the baseline had access to the state at all) — so the extra tool
calls bought verification and provenance rigor (genuine, real persisted
state; no fabricated history) rather than better answers. Whether that
rigor is worth the roughly 1.5–3x larger tool-call count seen in eval-3 and
eval-4 is a judgment call, but the Windows-console mojibake workaround in
particular is pure waste with a well-defined, cheap fix (read the file
instead of trusting the terminal, every time, not just after first getting
burned) that three separate runs each had to rediscover independently.
