import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAM_PREP = ROOT / "skill" / "exam-prep"
sys.path.insert(0, str(EXAM_PREP / "scripts"))

from exam_prep_lib.source_evidence import ingest_source_evidence  # noqa: E402
from exam_prep_lib.source_provider import normalize_source_evidence  # noqa: E402
from exam_prep_lib.storage import StudyStore  # noqa: E402


class NotebookLmBoundaryTests(unittest.TestCase):
    def test_host_envelope_is_normalized_without_mcp_in_python_core(self):
        envelope = normalize_source_evidence(
            {
                "provider_id": "notebooklm",
                "status": "ok",
                "evidence": [
                    {
                        "source_ref": {
                            "source_id": "notebook:limits",
                            "authority": "teacher_material",
                            "locator": "notebook citation 3",
                        },
                        "excerpt": "A limit describes local behaviour.",
                    }
                ],
                "diagnostics": [],
            }
        )
        self.assertEqual("notebooklm", envelope.provider_id)
        self.assertEqual("notebook:limits", envelope.evidence[0].source_ref.source_id)
        self.assertNotIn("learner", envelope.to_mapping())
        for path in (EXAM_PREP / "scripts" / "exam_prep_lib").glob("*.py"):
            self.assertNotIn("mcp", path.read_text(encoding="utf-8").casefold(), path.name)

    def test_notebooklm_absence_or_failure_is_graceful_and_never_learner_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StudyStore.for_exam_prep(Path(tmp))
            result = ingest_source_evidence(
                store,
                {
                    "provider_id": "notebooklm",
                    "status": "unavailable",
                    "evidence": [],
                    "diagnostics": ["host capability absent"],
                },
            )
            self.assertEqual(0, result.appended)
            self.assertEqual([], store.read_source_evidence())
            self.assertFalse((store.state_path / "learner.json").exists())

    def test_skill_describes_host_detection_normalization_and_ingestion(self):
        skill = (EXAM_PREP / "SKILL.md").read_text(encoding="utf-8").casefold()
        reference = (EXAM_PREP / "references" / "notebooklm-mcp.md").read_text(encoding="utf-8").casefold()
        for text in (skill, reference):
            for phrase in ("optional", "agent host", "normalizes", "sourceevidenceenvelope", "canonical learner state"):
                self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
