"""Karmi — Municipal Building Bylaws, Setbacks & Ground Coverage Engine.

Evaluates building layout and plot configuration against local municipal
building bylaws (Basic By-laws 2072, Kathmandu Valley, Kirtipur, Pokhara).

Honesty Invariants:
* Setback and coverage thresholds are municipal advisory checks, NEVER legal determinations.
* Findings are phrased strictly as "items to verify" (जाँच गर्नुपर्ने कुरा).
* The words "violation", "violates", "illegal", and "non-compliant" are FORBIDDEN.
* Every recommendation cites its source (e.g. Basic By-laws 2072 Rule 5.2).
"""

from __future__ import annotations

from typing import Any, Sequence
from pydantic import BaseModel, Field

from core import nepali
from core.geometry import polygon_area
from core.schema import (
    Opening,
    OpeningKind,
    Room,
    SceneGraph,
    Severity,
    VerifyItem,
    Wall,
)


class MunicipalProfile(BaseModel):
    """Bylaw configuration profile for a municipality or region."""

    name: str
    source_citation: str
    front_setback_local_m: float = 1.5
    front_setback_main_m: float = 6.0
    side_setback_with_openings_m: float = 1.5
    rear_setback_with_openings_m: float = 1.5
    max_ground_coverage_small_plot: float = 0.70  # plots <= 250 m²
    max_ground_coverage_large_plot: float = 0.60  # plots > 250 m²
    max_far: float = 1.75                         # residential FAR advisory baseline


NATIONAL_BASELINE = MunicipalProfile(
    name="National Baseline (Basic By-laws 2072)",
    source_citation="Basic By-laws 2072 / MoFAGA PLGSP Resource Book (2023) Rule 5.2 & 5.5",
    front_setback_local_m=1.5,
    front_setback_main_m=6.0,
    side_setback_with_openings_m=1.5,
    rear_setback_with_openings_m=1.5,
    max_ground_coverage_small_plot=0.70,
    max_ground_coverage_large_plot=0.60,
    max_far=1.75,
)

KATHMANDU_VALLEY = MunicipalProfile(
    name="Kathmandu Valley Building Bylaws",
    source_citation="Kathmandu Valley Development Authority (KVDA) Bylaws 2064/2072",
    front_setback_local_m=1.5,
    front_setback_main_m=6.0,
    side_setback_with_openings_m=1.5,
    rear_setback_with_openings_m=1.5,
    max_ground_coverage_small_plot=0.70,
    max_ground_coverage_large_plot=0.60,
    max_far=1.75,
)

KIRTIPUR = MunicipalProfile(
    name="Kirtipur Municipality Building Bylaws",
    source_citation="Kirtipur Municipality Planning & Building By-laws (2008)",
    front_setback_local_m=1.0,
    front_setback_main_m=6.0,
    side_setback_with_openings_m=1.5,
    rear_setback_with_openings_m=1.5,
    max_ground_coverage_small_plot=0.70,
    max_ground_coverage_large_plot=0.60,
    max_far=1.50,
)

POKHARA = MunicipalProfile(
    name="Pokhara Metropolitan City Building Bylaws",
    source_citation="Pokhara Metropolitan Building By-laws (2075)",
    front_setback_local_m=1.5,
    front_setback_main_m=6.0,
    side_setback_with_openings_m=1.5,
    rear_setback_with_openings_m=1.5,
    max_ground_coverage_small_plot=0.65,
    max_ground_coverage_large_plot=0.60,
    max_far=1.75,
)

_PROFILES: dict[str, MunicipalProfile] = {
    "national": NATIONAL_BASELINE,
    "baseline": NATIONAL_BASELINE,
    "kathmandu": KATHMANDU_VALLEY,
    "ktm": KATHMANDU_VALLEY,
    "lalitpur": KATHMANDU_VALLEY,
    "bhaktapur": KATHMANDU_VALLEY,
    "kirtipur": KIRTIPUR,
    "pokhara": POKHARA,
}


