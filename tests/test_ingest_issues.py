import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.ingest_issues import IngestIssue


class IngestIssueTests(unittest.TestCase):
    def test_issue_is_json_ready_and_preserves_contract(self):
        issue = IngestIssue("missing_answer", "hw2.md#q1", "no solution", "gap")
        self.assertEqual(
            {
                "kind": "missing_answer",
                "source_id": "hw2.md#q1",
                "detail": "no solution",
                "severity": "gap",
            },
            issue.to_mapping(),
        )

    def test_invalid_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            IngestIssue("not-a-kind", None, "bad", "info")

    def test_new_extraction_issue_kinds_are_valid(self):
        for kind in (
            "extraction_anomaly",
            "no_questions_extracted",
            "unclassified_source",
            "unsupported_language",
            "low_confidence_question",
        ):
            self.assertEqual(kind, IngestIssue(kind, "source.md", "detail", "gap").kind)


if __name__ == "__main__":
    unittest.main()
