"""Karmi render adapter — SceneGraph + ObservedState + DiffReport -> view payload.

Contract with the viewer (``render/viewer.html``)
-------------------------------------------------
The viewer is deterministic drawing code: it renders exactly what this payload
says and infers nothing. It never calls an AI and never touches the network.
Every decision — where an observed element sits, what a missing dimension was
defaulted to, which element is `matched` vs `unverifiable` — is made *here*,
and everything that had to be assumed is recorded in ``meta.assumptions`` so
the viewer can show it honestly.

Top-level shape (VIEW_SCHEMA = "0.1.0")::

    {"schema": "0.1.0", "meta": {...}, "approved": {...},
     "observed": {...}, "deltas": [...], "camera": {...}}

``approved`` / ``observed`` each carry::

    walls:    [{id, start:[x,y], end:[x,y], thickness, height, confidence, status}]
    openings: [{id, kind, center:[x,y], width, height, sill, confidence, status}]
    rooms:    [{id, name, name_np, polygon, area_m2, confidence}]
    bbox:     [minx, miny, maxx, maxy] | None
    warnings: [str]
    (+ ``stage`` on observed)

Status per element comes from the DiffReport by following ``scene_ref`` /
``observed_ref``; an element no delta refers to is ``unverifiable`` — never
silently ``matched``. ``build_view`` never raises: empty or ``None`` inputs
produce a valid payload that carries warnings.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

VIEW_SCHEMA = "0.1.0"

# --- defaults used only when the model itself has no value ------------------
# (every one of these that actually gets applied is reported in
#  meta.assumptions — the payload must be honest about what it assumed)
DEFAULT_WALL_HEIGHT_M = 2.7          # external and internal, per Karmi brief
DEFAULT_THICKNESS_EXTERNAL_M = 0.23  # 9" brick, Nepali standard
DEFAULT_THICKNESS_INTERNAL_M = 0.115  # 4.5" partition
DEFAULT_DOOR_HEIGHT_M = 2.1
DEFAULT_DOOR_SILL_M = 0.0            # semantic: doors start at floor level
DEFAULT_WINDOW_HEIGHT_M = 1.2
DEFAULT_WINDOW_SILL_M = 0.9

STATUSES = ("matched", "differs", "missing", "unexpected", "unverifiable")
# when several deltas touch one element, the most informative status wins
_STATUS_RANK = {"matched": 0, "unverifiable": 1, "unexpected": 2, "missing": 3, "differs": 4}

_OPENING_KINDS = ("door", "window", "vent", "unknown")


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _r(v: Any, nd: int = 4) -> float | None:
    """Round for a tidy, deterministic payload. None-safe."""
    if v is None:
        return None
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return None


def _num(d: Any, *keys: str) -> float | None:
    """First numeric value among ``keys`` in mapping ``d`` (bools excluded)."""
    if not isinstance(d, dict):
        return None
    for k in keys:
        v = d.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
    return None


def _pair(v: Any) -> list[float] | None:
    if isinstance(v, (list, tuple)) and len(v) >= 2:
        x, y = _r(v[0]), _r(v[1])
        if x is not None and y is not None:
            return [x, y]
    return None


def _as_dict(obj: Any) -> dict[str, Any] | None:
    """Normalise a pydantic model / plain dict / None into a plain dict."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    dump = getattr(obj, "model_dump", None)
    if callable(dump):
        try:
            return dump(mode="json")
        except TypeError:
            return dump()
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in vars(obj).items() if not k.startswith("_")}
    raise TypeError(f"cannot read {type(obj).__name__} as a model or dict")


def _confidence(el: dict[str, Any]) -> float:
    prov = el.get("provenance") or {}
    c = _num(prov, "confidence")
    if c is None:
        c = _num(el, "confidence")
    if c is None:
        return 0.0
    return min(1.0, max(0.0, c))


def _label_of(deltas_for_ref: list[dict[str, Any]], fallback: str) -> str:
    for d in deltas_for_ref:
        lbl = d.get("element")
        if isinstance(lbl, str) and lbl.strip():
            return lbl.strip()
    return fallback


