import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.capabilities import AssessmentCapability  # noqa: E402
from exam_prep_lib.optimizer import rank_source_aware_targets  # noqa: E402
from exam_prep_lib.verifier_registry import VerifierRegistry  # noqa: E402


class VerifierAndOptimizerTests(unittest.TestCase):
    def test_verifier_resolution_is_optional_and_unknown_is_unavailable(self):
        registry = VerifierRegistry()
        registry.register("always-pass", lambda request: {"status": "verified"})
        self.assertEqual({"status": "verified"}, registry.verify("always-pass", {}))
        self.assertIsNone(registry.resolve("missing"))
        self.assertEqual(
            {"status": "unavailable", "reason": "no verifier registered"},
            registry.verify("missing", {}),
        )

    def test_source_aware_optimizer_exposes_coverage_and_authority(self):
        ranked = rank_source_aware_targets(
            {
                "concepts": {
                    "limits": {
                        "importance": 0.9,
                        "frequency": 0.9,
                        "expected_points": 10,
                        "source_refs": [
                            {
                                "source_id": "teacher:week-1",
                                "authority": "teacher_material",
                            }
                        ],
                    },
                    "derivatives": {
                        "importance": 0.8,
                        "frequency": 0.8,
                        "expected_points": 8,
                        "source_refs": [],
                    },
                }
            },
            {"limits": {"mastery": {"conceptual": 0.1}}, "derivatives": {}},
            {"limits": {}, "derivatives": {}},
            {},
            datetime.now(timezone.utc),
            25,
            available_source_ids={"teacher:week-1"},
        )
        self.assertEqual("derivatives", ranked[0]["target_id"])
        self.assertTrue(ranked[0]["coverage_gap"])
        self.assertEqual("limits", ranked[1]["target_id"])
        self.assertEqual(5, ranked[1]["source_authority_rank"])


if __name__ == "__main__":
    unittest.main()
