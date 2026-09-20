"""Stdlib-first extraction of local course materials."""

# Portions adapted from ZeKaiNie/universal-examprep-skill (MIT), see vendor/exam-cram-coach/LICENSE

from __future__ import annotations

import hashlib
from html.parser import HTMLParser
from pathlib import Path
import re
import zipfile
from dataclasses import dataclass
from dataclasses import replace
from typing import Iterable
import xml.etree.ElementTree as ET

from exam_prep_lib.ingest_issues import IngestIssue
from exam_prep_lib.lexicon import load
from exam_prep_lib.semantics import best_slot

from .pdf_backend import PdfSupportMissing, pdf_backend, read_pdf as _read_pdf

read_pdf = _read_pdf

EXTRACTOR_VERSION = "3"
MAX_FILE_BYTES = 64 * 1024 * 1024
SKIP_DIRS = frozenset({".git", ".exam-prep", "__pycache__", "node_modules"})
SKIP_NAMES = frozenset({"~$", ".DS_Store"})


@dataclass(frozen=True)
class ExtractedPage:
    number: int
    text: str


@dataclass(frozen=True)
class ExtractedSource:
    relative_path: str
    kind: str
    pages: tuple[ExtractedPage, ...]
    content_hash: str
    backend: str | None
    backend_version: str | None
    issues: tuple[IngestIssue, ...] = ()


def natural_key(value: str | Path) -> tuple[object, ...]:
    return tuple(int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", str(value)))


def _slot_kind(text: str, language: str, *, name: bool = False) -> str | None:
    lexicon = load(language)
    if name:
        lexicon = replace(lexicon, word_boundaries=False)
    found = best_slot("kind.", text, lexicon)
    if found is None:
        return None
    return found.slot.split(".", 1)[1]


def _content_kind(content: str, language: str = "ru") -> str:
    lexicon = load(language)
    for raw_line in content[:12000].splitlines():
        line = raw_line.strip()
        if not line:
            continue
        first_word = line.split(maxsplit=1)[0].strip("#.,:;()[]{}")
        found = best_slot("kind.", first_word, lexicon)
        if found is not None:
            return found.slot.split(".", 1)[1]
    return "other"


def classify(path: str | Path, content: str | None = None, language: str = "ru") -> str:
    kind = _slot_kind(Path(path).stem, language, name=True)
    if kind is not None:
        return kind
    return _content_kind(content, language) if content else "other"


def _xml_text(element: ET.Element) -> str:
    return "".join(element.itertext()).strip()


def _docx_paragraph_text(paragraph: ET.Element, ns: dict[str, str]) -> str:
    return "".join(node.text or "" for node in paragraph.findall(".//w:t", ns)).strip()


def _docx_has_page_break(paragraph: ET.Element, ns: dict[str, str]) -> bool:
    return paragraph.find(".//w:br[@w:type='page']", ns) is not None


def read_docx(path: str | Path) -> tuple[ExtractedPage, ...]:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    pages: list[str] = []
    current: list[str] = []
    for paragraph in root.findall(".//w:p", ns):
        text = _docx_paragraph_text(paragraph, ns)
        if text:
            current.append(text)
        if _docx_has_page_break(paragraph, ns):
            pages.append("\n".join(current).strip())
            current = []
    if current or not pages:
        pages.append("\n".join(current).strip())
    return tuple(ExtractedPage(i, text) for i, text in enumerate(pages, 1))


def _pptx_text(element: ET.Element, ns: dict[str, str]) -> str:
    return " ".join(text.strip() for text in (node.text or "" for node in element.findall(".//a:t", ns)) if text.strip())


def read_pptx(path: str | Path) -> tuple[ExtractedPage, ...]:
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    with zipfile.ZipFile(path) as archive:
        slide_names = sorted((name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)), key=natural_key)
        pages = []
        for number, slide_name in enumerate(slide_names, 1):
            root = ET.fromstring(archive.read(slide_name))
            text = _pptx_text(root, ns)
            note_name = f"ppt/notesSlides/notesSlide{number}.xml"
            if note_name in archive.namelist():
                notes = _pptx_text(ET.fromstring(archive.read(note_name)), ns)
                if notes:
                    text = f"{text}\n{notes}" if text else notes
            pages.append(ExtractedPage(number, text))
    return tuple(pages)


