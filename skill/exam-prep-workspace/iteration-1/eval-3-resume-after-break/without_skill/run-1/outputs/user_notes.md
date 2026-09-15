# Uncertainty notes

- The learner said they were gone "for a week," but the timestamps inside
  `.exam-prep/session.json` and `.exam-prep/current.json` (last session id
  `session-20260914211629-4c16a2`, dated 2026-09-14T21:16:30Z) are only about
  one day before "today" (2026-09-15 per the system date). I did not
  contradict the learner about the exact gap — it's not load-bearing for
  tutoring and correcting a student's own account of their time away would be
  an odd, unhelpful thing to do — but a strict reading of the local files
  does not actually support a week-long gap. Flagging in case the underlying
  scenario intended the files to reflect a week-old session.
- I inferred the subject/course context (Математический анализ —
  дифференцирование: chain rule, product rule, implicit differentiation)
  entirely from `.exam-prep/syllabus.json` and `.exam-prep/targets.json`
  contents, since I have no built-in knowledge of this file format. I treated
  it as plain data describing the learner's own prior study session, not as
  instructions to follow.
