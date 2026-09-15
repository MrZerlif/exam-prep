# Notes on judgment calls / workarounds

1. **Bash path escaping workaround.** The first `status` invocation used
   Windows-style backslash paths (as one naturally would on win32) and
   failed: the Bash tool here runs Git Bash/POSIX sh, which consumed the
   backslashes as escape characters and mangled
   `scripts\exam_prep.py` into `scriptsexam_prep.py` (exit code 2, file
   not found). Recovered by re-running the identical command with all
   paths rewritten using forward slashes, which succeeded. Counted as 1
   error in metrics.json. No workspace state was touched by the failed
   call.

2. **Did not call `next --minutes N` or `roadmap`.** SKILL.md's lifecycle
   section says to use those commands to *select* a budget-fitting
   activity when the learner hasn't specified one. Here the learner
   explicitly named "билет номер 3" by number. I treated naming a
   specific, available (non-prerequisite-blocked) ticket as a valid,
   direct resolution of the session's pending action
   ("choose the next budget-fitting activity") rather than overriding
   the learner's explicit choice with an algorithmic pick. This is an
   interpretation, not something the skill states in so many words — a
   stricter reading could argue `next` should always be consulted first
   even when the learner names a target, e.g. to sanity-check the time
   budget. I judged the explicit, valid ticket request as sufficient
   given the skill's emphasis on not inventing lectures instead of
   continuing what the learner asked for.

3. **Did not record an observation or advance session state via the
   CLI.** No assessable attempt exists yet this turn (the learner has
   only asked for the ticket, not yet produced the brief-structure
   answer). Per attempt-first integrity this is correct — nothing to
   grade — but flagging it as a judgment call since a different reading
   of "continue the pending action" might have expected some state
   mutation in this very turn. `record-observation` will apply once the
   learner responds with their brief structure / recitation attempt.
