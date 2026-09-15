# Source-of-truth protocol

When teacher materials, an official exam list, lecture notes, assigned problem
sets, or a general reference are available, map their claims and questions to
learning-target ids. Preserve source_refs on observations and surface conflicts.

Default precedence:

~~~text
teacher material > official exam list > lecture notes
> assigned problem sets > general reference
~~~

Do not silently replace the declared syllabus with a generic standard course.
Add learning targets from declared sources or an explicit learner request. Keep
definitions, notation, expected methods, and grading conventions from the
highest-priority source. If two high-priority sources disagree, show the
conflict and ask which convention the instructor will grade.

The syllabus is canonical course input. In v2 it contains `LearningTarget`
records keyed by `target_id`; `observations.jsonl` is canonical learning
evidence keyed by `target_id` and `capability_id`. `targets.json` and
`review_queue.json` are rebuildable reducer outputs. learner.json and
session.json are protected profile/runtime snapshots. Legacy `concept_id` and
`concepts.json` remain readable only through compatibility paths.
Do not hand-edit derived mastery or review values.

For a new session, read compact state through the CLI. Old session detail is
diagnostic material only; it does not replace structured evidence.

A source is only "known" to `validate-curriculum`/`apply-curriculum` once it
has been persisted to this workspace through `ingest-source-evidence`.
Writing a `source_refs` entry inside the curriculum proposal itself does not
register that source - it only declares an intended citation, which the
engine checks against already-ingested evidence, not against itself. This is
what `SKILL.md`'s "Proposal-declared refs do not establish source existence"
means mechanically: an `unknown source ref` coverage gap is cleared by
ingesting the source first, not by editing the proposal's own `source_refs`
list (`references/commands.md`).

