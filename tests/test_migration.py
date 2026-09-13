import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.migration import migrate_legacy_workspace  # noqa: E402


class MigrationTests(unittest.TestCase):
    def test_explicit_migration_rewrites_ids_and_leaves_legacy_state_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state"
            state.mkdir()
            (state / "course.json").write_text(
                json.dumps({"schema_version": 1, "course_id": "legacy-course"}),
                encoding="utf-8",
            )
            (state / "syllabus.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "concepts": {
                            "limits": {"title": "Limits", "prerequisites": []},
                            "derivatives": {
                                "title": "Derivatives",
                                "prerequisites": ["limits"],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            (state / "learner.json").write_text("{}", encoding="utf-8")
            (state / "session.json").write_text("{}", encoding="utf-8")
            observation = {
                "schema_version": 1,
                "observation_id": "legacy-obs-1",
                "concept_id": "derivatives",
                "task_id": "legacy-task",
                "task_type": "independent_problem",
                "outcome": "correct",
                "assistance": {"levels_revealed": []},
                "error_tags": [],
                "diagnostic_confidence": "high",
                "source_refs": ["teacher:week-1"],
            }
            (state / "observations.jsonl").write_text(
                json.dumps(observation) + chr(10), encoding="utf-8"
            )
            before = {path: path.read_bytes() for path in state.iterdir()}

            result = migrate_legacy_workspace(root)
            self.assertTrue(result.migrated)
            self.assertEqual("legacy:math-study:limits", result.id_map["limits"])
            migrated_syllabus = json.loads(
                (root / ".exam-prep" / "syllabus.json").read_text(encoding="utf-8")
            )
            migrated_derivative = migrated_syllabus["concepts"]["legacy:math-study:derivatives"]
            self.assertEqual(
                ["legacy:math-study:limits"],
                migrated_derivative["prerequisites"],
            )
            self.assertEqual(
                "limits",
                migrated_syllabus["concepts"]["legacy:math-study:limits"]["legacy_concept_id"],
            )
            migrated_event = json.loads(
                (root / ".exam-prep" / "observations.jsonl").read_text(encoding="utf-8")
            )
            self.assertEqual("legacy:math-study:derivatives", migrated_event["target_id"])
            self.assertEqual("derivatives", migrated_event["legacy_concept_id"])
            self.assertEqual("legacy_unfrozen", migrated_event["assessment_integrity"])
            self.assertNotIn("spec_hash", migrated_event)
            self.assertTrue(isinstance(migrated_event["source_refs"][0], dict))
            self.assertEqual(before, {path: path.read_bytes() for path in state.iterdir()})

            repeat = migrate_legacy_workspace(root)
            self.assertFalse(repeat.migrated)
            self.assertEqual(result.id_map, repeat.id_map)


if __name__ == "__main__":
    unittest.main()
