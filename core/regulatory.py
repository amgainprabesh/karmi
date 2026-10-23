"""Karmi — National Building Code (NBC 206) Regulatory Conformance Verification.

This module evaluates architectural geometry against Nepal National Building
Code (NBC 206: Architectural Design Requirements, 2015/2024) guidelines.

Honesty Invariants:
* Karmi NEVER issues legal determinations, compliance certifications, or
  accusations. Findings are strictly "items to verify" (जाँच गर्नुपर्ने कुरा).
* The words "violation", "violates", "illegal", and "non-compliant" are FORBIDDEN.
* Every recommendation cites its specific regulatory section (e.g. NBC 206 §3.2.2).
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from core import nepali
from core.geometry import polygon_area
from core.schema import (
    Delta,
    DeltaStatus,
    ElementKind,
    ObservedElement,
    ObservedState,
    Opening,
    OpeningKind,
    Room,
    SceneGraph,
    Severity,
    VerifyItem,
    Wall,
)

# --------------------------------------------------------------------------- #
# NBC 206 thresholds (Nepal National Building Code)
# Citable references: docs/research/nbc-rules.md
# --------------------------------------------------------------------------- #
# Habitable rooms (§3.2.2)
NBC_HABITABLE_MIN_AREA_M2 = 6.0
NBC_HABITABLE_MIN_DIM_M = 2.0

# Kitchen (§3.2.2)
NBC_KITCHEN_MIN_AREA_M2 = 5.0
NBC_KITCHEN_MIN_DIM_M = 1.8

# Toilet & Bath (§3.2.2)
NBC_TOILET_MIN_AREA_M2 = 1.2
NBC_TOILET_MIN_DIM_M = 0.9
NBC_BATH_MIN_AREA_M2 = 1.8
NBC_BATH_MIN_DIM_M = 1.2

# Doors (§2.2.1)
NBC_EXIT_DOOR_MIN_WIDTH_M = 0.90
NBC_INTERNAL_DOOR_MIN_WIDTH_M = 0.75

# Lighting & Ventilation ratio (§3.3)
NBC_LIGHT_RATIO_HILLS = 0.10     # 1/10 of room area in Hill / Mountain regions
NBC_LIGHT_RATIO_TERAI = 0.125    # 1/8 of room area in other regions
NBC_VENT_RATIO = 0.0625          # 1/16 of room area


def classify_room_kind(room: Room) -> str:
    """Classify room into 'habitable', 'kitchen', 'toilet', 'bath', 'stair', 'corridor', or 'other'."""
    text = f"{room.name or ''} {room.name_np or ''}".lower()
    if any(k in text for k in ("kitchen", "भान्सा")):
        return "kitchen"
    if any(k in text for k in ("toilet", "wc", "शौचालय")):
        return "toilet"
    if any(k in text for k in ("bath", "स्नान")):
        return "bath"
    if any(k in text for k in ("stair", "सिँढी")):
        return "stair"
    if any(k in text for k in ("store", "भण्डार", "storage", "passage", "corridor", "balcony", "बाल्कनी")):
        return "other"
    # Default to habitable for bedrooms, living rooms, halls, dining, or unnamed rooms
    return "habitable"


def room_bounding_dimensions(room: Room) -> tuple[float, float]:
    """Compute (min_dimension, max_dimension) in metres from room polygon."""
    if not room.polygon or len(room.polygon) < 3:
        return (0.0, 0.0)
    xs = [p[0] for p in room.polygon]
    ys = [p[1] for p in room.polygon]
    w = max(xs) - min(xs)
    h = max(ys) - min(ys)
    return (min(w, h), max(w, h))


def check_room_dimensions(room: Room) -> list[VerifyItem]:
    """Verify room area and clear dimensions against NBC 206 §3.2.2 guidelines."""
    items: list[VerifyItem] = []
    kind = classify_room_kind(room)
    if kind == "other" or kind == "stair":
        return items

    area = room.area_m2 if room.area_m2 is not None else polygon_area(room.polygon)
    min_dim, _ = room_bounding_dimensions(room)
    r_name = room.name or f"Room {room.id}"
    r_name_np = room.name_np or nepali.room_name_np(r_name) or r_name

    if kind == "habitable":
        if area < NBC_HABITABLE_MIN_AREA_M2:
            items.append(
                VerifyItem(
                    id=f"v_reg_{room.id}_area",
                    item=f"Verify floor area for {r_name} ({area:.1f} m² measured)",
                    item_np=f"{r_name_np} को क्षेत्रफल ({nepali.format_area_np(area)}) जाँच्नुहोस्",
                    why=f"NBC 206 §3.2.2 recommends minimum 6.0 m² for habitable rooms.",
                    how=f"Confirm with project engineer if partition wall allows adequate space.",
                    severity=Severity.MEDIUM if area < 5.0 else Severity.LOW,
                )
            )
        if 0 < min_dim < NBC_HABITABLE_MIN_DIM_M:
            items.append(
                VerifyItem(
                    id=f"v_reg_{room.id}_dim",
                    item=f"Verify narrowest width for {r_name} ({min_dim:.2f} m measured)",
                    item_np=f"{r_name_np} को चौडाइ ({nepali.format_dimension_np(min_dim)}) जाँच्नुहोस्",
                    why=f"NBC 206 §3.2.2 recommends minimum clear dimension of 2.0 m for habitable rooms.",
                    how=f"Review architectural plans with site supervisor.",
                    severity=Severity.LOW,
                )
            )
    elif kind == "kitchen":
        if area < NBC_KITCHEN_MIN_AREA_M2:
            items.append(
                VerifyItem(
                    id=f"v_reg_{room.id}_kitchen_area",
                    item=f"Verify kitchen area ({area:.1f} m² measured)",
                    item_np=f"भान्सा कोठाको क्षेत्रफल ({nepali.format_area_np(area)}) जाँच्नुहोस्",
                    why=f"NBC 206 §3.2.2 recommends minimum 5.0 m² for kitchen.",
                    how=f"Verify kitchen counter arrangement and usable floor area.",
                    severity=Severity.LOW,
                )
            )
        if 0 < min_dim < NBC_KITCHEN_MIN_DIM_M:
            items.append(
                VerifyItem(
                    id=f"v_reg_{room.id}_kitchen_dim",
                    item=f"Verify kitchen dimension ({min_dim:.2f} m measured)",
                    item_np=f"भान्साको न्यूनतम चौडाइ ({nepali.format_dimension_np(min_dim)}) जाँच्नुहोस्",
                    why=f"NBC 206 §3.2.2 recommends minimum 1.8 m clear width for kitchen.",
                    how=f"Check usable clearance between opposite counters or walls.",
                    severity=Severity.LOW,
                )
            )
    elif kind in ("toilet", "bath"):
        min_allowed_area = NBC_TOILET_MIN_AREA_M2 if kind == "toilet" else NBC_BATH_MIN_AREA_M2
        std_name = "toilet" if kind == "toilet" else "bathroom"
        std_name_np = "शौचालय" if kind == "toilet" else "स्नान कोठा"
        if area < min_allowed_area:
            items.append(
                VerifyItem(
                    id=f"v_reg_{room.id}_wc_area",
                    item=f"Verify {std_name} area ({area:.1f} m² measured)",
                    item_np=f"{std_name_np}को क्षेत्रफल ({nepali.format_area_np(area)}) जाँच्नुहोस्",
                    why=f"NBC 206 §3.2.2 recommends minimum {min_allowed_area:.1f} m² for {std_name}.",
                    how=f"Ensure fixtures (commode, basin) have adequate clearance.",
                    severity=Severity.LOW,
                )
            )

    return items


def check_door_width(
    door: Opening,
    *,
    is_exit: bool = False,
    delta_ref: str | None = None,
) -> list[VerifyItem]:
    """Verify door width against NBC 206 §2.2.1 (0.9m exit, 0.75m internal)."""
    items: list[VerifyItem] = []
    if door.kind != OpeningKind.DOOR or door.width is None:
        return items

    threshold = NBC_EXIT_DOOR_MIN_WIDTH_M if is_exit else NBC_INTERNAL_DOOR_MIN_WIDTH_M
    label = "exit door" if is_exit else "internal door"
    label_np = "निकास ढोका" if is_exit else "भित्री ढोका"

    if door.width < threshold:
        items.append(
            VerifyItem(
                id=f"v_reg_{door.id}_width",
                item=f"Verify width of {label} {door.id} ({door.width:.2f} m)",
                item_np=f"{label_np} {door.id} को चौडाइ ({nepali.format_dimension_np(door.width)}) जाँच्नुहोस्",
                why=f"NBC 206 §2.2.1 recommends clear width of at least {threshold:.2f} m for {label}.",
                how=f"Measure clear opening inside frame before finishing.",
                severity=Severity.MEDIUM if is_exit and door.width < 0.80 else Severity.LOW,
                delta_ref=delta_ref,
            )
        )
    return items


def check_room_natural_light(
    room: Room,
    openings: Sequence[Opening],
    *,
    region: str = "hills",
) -> list[VerifyItem]:
    """Verify natural light opening area ratio against NBC 206 §3.3 (1/10 Hills, 1/8 Terai)."""
    items: list[VerifyItem] = []
    kind = classify_room_kind(room)
    if kind not in ("habitable", "kitchen"):
        return items

    area = room.area_m2 if room.area_m2 is not None else polygon_area(room.polygon)
    if area <= 0.0:
        return items

    ratio_target = NBC_LIGHT_RATIO_HILLS if region.lower() == "hills" else NBC_LIGHT_RATIO_TERAI
    ratio_pct_str = "10% (1/10)" if ratio_target == NBC_LIGHT_RATIO_HILLS else "12.5% (1/8)"

    # Compute opening area for windows associated with this room
    total_window_area = 0.0
    for op in openings:
        if op.kind in (OpeningKind.WINDOW, OpeningKind.VENT):
            w = op.width or 1.0
            h = op.height or 1.2
            total_window_area += w * h

    required_area = area * ratio_target
    if total_window_area < required_area:
        r_name = room.name or f"Room {room.id}"
        r_name_np = room.name_np or nepali.room_name_np(r_name) or r_name
        items.append(
            VerifyItem(
                id=f"v_reg_{room.id}_light",
                item=f"Verify natural light opening area for {r_name} ({total_window_area:.2f} m² vs {required_area:.2f} m² recommended)",
                item_np=f"{r_name_np}मा प्राकृतिक उज्यालो/झ्यालको क्षेत्रफल ({nepali.format_area_np(total_window_area)}) जाँच्नुहोस्",
                why=f"NBC 206 §3.3 recommends window opening area of at least {ratio_pct_str} of room floor area.",
                how=f"Check if additional window or ventilator can be placed to improve daylighting.",
                severity=Severity.LOW,
            )
        )
    return items


def evaluate_scene_regulatory(
    scene: SceneGraph,
    observed: ObservedState | None = None,
    deltas: list[Delta] | None = None,
    *,
    region: str = "hills",
) -> tuple[list[VerifyItem], dict[str, Any]]:
    """Evaluate full scene graph & observed discrepancies against NBC guidelines."""
    items: list[VerifyItem] = []
    checks_run = 0

    # Map external wall IDs
    external_wall_ids = {w.id for w in scene.walls if w.is_external is True}

    # 1. Room dimensions
    for room in scene.rooms:
        checks_run += 1
        items.extend(check_room_dimensions(room))

    # 2. Doors
    for door in scene.openings:
        if door.kind == OpeningKind.DOOR:
            checks_run += 1
            is_exit = (door.wall_id in external_wall_ids) or (door.is_external if hasattr(door, "is_external") else False)
            items.extend(check_door_width(door, is_exit=is_exit))

    # 3. Room lighting & ventilation
    # Associate openings to rooms spatially or by bounding box overlap
    for room in scene.rooms:
        checks_run += 1
        rx_min = min(p[0] for p in room.polygon) if room.polygon else 0.0
        rx_max = max(p[0] for p in room.polygon) if room.polygon else 0.0
        ry_min = min(p[1] for p in room.polygon) if room.polygon else 0.0
        ry_max = max(p[1] for p in room.polygon) if room.polygon else 0.0

        pad = 0.5  # half metre buffer to capture wall-boundary windows
        room_windows = [
            op for op in scene.openings
            if op.kind in (OpeningKind.WINDOW, OpeningKind.VENT)
            and (rx_min - pad <= op.center[0] <= rx_max + pad)
            and (ry_min - pad <= op.center[1] <= ry_max + pad)
        ]
        items.extend(check_room_natural_light(room, room_windows, region=region))

    # 4. Deltas: if an opening delta was detected that shrank an opening, check against NBC
    if deltas:
        for delta in deltas:
            if delta.status == DeltaStatus.DIFFERS and delta.scene_ref:
                scene_op = next((o for o in scene.openings if o.id == delta.scene_ref), None)
                if scene_op and scene_op.kind == OpeningKind.DOOR:
                    checks_run += 1
                    is_exit = scene_op.wall_id in external_wall_ids
                    # If observed size is available, check observed width
                    if delta.observed and "m" in delta.observed:
                        try:
                            obs_w = float(delta.observed.replace("m", "").strip())
                            temp_op = Opening(
                                id=f"{scene_op.id}_obs",
                                kind=OpeningKind.DOOR,
                                center=scene_op.center,
                                width=obs_w,
                                height=scene_op.height,
                            )
                            items.extend(check_door_width(temp_op, is_exit=is_exit, delta_ref=delta.id))
                        except ValueError:
                            pass

    meta = {
        "standard": "NBC 206 (Nepal National Building Code)",
        "region": region,
        "checks_run": checks_run,
        "items_flagged": len(items),
    }
    return items, meta


__all__ = [
    "NBC_HABITABLE_MIN_AREA_M2",
    "NBC_HABITABLE_MIN_DIM_M",
    "NBC_KITCHEN_MIN_AREA_M2",
    "NBC_KITCHEN_MIN_DIM_M",
    "NBC_TOILET_MIN_AREA_M2",
    "NBC_TOILET_MIN_DIM_M",
    "NBC_BATH_MIN_AREA_M2",
    "NBC_BATH_MIN_DIM_M",
    "NBC_EXIT_DOOR_MIN_WIDTH_M",
    "NBC_INTERNAL_DOOR_MIN_WIDTH_M",
    "NBC_LIGHT_RATIO_HILLS",
    "NBC_LIGHT_RATIO_TERAI",
    "classify_room_kind",
    "room_bounding_dimensions",
    "check_room_dimensions",
    "check_door_width",
    "check_room_natural_light",
    "evaluate_scene_regulatory",
]
