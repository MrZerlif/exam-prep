import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_adapters.local_materials.figures import (
    analyze_pdf,
    cluster,
    extract_office_media,
    find_text_top,
    safe_stem,
)
from exam_prep_adapters.local_materials.pdf_backend import has_pdfium


class FigureTests(unittest.TestCase):
    def test_cluster_joins_near_boxes_only(self):
        self.assertEqual(1, len(cluster([(0, 0, 10, 10), (12, 0, 20, 10)], gap=3)))
        self.assertEqual(2, len(cluster([(0, 0, 10, 10), (20, 0, 30, 10)], gap=3)))

    def test_safe_stem_never_keeps_path_separators(self):
        value = safe_stem("../C:\\secret\\answer.png")
        self.assertNotIn("..", value)
        self.assertNotIn("/", value)
        self.assertNotIn("\\", value)
        self.assertNotIn(":", value)

    def test_office_media_is_extracted_with_hash_name(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "figures.docx"
            out = Path(directory) / "assets"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("word/media/image1.png", b"png-bytes")
            assets = extract_office_media(path, out, role="reference", source_ref="figures.docx#p1")
            self.assertEqual(1, len(assets))
            self.assertTrue(Path(assets[0]["path"]).exists())
            self.assertEqual("reference", assets[0]["role"])
            self.assertIsNone(assets[0]["assessment_id"])

    def test_pdfium_probe_is_safe(self):
        self.assertIsInstance(has_pdfium(), bool)
        if not has_pdfium():
            pages, issues = analyze_pdf("missing.pdf")
            self.assertEqual((), pages)
            self.assertTrue(any(issue.kind == "unsupported_page" for issue in issues))

    def test_find_text_top_ignores_scan_cover(self):
        self.assertEqual(20.0, find_text_top(((0, 20, 10, 30), (0, 95, 10, 100)), page_height=100))


if __name__ == "__main__":
    unittest.main()
