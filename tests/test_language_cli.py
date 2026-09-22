import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep import main


class LanguageCliTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.materials = self.root / "materials"
        self.materials.mkdir()

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--workspace", str(self.root), *args])
        self.assertEqual(0, code, output.getvalue())
        return json.loads(output.getvalue())

    def test_configured_language_is_reported_in_status(self):
        self.run_cli("init", "--language", "de")
        status = self.run_cli("status")
        self.assertEqual(
            {"value": "de", "source": "configured", "confidence": 1.0},
            status["course"]["language"],
        )

    def test_detection_runs_once_and_does_not_switch_course_language(self):
        source = self.materials / "questions.txt"
        source.write_text("Die Aufgabe und der Beweis sind in diesem Kapitel.\n", encoding="utf-8")
        self.run_cli("init")
        self.run_cli("ingest-materials", str(self.materials))
        course_path = self.root / ".exam-prep" / "course.json"
        first = json.loads(course_path.read_text(encoding="utf-8"))
        self.assertEqual("de", first["language"])
        self.assertEqual("detected", first["language_source"])

        source.write_text("The task and the proof are in this chapter.\n", encoding="utf-8")
        self.run_cli("ingest-materials", str(self.materials))
        second = json.loads(course_path.read_text(encoding="utf-8"))
        self.assertEqual(first["language"], second["language"])
        self.assertEqual(first["language_source"], second["language_source"])

    def test_failed_detection_is_retried_when_materials_grow(self):
        (self.materials / "notes.md").write_text("# notes\n", encoding="utf-8")
        self.run_cli("init")
        self.run_cli("ingest-materials", str(self.materials))
        course_path = self.root / ".exam-prep" / "course.json"
        first = json.loads(course_path.read_text(encoding="utf-8"))
        self.assertIsNone(first["language"])
        self.assertTrue(first["language_detection_attempted"])

        (self.materials / "chapter.txt").write_text(
            "The task and the proof are in this chapter. We will use the "
            "definition in the course and in the exam.\n",
            encoding="utf-8",
        )
        self.run_cli("ingest-materials", str(self.materials))
        second = json.loads(course_path.read_text(encoding="utf-8"))
        self.assertEqual("en", second["language"])
        self.assertEqual("detected", second["language_source"])

    def test_each_source_keeps_its_own_detected_language(self):
        german = self.materials / "german.txt"
        english = self.materials / "english.txt"
        german.write_text("Die Aufgabe und der Beweis sind in diesem Kapitel.\n", encoding="utf-8")
        english.write_text("The task and the proof are in this chapter.\n", encoding="utf-8")
        self.run_cli("init", "--language", "ru")
        result = self.run_cli("ingest-materials", str(self.materials))
        by_path = {entry["relative_path"]: entry for entry in result["index"]["entries"]}
        self.assertEqual("de", by_path["german.txt"]["language"])
        self.assertEqual("en", by_path["english.txt"]["language"])
        self.assertEqual("detected", by_path["german.txt"]["language_source"])
        status = self.run_cli("status")
        self.assertEqual({"de": 1, "en": 1}, status["course"]["source_languages"])

    def test_hydrate_source_uses_course_and_per_source_language(self):
        german = self.materials / "german.txt"
        english = self.materials / "english.txt"
        german.write_text("Die Aufgabe 1\nDer Beweis folgt hier.\n", encoding="utf-8")
        english.write_text("The task 1\nThe proof follows here.\n", encoding="utf-8")
        self.run_cli("init", "--language", "ru")

        self.run_cli(
            "hydrate-source",
            "german.txt",
            "--materials-dir",
            str(self.materials),
        )
        evidence_path = self.root / ".exam-prep" / "source_evidence.jsonl"
        evidence = [json.loads(line) for line in evidence_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual("de", evidence[0]["source_ref"]["location"]["language"])

    def test_dry_run_does_not_persist_auto_detected_course_language(self):
        (self.materials / "questions.txt").write_text(
            "Die Aufgabe und der Beweis sind in diesem Kapitel.\n",
            encoding="utf-8",
        )
        self.run_cli("init")
        course_path = self.root / ".exam-prep" / "course.json"
        before = course_path.read_bytes()

        result = self.run_cli("ingest-materials", str(self.materials), "--dry-run")

        self.assertEqual("de", result["language"]["value"])
        self.assertEqual(before, course_path.read_bytes())
        course = json.loads(course_path.read_text(encoding="utf-8"))
        self.assertFalse(course["language_detection_attempted"])

    def test_unclassified_summary_uses_the_source_language(self):
        (self.materials / "unknown.txt").write_text(
            "Die unbekannte Darstellung bleibt ohne bekannte Überschrift.\n",
            encoding="utf-8",
        )
        self.run_cli("init", "--language", "ru")

        result = self.run_cli("ingest-materials", str(self.materials))

        self.assertEqual("de", result["index"]["unclassified"]["language"])


if __name__ == "__main__":
    unittest.main()
