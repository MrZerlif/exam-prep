import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.curriculum import build_syllabus_from_proposal  # noqa: E402


class W2CurriculumTests(unittest.TestCase):
    def test_target_source_locators_are_preserved_per_target(self):
        proposal = {
            "schema_version": 2,
            "proposal_id": "locators",
            "source_refs": [
                {"source_id": "book:calculus", "locator": "course overview"}
            ],
            "learning_targets": [
                {
                    "target_id": "definition",
                    "title": "Definition",
                    "prerequisites": [],
                    "source_refs": [
                        {"source_id": "book:calculus", "locator": "page 12, paragraph 2"}
                    ],
                },
                {
                    "target_id": "example",
                    "title": "Example",
                    "prerequisites": [],
                    "source_refs": [
                        {"source_id": "book:calculus", "locator": "page 18, example 4"}
                    ],
                },
            ],
            "assessment_capabilities": [],
            "exam_questions": [],
        }

        syllabus = build_syllabus_from_proposal(proposal)
        targets = {item["target_id"]: item for item in syllabus["learning_targets"]}

        self.assertEqual("page 12, paragraph 2", targets["definition"]["source_refs"][0]["locator"])
        self.assertEqual("page 18, example 4", targets["example"]["source_refs"][0]["locator"])
        self.assertEqual("book:calculus", targets["definition"]["source_refs"][0]["source_id"])


if __name__ == "__main__":
    unittest.main()
