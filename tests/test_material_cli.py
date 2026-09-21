import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep import _parser, main
from exam_prep_lib.storage import StudyStore


class MaterialCliTests(unittest.TestCase):
    def call(self, root: Path, *args: str) -> dict:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--workspace", str(root), *args])
        self.assertEqual(0, code, output.getvalue())
        return json.loads(output.getvalue())

    def test_ingest_and_hydrate_commands(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            materials = root / "materials"
            materials.mkdir()
            (materials / "lecture.md").write_text("Topic\nDefinition", encoding="utf-8")
            self.call(root, "init")
            indexed = self.call(root, "ingest-materials", str(materials), "--mode", "lightweight")
            self.assertEqual("lightweight", indexed["mode"])
            self.assertEqual([], StudyStore.for_exam_prep(root).read_source_evidence())
            hydrated = self.call(root, "hydrate-source", "lecture.md#p1", "--materials-dir", str(materials))
            self.assertEqual(1, hydrated["appended"])
            repeated = self.call(root, "hydrate-source", "lecture.md#p1", "--materials-dir", str(materials))
            self.assertEqual(0, repeated["appended"])


    def test_ingest_parser_rejects_include_unclassified(self):
        with self.assertRaises(SystemExit) as raised:
            _parser().parse_args([
                "ingest-materials", "materials", "--include-unclassified",
            ])
        self.assertEqual(2, raised.exception.code)

    def test_draft_parser_still_accepts_include_unclassified(self):
        args = _parser().parse_args([
            "draft-assessments", "input.json", "--out", "draft.json",
            "--include-unclassified",
        ])
        self.assertTrue(args.include_unclassified)
if __name__ == "__main__":
    unittest.main()
