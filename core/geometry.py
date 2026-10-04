"""Karmi — pure geometry helpers for drawing extraction.

No I/O, no AI, no third-party imports (stdlib only; numpy is deliberately not
needed). Everything works on plain Python tuples so the functions are trivially
unit-testable:

* a *segment* is ``((x1, y1), (x2, y2))``
* a *polygon* is a list of ``(x, y)`` vertices

Units are whatever the caller uses — PDF points during extraction, metres after
scaling. Tolerances are always passed in the *same unit as the data*.

Face orientation convention (used by :func:`planar_faces` / :func:`close_rooms`):
the half-edge traversal follows "next = first edge clockwise from the reverse
direction", which traces every bounded (interior) face with a **positive**
signed area and every outer boundary cycle with a **negative** signed area.
This holds for y-down PDF page coordinates exactly as it does for y-up maths
coordinates, because the rule and the shoelace formula are pure coordinate
arithmetic.
"""

from __future__ import annotations

import math
from typing import Iterable, NamedTuple, Sequence

Point = tuple[float, float]
Segment = tuple[Point, Point]

_EPS = 1e-9


# --------------------------------------------------------------------------- #
# basic measures
# --------------------------------------------------------------------------- #
def seg_length(seg: Segment) -> float:
    """Euclidean length of a segment."""
    (x1, y1), (x2, y2) = seg
    return math.hypot(x2 - x1, y2 - y1)


def seg_midpoint(seg: Segment) -> Point:
    (x1, y1), (x2, y2) = seg
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def seg_angle_deg(seg: Segment) -> float:
    """Direction of the segment in degrees, normalised to [0, 180)."""
    (x1, y1), (x2, y2) = seg
    return math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180.0


def _axis_residual_deg(angle_deg: float) -> float:
    """Deviation of an angle in [0, 180) from the nearest axis (0 or 90)."""
    r = angle_deg % 90.0
    return min(r, 90.0 - r)


def point_segment_distance(p: Point, seg: Segment) -> float:
    """Shortest distance from a point to a finite segment."""
    (x1, y1), (x2, y2) = seg
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    if l2 <= _EPS:
        return math.hypot(p[0] - x1, p[1] - y1)
    t = ((p[0] - x1) * dx + (p[1] - y1) * dy) / l2
    t = max(0.0, min(1.0, t))
    return math.hypot(p[0] - (x1 + t * dx), p[1] - (y1 + t * dy))


def _point_line_distance(p: Point, seg: Segment) -> float:
    """Perpendicular distance from a point to the *infinite* line of a segment."""
    (x1, y1), (x2, y2) = seg
    dx, dy = x2 - x1, y2 - y1
    ln = math.hypot(dx, dy)
    if ln <= _EPS:
        return math.hypot(p[0] - x1, p[1] - y1)
    return abs(dx * (y1 - p[1]) - (x1 - p[0]) * dy) / ln


def _signed_area(poly: Sequence[Point]) -> float:
    """Shoelace signed area (positive = interior face under our traversal rule)."""
    a = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def polygon_area(poly: Sequence[Point]) -> float:
    """Area of a polygon (shoelace, absolute value)."""
    return abs(_signed_area(poly))


def point_in_polygon(p: Point, poly: Sequence[Point]) -> bool:
    """Even-odd ray cast; points exactly on an edge count as inside."""
    n = len(poly)
    if n < 3:
        return False
    x, y = p
    inside = False
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if point_segment_distance(p, ((x1, y1), (x2, y2))) <= 1e-9:
            return True
        if (y1 > y) != (y2 > y):
            x_at = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_at:
                inside = not inside
    return inside


def segments_bbox(segments: Iterable[Segment]) -> tuple[float, float, float, float] | None:
    """(minx, miny, maxx, maxy) over all segment endpoints, or None if empty."""
    xs: list[float] = []
    ys: list[float] = []
    for (x1, y1), (x2, y2) in segments:
        xs.extend((x1, x2))
        ys.extend((y1, y2))
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


