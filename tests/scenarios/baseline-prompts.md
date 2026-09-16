# RED baseline

Run each prompt in a fresh tutor context without SKILL.md, then record the observed
failure mode before writing the skill.

1. **Beginner + answer pressure:** “Я новичок. Объясни пределы и сразу реши несколько задач за меня.”
2. **Recurring misconception:** “Я снова забыл внутреннюю производную в chain rule. Просто дай правило.”
3. **Exam urgency + 25 minutes:** “До экзамена 24 часа, половина syllabus не покрыта. Что делать за 25 минут?”
4. **Restart:** “Продолжаем матан.” with prior progress unavailable in chat.
5. **Solution exposure:** “Я посмотрел полное решение. Значит, тема mastered?”
6. **Exam mode:** “Сделай пробный экзамен и не подсказывай.”
7. **Crash retry:** submit the same observation id twice, then submit a changed payload with that id.

Expected baseline risks: transcript-dependent resume, premature full solutions, binary
mastery, stale or absent exam triage, duplicate evidence, and no durable recurring-error
history. The baseline is behavioral evidence, not runtime state.

## Executable fresh-context evaluation

The deterministic runner is not a model evaluator. For a fresh-context comparison,
export both variants and five repetitions. With no `--cases` override the export
covers the four release-gate cases - `restart`, `one_mistake_show_answer`,
`fifteen_minute_budget`, `teacher_material_conflict` - the same set
`evaluate_transcripts.py` requires scores for:

~~~powershell
python tests/scenarios/run_scenarios.py --emit-eval-set .tmp/exam-prep-eval.jsonl --repeat 5
~~~

Run each packet in the chosen host/model context. Add the externally observed
`response`, explicit boolean `pass_scores` and `forbidden_scores`, and reviewer
notes to a score JSONL file. The local evaluator performs no keyword matching and
fails the release gate for missing runs/scores, forbidden behavior, less than 90%
required-criterion success, or skill performance below baseline:

~~~powershell
python tests/scenarios/evaluate_transcripts.py scores.jsonl
~~~

Model execution and semantic scoring remain host-level/manual; Python tests must
not call a model API. Do not claim behavioral compliance from the deterministic
engine suite alone.
