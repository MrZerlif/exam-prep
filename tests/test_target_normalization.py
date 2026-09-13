import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "math-study" / "scripts"))

from math_study_lib.target_normalization import normalize_event, normalize_syllabus


class TargetNormalizationTests(unittest.TestCase):
    def test_legacy_concepts_become_learning_targets_without_losing_aliases(self):
        normalized = normalize_syllabus(
            {
                "schema_version": 1,
                "concepts": {
                    "limits": {"title": "Limits", "prerequisites": []},
                    "derivatives": {"title": "Derivatives", "prerequisites": ["limits"]},
                },
            }
        )
        self.assertEqual("limits", normalized.aliases["limits"])
        self.assertEqual("derivatives", normalized.aliases["derivatives"])
        self.assertEqual({"limits", "derivatives"}, set(normalized.targets))
        self.assertEqual(["limits"], normalized.targets["derivatives"]["prerequisites"])

    def test_target_id_is_canonical_and_old_event_ids_are_normalized(self):
        normalized = normalize_syllabus(
            {
                "schema_version": 2,
                "learning_targets": [
                    {"target_id": "algebra:linear", "title": "Linear equations"}
                ],
            }
        )
        event = normalize_event(
            {"concept_id": "algebra:linear", "outcome": "correct"}, normalized
        )
        self.assertEqual("algebra:linear", event["target_id"])
        self.assertNotIn("concept_id", event)

    def test_unknown_event_target_is_diagnostic_but_not_silently_rewritten(self):
        normalized = normalize_syllabus({"schema_version": 2, "learning_targets": []})
        event = normalize_event(
            {"target_id": "missing", "outcome": "correct"}, normalized
        )
        self.assertEqual("missing", event["target_id"])
        self.assertIn("unknown_target_id", event["diagnostics"])


if __name__ == "__main__":
    unittest.main()