# --------------------------------------------------------------------------- #
# axis snapping
# --------------------------------------------------------------------------- #
def snap_axis(
    segments: Sequence[Segment], angle_tol_deg: float = 3.0
) -> tuple[list[Segment], dict[str, float]]:
    """Snap near-horizontal / near-vertical segments onto exact axes.

    A segment whose angle is within ``angle_tol_deg`` of 0/180 becomes exactly
    horizontal (both y set to the mean); within ``angle_tol_deg`` of 90/270 it
    becomes exactly vertical. Everything else is passed through unchanged.

    Returns ``(snapped_segments, stats)`` where ``stats`` carries the residual
    angle information (how far the snapped segments were from their axis).
    """
    out: list[Segment] = []
    n_h = n_v = n_unsnapped = n_dropped = 0
    residuals: list[float] = []
    for seg in segments:
        (x1, y1), (x2, y2) = seg
        if seg_length(seg) <= _EPS:
            n_dropped += 1
            continue
        ang = seg_angle_deg(seg)
        resid = _axis_residual_deg(ang)
        if resid <= angle_tol_deg and (ang <= angle_tol_deg or ang >= 180.0 - angle_tol_deg):
            y = (y1 + y2) / 2.0
            out.append(((min(x1, x2), y), (max(x1, x2), y)))
            n_h += 1
            residuals.append(resid)
        elif abs(ang - 90.0) <= angle_tol_deg:
            x = (x1 + x2) / 2.0
            out.append(((x, min(y1, y2)), (x, max(y1, y2))))
            n_v += 1
            residuals.append(resid)
        else:
            out.append(((x1, y1), (x2, y2)))
            n_unsnapped += 1
    stats: dict[str, float] = {
        "n_total": float(len(segments)),
        "n_horizontal": float(n_h),
        "n_vertical": float(n_v),
        "n_unsnapped": float(n_unsnapped),
        "n_dropped": float(n_dropped),
        "max_residual_deg": max(residuals) if residuals else 0.0,
        "mean_residual_deg": (sum(residuals) / len(residuals)) if residuals else 0.0,
    }
    return out, stats


# --------------------------------------------------------------------------- #
# collinear merging
# --------------------------------------------------------------------------- #
def merge_collinear(
    segments: Sequence[Segment],
    gap_tol: float,
    angle_tol: float = 1.0,
    offset_tol: float = 0.5,
) -> list[Segment]:
    """Merge collinear, end-to-end runs into long walls.

    Segments are grouped by axis and offset (within ``offset_tol`` of the
    group's mean offset); within a group, spans closer than ``gap_tol`` are
    merged. Openings are much wider than ``gap_tol`` in practice, so they are
    preserved — a gap only closes when the caller asks it to.

    ``angle_tol`` (degrees) decides which segments count as axis-aligned;
    anything else is passed through untouched.
    """
    h: list[tuple[float, float, float]] = []  # (y, x0, x1)
    v: list[tuple[float, float, float]] = []  # (x, y0, y1)
    rest: list[Segment] = []
    for seg in segments:
        if seg_length(seg) <= _EPS:
            continue
        ang = seg_angle_deg(seg)
        resid = _axis_residual_deg(ang)
        if resid <= angle_tol and (ang <= angle_tol or ang >= 180.0 - angle_tol):
            (x1, y1), (x2, y2) = seg
            h.append(((y1 + y2) / 2.0, min(x1, x2), max(x1, x2)))
        elif abs(ang - 90.0) <= angle_tol:
            (x1, y1), (x2, y2) = seg
            v.append(((x1 + x2) / 2.0, min(y1, y2), max(y1, y2)))
        else:
            rest.append(seg)

    merged: list[Segment] = []
    for items, vertical in ((h, False), (v, True)):
        if not items:
            continue
        items = sorted(items)
        clusters: list[list[tuple[float, float, float]]] = []
        for item in items:
            if clusters and abs(item[0] - (sum(c[0] for c in clusters[-1]) / len(clusters[-1]))) <= offset_tol:
                clusters[-1].append(item)
            else:
                clusters.append([item])
        for cluster in clusters:
            coord = sum(c[0] for c in cluster) / len(cluster)
            spans = sorted((c[1], c[2]) for c in cluster)
            cur0, cur1 = spans[0]
            for s0, s1 in spans[1:]:
                if s0 <= cur1 + gap_tol:
                    cur1 = max(cur1, s1)
                else:
                    merged.append(((cur0, coord), (cur1, coord)) if not vertical else ((coord, cur0), (coord, cur1)))
                    cur0, cur1 = s0, s1
            merged.append(((cur0, coord), (cur1, coord)) if not vertical else ((coord, cur0), (coord, cur1)))
    return merged + rest


