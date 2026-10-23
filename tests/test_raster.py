"""Tests for ``core.raster`` — deterministic raster line and scale extraction."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image
import pymupdf
import pytest

from conftest import require

raster = require("core.raster")
model = require("core.model")
schema = require("core.schema")


@pytest.mark.slow
def test_extract_plan_from_rendered_pdf_fixture(fixtures_dir: Path, tmp_path: Path):
    doc = pymupdf.open(fixtures_dir / "naksa_base.pdf")
    pix = doc[0].get_pixmap(dpi=150)
    png_path = tmp_path / "naksa_scan.png"
    pix.save(str(png_path))
    doc.close()

    result = raster.extract_plan(png_path)
    assert isinstance(result, dict)
    assert len(result["segments"]) > 0
    # No invented scale when no scale bar/ratio exists
    assert result["scale_m_per_unit"] is None

    gray = raster.load_gray(png_path)
    assert gray.ndim == 2
    binary = raster.binarize(gray)
    assert binary.dtype == bool
    assert binary.mean() > 0.001  # contains ink


@pytest.mark.slow
def test_deskew_recovers_applied_rotation(fixtures_dir: Path, tmp_path: Path):
    doc = pymupdf.open(fixtures_dir / "naksa_base.pdf")
    pix = doc[0].get_pixmap(dpi=150)
    base_png = tmp_path / "base.png"
    pix.save(str(base_png))
    doc.close()

    # Rotate by 4 degrees counter-clockwise
    im = Image.open(base_png).convert("L").rotate(4.0, expand=True, fillcolor=255)
    rot_png = tmp_path / "rotated.png"
    im.save(rot_png)

    gray = raster.load_gray(rot_png)
    binary = raster.binarize(gray)
    _, angle_deg = raster.deskew(binary)
    # Applied rotation should be detected in the opposite direction (-4.0 ± 0.6)
    assert abs(angle_deg - (-4.0)) <= 0.6


def test_blank_image_returns_zero_segments_with_warnings(tmp_path: Path):
    blank_png = tmp_path / "blank.png"
    Image.new("L", (800, 600), 255).save(blank_png)

    result = raster.extract_plan(blank_png)
    assert len(result["segments"]) == 0
    assert len(result["warnings"]) > 0


def test_uniform_binarize_does_not_divide_by_zero():
    # Uniform gray image
    arr = np.full((100, 100), 128.0, dtype=np.float64)
    res = raster.binarize(arr)
    assert res.sum() == 0  # no ink found, no crash


@pytest.mark.slow
def test_scan_only_pdf_in_build_scene_graph(fixtures_dir: Path, tmp_path: Path):
    doc = pymupdf.open(fixtures_dir / "naksa_base.pdf")
    pix = doc[0].get_pixmap(dpi=150)
    png_path = tmp_path / "page_img.png"
    pix.save(str(png_path))
    doc.close()

    scan_pdf = tmp_path / "scan_only.pdf"
    new_doc = pymupdf.open()
    page = new_doc.new_page(width=842, height=595)
    page.insert_image(page.rect, filename=str(png_path))
    new_doc.save(str(scan_pdf))
    new_doc.close()

    scene = model.build_scene_graph(str(scan_pdf), scale_m_per_unit=None, north_deg=None, ai=None)
    assert scene.source_kind in (schema.SourceKind.SCAN, schema.SourceKind.RASTER_PDF)
    assert len(scene.walls) > 0
    # Honest confidence capped at 0.70
    assert all(w.provenance.confidence <= 0.70 for w in scene.walls)
    assert all(w.provenance.source == "raster_geometry" for w in scene.walls)
    assert any("raster/scan" in w.lower() for w in scene.warnings)
