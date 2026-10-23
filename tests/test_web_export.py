"""Tests for Karmi Web UI Export Endpoints & 3D Deep-Linking.

Following Extreme Programming (XP) TDD: Tests are written first before
implementing export endpoints in web/app.py and deep-linking in viewer.html.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

import web.app as webapp


@pytest.fixture
def test_client():
    return TestClient(webapp.app)


@pytest.fixture
def sample_completed_run():
    """Create a temporary run directory populated with fixture artifacts."""
    run_id = "20261007-120000-abc123"
    rdir = webapp.RUNS_DIR / run_id
    rdir.mkdir(parents=True, exist_ok=True)

    report_data = {
        "schema_version": "0.1.0",
        "deltas": [],
        "verify_list": [],
        "summary": {"total": 0, "matched": 0, "high": 0, "medium": 0, "low": 0, "info": 0, "verify_items": 0},
        "meta": {"regulatory": {"standard": "NBC 206", "checks_run": 5, "items_flagged": 0}},
    }
    (rdir / "report.json").write_text(json.dumps(report_data), encoding="utf-8")
    (rdir / "report.html").write_text("<!doctype html><html><body>Report</body></html>", encoding="utf-8")
    (rdir / "view.json").write_text(json.dumps({"schema": "0.1.0", "approved": {}, "observed": {}, "deltas": []}), encoding="utf-8")

    yield run_id

    # Cleanup
    import shutil
    shutil.rmtree(rdir, ignore_errors=True)


def test_export_json_valid_run(test_client, sample_completed_run):
    """GET /run/{run_id}/export/json must return report.json as an attachment."""
    run_id = sample_completed_run
    resp = test_client.get(f"/run/{run_id}/export/json")
    assert resp.status_code == 200
    assert "application/json" in resp.headers.get("content-type", "")
    disp = resp.headers.get("content-disposition", "")
    assert "attachment" in disp
    assert f"karmi-report-{run_id}.json" in disp
    data = resp.json()
    assert data["schema_version"] == "0.1.0"


def test_export_report_html_valid_run(test_client, sample_completed_run):
    """GET /run/{run_id}/export/report must return report.html as an attachment."""
    run_id = sample_completed_run
    resp = test_client.get(f"/run/{run_id}/export/report")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    disp = resp.headers.get("content-disposition", "")
    assert "attachment" in disp
    assert f"karmi-report-{run_id}.html" in disp
    assert "<!doctype html>" in resp.text


def test_export_routes_nonexistent_run_returns_404(test_client):
    """Export routes on nonexistent run must return 404."""
    fake_id = "20261007-999999-ffffff"
    resp_json = test_client.get(f"/run/{fake_id}/export/json")
    assert resp_json.status_code == 404

    resp_html = test_client.get(f"/run/{fake_id}/export/report")
    assert resp_html.status_code == 404


def test_api_export_summary_endpoint(test_client, sample_completed_run):
    """GET /api/export/{run_id} returns structured bundle metadata."""
    run_id = sample_completed_run
    resp = test_client.get(f"/api/export/{run_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["run_id"] == run_id
    assert "summary" in data
    assert "links" in data
    assert "regulatory" in data


def test_viewer_html_contains_deep_linking_support():
    """render/viewer.html must contain search query focus/highlight parameter logic."""
    viewer_file = Path("render/viewer.html")
    assert viewer_file.is_file()
    content = viewer_file.read_text(encoding="utf-8")
    assert "focus" in content
    assert "URLSearchParams" in content or "location.search" in content