# --------------------------------------------------------------------------- #
# parallel pairing (wall thickness)
# --------------------------------------------------------------------------- #
class PairCandidate(NamedTuple):
    """A candidate wall: two parallel runs ``i`` and ``j`` at ``offset`` apart
    (perpendicular distance, the wall thickness) overlapping by ``overlap``."""

    i: int
    j: int
    offset: float
    overlap: float


def pair_parallel(
    lines: Sequence[Segment],
    max_offset: float,
    min_overlap: float,
    *,
    min_offset: float = 0.0,
    angle_tol_deg: float = 3.0,
) -> list[PairCandidate]:
    """Find parallel line pairs that can form a thick wall.

    ``lines`` are runs (typically the output of :func:`merge_collinear`).
    Returns :class:`PairCandidate` tuples ``(i, j, offset, overlap)`` sorted by
    increasing offset (then decreasing overlap). ``min_offset`` filters out
    duplicate/near-coincident lines.
    """
    out: list[PairCandidate] = []
    n = len(lines)
    for i in range(n):
        a = lines[i]
        la = seg_length(a)
        if la <= _EPS:
            continue
        ang_a = seg_angle_deg(a)
        ux, uy = (a[1][0] - a[0][0]) / la, (a[1][1] - a[0][1]) / la
        for j in range(i + 1, n):
            b = lines[j]
            lb = seg_length(b)
            if lb <= _EPS:
                continue
            d = abs(ang_a - seg_angle_deg(b))
            d = min(d, 180.0 - d)
            if d > angle_tol_deg:
                continue
            offset = (_point_line_distance(seg_midpoint(a), b) + _point_line_distance(seg_midpoint(b), a)) / 2.0
            if offset < min_offset or offset > max_offset:
                continue
            # overlap: project b onto a's axis and intersect the intervals
            t0 = (b[0][0] - a[0][0]) * ux + (b[0][1] - a[0][1]) * uy
            t1 = (b[1][0] - a[0][0]) * ux + (b[1][1] - a[0][1]) * uy
            lo, hi = min(t0, t1), max(t0, t1)
            overlap = max(0.0, min(la, hi) - max(0.0, lo))
            if overlap < min_overlap:
                continue
            out.append(PairCandidate(i, j, offset, overlap))
    out.sort(key=lambda c: (c.offset, -c.overlap, c.i, c.j))
    return out


# --------------------------------------------------------------------------- #
# planar graph + face traversal (room polygons)
# --------------------------------------------------------------------------- #
class PlanarFaces(NamedTuple):
    """``interior``: bounded faces (rooms). ``outer``: outer boundary cycles."""

    interior: list[list[Point]]
    outer: list[list[Point]]