def read_text(path: str | Path) -> tuple[ExtractedPage, ...]:
    return (ExtractedPage(1, Path(path).read_text(encoding="utf-8-sig")),)


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def read_html(path: str | Path) -> tuple[ExtractedPage, ...]:
    parser = _HTMLText()
    parser.feed(Path(path).read_text(encoding="utf-8-sig"))
    return (ExtractedPage(1, "\n".join(parser.parts)),)


def strip_repeated_lines(pages: Iterable[ExtractedPage]) -> tuple[ExtractedPage, ...]:
    materialized = tuple(pages)
    if len(materialized) < 2:
        return materialized
    first_counts: dict[str, int] = {}
    last_counts: dict[str, int] = {}
    for page in materialized:
        lines = [line.strip() for line in page.text.splitlines() if line.strip()]
        if lines:
            first_counts[lines[0]] = first_counts.get(lines[0], 0) + 1
            last_counts[lines[-1]] = last_counts.get(lines[-1], 0) + 1
    repeated = {line for line, count in first_counts.items() if count >= 2} | {line for line, count in last_counts.items() if count >= 2}
    result = []
    for page in materialized:
        lines = page.text.splitlines()
        while lines and lines[0].strip() in repeated:
            lines.pop(0)
        while lines and lines[-1].strip() in repeated:
            lines.pop()
        result.append(ExtractedPage(page.number, "\n".join(lines).strip()))
    return tuple(result)


def list_files(root: str | Path) -> tuple[Path, ...]:
    base = Path(root).resolve()
    files = []
    for path in base.rglob("*"):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
            continue
        if any(path.name.startswith(prefix) for prefix in SKIP_NAMES):
            continue
        files.append(path)
    return tuple(sorted(files, key=lambda item: natural_key(item.relative_to(base))))


def _read_pages(path: Path) -> tuple[tuple[ExtractedPage, ...], str | None, str | None, tuple[IngestIssue, ...]]:
    suffix = path.suffix.casefold()
    if suffix == ".docx":
        return read_docx(path), None, None, ()
    if suffix == ".pptx":
        return read_pptx(path), None, None, ()
    if suffix in {".md", ".txt", ".rst", ".csv"}:
        return read_text(path), None, None, ()
    if suffix in {".html", ".htm"}:
        return read_html(path), None, None, ()
    if suffix == ".pdf":
        texts, backend, issues = _read_pdf(path)
        return tuple(ExtractedPage(i, text) for i, text in enumerate(texts, 1)), backend.name, backend.version, issues
    return (), None, None, (IngestIssue("unsupported_page", path.name, f"unsupported format: {suffix or 'none'}", "info"),)


def extract_source(root: str | Path, path: str | Path, *, max_file_bytes: int = MAX_FILE_BYTES, language: str = "ru") -> ExtractedSource:
    base = Path(root).resolve()
    source = Path(path).resolve()
    relative = source.relative_to(base).as_posix()
    raw = source.read_bytes()
    if len(raw) > max_file_bytes:
        issue = IngestIssue("unsupported_page", relative, f"file exceeds {max_file_bytes} bytes", "blocking")
        return ExtractedSource(relative, classify(source, language=language), (), hashlib.sha256(raw).hexdigest(), None, None, (issue,))
    issues: list[IngestIssue] = []
    try:
        pages, backend, backend_version, read_issues = _read_pages(source)
        issues.extend(read_issues)
    except PdfSupportMissing as exc:
        pages, backend, backend_version = (), None, None
        issues.append(IngestIssue("unsupported_page", relative, str(exc), "gap"))
    except Exception as exc:
        pages, backend, backend_version = (), None, None
        issues.append(IngestIssue("bad_pdf_extraction", relative, str(exc), "gap"))
    pages = strip_repeated_lines(pages)
    kind = classify(source, "\n".join(page.text for page in pages), language)
    if not pages:
        issues.append(IngestIssue("unsupported_page", relative, "no pages were extracted", "gap"))
    return ExtractedSource(relative, kind, tuple(pages), hashlib.sha256(raw).hexdigest(), backend, backend_version, tuple(issues))


def extract_sources(root: str | Path, *, max_file_bytes: int = MAX_FILE_BYTES, language: str = "ru") -> tuple[ExtractedSource, ...]:
    return tuple(extract_source(root, path, max_file_bytes=max_file_bytes, language=language) for path in list_files(root))
