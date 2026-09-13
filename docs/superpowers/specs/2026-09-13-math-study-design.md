# Math Study Agent Skill — Design Specification

**Status:** Design approved for written-spec review  
**Date:** 2026-09-13  
**Scope:** Portable Agent Skill for interactive, exam-first mathematical-analysis study. Repository root is the package; runtime state is relative to the active study workspace.

## 1. Goal

Build a restart-safe tutor for a first-year student preparing for a mathematical-analysis exam with limited time. Optimize expected exam performance: retrieval, method selection, solving, debugging, transfer, and delayed recall with progressively less assistance.

The LLM is the teacher and produces structured observations. A deterministic local state engine calculates and persists mastery, review, priority, and recovery state. LLM memory and chat transcripts are never the sole source of progress.

## 2. Research basis and reuse decisions

| Area | Reused idea | Adaptation |
|---|---|---|
| Persistence | study-skill uses file-backed phases and concrete pending_action resume state | Append-only evidence plus rebuildable derived snapshots |
| Review | study-skill uses FSRS cards, capped warm-ups, and no-guilt review | Smaller exam-cram scheduler; schedule evidence types, not only topics |
| Teaching | teach-me diagnoses first and tracks misconceptions | Evidence thresholds plus exam-value triage instead of rigid mastery gates |
| Misconceptions | teach-me uses counterexamples and a new scenario before resolution | Typed errors and recurrence detection |
| Sources | tutor-skills maps sources to concepts and practice | Keep traceability/conflicts without requiring Obsidian |
| Questions | tutor-skills uses zero-hint questions and weak-area drills | Add open work, formula reading, method selection, transfer, and exam tasks |

Inspected sources:

