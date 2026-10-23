"""Karmi — raster/scan drawings -> line segments (deterministic; no AI).

This is the priority-2/3 path of ``docs/architecture.md`` ("Ingestion
strategy"): a floor-plan image — a scan of a naksa, a phone photo of a
drawing, or a raster PDF page — is turned into straight line segments that the
same downstream wall / opening / room logic can consume.

    python -m core.raster <image-or-pdf> [--dpi 200] [--json out.json]

Pipeline::

    load_gray -> binarize -> deskew -> extract_segments -> estimate_scale
              -> to_scene_input

Everything here is deterministic numpy / Pillow / pymupdf: no machine
learning, no model calls, no network.  The module never invents geometry:
when the pixel evidence is weak (noisy photo, blank page, no scale reference)
it returns fewer segments, lower confidences and explicit warnings.

Coordinate conventions
----------------------
* Pixels, y grows downward — the same handedness as the PDF path (which works
  in PDF points, y down).
* A segment is ``((x1, y1), (x2, y2))`` — the exact tuple convention of
  ``core.ingest.IngestedDrawing.segments``, so the raster and vector paths
  share every downstream helper (``core.geometry``, the wall / opening / room
  logic of ``core.model``).  :func:`to_scene_input` emits that shape.
* ``Segment.angle_deg`` is in degrees, normalised to [0, 180), matching
  ``core.geometry.seg_angle_deg``.

Confidence story (honest by construction)
-----------------------------------------
* Every extracted element carries ``source="raster_geometry"`` and a
  confidence that reflects the evidence.
* :func:`extract_segments` grades each segment from *geometry only* — how
  line-like it is (length/thickness aspect) and how long it is — capped at
  0.70: a clean vector-rendered raster can justify about that much, and no
  more.
* :func:`extract_plan` multiplies those by an image-quality factor derived
  from measurable image properties (contrast, background evenness, speckle
  density), so a photo of a drawing lands around 0.2–0.3 and a noisy
  input lower still.  Confidence is never raised above what the pixels
  support.
* :func:`estimate_scale` never guesses: it returns ``None`` unless a scale bar
  is actually detected *and* calibrated by the caller (``bar_metres`` /
  ``metres_per_px``).

What this can and cannot do
---------------------------
Can: recover near-axis straight lines (walls, dimension lines, north-arrow
shafts, long jambs) from an image of a drawing, with honest confidences, and
degrade gracefully on noise/blank/rotated input.  Cannot: recover curved
lines, arbitrary-angle lines (beyond ``angle_tol_deg``), short strokes, or a
metric scale — see ``docs/RASTER.md`` for the full list.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pymupdf
from PIL import Image, ImageOps

from core import geometry as geo
from core.ingest import IngestError

# --------------------------------------------------------------------------- #
# constants
# --------------------------------------------------------------------------- #
DEFAULT_RENDER_DPI = 200

#: run-length analysis defaults (pixels)
MIN_LEN_PX = 25.0      # shortest segment kept — 25 px ≈ 0.22 m at 200 dpi/1:100
MAX_GAP_PX = 3.0       # runs closer than this are joined (same row, same band)
ANGLE_TOL_DEG = 3.0    # a band further than this from an axis is not a segment
MAX_DESKEW_DEG = 8.0

#: confidence model — a clean vector-rendered raster can justify ~0.70, never more
MAX_SEGMENT_CONFIDENCE = 0.70
MIN_QUALITY_FACTOR = 0.35
BLOB_ASPECT_MIN = 2.0  # length/thickness below this = a blob, not a line

#: image-quality thresholds (all on the [0, 1] grey scale)
LOW_CONTRAST = 0.35    # background mean minus ink mean
BG_STD_MAX = 0.10      # background spread above this = not a flat scan
BG_MEAN_MIN = 0.80     # background darker than this = not a flat scan
SPECKLE_WARN = 0.15    # share of isolated ink pixels above this = noisy
CLASS_SEP_MIN = 2.5    # ink/background separation, in units of the class spreads
DEGRADED_QUANTILE = 0.02   # keep only the darkest 2% of pixels when binarization fails
DEGRADED_MIN_LEN_FACTOR = 3.0  # ...and only segments this many times min_len_px
DEGRADED_MIN_KEPT = 1e-4   # sanity floor for the tightened mask
DEGRADED_QUALITY = 0.60

#: CAD convention used only to size heuristic windows when no scale exists
#: (mirrors core.model.CAD_M_PER_PT; never reported as a scale claim)
CAD_M_PER_PT = 0.025


# --------------------------------------------------------------------------- #
# data
# --------------------------------------------------------------------------- #
@dataclass
class Segment:
    """One straight line segment recovered from the raster, in PIXELS.

    ``angle_deg`` is degrees in [0, 180) (same convention as
    ``core.geometry.seg_angle_deg``); ``thickness_px`` is the mean
    perpendicular ink width; ``confidence`` reflects the pixel evidence only.
    """

    start: tuple[float, float]
    end: tuple[float, float]
    angle_deg: float
    length_px: float
    thickness_px: float
    confidence: float
    evidence: str = ""

    @property
    def as_tuple(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """The ``core.ingest`` tuple convention: ``((x1, y1), (x2, y2))``."""
        return (self.start, self.end)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": [round(self.start[0], 2), round(self.start[1], 2)],
            "end": [round(self.end[0], 2), round(self.end[1], 2)],
            "angle_deg": round(self.angle_deg, 3),
            "length_px": round(self.length_px, 2),
            "thickness_px": round(self.thickness_px, 2),
            "confidence": self.confidence,
            "provenance": {
                "source": "raster_geometry",
                "confidence": self.confidence,
                "evidence": self.evidence,
            },
        }


# --------------------------------------------------------------------------- #
# 1. load
# --------------------------------------------------------------------------- #
def load_gray(path: str | Path, *, dpi: int = DEFAULT_RENDER_DPI, page: int = 0) -> np.ndarray:
    """Load *path* as a float grayscale array in [0, 1] (0 = black).

    * PDFs are rendered with pymupdf at ``dpi`` (``page`` selects the page).
    * Image files are read with Pillow and the EXIF orientation tag is
      honoured (``ImageOps.exif_transpose``), so a phone photo that is stored
      sideways loads upright.

    Raises :class:`core.ingest.IngestError` with a readable message on any
    unreadable input — never a raw library traceback.
    """
    p = Path(path)
    if not p.exists():
        raise IngestError(f"Image file not found: {p}")

    if p.suffix.lower() == ".pdf":
        try:
            doc = pymupdf.open(str(p))
        except Exception:
            raise IngestError(
                f"Could not open '{p.name}': the file is not a readable PDF."
            ) from None
        try:
            if doc.needs_pass:
                raise IngestError(
                    f"'{p.name}' is password-protected (encrypted PDF). "
                    "Please supply an unlocked copy."
                )
            if doc.page_count == 0:
                raise IngestError(f"'{p.name}' contains no pages.")
            idx = max(0, min(int(page), doc.page_count - 1))
            pix = doc[idx].get_pixmap(dpi=int(dpi), colorspace=pymupdf.csGRAY)
            arr = np.frombuffer(pix.samples, dtype=np.uint8)
            arr = arr.reshape(pix.height, pix.width).astype(np.float32) / 255.0
            return arr
        except IngestError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise IngestError(
                f"Could not render '{p.name}' at {dpi} dpi "
                f"({type(exc).__name__} while rendering)."
            ) from None
        finally:
            doc.close()

    try:
        with Image.open(str(p)) as im:
            im = ImageOps.exif_transpose(im)  # honour EXIF orientation
            arr = np.asarray(im.convert("L"), dtype=np.float32) / 255.0
            return np.ascontiguousarray(arr)
    except Exception:  # noqa: BLE001
        raise IngestError(
            f"Could not read image '{p.name}': not a readable image file."
        ) from None


# --------------------------------------------------------------------------- #
# 1b. blueprint polarity & tolerance calibration
# --------------------------------------------------------------------------- #
def detect_blueprint_polarity(gray: np.ndarray) -> tuple[bool, str]:
    """Detect whether an image has inverted polarity (dark background with bright lines).

    Ammonia blueprints ('नीलो ब्लूप्रिन्ट') and photo negatives commonly feature
    dark blue, purple, or dark grey backgrounds with light line drawings.
    Returns (is_inverted, reason).
    """
    g = np.asarray(gray, dtype=np.float64)
    if g.size == 0:
        return False, "Empty image"
    lo, hi = float(np.nanmin(g)), float(np.nanmax(g))
    if hi - lo < 1e-4:
        return False, "Uniform image (blank)"

    med = float(np.median(g))
    dark_frac = float((g < (lo + 0.45 * (hi - lo))).mean())
    bright_frac = float((g > (lo + 0.70 * (hi - lo))).mean())

    if (med < 0.40 or dark_frac > 0.60) and bright_frac < 0.35 and bright_frac > 0.001:
        return True, "Ammonia blueprint / inverted tone detected (dark background with bright lines)"
    return False, "Standard drawing with white background and dark ink"


def calibrate_tolerances(
    dpi: int = DEFAULT_RENDER_DPI,
    base_scale_m_per_unit: float | None = None,
) -> dict[str, float]:
    """Calibrate run-length segment extraction tolerances according to rendering DPI.

    Ensures that physical feature thresholds (e.g., minimum detectable wall ~0.20m,
    collinear gap bridge ~2.5cm) scale proportionally with image resolution.
    """
    factor = float(dpi) / float(DEFAULT_RENDER_DPI)
    min_len = max(10.0, round(MIN_LEN_PX * factor, 1))
    max_gap = max(1.5, round(MAX_GAP_PX * factor, 1))
    return {
        "min_len_px": min_len,
        "max_gap_px": max_gap,
        "angle_tol_deg": ANGLE_TOL_DEG,
    }


def blueprint_quality_score(stats: dict[str, Any]) -> dict[str, Any]:
    """Grade image quality for floor plan extraction and generate Nepali diagnostics.

    Evaluates contrast, background uniformity, speckle noise, and class separation.
    Returns structured score, letter grade ('A', 'B', 'C', 'D'), and homeowner advice.
    """
    if stats.get("blank", False):
        return {
            "overall_score": 0,
            "grade": "D",
            "blueprint_type": "blank",
            "is_acceptable_for_diff": False,
            "diagnostic_np": "नक्सा खाली वा पूर्ण रूपमा अस्पष्ट छ — कृपया सही फाइल अपलोड गर्नुहोस्।",
        }

    contrast = float(stats.get("contrast", 0.0))
    bg_std = float(stats.get("bg_std", 0.10))
    speckle = float(stats.get("speckle", 0.0))
    degraded = bool(stats.get("degraded", False))

    contrast_pts = min(40.0, max(0.0, (contrast / 0.70) * 40.0))
    bg_pts = min(30.0, max(0.0, 30.0 - (bg_std / 0.15) * 30.0))
    speckle_pts = min(30.0, max(0.0, 30.0 - (speckle / 0.20) * 30.0))

    score = contrast_pts + bg_pts + speckle_pts
    if degraded:
        score = max(10.0, score - 25.0)

    score_val = int(round(score))

    if score_val >= 80:
        grade = "A"
        diag_np = "नक्साको गुणस्तर राम्रो र स्पष्ट छ — तुलनाको लागि उपयुक्त।"
        bp_type = "clean_scan"
    elif score_val >= 65:
        grade = "B"
        diag_np = "नक्सा सामान्य छ, केही मसिना रेखाहरू छुट्न सक्छन्।"
        bp_type = "standard_scan"
    elif score_val >= 50:
        grade = "C"
        diag_np = "नक्सामा छायाँ वा दाग देखिन्छ — ध्यानपूर्वक जाँच्नुहोस्।"
        bp_type = "phone_photo"
    else:
        grade = "D"
        diag_np = "नक्सा कमजोर वा अस्पष्ट छ — पुनः स्क्यान गर्न सिफारिस गरिन्छ।"
        bp_type = "noisy_degraded"

    is_acceptable = grade in ("A", "B") and not degraded

    return {
        "overall_score": score_val,
        "grade": grade,
        "blueprint_type": bp_type,
        "is_acceptable_for_diff": is_acceptable,
        "diagnostic_np": diag_np,
    }


# --------------------------------------------------------------------------- #
# 2. binarize
# --------------------------------------------------------------------------- #
def binarize(gray: np.ndarray, method: str = "otsu") -> np.ndarray:
    """Threshold *gray*; returns a bool array where dark ink is True.

    * ``method="otsu"``: global Otsu threshold, implemented in numpy
      (no OpenCV).
    * ``method="adaptive"``: local box-mean minus a small constant (integral
      image) — useful for unevenly lit photos where a global threshold fails.

    Degenerate inputs are handled without exceptions: a uniform image yields
    an empty mask (there is no ink to find).
    """
    g = np.asarray(gray, dtype=np.float64)
    if g.ndim != 2:
        raise ValueError("gray must be a 2-D array")
    if method == "otsu":
        thr = _otsu_threshold(g)
        return g < thr
    if method == "adaptive":
        return g < (_box_mean(g, 41) - 0.03)
    raise ValueError(f"unknown binarize method {method!r} (use 'otsu' or 'adaptive')")


def _otsu_threshold(g: np.ndarray) -> float:
    """Otsu's threshold (numpy only). Returns a value in the data's own units.

    For a uniform image the "threshold" is the single value, so the resulting
    mask (``g < thr``) is empty — which is the honest answer for a blank page.
    """
    lo, hi = float(np.nanmin(g)), float(np.nanmax(g))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi - lo < 1e-9:
        return lo
    hist, edges = np.histogram(g, bins=256, range=(lo, hi))
    hist = hist.astype(np.float64)
    centers = (edges[:-1] + edges[1:]) / 2.0
    total = float(hist.sum())
    w0 = np.cumsum(hist)
    w1 = total - w0
    csum = np.cumsum(hist * centers)
    sum_all = float(csum[-1])
    valid = (w0 > 0) & (w1 > 0)
    mu0 = np.where(valid, csum / np.maximum(w0, 1e-12), 0.0)
    mu1 = np.where(valid, (sum_all - csum) / np.maximum(w1, 1e-12), 0.0)
    between = np.where(valid, w0 * w1 * (mu0 - mu1) ** 2, 0.0)
    t = int(np.argmax(between))
    return float((edges[t] + edges[t + 1]) / 2.0)


def _box_mean(g: np.ndarray, win: int) -> np.ndarray:
    """Local box mean via an integral image (edge-padded)."""
    win = max(3, int(win) | 1)
    pad = win // 2
    p = np.pad(g, pad, mode="edge")
    ii = np.cumsum(np.cumsum(p, axis=0), axis=1)
    ii = np.pad(ii, ((1, 0), (1, 0)), mode="constant")
    h, w = g.shape
    ys = np.arange(h) + win
    xs = np.arange(w) + win
    s = (
        ii[np.ix_(ys, xs)]
        - ii[np.ix_(ys - win, xs)]
        - ii[np.ix_(ys, xs - win)]
        + ii[np.ix_(ys - win, xs - win)]
    )
    return s / float(win * win)


# --------------------------------------------------------------------------- #
# 3. deskew
# --------------------------------------------------------------------------- #
def deskew(binary: np.ndarray, max_angle_deg: float = MAX_DESKEW_DEG) -> tuple[np.ndarray, float]:
    """Estimate the dominant line angle and rotate the image back to axis.

    Method: projection-profile variance.  For each candidate angle the
    (downsampled) ink mask is rotated and scored by
    ``var(row sums) + var(col sums)`` — both are maximal when lines are
    exactly horizontal/vertical.  Coarse 0.5° sweep over ±``max_angle_deg``,
    then a 0.1° refinement around the winner.

    Returns ``(corrected_binary, applied_angle_deg)``.  The angle follows the
    PIL convention: positive = counter-clockwise rotation was applied.  A
    flat/blank/unstructured image returns ``(input, 0.0)`` unchanged — no
    angle is invented when there is no evidence for one.
    """
    m = np.asarray(binary, dtype=bool)
    if m.size == 0 or not m.any():
        return m.copy(), 0.0

    small = _downsample_float(m, 900)
    if float(small.sum()) < 8.0:  # fewer than ~8 px of ink: nothing to align
        return m.copy(), 0.0

    pad = int(math.ceil(max(small.shape) * math.sin(math.radians(max_angle_deg)))) + 4
    padded = np.pad(small, pad, constant_values=0.0)
    img = Image.fromarray((padded * 255.0).astype(np.uint8), "L")

    coarse = np.arange(-max_angle_deg, max_angle_deg + 1e-9, 0.5)
    scores = np.array([_profile_score(img, float(a)) for a in coarse])
    if float(scores.max()) <= 0.0 or float(scores.max()) < 1.5 * float(np.median(scores)):
        return m.copy(), 0.0  # no dominant direction — do not guess
    best = float(coarse[int(np.argmax(scores))])

    fine = np.arange(best - 0.5, best + 0.5 + 1e-9, 0.1)
    fscores = np.array([_profile_score(img, float(a)) for a in fine])
    best = float(fine[int(np.argmax(fscores))])

    if abs(best) < 0.05:
        return m.copy(), 0.0
    return _rotate_binary(m, best, expand=True), round(best, 2)


def _profile_score(img: Image.Image, angle_deg: float) -> float:
    rot = np.asarray(
        img.rotate(angle_deg, resample=Image.Resampling.BILINEAR, expand=False, fillcolor=0),
        dtype=np.float64,
    ) / 255.0
    return float(rot.sum(axis=1).var() + rot.sum(axis=0).var())


def _downsample_float(mask: np.ndarray, max_dim: int) -> np.ndarray:
    h, w = mask.shape
    if max(h, w) <= max_dim:
        return mask.astype(np.float64)
    s = max_dim / float(max(h, w))
    nw, nh = max(8, int(round(w * s))), max(8, int(round(h * s)))
    im = Image.fromarray((mask.astype(np.uint8) * 255), "L").resize(
        (nw, nh), Image.Resampling.BOX
    )
    return np.asarray(im, dtype=np.float64) / 255.0


def _rotate_binary(mask: np.ndarray, angle_deg: float, *, expand: bool) -> np.ndarray:
    im = Image.fromarray((mask.astype(np.uint8) * 255), "L")
    rot = im.rotate(angle_deg, resample=Image.Resampling.BILINEAR, expand=expand, fillcolor=0)
    return np.asarray(rot) > 127


# --------------------------------------------------------------------------- #
# 4. segments
# --------------------------------------------------------------------------- #
def extract_segments(
    binary: np.ndarray,
    *,
    min_len_px: float = MIN_LEN_PX,
    max_gap_px: float = MAX_GAP_PX,
    angle_tol_deg: float = ANGLE_TOL_DEG,
) -> list[Segment]:
    """Near-axis straight segments from a binarized drawing (pixels).

    Algorithm (row/column run-length analysis — see docs/RASTER.md):

    1.  For every row, collect runs of ink; join runs separated by ≤
        ``max_gap_px`` (a broken/dashed stroke of the same line).
    2.  Keep runs at least ``min_len_px`` long.  A near-horizontal line leaves
        one long run in every row it crosses; a vertical stroke leaves short
        runs and is invisible to this pass (it is found by the column pass,
        which is the same analysis on the transposed mask).
    3.  Band runs across adjacent rows whose x-intervals touch within
        ``max_gap_px`` (this follows slightly tilted lines as a staircase).
    4.  Per band: fit the tilt from the run-centre track (a band that is one
        row tall carries no tilt evidence and is reported as axis-aligned),
        drop it if the tilt exceeds ``angle_tol_deg``, project the extreme
        points to get the endpoints, and take ``thickness = ink / length``.
        Bands that are not at least ``BLOB_ASPECT_MIN`` times longer than they
        are thick (square blobs, text blocks, hatching) are dropped.
    5.  Merge collinear segments across gaps ≤ ``max_gap_px`` with a
        perpendicular offset tolerance scaled to their thickness.

    Confidence is graded from geometry only (aspect ratio and length), in
    [0.30, 0.70]; :func:`extract_plan` additionally scales it by the measured
    image quality.  The function is deterministic and never fabricates a
    segment: empty input -> empty list.
    """
    m = np.asarray(binary, dtype=bool)
    if m.size == 0 or m.ndim != 2 or not m.any():
        return []
    horiz = _extract_axis(m, min_len_px, max_gap_px, angle_tol_deg, vertical=False)
    vert = _extract_axis(m.T, min_len_px, max_gap_px, angle_tol_deg, vertical=True)
    segs = _merge_collinear(horiz + vert, max_gap_px, angle_tol_deg)
    segs.sort(
        key=lambda s: (
            round((s.start[1] + s.end[1]) / 2.0, 3),
            round((s.start[0] + s.end[0]) / 2.0, 3),
            s.angle_deg,
        )
    )
    return segs


def _extract_axis(
    mask: np.ndarray,
    min_len_px: float,
    max_gap_px: float,
    angle_tol_deg: float,
    *,
    vertical: bool,
) -> list[Segment]:
    """All bands of long runs in *mask* (which is transposed for vertical)."""
    runs = _row_runs(mask, min_len_px, max_gap_px)
    if runs is None:
        return []
    rows, x0s, x1s = runs
    out: list[Segment] = []
    for idx in _band_runs(rows, x0s, x1s, max_gap_px):
        seg = _component_to_segment(
            rows[idx], x0s[idx], x1s[idx], min_len_px, angle_tol_deg
        )
        if seg is None:
            continue
        if vertical:
            s = (seg.start[1], seg.start[0])
            e = (seg.end[1], seg.end[0])
            seg = Segment(
                start=s,
                end=e,
                angle_deg=geo.seg_angle_deg((s, e)),
                length_px=seg.length_px,
                thickness_px=seg.thickness_px,
                confidence=seg.confidence,
                evidence=seg.evidence + " (column runs)",
            )
        out.append(seg)
    return out


def _row_runs(
    mask: np.ndarray, min_len_px: float, max_gap_px: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """Runs of ink per row, gaps ≤ max_gap_px joined, length ≥ min_len_px kept.

    Returns ``(rows, x0, x1_exclusive)`` as int64 arrays, or None when nothing
    qualifies.
    """
    h, w = mask.shape
    padded = np.zeros((h, w + 2), dtype=np.int8)
    padded[:, 1:-1] = mask
    d = np.diff(padded, axis=1)
    starts = np.argwhere(d == 1)
    ends = np.argwhere(d == -1)
    if len(starts) == 0:
        return None
    rows_all = starts[:, 0]
    x0_all = starts[:, 1] - 1
    x1_all = ends[:, 1] - 1  # exclusive

    out_rows: list[int] = []
    out_x0: list[int] = []
    out_x1: list[int] = []
    uniq, idx = np.unique(rows_all, return_index=True)
    bounds = list(int(i) for i in idx) + [len(rows_all)]
    for k, r in enumerate(uniq):
        a = x0_all[bounds[k] : bounds[k + 1]]
        b = x1_all[bounds[k] : bounds[k + 1]]
        cur0, cur1 = int(a[0]), int(b[0])
        for j in range(1, len(a)):
            if int(a[j]) - cur1 <= max_gap_px:
                if int(b[j]) > cur1:
                    cur1 = int(b[j])
            else:
                if cur1 - cur0 >= min_len_px:
                    out_rows.append(int(r))
                    out_x0.append(cur0)
                    out_x1.append(cur1)
                cur0, cur1 = int(a[j]), int(b[j])
        if cur1 - cur0 >= min_len_px:
            out_rows.append(int(r))
            out_x0.append(cur0)
            out_x1.append(cur1)
    if not out_rows:
        return None
    return (
        np.array(out_rows, dtype=np.int64),
        np.array(out_x0, dtype=np.int64),
        np.array(out_x1, dtype=np.int64),
    )


def _band_runs(
    rows: np.ndarray, x0s: np.ndarray, x1s: np.ndarray, max_gap_px: float
) -> list[np.ndarray]:
    """Union runs of adjacent rows whose intervals touch within max_gap_px."""
    n = len(rows)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    uniq, idx = np.unique(rows, return_index=True)
    bounds = list(int(i) for i in idx) + [n]
    for k in range(len(uniq) - 1):
        if uniq[k + 1] != uniq[k] + 1:
            continue
        r0, r1 = bounds[k], bounds[k + 1]
        n0, n1 = bounds[k + 1], bounds[k + 2]
        a_x0, a_x1 = x0s[r0:r1], x1s[r0:r1]
        b_x0, b_x1 = x0s[n0:n1], x1s[n0:n1]
        for i in range(r1 - r0):
            klo = int(np.searchsorted(b_x1, a_x0[i] - max_gap_px, side="left"))
            khi = int(np.searchsorted(b_x0, a_x1[i] + max_gap_px, side="right"))
            for j in range(klo, khi):
                ra, rb = find(r0 + i), find(n0 + j)
                if ra != rb:
                    parent[rb] = ra

    comps: dict[int, list[int]] = {}
    for i in range(n):
        comps.setdefault(find(i), []).append(i)
    return list(comps.values())


def _component_to_segment(
    rows: np.ndarray,
    x0s: np.ndarray,
    x1s: np.ndarray,
    min_len_px: float,
    angle_tol_deg: float,
) -> Segment | None:
    """One run band -> one Segment (in the frame where it should be horizontal)."""
    y0, y1 = int(rows.min()), int(rows.max())
    n_rows = y1 - y0 + 1
    xmin = int(x0s.min())
    xmax = int((x1s - 1).max())
    span = xmax - xmin + 1
    ink = float((x1s - x0s).sum())
    if span < min_len_px:
        return None

    # ---- tilt: run-centre track; a straight band has shift ≈ 0 ------------- #
    theta = 0.0
    if n_rows >= 3:
        ys = rows.astype(np.float64)
        xs = (x0s + x1s - 1) / 2.0
        m = float(np.polyfit(ys, xs, 1)[0])  # dx per dy
        run_len = float(np.median(x1s - x0s))
        shift = abs(m) * (n_rows - 1)
        if shift > 0.5 * run_len and abs(m) > 1e-9:
            theta = math.degrees(math.atan2(1.0, m))
            if theta > 90.0:
                theta -= 180.0
            if theta < -90.0:
                theta += 180.0
    if abs(theta) > angle_tol_deg:
        return None  # genuinely slanted — out of scope, do not snap it

    # ---- endpoints / length / thickness ------------------------------------ #
    if n_rows <= 1 or abs(theta) < 1e-9:
        y_mid = float(rows.mean())
        start, end = (float(xmin), y_mid), (float(xmax), y_mid)
        length = float(span)
    else:
        cx = math.cos(math.radians(theta))
        cy = math.sin(math.radians(theta))
        px = np.concatenate([x0s, x1s - 1, (x0s + x1s - 1) / 2.0]).astype(np.float64)
        py = np.concatenate([rows, rows, rows]).astype(np.float64)
        proj = px * cx + py * cy
        i0, i1 = int(np.argmin(proj)), int(np.argmax(proj))
        start = (float(px[i0]), float(py[i0]))
        end = (float(px[i1]), float(py[i1]))
        length = float(proj[i1] - proj[i0])

    if length < min_len_px:
        return None
    thickness = ink / max(length, 1e-9)
    if length < BLOB_ASPECT_MIN * thickness:
        return None  # square-ish blob (junction, text block), not a line
    return Segment(
        start=start,
        end=end,
        angle_deg=geo.seg_angle_deg((start, end)),
        length_px=round(length, 2),
        thickness_px=round(thickness, 2),
        confidence=_segment_confidence(length, thickness),
        evidence=(
            f"run-length band: {n_rows} px across, {int(ink)} ink px, "
            f"fitted tilt {theta:+.2f}°"
        ),
    )


def _segment_confidence(length: float, thickness: float) -> float:
    """Geometry-only confidence in [0.30, 0.70] (clean-input assumption)."""
    aspect = length / max(thickness, 1e-9)
    conf = (
        0.30
        + 0.25 * min(1.0, aspect / 10.0)
        + 0.15 * min(1.0, length / 400.0)
    )
    return round(min(conf, MAX_SEGMENT_CONFIDENCE), 2)


def _axis_of(angle_deg: float, angle_tol_deg: float) -> int | None:
    """0 = horizontal-ish, 1 = vertical-ish, None = off-axis."""
    if angle_deg <= angle_tol_deg or angle_deg >= 180.0 - angle_tol_deg:
        return 0
    if abs(angle_deg - 90.0) <= angle_tol_deg:
        return 1
    return None


def _merge_collinear(
    segments: Sequence[Segment], max_gap_px: float, angle_tol_deg: float
) -> list[Segment]:
    """Join collinear fragments separated by ≤ max_gap_px (iterate to fixpoint)."""
    segs = list(segments)
    changed = True
    while changed:
        changed = False
        out: list[Segment] = []
        used = [False] * len(segs)
        for i, a in enumerate(segs):
            if used[i]:
                continue
            used[i] = True
            for j in range(i + 1, len(segs)):
                if used[j]:
                    continue
                merged = _try_merge(a, segs[j], max_gap_px, angle_tol_deg)
                if merged is not None:
                    a = merged
                    used[j] = True
                    changed = True
            out.append(a)
        segs = out
    return segs


def _try_merge(
    a: Segment, b: Segment, max_gap_px: float, angle_tol_deg: float
) -> Segment | None:
    axa = _axis_of(a.angle_deg, angle_tol_deg)
    axb = _axis_of(b.angle_deg, angle_tol_deg)
    if axa is None or axa != axb:
        return None
    perp_tol = max(2.5, 0.75 * max(a.thickness_px, b.thickness_px))
    ink = a.length_px * a.thickness_px + b.length_px * b.thickness_px
    if axa == 0:
        pa = (a.start[1] + a.end[1]) / 2.0
        pb = (b.start[1] + b.end[1]) / 2.0
        if abs(pa - pb) > perp_tol:
            return None
        ra = sorted((a.start[0], a.end[0]))
        rb = sorted((b.start[0], b.end[0]))
        gap = max(rb[0] - ra[1], ra[0] - rb[1], 0.0)
        if gap > max_gap_px:
            return None
        lo, hi = min(ra[0], rb[0]), max(ra[1], rb[1])
        y = (pa * a.length_px + pb * b.length_px) / max(a.length_px + b.length_px, 1e-9)
        start, end = (float(lo), float(y)), (float(hi), float(y))
    else:
        pa = (a.start[0] + a.end[0]) / 2.0
        pb = (b.start[0] + b.end[0]) / 2.0
        if abs(pa - pb) > perp_tol:
            return None
        ra = sorted((a.start[1], a.end[1]))
        rb = sorted((b.start[1], b.end[1]))
        gap = max(rb[0] - ra[1], ra[0] - rb[1], 0.0)
        if gap > max_gap_px:
            return None
        lo, hi = min(ra[0], rb[0]), max(ra[1], rb[1])
        x = (pa * a.length_px + pb * b.length_px) / max(a.length_px + b.length_px, 1e-9)
        start, end = (float(x), float(lo)), (float(x), float(hi))
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    thickness = ink / max(length, 1e-9)
    if length < BLOB_ASPECT_MIN * thickness:
        return None
    return Segment(
        start=start,
        end=end,
        angle_deg=geo.seg_angle_deg((start, end)),
        length_px=round(length, 2),
        thickness_px=round(thickness, 2),
        confidence=_segment_confidence(length, thickness),
        evidence="merged collinear run fragments",
    )


# --------------------------------------------------------------------------- #
# 5. scale
# --------------------------------------------------------------------------- #
def estimate_scale(
    binary: np.ndarray,
    segments: Sequence[Segment],
    *,
    bar_px: float | None = None,
    bar_metres: float | None = None,
) -> tuple[float | None, str]:
    """(metres_per_pixel, reason) — only with real evidence, else (None, why).

    Evidence accepted:

    * a **detected scale bar** whose real length is supplied by the caller
      (``bar_metres``): m/px = bar_metres / (measured bar length in px);
    * a fully **user-supplied calibration** (``bar_px`` + ``bar_metres``),
      i.e. "this known feature is N px long and L metres in reality" —
      the architecture's "user supplies one known dimension" step.

    A bar-like feature is detected as a thick segment with perpendicular ticks
    near both ends.  Without a calibration the function still returns ``None``
    and says that the bar was found but its label cannot be read by this
    deterministic path.  There is deliberately no "SCALE 1:100 + DPI" route:
    a raster's pixels have no trustworthy physical size, so that chain would
    be a guess dressed as evidence (see docs/RASTER.md).
    """
    if bar_px is not None and bar_metres is not None:
        if bar_px > 0 and bar_metres > 0:
            bar = _find_scale_bar(segments)
            note = "" if bar is not None else " (no matching bar structure was detected in the image — value is user-supplied)"
            return (
                bar_metres / bar_px,
                f"user-supplied calibration: {bar_metres:g} m / {bar_px:g} px "
                f"= {bar_metres / bar_px:.6g} m/px{note}",
            )
        return None, "ignored invalid bar calibration (bar_px and bar_metres must be positive)"

    bar = _find_scale_bar(segments)
    if bar is None:
        return (
            None,
            "no scale-bar-like feature found and no calibration supplied — metres "
            "per pixel is unknown (pass metres_per_px, or bar_metres to calibrate a "
            "detected bar)",
        )
    if bar_metres is not None and bar_metres > 0:
        mpp = bar_metres / bar.length_px
        return (
            mpp,
            f"calibrated from the detected scale bar: {bar_metres:g} m / "
            f"{bar.length_px:.1f} px = {mpp:.6g} m/px",
        )
    return (
        None,
        f"a scale-bar-like feature was detected (bar {bar.length_px:.0f} px long, "
        f"{bar.thickness_px:.1f} px thick, with end ticks) but its real length "
        "cannot be read by this deterministic path — pass bar_metres (or "
        "metres_per_px) to calibrate",
    )


def _find_scale_bar(segments: Sequence[Segment]) -> Segment | None:
    """Longest thick segment with perpendicular end ticks on both ends."""
    cands = [
        s
        for s in segments
        if s.thickness_px >= 4.0 and 60.0 <= s.length_px <= 1500.0
    ]
    cands.sort(key=lambda s: (-s.length_px, s.start[1], s.start[0]))
    for bar in cands:
        if _has_tick(segments, bar, bar.start) and _has_tick(segments, bar, bar.end):
            return bar
    return None


def _has_tick(segments: Sequence[Segment], bar: Segment, point: tuple[float, float]) -> bool:
    if bar.length_px <= 0:
        return False
    dx = (bar.end[0] - bar.start[0]) / bar.length_px
    dy = (bar.end[1] - bar.start[1]) / bar.length_px
    for s in segments:
        if s is bar:
            continue
        sdx, sdy = s.end[0] - s.start[0], s.end[1] - s.start[1]
        sl = math.hypot(sdx, sdy)
        if sl <= 0:
            continue
        if abs(sdx * dx + sdy * dy) / sl > 0.35:
            continue  # not roughly perpendicular to the bar
        if not (1.2 * bar.thickness_px <= sl <= 8.0 * bar.thickness_px):
            continue
        if s.thickness_px < 0.5 * bar.thickness_px:
            continue
        mx = (s.start[0] + s.end[0]) / 2.0
        my = (s.start[1] + s.end[1]) / 2.0
        along = (mx - bar.start[0]) * dx + (my - bar.start[1]) * dy
        along_end = (point[0] - bar.start[0]) * dx + (point[1] - bar.start[1]) * dy
        if abs(along - along_end) > 0.25 * bar.length_px:
            continue
        lateral = abs(-(mx - bar.start[0]) * dy + (my - bar.start[1]) * dx)
        if lateral > 1.5 * bar.thickness_px:
            continue
        return True
    return False


# --------------------------------------------------------------------------- #
# 6. scene-input dict
# --------------------------------------------------------------------------- #
def to_scene_input(
    segments: Sequence[Segment],
    *,
    metres_per_px: float | None = None,
    north_deg: float | None = None,
) -> dict[str, Any]:
    """Plain dict for the orchestrator, in the shared segment convention.

    ``"segments"`` is a list of ``((x1, y1), (x2, y2))`` pairs **in pixels** —
    exactly ``core.ingest.IngestedDrawing.segments`` — so the raster path and
    the vector path can share all downstream code (``core.geometry``, the
    wall/opening/room logic).  ``"segment_details"`` carries the per-segment
    angle / length / thickness / confidence and its ``raster_geometry``
    provenance.  ``"scale_m_per_unit"`` is metres per PIXEL (unit = ``"px"``);
    ``meta["px_to_pt"]`` lets a caller convert the coordinates to
    PDF-point-equivalents with :func:`to_point_units`.
    """
    segs = [
        (
            (round(s.start[0], 2), round(s.start[1], 2)),
            (round(s.end[0], 2), round(s.end[1], 2)),
        )
        for s in segments
    ]
    details = [s.to_dict() for s in segments]
    warnings: list[str] = []
    if not segments:
        warnings.append(
            "No line segments were extracted from this image — nothing downstream "
            "can be built from it. Check the image (contrast, focus, crop)."
        )
    if metres_per_px is None:
        warnings.append(
            "No scale evidence: metres per pixel is unknown. Coordinates stay in "
            "pixels; unit-dependent numbers (wall thickness in metres, opening "
            "widths, areas) must be omitted downstream — never assumed."
        )
    confs = [s.confidence for s in segments]
    return {
        "segments": segs,
        "segment_details": details,
        "scale_m_per_unit": float(metres_per_px) if metres_per_px is not None else None,
        "units": "px",
        "north_deg": float(north_deg) % 360.0 if north_deg is not None else None,
        "warnings": warnings,
        "provenance": {
            "source": "raster_geometry",
            "confidence": round(float(np.median(confs)), 2) if confs else 0.0,
            "evidence": (
                f"deterministic run-length line extraction: {len(segments)} segment(s), "
                "median segment confidence"
            ),
        },
        "meta": {
            "n_segments": len(segments),
            "coordinate_frame": "image pixels (y down) — convert with px_to_pt for the PDF pipeline",
        },
    }


def to_point_units(scene_input: dict[str, Any], px_to_pt: float | None = None) -> dict[str, Any]:
    """Convert a :func:`to_scene_input` dict from pixels to PDF-point units.

    The vector pipeline (``core.model``) works in PDF points; a raster render
    at ``dpi`` relates the two by ``pt = px * 72/dpi``.  This helper returns a
    new dict with converted ``segments`` / ``segment_details`` /
    ``scale_m_per_unit`` (metres per pt) so the orchestrator can hand the
    raster segments to the same wall/opening/room code with no other change.
    """
    f = px_to_pt if px_to_pt is not None else scene_input.get("meta", {}).get("px_to_pt")
    if not f or f <= 0:
        raise ValueError("px_to_pt factor unavailable — pass it or use extract_plan() output")
    out = dict(scene_input)
    out["segments"] = [
        ((round(p[0] * f, 4), round(p[1] * f, 4)), (round(q[0] * f, 4), round(q[1] * f, 4)))
        for p, q in scene_input["segments"]
    ]
    details = []
    for d in scene_input.get("segment_details", []):
        d2 = dict(d)
        d2["start"] = [round(d["start"][0] * f, 4), round(d["start"][1] * f, 4)]
        d2["end"] = [round(d["end"][0] * f, 4), round(d["end"][1] * f, 4)]
        d2["length_pt"] = round(d["length_px"] * f, 4)
        d2["thickness_pt"] = round(d["thickness_px"] * f, 4)
        details.append(d2)
    out["segment_details"] = details
    if scene_input.get("scale_m_per_unit") is not None:
        out["scale_m_per_unit"] = float(scene_input["scale_m_per_unit"]) / f
    out["units"] = "pt"
    out["warnings"] = list(scene_input.get("warnings", [])) + [
        f"Coordinates converted px -> PDF points (x{f:.6g} = 72/dpi) so the raster "
        "path shares the vector pipeline's working units."
    ]
    return out


# --------------------------------------------------------------------------- #
# 7. one-call entry point
# --------------------------------------------------------------------------- #
def extract_plan(
    path: str | Path,
    *,
    dpi: int = DEFAULT_RENDER_DPI,
    page: int = 0,
    min_len_px: float = MIN_LEN_PX,
    max_gap_px: float = MAX_GAP_PX,
    angle_tol_deg: float = ANGLE_TOL_DEG,
    max_deskew_deg: float = MAX_DESKEW_DEG,
    binarize_method: str = "otsu",
    auto_invert: bool = True,
    metres_per_px: float | None = None,
    bar_px: float | None = None,
    bar_metres: float | None = None,
    north_deg: float | None = None,
) -> dict[str, Any]:
    """load -> binarize -> deskew -> extract -> scale -> scene-input dict.

    Returns the :func:`to_scene_input` dict plus processing warnings
    ("deskewed by N degrees", "no scale evidence found", "low contrast",
    "looks like a photo of a screen", ...) and a ``meta`` block with the
    diagnostics.  Never raises for weak input: a blank page returns zero
    segments and a clear warning.
    """
    warnings: list[str] = []
    gray = load_gray(path, dpi=dpi, page=page)

    polarity_inverted = False
    if auto_invert:
        is_inv, pol_reason = detect_blueprint_polarity(gray)
        if is_inv:
            gray = 1.0 - gray
            polarity_inverted = True
            warnings.append(
                f"Detected ammonia blueprint or inverted drawing ({pol_reason}) — "
                "automatically calibrated and inverted tone for line extraction."
            )

    binary = binarize(gray, method=binarize_method)
    threshold: float | None = None
    degraded = False

    # ---- binarization sanity: are the ink/background classes separated? ----- #
    # Heavy noise (or a very faint drawing) makes the two grey-level classes
    # overlap; Otsu then cuts through the background tail and noise streaks
    # start to look like lines.  When that is measured, the threshold is
    # tightened to the darkest DEGRADED_QUANTILE of pixels (the line cores) and
    # only strong segments are kept — the mask can only shrink, so this can
    # never invent ink.
    if binarize_method == "otsu":
        threshold = _otsu_threshold(gray.astype(np.float64))
        sep_ok, sep, spread = _class_separation(gray, binary)
        ink_otsu = float(binary.mean())
        if not sep_ok and 0.0 < ink_otsu <= 0.5:
            degraded = True
            q_thr = float(np.quantile(gray, DEGRADED_QUANTILE))
            strict_mask = gray < q_thr
            if DEGRADED_MIN_KEPT <= float(strict_mask.mean()) < ink_otsu:
                binary = strict_mask
                threshold = q_thr
                warnings.append(
                    f"The ink and background classes are not separated (contrast "
                    f"{sep:.2f} vs class spread {spread:.2f}): this image is too "
                    "noisy or too faint for a global threshold. The threshold was "
                    f"tightened to keep only the darkest {DEGRADED_QUANTILE:.0%} of "
                    f"pixels (ink {ink_otsu:.1%} → {float(strict_mask.mean()):.2%}) "
                    f"and only segments at least {DEGRADED_MIN_LEN_FACTOR:.0f}× the "
                    "minimum length are kept — treat the result as a partial, "
                    "low-confidence subset."
                )
            else:
                warnings.append(
                    f"The ink and background classes are not separated (contrast "
                    f"{sep:.2f} vs class spread {spread:.2f}) — the binarization is "
                    "unreliable on this image; the extraction result should not be trusted."
                )

    else:
        sep_ok, sep, spread = _class_separation(gray, binary)
        if not sep_ok and 0.0 < float(binary.mean()) <= 0.5:
            degraded = True
            warnings.append(
                f"The ink and background classes are not separated (contrast "
                f"{sep:.2f} vs class spread {spread:.2f}) — the '{binarize_method}' "
                "binarization is unreliable on this image; the extraction result "
                "should not be trusted (adaptive thresholding is for uneven lighting "
                "with clean ink, not for heavy noise)."
            )

    stats = _image_stats(gray, binary, threshold=threshold)
    stats["degraded"] = degraded

    ink_frac = float(binary.mean())
    if stats["blank"]:
        warnings.append(
            "The image is (nearly) blank — no drawing content was found."
        )
    elif ink_frac > 0.5:
        warnings.append(
            f"More than half the pixels are dark ({ink_frac:.0%}) — the image may "
            "be inverted or badly exposed; treat the result as unreliable."
        )

    # ---- image-quality warnings (each is measurable, not a guess) --------- #
    if not stats["blank"]:
        if stats["contrast"] < LOW_CONTRAST:
            warnings.append(
                f"Low contrast between ink and background ({stats['contrast']:.0%}) — "
                "faint lines may have been missed."
            )
        if stats["bg_std"] > BG_STD_MAX or stats["bg_mean"] < BG_MEAN_MIN:
            warnings.append(
                f"The background is uneven (mean {stats['bg_mean']:.0%}, spread "
                f"{stats['bg_std']:.0%}) — this looks like a photo of a drawing "
                "rather than a flat scan; geometry confidence is reduced."
            )
        if stats["speckle"] > SPECKLE_WARN:
            warnings.append(
                f"Noisy input: {stats['speckle']:.0%} of the ink pixels are isolated "
                "specks and were discarded."
            )

    # ---- deskew ------------------------------------------------------------ #
    deskewed, angle = deskew(binary, max_angle_deg=max_deskew_deg)
    if abs(angle) >= 0.1:
        direction = "counter-clockwise" if angle > 0 else "clockwise"
        warnings.append(
            f"Deskewed by {abs(angle):.1f}° ({direction}) to straighten the drawing."
        )

    # ---- segments ---------------------------------------------------------- #
    segments = extract_segments(
        deskewed, min_len_px=min_len_px, max_gap_px=max_gap_px, angle_tol_deg=angle_tol_deg
    )
    quality = _quality_factor(stats)
    if degraded:
        quality = max(MIN_QUALITY_FACTOR, quality * DEGRADED_QUALITY)
        segments = [
            s
            for s in segments
            if s.length_px >= DEGRADED_MIN_LEN_FACTOR * min_len_px
        ]
        if not segments:
            warnings.append(
                "No segments passed the degraded-image reliability filter (only "
                f"segments at least {DEGRADED_MIN_LEN_FACTOR:.0f}× min_len_px long are "
                "kept when the binarization is unreliable)."
            )
    if quality < 0.999:
        segments = [
            replace(s, confidence=round(s.confidence * quality, 2)) for s in segments
        ]
    if 0 < len(segments) < 5:
        warnings.append(
            f"Only {len(segments)} line segment(s) were extracted — the result is "
            "very likely incomplete; a CAD-exported PDF will give a much better model."
        )

    # ---- scale ------------------------------------------------------------- #
    scale, reason = estimate_scale(
        deskewed, segments, bar_px=bar_px, bar_metres=bar_metres
    )
    if metres_per_px is not None:
        if metres_per_px > 0:
            scale = float(metres_per_px)
            reason = f"metres_per_px supplied by caller ({metres_per_px:g} m/px)"
        else:
            warnings.append(
                f"Ignored invalid metres_per_px={metres_per_px!r} (must be positive)."
            )
    if scale is None:
        warnings.append(f"No scale evidence found: {reason}")

    out = to_scene_input(segments, metres_per_px=scale, north_deg=north_deg)
    out["warnings"] = warnings + out["warnings"]
    out["meta"].update(
        {
            "source_file": str(path),
            "render_dpi": int(dpi),
            "page_index": int(page),
            "image_size_px": [int(gray.shape[1]), int(gray.shape[0])],
            "px_to_pt": 72.0 / float(dpi),
            "binarize_method": binarize_method,
            "polarity_inverted": bool(polarity_inverted),
            "blueprint_quality": blueprint_quality_score(stats),
            "ink_fraction": round(ink_frac, 5),
            "deskew_deg": float(angle),
            "quality_factor": round(quality, 3),
            "degraded": bool(degraded),
            "scale_reason": reason,
            "diagnostics": stats,
        }
    )
    return out


def _image_stats(
    gray: np.ndarray, binary: np.ndarray, *, threshold: float | None = None
) -> dict[str, float | bool]:
    """Measurable image properties used for warnings and the quality factor."""
    g = np.asarray(gray, dtype=np.float64)
    m = np.asarray(binary, dtype=bool)
    blank = bool(float(g.std()) < 0.012)
    bg = ~m
    ink = m
    bg_mean = float(g[bg].mean()) if bg.any() else 1.0
    bg_std = float(g[bg].std()) if bg.any() else 0.0
    ink_mean = float(g[ink].mean()) if ink.any() else 0.0
    return {
        "blank": blank,
        "threshold": round(float(threshold), 4) if threshold is not None else None,
        "bg_mean": round(bg_mean, 4),
        "bg_std": round(bg_std, 4),
        "ink_mean": round(ink_mean, 4),
        "contrast": round(bg_mean - ink_mean, 4),
        "speckle": round(_speckle_ratio(m), 4),
    }


def _class_separation(gray: np.ndarray, binary: np.ndarray) -> tuple[bool, float, float]:
    """(separated?, contrast, class spread) for the ink/background split.

    ``contrast`` is ``mean(background) - mean(ink)``; ``spread`` is the sum of
    the two class standard deviations.  A well-binarized line drawing separates
    its classes by many spreads; heavy noise or a very faint drawing makes the
    classes overlap and the threshold meaningless.
    """
    g = np.asarray(gray, dtype=np.float64)
    m = np.asarray(binary, dtype=bool)
    if not m.any() or m.all():
        return True, 1.0, 0.0
    ink, bg = g[m], g[~m]
    sep = float(bg.mean() - ink.mean())
    spread = float(bg.std() + ink.std())
    return sep >= CLASS_SEP_MIN * spread, sep, spread


def _quality_factor(stats: dict[str, Any]) -> float:
    """Scale confidences by what the image itself supports, clamp [0.35, 1]."""
    q = 1.0
    if stats.get("contrast", 1.0) < LOW_CONTRAST:
        q *= 0.70
    if stats.get("bg_std", 0.0) > BG_STD_MAX or stats.get("bg_mean", 1.0) < BG_MEAN_MIN:
        q *= 0.75
    speckle = float(stats.get("speckle", 0.0))
    if speckle > SPECKLE_WARN:
        q *= max(0.5, 1.0 - 0.5 * min(1.0, speckle))
    return max(MIN_QUALITY_FACTOR, min(1.0, q))


def _speckle_ratio(mask: np.ndarray) -> float:
    """Share of ink pixels with no ink in their 8-neighbourhood."""
    n = int(mask.sum())
    if n == 0:
        return 0.0
    p = np.pad(mask, 1, constant_values=False)
    h, w = mask.shape
    nb = np.zeros_like(mask)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            nb |= p[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w]
    isolated = mask & ~nb
    return float(isolated.sum()) / float(n)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _format_summary(plan: dict[str, Any], path: str | Path) -> str:
    meta = plan.get("meta", {})
    diag = meta.get("diagnostics", {})
    segs = plan.get("segment_details", [])
    lines: list[str] = []
    lines.append(f"Karmi raster extraction — {path}")
    size = meta.get("image_size_px", ["?", "?"])
    lines.append(
        f"  image       : {size[0]} x {size[1]} px "
        f"(render dpi {meta.get('render_dpi', '?')}, page {meta.get('page_index', 0) + 1})"
    )
    method = meta.get("binarize_method", "?")
    thr = diag.get("threshold")
    thr_txt = f"{thr}" if thr is not None else "local mean − 0.03 (adaptive)"
    lines.append(
        f"  binarize    : {method} threshold "
        f"{thr_txt}, ink {meta.get('ink_fraction', 0.0):.2%} of pixels"
        + ("  [DEGRADED: threshold judged unreliable]" if meta.get("degraded") else "")
    )
    lines.append(
        f"  contrast    : ink {diag.get('ink_mean', 0.0):.2f} vs background "
        f"{diag.get('bg_mean', 0.0):.2f} (contrast {diag.get('contrast', 0.0):.2f}), "
        f"background spread {diag.get('bg_std', 0.0):.2f}"
    )
    ang = float(meta.get("deskew_deg", 0.0))
    if abs(ang) >= 0.1:
        lines.append(f"  deskew      : applied {ang:+.2f}° (PIL convention, + = counter-clockwise)")
    else:
        lines.append("  deskew      : none needed (drawing is axis-aligned)")
    lines.append(
        f"  quality     : {meta.get('quality_factor', 1.0):.2f} "
        f"(speckle {diag.get('speckle', 0.0):.1%})"
    )

    if not segs:
        lines.append("  segments    : 0 — nothing to model")
    else:
        n_h = sum(1 for s in segs if _axis_of(s["angle_deg"], ANGLE_TOL_DEG) == 0)
        n_v = sum(1 for s in segs if _axis_of(s["angle_deg"], ANGLE_TOL_DEG) == 1)
        confs = [s["confidence"] for s in segs]
        lines.append(
            f"  segments    : {len(segs)} ({n_h} horizontal, {n_v} vertical); "
            f"confidence {min(confs):.2f}–{max(confs):.2f} (median "
            f"{float(np.median(confs)):.2f})"
        )
        devs = [min(s["angle_deg"] % 90.0, 90.0 - s["angle_deg"] % 90.0) for s in segs]
        n_le_1 = sum(1 for d in devs if d <= 1.0)
        n_le_2 = sum(1 for d in devs if 1.0 < d <= 2.0)
        n_gt_2 = len(devs) - n_le_1 - n_le_2
        lines.append(
            f"  angles      : deviation from axis — ≤1°: {n_le_1}, 1–2°: {n_le_2}, "
            f">2°: {n_gt_2}"
        )
        lens = sorted(s["length_px"] for s in segs)
        thick = sorted(s["thickness_px"] for s in segs)
        lines.append(
            f"  lengths     : min {lens[0]:.0f} / median {lens[len(lens) // 2]:.0f} / "
            f"max {lens[-1]:.0f} px"
        )
        lines.append(
            f"  thickness   : min {thick[0]:.1f} / median {thick[len(thick) // 2]:.1f} / "
            f"max {thick[-1]:.1f} px"
        )

    if plan.get("scale_m_per_unit") is not None:
        lines.append(
            f"  scale       : {plan['scale_m_per_unit']:.6g} m/px — "
            f"{meta.get('scale_reason', '')}"
        )
    else:
        lines.append(f"  scale       : UNKNOWN — {meta.get('scale_reason', '')}")

    warns = plan.get("warnings", [])
    lines.append(f"  warnings ({len(warns)})")
    for w in warns:
        lines.append(f"    - {w}")
    return "\n".join(lines)


def _jsonable(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m core.raster",
        description=(
            "Extract straight line segments from a raster/scan floor plan "
            "(deterministic, offline)."
        ),
    )
    ap.add_argument("image", help="path to the image (PNG/JPEG/...) or PDF")
    ap.add_argument("--dpi", type=int, default=DEFAULT_RENDER_DPI, help="PDF render dpi")
    ap.add_argument("--page", type=int, default=0, help="PDF page index")
    ap.add_argument("--min-len-px", type=float, default=MIN_LEN_PX, help="shortest segment kept")
    ap.add_argument("--max-gap-px", type=float, default=MAX_GAP_PX, help="join runs closer than this")
    ap.add_argument("--angle-tol", type=float, default=ANGLE_TOL_DEG, help="degrees from axis")
    ap.add_argument("--method", default="otsu", choices=["otsu", "adaptive"], help="binarize method")
    ap.add_argument("--metres-per-px", type=float, default=None, help="known scale, if any")
    ap.add_argument("--bar-px", type=float, default=None, help="known reference length in px")
    ap.add_argument("--bar-metres", type=float, default=None, help="known reference length in metres")
    ap.add_argument("--north", type=float, default=None, help="north bearing (0 = up)")
    ap.add_argument("--json", default=None, help="write the full dict to this JSON path")
    args = ap.parse_args(argv)

    try:
        plan = extract_plan(
            args.image,
            dpi=args.dpi,
            page=args.page,
            min_len_px=args.min_len_px,
            max_gap_px=args.max_gap_px,
            angle_tol_deg=args.angle_tol,
            binarize_method=args.method,
            metres_per_px=args.metres_per_px,
            bar_px=args.bar_px,
            bar_metres=args.bar_metres,
            north_deg=args.north,
        )
    except IngestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(_format_summary(plan, args.image))
    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(_jsonable(plan), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "Segment",
    "load_gray",
    "binarize",
    "deskew",
    "extract_segments",
    "estimate_scale",
    "to_scene_input",
    "to_point_units",
    "extract_plan",
    "main",
    "MIN_LEN_PX",
    "MAX_GAP_PX",
    "ANGLE_TOL_DEG",
    "DEFAULT_RENDER_DPI",
]