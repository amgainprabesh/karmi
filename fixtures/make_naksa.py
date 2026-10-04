"""Generate a synthetic — but structurally realistic — Nepali naksa-style floor plan PDF.

Why this exists: the whole pipeline needs one *known* drawing to test against, and we
cannot ship a real Naksa Pass (they contain names, addresses and engineer signatures).
This generator draws a single-floor residential plan the way CAD exports look: walls as
real vector line pairs, door/window gaps with jamb lines, room label text, dimension
text, a scale note and a north arrow.

Usage:
    python fixtures/make_naksa.py [out.pdf] [--variant base|drift|sparse]

Variants:
    base   : the reference plan (2 bed, 1 kitchen, 1 bath, 1 living)
    drift  : same plan, drawn with a narrower stair and a smaller window — used by the
             diff tests as a *drawing* that should produce differences
    sparse : walls only, no text, no north arrow — exercises the warning paths
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pymupdf

# A4 landscape in points
PAGE_W, PAGE_H = 842.0, 595.0
MARGIN = 60.0

# Drawing scale: 1 pt = 25 mm  ->  1 m = 40 pt.  (so a 10 m house is 400 pt wide)
PT_PER_M = 40.0

# Wall thicknesses (metres)
EXT_T, INT_T = 0.23, 0.115


def m(v: float) -> float:
    """metres -> page points"""
    return v * PT_PER_M


def _line(page: "pymupdf.Page", a, b, *, width=1.2, color=(0, 0, 0)):
    page.draw_line(pymupdf.Point(*a), pymupdf.Point(*b), color=color, width=width)


def _rect(page: "pymupdf.Page", x0, y0, x1, y1, *, width=1.0, color=(0, 0, 0), dashes=None):
    r = pymupdf.Rect(x0, y0, x1, y1)
    page.draw_rect(r, color=color, width=width, dashes=dashes)


def _text(page: "pymupdf.Page", x, y, s, *, size=8, color=(0, 0, 0)):
    page.insert_text(pymupdf.Point(x, y), s, fontsize=size, color=color, fontname="helv")


def _wall_run(page, start, end, thickness, *, gaps=(), color=(0, 0, 0)):
    """Draw a wall as a pair of parallel lines with optional openings (gaps).

    gaps: sequence of (centre_along_run_metres, width_metres)
    """
    (x0, y0), (x1, y1) = start, end
    horiz = abs(y1 - y0) < 1e-6
    half = m(thickness) / 2.0

    # normal offsets
    if horiz:
        offs = [(0, -half), (0, half)]
    else:
        offs = [(-half, 0), (half, 0)]

    length = abs((x1 - x0) if horiz else (y1 - y0))
    # build spans (0..length) minus gaps
    spans = [(0.0, length)]
    for centre_m, width_m in gaps:
        c, w = m(centre_m), m(width_m)
        new = []
        for s, e in spans:
            if c - w / 2 > s:
                new.append((s, min(e, c - w / 2)))
            if c + w / 2 < e:
                new.append((max(s, c + w / 2), e))
        spans = [sp for sp in new if sp[1] - sp[0] > 0.5]

    for ox, oy in offs:
        for s, e in spans:
            if horiz:
                a = (min(x0, x1) + s + ox, y0 + oy)
                b = (min(x0, x1) + e + ox, y0 + oy)
            else:
                a = (x0 + ox, min(y0, y1) + s + oy)
                b = (x0 + ox, min(y0, y1) + e + oy)
            _line(page, a, b)

    # jambs at each gap
    for centre_m, width_m in gaps:
        c, w = m(centre_m), m(width_m)
        for edge in (c - w / 2, c + w / 2):
            if horiz:
                a = (min(x0, x1) + edge - half, y0 - half)
                b = (min(x0, x1) + edge + half, y0 + half)
            else:
                a = (x0 - half, min(y0, y1) + edge - half)
                b = (x0 + half, min(y0, y1) + edge + half)
            _line(page, a, b, width=1.0)


def _north_arrow(page, cx, cy, size=26):
    _line(page, (cx, cy + size / 2), (cx, cy - size / 2), width=1.6)
    _line(page, (cx - size * 0.18, cy - size * 0.22), (cx, cy - size / 2), width=1.2)
    _line(page, (cx + size * 0.18, cy - size * 0.22), (cx, cy - size / 2), width=1.2)
    _text(page, cx - 3, cy - size / 2 - 6, "N", size=9)


def _dimension(page, a, b, label):
    """A dimension line with ticks and a label, drawn offset from a wall."""
    _line(page, a, b, width=0.6)
    for p in (a, b):
        _line(page, (p[0] - 3, p[1] - 3), (p[0] + 3, p[1] + 3), width=0.6)
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    _text(page, mx - len(label) * 2.2, my - 3, label, size=7)


def build(out: Path, variant: str = "base") -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)

    ox, oy = MARGIN + 40, MARGIN + 40  # drawing origin on the page

    # ---- house envelope: 10.0 m x 7.5 m -------------------------------- #
    W, H = 10.0, 7.5
    x0, y0 = ox, oy
    x1, y1 = ox + m(W), oy + m(H)

    # openings differ per variant
    if variant == "drift":
        front_gaps = [(2.0, 1.0), (7.0, 0.9)]     # narrow window (1.0 m)
        stair_note = "STAIR 0.85 M"
    else:
        front_gaps = [(2.0, 1.5), (7.0, 1.2)]     # reference window (1.5 m)
        stair_note = "STAIR 1.00 M"

    _wall_run(page, (x0, y1), (x1, y1), EXT_T, gaps=front_gaps)          # south (front) wall
    _wall_run(page, (x1, y0), (x1, y1), EXT_T, gaps=[(3.0, 0.9)])        # east wall — side door
    _wall_run(page, (x0, y0), (x1, y0), EXT_T, gaps=[(3.0, 1.2), (6.5, 1.2)])  # north wall
    _wall_run(page, (x0, y0), (x0, y1), EXT_T)                           # west wall

    # ---- internal walls ------------------------------------------------- #
    # Spine wall: splits the plan into a left column (bedrooms) and a right
    # column (living / kitchen / bath).  Runs the full height with a door gap.
    midx = x0 + m(6.0)
    _wall_run(page, (midx, y0), (midx, y1), INT_T, gaps=[(4.0, 0.8)])

    # Horizontal divider at 4.0 m, on BOTH sides of the spine wall, so each
    # column closes its own rooms: left -> BEDROOM 1 (north) / BEDROOM 2 (south),
    # right -> LIVING (north) / KITCHEN + BATH (south).
    midy = y0 + m(4.0)
    _wall_run(page, (x0, midy), (midx, midy), INT_T, gaps=[(3.0, 0.8)])
    _wall_run(page, (midx, midy), (x1, midy), INT_T, gaps=[(1.6, 0.75)])

    # Second divider in the right column at 5.6 m: separates KITCHEN from BATH.
    bathy = y0 + m(5.6)
    _wall_run(page, (midx, bathy), (x1, bathy), INT_T, gaps=[(1.6, 0.7)])

    # ---- room labels ----------------------------------------------------- #
    if variant != "sparse":
        _text(page, x0 + m(0.9), y0 + m(2.2), "BEDROOM 1", size=8)
        _text(page, x0 + m(0.9), y0 + m(5.6), "BEDROOM 2", size=8)
        _text(page, x0 + m(6.6), y0 + m(1.4), "LIVING", size=8)
        _text(page, x0 + m(6.6), y0 + m(4.9), "KITCHEN", size=8)
        _text(page, x0 + m(6.6), y0 + m(6.6), "BATH", size=8)
        _text(page, x0 + m(6.5), y0 + m(3.2), stair_note, size=6)

        # ---- dimensions --------------------------------------------------- #
        _dimension(page, (x0, y1 + 26), (x1, y1 + 26), f"{W:.1f} m")
        _dimension(page, (x0 - 26, y0), (x0 - 26, y1), f"{H:.1f} m")

        # ---- scale note + north arrow -------------------------------------- #
        _text(page, x0, y1 + 52, "SCALE 1:100   |   ALL DIMENSIONS IN METRES", size=7)
        _north_arrow(page, x1 + 40, y0 + 20)

        _text(page, x0, y0 - 26, "GROUND FLOOR PLAN — SAMPLE (synthetic, no real data)", size=8)

    doc.set_metadata(
        {
            "title": f"Karmi sample naksa ({variant})",
            "author": "Karmi fixtures",
            "subject": "Synthetic residential ground floor plan — not a real submission",
        }
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    doc.close()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default=None)
    ap.add_argument("--variant", default="base", choices=["base", "drift", "sparse"])
    args = ap.parse_args()
    default = Path(__file__).parent / f"naksa_{args.variant}.pdf"
    p = build(Path(args.out) if args.out else default, args.variant)
    print(f"wrote {p} ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()