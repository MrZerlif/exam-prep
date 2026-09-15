# Notes on judgment calls made this turn

1. **Deviated from the engine's top `next` pick.** `next --minutes 25` returned
   `substitution-method` as the highest-priority target (score 0.233, driven
   mostly by prerequisite-unlock value — it gates `partial-fractions`, which
   is currently `prerequisite_blocked`). The learner explicitly asked to
   practice integration by parts specifically, not for a generic "continue
   studying" pick. `integration-by-parts` is `availability: available` (not
   blocked) and is itself `due` with `reason: "no prior evidence for this
   concept"`, so honoring the learner's request is consistent with
   `exam-optimizer.md`'s "Never require complete topic mastery before
   touching a higher-yield topic" and doesn't violate any lifecycle rule —
   there is no rule that `next`'s suggestion overrides an explicit,
   in-scope learner topic request. I surfaced the tradeoff briefly in the
   reply per "Explain the selected tradeoff briefly" rather than silently
   overriding or silently complying.

2. **Did not call `start` or any "set current task" command.** There is no
   CLI command in `references/commands.md` for setting `session.current_task`
   directly; a second `status` call after `next` confirmed `next` is
   read-only (session state unchanged: `current_target_id`, `current_task`
   still `null`). The session was already open (`phase: study`, an existing
   `session_id`), so `start` was not needed. Posing the problem in chat is
   the correct next action; the task/attempt will presumably be recorded via
   `record-observation` once the learner actually submits a solution in a
   later turn (out of scope for this single turn per the task instructions).

3. **Problem choice (∫x·cos(x) dx) was my own pedagogical judgment**, not
   engine-specified — the CLI has no "give me a problem" content generator.
   Picked as a standard, moderate-difficulty diagnostic first example for an
   `unseen` concept under `problem_set` track (intuition/diagnostic stage),
   matching the learner's own request to attempt a problem directly rather
   than receive a worked example first.
