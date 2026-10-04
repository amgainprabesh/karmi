"""Karmi — drawing → scene graph (the machine-readable APPROVED building).

    python -m core.model fixtures/naksa_base.pdf

Pipeline
--------
ingest (``core.ingest``) → snap near-axis segments → merge collinear runs →
wall extraction (parallel line pairs give thickness; single lines degrade to
``thickness=None``) → opening detection (gaps between wall spans, capped by
jamb lines; door/window by width band) → room extraction (minimal cycles of the
wall-centreline planar graph, ``core.geometry.close_rooms``) → room naming from
the drawing's own label texts (with Nepali ``name_np`` for the common ones) →
dimension text parsing (m / mm / feet-inches / Devanagari digits) → scale
derivation → north-arrow detection.

Honesty rules
-------------
* Nothing is fabricated: every field carries a :class:`~core.schema.Provenance`
  with a confidence we can justify; missing information is a warning, never a
  made-up number.
* The module runs fully **offline** with ``ai=None`` (the default). ``ai`` is an
  optional injected hook: if the object exposes ``refine_scene_graph(scene,
  drawing=...)`` it is called and a returned SceneGraph replaces the
  deterministic one (failures only add warnings).
* Raster/scan drawings never crash: the vector pipeline is skipped and the
  returned SceneGraph carries explicit warnings.

Scale
-----
``scale_m_per_unit`` is metres per PDF point. Priority: an explicitly passed
value (``user_supplied``, confidence 1.0) → a CAD scale note such as
``SCALE 1:100`` on a vector page, which confirms the CAD export convention
1 pt = 25 mm (confidence 0.75, raised to 0.9 when dimension texts corroborate
it) → otherwise ``None`` plus a warning; coordinates are then left in PDF points
(unscaled) and unit-dependent numbers (widths, thicknesses, areas) are omitted.

North
-----
``north_deg`` is a compass-style bearing in degrees **clockwise from "up" on
the page** (0 = the arrow points up). Detection looks for an ``N`` text with a
short line near one end; the line's far end is the tail, the end near the text
is the tip.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from core import geometry as geo
from core.ingest import IngestError, IngestedDrawing, TextItem, ingest_drawing
from core.schema import (
    Dimension,
    Opening,
    OpeningKind,
    Provenance,
    Room,
    SceneGraph,
    SourceKind,
    Wall,
)

# --------------------------------------------------------------------------- #
# constants — tolerances are METRES; they are divided by the working scale
# (metres per pt) to get working units. When the scale is unknown we size the
# tolerance windows with the CAD default (1 pt = 25 mm) — that only affects
# heuristic windows, never a reported number.
# --------------------------------------------------------------------------- #
CAD_M_PER_PT = 0.025  # 1 pt = 25 mm — the CAD export convention a scale note confirms
CAD_PT_PER_M = 40.0

SNAP_TOL_DEG = 3.0
MERGE_GAP_M = 0.12  # join collinear fragments closer than this
PAIR_MAX_OFFSET_M = 0.35  # max wall thickness (parallel-line offset)
PAIR_MIN_OFFSET_M = 0.04  # below this, lines are duplicates, not a wall
PAIR_MIN_OVERLAP_M = 0.30  # parallel lines must overlap at least this much
PAIR_MIN_RUN_LEN_M = 0.40  # runs shorter than this are never wall candidates
CENTRE_TOL_M = 0.05  # pairs on the same centreline belong to one wall run
SPAN_MERGE_GAP_M = 0.40  # gaps below the min opening width are drawing noise
MIN_OPENING_M = 0.40
MAX_OPENING_M = 3.20  # a bigger break means two separate walls
JAMB_MAX_LEN_FACTOR = 2.5  # jamb line length ≤ 2.5 × wall thickness
JAMB_EDGE_TOL_FACTOR = 1.2  # jamb midpoint must sit within 1.2 × t of the gap edge
JAMB_LATERAL_TOL_FACTOR = 0.75  # and within 0.75 × t of the wall centreline
JAMB_MIN_ANGLE_DEG = 30.0  # jambs are clearly not parallel to the wall
FALLBACK_MIN_LEN_M = 0.50  # single-line fallback walls must be at least this long
JUNCTION_TOL_M = 0.20  # single-line walls must touch the network
ROOM_TOL_M = 0.15  # node clustering tolerance for the planar graph
OUTER_TOL_M = 0.05  # distance from the outer boundary that still counts as "on" it
DIM_LINE_MAX_DIST_PT = 25.0  # dimension text ↔ its line search radius (points)

#: keyword → Nepali name (the drawing's own label text stays in ``Room.name``)
ROOM_KEYWORDS: list[tuple[str, str]] = [
    (r"\bBED\s?ROOM\b", "शयनकक्ष"),
    (r"\bLIVING\b|\bLOUNGE\b", "बैठक"),
    (r"\bKITCHEN\b", "भान्सा"),
    (r"\bBATH\b|\bBATHROOM\b|\bTOILET\b|\bW\.?C\.?\b", "शौचालय"),
    (r"\bSTAIRS?\b|\bSTAIRCASE\b", "सिँढी"),
    (r"\bSTORE\b|\bSTORAGE\b", "भण्डार"),
    (r"\bDINING\b", "भोजनकक्ष"),
]

_DEVA_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_SCALE_NOTE_RE = re.compile(r"SCALE[^0-9]{0,12}1\s*:\s*(\d{1,4})", re.I)
_MEASURE_TAIL_RE = re.compile(r"\d+(?:\.\d+)?\s*M\s*$", re.I)
_NORTH_TEXT_RE = re.compile(r"N\.?|NORTH|उत्तर", re.I)


def _tol(metric_m: float, s: float) -> float:
    """A metric tolerance expressed in working units.

    The window is ``metric_m`` metres at the working scale ``s``, but it is
    never narrower than the same window at the CAD convention (1 pt = 25 mm):
    this keeps extraction stable when a caller-supplied scale differs from the
    drawing's native one, while still widening properly for genuinely
    smaller-scale (larger ``s``) drawings.
    """
    return max(metric_m / s, metric_m / CAD_M_PER_PT)


# --------------------------------------------------------------------------- #
# internal wall representation (all values in PDF points until assembly)
# --------------------------------------------------------------------------- #
@dataclass
class _WallGeom:
    a: tuple[float, float]  # centreline start (pt)
    b: tuple[float, float]  # centreline end (pt)
    horizontal: bool
    thickness: float | None  # pt
    spans: list[tuple[float, float]]  # solid spans along the wall axis (pt)
    confidence: float
    evidence: str
    paired: bool
    external: bool | None = None
    wall_id: str = ""

    @property
    def coord(self) -> float:
        return self.a[1] if self.horizontal else self.a[0]


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def build_scene_graph(
    drawing_path: str | Path,
    *,
    scale_m_per_unit: float | None = None,
    north_deg: float | None = None,
    ai: Any = None,
) -> SceneGraph:
    """Turn a naksa drawing (vector PDF) into a :class:`SceneGraph`.

    Never raises for unreadable/raster drawings — it degrades to an empty model
    with explicit warnings. Works fully offline with ``ai=None``.
    """
    sg = SceneGraph(source_file=str(drawing_path))
    try:
        ing = ingest_drawing(drawing_path)
    except IngestError as exc:
        sg.warnings.append(f"Drawing could not be read: {exc}")
        sg.meta["ingest_error"] = str(exc)
        return sg

    sg.source_kind = ing.kind
    sg.warnings.extend(ing.warnings)
    sg.meta.update(
        {
            "page_index": ing.page_index,
            "page_size_pt": [ing.page_size_pt[0], ing.page_size_pt[1]],
            "n_segments_raw": len(ing.segments),
            "n_texts": len(ing.texts),
            "image_count": ing.image_count,
            "ai_used": False,
            "north_frame": "degrees clockwise from 'up' on the page (0 = up)",
        }
    )

    # ---- scale (drives every metric tolerance) ---------------------------- #
    scale, scale_prov, scale_notes = _derive_scale(ing, scale_m_per_unit)
    sg.scale_m_per_unit = scale
    sg.scale_provenance = scale_prov
    sg.warnings.extend(scale_notes)

    if ing.kind in (SourceKind.RASTER_PDF, SourceKind.SCAN, SourceKind.IMAGE) and (
        len(ing.segments) < 4
    ):
        return _build_raster_model(
            sg, ing, drawing_path, scale_m_per_unit=scale_m_per_unit, north_deg=north_deg
        )

    if not ing.texts:
        sg.warnings.append(
            "No text layer on the drawing — room names, dimensions, the scale note and "
            "the north arrow could not be read."
        )

    try:
        _build_vector_model(sg, ing, scale, north_deg)
    except Exception as exc:  # noqa: BLE001 — degrade, never crash the demo
        sg.warnings.append(
            f"Extraction failed unexpectedly ({type(exc).__name__}: {exc}); "
            "returning the partial model."
        )
        sg.meta["extraction_error"] = traceback.format_exc()

    # ---- optional AI hook (never required; offline result is the baseline) - #
    if ai is not None:
        hook = getattr(ai, "refine_scene_graph", None)
        if callable(hook):
            try:
                refined = hook(sg, drawing=ing)
                if isinstance(refined, SceneGraph):
                    refined.meta["ai_used"] = True
                    sg = refined
                else:
                    sg.warnings.append(
                        "ai.refine_scene_graph returned no SceneGraph; deterministic result kept."
                    )
            except Exception as exc:  # noqa: BLE001
                sg.warnings.append(
                    f"ai.refine_scene_graph failed ({type(exc).__name__}); deterministic result kept."
                )
        else:
            sg.warnings.append(
                "ai provider supplied but has no refine_scene_graph() hook; ignored."
            )
    return sg


def save_scene_graph(sg: SceneGraph, path: str | Path) -> Path:
    """Write a scene graph to JSON (UTF-8, pretty). Returns the path written."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(sg.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return p


