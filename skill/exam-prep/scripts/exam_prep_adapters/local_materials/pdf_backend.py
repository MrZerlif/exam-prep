"""The sole import boundary for optional PDF extraction dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

from exam_prep_lib.ingest_issues import IngestIssue


class PdfSupportMissing(RuntimeError):
    """Raised when no supported local PDF backend is installed."""


@dataclass(frozen=True)
class PdfBackend:
    name: str
    version: str


def _distribution_version(distribution: str, module: Any) -> str:
    try:
        return str(importlib_metadata.version(distribution))
    except importlib_metadata.PackageNotFoundError:
        return str(getattr(module, "__version__", "unknown"))


def pdf_backend() -> PdfBackend | None:
    try:
        import pypdfium2  # type: ignore

        version = _distribution_version("pypdfium2", pypdfium2)
        return PdfBackend("pypdfium2", version)
    except ImportError:
        pass
    try:
        import pypdf  # type: ignore

        version = _distribution_version("pypdf", pypdf)
        return PdfBackend("pypdf", version)
    except ImportError:
        return None


def read_pdf(path: str | Path) -> tuple[tuple[str, ...], PdfBackend, tuple[IngestIssue, ...]]:
    """Read PDF text without importing either optional package elsewhere."""

    backend = pdf_backend()
    if backend is None:
        raise PdfSupportMissing("no optional PDF backend is installed")
    source = Path(path)
    texts: list[str] = []
    issues: list[IngestIssue] = []
    if backend.name == "pypdfium2":
        import pypdfium2  # type: ignore

        document = pypdfium2.PdfDocument(str(source))
        for number in range(len(document)):
            page = document[number]
            text_page = page.get_textpage()
            text = text_page.get_text_range() or ""
            texts.append(text.strip())
            if not text.strip():
                issues.append(
                    IngestIssue("unsupported_page", f"{source.name}#p{number + 1}", "page has no extractable text", "gap")
                )
        return tuple(texts), backend, tuple(issues)

    import pypdf  # type: ignore

    try:
        reader = pypdf.PdfReader(str(source))
        for number, page in enumerate(reader.pages, 1):
            try:
                text = (page.extract_text() or "").strip()
            except Exception as exc:  # pragma: no cover - backend-specific
                text = ""
                issues.append(
                    IngestIssue("bad_pdf_extraction", f"{source.name}#p{number}", str(exc), "gap")
                )
            texts.append(text)
            if not text:
                issues.append(
                    IngestIssue("unsupported_page", f"{source.name}#p{number}", "page has no extractable text", "gap")
                )
    except Exception as exc:
        raise PdfSupportMissing(f"PDF extraction failed: {exc}") from exc
    return tuple(texts), backend, tuple(issues)


def has_pdfium() -> bool:
    backend = pdf_backend()
    return bool(backend and backend.name == "pypdfium2")
