# Transcript — exam-prep skill, one tutor turn

## Learner's message (Russian)

> Через неделю у меня письменный экзамен — это просто сборник задач, без билетов и теории. Хочу порешать интегралы. Давай разберём интегрирование по частям: дай мне задачу и посмотри, как я её решаю.

## Reasoning: skill activation

The `exam-prep` skill's description ("interactive, exam-first preparation
across subjects and sessions ... especially with limited time ... or a
request to continue from persistent local progress") matches this request:
the learner references a specific exam, a specific practice topic, and
implies there may be existing local state (the task environment also said a
`.exam-prep/` subfolder may already exist). Per SKILL.md, read `SKILL.md`
first, then only the references it names, only when needed.

## Step 1 — Read SKILL.md

Read `C:\programs-_-\projects\github\exam-prep\skill\exam-prep\SKILL.md` in
full (47 lines). Key takeaways applied this turn:

- Source/curriculum boundary: workspace + `observations.jsonl` are the
  canonical record, not chat memory.
- Lifecycle: run `status` first; a new workspace would need `init`; an
  existing one should have its pending action continued rather than
  inventing a lecture.
- attempt-first integrity: track is selected from
  `course.exam.question_model` (`ticket_list` vs. the
  intuition→...→transfer ladder for `problem_set`/`mixed`/`open`/unset).
  Every track requires an attempt before evaluation — no premature full
  solutions, no mastery credit for "понятно".
- After an assessable attempt, one observation proposal is created via
  `record-observation` — not applicable yet this turn since no attempt has
  happened.
- Read further references only as needed: `commands.md` (always, for exact
  CLI syntax/formats), `pedagogy.md` (needed — hints/tracks/attempt-first
  apply directly), `exam-optimizer.md` (needed — a tradeoff statement is
  expected when choosing the next activity). `source-of-truth.md`,
  `verification.md`, `notebooklm-mcp.md` were judged not needed for this
  turn (no source conflict, no numeric answer to verify yet, no NotebookLM
  integration involved).

## Step 2 — Read references/commands.md

Read in full (85 lines). Confirmed exact subcommand names and invocation
shape (`python exam_prep.py --workspace <path> <subcommand> [args]`):
`status`, `next --minutes N`, `record-observation <path>`, etc. Noted there
is no CLI command to directly set `session.current_task`/`current_target_id`
— that must happen implicitly through `next`/`record-observation`, which
matters later when deciding whether an extra "set task" call was needed (it
wasn't — see Step 5's reasoning).

## Step 3 — Read references/pedagogy.md

Read in full (123 lines). Key points applied:

- H0–H5 assistance ladder; H0 = wait for an attempt. Since no attempt has
  been made yet, the correct action is to give the problem and wait — no
  hints, no partial solution.
