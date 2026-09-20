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


if __name__ == "__main__":
    unittest.main()
