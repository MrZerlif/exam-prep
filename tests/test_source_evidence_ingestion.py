import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.source_evidence import ingest_source_evidence  # noqa: E402
from exam_prep_lib.storage import StudyStore  # noqa: E402


class SourceEvidenceIngestionTests(unittest.TestCase):
    def test_normalized_evidence_is_persisted_idempotently(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = StudyStore.for_exam_prep(root)
            envelope = {
                "provider_id": "local",
                "status": "ok",
                "evidence": [
                    {
                        "source_ref": {
                            "source_id": "teacher:week-1",
                            "authority": "teacher_material",
                            "locator": "page 2",
                        },
                        "excerpt": "A limit describes local behaviour.",
                    }
                ],
                "diagnostics": [],
            }
            first = ingest_source_evidence(store, envelope)
            second = ingest_source_evidence(store, envelope)
            self.assertEqual(1, first.appended)
            self.assertEqual(0, second.appended)
            records = store.read_source_evidence()
            self.assertEqual(1, len(records))
            self.assertEqual("teacher:week-1", records[0]["source_ref"]["source_id"])
            self.assertEqual("local", records[0]["provider_id"])

    def test_unavailable_provider_is_recorded_as_diagnostic_without_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StudyStore.for_exam_prep(Path(tmp))
            result = ingest_source_evidence(
                store,
                {
                    "provider_id": "not-installed",
                    "status": "unavailable",
                    "evidence": [],
                    "diagnostics": ["capability absent"],
                },
            )
            self.assertEqual(0, result.appended)
            self.assertEqual(["capability absent"], result.diagnostics)
            self.assertEqual([], store.read_source_evidence())


if __name__ == "__main__":
    unittest.main()