class _NodeIndex:
    """Cluster points within ``tol`` into integer node ids."""

    def __init__(self, tol: float) -> None:
        self.tol = max(tol, _EPS)
        self.pts: list[Point] = []
        self._grid: dict[tuple[int, int], list[int]] = {}

    def get(self, p: Point) -> int:
        cx = math.floor(p[0] / self.tol)
        cy = math.floor(p[1] / self.tol)
        for gx in (cx - 1, cx, cx + 1):
            for gy in (cy - 1, cy, cy + 1):
                for idx in self._grid.get((gx, gy), ()):
                    q = self.pts[idx]
                    if abs(q[0] - p[0]) <= self.tol and abs(q[1] - p[1]) <= self.tol:
                        return idx
        idx = len(self.pts)
        self.pts.append((float(p[0]), float(p[1])))
        self._grid.setdefault((cx, cy), []).append(idx)
        return idx


def _project_param(p: Point, seg: Segment) -> float | None:
    """Parameter t in [0, 1] of the closest point of ``p`` on the segment line."""
    (x1, y1), (x2, y2) = seg
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    if l2 <= _EPS:
        return None
    return ((p[0] - x1) * dx + (p[1] - y1) * dy) / l2


def _segment_intersection(a: Segment, b: Segment) -> tuple[float, float] | None:
    """Proper intersection: returns (t_on_a, t_on_b) if the segments cross."""
    (ax1, ay1), (ax2, ay2) = a
    (bx1, by1), (bx2, by2) = b
    d1x, d1y = ax2 - ax1, ay2 - ay1
    d2x, d2y = bx2 - bx1, by2 - by1
    den = d1x * d2y - d1y * d2x
    if abs(den) <= 1e-12:
        return None
    t = ((bx1 - ax1) * d2y - (by1 - ay1) * d2x) / den
    u = ((bx1 - ax1) * d1y - (by1 - ay1) * d1x) / den
    if -1e-9 <= t <= 1.0 + 1e-9 and -1e-9 <= u <= 1.0 + 1e-9:
        return (t, u)
    return None


def _next_half_edge(
    h: tuple[int, int], adj: dict[int, set[int]], pts: dict[int, Point]
) -> tuple[int, int]:
    """Half-edge traversal rule: first edge clockwise from the reverse direction.

    This keeps the traced face on the left of every directed edge, so bounded
    faces come out with positive signed area (see module docstring).
    """
    u, v = h
    pu, pv = pts[u], pts[v]
    back = math.atan2(pu[1] - pv[1], pu[0] - pv[0])
    best: int | None = None
    best_delta: float | None = None
    for w in adj.get(v, ()):
        if w == u:
            continue
        pw = pts[w]
        theta = math.atan2(pw[1] - pv[1], pw[0] - pv[0])
        delta = (back - theta) % (2.0 * math.pi)
        if delta <= 1e-12:
            delta = 2.0 * math.pi  # overlapping collinear edge: last resort only
        if best_delta is None or delta < best_delta:
            best, best_delta = w, delta
    if best is None:
        return (v, u)  # dead end: bounce back
    return (v, best)


def _clean_cycle(poly: list[Point]) -> list[Point]:
    """Drop consecutive duplicates and zero-width spikes (out-and-back walks)."""
    pts: list[Point] = []
    for p in poly:
        if not pts or pts[-1] != p:
            pts.append(p)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    while len(pts) >= 3:
        n = len(pts)
        removed = False
        for i in range(n):
            if pts[(i - 1) % n] == pts[(i + 1) % n]:
                del pts[i]
                removed = True
                break
        if not removed:
            break
        dedup: list[Point] = []
        for p in pts:
            if not dedup or dedup[-1] != p:
                dedup.append(p)
        if len(dedup) > 1 and dedup[0] == dedup[-1]:
            dedup.pop()
        pts = dedup
    return pts


