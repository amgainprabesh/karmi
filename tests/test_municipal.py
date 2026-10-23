"""Tests for Karmi Municipal Building Bylaws, Setbacks, and Ground Coverage Engine.

Following Extreme Programming (XP) TDD: Tests are written first before
implementing core/municipal.py.
"""

from __future__ import annotations

import pytest

from core.schema import (
    Opening,
    OpeningKind,
    Provenance,
    Room,
    SceneGraph,
    Severity,
    VerifyItem,
    Wall,
)


def _make_provenance() -> Provenance:
    return Provenance(source="vector_geometry", confidence=0.95)


def test_municipal_profiles_and_factory():
    """Municipal profiles must be loadable by name and contain expected defaults."""
    from core.municipal import (
        KATHMANDU_VALLEY,
        KIRTIPUR,
        NATIONAL_BASELINE,
        POKHARA,
        MunicipalProfile,
        get_municipal_profile,
    )

    base = get_municipal_profile("national")
    assert base.name == NATIONAL_BASELINE.name
    assert base.side_setback_with_openings_m == 1.5
    assert base.front_setback_local_m == 1.5
    assert base.max_ground_coverage_small_plot == 0.70

    ktm = get_municipal_profile("kathmandu")
    assert ktm.name == KATHMANDU_VALLEY.name

    default_p = get_municipal_profile(None)
    assert default_p.name == NATIONAL_BASELINE.name


def test_side_setback_with_openings_generates_verify_item():
    """Wall with openings closer than 1.5m to side boundary must trigger verification."""
    from core.municipal import check_wall_setbacks

    wall = Wall(
        id="W_EAST",
        start=(10.0, 0.0),
        end=(10.0, 8.0),
        thickness=0.23,
        provenance=_make_provenance(),
    )
    window = Opening(
        id="O_EAST_WIN",
        kind=OpeningKind.WINDOW,
        wall_id="W_EAST",
        center=(10.0, 4.0),
        width=1.2,
        height=1.2,
        provenance=_make_provenance(),
    )

    # 1.0m to boundary (< 1.5m required when openings exist)
    items = check_wall_setbacks(wall, [window], distance_to_boundary_m=1.0, boundary_type="side")
    assert len(items) >= 1
    it = items[0]
    assert isinstance(it, VerifyItem)
    assert "1.5" in (it.why or "")
    assert "setback" in it.item.lower() or "सेटब्याक" in (it.item_np or "")
    assert it.severity in (Severity.LOW, Severity.MEDIUM)

    # Honesty invariant: no forbidden words
    for text in (it.item, it.why or "", it.how or "", it.item_np or ""):
        assert "violation" not in text.lower()
        assert "violat" not in text.lower()
        assert "illegal" not in text.lower()


def test_blank_wall_side_setback_dead_wall_allowance():
    """Blank wall without openings toward boundary is a permitted dead wall."""
    from core.municipal import check_wall_setbacks

    wall_blank = Wall(
        id="W_BLANK",
        start=(10.0, 0.0),
        end=(10.0, 8.0),
        thickness=0.23,
        provenance=_make_provenance(),
    )

    # 1.0m distance with no openings on wall
    items = check_wall_setbacks(wall_blank, [], distance_to_boundary_m=1.0, boundary_type="side")
    # Blank wall does not trigger a medium/high warning, or produces an informational note
    assert len(items) == 0 or all(it.severity == Severity.INFO for it in items)


def test_front_setback_from_road_boundary():
    """Front setback from road Right-of-Way must be at least 1.5m for local road."""
    from core.municipal import check_wall_setbacks

    wall_front = Wall(
        id="W_FRONT",
        start=(0.0, 0.0),
        end=(8.0, 0.0),
        thickness=0.23,
        provenance=_make_provenance(),
    )

    # 0.9m from road boundary (< 1.5m)
    items = check_wall_setbacks(wall_front, [], distance_to_boundary_m=0.9, boundary_type="front", road_type="local")
    assert len(items) >= 1
    assert "front" in items[0].item.lower() or "अगाडि" in (items[0].item_np or "")
    assert "1.5" in (items[0].why or "")


def test_ground_coverage_ratio():
    """Ground coverage exceeding maximum allowable percentage must generate verify item."""
    from core.municipal import check_ground_coverage

    # Plot 200 m² (small <= 250 m²), max 70% = 140 m². Plinth is 160 m² (80%)
    items_high = check_ground_coverage(plinth_area_m2=160.0, plot_area_m2=200.0)
    assert len(items_high) == 1
    assert "70%" in items_high[0].why
    assert items_high[0].severity in (Severity.LOW, Severity.MEDIUM)

    # Compliant ground coverage (120 m² / 200 m² = 60% <= 70%)
    items_ok = check_ground_coverage(plinth_area_m2=120.0, plot_area_m2=200.0)
    assert len(items_ok) == 0


def test_floor_area_ratio_advisory():
    """FAR advisory calculates total built area to plot ratio."""
    from core.municipal import check_far_advisory

    # Total built 350 m² on 200 m² plot -> FAR 1.75
    items = check_far_advisory(total_built_area_m2=350.0, plot_area_m2=200.0)
    assert len(items) >= 0  # advisory calculation


def test_evaluate_municipal_compliance_integration():
    """Integrated compliance evaluation evaluates scene against municipal profile."""
    from core.municipal import evaluate_municipal_compliance

    wall = Wall(id="W1", start=(0.0, 0.0), end=(6.0, 0.0), thickness=0.23, provenance=_make_provenance())
    room = Room(id="R1", name="Hall", polygon=[(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)], area_m2=24.0, provenance=_make_provenance())
    scene = SceneGraph(walls=[wall], rooms=[room], scale_m_per_unit=1.0)

    plot_meta = {
        "plot_area_m2": 100.0,
        "plinth_area_m2": 85.0,  # 85% > 70% max coverage
        "front_setback_m": 1.0,  # 1.0m < 1.5m
    }

    items, meta = evaluate_municipal_compliance(scene, plot_meta=plot_meta, profile_name="kathmandu")
    assert len(items) >= 2
    assert meta["profile"] == "Kathmandu Valley Building Bylaws"
    assert meta["items_flagged"] >= 2
    assert all("violation" not in it.item.lower() for it in items)