def load_scene_graph(path: str | Path) -> SceneGraph:
    """Load a scene graph from JSON."""
    return SceneGraph.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


# --------------------------------------------------------------------------- #
# the vector pipeline
# --------------------------------------------------------------------------- #
def _build_raster_model(
    sg: SceneGraph,
    ing: "IngestedDrawing",
    drawing_path: str | Path,
    *,
    scale_m_per_unit: float | None = None,
    north_deg: float | None = None,
) -> SceneGraph:
    """Raster/scan fallback: deterministic line extraction on the image itself.

    Replaces the old "return empty + warning" behaviour. `core/raster.py` does the
    image analysis (Otsu binarize, projection-profile deskew, run-length segment
    extraction); this wrapper feeds its segments to the same wall/opening logic the
    vector path uses, with honest raster confidence and NO invented scale.

    Contract when `scale_m_per_unit` is None (documented in docs/RASTER.md):
    coordinates stay in PIXELS, so every metric field (wall thickness in metres,
    opening width, room area, dimensions) stays None, and a warning says exactly
    why. The scene graph remains valid for topology-only comparison and for the
    3D viewer; metric deltas come back UNVERIFIABLE rather than being guessed.
    """
    sg.warnings.append(
        "The drawing is a raster/scan (no usable vector paths): running the "
        "deterministic raster extractor. Geometry will be approximate; supply a "
        "CAD-exported PDF for the full model."
    )
    sg.meta["coordinate_frame"] = "pixels (raster — metric numbers unavailable without a scale)"
    try:
        from core.raster import extract_plan

        plan = extract_plan(drawing_path)
        segs = plan.get("segments", [])
        sg.warnings.extend(plan.get("warnings", []))
        sg.meta["raster"] = {
            "segments": len(segs),
            "quality": plan.get("quality"),
            "deskew_deg": plan.get("deskew_applied_deg", 0.0),
        }
        mpp = plan.get("scale_m_per_unit")
        if scale_m_per_unit is not None:
            mpp = scale_m_per_unit
            sg.warnings.append(
                "Using the caller-supplied scale for this raster drawing "
                f"({mpp} m per pixel)."
            )
        if mpp is not None:
            sg.scale_m_per_unit = mpp
            sg.scale_provenance = Provenance(
                source="raster_geometry", confidence=0.4,
                evidence="raster path, caller-supplied or calibrated",
            )
        else:
            sg.warnings.append(
                "No scale evidence in this raster: coordinates stay in pixels, so "
                "metric sizes (metres, areas) are not computed. Supply the scale or "
                "a known dimension to enable them."
            )

        if not segs:
            sg.warnings.append(
                "The raster extractor found no line segments — check contrast, "
                "focus and crop of the image."
            )
            return sg

        # Feed the same downstream builder the vector path uses, by re-ingesting the
        # extracted segments as if they were vector paths. Scale: pixels (or the
        # caller's m/px). `ing` here is the original ingest of the raster page, whose
        # vector `segments` are empty — that is exactly why we are here.
        from core.ingest import IngestedDrawing, SourceKind as _SK

        px_ing = IngestedDrawing(
            kind=_SK.IMAGE if ing.kind == SourceKind.IMAGE else ing.kind,
            page_index=ing.page_index,
            page_size_pt=ing.page_size_pt,
            segments=list(segs),  # already ((x1,y1),(x2,y2)) tuples — same convention as ingest
            texts=ing.texts,  # rare: a scanned PDF may still carry a text layer
            image_count=ing.image_count,
            warnings=[],
        )
        # The vector builder expects to set provenance itself; raster segments get
        # raster_geometry provenance via the hook below.
        sg.meta["raster_segments_used"] = len(px_ing.segments)
        _build_vector_model(sg, px_ing, mpp, north_deg, provenance_source="raster_geometry")
        sg.warnings.append(
            "Raster extraction is approximate: walls come from pixel runs, opening "
            "kinds are heuristics. Treat every number as an estimate to verify."
        )
    except Exception as exc:  # noqa: BLE001 — degrade, never crash the demo
        sg.warnings.append(
            f"Raster extraction failed ({type(exc).__name__}: {exc}); returning the "
            "empty model. Supply a CAD-exported PDF for the full pipeline."
        )
        sg.meta["raster_error"] = traceback.format_exc()
    return sg


