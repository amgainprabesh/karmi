"""Tests for Karmi Printable Report & Document Exporter.

Following Extreme Programming (XP) TDD: Tests are written first before
implementing core/pdf_export.py and wiring into web/app.py.
"""

from __future__ import annotations

import re
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from core.schema import (
    Delta,
    DeltaStatus,
    DiffReport,
    ObservedState,
    Provenance,
    Room,
    SceneGraph,
    Severity,
    VerifyItem,
    Wall,
)


def _sample_report() -> tuple[DiffReport, SceneGraph, ObservedState]:
    prov = Provenance(source="vector_geometry", confidence=0.95)
    wall = Wall(id="W1", start=(0, 0), end=(5, 0), provenance=prov)
    room = Room(id="R1", name="Living Room", polygon=[(0, 0), (5, 0), (5, 4), (0, 4)], area_m2=20.0, provenance=prov)
    scene = SceneGraph(walls=[wall], rooms=[room], scale_m_per_unit=1.0)
    observed = ObservedState()

    delta = Delta(
        id="d001",
        element="Living Room area",
        status=DeltaStatus.DIFFERS,
        expected="20.0 m²",
        observed="18.5 m²",
        severity=Severity.LOW,
        confidence=0.85,
        reason="Living room measured 18.5 m² vs 20.0 m² in approved drawing",
        reason_np="बैठक कोठाको क्षेत्रफल १८.५ वर्गमिटर देखियो",
    )
    v_item = VerifyItem(
        id="v001",
        item="Verify living room floor area with mason",
        item_np="डकर्मीसँग बैठक कोठाको भित्री क्षेत्रफल जाँच्नुहोस्",
        why="Measured 18.5 m² vs 20.0 m² drawn",
        how="Measure clear interior dimension between plastered walls",
        severity=Severity.LOW,
        delta_ref="d001",
    )
    report = DiffReport(
        deltas=[delta],
        verify_list=[v_item],
        summary={"total": 1, "matched": 0, "high": 0, "medium": 0, "low": 1, "info": 0, "verify_items": 1},
        meta={"regulatory": {"standard": "NBC 206"}, "municipal": {"profile": "Kathmandu Valley"}},
    )
    return report, scene, observed


def test_render_printable_report_structure():
    """Printable report must contain official header, bilingual sections, and print styles."""
    from core.pdf_export import render_printable_report

    report, scene, observed = _sample_report()
    html = render_printable_report(report, scene, observed, metadata={"owner": "Prabesh Amgain", "ward": "Kathmandu-4"})

    assert isinstance(html, str)
    assert "<!doctype html>" in html.lower()
    # Official headings in Devanagari & English
    assert "कर्मी" in html
    assert "प्रतिवेदन" in html or "प्रमाणीकरण" in html
    assert "Items to verify" in html or "जाँच गर्नुपर्ने" in html
    # Metadata
    assert "Prabesh Amgain" in html
    assert "Kathmandu-4" in html
    # Signature / verification sign-off block
    assert "हस्ताक्षर" in html or "Signature" in html
    # Checkbox for physical check
    assert "checkbox" in html or "☐" in html or "[ ]" in html
    # Print media query
    assert "@media print" in html

    # Honesty invariant
    assert "violation" not in html.lower()
    assert "violat" not in html.lower()


def test_web_app_print_export_route():
    """GET /run/{run_id}/export/print must serve printable HTML."""
    import web.app as webapp
    client = TestClient(webapp.app)

    run_id = "20261007-123456-abcdef"
    rdir = webapp.RUNS_DIR / run_id
    rdir.mkdir(parents=True, exist_ok=True)
    report_data = {
        "schema_version": "0.1.0",
        "deltas": [],
        "verify_list": [],
        "summary": {"total": 0, "matched": 0, "high": 0, "medium": 0, "low": 0, "info": 0, "verify_items": 0},
    }
    import json
    (rdir / "report.json").write_text(json.dumps(report_data), encoding="utf-8")

    try:
        resp = client.get(f"/run/{run_id}/export/print")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "@media print" in resp.text
        assert "कर्मी" in resp.text

        # Also verify API export links include report_print
        api_resp = client.get(f"/api/export/{run_id}")
        assert api_resp.status_code == 200
        data = api_resp.json()
        assert "report_print" in data["links"]
        assert data["links"]["report_print"] == f"/run/{run_id}/export/print"
    finally:
        # Cleanup
        import shutil
        shutil.rmtree(rdir, ignore_errors=True)


def test_render_printable_report_empty():
    """Report renderer must safely handle empty report and None inputs."""
    from core.pdf_export import render_printable_report

    html = render_printable_report({}, None, None, None)
    assert isinstance(html, str)
    assert "<!doctype html>" in html.lower()
    assert "@media print" in html
    assert "कुनै स्थलगत जाँच सूची फेला परेन" in html
    assert "violation" not in html.lower()
