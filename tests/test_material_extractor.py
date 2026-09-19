import sys
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_adapters.local_materials.chapters import build_chapters
from exam_prep_adapters.local_materials.extractor import (
    ExtractedPage,
    classify,
    read_docx,
    strip_repeated_lines,
)


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


if __name__ == "__main__":
    unittest.main()
