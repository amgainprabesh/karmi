"""Tests for Raster & Blueprint Extractor Calibration & Tolerance Tuning.

Following Extreme Programming (XP) TDD: Tests are written first before
implementing blueprint polarity detection, tolerance calibration, and
quality scoring in core/raster.py.
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest
from PIL import Image

from conftest import require

raster = require("core.raster")


def test_detect_blueprint_polarity_standard():
    """Standard drawing has white background and dark ink."""
    # 200x200 mostly white (0.95), with dark line (0.10) in the middle
    arr = np.full((200, 200), 0.95, dtype=np.float32)
    arr[98:102, 20:180] = 0.10

    is_inverted, reason = raster.detect_blueprint_polarity(arr)
    assert not is_inverted
    assert "standard" in reason.lower() or "white background" in reason.lower()


def test_detect_blueprint_polarity_ammonia_blueprint():
    """Ammonia / blueprint has dark background and bright lines."""
    # 200x200 dark background (0.15) with bright lines (0.90)
    arr = np.full((200, 200), 0.15, dtype=np.float32)
    arr[98:102, 20:180] = 0.90
    arr[20:180, 98:102] = 0.90

    is_inverted, reason = raster.detect_blueprint_polarity(arr)
    assert is_inverted
    assert "ammonia" in reason.lower() or "inverted" in reason.lower() or "dark background" in reason.lower()


def test_extract_plan_auto_inverts_blueprint(tmp_path: Path):
    """extract_plan with auto_invert=True recovers lines from inverted blueprint."""
    # Create an inverted blueprint image on disk
    arr = np.full((300, 300), 30, dtype=np.uint8)  # dark background
    # Add horizontal and vertical white lines
    arr[145:155, 30:270] = 240
    arr[30:270, 145:155] = 240
    img_path = tmp_path / "ammonia_blueprint.png"
    Image.fromarray(arr).save(img_path)

    res = raster.extract_plan(img_path, auto_invert=True)
    assert isinstance(res, dict)
    assert len(res["segments"]) >= 2
    assert any("inverted" in w.lower() or "ammonia" in w.lower() or "polarity" in w.lower() for w in res["warnings"])
    assert res["meta"].get("polarity_inverted") is True


def test_blueprint_quality_score():
    """Blueprint quality score grades input image and outputs Nepali diagnostics."""
    stats_clean = {
        "contrast": 0.75,
        "bg_mean": 0.92,
        "bg_std": 0.03,
        "speckle": 0.02,
        "blank": False,
        "degraded": False,
    }
    score_clean = raster.blueprint_quality_score(stats_clean)
    assert score_clean["overall_score"] >= 80
    assert score_clean["grade"] == "A"
    assert score_clean["is_acceptable_for_diff"] is True
    assert "राम्रो" in score_clean["diagnostic_np"] or "उपयुक्त" in score_clean["diagnostic_np"]

    stats_noisy = {
        "contrast": 0.20,
        "bg_mean": 0.65,
        "bg_std": 0.22,
        "speckle": 0.35,
        "blank": False,
        "degraded": True,
    }
    score_noisy = raster.blueprint_quality_score(stats_noisy)
    assert score_noisy["overall_score"] < 50
    assert score_noisy["grade"] in ("C", "D")
    assert score_noisy["is_acceptable_for_diff"] is False
    assert "कमजोर" in score_noisy["diagnostic_np"] or "पुनः" in score_noisy["diagnostic_np"] or "स्पष्ट" in score_noisy["diagnostic_np"]


def test_calibrate_tolerances_dpi_scaling():
    """Tolerances scale proportionally with DPI to preserve physical dimension thresholds."""
    tol_100 = raster.calibrate_tolerances(dpi=100)
    tol_200 = raster.calibrate_tolerances(dpi=200)
    tol_300 = raster.calibrate_tolerances(dpi=300)

    assert tol_200["min_len_px"] == pytest.approx(2.0 * tol_100["min_len_px"], rel=0.1)
    assert tol_300["min_len_px"] == pytest.approx(1.5 * tol_200["min_len_px"], rel=0.1)
    assert tol_300["max_gap_px"] >= tol_100["max_gap_px"]
    assert 1.0 <= tol_200["angle_tol_deg"] <= 5.0
