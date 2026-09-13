import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, "skill/exam-prep/scripts")

from exam_prep import main  # noqa: E402
from exam_prep_lib.storage import StudyStore  # noqa: E402


ROOT = Path(__file__).parents[1]
SYLLABUS = ROOT / "skill" / "exam-prep" / "examples" / "example-syllabus.json"


def proposal(observation_id, concept_id="chain_rule", outcome="correct"):
    return {
        "schema_version": 1,
        "observation_id": observation_id,
        "concept_id": concept_id,
        "task_id": observation_id,
        "task_type": "independent_problem",
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
        "source_refs": ["teacher:worksheet-1"],
    }


class ValidateDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--workspace", str(self.root), *args])
        self.assertEqual(code, 0, output.getvalue())
        return json.loads(output.getvalue())

    def record(self, item):
        path = self.root / f"{item['observation_id']}.json"
        path.write_text(json.dumps(item), encoding="utf-8")
        return self.cli("record-observation", str(path))

    def ready(self):
        self.cli("init")
        self.cli("load-syllabus", str(SYLLABUS))
        self.cli("start")

    def test_healthy_workspace_reports_valid_with_a_real_checklist(self):
        self.ready()
        self.record(proposal("obs-1"))
        report = self.cli("validate")
        self.assertEqual(report["status"], "valid")
        self.assertEqual(report["error_count"], 0)
        self.assertGreaterEqual(len(report["checks"]), 8)

    def test_detects_observation_referencing_unknown_concept(self):
        self.ready()
        store = StudyStore(self.root)
        store.append_observation(
            proposal("obs-orphan", concept_id="not_in_syllabus"),
            "session-x",
            "2026-09-13T10:00:00+00:00",
            None,
            None,
        )
        report = self.cli("validate")
        names = {c["name"]: c for c in report["checks"]}
        self.assertEqual(names["observation_concept_ids_known"]["status"], "warning")

    def test_detects_hash_mismatched_revision(self):
        self.ready()
        self.record(proposal("obs-1"))
        store = StudyStore(self.root)
        latest = sorted(store.revisions_path.iterdir())[-1]
        (latest / "concepts.json").write_text(
            json.dumps({"schema_version": 1, "derived_from_revision": 1, "concepts": {}}),
            encoding="utf-8",
        )
        report = self.cli("validate")
        names = {c["name"]: c for c in report["checks"]}
        self.assertEqual(names["revision_manifests_and_hashes"]["status"], "warning")

    def test_detects_torn_final_observation_line(self):
        self.ready()
        self.record(proposal("obs-1"))
        store = StudyStore(self.root)
        with store.observations_path.open("ab") as handle:
            handle.write(b'{"observation_id":"partial"')
        report = self.cli("validate")
        names = {c["name"]: c for c in report["checks"]}
        self.assertEqual(names["observations_jsonl_readable"]["status"], "warning")


if __name__ == "__main__":
    unittest.main()
