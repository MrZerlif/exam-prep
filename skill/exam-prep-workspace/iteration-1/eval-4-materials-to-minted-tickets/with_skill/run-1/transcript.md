# Transcript — Case 4: materials to minted tickets (with_skill)

## Learner's message

> Вот у меня текст лекций по теории вероятностей (вытащил из PDF, распознавание местами кривое, файл case4-lecture-notes.txt лежит в этой папке) и официальный список экзаменационных билетов от кафедры (case4-tickets-list.txt, тоже здесь). Экзамен устный, строго по этим 5 билетам. Помоги подготовиться с нуля — хочу, чтобы билеты в итоге были оформлены как экзаменационные карточки для тренировки, а не просто лежали текстом.

## Step 1 — Read the skill

**Tool:** Read `C:\programs-_-\projects\github\exam-prep\skill\exam-prep\SKILL.md`

**Output summary:** Full skill body. Key points used later: source/curriculum boundary (`validate-curriculum` before `apply-curriculum`, authority order teacher > official exam list > lecture notes > problem sets > general reference, conflicts must be surfaced), lifecycle (`status` first, `init` once, curriculum path for materials without a ready syllabus), attempt-first integrity (track chosen from `course.exam.question_model`; `ticket_list` uses the ticket-recitation ladder from `references/pedagogy.md`), and the "read references only when needed" list.

