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
SYLLABUS = ROOT / "skill" / "exam-prep" / "examples" / "mathematics-regression-syllabus.json"


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

    def test_invalid_exam_timezone_is_named_exam_datetime_error(self):
        self.ready()
        course_path = self.root / ".exam-prep" / "course.json"
        course = json.loads(course_path.read_text(encoding="utf-8"))
        course["exam"] = {"date": "2026-09-14T10:00:00", "timezone": "+99:00"}
        course_path.write_text(json.dumps(course), encoding="utf-8")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--workspace", str(self.root), "validate"])
        report = json.loads(output.getvalue())
        names = {item["name"]: item for item in report["checks"]}
        self.assertEqual(1, code)
        self.assertEqual("error", names["exam_datetime"]["status"])
    def test_detects_observation_referencing_unknown_concept(self):
        self.ready()
        store = StudyStore.for_exam_prep(self.root)
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
        store = StudyStore.for_exam_prep(self.root)
        latest = sorted(store.revisions_path.iterdir())[-1]
        (latest / "targets.json").write_text(
            json.dumps({"schema_version": 2, "derived_from_revision": 1, "targets": {}, "aliases": {}}),
            encoding="utf-8",
        )
        report = self.cli("validate")
        names = {c["name"]: c for c in report["checks"]}
        self.assertEqual(names["revision_manifests_and_hashes"]["status"], "warning")

    def test_detects_torn_final_observation_line(self):
        self.ready()
        self.record(proposal("obs-1"))
        store = StudyStore.for_exam_prep(self.root)
        with store.observations_path.open("ab") as handle:
            handle.write(b'{"observation_id":"partial"')
        report = self.cli("validate")
        names = {c["name"]: c for c in report["checks"]}
        self.assertEqual(names["observations_jsonl_readable"]["status"], "warning")


    def test_detects_unknown_capability_dimension_in_existing_syllabus(self):
        self.ready()
        syllabus_path = self.root / ".exam-prep" / "syllabus.json"
        syllabus = json.loads(syllabus_path.read_text(encoding="utf-8"))
        syllabus["assessment_capabilities"] = {
            "custom": {"affected_dimensions": ["knowledge"]}
        }
        syllabus_path.write_text(json.dumps(syllabus), encoding="utf-8")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--workspace", str(self.root), "validate"])
        self.assertEqual(code, 1, output.getvalue())
        report = json.loads(output.getvalue())
        names = {c["name"]: c for c in report["checks"]}
        self.assertEqual(names["capability_dimensions"]["status"], "error")
        self.assertIn("unknown affected dimension", names["capability_dimensions"]["detail"])

class ExpectedTotalPointsDiagnosticTests(unittest.TestCase):
    """Workspaces still carrying the template 100 get a nudge, never a failure."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--workspace", str(self.root), *args])
        return json.loads(output.getvalue())

    def workspace(self, expected_total, points):
        materials = self.root / "materials"
        materials.mkdir(exist_ok=True)
        (materials / "klausur.txt").write_text(
            "\n".join(
                f"Aufgabe {index}) Berechnen Sie den Grenzwert. ({value} Punkte)"
                for index, value in enumerate(points, start=1)
            ),
            encoding="utf-8",
        )
        self.cli("init", "--language", "de")
        course_path = self.root / ".exam-prep" / "course.json"
        course = json.loads(course_path.read_text(encoding="utf-8"))
        course["exam"]["expected_total_points"] = expected_total
        course_path.write_text(json.dumps(course), encoding="utf-8")
        self.cli("ingest-materials", str(materials))
        return {check["name"]: check for check in self.cli("validate")["checks"]}

    def test_template_total_against_other_points_is_info_only(self):
        checks = self.workspace(100, (10, 10, 15, 25))
        check = checks["expected_total_points"]
        self.assertEqual("info", check["status"])
        self.assertIn("60", check["detail"])

    def test_info_does_not_make_the_workspace_invalid(self):
        checks = self.workspace(100, (10, 10, 15, 25))
        report = self.cli("validate")
        self.assertTrue(report["valid"])
        self.assertEqual(0, report["error_count"])
        self.assertNotIn(checks["expected_total_points"]["status"], {"error", "warning"})

    def test_matching_total_is_not_flagged(self):
        checks = self.workspace(100, (40, 60))
        self.assertEqual("ok", checks["expected_total_points"]["status"])

    def test_cleared_total_is_not_flagged(self):
        checks = self.workspace(None, (10, 10, 15, 25))
        self.assertEqual("ok", checks["expected_total_points"]["status"])


if __name__ == "__main__":
    unittest.main()