def save_scene_graph(sg: SceneGraph, path: str | Path) -> Path:
    """Write a scene graph to JSON (UTF-8, pretty). Returns the path written."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(sg.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return p


def load_scene_graph(path: str | Path) -> SceneGraph:
    """Load a scene graph from JSON."""
    return SceneGraph.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


# --------------------------------------------------------------------------- #
# the vector pipeline
# --------------------------------------------------------------------------- #
def _build_vector_model(
    sg: SceneGraph,
    ing: IngestedDrawing,
    scale: float | None,
    north_deg: float | None,
    provenance_source: str = "vector_geometry",
) -> None:
    s = scale if scale is not None else CAD_M_PER_PT  # working scale (metres per pt)
    sf = scale if scale is not None else 1.0  # output factor (1.0 = leave in pt)

    def M(p: tuple[float, float]) -> tuple[float, float]:
        return (round(p[0] * sf, 6), round(p[1] * sf, 6))

    # ---- 1. snap + merge -------------------------------------------------- #
    snapped, snap_stats = geo.snap_axis(ing.segments, SNAP_TOL_DEG)
    merged = geo.merge_collinear(snapped, gap_tol=_tol(MERGE_GAP_M, s), offset_tol=0.5)

    # ---- 2. walls --------------------------------------------------------- #
    walls_pt = _extract_walls(merged, s, scale)
    walls_pt.sort(key=lambda w: (round(geo.seg_midpoint((w.a, w.b))[1], 3), round(geo.seg_midpoint((w.a, w.b))[0], 3)))
    for i, w in enumerate(walls_pt, 1):
        w.wall_id = f"W{i}"

    # ---- 3. planar faces (rooms + outer boundary for is_external) --------- #
    pf = geo.planar_faces([(w.a, w.b) for w in walls_pt], _tol(ROOM_TOL_M, s))
    outer_tol = _tol(OUTER_TOL_M, s)
    for w in walls_pt:
        if not pf.outer:
            w.external = None
            continue
        mid = geo.seg_midpoint((w.a, w.b))
        w.external = any(
            geo.point_segment_distance(mid, (o[i], o[(i + 1) % len(o)])) <= outer_tol
            for o in pf.outer
            for i in range(len(o))
        )
    if walls_pt and not pf.outer:
        sg.warnings.append(
            "The wall network does not close — external/internal walls could not be told apart."
        )

    # ---- 4. openings ------------------------------------------------------ #
    openings = _extract_openings(walls_pt, ing.segments, s, scale)
    for o in openings:
        if o["jambs"] == 0:
            sg.warnings.append(
                f"Opening {o['id']} has no jamb lines at the gap edges — "
                "it may not be a real opening; verify on the drawing."
            )

    # ---- 5. rooms --------------------------------------------------------- #
    faces_sorted = sorted(
        pf.interior,
        key=lambda f: (
            round(sum(p[1] for p in f) / len(f), 3),
            round(sum(p[0] for p in f) / len(f), 3),
        ),
    )
    rooms, room_warnings, unmatched_labels = _name_rooms(faces_sorted, ing.texts, scale)
    sg.warnings.extend(room_warnings)

    # ---- 6. dimensions + scale cross-check -------------------------------- #
    dims = _parse_dimensions(ing.texts, ing.segments, scale)
    _crosscheck_scale(sg, walls_pt, dims)

    # ---- 7. north --------------------------------------------------------- #
    if north_deg is not None:
        sg.north_deg = float(north_deg) % 360.0
        sg.north_provenance = Provenance(
            source="user_supplied", confidence=1.0, evidence="north_deg supplied by caller"
        )
    else:
        ndeg, nprov, nwarn = _detect_north(ing)
        sg.north_deg = ndeg
        sg.north_provenance = nprov
        sg.warnings.extend(nwarn)

    # ---- 8. assemble schema objects --------------------------------------- #
    for w in walls_pt:
        thickness = (
            round(w.thickness * sf, 4) if (w.thickness is not None and scale is not None) else None
        )
        # Raster path: the run-length extractor's confidence is the wall confidence,
        # but it cannot exceed the honesty ceiling for pixel evidence.
        if provenance_source == "raster_geometry":
            _wall_conf = min(w.confidence, 0.70)
        else:
            _wall_conf = w.confidence
        sg.walls.append(
                    Wall(
                        id=w.wall_id,
                        start=M(w.a),
                        end=M(w.b),
                        thickness=thickness,
                        is_external=w.external,
                        provenance=Provenance(
                            source=provenance_source, confidence=_wall_conf, evidence=w.evidence
                        ),
                    )
                )

    for o in openings:
        sg.openings.append(
            Opening(
                id=o["id"],
                kind=o["kind"],
                wall_id=o["wall_id"],
                center=M(o["center"]),
                width=round(o["width"], 4) if o["width"] is not None else None,
                height=None,
                sill_height=None,
                provenance=Provenance(
                    source=provenance_source, confidence=o["confidence"], evidence=o["evidence"]
                ),
            )
        )

    for r in rooms:
        sg.rooms.append(
            Room(
                id=r["id"],
                name=r["name"],
                name_np=r["name_np"],
                polygon=[M(p) for p in r["polygon"]],
                area_m2=round(r["area_m2"], 3) if r["area_m2"] is not None else None,
                provenance=Provenance(
                    source=provenance_source, confidence=r["confidence"], evidence=r["evidence"]
                ),
            )
        )

    for i, d in enumerate(dims, 1):
        sg.dimensions.append(
            Dimension(
                id=f"D{i}",
                value=d["value"],
                unit="m",
                label=d["label"],
                start=M(d["start"]) if d["start"] else None,
                end=M(d["end"]) if d["end"] else None,
                provenance=Provenance(
                    source=provenance_source, confidence=d["conf"], evidence=d["evidence"]
                ),
            )
        )

    # ---- 9. bbox + meta ---------------------------------------------------- #
    pts: list[tuple[float, float]] = []
    for w in walls_pt:
        pts.extend([w.a, w.b])
    for r in rooms:
        pts.extend(r["polygon"])
    if pts:
        minx = min(p[0] for p in pts) * sf
        miny = min(p[1] for p in pts) * sf
        maxx = max(p[0] for p in pts) * sf
        maxy = max(p[1] for p in pts) * sf
        sg.bbox = (minx, miny, maxx, maxy)

    n_paired = sum(1 for w in walls_pt if w.paired)
    sg.meta["coordinate_frame"] = (
        "pdf page points scaled to metres (y down)"
        if scale is not None
        else "pdf page points, UNSCALED (y down) — scale unknown"
    )
    sg.meta["snap_stats"] = snap_stats
    sg.meta["extraction"] = {
        "n_runs": len(merged),
        "n_walls_paired": n_paired,
        "n_walls_single_line": len(walls_pt) - n_paired,
        "n_faces": len(pf.interior),
        "n_outer_cycles": len(pf.outer),
    }
    sg.meta["unmatched_room_labels"] = unmatched_labels
    sg.meta["ingest"] = ing.meta


# --------------------------------------------------------------------------- #
# scale
# --------------------------------------------------------------------------- #
def _derive_scale(
    ing: IngestedDrawing, scale_arg: float | None
) -> tuple[float | None, Provenance, list[str]]:
    """(scale_m_per_pt, provenance, warnings). Explicit arg > CAD scale note > None."""
    notes: list[str] = []
    if scale_arg is not None:
        if scale_arg > 0:
            return (
                float(scale_arg),
                Provenance(
                    source="user_supplied",
                    confidence=1.0,
                    evidence="scale_m_per_unit supplied by caller",
                ),
                notes,
            )
        notes.append(f"Ignored invalid scale_m_per_unit={scale_arg!r} (must be positive).")

    note_text: str | None = None
    note_ratio: int | None = None
    for t in ing.texts:
        m = _SCALE_NOTE_RE.search(t.text)
        if m:
            note_text = t.text.strip()
            note_ratio = int(m.group(1))
            break

    if note_text is not None and ing.kind is SourceKind.VECTOR_PDF:
        conf = 0.75
        ev = (
            f"scale note '{note_text}'; vector CAD export assumed at 1 pt = 25 mm "
            "(1 m = 40 pt)"
        )
        if note_ratio != 100:
            conf = 0.6
            ev += f" (note ratio 1:{note_ratio} differs from the usual 1:100 — verify)"
        return CAD_M_PER_PT, Provenance(source="vector_geometry", confidence=conf, evidence=ev), notes

    if note_text is not None:
        notes.append(
            f"Scale note '{note_text}' found but the drawing is {ing.kind.value}; "
            "the scale was not trusted — pass scale_m_per_unit."
        )
    notes.append(
        "No scale note found — the drawing scale could not be derived. Coordinates are "
        "left in PDF points (unscaled); pass scale_m_per_unit to get metres."
    )
    return None, Provenance(source="default", confidence=0.0, evidence="no usable scale information"), notes


def _crosscheck_scale(sg: SceneGraph, walls_pt: Sequence[_WallGeom], dims: list[dict[str, Any]]) -> None:
    """Corroborate a note-derived scale against parsed dimension texts."""
    if (
        sg.scale_m_per_unit is None
        or sg.scale_provenance.source != "vector_geometry"
        or not dims
        or not walls_pt
    ):
        return
    xs = [p[0] for w in walls_pt for p in (w.a, w.b)]
    ys = [p[1] for w in walls_pt for p in (w.a, w.b)]
    extents = [e for e in (max(xs) - min(xs), max(ys) - min(ys)) if e > 0]
    s = sg.scale_m_per_unit
    cands: list[dict[str, Any]] = []
    for d in dims:
        for e in extents:
            r = d["value"] / e
            if abs(r - s) <= 0.12 * s:
                cands.append(
                    {"value_m": round(d["value"], 4), "extent_pt": round(e, 3), "implied_m_per_pt": r}
                )
    sg.meta["scale_candidates"] = cands
    if cands:
        sg.scale_provenance.confidence = 0.9
        sg.scale_provenance.evidence = (
            (sg.scale_provenance.evidence or "") + f"; corroborated by {len(cands)} dimension text(s)"
        )
    else:
        sg.scale_provenance.confidence = 0.6
        sg.warnings.append(
            "Dimension texts did not corroborate the assumed CAD scale (1 pt = 25 mm) — "
            "verify the drawing scale."
        )


# --------------------------------------------------------------------------- #
# walls
# --------------------------------------------------------------------------- #
def _extract_walls(
    runs: Sequence[geo.Segment], s: float, scale: float | None
) -> list[_WallGeom]:
    """Paired parallel runs → thick walls; unpaired connected runs → thin fallback."""
    cand_runs = [r for r in runs if geo.seg_length(r) >= _tol(PAIR_MIN_RUN_LEN_M, s)]
    cands = geo.pair_parallel(
        cand_runs,
        max_offset=_tol(PAIR_MAX_OFFSET_M, s),
        min_overlap=_tol(PAIR_MIN_OVERLAP_M, s),
        min_offset=_tol(PAIR_MIN_OFFSET_M, s),
        angle_tol_deg=SNAP_TOL_DEG,
    )
    used: set[int] = set()
    pairs: list[dict[str, Any]] = []
    for c in cands:
        if c.i in used or c.j in used:
            continue
        a, b = cand_runs[c.i], cand_runs[c.j]
        ang = geo.seg_angle_deg(a)
        horizontal = ang <= 45.0 or ang >= 135.0
        if horizontal:
            t0 = max(min(a[0][0], a[1][0]), min(b[0][0], b[1][0]))
            t1 = min(max(a[0][0], a[1][0]), max(b[0][0], b[1][0]))
            coord = (a[0][1] + b[0][1]) / 2.0
        else:
            t0 = max(min(a[0][1], a[1][1]), min(b[0][1], b[1][1]))
            t1 = min(max(a[0][1], a[1][1]), max(b[0][1], b[1][1]))
            coord = (a[0][0] + b[0][0]) / 2.0
        if t1 - t0 <= 0:
            continue
        used.add(c.i)
        used.add(c.j)
        pairs.append(
            {
                "horizontal": horizontal,
                "coord": coord,
                "t0": t0,
                "t1": t1,
                "thickness": c.offset,
            }
        )

    # consolidate pairs sharing a centreline into wall runs
    walls: list[_WallGeom] = []
    centre_tol = _tol(CENTRE_TOL_M, s)
    for horizontal in (True, False):
        group_pairs = sorted(
            (p for p in pairs if p["horizontal"] == horizontal), key=lambda p: p["coord"]
        )
        clusters: list[list[dict[str, Any]]] = []
        for p in group_pairs:
            if clusters and abs(p["coord"] - sum(c["coord"] for c in clusters[-1]) / len(clusters[-1])) <= centre_tol:
                clusters[-1].append(p)
            else:
                clusters.append([p])
        for cluster in clusters:
            coord = sum(c["coord"] for c in cluster) / len(cluster)
            thickness = sorted(c["thickness"] for c in cluster)[len(cluster) // 2]
            spans = sorted((c["t0"], c["t1"]) for c in cluster)
            merged_spans: list[tuple[float, float]] = []
            cur0, cur1 = spans[0]
            for s0, s1 in spans[1:]:
                if s0 <= cur1 + _tol(SPAN_MERGE_GAP_M, s):
                    cur1 = max(cur1, s1)
                else:
                    merged_spans.append((cur0, cur1))
                    cur0, cur1 = s0, s1
            merged_spans.append((cur0, cur1))
            # split at breaks too large to be openings → separate walls
            chunks: list[list[tuple[float, float]]] = []
            cur = [merged_spans[0]]
            for sp in merged_spans[1:]:
                if sp[0] - cur[-1][1] > _tol(MAX_OPENING_M, s):
                    chunks.append(cur)
                    cur = [sp]
                else:
                    cur.append(sp)
            chunks.append(cur)
            for chunk in chunks:
                a_pt = (chunk[0][0], coord) if horizontal else (coord, chunk[0][0])
                b_pt = (chunk[-1][1], coord) if horizontal else (coord, chunk[-1][1])
                plausible = _tol(0.05, s) <= thickness <= _tol(0.45, s)
                conf = 0.95 if plausible else 0.85
                if scale is not None:
                    ev = (
                        f"wall run: {len(cluster)} parallel line pair(s), offset "
                        f"{thickness:.1f} pt ({thickness * scale:.2f} m); "
                        f"{len(chunk)} solid span(s); snapped to axis"
                    )
                else:
                    ev = (
                        f"wall run: {len(cluster)} parallel line pair(s), offset "
                        f"{thickness:.1f} pt (unscaled); {len(chunk)} solid span(s); snapped to axis"
                    )
                walls.append(
                    _WallGeom(
                        a=a_pt,
                        b=b_pt,
                        horizontal=horizontal,
                        thickness=thickness,
                        spans=chunk,
                        confidence=conf,
                        evidence=ev,
                        paired=True,
                    )
                )

    # fallback: single-line walls (thickness unknown), only if they join the network
    jtol = _tol(JUNCTION_TOL_M, s)
    for idx, run in enumerate(cand_runs):
        if idx in used or geo.seg_length(run) < _tol(FALLBACK_MIN_LEN_M, s):
            continue
        if not any(
            geo.point_segment_distance(run[0], (w.a, w.b)) <= jtol
            or geo.point_segment_distance(run[1], (w.a, w.b)) <= jtol
            for w in walls
        ):
            continue
        ang = geo.seg_angle_deg(run)
        horizontal = ang <= 45.0 or ang >= 135.0
        t0 = min(run[0][0], run[1][0]) if horizontal else min(run[0][1], run[1][1])
        t1 = max(run[0][0], run[1][0]) if horizontal else max(run[0][1], run[1][1])
        coord = run[0][1] if horizontal else run[0][0]
        a_pt = (t0, coord) if horizontal else (coord, t0)
        b_pt = (t1, coord) if horizontal else (coord, t1)
        walls.append(
            _WallGeom(
                a=a_pt,
                b=b_pt,
                horizontal=horizontal,
                thickness=None,
                spans=[(t0, t1)],
                confidence=0.4,
                evidence=(
                    "single-line wall: no parallel partner found — thickness unknown; "
                    "it connects to the rest of the wall network"
                ),
                paired=False,
            )
        )
        used.add(idx)
    return walls


def _jamb_at(w: _WallGeom, edge: float, all_segments: Sequence[geo.Segment], s: float) -> bool:
    """Is there a jamb line (short, non-parallel, inside the wall band) at `edge`?"""
    if w.thickness is None:
        return False
    t = w.thickness
    wall_ang = 0.0 if w.horizontal else 90.0
    for seg in all_segments:
        ln = geo.seg_length(seg)
        if ln <= 1e-9 or ln > JAMB_MAX_LEN_FACTOR * t or ln < 0.2 * t:
            continue
        d = abs(geo.seg_angle_deg(seg) - wall_ang) % 180.0
        d = min(d, 180.0 - d)
        if d < JAMB_MIN_ANGLE_DEG:
            continue
        mx, my = geo.seg_midpoint(seg)
        along = mx if w.horizontal else my
        lateral = my if w.horizontal else mx
        if abs(along - edge) > JAMB_EDGE_TOL_FACTOR * t:
            continue
        if abs(lateral - w.coord) > JAMB_LATERAL_TOL_FACTOR * t:
            continue
        return True
    return False


def _classify_opening(width_m: float | None) -> tuple[OpeningKind, float, str]:
    """door / window by width band, with an honest confidence and a note.

    Bands: door 0.6–1.0 m; ambiguous 1.0–1.3 m (either a wide door or a narrow
    window → window with reduced confidence); window 1.3–3.0 m; outside → unknown.
    """
    if width_m is None:
        return OpeningKind.UNKNOWN, 0.3, "width unknown (scale not determined)"
    if width_m < 0.5:
        return OpeningKind.UNKNOWN, 0.3, "narrower than a standard opening"
    if width_m < 0.6:
        return OpeningKind.WINDOW, 0.5, "narrow window band (0.5–0.6 m)"
    if width_m < 1.0:
        return OpeningKind.DOOR, 0.7, "door width band (0.6–1.0 m)"
    if width_m <= 1.3:
        return OpeningKind.WINDOW, 0.6, "ambiguous band 1.0–1.3 m (could be a wide door)"
    if width_m <= 3.0:
        return OpeningKind.WINDOW, 0.75, "window width band (>1.3 m)"
    return OpeningKind.UNKNOWN, 0.3, "wider than a standard opening"


def _extract_openings(
    walls: Sequence[_WallGeom],
    all_segments: Sequence[geo.Segment],
    s: float,
    scale: float | None,
) -> list[dict[str, Any]]:
    """Gaps between a wall's solid spans, kept when ≥ MIN_OPENING and jamb-capped."""
    out: list[dict[str, Any]] = []
    for w in walls:
        if len(w.spans) < 2:
            continue
        for (t0, t1), (u0, u1) in zip(w.spans, w.spans[1:]):
            gap = u0 - t1
            if gap < _tol(MIN_OPENING_M, s) or gap > _tol(MAX_OPENING_M, s):
                continue
            jambs = int(_jamb_at(w, t1, all_segments, s)) + int(_jamb_at(w, u0, all_segments, s))
            if jambs == 0 and gap < _tol(0.6, s):
                continue  # small uncapped gap: drawing noise, not an opening
            width_m = gap * scale if scale is not None else None
            kind, kind_conf, note = _classify_opening(width_m)
            geom_conf = {2: 0.85, 1: 0.6, 0: 0.45}[jambs]
            conf = round(min(geom_conf, kind_conf), 2)
            mid = (t1 + u0) / 2.0
            center = (mid, w.coord) if w.horizontal else (w.coord, mid)
            if scale is not None:
                ev = (
                    f"gap {gap:.1f} pt ({width_m:.2f} m) between wall spans; "
                    f"{jambs}/2 jamb line(s) at the edges; {note}"
                )
            else:
                ev = (
                    f"gap {gap:.1f} pt (unscaled) between wall spans; "
                    f"{jambs}/2 jamb line(s) at the edges; width unknown without a scale"
                )
            out.append(
                {
                    "id": f"O{len(out) + 1}",
                    "wall_id": w.wall_id,
                    "kind": kind,
                    "width": width_m,
                    "center": center,
                    "confidence": conf,
                    "evidence": ev,
                    "jambs": jambs,
                }
            )
    return out


