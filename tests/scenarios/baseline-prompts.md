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
