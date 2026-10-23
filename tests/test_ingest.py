"""Tests for ``core.ingest`` — drawing and photo normalisation."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from conftest import require

ingest = require("core.ingest")
schema = require("core.schema")


def test_ingest_vector_pdf_fixture(fixtures_dir: Path):
    path = fixtures_dir / "naksa_base.pdf"
    res = ingest.ingest_drawing(path)
    assert res.kind == schema.SourceKind.VECTOR_PDF
    assert res.page_index == 0
    assert len(res.segments) > 0
    assert len(res.texts) > 0
    assert any("BEDROOM" in t.text for t in res.texts)
    assert res.image_count == 0


def test_ingest_raster_scan_pdf(tmp_path: Path):
    # Create a synthetic scan-only PDF containing only an image and no vector paths
    img_path = tmp_path / "plan_scan.png"
    Image.new("RGB", (800, 600), color="white").save(img_path)

    pdf_path = tmp_path / "scan.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=800, height=600)
    page.insert_image(page.rect, filename=str(img_path))
    doc.save(str(pdf_path))
    doc.close()

    res = ingest.ingest_drawing(pdf_path)
    assert res.kind in (schema.SourceKind.SCAN, schema.SourceKind.RASTER_PDF)
    assert res.image_count >= 1
    assert len(res.segments) == 0
    assert len(res.warnings) > 0


def test_ingest_drawing_nonexistent_file():
    with pytest.raises(ingest.IngestError, match="not found"):
        ingest.ingest_drawing("fixtures/nonexistent_file_xyz.pdf")


def test_ingest_drawing_unsupported_extension(tmp_path: Path):
    bad_file = tmp_path / "test.docx"
    bad_file.write_text("dummy", encoding="utf-8")
    with pytest.raises(ingest.IngestError, match="not a readable PDF/image"):
        ingest.ingest_drawing(bad_file)


def test_ingest_photo_valid_fixture(fixtures_dir: Path):
    photo_path = fixtures_dir / "photos" / "front_walls_stage.jpg"
    res = ingest.ingest_photo(photo_path)
    assert res.width > 0
    assert res.height > 0
    assert res.path.replace("\\", "/").endswith("front_walls_stage.jpg")


def test_ingest_photo_nonexistent():
    with pytest.raises(ingest.IngestError, match="not found"):
        ingest.ingest_photo("fixtures/photos/nonexistent.jpg")
