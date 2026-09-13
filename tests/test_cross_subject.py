import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.reducer import reduce_learning_state  # noqa: E402
from exam_prep_lib.scheduler import build_review_queue, select_next_activity  # noqa: E402


class CrossSubjectTests(unittest.TestCase):
    def test_algebra_and_physics_use_the_same_target_and_evidence_contract(self):
        syllabus = {
            "schema_version": 2,
            "learning_targets": [
                {
                    "target_id": "algebra:linear",
                    "title": "Linear equations",
                    "prerequisites": [],
                    "source_refs": [{"source_id": "algebra:notes", "authority": "teacher_material"}],
                },
                {
                    "target_id": "physics:newton-2",
                    "title": "Newton's second law",
                    "prerequisites": [],
                    "source_refs": [{"source_id": "physics:notes", "authority": "teacher_material"}],
                },
            ],
        }
        events = [
            {
                "target_id": "algebra:linear",
                "capability_id": "independent_problem",
                "task_type": "independent_problem",
                "outcome": "correct",
                "assistance": {"levels_revealed": []},
            },
            {
                "target_id": "physics:newton-2",
                "capability_id": "transfer",
                "task_type": "transfer",
                "outcome": "correct",
                "assistance": {"levels_revealed": []},
            },
        ]
        derived = reduce_learning_state({}, syllabus, events, {})
        self.assertGreater(
            derived["targets"]["algebra:linear"]["mastery"]["procedural"], 0
        )
        self.assertGreater(
            derived["targets"]["physics:newton-2"]["mastery"]["transfer"], 0
        )
        reviews = build_review_queue(
            events,
            derived["targets"],
            {},
            __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            syllabus,
        )
        selected = select_next_activity(
            syllabus, derived["targets"], reviews["items"], {}, __import__("datetime").datetime.now(__import__("datetime").timezone.utc), 25
        )
        self.assertIn(selected["concept_id"], {"algebra:linear", "physics:newton-2"})

    def test_humanities_security_and_programming_share_the_same_v2_path(self):
        syllabus = {
            "schema_version": 2,
            "learning_targets": [
                {"target_id": "philosophy:categorical-imperative", "prerequisites": [], "capability_ids": ["oral_answer"]},
                {"target_id": "history:source-interpretation", "prerequisites": [], "capability_ids": ["source_criticism"]},
                {"target_id": "security:dac-vs-mac", "prerequisites": [], "capability_ids": ["scenario_application"]},
                {"target_id": "programming:debugging", "prerequisites": [], "capability_ids": ["debugging"]},
            ],
            "assessment_capabilities": {
                "oral_answer": {"affected_dimensions": ["conceptual"]},
                "scenario_application": {"affected_dimensions": ["transfer"]},
            },
        }
        events = [
            {
                "schema_version": 2,
                "observation_id": target_id,
                "target_id": target_id,
                "capability_id": capability_id,
                "task_type": "open_activity",
                "outcome": "correct",
                "assistance": {"levels_revealed": []},
                "error_tags": [],
            }
            for target_id, capability_id in (
                ("philosophy:categorical-imperative", "oral_answer"),
                ("history:source-interpretation", "source_criticism"),
                ("security:dac-vs-mac", "scenario_application"),
                ("programming:debugging", "debugging"),
            )
        ]
        derived = reduce_learning_state({}, syllabus, events, {})
        self.assertGreater(derived["targets"]["philosophy:categorical-imperative"]["mastery"]["conceptual"], 0)
        self.assertGreater(derived["targets"]["security:dac-vs-mac"]["mastery"]["transfer"], 0)
        self.assertEqual(0, derived["targets"]["history:source-interpretation"]["mastery"]["conceptual"])
        self.assertEqual(0, derived["targets"]["programming:debugging"]["mastery"]["conceptual"])

    def test_required_subject_capabilities_use_one_generic_scheduler_and_reducer(self):
        def source(source_id):
            return {
                "source_id": source_id,
                "authority": "teacher_material",
                "locator": "section 1",
            }

        syllabus = {
            "schema_version": 2,
            "learning_targets": [
                {"target_id": "math:limits", "title": "Limits", "prerequisites": [], "source_refs": [source("math:notes")]},
                {"target_id": "philosophy:argument", "title": "Argument", "prerequisites": [], "source_refs": [source("philosophy:notes")]},
                {"target_id": "security:dac-mac", "title": "DAC versus MAC", "prerequisites": [], "source_refs": [source("security:notes")]},
                {"target_id": "programming:code", "title": "Code reasoning", "prerequisites": [], "source_refs": [source("programming:notes")]},
            ],
            "assessment_capabilities": {
                "calculation": {"affected_dimensions": ["procedural"], "response_type": "numeric", "review_kind": "calculation"},
                "method_selection": {"affected_dimensions": ["conceptual"], "response_type": "choice", "review_kind": "method_selection"},
                "oral_argument": {"affected_dimensions": ["conceptual"], "response_type": "oral", "review_kind": "oral_answer"},
                "scenario_application": {"affected_dimensions": ["transfer"], "response_type": "scenario", "review_kind": "scenario"},
                "code_explanation": {"affected_dimensions": ["conceptual"], "response_type": "explanation", "review_kind": "explanation"},
                "testing_execution": {"affected_dimensions": ["procedural"], "response_type": "execution", "review_kind": "testing", "verifier_id": None},
            },
        }
        events = [
            {
                "schema_version": 2,
                "observation_id": capability_id,
                "target_id": target_id,
                "capability_id": capability_id,
                "task_id": f"task:{capability_id}",
                "task_type": task_type,
                "outcome": "correct",
                "assistance": {"levels_revealed": []},
                "error_tags": [],
                "source_refs": [source(f"{target_id}:notes")],
            }
            for target_id, capability_id, task_type in (
                ("math:limits", "calculation", "calculation"),
                ("math:limits", "method_selection", "method_selection"),
                ("math:limits", "transfer", "transfer"),
                ("philosophy:argument", "oral_argument", "oral_answer"),
                ("security:dac-mac", "scenario_application", "scenario"),
                ("programming:code", "code_explanation", "explanation"),
                ("programming:code", "testing_execution", "testing"),
                ("programming:code", "optional_executor", "testing"),
            )
        ]
        derived = reduce_learning_state({}, syllabus, events, {})
        self.assertGreater(derived["targets"]["math:limits"]["mastery"]["procedural"], 0)
        self.assertGreater(derived["targets"]["math:limits"]["mastery"]["conceptual"], 0)
        self.assertGreater(derived["targets"]["math:limits"]["mastery"]["transfer"], 0)
        self.assertGreater(derived["targets"]["philosophy:argument"]["mastery"]["conceptual"], 0)
        self.assertGreater(derived["targets"]["security:dac-mac"]["mastery"]["transfer"], 0)
        self.assertGreater(derived["targets"]["programming:code"]["mastery"]["conceptual"], 0)
        self.assertGreater(derived["targets"]["programming:code"]["mastery"]["procedural"], 0)
        self.assertIn("optional_executor", derived["unmapped_capability_events"])
        self.assertEqual(0, derived["targets"]["programming:code"]["mastery"]["transfer"])
        queue = build_review_queue(
            events,
            derived["targets"],
            {},
            __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            syllabus,
        )
        selected = select_next_activity(
            syllabus,
            derived["targets"],
            queue["items"],
            {},
            __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            25,
        )
        self.assertIn(
            selected["concept_id"],
            {item["target_id"] for item in syllabus["learning_targets"]},
        )


if __name__ == "__main__":
    unittest.main()