def _dedupe(seq: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for s in seq:
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


# --------------------------------------------------------------------------- #
# delta index — element id -> best status
# --------------------------------------------------------------------------- #
class _DeltaIndex:
    def __init__(self, deltas: list[dict[str, Any]], warnings: list[str]):
        self.by_scene: dict[str, list[dict[str, Any]]] = {}
        self.by_observed: dict[str, list[dict[str, Any]]] = {}
        for d in deltas:
            if not isinstance(d, dict):
                continue
            st = d.get("status")
            if not isinstance(st, str) or st not in STATUSES:
                if st is not None:
                    warnings.append(
                        f"delta {d.get('id')!r} has unknown status {st!r}; treated as unverifiable."
                    )
                d = dict(d)
                d["status"] = "unverifiable"
            ref = d.get("scene_ref")
            if isinstance(ref, str) and ref:
                self.by_scene.setdefault(ref, []).append(d)
            ref = d.get("observed_ref")
            if isinstance(ref, str) and ref:
                self.by_observed.setdefault(ref, []).append(d)

    def for_scene(self, el_id: str) -> tuple[str, list[str], list[dict[str, Any]]]:
        return self._resolve(self.by_scene.get(el_id, []))

    def for_observed(self, el_id: str) -> tuple[str, list[str], list[dict[str, Any]]]:
        return self._resolve(self.by_observed.get(el_id, []))

    @staticmethod
    def _resolve(refs: list[dict[str, Any]]) -> tuple[str, list[str], list[dict[str, Any]]]:
        if not refs:
            # no delta refers to this element: honest default, never "matched"
            return "unverifiable", [], []
        best = max(refs, key=lambda d: _STATUS_RANK.get(d.get("status", "unverifiable"), 1))
        status = best.get("status", "unverifiable")
        ids = [str(d.get("id")) for d in refs if d.get("id") is not None]
        return status, ids, refs


# --------------------------------------------------------------------------- #
# geometry helpers
# --------------------------------------------------------------------------- #
def _shoelace(poly: list[list[float]]) -> float | None:
    if len(poly) < 3:
        return None
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def _polygon(v: Any) -> list[list[float]]:
    out: list[list[float]] = []
    if not isinstance(v, (list, tuple)):
        return out
    for p in v:
        pp = _pair(p)
        if pp:
            out.append(pp)
    return out


def _bbox(points: list[tuple[float, float]]) -> list[float] | None:
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return [_r(min(xs)), _r(min(ys)), _r(max(xs)), _r(max(ys))]


def _bbox_union(a: list[float] | None, b: list[float] | None) -> list[float] | None:
    if a is None:
        return b
    if b is None:
        return a
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


def _camera(bbox: list[float] | None) -> dict[str, Any]:
    if not bbox:
        return {
            "target": [0.0, 0.0, 0.0],
            "yaw_deg": -35.0,
            "pitch_deg": 32.0,
            "distance": 14.0,
            "fov": 45.0,
            "fit": False,
        }
    cx = (bbox[0] + bbox[2]) / 2.0
    cy = (bbox[1] + bbox[3]) / 2.0
    span = max(bbox[2] - bbox[0], bbox[3] - bbox[1], 1.0)
    return {
        "target": [_r(cx), _r(cy), 0.0],
        "yaw_deg": -35.0,
        "pitch_deg": 32.0,
        "distance": _r(span * 1.7 + 3.0),
        "fov": 45.0,
        "fit": True,
    }


# --------------------------------------------------------------------------- #
# approved side
# --------------------------------------------------------------------------- #
def _approved_side(
    s: dict[str, Any] | None,
    idx: _DeltaIndex,
    assumptions: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    walls: list[dict[str, Any]] = []
    openings: list[dict[str, Any]] = []
    rooms: list[dict[str, Any]] = []
    pts: list[tuple[float, float]] = []
    own_warnings: list[str] = []
    if s is None:
        warnings.append("No approved model (scene graph) was supplied — nothing to draw on the drawing side.")
        return {
            "walls": walls, "openings": openings, "rooms": rooms,
            "bbox": None, "warnings": ["No approved model was supplied."],
        }

    # wall height: the schema carries none — look in meta, else default (honest)
    meta = s.get("meta") if isinstance(s.get("meta"), dict) else {}
    wall_h = _num(meta, "wall_height_m", "wall_height")
    wall_h_defaulted = wall_h is None
    if wall_h_defaulted:
        wall_h = DEFAULT_WALL_HEIGHT_M

    th_ext = th_int = 0
    scene_walls: dict[str, dict[str, Any]] = {}
    for w in s.get("walls") or []:
        if not isinstance(w, dict):
            continue
        wid = str(w.get("id") or f"wall-{len(walls)}")
        start = _pair(w.get("start"))
        end = _pair(w.get("end"))
        if start is None or end is None:
            own_warnings.append(f"wall {wid!r} has no usable geometry; skipped.")
            continue
        thickness = _num(w, "thickness")
        if thickness is None or thickness <= 0:
            if w.get("is_external") is False:
                thickness = DEFAULT_THICKNESS_INTERNAL_M
                th_int += 1
            else:
                thickness = DEFAULT_THICKNESS_EXTERNAL_M
                th_ext += 1
        status, delta_ids, refs = idx.for_scene(wid)
        rec = {
            "id": wid,
            "start": start,
            "end": end,
            "thickness": _r(thickness),
            "height": _r(wall_h),
            "confidence": _r(_confidence(w)),
            "status": status,
            "is_external": w.get("is_external"),
            "label": _label_of(refs, f"wall {wid}"),
            "delta_ids": delta_ids,
        }
        walls.append(rec)
        scene_walls[wid] = rec
        pts.extend([(start[0], start[1]), (end[0], end[1])])
        t2 = thickness / 2.0
        pts.extend([(start[0] - t2, start[1] - t2), (end[0] + t2, end[1] + t2)])

    no_width: list[str] = []
    d_h = d_sh = w_h = w_sh = 0
    scene_openings: dict[str, dict[str, Any]] = {}
    for op in s.get("openings") or []:
        if not isinstance(op, dict):
            continue
        oid = str(op.get("id") or f"opening-{len(openings)}")
        center = _pair(op.get("center"))
        if center is None:
            own_warnings.append(f"opening {oid!r} has no centre; skipped.")
            continue
        kind = op.get("kind")
        kind = kind.lower() if isinstance(kind, str) else "unknown"
        if kind not in _OPENING_KINDS:
            kind = "unknown"
        width = _num(op, "width")
        height = _num(op, "height")
        sill = _num(op, "sill_height", "sill")
        if kind == "door":
            if sill is None:
                sill, d_sh = DEFAULT_DOOR_SILL_M, d_sh + 1
            if height is None:
                height, d_h = DEFAULT_DOOR_HEIGHT_M, d_h + 1
        elif kind == "window":
            if sill is None:
                sill, w_sh = DEFAULT_WINDOW_SILL_M, w_sh + 1
            if height is None:
                height, w_h = DEFAULT_WINDOW_HEIGHT_M, w_h + 1
        if width is None:
            no_width.append(oid)
        status, delta_ids, refs = idx.for_scene(oid)
        rec = {
            "id": oid,
            "kind": kind,
            "center": center,
            "width": _r(width),
            "height": _r(height),
            "sill": _r(sill),
            "confidence": _r(_confidence(op)),
            "status": status,
            "wall_id": op.get("wall_id"),
            "label": _label_of(refs, f"{kind} {oid}"),
            "delta_ids": delta_ids,
        }
        openings.append(rec)
        scene_openings[oid] = rec

    areas_computed = 0
    for rm in s.get("rooms") or []:
        if not isinstance(rm, dict):
            continue
        rid = str(rm.get("id") or f"room-{len(rooms)}")
        poly = _polygon(rm.get("polygon"))
        area = _num(rm, "area_m2")
        if area is None and len(poly) >= 3:
            area = _shoelace(poly)
            if area is not None:
                areas_computed += 1
        status, delta_ids, refs = idx.for_scene(rid)  # same rule as walls: no delta -> unverifiable
        rec = {
            "id": rid,
            "name": rm.get("name"),
            "name_np": rm.get("name_np"),
            "polygon": poly,
            "area_m2": _r(area),
            "confidence": _r(_confidence(rm)),
            "status": status,
            "label": _label_of(refs, rm.get("name") or f"room {rid}"),
            "delta_ids": delta_ids,
        }
        rooms.append(rec)
        pts.extend((p[0], p[1]) for p in poly)

    bbox = _bbox(pts)
    if s.get("bbox"):
        given = [v for v in (_r(v) for v in s["bbox"][:4]) if v is not None]
        if len(given) == 4:
            bbox = _bbox_union(bbox, given)

    if wall_h_defaulted and walls:
        assumptions.append(
            f"Wall height is not part of the drawing schema; assumed "
            f"{DEFAULT_WALL_HEIGHT_M:g} m for all {len(walls)} walls (external and internal)."
        )
    if th_ext:
        assumptions.append(
            f"{th_ext} wall(s) had no thickness in the drawing; assumed "
            f"{DEFAULT_THICKNESS_EXTERNAL_M:g} m (9\" external)."
        )
    if th_int:
        assumptions.append(
            f"{th_int} wall(s) had no thickness in the drawing; assumed "
            f"{DEFAULT_THICKNESS_INTERNAL_M:g} m (4.5\" partition)."
        )
    if d_h:
        assumptions.append(f"{d_h} door opening(s) had no height; assumed {DEFAULT_DOOR_HEIGHT_M:g} m.")
    if d_sh:
        assumptions.append("Door openings start at floor level; sill assumed 0 m.")
    if w_h:
        assumptions.append(f"{w_h} window opening(s) had no height; assumed {DEFAULT_WINDOW_HEIGHT_M:g} m.")
    if w_sh:
        assumptions.append(f"{w_sh} window opening(s) had no sill height; assumed {DEFAULT_WINDOW_SILL_M:g} m.")
    if areas_computed:
        assumptions.append(
            f"{areas_computed} room area(s) were not stated in the drawing; computed from the polygon."
        )
    if no_width:
        own_warnings.append(
            f"{len(no_width)} opening(s) have no width ({', '.join(no_width[:6])}"
            f"{', …' if len(no_width) > 6 else ''}) — the viewer shows them as markers, not holes."
        )

    return {
        "walls": walls,
        "openings": openings,
        "rooms": rooms,
        "bbox": bbox,
        "warnings": _dedupe(list(s.get("warnings") or []) + own_warnings),
        "_walls_index": scene_walls,
        "_openings_index": scene_openings,
        "_rooms": {r["id"]: r for r in rooms},
    }


# --------------------------------------------------------------------------- #
# observed side
# --------------------------------------------------------------------------- #
def _place_observed_wall(
    el: dict[str, Any],
    scene_walls: dict[str, dict[str, Any]],
    wall_h: float,
    notes: dict[str, int],
) -> dict[str, Any] | None:
    size = el.get("approx_size") if isinstance(el.get("approx_size"), dict) else {}
    x0 = _num(size, "x0", "start_x")
    y0 = _num(size, "y0", "start_y")
    x1 = _num(size, "x1", "end_x")
    y1 = _num(size, "y1", "end_y")
    anchor_id = el.get("matches_scene_id")
    anchor = scene_walls.get(anchor_id) if isinstance(anchor_id, str) else None

    if None not in (x0, y0, x1, y1) and (abs(x1 - x0) > 1e-6 or abs(y1 - y0) > 1e-6):
        start, end = [x0, y0], [x1, y1]
        placed = "measured"
    elif anchor is not None:
        a, b = anchor["start"], anchor["end"]
        ln = _num(size, "length")
        if ln and ln > 0.05:
            mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
            L = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
            ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            start = [mx - ux * ln / 2.0, my - uy * ln / 2.0]
            end = [mx + ux * ln / 2.0, my + uy * ln / 2.0]
            placed = "anchored_rescaled"
            notes["rescaled"] = notes.get("rescaled", 0) + 1
        else:
            start, end = [a[0], a[1]], [b[0], b[1]]
            placed = "anchored"
        notes["anchored"] = notes.get("anchored", 0) + 1
    else:
        return None

    thickness = _num(size, "thickness")
    if thickness is None or thickness <= 0:
        thickness = (anchor or {}).get("thickness") or DEFAULT_THICKNESS_EXTERNAL_M
    height = _num(size, "height") or (anchor or {}).get("height") or wall_h
    return {
        "start": [_r(start[0]), _r(start[1])],
        "end": [_r(end[0]), _r(end[1])],
        "thickness": _r(thickness),
        "height": _r(height),
        "_placed": placed,
    }


def _place_observed_opening(
    el: dict[str, Any],
    scene_openings: dict[str, dict[str, Any]],
    scene_walls: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    size = el.get("approx_size") if isinstance(el.get("approx_size"), dict) else {}
    cx = _num(size, "cx", "x")
    cy = _num(size, "cy", "y")
    anchor_id = el.get("matches_scene_id")
    anchor = scene_openings.get(anchor_id) if isinstance(anchor_id, str) else None
    if cx is not None and cy is not None:
        center = [cx, cy]
    elif anchor is not None:
        center = list(anchor["center"])
    else:
        return None

    width = _num(size, "width")
    height = _num(size, "height")
    sill = _num(size, "sill", "sill_height")
    if _num(size, "door") and _num(size, "door") >= 0.5:
        kind = "door"
    elif _num(size, "window") and _num(size, "window") >= 0.5:
        kind = "window"
    elif sill is not None:
        kind = "door" if abs(sill) < 1e-9 else "window"
    elif anchor is not None and anchor.get("kind") in _OPENING_KINDS:
        kind = anchor["kind"]
    else:
        kind = "unknown"
    if width is None and anchor is not None:
        width = anchor.get("width")
    if height is None and anchor is not None:
        height = anchor.get("height")
    if sill is None and anchor is not None:
        sill = anchor.get("sill")
    wall_id = el.get("wall_id") or (anchor or {}).get("wall_id")
    return {
        "center": [_r(center[0]), _r(center[1])],
        "kind": kind,
        "width": _r(width),
        "height": _r(height),
        "sill": _r(sill),
        "wall_id": wall_id,
    }


def _observed_side(
    o: dict[str, Any] | None,
    scene_walls: dict[str, dict[str, Any]],
    scene_openings: dict[str, dict[str, Any]],
    scene_rooms: dict[str, dict[str, Any]],
    idx: _DeltaIndex,
    wall_h: float,
    assumptions: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    walls: list[dict[str, Any]] = []
    openings: list[dict[str, Any]] = []
    rooms: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    unplaced: list[dict[str, Any]] = []
    pts: list[tuple[float, float]] = []
    own_warnings: list[str] = []
    notes: dict[str, int] = {}
    stage = "unknown"

    if o is None:
        warnings.append("No as-built observations were supplied — nothing to draw on the observed side.")
        return {
            "walls": walls, "openings": openings, "rooms": rooms,
            "bbox": None, "stage": "unknown", "other": [], "unplaced": [],
            "warnings": ["No observed state was supplied."],
        }

    stage = o.get("stage") if isinstance(o.get("stage"), str) else "unknown"

    for el in o.get("elements") or []:
        if not isinstance(el, dict):
            continue
        eid = str(el.get("id") or f"obs-{len(walls) + len(other)}")
        kind = el.get("kind")
        kind = kind if isinstance(kind, str) else "other"
        conf = _r(_confidence(el))
        status, delta_ids, refs = idx.for_observed(eid)
        label = _label_of(refs, el.get("location_hint") or f"{kind} {eid}")

        if kind == "wall":
            geom = _place_observed_wall(el, scene_walls, wall_h, notes)
            if geom is None:
                unplaced.append({
                    "id": eid, "kind": kind, "label": label, "confidence": conf,
                    "status": status, "delta_ids": delta_ids,
                    "note": "no coordinates and no matched approved wall — position unknown",
                })
                continue
            rec = {
                "id": eid,
                "start": geom["start"],
                "end": geom["end"],
                "thickness": geom["thickness"],
                "height": geom["height"],
                "confidence": conf,
                "status": status,
                "label": label,
                "delta_ids": delta_ids,
                "_placed": geom["_placed"],
            }
            walls.append(rec)
            pts.extend([(rec["start"][0], rec["start"][1]), (rec["end"][0], rec["end"][1])])
        elif kind == "opening":
            geom = _place_observed_opening(el, scene_openings, scene_walls)
            if geom is None:
                unplaced.append({
                    "id": eid, "kind": kind, "label": label, "confidence": conf,
                    "status": status, "delta_ids": delta_ids,
                    "note": "no centre and no matched approved opening — position unknown",
                })
                continue
            rec = {
                "id": eid,
                "kind": geom["kind"],
                "center": geom["center"],
                "width": geom["width"],
                "height": geom["height"],
                "sill": geom["sill"],
                "confidence": conf,
                "status": status,
                "wall_id": geom["wall_id"],
                "label": label,
                "delta_ids": delta_ids,
            }
            openings.append(rec)
            pts.append((rec["center"][0], rec["center"][1]))
        elif kind == "room":
            anchor_id = el.get("matches_scene_id")
            anchor = scene_rooms.get(anchor_id) if isinstance(anchor_id, str) else None
            if anchor is None:
                unplaced.append({
                    "id": eid, "kind": kind, "label": label, "confidence": conf,
                    "status": status, "delta_ids": delta_ids,
                    "note": "no polygon and no matched approved room — shape unknown",
                })
                continue
            size = el.get("approx_size") if isinstance(el.get("approx_size"), dict) else {}
            area = _num(size, "area_m2", "area") or anchor.get("area_m2")
            rec = {
                "id": eid,
                "name": anchor.get("name"),
                "name_np": anchor.get("name_np"),
                "polygon": [list(p) for p in anchor.get("polygon") or []],
                "area_m2": _r(area),
                "confidence": conf,
                "status": status,
                "label": label,
                "delta_ids": delta_ids,
            }
            rooms.append(rec)
            pts.extend((p[0], p[1]) for p in rec["polygon"])
        else:
            other.append({
                "id": eid, "kind": kind, "label": label, "confidence": conf,
                "status": status, "delta_ids": delta_ids,
                "approx_size": el.get("approx_size") or {},
                "note": "element kind is not drawn on the plan",
            })

    if notes.get("anchored"):
        assumptions.append(
            f"{notes['anchored']} observed element(s) carried no coordinates and were placed at their "
            "matched approved element's position — positions are approximate."
        )
    if notes.get("rescaled"):
        assumptions.append(
            f"{notes['rescaled']} observed wall(s) were re-scaled around their anchor using the "
            "observed length; direction taken from the matched approved wall."
        )
    if other:
        own_warnings.append(
            f"{len(other)} observed element(s) are of kinds not drawn on the plan "
            f"({', '.join(sorted({e['kind'] for e in other}))}) — listed in observed.other."
        )
    if unplaced:
        own_warnings.append(
            f"{len(unplaced)} observed element(s) could not be placed (no position evidence) — "
            "listed in observed.unplaced."
        )
    if not openings and walls:
        own_warnings.append("No opening observations in this run — doors/windows on site were not checked.")
    if not rooms:
        own_warnings.append("No room observations in this run — room-by-room comparison is not possible.")

    bbox = _bbox(pts)
    return {
        "walls": walls,
        "openings": openings,
        "rooms": rooms,
        "bbox": bbox,
        "stage": stage,
        "other": other,
        "unplaced": unplaced,
        "warnings": _dedupe(list(o.get("warnings") or []) + own_warnings),
    }


# --------------------------------------------------------------------------- #
# public entry point
# --------------------------------------------------------------------------- #
def _blank_view(warnings: list[str], empty: bool = True) -> dict[str, Any]:
    approved = {"walls": [], "openings": [], "rooms": [], "bbox": None, "warnings": []}
    observed = {
        "walls": [], "openings": [], "rooms": [], "bbox": None,
        "stage": "unknown", "other": [], "unplaced": [], "warnings": [],
    }
    return {
        "schema": VIEW_SCHEMA,
        "meta": {
            "schema": VIEW_SCHEMA,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "generator": "karmi render adapter",
            "scene_source": None,
            "observed_sources": [],
            "stage": "unknown",
            "counts": {
                "approved": {"walls": 0, "openings": 0, "rooms": 0},
                "observed": {"elements": 0, "walls": 0, "openings": 0, "rooms": 0,
                             "other": 0, "unplaced": 0},
                "deltas": {"total": 0},
            },
            "assumptions": [],
            "warnings": _dedupe(warnings),
            "limits": [],
            "narration_en": [],
            "narration_np": [],
            "diff_summary": {},
            "empty": empty,
        },
        "approved": approved,
        "observed": observed,
        "deltas": [],
        "camera": _camera(None),
    }


def build_view(scene: Any, observed: Any, report: Any) -> dict[str, Any]:
    """Build the viewer payload. Never raises — bad/empty input degrades to warnings."""
    warnings: list[str] = []
    assumptions: list[str] = []
    try:
        s = _as_dict(scene)
        o = _as_dict(observed)
        r = _as_dict(report)
    except Exception as exc:  # noqa: BLE001 — a demo must not die on a bad object
        return _blank_view([f"View inputs could not be read ({type(exc).__name__}: {exc})."])

    if s is None and o is None and r is None:
        return _blank_view(["No pipeline output was supplied — nothing to show."])

    deltas = []
    if isinstance(r, dict):
        deltas = [d for d in (r.get("deltas") or []) if isinstance(d, dict)]
    elif r is not None:
        warnings.append("Diff report could not be read; every element stays unverifiable.")

    idx = _DeltaIndex(deltas, warnings)

    approved = _approved_side(s, idx, assumptions, warnings)
    scene_walls = approved.pop("_walls_index", {})
    scene_openings = approved.pop("_openings_index", {})
    scene_rooms = approved.pop("_rooms", {})

    # wall height used for observed geometry too (keep the two sides consistent)
    wall_h = DEFAULT_WALL_HEIGHT_M
    if s is not None and isinstance(s.get("meta"), dict):
        wall_h = _num(s["meta"], "wall_height_m", "wall_height") or DEFAULT_WALL_HEIGHT_M

    observed_side = _observed_side(o, scene_walls, scene_openings, scene_rooms, idx, wall_h, assumptions, warnings)

    # ---- resolve delta refs against the elements we actually built --------
    known_scene = {w["id"] for w in approved["walls"]} | {p["id"] for p in approved["openings"]} | {
        rm["id"] for rm in approved["rooms"]
    }
    known_obs = (
        {w["id"] for w in observed_side["walls"]}
        | {p["id"] for p in observed_side["openings"]}
        | {rm["id"] for rm in observed_side["rooms"]}
        | {e["id"] for e in observed_side["other"]}
        | {e["id"] for e in observed_side["unplaced"]}
    )
    dangling: list[str] = []
    for d in deltas:
        ref = d.get("scene_ref")
        if isinstance(ref, str) and ref and ref not in known_scene:
            dangling.append(f"{d.get('id')}→{ref}")
        ref = d.get("observed_ref")
        if isinstance(ref, str) and ref and ref not in known_obs:
            dangling.append(f"{d.get('id')}→{ref}")
    if dangling:
        warnings.append(
            f"{len(dangling)} delta reference(s) point at element ids that are not in the models "
            f"({', '.join(dangling[:6])}{', …' if len(dangling) > 6 else ''}); they are listed but not drawn."
        )

    if r is None:
        warnings.append(
            "No diff report was supplied — no element can be marked matched; everything shows as unverifiable."
        )

    # ---- meta --------------------------------------------------------------
    status_counts = {st: 0 for st in STATUSES}
    for d in deltas:
        st = d.get("status") if isinstance(d.get("status"), str) else "unverifiable"
        status_counts[st if st in status_counts else "unverifiable"] += 1

    bbox_all = _bbox_union(approved.get("bbox"), observed_side.get("bbox"))
    empty = (
        not approved["walls"] and not approved["openings"] and not approved["rooms"]
        and not observed_side["walls"] and not observed_side["openings"]
        and not observed_side["rooms"] and not observed_side["other"]
        and not deltas
    )

    meta = {
        "schema": VIEW_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "karmi render adapter",
        "scene_source": (s or {}).get("source_file"),
        "observed_sources": [
            c.get("file") for c in ((o or {}).get("captures") or [])
            if isinstance(c, dict) and c.get("file")
        ],
        "stage": observed_side["stage"],
        "counts": {
            "approved": {
                "walls": len(approved["walls"]),
                "openings": len(approved["openings"]),
                "rooms": len(approved["rooms"]),
            },
            "observed": {
                "elements": len((o or {}).get("elements") or []),
                "walls": len(observed_side["walls"]),
                "openings": len(observed_side["openings"]),
                "rooms": len(observed_side["rooms"]),
                "other": len(observed_side["other"]),
                "unplaced": len(observed_side["unplaced"]),
            },
            "deltas": {"total": len(deltas), **status_counts},
        },
        "assumptions": _dedupe(assumptions),
        "warnings": _dedupe(warnings),
        "limits": list((r or {}).get("limits") or []),
        "narration_en": list((r or {}).get("narration_en") or []),
        "narration_np": list((r or {}).get("narration_np") or []),
        "diff_summary": dict((r or {}).get("summary") or {}),
        "municipal": dict((r or {}).get("meta", {}).get("municipal", {}) if isinstance((r or {}).get("meta"), dict) else {}),
        "regulatory": dict((r or {}).get("meta", {}).get("regulatory", {}) if isinstance((r or {}).get("meta"), dict) else {}),
        "scale_m_per_unit": (s or {}).get("scale_m_per_unit"),
        "empty": empty,
    }

    return {
        "schema": VIEW_SCHEMA,
        "meta": meta,
        "approved": approved,
        "observed": observed_side,
        "deltas": deltas,
        "camera": _camera(bbox_all),
    }


__all__ = ["VIEW_SCHEMA", "build_view", "DEFAULT_WALL_HEIGHT_M"]