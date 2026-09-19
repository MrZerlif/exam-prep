import sys
import unittest
import zipfile
from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_adapters.local_materials.chapters import build_chapters
from exam_prep_adapters.local_materials.extractor import (
    ExtractedPage,
    classify,
    extract_sources,
    read_docx,
    strip_repeated_lines,
)
from exam_prep_adapters.local_materials.pdf_backend import pdf_backend
from exam_prep_adapters.local_materials.questions import extract_questions


class MaterialExtractorTests(unittest.TestCase):
    def test_docx_page_break_creates_two_pages(self):
        document = b'''<?xml version="1.0" encoding="UTF-8"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body><w:p><w:r><w:t>one</w:t></w:r></w:p>
          <w:p><w:r><w:br w:type="page"/></w:r></w:p>
          <w:p><w:r><w:t>two</w:t></w:r></w:p></w:body>
        </w:document>'''
        with TemporaryDirectory() as directory:
            path = Path(directory) / "lekciya_03.docx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("word/document.xml", document)
            pages = read_docx(path)
        self.assertEqual(("one", "two"), tuple(page.text for page in pages))

    def test_russian_kind_and_header_stripping(self):
        self.assertEqual("lecture", classify(Path("lekciya_03.pdf")))
        pages = (ExtractedPage(1, "header\nbody\nfooter"), ExtractedPage(2, "header\nnext\nfooter"))
        self.assertEqual("body", strip_repeated_lines(pages)[0].text)

    def test_chapters_are_natural_and_numbered(self):
        pages = [ExtractedPage(1, "Тема 2\nB"), ExtractedPage(2, "Тема 1\nA")]
        chapters = build_chapters([("b.md", pages[0]), ("a.md", pages[1])])
        self.assertEqual([1, 2], [chapter.number for chapter in chapters])

    def test_transliterated_material_names_are_classified(self):
        expected = {
            "dz-1.md": "homework",
            "ekzamen_2025.pdf": "exam",
            "bilety.docx": "exam",
            "kontrolnaya_2.pdf": "exam",
            "zachet.md": "exam",
            "resheniya.md": "solution",
            "variant_5.md": "exam",
            "вариант_5.md": "exam",
        }
        for name, kind in expected.items():
            self.assertEqual(kind, classify(Path(name)), name)

    def test_pdf_backend_uses_distribution_metadata_version(self):
        fake_pdfium = SimpleNamespace()
        with patch.dict(sys.modules, {"pypdfium2": fake_pdfium}):
            with patch("importlib.metadata.version", return_value="5.7.1"):
                backend = pdf_backend()
        self.assertIsNotNone(backend)
        self.assertEqual("5.7.1", backend.version)

    def test_transliterated_question_and_solution_pair_end_to_end(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "dz-1.md").write_text("Задача 1\nFind x", encoding="utf-8")
            (root / "dz-1_resheniya.md").write_text("Решение 1\nx = 2", encoding="utf-8")
            questions = extract_questions(extract_sources(root))
        self.assertEqual(1, len(questions))
        self.assertEqual("x = 2", questions[0].reference_answer)
        self.assertEqual(["x = 2"], questions[0].expected_evidence)


if __name__ == "__main__":
    unittest.main()
