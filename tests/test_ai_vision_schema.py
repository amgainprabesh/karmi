"""Tests for AI Vision Structured Schema & Multi-Photo Consensus.

Following Extreme Programming (XP) TDD: Tests are written first before
implementing perspective/occlusion schema extensions and multi-photo consensus
clustering in core/ai/vision.py.
"""

from __future__ import annotations

import pytest
from core.schema import ElementKind, Stage
from core.ai.vision import (
    PhotoElement,
    PhotoObservation,
    multi_photo_consensus,
)


def test_photo_element_occlusion_and_perspective():
    """PhotoElement parses occlusion and perspective, damping confidence appropriately."""
    el = PhotoElement(
        kind=ElementKind.WALL,
        approx_size={"length": 10.0, "height": 3.0},
        location_hint="south wall",
        confidence=0.70,
        occlusion="heavy",
        perspective="oblique",
    )
    assert el.occlusion == "heavy"
    assert el.perspective == "oblique"
    # When heavy occlusion or oblique perspective is flagged, confidence is dampened
    assert el.effective_confidence < 0.70
    assert el.effective_confidence <= 0.55


def test_photo_element_occlusion_coercion():
    """Defensively coerce fuzzy model outputs for occlusion and perspective."""
    el = PhotoElement.model_validate({
        "kind": "wall",
        "occlusion": "partially covered by scaffolding",
        "perspective": "angled view from corner",
        "confidence": 0.60,
    })
    assert el.occlusion == "partial"
    assert el.perspective == "oblique"


def test_multi_photo_consensus_stage_agreement():
    """When multiple photos agree on construction stage, consensus stage is selected."""
    captures = [
        {"file": "p1.jpg", "stage": "walls", "stage_confidence": 0.85, "view": "front"},
        {"file": "p2.jpg", "stage": "walls", "stage_confidence": 0.80, "view": "side"},
        {"file": "p3.jpg", "stage": "columns", "stage_confidence": 0.40, "view": "rear"},
    ]
    consensus = multi_photo_consensus(captures, [])
    assert consensus["stage"] == Stage.WALLS.value
    assert consensus["stage_discrepancy"] is False
    assert len(consensus["warnings"]) == 0


def test_multi_photo_consensus_stage_discrepancy():
    """Conflicting stage estimates across captures generate an explicit verification warning."""
    captures = [
        {"file": "p1.jpg", "stage": "foundation", "stage_confidence": 0.90, "view": "front"},
        {"file": "p2.jpg", "stage": "roof", "stage_confidence": 0.85, "view": "aerial"},
    ]
    consensus = multi_photo_consensus(captures, [])
    assert consensus["stage_discrepancy"] is True
    assert any("discrepancy" in w.lower() or "conflict" in w.lower() for w in consensus["warnings"])


def test_multi_photo_consensus_element_clustering():
    """Corroborated elements across multiple photos are merged with averaged dimensions and source attribution."""
    captures = [
        {"file": "front.jpg", "stage": "walls", "stage_confidence": 0.8, "view": "front"},
        {"file": "angle.jpg", "stage": "walls", "stage_confidence": 0.8, "view": "side"},
    ]
    elements = [
        {
            "file": "front.jpg",
            "kind": "wall",
            "approx_size": {"length": 10.0, "height": 3.0},
            "location_hint": "main front facade",
            "confidence": 0.60,
            "evidence": "front elevation view",
        },
        {
            "file": "angle.jpg",
            "kind": "wall",
            "approx_size": {"length": 10.4, "height": 2.9},
            "location_hint": "main front facade",
            "confidence": 0.55,
            "evidence": "angled side view showing front wall",
        },
        {
            "file": "angle.jpg",
            "kind": "opening",
            "approx_size": {"width": 1.2, "height": 1.5},
            "location_hint": "side window",
            "confidence": 0.50,
            "evidence": "side window opening",
        },
    ]

    consensus = multi_photo_consensus(captures, elements)
    merged_elements = consensus["elements"]

    # 3 raw elements merged into 2 consensus elements (the 2 front wall sightings clustered into 1)
    assert len(merged_elements) == 2
    front_wall = next(el for el in merged_elements if el["kind"] == "wall")

    assert front_wall["corroboration_count"] == 2
    assert "front.jpg" in front_wall["source_files"]
    assert "angle.jpg" in front_wall["source_files"]
    # Averaged length is (10.0 + 10.4) / 2 = 10.2
    assert front_wall["approx_size"]["length"] == pytest.approx(10.2, abs=0.05)
    # Corroborated confidence is boosted but strictly <= 0.70
    assert front_wall["confidence"] > 0.60
    assert front_wall["confidence"] <= 0.70
