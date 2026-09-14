import sys
import unittest


sys.path.insert(0, "skill/exam-prep/scripts")

from exam_prep_lib.reducer import (  # noqa: E402
    derive_assistance_band,
    reduce_learning_state,
    MASTERY_DIMENSIONS,
)


SYLLABUS = {
    "schema_version": 1,
    "concepts": {
        "chain_rule": {
            "title": "Chain rule",
            "prerequisites": ["derivative_rules"],
            "importance": 0.9,
            "frequency": 0.8,
            "expected_points": 10,
            "estimated_learning_minutes": 30,
        },
        "derivative_rules": {
            "title": "Derivative rules",
            "prerequisites": [],
            "importance": 0.8,
            "frequency": 0.8,
            "expected_points": 10,
            "estimated_learning_minutes": 20,
        },
    },
}


COURSE = {"schema_version": 1, "scheduler": {"mode": "exam_cram"}}


def event(
    *,
    concept_id="chain_rule",
    task_type="independent_problem",
    outcome="correct",
    assistance=None,
    error_tags=None,
    elapsed_seconds=20,
    expected_seconds=30,
    session_id="session-1",
):
    return {
        "schema_version": 1,
        "observation_id": f"obs-{session_id}-{concept_id}-{task_type}-{outcome}",
        "recorded_at": "2026-09-13T15:30:00+00:00",
        "session_id": session_id,
        "concept_id": concept_id,
        "task_id": "task-1",
        "task_type": task_type,
        "outcome": outcome,
        "assistance": assistance
        or {
            "requested": False,
            "levels_revealed": [],
            "scaffold_types": [],
            "partial_transformation_shown": False,
            "full_solution_viewed": False,
        },
        "error_tags": error_tags or [],
        "diagnostic_confidence": "high",
        "learner_self_confidence": "medium",
        "learner_explanation": "Проверил шаги.",
        "source_refs": [],
        "elapsed_seconds": elapsed_seconds,
        "expected_seconds": expected_seconds,
    }


class ReducerTests(unittest.TestCase):
    def test_assistance_band_is_derived_from_structured_assistance(self):
        self.assertEqual(
            derive_assistance_band(
                {
                    "requested": False,
                    "levels_revealed": [],
                    "scaffold_types": [],
                    "partial_transformation_shown": False,
                    "full_solution_viewed": False,
                }
            ),
            "independent",
        )
        self.assertEqual(
            derive_assistance_band(
                {
                    "requested": True,
                    "levels_revealed": ["H1"],
                    "scaffold_types": ["direction"],
                    "partial_transformation_shown": False,
                    "full_solution_viewed": False,
                }
            ),
            "lightly_scaffolded",
        )
        self.assertEqual(
            derive_assistance_band(
                {
                    "requested": True,
                    "levels_revealed": ["H2", "H3"],
                    "scaffold_types": ["method_prompt", "next_step"],
                    "partial_transformation_shown": False,
                    "full_solution_viewed": False,
                }
            ),
            "guided",
        )
        self.assertEqual(
            derive_assistance_band(
                {
                    "requested": True,
                    "levels_revealed": ["H4"],
                    "scaffold_types": [],
                    "partial_transformation_shown": True,
                    "full_solution_viewed": False,
                }
            ),
            "heavily_scaffolded",
        )
        self.assertEqual(
            derive_assistance_band(
                {
                    "requested": True,
                    "levels_revealed": ["H5"],
                    "scaffold_types": [],
                    "partial_transformation_shown": True,
                    "full_solution_viewed": True,
                }
            ),
            "solution_seen",
        )

    def test_solution_view_does_not_promote_mastery(self):
        before = reduce_learning_state(COURSE, SYLLABUS, [], {})
        after = reduce_learning_state(
            COURSE,
            SYLLABUS,
            [
                event(
                    task_type="worked_example",
                    outcome="solution_seen",
                    assistance={
                        "requested": True,
                        "levels_revealed": ["H5"],
                        "scaffold_types": ["full_solution"],
                        "partial_transformation_shown": True,
                        "full_solution_viewed": True,
                    },
                )
            ],
            {},
        )
        self.assertEqual(
            before["concepts"]["chain_rule"]["mastery"],
            after["concepts"]["chain_rule"]["mastery"],
        )
        self.assertEqual(after["concepts"]["chain_rule"]["evidence"]["solution_views"], 1)

    def test_independent_success_updates_multiple_dimensions(self):
        result = reduce_learning_state(
            COURSE, SYLLABUS, [event(task_type="transfer")], {}
        )
        mastery = result["concepts"]["chain_rule"]["mastery"]
        self.assertGreater(mastery["procedural"], 0.0)
        self.assertGreater(mastery["transfer"], 0.0)
        self.assertGreater(mastery["speed"], 0.0)

    def test_confidence_fields_are_not_merged(self):
        result = reduce_learning_state(
            COURSE,
            SYLLABUS,
            [event()],
            {},
        )
        confidence = result["concepts"]["chain_rule"]["confidence"]
        self.assertIn("diagnostic", confidence)
        self.assertIn("learner_self_report", confidence)
        self.assertNotEqual(confidence["diagnostic"], confidence["learner_self_report"])

    def test_recurring_mistake_is_concept_local(self):
        events = [
            event(
                outcome="incorrect",
                error_tags=["conceptual_error"],
                session_id="session-1",
            ),
            event(
                outcome="incorrect",
                error_tags=["conceptual_error"],
                session_id="session-2",
            ),
            event(
                outcome="incorrect",
                error_tags=["conceptual_error"],
                session_id="session-3",
            ),
        ]
        result = reduce_learning_state(COURSE, SYLLABUS, events, {})
        mistakes = result["concepts"]["chain_rule"]["recurring_mistakes"]
        self.assertEqual(mistakes[0]["tag"], "conceptual_error")
        self.assertEqual(mistakes[0]["count"], 3)
        self.assertEqual(mistakes[0]["sessions_seen"], 3)
        self.assertNotIn("persistent_misconceptions", result)


    def test_corrupt_syllabus_dimension_is_ignored_during_recovery(self):
        syllabus = {
            "schema_version": 1,
            "concepts": {"target": {"prerequisites": []}},
            "assessment_capabilities": {
                "custom": {"affected_dimensions": ["knowledge"]}
            },
        }
        result = reduce_learning_state(
            COURSE,
            syllabus,
            [
                {
                    "schema_version": 2,
                    "observation_id": "corrupt-dimension",
                    "concept_id": "target",
                    "target_id": "target",
                    "task_id": "task",
                    "capability_id": "custom",
                    "outcome": "correct",
                    "assistance": {"levels_revealed": []},
                }
            ],
            {},
        )
        mastery = result["concepts"]["target"]["mastery"]
        self.assertEqual(set(MASTERY_DIMENSIONS), set(mastery))
        self.assertNotIn("knowledge", mastery)

if __name__ == "__main__":
    unittest.main()