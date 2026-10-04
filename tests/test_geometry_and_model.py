"""Structural sanity of the drawing -> scene-graph extractor (``core.model``).

The whole module skips while ``core.model`` is not importable (another agent
is writing it). Once it imports, a scene graph that cannot describe the sample
house turns the suite red — that is the signal.
"""

from __future__ import annotations

import pytest

from core import schema as S
from conftest import call_adaptive, require, require_attr

model_mod = require(
    "core.model",
    reason="core.model is not importable yet (extractor being written in parallel) — skipping the drawing tests",
)


def _build(pdf_path):
    build_scene_graph = require_attr(model_mod, "build_scene_graph")
    return call_adaptive(
        build_scene_graph, pdf_path, scale_m_per_unit=None, north_deg=None, ai=None
    )


def _opening_widths(scene: S.SceneGraph):
    return sorted(round(o.width, 3) for o in scene.openings if o.width is not None)


def test_base_drawing_builds_a_structurally_sane_scene(naksa_base):
    scene = _build(naksa_base)

    assert isinstance(scene, S.SceneGraph)
    assert len(scene.walls) >= 4, (
        f"expected >= 4 walls for the sample house (4 external + partitions), got {scene.summary()}"
    )
    assert len(scene.rooms) >= 1, f"expected >= 1 closed room polygon, got {scene.summary()}"

    assert scene.bbox is not None, "a dimensioned vector drawing should yield a bbox"
    minx, miny, maxx, maxy = scene.bbox
    width, height = abs(maxx - minx), abs(maxy - miny)
    assert 6.0 <= width <= 16.0, (
        f"bbox width {width:.2f} is not plausible for a ~10 m house — unit conversion bug?"
    )
    assert 4.0 <= height <= 12.0, (
        f"bbox height {height:.2f} is not plausible for a ~7.5 m house — unit conversion bug?"
    )

    for wall in scene.walls:
        assert wall.length > 0
        if wall.thickness is not None:
            assert 0.05 <= wall.thickness <= 1.0, (
                f"wall {wall.id} thickness {wall.thickness} is not a metre value"
            )
    for opening in scene.openings:
        if opening.width is not None:
            assert 0.4 <= opening.width <= 3.5, (
                f"opening {opening.id} width {opening.width} is not plausible"
            )


def test_sparse_drawing_warns_without_raising(naksa_sparse):
    scene = _build(naksa_sparse)
    assert isinstance(scene, S.SceneGraph)
    assert scene.warnings, (
        "a walls-only drawing (no text, no north arrow) should produce at least one warning"
    )


def test_drift_drawing_differs_from_base_in_an_opening_width(naksa_base, naksa_drift):
    base = _build(naksa_base)
    drift = _build(naksa_drift)

    widths_base = _opening_widths(base)
    widths_drift = _opening_widths(drift)
    if not widths_base and not widths_drift:
        pytest.skip("extractor found no opening widths yet — cannot compare base vs drift")

    assert widths_base != widths_drift, (
        "the drift drawing should differ from base in at least one opening width; "
        f"base={widths_base} drift={widths_drift}"
    )