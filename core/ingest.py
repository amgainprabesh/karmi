"""Karmi — ingestion: drawing files (PDF) and photos.

Deterministic, offline, no AI. The job of this module is to turn a file into
plain Python data that the extraction pipeline can chew on:

* :func:`ingest_drawing` — vector paths, text items, page info from a PDF
  (or a raster file opened as a single image page).
* :func:`ingest_photo` — minimal metadata for a site photo (size, EXIF time,
  orientation flag).

Failures are always raised as :class:`IngestError` with a human-readable
message — never a raw library traceback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf

from core.schema import SourceKind

#: A page needs at least this many straight segments to be treated as a
#: CAD-exported vector drawing.
MIN_VECTOR_SEGMENTS = 4


class IngestError(Exception):
    """A clean, human-readable ingestion failure."""


@dataclass
class TextItem:
    """One text span from the drawing.

    ``x``/``y`` are the *centre* of the span's bounding box (page points), which
    is what room-label matching needs; ``size`` is the font size in points.
    """

    text: str
    x: float
    y: float
    size: float
    page: int


@dataclass
class IngestedDrawing:
    kind: SourceKind
    page_index: int
    page_size_pt: tuple[float, float]
    segments: list[tuple[tuple[float, float], tuple[float, float]]]
    texts: list[TextItem]
    image_count: int
    warnings: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class IngestedPhoto:
    path: str
    width: int
    height: int
    exif_datetime: str | None = None
    orientation: int | None = None
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# drawing ingestion
# --------------------------------------------------------------------------- #
def ingest_drawing(path: str | Path) -> IngestedDrawing:
    """Read a drawing file into segments + texts + a source-kind guess.

    Raises :class:`IngestError` for missing, encrypted, corrupt or empty files.
    """
    p = Path(path)
    if not p.exists():
        raise IngestError(f"Drawing file not found: {p}")

    try:
        doc = pymupdf.open(str(p))
    except Exception:
        raise IngestError(
            f"Could not open '{p.name}': the file is not a readable PDF/image or is corrupt."
        ) from None

    try:
        if doc.needs_pass:
            raise IngestError(
                f"'{p.name}' is password-protected (encrypted PDF). "
                "Please supply an unlocked copy."
            )
        if doc.page_count == 0:
            raise IngestError(f"'{p.name}' contains no pages.")

        warnings: list[str] = []
        page_index, page = _select_page(doc)
        if doc.page_count > 1:
            warnings.append(
                f"PDF has {doc.page_count} pages; page {page_index + 1} was read "
                "(single-floor scope)."
            )

        segments, n_curves = _page_segments(page)
        texts = _page_texts(page, page_index)
        infos = page.get_image_info()
        image_count = len(page.get_images(full=True))
        kind = _classify(p, page, segments, texts, infos)

        if n_curves:
            warnings.append(
                f"{n_curves} bezier curve item(s) were skipped (only straight segments are used)."
            )
        if kind is SourceKind.VECTOR_PDF and len(segments) < MIN_VECTOR_SEGMENTS:
            warnings.append("No usable vector geometry was found on the selected page.")
        if kind in (SourceKind.RASTER_PDF, SourceKind.SCAN, SourceKind.IMAGE):
            warnings.append(
                "The page has no usable vector paths — it looks like a raster/scan; "
                "vector extraction will be skipped."
            )

        meta: dict[str, Any] = {
            "n_pages": doc.page_count,
            "curves_skipped": n_curves,
            "pdf_title": (doc.metadata or {}).get("title"),
            "file_name": p.name,
        }
        return IngestedDrawing(
            kind=kind,
            page_index=page_index,
            page_size_pt=(float(page.rect.width), float(page.rect.height)),
            segments=segments,
            texts=texts,
            image_count=image_count,
            warnings=warnings,
            meta=meta,
        )
    except IngestError:
        raise
    except Exception as exc:  # noqa: BLE001 — never leak a raw library traceback
        raise IngestError(f"Could not read '{p.name}': {type(exc).__name__} while parsing the file.") from None
    finally:
        doc.close()


def _select_page(doc: "pymupdf.Document") -> tuple[int, "pymupdf.Page"]:
    """First page with vector content; else first page with an image; else page 0."""
    first_image: tuple[int, "pymupdf.Page"] | None = None
    for i in range(doc.page_count):
        page = doc[i]
        segs, _ = _page_segments(page)
        if len(segs) >= MIN_VECTOR_SEGMENTS:
            return i, page
        if first_image is None and page.get_images(full=True):
            first_image = (i, page)
    if first_image is not None:
        return first_image
    return 0, doc[0]


def _page_segments(page: "pymupdf.Page") -> tuple[list[tuple[tuple[float, float], tuple[float, float]]], int]:
    """Straight segments from ``page.get_drawings()``; also counts skipped curves.

    ``l`` items become one segment, ``re`` rectangles and ``qu`` quads become
    their four edges. Bezier curves (``c``) are counted and skipped.
    """
    segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    n_curves = 0
    try:
        drawings = page.get_drawings()
    except Exception:  # noqa: BLE001 — a page we cannot draw is a page with no vectors
        return segments, n_curves
    for d in drawings:
        for item in d.get("items", ()):  # type: ignore[union-attr]
            op = item[0]
            if op == "l":
                a, b = item[1], item[2]
                segments.append(((float(a.x), float(a.y)), (float(b.x), float(b.y))))
            elif op == "re":
                r = item[1]
                corners = [(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)]
                for k in range(4):
                    segments.append(
                        ((float(corners[k][0]), float(corners[k][1])),
                         (float(corners[(k + 1) % 4][0]), float(corners[(k + 1) % 4][1])))
                    )
            elif op == "qu":
                q = item[1]
                corners = [(q.ul.x, q.ul.y), (q.ur.x, q.ur.y), (q.lr.x, q.lr.y), (q.ll.x, q.ll.y)]
                for k in range(4):
                    segments.append(
                        ((float(corners[k][0]), float(corners[k][1])),
                         (float(corners[(k + 1) % 4][0]), float(corners[(k + 1) % 4][1])))
                    )
            elif op == "c":
                n_curves += 1
    return segments, n_curves


def _page_texts(page: "pymupdf.Page", page_index: int) -> list[TextItem]:
    """All non-empty text spans on the page, positioned at their bbox centre."""
    out: list[TextItem] = []
    try:
        d = page.get_text("dict")
    except Exception:  # noqa: BLE001
        return out
    for blk in d.get("blocks", ()):
        if blk.get("type", 0) != 0:
            continue
        for line in blk.get("lines", ()):
            for span in line.get("spans", ()):
                text = span.get("text", "")
                if not text.strip():
                    continue
                x0, y0, x1, y1 = span["bbox"]
                out.append(
                    TextItem(
                        text=text.strip(),
                        x=(x0 + x1) / 2.0,
                        y=(y0 + y1) / 2.0,
                        size=float(span.get("size", 0.0)),
                        page=page_index,
                    )
                )
    return out


def _classify(
    p: Path,
    page: "pymupdf.Page",
    segments: list[tuple[tuple[float, float], tuple[float, float]]],
    texts: list[TextItem],
    infos: list[dict[str, Any]],
) -> SourceKind:
    """vector_pdf / raster_pdf / scan / image — see docs/architecture.md."""
    if len(segments) >= MIN_VECTOR_SEGMENTS:
        return SourceKind.VECTOR_PDF
    if infos:
        full_page = False
        if len(infos) == 1:
            b = infos[0].get("bbox")
            if b:
                area = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
                page_area = page.rect.width * page.rect.height
                full_page = page_area > 0 and area >= 0.9 * page_area
        has_text = any(t.text.strip() for t in texts)
        if full_page and not has_text:
            return SourceKind.SCAN if p.suffix.lower() == ".pdf" else SourceKind.IMAGE
        return SourceKind.RASTER_PDF
    return SourceKind.VECTOR_PDF  # empty vector page; degraded downstream, with a warning


# --------------------------------------------------------------------------- #
# photo ingestion
# --------------------------------------------------------------------------- #
def ingest_photo(path: str | Path) -> IngestedPhoto:
    """Minimal photo metadata: pixel size, EXIF datetime, orientation flag."""
    p = Path(path)
    if not p.exists():
        raise IngestError(f"Photo file not found: {p}")
    try:
        from PIL import Image

        with Image.open(str(p)) as im:
            width, height = im.size
            orientation: int | None = None
            exif_dt: str | None = None
            try:
                exif = im.getexif()
                orientation = exif.get(274)
                exif_dt = exif.get(36867) or exif.get(306)
                if exif_dt is None:
                    ifd = exif.get_ifd(0x8769)
                    if ifd:
                        exif_dt = ifd.get(36867)
            except Exception:  # noqa: BLE001 — EXIF is optional
                pass
            warnings: list[str] = []
            if exif_dt is None:
                warnings.append("No EXIF DateTimeOriginal/DateTime found.")
            if orientation is None:
                warnings.append("No EXIF orientation tag found.")
            return IngestedPhoto(
                path=str(p),
                width=int(width),
                height=int(height),
                exif_datetime=str(exif_dt) if exif_dt else None,
                orientation=int(orientation) if orientation is not None else None,
                warnings=warnings,
            )
    except IngestError:
        raise
    except Exception:  # noqa: BLE001
        raise IngestError(
            f"Could not read photo '{p.name}': not a readable image file."
        ) from None


__all__ = [
    "IngestError",
    "TextItem",
    "IngestedDrawing",
    "IngestedPhoto",
    "ingest_drawing",
    "ingest_photo",
    "MIN_VECTOR_SEGMENTS",
]