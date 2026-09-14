import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep import main  # noqa: E402


SYLLABUS = {
    "schema_version": 2,
    "learning_targets": [
        {
            "target_id": "limits",
            "title": "Limits",
            "prerequisites": [],
            "importance": 0.9,
            "frequency": 0.8,
            "expected_points": 10,
            "estimated_learning_minutes": 25,
            "source_refs": ["teacher:worksheet-1"],
        }
    ],
}


def proposal(observation_id):
    return {
        "schema_version": 2,
        "observation_id": observation_id,
        "target_id": "limits",
        "task_id": observation_id,
        "capability_id": "independent_problem",
        "task_type": "independent_problem",
        "outcome": "correct",
        "assistance": {
            "requested": False,
            "levels_revealed": [],
            "scaffold_types": [],
            "partial_transformation_shown": False,
            "full_solution_viewed": False,
        },
        "error_tags": [],
        "diagnostic_confidence": "high",
        "source_refs": [],
    }


class ExamBlueprintRevisionTests(unittest.TestCase):
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

    def record(self, observation_id):
        path = self.root / f"{observation_id}.json"
        path.write_text(json.dumps(proposal(observation_id)), encoding="utf-8")
        return self.cli("record-observation", str(path))

    def bump_exam_revision(self, revision, **exam_overrides):
        course_path = self.root / ".exam-prep" / "course.json"
        course = json.loads(course_path.read_text(encoding="utf-8"))
        course["exam"]["revision"] = revision
        course["exam"].update(exam_overrides)
        course_path.write_text(json.dumps(course), encoding="utf-8")

    def test_exam_format_changed_mid_prep_preserves_evidence_and_surfaces_a_diagnostic(self):
        syllabus_path = self.root / "syllabus.json"
        syllabus_path.write_text(json.dumps(SYLLABUS), encoding="utf-8")
        self.cli("init")
        self.cli("load-syllabus", str(syllabus_path))
        self.cli("start")

        self.record("obs-revision-1-a")
        self.record("obs-revision-1-b")

        status_before = self.cli("status")
        self.assertIsNone(status_before["blueprint_diagnostics"])
        evidence_before = status_before["targets"]["targets"]["limits"]["evidence"]
        self.assertEqual(2, evidence_before["independent_successes"])

        # The exam format changes mid-preparation: a new question_model and
        # a bumped revision, exactly the roadmap scenario.
        self.bump_exam_revision(2, question_model="problem_set")

        result = self.record("obs-revision-2-a")

        # Evidence is not discarded: readiness now reflects all three
        # observations, spanning both blueprint revisions.
        evidence_after = result["targets"]["targets"]["limits"]["evidence"]
        self.assertEqual(3, evidence_after["independent_successes"])

        status_after = self.cli("status")
        diagnostic = status_after["blueprint_diagnostics"]
        self.assertIsNotNone(diagnostic)
        self.assertEqual(2, diagnostic["current_exam_revision"])
        self.assertEqual(1, len(diagnostic["stale_revisions"]))
        stale = diagnostic["stale_revisions"][0]
        self.assertEqual(1, stale["exam_revision"])
        self.assertEqual(2, stale["observation_count"])
        self.assertTrue(stale["exam_hash"])
        self.assertNotEqual(diagnostic["current_exam_hash"], stale["exam_hash"])

        # `validate` shows the same fact as a warning, not a blocking error -
        # the workspace is still valid, just diagnosable.
        report = self.cli("validate")
        self.assertEqual("valid", report["status"])
        checks_by_name = {c["name"]: c for c in report["checks"]}
        blueprint_check = checks_by_name["blueprint_revision_consistency"]
        self.assertEqual("warning", blueprint_check["status"])
        self.assertIn("revision 1", blueprint_check["detail"])
        self.assertIn("2", blueprint_check["detail"])

        # The revision manifest for the post-change commit records which
        # exam.revision was active when it was committed.
        revisions_dir = self.root / ".exam-prep" / "revisions"
        latest_revision_dir = max(
            (p for p in revisions_dir.iterdir() if p.is_dir() and p.name.isdigit()),
            key=lambda p: int(p.name),
        )
        manifest = json.loads((latest_revision_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(2, manifest["exam_revision"])

    def test_events_are_tagged_with_the_exam_revision_active_when_recorded(self):
        syllabus_path = self.root / "syllabus.json"
        syllabus_path.write_text(json.dumps(SYLLABUS), encoding="utf-8")
        self.cli("init")
        self.cli("load-syllabus", str(syllabus_path))
        self.cli("start")
        first = self.record("obs-tagged-1")
        self.assertEqual(1, first["event"]["exam_revision"])

        self.bump_exam_revision(5)
        second = self.record("obs-tagged-2")
        self.assertEqual(5, second["event"]["exam_revision"])

    def test_question_model_changed_without_bumping_revision_still_diagnoses(self):
        # 1.4's literal acceptance criterion: a hand-edit (or any bypass of
        # update-exam-blueprint) that changes question_model but forgets to
        # bump exam.revision must not silently defeat the diagnostic - the
        # whole point of invariant 3. Detection has to key on exam content
        # (exam_hash), not only the manually-maintained revision integer.
        syllabus_path = self.root / "syllabus.json"
        syllabus_path.write_text(json.dumps(SYLLABUS), encoding="utf-8")
        self.cli("init")
        self.cli("load-syllabus", str(syllabus_path))
        self.cli("start")
        self.record("obs-unbumped-1")

        course_path = self.root / ".exam-prep" / "course.json"
        course = json.loads(course_path.read_text(encoding="utf-8"))
        self.assertEqual(1, course["exam"]["revision"])
        course["exam"]["question_model"] = "problem_set"
        # revision is deliberately left at 1 - the exact mistake 1.4 guards
        # against.
        course_path.write_text(json.dumps(course), encoding="utf-8")

        self.record("obs-unbumped-2")

        status = self.cli("status")
        diagnostic = status["blueprint_diagnostics"]
        self.assertIsNotNone(diagnostic)
        self.assertEqual(1, diagnostic["current_exam_revision"])
        self.assertEqual(1, diagnostic["stale_revisions"][0]["exam_revision"])
        self.assertEqual(1, diagnostic["stale_revisions"][0]["observation_count"])

        report = self.cli("validate")
        checks_by_name = {c["name"]: c for c in report["checks"]}
        self.assertEqual("warning", checks_by_name["blueprint_revision_consistency"]["status"])

    def test_update_exam_blueprint_auto_bumps_revision(self):
        syllabus_path = self.root / "syllabus.json"
        syllabus_path.write_text(json.dumps(SYLLABUS), encoding="utf-8")
        self.cli("init")
        self.cli("load-syllabus", str(syllabus_path))
        self.cli("start")
        self.record("obs-before-update")

        patch_path = self.root / "exam-patch.json"
        patch_path.write_text(json.dumps({"question_model": "ticket_list", "delivery": "oral"}), encoding="utf-8")
        result = self.cli("update-exam-blueprint", str(patch_path))

        self.assertEqual(2, result["course"]["exam"]["revision"])
        self.assertEqual("ticket_list", result["course"]["exam"]["question_model"])
        self.assertEqual("oral", result["course"]["exam"]["delivery"])
        # Untouched fields survive the partial update.
        self.assertEqual("mixed", result["course"]["exam"]["format"])

        status = self.cli("status")
        self.assertEqual(2, status["course"]["exam"]["revision"])
        diagnostic = status["blueprint_diagnostics"]
        self.assertIsNotNone(diagnostic)
        self.assertEqual(1, diagnostic["stale_revisions"][0]["exam_revision"])

        # New evidence recorded after the update is tagged with the new
        # revision and stops being flagged as stale.
        self.record("obs-after-update")
        status_after = self.cli("status")
        self.assertEqual(
            1, status_after["blueprint_diagnostics"]["stale_revisions"][0]["observation_count"]
        )

    def test_update_exam_blueprint_rejects_a_manual_revision_field(self):
        syllabus_path = self.root / "syllabus.json"
        syllabus_path.write_text(json.dumps(SYLLABUS), encoding="utf-8")
        self.cli("init")
        self.cli("load-syllabus", str(syllabus_path))

        patch_path = self.root / "exam-patch-bad.json"
        patch_path.write_text(json.dumps({"revision": 99}), encoding="utf-8")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaises(ValueError):
                main(["--workspace", str(self.root), "update-exam-blueprint", str(patch_path)])

    def test_update_exam_blueprint_rejects_unknown_question_model(self):
        syllabus_path = self.root / "syllabus.json"
        syllabus_path.write_text(json.dumps(SYLLABUS), encoding="utf-8")
        self.cli("init")
        self.cli("load-syllabus", str(syllabus_path))

        patch_path = self.root / "exam-patch-invalid.json"
        patch_path.write_text(json.dumps({"question_model": "trivia_night"}), encoding="utf-8")
        with self.assertRaises(ValueError):
            main(["--workspace", str(self.root), "update-exam-blueprint", str(patch_path)])

    def test_update_exam_blueprint_is_a_no_op_when_nothing_changes(self):
        syllabus_path = self.root / "syllabus.json"
        syllabus_path.write_text(json.dumps(SYLLABUS), encoding="utf-8")
        self.cli("init")
        self.cli("load-syllabus", str(syllabus_path))

        patch_path = self.root / "exam-patch-noop.json"
        patch_path.write_text(json.dumps({"format": "mixed"}), encoding="utf-8")
        result = self.cli("update-exam-blueprint", str(patch_path))
        self.assertEqual(1, result["course"]["exam"]["revision"])
        self.assertFalse(result["changed"])

    def test_no_diagnostic_when_all_evidence_matches_the_current_revision(self):
        syllabus_path = self.root / "syllabus.json"
        syllabus_path.write_text(json.dumps(SYLLABUS), encoding="utf-8")
        self.cli("init")
        self.cli("load-syllabus", str(syllabus_path))
        self.cli("start")
        self.record("obs-clean-1")

        status = self.cli("status")
        self.assertIsNone(status["blueprint_diagnostics"])
        report = self.cli("validate")
        checks_by_name = {c["name"]: c for c in report["checks"]}
        self.assertEqual("ok", checks_by_name["blueprint_revision_consistency"]["status"])


if __name__ == "__main__":
    unittest.main()