def get_municipal_profile(name: str | None = None) -> MunicipalProfile:
    """Retrieve municipal profile by name or default to National Baseline."""
    if not name:
        return NATIONAL_BASELINE
    key = str(name).strip().lower()
    return _PROFILES.get(key, NATIONAL_BASELINE)


def check_wall_setbacks(
    wall: Wall,
    openings_on_wall: Sequence[Opening],
    distance_to_boundary_m: float,
    *,
    boundary_type: str = "side",
    road_type: str = "local",
    profile: MunicipalProfile | None = None,
) -> list[VerifyItem]:
    """Check wall distance to plot/road boundary against municipal bylaws."""
    prof = profile or NATIONAL_BASELINE
    items: list[VerifyItem] = []
    has_openings = any(op.kind in (OpeningKind.DOOR, OpeningKind.WINDOW, OpeningKind.VENT) for op in openings_on_wall)
    w_label = wall.id or "Wall"

    if boundary_type == "front":
        required = prof.front_setback_main_m if road_type.lower() in ("main", "feeder", "highway") else prof.front_setback_local_m
        if distance_to_boundary_m < required:
            items.append(
                VerifyItem(
                    id=f"v_setback_front_{wall.id}",
                    item=f"Verify front setback from road Right-of-Way ({distance_to_boundary_m:.2f} m measured vs {required:.2f} m recommended)",
                    item_np=f"सडक सीमाबाट अगाडिको सेटब्याक दूरी ({nepali.format_dimension_np(distance_to_boundary_m)}) जाँच्नुहोस्",
                    why=f"{prof.source_citation} recommends minimum front setback of {required:.2f} m from road boundary.",
                    how="Verify road center and Right-of-Way (ROW) boundary with local ward surveyor.",
                    severity=Severity.MEDIUM if distance_to_boundary_m < (required * 0.75) else Severity.LOW,
                )
            )
    else:  # side or rear
        if has_openings:
            required = prof.side_setback_with_openings_m if boundary_type == "side" else prof.rear_setback_with_openings_m
            if distance_to_boundary_m < required:
                items.append(
                    VerifyItem(
                        id=f"v_setback_{boundary_type}_{wall.id}",
                        item=f"Verify {boundary_type} setback for {w_label} with openings ({distance_to_boundary_m:.2f} m measured vs {required:.2f} m recommended)",
                        item_np=f"झ्याल/ढोका भएको {w_label}को {boundary_type} सेटब्याक ({nepali.format_dimension_np(distance_to_boundary_m)}) जाँच्नुहोस्",
                        why=f"{prof.source_citation} requires minimum {required:.2f} m setback when openings face neighboring property (under {required:.2f} m requires a dead wall).",
                        how="Review opening placement with architect or verify if neighboring consent/dead-wall applies.",
                        severity=Severity.MEDIUM if distance_to_boundary_m < 1.0 else Severity.LOW,
                    )
                )

    return items


def check_ground_coverage(
    plinth_area_m2: float,
    plot_area_m2: float,
    *,
    profile: MunicipalProfile | None = None,
) -> list[VerifyItem]:
    """Check building ground coverage percentage against plot size limits."""
    if plot_area_m2 <= 0.0 or plinth_area_m2 <= 0.0:
        return []
    prof = profile or NATIONAL_BASELINE
    max_ratio = prof.max_ground_coverage_small_plot if plot_area_m2 <= 250.0 else prof.max_ground_coverage_large_plot
    actual_ratio = plinth_area_m2 / plot_area_m2

    if actual_ratio > max_ratio:
        max_pct_str = f"{max_ratio * 100:.0f}%"
        actual_pct_str = f"{actual_ratio * 100:.1f}%"
        return [
            VerifyItem(
                id="v_ground_coverage",
                item=f"Verify ground coverage ({actual_pct_str} of plot vs {max_pct_str} recommended)",
                item_np=f"जमिन ओगटेको प्रतिशत ({nepali.format_percent_np(actual_ratio)}) जाँच्नुहोस्",
                why=f"{prof.source_citation} specifies maximum ground coverage of {max_pct_str} for plots of {plot_area_m2:.0f} m².",
                how="Confirm plinth dimensions and open space calculation with site supervisor.",
                severity=Severity.MEDIUM if actual_ratio > (max_ratio + 0.05) else Severity.LOW,
            )
        ]
    return []


