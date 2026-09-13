import sys
import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.reducer import reduce_learning_state  # noqa: E402
from exam_prep_lib.scheduler import select_next_activity  # noqa: E402
from exam_prep_lib.storage import StudyStore  # noqa: E402
from exam_prep import main  # noqa: E402


SOURCE_REF = {
    "source_id": "teacher:algebra",
    "authority": "teacher_material",
    "locator": "page 1",
}


def syllabus():
    return {
        "schema_version": 2,
        "learning_targets": [
            {
                "target_id": "algebra:linear",
                "title": "Linear equations",
                "prerequisites": [],
                "importance": 0.9,
                "source_refs": [SOURCE_REF],
            }
        ],
        "source_refs": [SOURCE_REF],
        "assessment_capabilities": {},
    }


def event():
    return {
        "schema_version": 2,
        "observation_id": "obs-target-only",
        "target_id": "algebra:linear",
        "task_id": "task-target-only",
        "capability_id": "independent_problem",
        "task_type": "independent_problem",
        "outcome": "correct",
        "assistance": {"levels_revealed": []},
        "error_tags": [],
        "diagnostic_confidence": "high",
        "source_refs": [SOURCE_REF],
    }


class TargetOnlyRuntimeTests(unittest.TestCase):
    def test_reducer_and_scheduler_use_learning_targets_as_canonical_ids(self):
        reduced = reduce_learning_state({}, syllabus(), [event()], {})
        self.assertIn("algebra:linear", reduced["concepts"])
        self.assertGreater(reduced["concepts"]["algebra:linear"]["mastery"]["procedural"], 0)
        selected = select_next_activity(
            syllabus(),
            reduced["concepts"],
            {"items": {}},
            {},
            datetime.now(timezone.utc),
            25,
        )
        self.assertEqual("algebra:linear", selected["concept_id"])

    def test_v2_observation_is_stored_with_target_id_without_fabricating_concept_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StudyStore.for_exam_prep(Path(tmp))
            result = store.append_observation(event(), "session-1", "2026-09-13T10:00:00+00:00", None, None)
            self.assertTrue(result.appended)
            stored = store.read_complete_observations()[0]
            self.assertEqual("algebra:linear", stored["target_id"])
            self.assertNotIn("concept_id", stored)

    def test_validate_accepts_a_v2_target_only_syllabus(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            syllabus_path = root / "syllabus.json"
            syllabus_path.write_text(json.dumps(syllabus()), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, main(["--workspace", str(root), "init"]))
                self.assertEqual(0, main(["--workspace", str(root), "load-syllabus", str(syllabus_path)]))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(0, main(["--workspace", str(root), "validate"]))
            report = json.loads(output.getvalue())
            checks = {item["name"]: item for item in report["checks"]}
            self.assertEqual("ok", checks["schema_versions"]["status"])
            self.assertEqual("ok", checks["syllabus_source_refs"]["status"])


if __name__ == "__main__":
    unittest.main()
