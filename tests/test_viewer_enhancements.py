"""Tests for Interactive 3D/2D Measurement & Bilingual Overlay Inspector.

Following Extreme Programming (XP) TDD: Tests are written first before
implementing measurement tool and bilingual HUD enhancements in render/viewer.html
and render/adapter.py.
"""

from __future__ import annotations

import re
from pathlib import Path
import pytest

from core.schema import (
    Delta,
    DeltaStatus,
    DiffReport,
    ObservedState,
    Provenance,
    Room,
    SceneGraph,
    Severity,
    Wall,
)
from render.adapter import build_view


def _sample_data():
    prov = Provenance(source="vector_geometry", confidence=0.95)
    wall = Wall(id="W1", start=(0.0, 0.0), end=(5.0, 0.0), provenance=prov)
    room = Room(id="R1", name="Living Room", polygon=[(0, 0), (5, 0), (5, 4), (0, 4)], area_m2=20.0, provenance=prov)
    scene = SceneGraph(walls=[wall], rooms=[room], scale_m_per_unit=1.0)
    observed = ObservedState()
    delta = Delta(
        id="d001",
        element="W1",
        status=DeltaStatus.MATCHED,
        expected="5.0 m",
        observed="5.0 m",
        severity=Severity.INFO,
        confidence=0.90,
        reason="Wall matches approved plan",
    )
    report = DiffReport(
        deltas=[delta],
        verify_list=[],
        summary={"total": 1, "matched": 1, "high": 0, "medium": 0, "low": 0, "info": 1, "verify_items": 0},
        meta={
            "regulatory": {"standard": "NBC 206"},
            "municipal": {"profile": "Kathmandu Valley (KVDA)"},
        },
    )
    return report, scene, observed


def test_adapter_passes_regulatory_and_municipal_metadata():
    """render/adapter.py must forward regulatory and municipal data to view payload."""
    report, scene, observed = _sample_data()
    payload = build_view(scene, observed, report)

    assert "meta" in payload
    assert "municipal" in payload["meta"]
    assert payload["meta"]["municipal"]["profile"] == "Kathmandu Valley (KVDA)"
    assert "regulatory" in payload["meta"]
    assert payload["meta"]["regulatory"]["standard"] == "NBC 206"
    assert payload["meta"]["scale_m_per_unit"] == 1.0


def test_viewer_html_measurement_tool_elements():
    """render/viewer.html must contain measurement tool toggle and measurement UI."""
    viewer_path = Path("render/viewer.html")
    assert viewer_path.is_file()
    html = viewer_path.read_text(encoding="utf-8")

    # Measurement tool button
    assert 'id="btn-measure"' in html
    # Distance / measurement display logic
    assert "measure" in html.lower()
    assert "distance" in html.lower() or "dist" in html.lower()
    # Meter and feet units
    assert "m" in html and "ft" in html


def test_viewer_html_bilingual_support():
    """render/viewer.html must support bilingual English/Nepali labels and status."""
    viewer_path = Path("render/viewer.html")
    html = viewer_path.read_text(encoding="utf-8")

    # Devanagari labels
    assert "स्वीकृत" in html or "नक्सा" in html
    assert "नाप्नुहोस्" in html or "दूरी" in html
    # Language toggle or bilingual elements
    assert "btn-lang" in html or "lang-toggle" in html or "नेपाली" in html

    # Honesty invariant
    assert "violation" not in html.lower()
