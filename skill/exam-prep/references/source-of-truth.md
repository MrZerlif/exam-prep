# Source-of-truth protocol

When teacher materials, an official exam list, lecture notes, assigned problem
sets, or a general reference are available, map their claims and questions to
concept ids. Preserve source_refs on observations and surface conflicts.

Default precedence:

~~~text
teacher material > official exam list > lecture notes
> assigned problem sets > general reference
~~~

Do not silently replace the declared syllabus with a standard calculus course.
Add concepts from declared sources or an explicit learner request. Keep
definitions, notation, expected methods, and grading conventions from the
highest-priority source. If two high-priority sources disagree, show the
conflict and ask which convention the instructor will grade.

The syllabus is canonical course input. observations.jsonl is canonical
learning evidence. concepts.json and review_queue.json are rebuildable reducer
outputs. learner.json and session.json are protected profile/runtime snapshots.
Do not hand-edit derived mastery or review values.

For a new session, read compact state through the CLI. Old session detail is
diagnostic material only; it does not replace structured evidence.

