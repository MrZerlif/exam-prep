import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep import main


class AssessmentDraftCliTests(unittest.TestCase):
    def test_draft_then_finalize(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            materials = root / "materials"
            materials.mkdir()
            (materials / "hw2.md").write_text("Задача 1\nCompute x", encoding="utf-8")
            solution = materials / "hw2_resheniya.md"
            solution.write_text("Решение 1\nx=2", encoding="utf-8")
            draft_path = root / "draft.json"
            final_path = root / "mint.json"
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, main(["draft-assessments", str(materials), "--out", str(draft_path)]))
            draft = json.loads(draft_path.read_text(encoding="utf-8"))
            self.assertIsNone(draft["assessments"][0]["target_id"])
            target_map = root / "targets.json"
            target_map.write_text(json.dumps({draft["assessments"][0]["question_id"]: "target-x"}), encoding="utf-8")
            with redirect_stdout(output):
                self.assertEqual(0, main(["finalize-assessment-draft", str(draft_path), "--target-map", str(target_map), "--out", str(final_path)]))
            package = json.loads(final_path.read_text(encoding="utf-8"))
            self.assertEqual("target-x", package["assessments"][0]["target_id"])


if __name__ == "__main__":
    unittest.main()
