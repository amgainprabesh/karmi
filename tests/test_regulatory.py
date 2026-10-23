"""Tests for Karmi NBC 206 Regulatory Conformance Verification Engine.

Following Extreme Programming (XP) TDD: Tests are written first before
implementing core/regulatory.py and wiring into core/diff.py.
"""

from __future__ import annotations

import re
import pytest

from core.schema import (
    Delta,
    DeltaStatus,
    ElementKind,
    ObservedElement,
    ObservedState,
    Opening,
    OpeningKind,
    Provenance,
    Room,
    SceneGraph,
    Severity,
    VerifyItem,
    Wall,
)
from core.diff import diff_scene


def _make_provenance() -> Provenance:
    return Provenance(source="vector_geometry", confidence=0.95)


def test_habitable_room_minimum_area_check():
    """NBC 206 §3.2.2 requires habitable room area >= 6.0 m²."""
    from core.regulatory import check_room_dimensions

    # Compliant bedroom (12 m²)
    room_ok = Room(
        id="R1",
        name="Bedroom",
        polygon=[(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)],
        area_m2=12.0,
        provenance=_make_provenance(),
    )
    items_ok = check_room_dimensions(room_ok)
    assert len(items_ok) == 0

    # Sub-standard room (4.5 m²)
    room_small = Room(
        id="R2",
        name="Bedroom 2",
        polygon=[(0.0, 0.0), (2.5, 0.0), (2.5, 1.8), (0.0, 1.8)],
        area_m2=4.5,
        provenance=_make_provenance(),
    )
    items_small = check_room_dimensions(room_small)
    assert len(items_small) >= 1
    item = items_small[0]
    assert isinstance(item, VerifyItem)
    assert "NBC 206" in (item.why or "")
    assert "6" in (item.why or "") or "6.0" in (item.why or "")
    assert item.item_np is not None
    # Honesty invariant: no forbidden words
    for text in (item.item, item.why or "", item.how or "", item.item_np or ""):
        assert "violation" not in text.lower()
        assert "violat" not in text.lower()
        assert "illegal" not in text.lower()


def test_kitchen_minimum_area_and_dimension():
    """NBC 206 §3.2.2 requires kitchen area >= 5.0 m² and min dimension >= 1.8 m."""
    from core.regulatory import check_room_dimensions

    kitchen_narrow = Room(
        id="R_KITCHEN",
        name="Kitchen",
        polygon=[(0.0, 0.0), (1.5, 0.0), (1.5, 2.66), (0.0, 2.66)],
        area_m2=4.0,
        provenance=_make_provenance(),
    )
    items = check_room_dimensions(kitchen_narrow)
    assert len(items) >= 1
    assert any("kitchen" in it.item.lower() or "भान्सा" in (it.item_np or "") for it in items)
    assert any("NBC 206" in (it.why or "") for it in items)


def test_toilet_minimum_area():
    """NBC 206 §3.2.2 requires toilet/WC area >= 1.2 m²."""
    from core.regulatory import check_room_dimensions

    toilet_tiny = Room(
        id="R_WC",
        name="Toilet",
        polygon=[(0.0, 0.0), (0.8, 0.0), (0.8, 1.0), (0.0, 1.0)],
        area_m2=0.8,
        provenance=_make_provenance(),
    )
    items = check_room_dimensions(toilet_tiny)
    assert len(items) >= 1
    assert any("toilet" in it.item.lower() or "शौचालय" in (it.item_np or "") for it in items)


def test_exit_door_clear_width():
    """NBC 206 §2.2.1 requires residential exit doors to have clear width >= 0.9 m."""
    from core.regulatory import check_door_width

    door_ok = Opening(
        id="D1",
        kind=OpeningKind.DOOR,
        wall_id="W1",
        center=(2.0, 0.0),
        width=0.95,
        height=2.1,
        provenance=_make_provenance(),
    )
    assert len(check_door_width(door_ok, is_exit=True)) == 0

    door_narrow = Opening(
        id="D2",
        kind=OpeningKind.DOOR,
        wall_id="W1",
        center=(2.0, 0.0),
        width=0.75,
        height=2.0,
        provenance=_make_provenance(),
    )
    items = check_door_width(door_narrow, is_exit=True)
    assert len(items) >= 1
    assert "NBC 206" in (items[0].why or "")
    assert items[0].delta_ref is None
    assert items[0].severity in (Severity.LOW, Severity.MEDIUM)


def test_room_natural_light_opening_ratio():
    """NBC 206 §3.3 requires natural light opening area >= 10% (1/10) of habitable room area in Hills."""
    from core.regulatory import check_room_natural_light

    room = Room(
        id="R_BED",
        name="Master Bed",
        polygon=[(0.0, 0.0), (5.0, 0.0), (5.0, 3.0), (0.0, 3.0)],
        area_m2=15.0,  # 15 m² requires at least 1.5 m² window area
        provenance=_make_provenance(),
    )

    # Window too small: 1.0m width x 1.0m height = 1.0 m² (< 1.5 m²)
    window_small = Opening(
        id="O_WIN",
        kind=OpeningKind.WINDOW,
        wall_id="W1",
        center=(1.5, 0.0),
        width=1.0,
        height=1.0,
        provenance=_make_provenance(),
    )

    items = check_room_natural_light(room, [window_small], region="hills")
    assert len(items) == 1
    assert "10%" in items[0].why or "1/10" in items[0].why
    assert "NBC 206" in items[0].why

    # Sufficient window: add another 1.2m x 1.0m window (total 2.2 m² > 1.5 m²)
    window_2 = Opening(
        id="O_WIN2",
        kind=OpeningKind.WINDOW,
        wall_id="W2",
        center=(3.5, 0.0),
        width=1.2,
        height=1.0,
        provenance=_make_provenance(),
    )
    items_ok = check_room_natural_light(room, [window_small, window_2], region="hills")
    assert len(items_ok) == 0


def test_regulatory_integration_in_diff_scene():
    """Integration check: diff_scene() evaluates NBC regulatory rules and adds to verify_list."""
    wall = Wall(
        id="W1",
        start=(0.0, 0.0),
        end=(5.0, 0.0),
        thickness=0.23,
        is_external=True,
        provenance=_make_provenance(),
    )
    # Undersized door on external wall
    door = Opening(
        id="D1",
        kind=OpeningKind.DOOR,
        wall_id="W1",
        center=(2.5, 0.0),
        width=0.75,  # < 0.9 m
        height=2.0,
        provenance=_make_provenance(),
    )
    room = Room(
        id="R1",
        name="Small Bed",
        polygon=[(0.0, 0.0), (2.6, 0.0), (2.6, 2.0), (0.0, 2.0)],
        area_m2=5.2,  # < 6.0 m²
        provenance=_make_provenance(),
    )
    scene = SceneGraph(
        walls=[wall],
        openings=[door],
        rooms=[room],
        scale_m_per_unit=1.0,
    )
    observed = ObservedState()

    report = diff_scene(scene, observed)

    # Must contain regulatory items in verify_list
    assert len(report.verify_list) > 0
    reg_items = [it for it in report.verify_list if "NBC 206" in (it.why or "")]
    assert len(reg_items) >= 2  # door and room

    # Check report.meta contains regulatory summary
    assert "regulatory" in report.meta
    assert report.meta["regulatory"]["checks_run"] > 0
    assert report.meta["regulatory"]["items_flagged"] >= 2

    # Invariant: no "violation" in entire report
    dumped = report.model_dump_json()
    assert "violation" not in dumped.lower()
    assert "violat" not in dumped.lower()