- [study-skill](https://github.com/mordor-forge/study-skill)
- [study-skill workspace lifecycle](https://github.com/mordor-forge/study-skill/blob/main/references/workspace-lifecycle.md)
- [study-skill FSRS protocol](https://github.com/mordor-forge/study-skill/blob/main/references/fsrs-spaced-repetition.md)
- [study-skill difficulty adaptation](https://github.com/mordor-forge/study-skill/blob/main/references/difficulty-adaptation.md)
- [teach-me](https://github.com/claude-code-best/claude-code/blob/main/.claude/skills/teach-me/SKILL.md)
- [tutor-skills README](https://github.com/bevibing/tutor-skills/blob/main/README.md)
- [tutor-skills tutor skill](https://github.com/bevibing/tutor-skills/blob/main/skills/tutor/SKILL.md)
- [tutor-skills quiz rules](https://github.com/bevibing/tutor-skills/blob/main/skills/tutor/references/quiz-rules.md)

## 3. Constraints and non-goals

- No YAML. Machine-readable course/state files use JSON; evidence uses JSONL.
- No external JSON Schema validator; use a small standard-library validator for fields, types, enums, ranges, and schema versions.
- No database, web service, background scheduler, push notification, or mandatory plugin.
- No full FSRS or CAS in this phase.
- Core verification is numerical finite-difference verification; symbolic differentiation belongs only to an optional CAS adapter.
- Persist structured observations, compact summaries, bounded recent mistakes, and derived aggregates, never a giant transcript.
- Teacher materials, official exam questions, lectures, and assigned problems outrank generic model knowledge; conflicts are surfaced.
- Optional tools degrade gracefully.

## 4. Data flow

~~~text
User answer
    |
    v
LLM tutor: task, bounded assistance, observable grading
    |
    | structured Observation JSON only
    v
state/observations.jsonl  <--- append-only source of truth
    |
    v
deterministic state engine
    validate -> replay/reduce -> mastery -> mistakes
    -> priority -> review -> revision/recovery snapshot
    |
    v
compact state for the next session
~~~

The LLM may propose an observation, but the engine owns all derived scores, review dates, priority scores, and status transitions.

## 5. Package and runtime layout

~~~text
math-study/
├── SKILL.md
├── README.md
├── references/
│   ├── pedagogy.md
│   ├── exam-optimizer.md
│   ├── math-verification.md
│   └── source-of-truth.md
├── schemas/
├── scripts/
│   ├── math_study.py
│   ├── state_engine.py
│   ├── numerical_verify.py
│   └── symbolic_backend.py
├── config/config.template.json
├── syllabus/example-syllabus.json
├── state/templates/
├── knowledge/concepts/
├── reviews/
├── sessions/
├── exams/
├── examples/
└── tests/
~~~

When installed elsewhere, runtime files are relative to the active study workspace, not the installed skill directory. Package examples are inert fixtures.

## 6. State schemas

### 6.1 Course and syllabus

state/course.json owns course identity, exam date/timezone, expected points, available minutes, source precedence, and scheduler policy:

~~~json
{
  "schema_version": 1,
  "course_id": "calculus-1",
  "title": "Mathematical analysis",
  "exam": {
    "date": "2026-09-20T09:00:00+03:00",
    "timezone": "Europe/Moscow",
    "format": "mixed",
    "expected_total_points": 100
  },
  "time_budget": {
    "default_minutes": 25,
    "available_minutes_by_day": {}
  },
  "source_policy": {
    "priority_order": [
      "teacher_material",
      "official_exam_list",
      "lecture_notes",
      "problem_sets",
      "general_reference"
    ],
    "conflicts": "flag_for_user"
  },
  "scheduler": {
    "mode": "exam_cram",
    "max_review_interval_hours": 72,
    "review_warmup_limit": 3
  }
}
~~~

state/syllabus.json is the authoritative dependency graph. A concept has id, title, prerequisites, source references, exam importance/frequency/expected points, estimated learning minutes, and optional formal definition, plain explanation, intuition, read-aloud notation, exam questions, and common mistakes. Concepts are added only from declared sources or an explicit user request.

### 6.2 Append-only evidence

state/observations.jsonl is the append-only evidence/event log and ultimate rebuild source. Each complete line is one validated interaction fact, not transcript text:

~~~json
{
  "schema_version": 1,
  "observation_id": "obs-20260913-0007",
  "session_id": "session-20260913",
  "timestamp": "2026-09-13T18:30:00Z",
  "concept_id": "chain_rule",
  "task_id": "transfer-003",
  "task_type": "transfer",
  "outcome": "incorrect",
  "assistance": {
    "requested": true,
    "levels_revealed": ["H1", "H2"],
    "scaffold_types": ["method_prompt"],
    "partial_transformation_shown": false,
    "full_solution_viewed": false
  },
  "error_tags": ["conceptual_error", "prerequisite_gap"],
  "elapsed_seconds": 180,
  "expected_seconds": 240,
  "diagnostic_confidence": "high",
  "learner_self_confidence": "high",
  "learner_explanation": "Я считаю, что производная композиции...",
  "source_refs": ["official-exam-list:q7"]
}
~~~

independence and hint_level are absent. The engine derives an assistance band:

| Assistance data | Derived band |
|---|---|
| No assistance | independent |
| H1 only, no transformation shown | lightly_scaffolded |
| H2–H3 or method/next-step scaffold | guided |
| H4 or partial transformation | heavily_scaffolded |
| H5 or full solution viewed | solution_seen |

The band is calculated, not accepted from the LLM. Solution view records exposure and cannot promote mastery.

diagnostic_confidence is the tutor's confidence in classifying the observation. learner_self_confidence is the student's self-report. Neither is task correctness. Low diagnostic confidence makes evidence provisional until corroborated.

Allowed task types: definition_recall, formula_reading, recognition, explanation, error_detection, worked_example, faded_example, guided_problem, independent_problem, transfer, exam_problem, delayed_recall.

Allowed outcomes: correct, partial, incorrect, skipped, solution_seen.

Allowed errors: conceptual_error, formula_recall_error, algebra_error, method_selection_error, notation_error, careless_error, speed_problem, prerequisite_gap, domain_condition_error, proof_structure_error.

### 6.3 Rebuildable derived concept state

state/concepts.json is a derived snapshot, never the sole evidence source:

~~~json
{
  "schema_version": 1,
  "derived_from_revision": 12,
  "concepts": {
    "chain_rule": {
      "mastery": {
        "conceptual": 0.42,
        "procedural": 0.61,
        "recall": 0.74,
        "transfer": 0.28,
        "speed": 0.55
      },
      "confidence": {
        "diagnostic": 0.82,
        "learner_self_report": 0.67
      },
      "evidence": {
        "independent_successes": 3,
        "hinted_successes": 4,
        "failures": 5,
        "solution_views": 1,
        "delayed_recall_successes": 1
      },
      "status": "weak",
      "priority_score": 0.86,
      "last_tested": "2026-09-13T18:30:00Z",
      "recurring_mistakes": [
        {
          "tag": "prerequisite_gap",
          "summary": "forgets to differentiate the inner function",
          "count": 3,
          "sessions_seen": 2,
          "resolved": false
        }
      ]
    }
  }
}
~~~

The reducer maps task type to dimensions, outcome to success/partial/failure, assistance band to evidence discount, and elapsed/expected time to speed evidence. Solution views and exposure do not promote mastery. Policy defaults are configurable, but the LLM cannot override them per answer.

Statuses are locked, unseen, learning, practicing, weak, review_due, exam_ready, mastered. exam_ready requires recent independent evidence across relevant task types and one transfer or exam-style task. Perfect mastery is not a prerequisite for moving to a higher-yield concept.

### 6.4 Learner and session

state/learner.json stores durable preferences and stable patterns only:

~~~json
{
  "schema_version": 1,
  "updated_at": "2026-09-13T18:30:00Z",
  "preferences": {
    "learning_style": ["interactive", "problem_solving", "programmer_analogies"],
    "explanation_length": "concise",
    "solution_policy": "delay_full_solution"
  },
  "stable_patterns": ["benefits from algorithmic decision trees"],
  "persistent_misconceptions": ["confuses composition with multiplication"]
}
~~~

state/session.json stores current recoverable work: session id, phase, timestamps, time budget, current concept/task, energy, context, and a concrete pending_action. Summaries under sessions/ contain studied concepts, evidence changes, mistakes, due reviews, and next action; never the whole chat.

### 6.5 Review queue

state/review_queue.json is derived from evidence and exam horizon:

~~~json
{
  "schema_version": 1,
  "derived_from_revision": 12,
  "items": {
    "chain_rule": {
      "due_at": "2026-09-14T09:00:00+03:00",
      "last_review_at": "2026-09-13T18:30:00+03:00",
      "interval_hours": 15,
      "lapses": 2,
      "last_outcome": "incorrect",
      "review_kind": "targeted_recall",
      "priority_score": 0.86
    }
  }
}
~~~

Failures, recurring errors, low recall, and a near exam shorten intervals. Independent recall can lengthen them. Intervals are capped at the exam horizon and low-yield perfection may be deferred.

## 7. Revisions and crash recovery

The system must not claim multi-file writes are fully atomic. It uses an append-first log and revisioned derived snapshots:

~~~text
state/
├── observations.jsonl
├── current.json
├── revisions/000001/
│   ├── manifest.json
│   ├── concepts.json
│   ├── learner.json
│   ├── review_queue.json
│   └── session.json
└── recovery/
~~~

For a state-changing command:

1. Validate the observation without changing state.
2. Append one complete JSON line, flush, and call os.fsync where supported.
3. Replay the log or prior revision plus new evidence.
4. Write derived files into a new revision directory.
5. Write a manifest with revision, last complete observation id/line, log byte offset, and derived-file hashes.
6. Validate the revision directory.
7. Atomically replace the small current.json pointer.
8. Materialize convenience copies only after the pointer is valid.

Recovery scans the highest valid revision when the pointer is missing/corrupt, then replays unapplied complete log lines. A partial final JSONL line is ignored and diagnosed, never counted as evidence. Hash-mismatched revisions are quarantined under state/recovery/. The log is durable and rebuildable; derived JSON is a verified cache/snapshot.

## 8. Pedagogy and tutor contract

Assistance ladder:

~~~text
H0 wait/attempt
H1 point to relevant object or direction
H2 name candidate concept or method
H3 ask for the next logical step
H4 reveal a partial transformation/checkpoint
H5 show and explain the complete solution
~~~

The tutor records assistance details once, delays H5, and follows a full solution with a structurally different task. Fading is adaptive:

~~~text
intuition → worked example → faded example → guided problem
→ independent problem → transfer → exam problem → delayed recall
~~~

If the learner succeeds quickly, skip stages. If they cannot start, diagnose prerequisites and add scaffolding without silently marking mastery.

For an error, preserve the last valid step, isolate the first invalid transformation, classify internally, and ask for repair. A recurring misconception requires repeated evidence across observations/sessions. Explanation exposure, “понятно”, solution viewing, and unelaborated recognition are not strong mastery evidence.

## 9. Exam-first priority

For each unlocked concept:

~~~text
priority =
  exam_value × mastery_gap × urgency × prerequisite_readiness
  × improvement_potential ÷ estimated_learning_minutes
~~~

exam_value combines official importance, frequency, and expected points. mastery_gap uses dimensions required by likely exam tasks. urgency rises as the exam approaches and reviews become overdue. prerequisite_readiness permits targeted prerequisite repair. improvement_potential discounts topics unlikely to improve in available time.

This is a decision aid, not an exact grade prediction. The tutor explains the choice and may explicitly defer low-yield perfection. Time budgets include 10, 20, 45, 90 minutes, and deep session; every plan fits the budget and has a persistence point.

## 10. Review, interleaving, and exam mode

Reviews vary across definition/formula recall, reading aloud, method recognition, validity conditions, error detection, mini-problems, transfer, and delayed recall. After initial learning, mix neighboring methods and prerequisites so the learner identifies the method before execution.

Exam mode is stateful: no unsolicited hints, neutral question wording, optional timing, mixed syllabus sampling, minimal feedback until submission/stop, and grading by method, correctness, notation, conditions, and time. Post-mortem emits typed observations and cannot overwrite normal history.

## 11. Mathematical verification

### Core stdlib backend

Core verification uses restricted safe expression parsing, numeric sampling away from singularities, substitution checks, arithmetic recomputation, domain/denominator checks, and numerical finite-difference verification. Finite differences compare proposed derivative values with local numerical slopes and compare a proposed antiderivative's numerical derivative with the integrand. This is numerical consistency evidence, not a symbolic proof.

### Optional symbolic backend

symbolic_backend.py defines an adapter for an installed CAS such as SymPy. Symbolic differentiation, simplification, exact domain reasoning, and algebraic equivalence belong only there. The CLI reports unavailable, passed, failed, or inconclusive; domain conditions remain required.

## 12. Unified CLI

All deterministic operations use one entry point:

~~~text
python scripts/math_study.py init
python scripts/math_study.py load-syllabus syllabus/example-syllabus.json
python scripts/math_study.py start
python scripts/math_study.py status
python scripts/math_study.py next --minutes 25
python scripts/math_study.py record-observation observation.json
python scripts/math_study.py review-due
python scripts/math_study.py mistakes
python scripts/math_study.py roadmap
python scripts/math_study.py exam
python scripts/math_study.py verify expression.json
python scripts/math_study.py rebuild
python scripts/math_study.py validate
python scripts/math_study.py end-session
~~~

The Skill maps natural-language requests to these operations. The CLI validates input and computes state; it does not teach or invent observations.

## 13. Testing and acceptance criteria

Deterministic tests cover valid/invalid observations, append/revision creation, replay equivalence, pointer/revision recovery, partial-log-line handling, full-solution non-promotion, independent transfer evidence, recurring errors, time/exam priority, finite-difference pass/fail, and CAS absence.

Synthetic scenarios cover beginner limits, chain-rule misconception, 24-hour triage, restart, full-solution viewing, repeated conceptual error, and exam mode with post-mortem.

Before deployment, run pressure scenarios combining urgency, frustration, and requests for answers. Compare baseline without the Skill and behavior with the Skill, then close discovered loopholes.

Acceptance requires fresh initialization without YAML or non-stdlib runtime dependencies; resume from local state after a new session; all derived values computed by the engine; state rebuildable from observations.jsonl; revision-based recovery without a false atomicity claim; assistance represented once with independence derived; diagnostic and learner confidence separated; core numerical verification without CAS; optional symbolic verification isolated; exam-first roadmap observable; deterministic and synthetic tests passing; and concise SKILL.md with detailed protocols in references.

