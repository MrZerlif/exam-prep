import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_adapters.local_materials.material_index import ingest_materials, load_material_index
from exam_prep_lib.storage import StudyStore


class MaterialIndexTests(unittest.TestCase):
    def test_lightweight_mode_writes_index_without_evidence(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            materials = root / "materials"
            materials.mkdir()
            (materials / "lecture_01.md").write_text("Тема 1\nDerivative", encoding="utf-8")
            store = StudyStore.for_exam_prep(root)
            result = ingest_materials(materials, store, mode="lightweight")
            self.assertEqual("lightweight", result["mode"])
            self.assertTrue((root / ".exam-prep" / "material_index.json").exists())
            self.assertEqual([], store.read_source_evidence())
            self.assertEqual("lecture_01.md", load_material_index(root / ".exam-prep")["entries"][0]["relative_path"])

    def test_full_mode_is_deterministic_and_hydrates_once(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            materials = root / "materials"
            materials.mkdir()
            (materials / "hw2.md").write_text("Задача 1\nCompute x", encoding="utf-8")
            store = StudyStore.for_exam_prep(root)
            first = ingest_materials(materials, store, mode="full")
            second = ingest_materials(materials, store, mode="full")
            self.assertEqual(first["index"], second["index"])
            self.assertEqual(1, len(store.read_source_evidence()))
            self.assertEqual(0, second["appended"])


if __name__ == "__main__":
    unittest.main()