def check_far_advisory(
    total_built_area_m2: float,
    plot_area_m2: float,
    *,
    profile: MunicipalProfile | None = None,
) -> list[VerifyItem]:
    """Advisory check for Floor Area Ratio (FAR)."""
    if plot_area_m2 <= 0.0 or total_built_area_m2 <= 0.0:
        return []
    prof = profile or NATIONAL_BASELINE
    far = total_built_area_m2 / plot_area_m2
    if far > prof.max_far:
        return [
            VerifyItem(
                id="v_far_advisory",
                item=f"Advisory: Floor Area Ratio (FAR {far:.2f} vs {prof.max_far:.2f} standard)",
                item_np=f"फ्लोर एरिया रेसियो (FAR {nepali.format_confidence_np(far)}) जाँच्नुहोस्",
                why=f"{prof.source_citation} advises residential FAR baseline of {prof.max_far:.2f}.",
                how="Check permissible floor area with municipality building department.",
                severity=Severity.LOW,
            )
        ]
    return []


def evaluate_municipal_compliance(
    scene: SceneGraph,
    plot_meta: dict[str, Any] | None = None,
    *,
    profile_name: str | None = None,
) -> tuple[list[VerifyItem], dict[str, Any]]:
    """Evaluate scene geometry and plot metadata against municipal bylaws."""
    prof = get_municipal_profile(profile_name)
    meta_in = plot_meta or {}
    items: list[VerifyItem] = []
    checks_run = 0

    # 1. Ground coverage
    plot_area = float(meta_in.get("plot_area_m2", 0.0) or 0.0)
    plinth_area = float(meta_in.get("plinth_area_m2", 0.0) or 0.0)
    if plot_area > 0 and plinth_area > 0:
        checks_run += 1
        items.extend(check_ground_coverage(plinth_area, plot_area, profile=prof))

    # 2. FAR
    built_area = float(meta_in.get("total_built_area_m2", 0.0) or 0.0)
    if plot_area > 0 and built_area > 0:
        checks_run += 1
        items.extend(check_far_advisory(built_area, plot_area, profile=prof))

    # 3. Front setback
    front_setback = float(meta_in.get("front_setback_m", 0.0) or 0.0)
    if front_setback > 0:
        checks_run += 1
        dummy_wall = Wall(id="W_FRONT", start=(0, 0), end=(1, 0))
        items.extend(check_wall_setbacks(dummy_wall, [], front_setback, boundary_type="front", profile=prof))

    # 4. Side setbacks
    side_setback = float(meta_in.get("side_setback_m", 0.0) or 0.0)
    has_side_openings = bool(meta_in.get("has_side_openings", True))
    if side_setback > 0:
        checks_run += 1
        dummy_wall = Wall(id="W_SIDE", start=(0, 0), end=(1, 0))
        dummy_ops = [Opening(id="O_DUMMY", kind=OpeningKind.WINDOW, center=(0, 0))] if has_side_openings else []
        items.extend(check_wall_setbacks(dummy_wall, dummy_ops, side_setback, boundary_type="side", profile=prof))

    summary_meta = {
        "profile": prof.name,
        "source": prof.source_citation,
        "checks_run": checks_run,
        "items_flagged": len(items),
    }
    return items, summary_meta


__all__ = [
    "MunicipalProfile",
    "NATIONAL_BASELINE",
    "KATHMANDU_VALLEY",
    "KIRTIPUR",
    "POKHARA",
    "get_municipal_profile",
    "check_wall_setbacks",
    "check_ground_coverage",
    "check_far_advisory",
    "evaluate_municipal_compliance",
]
