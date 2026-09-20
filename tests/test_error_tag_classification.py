import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.defaults import ERROR_TAG_CLASS, classify_error_tag
from exam_prep_lib.reducer import MISTAKE_SUMMARIES
from exam_prep_lib.schema_validation import (
    SchemaError,
    validate_observation_proposal,
)


def proposal_with_tag(tag):
    return {
        "schema_version": 2,
        "observation_id": "obs-tag-contract",
        "target_id": "target-1",
        "task_id": "task-1",
        "capability_id": "independent_problem",
        "task_type": "independent_problem",
        "outcome": "incorrect",
        "assistance": {
            "requested": False,
            "levels_revealed": [],
            "scaffold_types": [],
            "partial_transformation_shown": False,
            "full_solution_viewed": False,
        },
        "error_tags": [tag],
        "diagnostic_confidence": "high",
        "source_refs": [],
    }


class ErrorTagClassificationTests(unittest.TestCase):
    def test_classification_covers_all_builtin_mistakes(self):
        self.assertEqual(set(ERROR_TAG_CLASS), set(MISTAKE_SUMMARIES))
        self.assertTrue(set(ERROR_TAG_CLASS.values()) <= {"understanding", "execution"})

    def test_known_and_unknown_tags_are_classified(self):
        self.assertEqual("understanding", classify_error_tag("conceptual_error"))
        self.assertEqual("execution", classify_error_tag("careless_error"))
        self.assertEqual("other", classify_error_tag("new_open_error_tag"))

    def test_unknown_string_is_valid_v2_tag(self):
        validate_observation_proposal(proposal_with_tag("new_open_error_tag"))

    def test_non_string_tag_is_rejected_by_proposal_validation(self):
        with self.assertRaises(SchemaError):
            validate_observation_proposal(proposal_with_tag(123))


if __name__ == "__main__":
    unittest.main()