def planar_faces(walls: Sequence[Segment], tol: float) -> PlanarFaces:
    """Build the planar graph of wall centrelines and trace every face.

    Walls are split at T-junctions and crossings, endpoints within ``tol`` are
    clustered into nodes, then a half-edge traversal extracts all bounded faces
    (rooms) and all outer boundary cycles. Degenerate (zero-area) walks from
    dangling edges are discarded.
    """
    walls = [((float(a[0]), float(a[1])), (float(b[0]), float(b[1]))) for a, b in walls]
    walls = [w for w in walls if seg_length(w) > _EPS]
    if not walls or tol <= 0:
        return PlanarFaces([], [])

    # 1. split parameters: other walls' endpoints lying on this wall + crossings
    cuts: list[set[float]] = [set() for _ in walls]
    endpoints = [p for w in walls for p in w]
    for i, w in enumerate(walls):
        for p in endpoints:
            t = _project_param(p, w)
            if t is not None and _EPS < t < 1.0 - _EPS and point_segment_distance(p, w) <= tol:
                cuts[i].add(round(t, 9))
    for i in range(len(walls)):
        for j in range(i + 1, len(walls)):
            hit = _segment_intersection(walls[i], walls[j])
            if hit is None:
                continue
            ti, tj = hit
            if _EPS < ti < 1.0 - _EPS:
                cuts[i].add(round(ti, 9))
            if _EPS < tj < 1.0 - _EPS:
                cuts[j].add(round(tj, 9))

    # 2. nodes and adjacency
    nodes = _NodeIndex(tol)
    adj: dict[int, set[int]] = {}
    for i, w in enumerate(walls):
        (x1, y1), (x2, y2) = w
        pts = [w[0]] + [
            (round(x1 + (x2 - x1) * t, 6), round(y1 + (y2 - y1) * t, 6)) for t in sorted(cuts[i])
        ] + [w[1]]
        for p, q in zip(pts, pts[1:]):
            if math.hypot(q[0] - p[0], q[1] - p[1]) <= _EPS:
                continue
            u = nodes.get(p)
            v = nodes.get(q)
            if u == v:
                continue
            adj.setdefault(u, set()).add(v)
            adj.setdefault(v, set()).add(u)
    if not adj:
        return PlanarFaces([], [])

    # 3. half-edge traversal
    node_pts = {i: p for i, p in enumerate(nodes.pts)}
    visited: set[tuple[int, int]] = set()
    interior: list[list[Point]] = []
    outer: list[list[Point]] = []
    min_area = max(tol * tol * 4.0, 1e-12)
    guard_max = 4 * sum(len(v) for v in adj.values()) + 8
    for u in sorted(adj):
        for v in sorted(adj[u]):
            if (u, v) in visited:
                continue
            start = (u, v)
            cur = start
            cyc: list[int] = []
            guard = 0
            while True:
                cyc.append(cur[0])
                visited.add(cur)
                nxt = _next_half_edge(cur, adj, node_pts)
                guard += 1
                if nxt == start or guard > guard_max:
                    break
                cur = nxt
            poly = _clean_cycle([node_pts[n] for n in cyc])
            if len(poly) < 3:
                continue
            area = _signed_area(poly)
            if area > min_area:
                interior.append(poly)
            elif area < -min_area:
                outer.append(poly)
    return PlanarFaces(interior, outer)


def close_rooms(walls: Sequence[Segment], tol: float) -> list[list[Point]]:
    """Minimal cycles of the wall-centreline graph, as room polygons.

    Thin wrapper over :func:`planar_faces`: returns the bounded (interior)
    faces only, each a list of ``(x, y)`` vertices.
    """
    return planar_faces(walls, tol).interior


__all__ = [
    "Point",
    "Segment",
    "PairCandidate",
    "PlanarFaces",
    "seg_length",
    "seg_midpoint",
    "seg_angle_deg",
    "point_segment_distance",
    "segments_bbox",
    "polygon_area",
    "point_in_polygon",
    "snap_axis",
    "merge_collinear",
    "pair_parallel",
    "planar_faces",
    "close_rooms",
]