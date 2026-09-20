"""Deterministic figure extraction and role-tagged asset indexing."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import re
from dataclasses import dataclass
from typing import Iterable, Sequence
import zipfile

from exam_prep_lib.ingest_issues import IngestIssue

from .extractor import extract_source, list_files, classify
from .pdf_backend import has_pdfium

MARGIN = 8
GAP = 12
SCAN_COVER = 0.08
MAX_PER_PAGE = 16
RENDER_SCALE = 2.0


@dataclass(frozen=True)
class PdfPageInfo:
    number: int
    width: float
    height: float
    text_top: float | None = None


def safe_stem(value: str | Path) -> str:
    raw = Path(str(value)).name
    raw = raw.replace(":", "_")
    raw = re.sub(r"[^A-Za-z0-9._-]+", "_", raw)
    raw = raw.replace("..", "_").strip("._")
    return raw or "asset"


def cluster(boxes: Iterable[Sequence[float]], gap: float = GAP) -> list[tuple[float, float, float, float]]:
    clusters: list[list[float]] = []
    for raw in boxes:
        box = [float(value) for value in raw]
        if len(box) != 4:
            continue
        merged = False
        for existing in clusters:
            horizontal = box[0] <= existing[2] + gap and box[2] >= existing[0] - gap
            vertical = box[1] <= existing[3] + gap and box[3] >= existing[1] - gap
            if horizontal and vertical:
                existing[:] = [min(existing[0], box[0]), min(existing[1], box[1]), max(existing[2], box[2]), max(existing[3], box[3])]
                merged = True
                break
        if not merged:
            clusters.append(box)
    return [tuple(box) for box in clusters]


def png_bytes(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    image = value.to_pil() if hasattr(value, "to_pil") else value
    output = io.BytesIO()
    if hasattr(image, "save"):
        image.save(output, format="PNG")
        return output.getvalue()
    return bytes(value)  # type: ignore[arg-type]


def _zip_media(path: Path) -> list[tuple[str, bytes]]:
    prefix = "word/media/" if path.suffix.casefold() == ".docx" else "ppt/media/"
    with zipfile.ZipFile(path) as archive:
        return [(name, archive.read(name)) for name in archive.namelist() if name.startswith(prefix) and not name.endswith("/")]


def extract_office_media(path: str | Path, output_dir: str | Path, *, role: str = "reference", source_ref: str | None = None) -> list[dict[str, str]]:
    source = Path(path)
    output = Path(output_dir) / role
    assets: list[dict[str, str]] = []
    for name, data in _zip_media(source):
        digest = hashlib.sha256(data).hexdigest()[:16]
        extension = Path(name).suffix.casefold() or ".bin"
        target = output / f"{digest}{extension}"
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(png_bytes(data))
        assets.append(
            {
                "asset_id": digest,
                "path": str(target),
                "role": role,
                "source_ref": source_ref or source.name,
                "assessment_id": None,
            }
        )
    return assets


def analyze_pdf(path: str | Path) -> tuple[tuple[PdfPageInfo, ...], tuple[IngestIssue, ...]]:
    if not has_pdfium():
        return (), (IngestIssue("unsupported_page", str(path), "PDF figure rendering requires pypdfium2", "gap"),)
    import pypdfium2  # type: ignore

    pages: list[PdfPageInfo] = []
    try:
        document = pypdfium2.PdfDocument(str(path))
        for number in range(len(document)):
            page = document[number]
            pages.append(PdfPageInfo(number + 1, float(page.get_width()), float(page.get_height())))
    except Exception as exc:  # pragma: no cover - backend-specific
        return (), (IngestIssue("bad_pdf_extraction", str(path), str(exc), "gap"),)
    return tuple(pages), ()


def render_region(
    path: str | Path,
    page_number: int,
    crop: Sequence[float] | None = None,
    *,
    scale: float = RENDER_SCALE,
) -> bytes | None:
    if not has_pdfium():
        return None
    import pypdfium2  # type: ignore

    document = pypdfium2.PdfDocument(str(path))
    page = document[page_number - 1]
    bitmap = page.render(scale=scale)
    image = bitmap.to_pil()
    if crop is not None:
        if len(crop) != 4:
            raise ValueError("crop must contain x0,y0,x1,y1")
        left, top, right, bottom = (int(float(value) * scale) for value in crop)
        image = image.crop((left, top, right, bottom))
    return png_bytes(image)


def find_text_top(boxes: Iterable[Sequence[float]] | None, *, page_height: float | None = None) -> float | None:
    if boxes is None:
        return None
    tops: list[float] = []
    for box in boxes:
        if len(box) != 4:
            continue
        top = float(box[1])
        if page_height and top >= page_height * (1 - SCAN_COVER):
            continue
        tops.append(top)
    return min(tops) if tops else None


def _page_selection(pages: Iterable[str] | None) -> dict[str, set[int] | None]:
    selection: dict[str, set[int] | None] = {}
    for raw in pages or ():
        relative, separator, number = str(raw).rpartition(":")
        if separator and number.isdigit():
            selection.setdefault(relative, set()).add(int(number))
        else:
            selection[str(raw)] = None
    return selection


def extract_figures(
    materials_dir: str | Path,
    output_dir: str | Path,
    *,
    pages: Iterable[str] | None = None,
    scale: float = RENDER_SCALE,
    crop: Sequence[float] | None = None,
) -> dict[str, object]:
    output = Path(output_dir)
    selected = _page_selection(pages)
    assets: list[dict[str, str]] = []
    issues: list[IngestIssue] = []
    for path in list_files(materials_dir):
        relative = path.relative_to(Path(materials_dir).resolve()).as_posix()
        if selected and relative not in selected:
            continue
        if path.suffix.casefold() in {".docx", ".pptx"}:
            kind = classify(path)
            role = "answer" if kind == "solution" else ("prompt" if kind in {"homework", "exam"} else "reference")
            assets.extend(extract_office_media(path, output, role=role, source_ref=relative))
        elif path.suffix.casefold() == ".pdf":
            page_info, pdf_issues = analyze_pdf(path)
            issues.extend(pdf_issues)
            if not page_info:
                continue
            chosen_pages = selected.get(relative) if selected else None
            for info in page_info[:MAX_PER_PAGE]:
                if chosen_pages is not None and info.number not in chosen_pages:
                    continue
                data = render_region(path, info.number, crop, scale=scale)
                if data is None:
                    issues.append(IngestIssue("unsupported_page", f"{relative}#p{info.number}", "PDF page was not rendered", "gap"))
                    continue
                digest = hashlib.sha256(data).hexdigest()[:16]
                kind = classify(path)
                role = "answer" if kind == "solution" else ("prompt" if kind in {"homework", "exam"} else "reference")
                target = output / role / f"{digest}.png"
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    target.write_bytes(data)
                assets.append(
                    {
                        "asset_id": digest,
                        "path": str(target),
                        "role": role,
                        "source_ref": f"{relative}#p{info.number}",
                        "assessment_id": None,
                    }
                )
    index = output / "index.json"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text(json.dumps({"assets": assets}, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return {"assets": assets, "issues": [issue.to_mapping() for issue in issues], "scale": scale}