# --------------------------------------------------------------------------- #
# rooms
# --------------------------------------------------------------------------- #
def _room_label(text: str) -> tuple[str, str] | None:
    """(drawing label, Nepali name) if the text names a room; else None."""
    t = text.strip()
    if not t or len(t) > 40:
        return None
    if _MEASURE_TAIL_RE.search(t):  # e.g. "STAIR 1.00 M" is a note, not a room name
        return None
    up = t.upper()
    for pattern, np_name in ROOM_KEYWORDS:
        if re.search(pattern, up):
            return t, np_name
    return None


def _name_rooms(
    faces: Sequence[list[tuple[float, float]]],
    texts: Sequence[TextItem],
    scale: float | None,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Match label texts to closed faces; returns (rooms, warnings, unmatched labels).

    One Room is emitted per matched label. When several labels fall in the same
    face the drawing does not close a wall between them, so each label still
    gets its own Room (same polygon) with reduced confidence and an explicit
    warning — Karmi lists what the drawing says instead of inventing a wall.
    """
    labels: list[tuple[TextItem, str, str]] = []
    for t in texts:
        hit = _room_label(t.text)
        if hit is not None:
            labels.append((t, hit[0], hit[1]))

    rooms: list[dict[str, Any]] = []
    warnings: list[str] = []
    for face in faces:
        area_pt2 = geo.polygon_area(face)
        area_m2 = area_pt2 * scale * scale if scale is not None else None
        inside = [l for l in labels if geo.point_in_polygon((l[0].x, l[0].y), face)]
        if not inside:
            rooms.append(
                {
                    "id": f"R{len(rooms) + 1}",
                    "name": None,
                    "name_np": None,
                    "polygon": list(face),
                    "area_m2": area_m2,
                    "confidence": 0.45,
                    "evidence": "closed face of the wall network with no label text inside",
                }
            )
            continue
        inside.sort(key=lambda l: (round(l[0].y, 1), round(l[0].x, 1)))
        shared = len(inside) > 1
        if shared:
            names = ", ".join(f"'{l[0].text}'" for l in inside)
            warnings.append(
                f"Room labels {names} fall inside one undivided space (the drawing does not "
                "close a wall between them) — every label is listed with the same boundary; "
                "verify room separation."
            )
        for t, name, np_name in inside:
            if scale is not None:
                ev = f"label '{t.text}' at ({t.x:.1f}, {t.y:.1f}) pt lies inside a closed wall face"
            else:
                ev = f"label '{t.text}' at ({t.x:.1f}, {t.y:.1f}) pt lies inside a closed wall face (unscaled)"
            if shared:
                others = ", ".join(f"'{l[0].text}'" for l in inside if l[0] is not t)
                ev += f"; face shared with {others} — no wall closes between them in the drawing"
            rooms.append(
                {
                    "id": f"R{len(rooms) + 1}",
                    "name": name,
                    "name_np": np_name,
                    "polygon": list(face),
                    "area_m2": area_m2,
                    "confidence": 0.75 if not shared else 0.5,
                    "evidence": ev,
                }
            )

    unmatched = [
        t.text
        for t, _, _ in labels
        if not any(geo.point_in_polygon((t.x, t.y), f) for f in faces)
    ]
    for text in unmatched:
        warnings.append(
            f"Room label '{text}' does not fall inside any closed room — it was not matched "
            "to a room; verify on the drawing."
        )
    return rooms, warnings, unmatched


# --------------------------------------------------------------------------- #
# dimensions
# --------------------------------------------------------------------------- #
def _parse_dim_text(text: str) -> tuple[float, str] | None:
    """Parse a whole dimension text into (metres, note). Devanagari digits OK.

    Handles ``10.0 m`` / ``10.0m``, ``5'-0"`` / ``5' - 6"``, plain feet, mm,
    Devanagari digits (०-९) and Devanagari unit words (मिटर/मि, फिट/फुट, इन्च).
    """
    t = text.strip().translate(_DEVA_DIGITS)
    if not t:
        return None
    m = re.fullmatch(r"(\d+)\s*['′]\s*[-–—]?\s*(\d+(?:\.\d+)?)?\s*[\"″]?", t)
    if m and ("'" in t or "′" in t):
        feet = float(m.group(1))
        inches = float(m.group(2) or 0.0)
        if inches:
            return feet * 0.3048 + inches * 0.0254, "feet-inches converted to metres"
        return feet * 0.3048, "feet converted to metres"
    m = re.fullmatch(
        r"(\d+)\s*(?:फिट|फुट|ft|feet|foot)\s*(?:(\d+(?:\.\d+)?)\s*(?:इन्च|inch|inches|in))?", t, re.I
    )
    if m:
        feet = float(m.group(1))
        inches = float(m.group(2) or 0.0)
        if inches:
            return feet * 0.3048 + inches * 0.0254, "feet-inches converted to metres"
        return feet * 0.3048, "feet converted to metres"
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:m|m\.|mtr|meters?|metres?|मिटर|मीटर|मि\.?|मी)", t, re.I)
    if m:
        return float(m.group(1)), "metres"
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:mm|मिमि|मिलिमिटर)", t, re.I)
    if m:
        return float(m.group(1)) / 1000.0, "millimetres converted to metres"
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:'|′|ft|feet|foot|फिट|फुट)", t, re.I)
    if m:
        return float(m.group(1)) * 0.3048, "feet converted to metres"
    return None


def _parse_dimensions(
    texts: Sequence[TextItem], segments: Sequence[geo.Segment], scale: float | None
) -> list[dict[str, Any]]:
    """Dimension texts, with best-effort association to a nearby matching line."""
    out: list[dict[str, Any]] = []
    for t in texts:
        parsed = _parse_dim_text(t.text)
        if parsed is None:
            continue
        value_m, note = parsed
        conf = 0.7
        start: tuple[float, float] | None = None
        end: tuple[float, float] | None = None
        ev = f"text '{t.text.strip()}' → {value_m:.4g} m ({note})"
        if scale is not None:
            best: tuple[float, geo.Segment, float] | None = None
            for seg in segments:
                ln = geo.seg_length(seg)
                if ln < 10.0:
                    continue
                mx, my = geo.seg_midpoint(seg)
                dist = math.hypot(mx - t.x, my - t.y)
                if dist > DIM_LINE_MAX_DIST_PT:
                    continue
                implied = ln * scale
                if abs(implied - value_m) <= max(0.03 * value_m, 0.05):
                    if best is None or dist < best[0]:
                        best = (dist, seg, implied)
            if best is not None:
                start, end = best[1]
                conf = 0.9
                ev += (
                    f"; matches a {geo.seg_length(best[1]):.0f} pt line nearby "
                    f"({best[2]:.2f} m at the derived scale)"
                )
        out.append(
            {
                "value": value_m,
                "label": t.text.strip(),
                "conf": conf,
                "evidence": ev,
                "start": start,
                "end": end,
            }
        )
    return out


# --------------------------------------------------------------------------- #
# north
# --------------------------------------------------------------------------- #
def _detect_north(
    ing: IngestedDrawing,
) -> tuple[float | None, Provenance, list[str]]:
    """Find an 'N' text with a short line near one end → bearing (0 = up)."""
    n_texts = [t for t in ing.texts if _NORTH_TEXT_RE.fullmatch(t.text.strip())]
    if not n_texts:
        return (
            None,
            Provenance(source="default", confidence=0.0, evidence="no north indicator found"),
            [
                "No north arrow found on the drawing — orientation is unknown; supply "
                "north_deg or check the drawing's own north arrow."
            ],
        )
    best: tuple[float, geo.Segment, TextItem, float] | None = None
    for seg in ing.segments:
        ln = geo.seg_length(seg)
        if ln < 4.0 or ln > 90.0:
            continue
        for t in n_texts:
            d0 = math.hypot(seg[0][0] - t.x, seg[0][1] - t.y)
            d1 = math.hypot(seg[1][0] - t.x, seg[1][1] - t.y)
            dmin = min(d0, d1)
            if dmin > 22.0:
                continue
            if best is None or ln > best[0]:
                best = (ln, seg, t, dmin)
    if best is None:
        return (
            None,
            Provenance(
                source="vector_geometry",
                confidence=0.0,
                evidence="'N' text found but no short line near it",
            ),
            [
                "An 'N' label exists but no arrow line was found near it — orientation is "
                "unknown."
            ],
        )
    _, seg, t, _ = best
    d0 = math.hypot(seg[0][0] - t.x, seg[0][1] - t.y)
    d1 = math.hypot(seg[1][0] - t.x, seg[1][1] - t.y)
    tip, tail = (seg[0], seg[1]) if d0 <= d1 else (seg[1], seg[0])
    bearing = math.degrees(math.atan2(tip[0] - tail[0], -(tip[1] - tail[1]))) % 360.0
    return (
        round(bearing, 1),
        Provenance(
            source="vector_geometry",
            confidence=0.8,
            evidence=(
                f"arrow line (length {geo.seg_length(seg):.0f} pt) with 'N' text at the tip; "
                f"bearing {bearing:.1f}° clockwise from up on the page"
            ),
        ),
        [],
    )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _format_summary(sg: SceneGraph) -> str:
    lines: list[str] = []
    lines.append(f"Karmi scene graph — {sg.source_file}")
    size = sg.meta.get("page_size_pt")
    size_txt = f"{size[0]:.0f} x {size[1]:.0f} pt" if size else "?"
    lines.append(
        f"  source      : {sg.source_kind.value}, page {sg.meta.get('page_index', 0) + 1}, {size_txt}"
    )
    if sg.scale_m_per_unit is not None:
        lines.append(
            f"  scale       : {sg.scale_m_per_unit:.4f} m/pt "
            f"(confidence {sg.scale_provenance.confidence:.2f}, {sg.scale_provenance.source})"
        )
    else:
        lines.append("  scale       : UNKNOWN — coordinates are PDF points (unscaled)")
    if sg.scale_provenance.evidence:
        lines.append(f"                {sg.scale_provenance.evidence}")
    if sg.north_deg is not None:
        lines.append(
            f"  north       : {sg.north_deg:.1f}° "
            f"(confidence {sg.north_provenance.confidence:.2f}, {sg.north_provenance.source})"
        )
    else:
        lines.append("  north       : UNKNOWN (no north arrow found)")
    lines.append(f"  coordinates : {sg.meta.get('coordinate_frame', '?')}")

    n_ext = sum(1 for w in sg.walls if w.is_external)
    n_int = sum(1 for w in sg.walls if w.is_external is False)
    lines.append("")
    lines.append(f"  walls ({len(sg.walls)}: {n_ext} external, {n_int} internal)")
    for w in sg.walls:
        kind = "ext" if w.is_external else ("int" if w.is_external is False else "?  ")
        t = f"{w.thickness:.2f} m" if w.thickness is not None else "unknown"
        lines.append(
            f"    {w.id:<4} {kind}  ({w.start[0]:7.2f},{w.start[1]:7.2f}) -> "
            f"({w.end[0]:7.2f},{w.end[1]:7.2f})  len {w.length:6.2f}  t {t:<9} conf {w.provenance.confidence:.2f}"
        )

    kinds: dict[str, int] = {}
    for o in sg.openings:
        kinds[o.kind.value] = kinds.get(o.kind.value, 0) + 1
    kind_txt = ", ".join(f"{v} {k}" for k, v in sorted(kinds.items()))
    lines.append("")
    lines.append(f"  openings ({len(sg.openings)}{': ' + kind_txt if kind_txt else ''})")
    for o in sg.openings:
        w_txt = f"{o.width:.2f} m" if o.width is not None else "unknown"
        lines.append(
            f"    {o.id:<4} {o.kind.value:<7} on {o.wall_id or '-':<4} w {w_txt:<10} "
            f"centre ({o.center[0]:6.2f},{o.center[1]:6.2f})  conf {o.provenance.confidence:.2f}"
        )

    lines.append("")
    lines.append(f"  rooms ({len(sg.rooms)})")
    for r in sg.rooms:
        name = r.name or "(unlabeled)"
        np_name = f" ({r.name_np})" if r.name_np else ""
        area = f"{r.area_m2:7.2f} m²" if r.area_m2 is not None else "    ?    "
        lines.append(
            f"    {r.id:<4} {name}{np_name:<18} {area}  conf {r.provenance.confidence:.2f}"
        )

    lines.append("")
    lines.append(f"  dimensions ({len(sg.dimensions)})")
    for d in sg.dimensions:
        lines.append(f"    {d.id:<4} {d.label}  = {d.value:.4g} m  conf {d.provenance.confidence:.2f}")

    lines.append("")
    lines.append(f"  warnings ({len(sg.warnings)})")
    for wmsg in sg.warnings:
        lines.append(f"    - {wmsg}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m core.model",
        description="Build a Karmi scene graph from a naksa drawing (offline, deterministic).",
    )
    ap.add_argument("drawing", help="path to the drawing (vector PDF)")
    ap.add_argument("--out", default=None, help="output JSON path (default: <drawing stem>.scene.json)")
    ap.add_argument("--scale", type=float, default=None, help="metres per PDF point, if known")
    ap.add_argument("--north", type=float, default=None, help="north bearing in degrees (0 = up)")
    args = ap.parse_args(argv)

    sg = build_scene_graph(
        args.drawing, scale_m_per_unit=args.scale, north_deg=args.north, ai=None
    )
    out = Path(args.out) if args.out else Path(args.drawing).with_suffix(".scene.json")
    save_scene_graph(sg, out)
    print(_format_summary(sg))
    print()
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "build_scene_graph",
    "save_scene_graph",
    "load_scene_graph",
    "main",
]