**Reasoning:** This is a from-scratch, materials-in-hand, ticket-based oral exam case — matches the `ticket_list` question model and the curriculum-from-materials path (not `load-syllabus`, since there's no ready-made syllabus file, only raw lecture notes + an official ticket list to derive targets from).

## Step 2 — Read command catalog and list workspace

**Tool:** Read `references/commands.md`
**Tool:** Bash `ls "<workspace>"`

**Output summary:** commands.md gave the full CLI surface (lifecycle, curriculum, exam blueprint/assessment commands, `FrozenAssessment` spec, `mint-assessments` package format). `ls` confirmed the workspace only contains `case4-lecture-notes.txt` and `case4-tickets-list.txt` — no `.exam-prep` yet, consistent with "brand new learner."

## Step 3 — Read both learner materials in full

**Tool:** Read `case4-lecture-notes.txt`
**Tool:** Read `case4-tickets-list.txt`

**lecture-notes.txt content (verbatim):** 6 lectures worth of content but only 4 topics: Лекция 3 (формула полной вероятности / Байес, пример с тремя урнами), Лекция 4 (распределение Пуассона: предел биномиального при np=λ=const, формула, M=D=λ, пример call-центра), Лекция 5 (ЦПТ, теорема Ляпунова, явно "без доказательства... не входит в программу"), Лекция 6 (ЗБЧ в форме Чебышева, доказательство через неравенство Чебышева "было показано на лекции полностью").

**tickets-list.txt content (verbatim):** 5 official tickets from the department: Билет 1 (полная вероятность/Байес), Билет 2 (Пуассон, параметры, связь с биномиальным), Билет 3 (ЦПТ, без доказательства), Билет 4 (ЗБЧ Чебышева, **с доказательством**), Билет 5 (**независимость случайных величин**, критерий, пример двух зависимых величин с нулевой ковариацией). Дополнительная пометка: "экзамен устный, строго по этим пяти билетам, приоритетнее общих учебников."

**Reasoning / key finding:** Cross-checking the two files immediately surfaces a coverage gap: **Билет 5 (независимость случайных величин) has zero coverage in the lecture notes** — none of the six lectures mention independence of random variables. Билеты 1–4 map cleanly onto Лекции 3, 4, 5, 6 respectively, including matching fine detail (ticket 3 explicitly excludes the proof, matching the lecture note's own "не входит в программу"; ticket 4 explicitly requires the proof, matching the lecture note's "доказательство ... было показано ... полностью"). This gap needs to be flagged to the learner, per SKILL.md's "report missing or unknown sources as coverage gaps."

## Step 4 — Check workspace status

**Tool:** Bash `python scripts/exam_prep.py --workspace "<workspace>" status`

**Output:**
```json
{"initialized": false, "status": "uninitialized", "workspace": "<workspace>"}
```

**Reasoning:** Confirms brand-new workspace, as expected. Per lifecycle rules, only `init`, `validate`, `validate-curriculum` are allowed pre-init; run `init` once.

## Step 5 — Initialize the workspace

**Tool:** Bash `python scripts/exam_prep.py --workspace "<workspace>" init`

**Output:**
```json
{"status": "initialized", "workspace": "<workspace>"}
```

## Step 6 — Inspect what `init` created

**Tool:** Bash `find .exam-prep -type f`

**Output:** `.exam-prep/assessments.jsonl`, `course.json`, `current.json`, `learner.json`, `observations.jsonl`, `review_queue.json`, `revisions/000001/*`, `session.json`, `sessions.jsonl`, `source_evidence.jsonl`, `syllabus.json`, `targets.json`.

**Tool:** Read `.exam-prep/course.json`
**Tool:** Read `.exam-prep/syllabus.json`

**Output summary:** Default `course.json` — `exam.question_model` unset, `exam.format: "mixed"`, `source_policy.priority_order` already matches the skill's authority order (teacher_material > official_exam_list > lecture_notes > problem_sets > general_reference), `source_policy.conflicts: "flag_for_user"`. Default `syllabus.json` — empty `learning_targets`, `exam_questions`, `assessment_capabilities`, `source_refs`.

**Reasoning:** Since this is an oral, strictly-5-ticket exam, `course.exam` needs to be updated to `question_model: "ticket_list"` and `delivery: "oral"` before building the curriculum, so validation and the tutoring track selection use the right ladder (ticket → brief structure → model answer → comprehension check → unprompted reproduction → delayed recall, per `references/pedagogy.md`, read next).

## Step 7 — Read source-of-truth and pedagogy references

**Tool:** Read `references/source-of-truth.md`
**Tool:** Read `references/pedagogy.md`

**Output summary:** source-of-truth.md confirms the authority order and that the syllabus is canonical input; conflicts between high-priority sources must be surfaced and the learner asked which convention is graded. pedagogy.md gave the exact `ticket_list` stage ladder (ticket → brief answer structure → model answer → comprehension check → unprompted reproduction from memory → follow-up questions [only if `exam.follow_up_questions`] → delayed recall) and the H0–H5 assistance scale, plus the anti-illusion checks (don't promote mastery for "понятно", solution viewing, etc.).

**Reasoning:** This fixed the shape of the assessment capabilities I'd need to declare in the curriculum: `brief_structure`, `comprehension_check`, `unprompted_reproduction`, `delayed_recall` (no `follow_up_questions` stage since the blueprint wouldn't declare it).

## Step 8 — Locate schemas and examples

**Tool:** Bash `find . -iname "*.schema.json"; find . -iname "*curriculum*"; find . -iname "*example*" -o -iname "*sample*" | grep -i -E "curriculum|proposal|assessment"`

**Output summary:** Found `schemas/curriculum-proposal.schema.json`, `schemas/course.schema.json`, `schemas/learning-target.schema.json`, `schemas/assessment.schema.json`, `schemas/source-ref.schema.json`, `schemas/source-evidence.schema.json`, and `examples/curriculum-proposal.json`, `examples/assessment.json`, `examples/example-syllabus.json`, `examples/source-evidence-envelope.json`.

## Step 9 — Read curriculum proposal example + schemas

**Tool:** Read `examples/curriculum-proposal.json`
**Tool:** Read `schemas/curriculum-proposal.schema.json`
**Tool:** Read `schemas/source-ref.schema.json`

**Output summary:** Curriculum proposal needs `schema_version`, `proposal_id`, `source_refs`, `learning_targets` (each with `target_id`, `title`, `prerequisites`, `source_refs`, optional `capability_ids`/`exam_question_ids`), `assessment_capabilities`, `exam_questions`. `SourceRef` requires only `source_id`; `authority`, `locator`, `title`, etc. are optional.

## Step 10 — Read learning-target, course, and assessment schemas

**Tool:** Read `schemas/learning-target.schema.json`
**Tool:** Read `schemas/course.schema.json`
**Tool:** Read `schemas/assessment.schema.json`

**Output summary:** `course.schema.json` confirmed `exam.question_model` enum includes `"ticket_list"`, `exam.delivery` enum includes `"oral"`, and that `exam.revision` is caller-forbidden (auto-advanced). `assessment.schema.json` (`FrozenAssessment`) requires `assessment_id, target_id, capability_id, prompt, rubric, expected_evidence, source_refs, difficulty, question_version, rubric_version, spec_hash, question_hash` — but `spec_hash`/`question_hash` looked engine-computed (confirmed later in Step 15).

## Step 11 — Investigate capability-id validation rules

**Tool:** Bash `ls examples/ && grep -n "capability" scripts/exam_prep_lib/curriculum.py`
**Tool:** Bash `grep -n "AssessmentCapability(" scripts/exam_prep_lib/capabilities.py`
**Tool:** Read `scripts/exam_prep_lib/capabilities.py` (lines 1–80)
**Tool:** Bash `grep -n "MASTERY_DIMENSIONS" -A 5 scripts/exam_prep_lib/capabilities.py; cat examples/example-syllabus.json | head -80`
**Tool:** Read `examples/example-syllabus.json` (lines 80–120, the tail)

**Output summary / reasoning:** Capability ids are an open registry — unknown ones only produce a non-blocking warning, not a validation error. Notably, `AssessmentCapability.counts_as_exam_success()` special-cases `question_model == "ticket_list"` together with `delayed_recall`/`delayed_transfer` capability ids: for a ticket exam, independently reproducing a memorized ticket from memory (what `delayed_recall`/`delayed_transfer` already measure) *is* exam success — unlike a written `problem_set` exam. This confirmed that declaring `unprompted_reproduction` and `delayed_recall` as real capabilities (not placeholders) was the right call for ticket cards. The example syllabus showed the exact JSON shape for `assessment_capabilities` (dict keyed by capability id, with `affected_dimensions`, `response_type`, `review_kind`, `evidence_requirements`) and `exam_questions` (list with `question_id`, `target_ids`, `capability_ids`).

## Step 12 — Write the curriculum proposal

**Tool:** Write `curriculum-proposal-case4.json` (in the workspace)

**Content summary:** `proposal_id: "tv-case4-tickets-v1"`; top-level `source_refs` for `dept:tickets-list` (authority `official_exam_list`) and `notes:lecture-notes` (authority `lecture_notes`); 5 learning targets `tv:ticket-1-total-probability-bayes` … `tv:ticket-5-independence`, each titled with the exact Russian ticket wording, `capability_ids: ["brief_structure","comprehension_check","unprompted_reproduction","delayed_recall"]`, and per-target `source_refs` pointing at the specific lecture (targets 1–4) or, for target 5, **only** the official ticket list (no lecture-notes ref, since none exists); `assessment_capabilities` dict for the four capabilities above; 5 `exam_questions` (`tv:q1`…`tv:q5`) each mapped to its target with `capability_ids: ["unprompted_reproduction","delayed_recall"]`.

## Step 13 — Write and apply the exam blueprint patch

**Tool:** Write `exam-blueprint-patch-case4.json` — `{"delivery":"oral","question_model":"ticket_list","question_count":5,"format":"oral_ticket_exam","verbatim_definitions":true,"follow_up_questions":false}`

**Tool:** Bash `python scripts/exam_prep.py --workspace "<workspace>" update-exam-blueprint "<...>/exam-blueprint-patch-case4.json"`

**Output (full):**
```json
{
  "changed": true,
  "course": {
    "course_id": "exam-prep-course",
    "exam": {
      "date": null, "delivery": "oral", "expected_total_points": 100,
      "follow_up_questions": false, "format": "oral_ticket_exam",
      "question_count": 5, "question_model": "ticket_list",
      "revision": 2, "timezone": "UTC", "verbatim_definitions": true
    },
    "scheduler": { "...": "unchanged" },
    "schema_version": 2,
    "source_policy": { "...": "unchanged, priority_order teacher>official>lecture>problem_sets>general" },
    "time_budget": { "available_minutes_by_day": {}, "default_minutes": 25 },
    "title": "Exam preparation"
  },
  "status": "exam_blueprint_updated"
}
```

**Reasoning:** `exam.revision` auto-advanced from 1 to 2 as expected (patch never set `revision` directly). Blueprint now correctly reflects an oral, 5-ticket exam before curriculum validation runs, so `ticket_list`-specific validation/tutoring logic applies from here on.

## Step 14 — First `validate-curriculum` run (dry run) — coverage gap found

**Tool:** Bash `python scripts/exam_prep.py --workspace "<workspace>" validate-curriculum "<...>/curriculum-proposal-case4.json"`

**Output (full):**
```json
{
  "proposal_id": "tv-case4-tickets-v1",
  "valid": true,
  "validation": {
    "coverage_gaps": [
      "unknown source ref 'dept:tickets-list' in curriculum proposal",
      "unknown source ref 'notes:lecture-notes' in curriculum proposal"
    ],
    "errors": [],
    "warnings": []
  }
}
```

**Reasoning:** `valid: true` (no blocking errors), but both source ids I declared are flagged as "unknown" — per SKILL.md, "Proposal-declared refs do not establish source existence." I needed to investigate whether/how to register these two real, learner-provided files as trusted sources before applying, rather than either ignoring the gap or silently treating my own proposal's declarations as sufficient.

## Step 15 — Trace how the coverage-gap check works

**Tool:** Bash `grep -n "unknown source ref\|coverage_gap\|known_source\|source_evidence" scripts/exam_prep_lib/curriculum.py`
**Tool:** Read `scripts/exam_prep_lib/curriculum.py` (lines 255–295)

**Output summary:** `validate_curriculum_proposal` builds a `verified_source_catalog` and checks every source id referenced by the proposal against it; anything not found there is reported as an "unknown source ref" coverage gap. The catalog is passed in by the caller — not derived from the proposal's own `source_refs`.

**Tool:** Read `examples/source-evidence-envelope.json`
**Tool:** Read `schemas/source-evidence.schema.json`
**Tool:** Bash `grep -n "ingest_source_evidence\|verified_source_catalog\|build_verified_source_catalog\|def ingest" scripts/exam_prep_lib/*.py scripts/exam_prep.py`
**Tool:** Read `scripts/exam_prep_lib/source_provider.py` (lines 175–220)
**Tool:** Read `scripts/exam_prep.py` (lines 395–435)

**Output summary / reasoning:** `build_verified_source_catalog()`'s own docstring says proposal-declared refs are "intentionally not accepted here" — the caller must supply "provider-backed manifest refs or normalized persisted source evidence." `ingest-source-evidence` (via `ingest_source_evidence()`) is exactly the mechanism to persist such evidence, and `validate-curriculum`'s CLI handler builds its `verified_source_catalog` from `build_runtime_source_catalog(store)`, which reads that persisted evidence. Since I had genuinely read both `.txt` files myself (no NotebookLM MCP host is attached in this session), constructing a `SourceEvidenceEnvelope` by hand with an honest `provider_id` (`"manual-file-read"`) and real excerpts is the legitimate way to register these as trusted sources — SKILL.md explicitly says the CLI "has no MCP transport, SDK, authentication, or provider dependency," so a host-agnostic, manually-authored envelope fits the generic `SourceProvider` contract.

## Step 16 — Write and ingest the source evidence envelope

**Tool:** Write `source-evidence-case4.json` — envelope with `provider_id: "manual-file-read"`, `status: "ok"`, two evidence entries (`dept:tickets-list` / `official_exam_list`, `notes:lecture-notes` / `lecture_notes`) each with an honest excerpt summarizing the real file content, plus `diagnostics` noting the OCR caveat and the missing Билет 5 coverage.

**Tool:** Bash `python scripts/exam_prep.py --workspace "<workspace>" ingest-source-evidence "<...>/source-evidence-case4.json"`

**Output (full, as printed by the tool):**
```json
{
  "appended": 2,
  "diagnostics": [
    "OCR quality noted as imperfect by the learner; excerpts are read as-is from the provided text file.",
    "No lecture-notes coverage found for ????? 5 (?????????????? ????????? ????????)."
  ],
  "provider_id": "manual-file-read",
  "status": "ok"
}
```

**Note (uncertainty flagged, see `outputs/user_notes.md`):** The second diagnostic string printed as mojibake in the Bash console — a Windows console-codepage rendering issue, not data corruption. `appended: 2` and `status: "ok"` confirm the write succeeded; the underlying JSON file and workspace state are UTF-8 correct (verified in Step 18).

## Step 17 — Second `validate-curriculum` run — clean

**Tool:** Bash `python scripts/exam_prep.py --workspace "<workspace>" validate-curriculum "<...>/curriculum-proposal-case4.json"`

**Output (full):**
```json
{
  "proposal_id": "tv-case4-tickets-v1",
  "valid": true,
  "validation": { "coverage_gaps": [], "errors": [], "warnings": [] }
}
```

**Reasoning:** Both source ids are now recognized; zero coverage gaps, zero warnings/errors. Safe to apply.

## Step 18 — Apply the curriculum

**Tool:** Bash `python scripts/exam_prep.py --workspace "<workspace>" apply-curriculum "<...>/curriculum-proposal-case4.json"`

**Output summary (full JSON was long; key facts):** `"changed": true`, `"proposal_id": "tv-case4-tickets-v1"`. Resulting `syllabus` contains all 4 `assessment_capabilities` (`brief_structure`, `comprehension_check`, `delayed_recall`, `unprompted_reproduction`), all 5 `exam_questions` (`tv:q1`…`tv:q5`), all 5 `learning_targets` with correct titles, `source_refs`, and `capability_ids`; `source_coverage.targets_without_sources: []`, `source_coverage.unknown_source_refs: []`; final `validation` block again shows `coverage_gaps: [] / errors: [] / warnings: []`.

**Tool:** Read `.exam-prep/syllabus.json` (first 20 lines)

**Reasoning:** The Bash console again rendered Cyrillic text as mojibake in this call's output (same codepage artifact as Step 16). To rule out actual corruption, I read `.exam-prep/syllabus.json` directly with the Read tool — confirmed the file on disk is proper UTF-8 with intact Cyrillic; the garbling was confined to that one terminal echo.

## Step 19 — Design the ticket practice cards

**Tool:** Read `examples/assessment.json`

**Output summary:** Confirmed the flat `FrozenAssessment` shape used for `freeze-assessment`/`mint-assessments` entries (`assessment_id, target_id, capability_id, prompt, rubric, expected_evidence, source_refs, difficulty, question_version, rubric_version, spec_hash`).

**Tool:** Bash `grep -n "spec_hash\|question_hash" scripts/exam_prep_lib/*.py`

**Output summary / reasoning:** `spec_hash`/`question_hash` are computed by `assessment_spec_hash()`/`question_content_hash()` inside the engine and only validated against a *supplied* hash if the caller happens to include one — they are not caller-authored fields (matches commands.md's `FrozenAssessment spec`, which never lists them as inputs). So the mint package omits them entirely.

## Step 20 — Write and mint the 5 ticket cards

**Tool:** Write `mint-assessments-case4.json` — `purpose: "practice"`, 5 assessments (`tv:card-1-total-probability-bayes` … `tv:card-5-independence`), each with `capability_id: "unprompted_reproduction"`, a full Russian prompt restating the ticket's exact requirement, a rubric with concrete checkable criteria (formulas, named conditions, "must/must not include a proof" per ticket, example/counterexample requirements), `expected_evidence`, per-target `source_refs`, and a `difficulty` reflecting how demanding each ticket is (0.35 for the CLT statement-only ticket, up to 0.6 for the ЗБЧ ticket that requires a full proof). Card 5's rubric carries an extra `note_for_tutor` flagging the missing lecture-notes grounding.

**Tool:** Bash `python scripts/exam_prep.py --workspace "<workspace>" mint-assessments "<...>/mint-assessments-case4.json"`

**Output (full):**
```json
{
  "already_existed": [], "already_existed_count": 0,
  "minted": [
    {"assessment_id": "tv:card-1-total-probability-bayes", "purpose": "practice", "spec_hash": "2e39917..."},
    {"assessment_id": "tv:card-2-poisson", "purpose": "practice", "spec_hash": "2c23e9e..."},
    {"assessment_id": "tv:card-3-clt", "purpose": "practice", "spec_hash": "485ed44..."},
    {"assessment_id": "tv:card-4-lln-chebyshev", "purpose": "practice", "spec_hash": "7a40b38..."},
    {"assessment_id": "tv:card-5-independence", "purpose": "practice", "spec_hash": "339319f..."}
  ],
  "minted_count": 5, "rejected": [], "rejected_count": 0,
  "status": "assessments_minted"
}
```

**Reasoning:** All 5 cards minted cleanly, zero rejections — exactly the "экзаменационные карточки для тренировки" (practice ticket cards) the learner asked for, one per official ticket.

## Step 21 — Confirm state with `status`

**Tool:** Bash `python scripts/exam_prep.py --workspace "<workspace>" status`

**Output summary:** `course.exam` shows the oral/ticket_list blueprint at revision 2. `review_queue.items` lists all 5 targets as `due`, `review_kind: "diagnostic"`, `reason: "no prior evidence for this concept"` — expected for a fresh curriculum. `targets.targets` shows all 5 as `availability: "available"`, `mastery_status: "unseen"`, all mastery/evidence counters at 0 — correct starting state. `session.pending_action: "load a syllabus and start a session"`, `session.phase: "idle"` — session not yet opened.

## Step 22 — Open the study session

**Tool:** Bash `python scripts/exam_prep.py --workspace "<workspace>" start`

**Output summary:** `"status": "resumed"`, new `session_id: "session-20260915002650-e356b3"`, `session.phase: "study"`, `session.pending_action: "choose the next budget-fitting activity"`, `time_budget_minutes: 25` (course default, not yet confirmed with the learner). Targets unchanged (still `unseen`).

**Reasoning:** Per the lifecycle protocol, before inventing a lecture/quiz I must "ask for available time when unknown" — the learner's message didn't state a time budget for an immediate practice round, so I stop here rather than picking `next --minutes N` on their behalf, and ask them for their available time in the reply instead.

## Step 23 — Deep validation of the whole workspace

**Tool:** Bash `python scripts/exam_prep.py --workspace "<workspace>" validate`

**Output summary:** All 25 checks (`course_json_readable`, `syllabus_schema`, `capability_dimensions`, `syllabus_source_refs`, `observation_target_ids_known`, `blueprint_revision_consistency`, `assessments_jsonl_readable`, `source_evidence_jsonl_readable`, `revision_manifests_and_hashes`, `derived_target_snapshot`, `session_lifecycle`, etc.) returned `"status": "ok"`. Final: `"error_count": 0, "status": "valid", "valid": true, "warning_count": 0`.

**Reasoning:** Clean bill of health before handing back to the learner — no structural, schema, or consistency issues anywhere in the workspace.

## Step 24 — Prepare deliverables

**Tool:** Bash `mkdir -p "<outputs>"`
**Tool:** Write `outputs/final_reply.md`
**Tool:** Write `outputs/user_notes.md`
**Tool:** Write `transcript.md` (this file)
**Tool:** Write `outputs/metrics.json`

## Final reply sent to the learner (Russian, in full)

> Посмотрел оба файла и настроил рабочее пространство под устный экзамен строго по 5 билетам. Что уже готово:
>
> **Билеты сопоставлены с конспектом**
>
> | Билет | Тема | Покрытие в конспекте |
> |---|---|---|
> | 1 | Формула полной вероятности, формула Байеса | Лекция 3 — есть, с примером про три урны |
> | 2 | Пуассон: определение, параметры, M и D, связь с биномиальным | Лекция 4 — есть полностью |
> | 3 | ЦПТ: формулировка и условия (без доказательства) | Лекция 5 — есть, включая явную оговорку "без доказательства", как и в билете |
> | 4 | ЗБЧ в форме Чебышева: формулировка **и доказательство** | Лекция 6 — доказательство через неравенство Чебышева разобрано полностью на лекции |
> | 5 | Независимость случайных величин, критерий, пример с нулевой ковариацией | **В конспекте темы нет вообще** |
>
> **Важно — пробел в материалах.** Билет 5 (независимость случайных величин) не встречается ни в одной из шести лекций конспекта — либо лектор давал эту тему на занятии, которого нет в PDF, либо распознавание её "съело". Я всё равно завёл билет 5 как полноценную карточку (по официальному списку кафедры — он приоритетнее конспекта), но карточка сейчас без опоры на ваш конспект: нужен либо кусок лекции по этой теме, либо учебник/семинарские материалы, иначе при подготовке я буду опираться на общий стандартный материал, а не на то, что реально давал ваш лектор (может отличаться обозначениями или тем, какой контрпример "канонический").
>
> **Что технически сделано:**
> - Инициализировано рабочее пространство подготовки (`init`).
> - Экзамен настроен как устный, по формату билетов, 5 штук, без дополнительных вопросов (`question_model = ticket_list`, `delivery = oral`).
> - Оба файла зарегистрированы как источники (официальный список — высший приоритет, конспект — ниже, как и положено по вашей же пометке деканата).
> - Из билетов и конспекта собран учебный план (5 целей, по одной на билет), провалидирован и применён без ошибок и пробелов покрытия (кроме зафиксированного пробела по билету 5, о котором сказано выше).
> - Для каждого билета выпущена отдельная тренировочная карточка (5 штук) с точной формулировкой вопроса и критериями оценки (что именно должно прозвучать: формулы, условия, пример/доказательство — по каждому билету отдельно, с учётом того, что в билете 3 доказательство не нужно, а в билете 4 нужно полностью).
> - Открыта учебная сессия — можно сразу начинать тренировку.
>
> **Как будем тренироваться:** по каждому билету — сначала краткая структура ответа (какая формула/теорема, что дано, что доказывается, в двух словах), затем полный билет своими словами, потом я проверяю и по необходимости даю следующий билет. Готовых ответов заранее не показываю — экзамен устный, важно, чтобы вы реально проговаривали билет от начала до конца, а не узнавали его.
>
> Два вопроса к вам:
> 1. Сколько времени есть сейчас на тренировку (минут), чтобы я предложил билет, который впишется в бюджет?
> 2. Насчёт билета 5 — есть ли у вас ещё материалы (кусок другой лекции, учебник, семинар), или готовить его по общей теории вероятностей без опоры на вашего лектора?
