"""Single source of truth for exam-prep runtime defaults."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_RECURRING_MISTAKE_POLICY = {
    "min_count": 3,
    "min_sessions": 2,
    "resolve_after_clean_successes": 3,
}

EXTRACTION_ACCEPTED_FRACTION_BLOCKING = 0.9
EXTRACTION_LECTURE_QUESTIONS_PER_PAGE_BLOCKING = 20
EXTRACTION_QUESTIONS_PER_PAGE_GAP = 40
EXTRACTION_HARD_QUESTION_CAP = 5000

EXTRACTION_SCORE_WEIGHTS = {
    "solution_pair": 3.0,
    "has_points": 1.5,
    "has_options": 1.5,
    "source_kind": 1.5,
    "flat_label": 1.0,
    "sibling_uniformity": 1.0,
    "lexicon_hit": 1.0,
    "dense_run": 0.5,
    "heading_shape": -2.0,
    "global_hierarchy": -2.0,
}
EXTRACTION_SCORE_ACCEPT = 3.0
EXTRACTION_SCORE_REVIEW = 1.0

VERB_SLOT_TO_QTYPE = {
    "verb.definition": "definition",
    "verb.proof": "proof",
    "verb.calculation": "calculation",
}
VERB_SLOT_TO_CAPABILITY = {
    "verb.definition": "definition_recall",
    "verb.proof": "independent_problem",
    "verb.calculation": "calculation",
}

_DEFAULT_COURSE = {
    "schema_version": 2,
    "course_id": "exam-prep-course",
    "title": "Exam preparation",
    "language": None,
    "language_source": "unknown",
    "language_confidence": None,
    "language_detection_attempted": False,
    "exam": {
        "date": None,
        "timezone": "UTC",
        "format": "mixed",
        "expected_total_points": None,
        "revision": 1,
    },
    "time_budget": {"default_minutes": 25, "available_minutes_by_day": {}},
    "source_policy": {
        "priority_order": [
            "teacher_material",
            "official_exam_list",
            "lecture_notes",
            "problem_sets",
            "general_reference",
        ],
        "conflicts": "flag_for_user",
    },
    "scheduler": {
        "mode": "exam_cram",
        "max_review_interval_hours": 72,
        "review_warmup_limit": 3,
        "recurring_mistake_policy": DEFAULT_RECURRING_MISTAKE_POLICY,
    },
}

_DEFAULT_SYLLABUS = {
    "schema_version": 2,
    "course_id": "exam-prep-course",
    "source_refs": [],
    "learning_targets": [],
    "assessment_capabilities": {},
    "exam_questions": [],
}

_DEFAULT_LEARNER = {
    "schema_version": 1,
    "updated_at": None,
    "preferences": {
        "interaction_preferences": ["interactive"],
        "explanation_preferences": ["concise", "use_analogies_when_helpful"],
        "preferred_practice_modes": [],
        "explanation_length": "concise",
        "solution_policy": "delay_full_solution",
    },
    "stable_patterns": [],
}

_DEFAULT_SESSION = {
    "schema_version": 2,
    "session_id": "",
    "phase": "idle",
    "pending_action": "load a syllabus and start a session",
    "current_target_id": None,
    "current_task": None,
    "time_budget_minutes": 25,
    "last_attempt_outcome": None,
    "last_attempt_error_tags": [],
    "current_task_done": False,
    "mock_assessment_ids": [],
}


def default_course() -> dict[str, Any]:
    return deepcopy(_DEFAULT_COURSE)


def default_syllabus() -> dict[str, Any]:
    return deepcopy(_DEFAULT_SYLLABUS)


def default_learner(updated_at: str) -> dict[str, Any]:
    result = deepcopy(_DEFAULT_LEARNER)
    result["updated_at"] = updated_at
    return result


def default_session() -> dict[str, Any]:
    return deepcopy(_DEFAULT_SESSION)