- Track for `problem_set` (matches this course's `question_model`):
  `intuition → worked → faded → guided → independent → transfer → exam →
  delayed recall`. For a brand-new/unseen concept, "start at the smallest
  useful stage" — but "a fast correct independent answer can skip stages,"
  and the learner explicitly asked to attempt directly ("дай мне задачу и
  посмотри, как я её решаю"), which is itself a legitimate diagnostic-first
  attempt rather than a violation of attempt-first policy.
- Anti-illusion checks: do not pre-teach or lecture on the formula before an
  attempt; the learner already named the method themselves, so no method
  orientation is owed.

## Step 4 — Read references/exam-optimizer.md

Read in full (57 lines). Key points applied:

- Decision rule for ranking targets: exam value × mastery gap × urgency ×
  prerequisite readiness × improvement potential ÷ estimated minutes.
  "Explain the selected tradeoff briefly" when choosing an activity.
- Session budgets: fit the actual minutes the learner has; do not round up
  or start an oversized lesson.
- "Never require complete topic mastery before touching a higher-yield
  topic" — supports honoring a specific, in-scope learner topic request
  even if it isn't the single top-ranked item.

## Step 5 — Bash: `status`

Command:
```
python exam_prep.py --workspace "C:\Users\lfyzer\AppData\Local\Temp\claude\C--programs----projects-github-exam-prep\29021b7a-77e5-4fdb-bcf9-87a4c16c7411\scratchpad\runs\eval-2-problem-set-practical-track\with_skill\workspace" status
```

Output summary: workspace already initialized (not `uninitialized`). Course
`exam-prep-course`, exam date `2026-09-22` (exactly one week from today,
2026-09-15, matching "через неделю"), `delivery: written`,
`question_model: problem_set` (matches the learner's "просто сборник задач,
без билетов и теории" — confirms the `problem_set` ladder, not
`ticket_list`, is correct). An open session already exists
(`session-20260914211939-cf9c59`, `phase: study`, `time_budget_minutes: 25`,
`pending_action: "choose the next budget-fitting activity"`,
`current_target_id: null`). Three targets exist:
`integration-by-parts` (`availability: available`, `mastery_status: unseen`,
all evidence counters 0, review `due`, reason "no prior evidence for this
concept"), `partial-fractions` (`availability: prerequisite_blocked`), and
`substitution-method` (`available`, also unseen/due). No errors.

Reasoning: workspace already `init`'d, so no `init` call needed. A session
is already open, so no `start` call needed. The pending action ("choose the
next budget-fitting activity") is exactly what the learner's request
resolves, via an explicit topic rather than a generic "continue" — per
SKILL.md this counts as continuing the pending action, not inventing a
lecture.

## Step 6 — Bash: `next --minutes 25`

Command:
```
python exam_prep.py --workspace "...\workspace" next --minutes 25
```

Used the session's existing `time_budget_minutes` (25) since it was already
recorded and the learner didn't state a different available time this turn.

Output summary: engine recommends `target_id: substitution-method`, not
`integration-by-parts`, with `score: 0.233243`, `reason: "exam value 3.67,
mastery gap 1.00 (required dimensions procedural/transfer), no
prerequisites, unlock value 1.19, evidence factor 0.85, time fit 1.00, due
review 1.25x"`. Its higher `prerequisite_unlock_value` (1.192) — because it
unblocks `partial-fractions` — edges out `integration-by-parts` in the raw
ranking.

Reasoning: this creates a genuine tension between the engine's top pick and
the learner's explicit, specific request. Resolved by honoring the
learner's request (integration-by-parts is itself available, due, and
zero-evidence — a legitimate target, just not the single highest-ranked
one) while briefly surfacing the tradeoff in the reply, per
exam-optimizer.md's "explain the selected tradeoff briefly" and "never
require complete topic mastery before touching a higher-yield topic."
Logged as a judgment call in `outputs/user_notes.md`.

## Step 7 — Bash: `status` (recheck)

Command:
```
python exam_prep.py --workspace "...\workspace" status
```

Run to confirm whether `next` (a read-only ranking query) had mutated
session state. Output was byte-for-byte the same session block as Step 5
(`current_target_id: null`, `current_task: null`, `pending_action`
unchanged) — confirms `next` is advisory/read-only and does not set a
"current task." This means no CLI call exists to formally mark the task as
started; the correct action is simply to pose the problem in the chat reply
itself and record the observation later, once the learner submits an
attempt (out of scope for this single turn).

## Step 8 — Compose the tutor reply

No further tool calls. Selected problem `∫ x·cos(x) dx`: a standard,
moderate-difficulty integration-by-parts example, appropriate as a
diagnostic first attempt for an `unseen` target under the `problem_set`
ladder (intuition/diagnostic stage), and matching the learner's own request
to attempt directly rather than receive a worked example first. No
theory/formula lecture given beforehand (learner already named the method
and asked to be evaluated on their own solving process — anti-lecture /
attempt-first policy applies). No hints given (H0 — wait for the attempt).
Briefly surfaced the substitution-method vs. integration-by-parts priority
tradeoff for transparency, then honored the specific request.

No `record-observation` call was made — there is no learner attempt yet to
record; observations are created only "after each assessable attempt" per
SKILL.md.

## Final reply sent to the learner (Russian)

Заглянул в твой прогресс: тема «интегрирование по частям» пока ни разу не проверялась — статус «unseen», ноль попыток, и по плану повторения она сегодня как раз «due» как диагностика. Экзамен через неделю (22.09), письменный, формат курса уже настроен как «сборник задач без билетов и теории» — так что и тренироваться будем сразу через задачи, без лекции про формулу.

Небольшая честная ремарка: формально движок приоритетов сейчас чуть выше оценивает другую тему (substitution-method — она открывает больше последующих тем и имеет чуть больший вес по времени на подготовку). Но интегрирование по частям тебе тоже всё равно нужно закрывать, оно доступно и не заблокировано пререквизитами — так что начнём с него, раз ты просишь именно его.

Теорию заранее не даю — попробуй сам(а), я смотрю. Вот задача:

**∫ x·cos(x) dx**

Реши её полностью:
1. Покажи, что берёшь за u, а что за dv (и почему именно так).
2. Примени формулу ∫u dv = uv − ∫v du — распиши этот шаг явно.
3. Доведи до финального ответа с +C.

Пиши как на письменном экзамене — по шагам, без пропусков. Я не буду подсказывать заранее; посмотрю на решение целиком и скажу, где именно первый сбой, если он будет, а не просто «верно/неверно».

## Notes

- No CLI errors occurred this turn (`errors_encountered: 0`).
- `.exam-prep/` workspace state was read but not modified this turn (no
  `record-observation`, `end-session`, `apply-curriculum`, etc. were
  called) — appropriate, since no attempt has happened yet to generate
  canonical evidence.
- A separate `outputs/user_notes.md` documents the one meaningful judgment
  call made (deviating from the engine's top `next` recommendation to honor
  the learner's explicit topic request) plus two smaller ones.
