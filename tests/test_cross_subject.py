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
            "concepts": {
                "algebra:linear": {
                    "title": "Linear equations",
                    "prerequisites": [],
                    "source_refs": [{"source_id": "algebra:notes", "authority": "teacher_material"}],
                },
                "physics:newton-2": {
                    "title": "Newton's second law",
                    "prerequisites": [],
                    "source_refs": [{"source_id": "physics:notes", "authority": "teacher_material"}],
                },
            },
        }
        events = [
            {
                "concept_id": "algebra:linear",
                "task_type": "independent_problem",
                "outcome": "correct",
                "assistance": {"levels_revealed": []},
            },
            {
                "concept_id": "physics:newton-2",
                "task_type": "transfer",
                "outcome": "correct",
                "assistance": {"levels_revealed": []},
            },
        ]
        derived = reduce_learning_state({}, syllabus, events, {})
        self.assertGreater(
            derived["concepts"]["algebra:linear"]["mastery"]["procedural"], 0
        )
        self.assertGreater(
            derived["concepts"]["physics:newton-2"]["mastery"]["transfer"], 0
        )
        reviews = build_review_queue(
            events,
            derived["concepts"],
            {},
            __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            syllabus,
        )
        selected = select_next_activity(
            syllabus, derived["concepts"], reviews["items"], {}, __import__("datetime").datetime.now(__import__("datetime").timezone.utc), 25
        )
        self.assertIn(selected["concept_id"], {"algebra:linear", "physics:newton-2"})


if __name__ == "__main__":
    unittest.main()
