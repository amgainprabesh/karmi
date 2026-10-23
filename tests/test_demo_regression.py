"""Tests for demo scenario regression, control-run honesty, and DoD invariants."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import require

pipeline = require("core.pipeline")
diff = require("core.diff")
schema = require("core.schema")
scripts_check_dod = require("scripts.check_dod")


@pytest.fixture
def demo_run_artifacts(tmp_path: Path, fixtures_dir: Path):
    drawing = fixtures_dir / "naksa_base.pdf"
    photos_dir = fixtures_dir / "photos"
    photo_names = ["front_walls_stage.jpg", "rear_foundation_stage.jpg", "side_columns_stage.jpg"]
    photos = [str(photos_dir / n) for n in photo_names]
    sidecars = {str(photos_dir / n): str(photos_dir / f"{n}.json") for n in photo_names}

    out_dir = tmp_path / "demo_run"
    res = pipeline.run_pipeline(
        drawing=str(drawing),
        photos=photos,
        out_dir=str(out_dir),
        known_dimension=10.0,
        sidecars=sidecars,
    )
    return res, out_dir


def test_demo_scenario_expected_findings(demo_run_artifacts):
    res, out_dir = demo_run_artifacts
    assert res.report is not None

    summary = res.report.summary
    assert summary["high"] == 1
    assert summary["medium"] == 1
    assert summary["matched"] == 5
    assert summary["verify_items"] == 16

    delta_map = {d.scene_ref: (d.status.value, d.severity.value) for d in res.report.deltas if d.scene_ref}
    # Expected key elements from the demo scenario
    assert delta_map.get("O8") == ("differs", "high")      # Front window width
    assert delta_map.get("O4") == ("differs", "medium")    # Side door frame
    assert delta_map.get("R1") == ("differs", "low")       # Bedroom 1 area
    assert delta_map.get("W7") == ("matched", "info")      # Front wall length
    assert delta_map.get("W4") == ("matched", "info")      # East wall length
    assert delta_map.get("W1") == ("matched", "info")      # North wall length
    assert delta_map.get("W2") == ("matched", "info")      # West wall length


def test_control_run_perfect_observation_yields_zero_differences(demo_run_artifacts):
    res, _ = demo_run_artifacts
    scene = res.scene
    assert scene is not None

    # Use check_dod's helper to create an exact observation of all drawn elements
    ctl_obs = scripts_check_dod._perfect_observation(scene)
    ctl_report = diff.diff_scene(scene, ctl_obs)

    # Perfect match should yield 0 differs/missing/unexpected
    diffs = [d for d in ctl_report.deltas if d.status.value in ("differs", "missing", "unexpected")]
    assert len(diffs) == 0, f"Control run produced unexpected differences: {diffs}"
    assert ctl_report.summary["matched"] == len(ctl_report.deltas)


@pytest.mark.slow
def test_dod_invariants_pass(tmp_path: Path):
    """Directly test that check_dod's automated checks (D1–D7) pass."""
    ctx = {"tmp": tmp_path, "skip_pytest": True}
    res_d1 = scripts_check_dod.check_d1(ctx)
    assert res_d1.ok is True, f"D1 failed: {res_d1.problems}"

    res_d2 = scripts_check_dod.check_d2(ctx)
    assert res_d2.ok is True, f"D2 failed: {res_d2.problems}"

    res_d3 = scripts_check_dod.check_d3(ctx)
    assert res_d3.ok is True, f"D3 failed: {res_d3.problems}"

    import sys
    if "web.app" in sys.modules:
        sys.modules["web.app"].RUNS_DIR = (tmp_path / "web-runs").resolve()

    res_d4 = scripts_check_dod.check_d4(ctx)
    assert res_d4.ok is True, f"D4 failed: {res_d4.problems}"

    res_d5 = scripts_check_dod.check_d5(ctx)
    assert res_d5.ok is True, f"D5 failed: {res_d5.problems}"

    res_d6 = scripts_check_dod.check_d6(ctx)
    assert res_d6.ok is True, f"D6 failed: {res_d6.problems}"

    res_d7 = scripts_check_dod.check_d7(ctx)
    assert res_d7.ok is True, f"D7 failed: {res_d7.problems}"
