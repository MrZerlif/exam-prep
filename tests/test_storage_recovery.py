import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


sys.path.insert(0, "scripts")

from math_study_lib.storage import ObservationConflict, StudyStore  # noqa: E402


def proposal(observation_id="obs-1", outcome="correct"):
    return {
        "schema_version": 1,
        "observation_id": observation_id,
        "concept_id": "chain_rule",
        "task_id": "transfer-1",
        "task_type": "transfer",
        "outcome": outcome,
        "assistance": {
            "requested": False,
            "levels_revealed": [],
            "scaffold_types": [],
            "partial_transformation_shown": False,
            "full_solution_viewed": False,
        },
        "error_tags": [],
        "diagnostic_confidence": "high",
        "learner_self_confidence": "medium",
        "learner_explanation": "Проверил внутреннюю производную.",
        "source_refs": ["official-exam-list:q7"],
    }


class StorageRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = StudyStore(Path(self.temp_dir.name))
        self.store.initialize()
        self.now = datetime(2026, 9, 13, 15, 30, tzinfo=timezone.utc).isoformat()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_append_enriches_event_and_preserves_append_order(self):
        result = self.store.append_observation(
            proposal(), "session-1", self.now, 90, 22
        )
        events = self.store.read_complete_observations()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0], result.canonical_event)
        self.assertEqual(events[0]["session_id"], "session-1")
        self.assertEqual(events[0]["recorded_at"], self.now)
        self.assertEqual(events[0]["expected_seconds"], 90)
        self.assertEqual(events[0]["elapsed_seconds"], 22)

    def test_identical_observation_retry_is_idempotent(self):
        first = self.store.append_observation(
            proposal(), "session-1", self.now, 90, 22
        )
        second = self.store.append_observation(
            proposal(), "session-1", self.now, 90, 22
        )
        self.assertEqual(first.observation_id, second.observation_id)
        self.assertEqual(self.store.read_complete_observations(), [first.canonical_event])
        self.assertFalse(second.appended)

    def test_divergent_observation_retry_is_conflict(self):
        self.store.append_observation(proposal(), "session-1", self.now, 90, 22)
        with self.assertRaises(ObservationConflict):
            self.store.append_observation(
                proposal(outcome="incorrect"), "session-1", self.now, 90, 22
            )
        self.assertEqual(len(self.store.read_complete_observations()), 1)

    def test_partial_final_jsonl_line_is_ignored(self):
        self.store.append_observation(
            proposal(), "session-1", self.now, 90, 22
        )
        with self.store.observations_path.open("ab") as handle:
            handle.write(b'{"observation_id":"partial"')
        self.assertEqual(len(self.store.read_complete_observations()), 1)
        self.assertTrue(self.store.read_log_diagnostics()["partial_final_line"])

    def test_revision_manifest_and_corrupt_pointer_recovery(self):
        manifest = self.store.commit_revision(
            {"schema_version": 1, "derived_from_revision": 1, "concepts": {}},
            {"schema_version": 1, "session_id": "session-1", "phase": "study", "pending_action": "solve"},
            {"schema_version": 1, "updated_at": self.now, "preferences": {}, "stable_patterns": []},
        )
        self.assertEqual(manifest.revision, 1)
        self.assertTrue((self.store.revisions_path / "000001" / "manifest.json").exists())
        self.store.current_path.write_text("{not-json", encoding="utf-8")
        recovered = self.store.recover()
        self.assertEqual(recovered.manifest.revision, 1)


if __name__ == "__main__":
    unittest.main()
