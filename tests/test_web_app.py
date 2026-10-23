"""Tests for ``web.app`` — FastAPI routes, uploads, and viewer rendering."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import require

# Ensure KARMI_RUNS_DIR points to a safe temp dir before importing or testing web.app
@pytest.fixture(scope="module")
def client(tmp_path_factory):
    runs_dir = tmp_path_factory.mktemp("web_runs")
    os.environ["KARMI_RUNS_DIR"] = str(runs_dir)

    import web.app as webapp
    # Update global in webapp in case it was imported earlier
    webapp.RUNS_DIR = runs_dir

    return TestClient(webapp.app)


def test_healthz(client: TestClient):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["core_available"] is True
    assert data["viewer_available"] is True


def test_index_page(client: TestClient):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Karmi" in resp.text
    assert "नक्सा" in resp.text


@pytest.mark.slow
def test_full_upload_flow(client: TestClient, fixtures_dir: Path):
    drawing_path = fixtures_dir / "naksa_base.pdf"
    photos_dir = fixtures_dir / "photos"
    photo_names = ["front_walls_stage.jpg", "rear_foundation_stage.jpg", "side_columns_stage.jpg"]

    files = [("drawing", (drawing_path.name, drawing_path.read_bytes(), "application/pdf"))]
    for n in photo_names:
        p = photos_dir / n
        s = photos_dir / f"{n}.json"
        files.append(("photos", (p.name, p.read_bytes(), "image/jpeg")))
        files.append(("photos", (s.name, s.read_bytes(), "application/json")))

    resp = client.post("/api/analyze", files=files, data={"known_dimension": "10.0"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    run_id = data["run_id"]
    assert run_id is not None
    assert data["counts"]["high"] >= 1
    assert data["counts"]["medium"] >= 1

    # Verify run HTML page
    run_resp = client.get(f"/run/{run_id}")
    assert run_resp.status_code == 200
    assert 'id="verify-list"' in run_resp.text
    assert "नक्साअनुसार" in run_resp.text or "जाँच" in run_resp.text

    # Verify JSON report API
    rep_resp = client.get(f"/api/report/{run_id}")
    assert rep_resp.status_code == 200
    rep_data = rep_resp.json()
    assert len(rep_data["verify_list"]) == data["counts"]["verify_items"]

    # Verify 3D viewer routes
    viewer_resp = client.get(f"/viewer/{run_id}")
    assert viewer_resp.status_code == 200
    view_json_resp = client.get(f"/viewer/{run_id}/view.json")
    assert view_json_resp.status_code == 200
    vendor_resp = client.get(f"/viewer/{run_id}/vendor/three.module.js")
    assert vendor_resp.status_code == 200


def test_upload_without_photos_degrades_gracefully(client: TestClient, fixtures_dir: Path):
    drawing_path = fixtures_dir / "naksa_base.pdf"
    files = [("drawing", (drawing_path.name, drawing_path.read_bytes(), "application/pdf"))]

    resp = client.post("/api/analyze", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert len(data.get("warnings", [])) > 0 or data.get("counts", {}).get("total", 0) > 0


def test_upload_without_drawing_fails_with_400(client: TestClient, fixtures_dir: Path):
    photo_path = fixtures_dir / "photos" / "front_walls_stage.jpg"
    files = [("photos", (photo_path.name, photo_path.read_bytes(), "image/jpeg"))]

    resp = client.post("/api/analyze", files=files)
    assert resp.status_code == 400
    data = resp.json()
    assert data["ok"] is False


def test_path_traversal_returns_404(client: TestClient):
    assert client.get("/run/../../etc/passwd").status_code in (404, 400)
    assert client.get("/viewer/..%2f..%2fview.json").status_code in (404, 400)
