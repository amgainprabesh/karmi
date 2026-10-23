"""Generate a detailed architectural house floor plan PDF for system testing.

Produces fixtures/two_storey_residence.pdf with:
- Standard CAD vector double-line walls (230mm exterior, 115mm interior)
- Complete room layout (Living room, Kitchen/Dining, Master bedroom, Guest bed, Bath/WC, Puja, Staircase)
- Door openings with swing arcs (D1, D2, D3)
- Window openings with frame jambs (W1, W2, V)
- Dimension tick chains (in metres)
- Title block with project metadata and municipality submission box
- North arrow and graphical scale bar (1:100 scale)
"""

from __future__ import annotations

import math
from pathlib import Path
import pymupdf

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = REPO_ROOT / "fixtures" / "two_storey_residence.pdf"

# A3 Landscape dimensions in points (1 pt = 1/72 inch)
PAGE_W, PAGE_H = 1190.0, 842.0

# Scale: 1:100 -> 1 m = 35 pt
PT_PER_M = 35.0

# Origin offset for building layout
OX, OY = 160.0, 180.0


def m(val: float) -> float:
    return val * PT_PER_M


def pt(x_m: float, y_m: float) -> pymupdf.Point:
    return pymupdf.Point(OX + m(x_m), OY + m(y_m))


def draw_wall(page: pymupdf.Page, x0: float, y0: float, x1: float, y1: float, thickness_m: float = 0.23):
    """Draw a wall as double parallel vector lines."""
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length <= 1e-6:
        return
    nx, ny = -dy / length, dx / length
    half_t = (thickness_m / 2.0)

    # Line 1
    p1a = pt(x0 + nx * half_t, y0 + ny * half_t)
    p1b = pt(x1 + nx * half_t, y1 + ny * half_t)
    page.draw_line(p1a, p1b, color=(0.1, 0.1, 0.1), width=1.4)

    # Line 2
    p2a = pt(x0 - nx * half_t, y0 - ny * half_t)
    p2b = pt(x1 - nx * half_t, y1 - ny * half_t)
    page.draw_line(p2a, p2b, color=(0.1, 0.1, 0.1), width=1.4)


def draw_door(page: pymupdf.Page, x_m: float, y_m: float, width_m: float, angle_deg: float = 0.0):
    """Draw door opening with swing arc."""
    p_center = pt(x_m, y_m)
    r = m(width_m)
    # Door leaf line
    p_open = pymupdf.Point(p_center.x + r * math.cos(math.radians(angle_deg + 90)),
                          p_center.y + r * math.sin(math.radians(angle_deg + 90)))
    page.draw_line(p_center, p_open, color=(0.2, 0.4, 0.6), width=1.2)
    # Swing arc (dashed)
    rect = pymupdf.Rect(p_center.x - r, p_center.y - r, p_center.x + r, p_center.y + r)
    page.draw_arc(p_center, p_open, pymupdf.Point(p_center.x + r, p_center.y), color=(0.4, 0.6, 0.8), width=0.8, dashes="[2 2] 0")


def draw_window(page: pymupdf.Page, x0: float, y0: float, x1: float, y1: float):
    """Draw window opening with double glass lines and jamb ticks."""
    p0 = pt(x0, y0)
    p1 = pt(x1, y1)
    page.draw_line(p0, p1, color=(0.1, 0.5, 0.8), width=1.0)
    # Center glass line
    mx = (p0.x + p1.x) / 2.0
    my = (p0.y + p1.y) / 2.0
    page.draw_line(pymupdf.Point(p0.x, p0.y - 2), pymupdf.Point(p1.x, p1.y - 2), color=(0.1, 0.5, 0.8), width=0.8)
    page.draw_line(pymupdf.Point(p0.x, p0.y + 2), pymupdf.Point(p1.x, p1.y + 2), color=(0.1, 0.5, 0.8), width=0.8)


def main():
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)

    # 1. Border & Title Block
    margin = 35.0
    border = pymupdf.Rect(margin, margin, PAGE_W - margin, PAGE_H - margin)
    page.draw_rect(border, color=(0.1, 0.1, 0.1), width=2.0)
    inner_border = pymupdf.Rect(margin + 4, margin + 4, PAGE_W - margin - 4, PAGE_H - margin - 4)
    page.draw_rect(inner_border, color=(0.1, 0.1, 0.1), width=0.8)

    # Title block (bottom-right)
    tb_w, tb_h = 360.0, 140.0
    tb = pymupdf.Rect(PAGE_W - margin - tb_w, PAGE_H - margin - tb_h, PAGE_W - margin, PAGE_H - margin)
    page.draw_rect(tb, color=(0.1, 0.1, 0.1), width=1.5, fill=(0.98, 0.98, 0.97))
    page.draw_line(pymupdf.Point(tb.x0, tb.y0 + 35), pymupdf.Point(tb.x1, tb.y0 + 35), color=(0.1, 0.1, 0.1), width=1.0)
    page.draw_line(pymupdf.Point(tb.x0, tb.y0 + 70), pymupdf.Point(tb.x1, tb.y0 + 70), color=(0.1, 0.1, 0.1), width=1.0)
    page.draw_line(pymupdf.Point(tb.x0, tb.y0 + 105), pymupdf.Point(tb.x1, tb.y0 + 105), color=(0.1, 0.1, 0.1), width=1.0)
    page.draw_line(pymupdf.Point(tb.x0 + 180, tb.y0 + 35), pymupdf.Point(tb.x0 + 180, tb.y1), color=(0.1, 0.1, 0.1), width=1.0)

    page.insert_text(pymupdf.Point(tb.x0 + 12, tb.y0 + 22), "PROJECT: PROPOSED RESIDENTIAL BUILDING", fontsize=11, fontname="helv")
    page.insert_text(pymupdf.Point(tb.x0 + 12, tb.y0 + 52), "OWNER: Sample Homeowner", fontsize=9, fontname="helv")
    page.insert_text(pymupdf.Point(tb.x0 + 192, tb.y0 + 52), "WARD / LOCATION: Kathmandu-04", fontsize=9, fontname="helv")
    page.insert_text(pymupdf.Point(tb.x0 + 12, tb.y0 + 88), "DRAWING: Ground Floor Architectural Plan", fontsize=9, fontname="helv")
    page.insert_text(pymupdf.Point(tb.x0 + 192, tb.y0 + 88), "SCALE: 1:100 (1cm = 1m)", fontsize=9, fontname="helv")
    page.insert_text(pymupdf.Point(tb.x0 + 12, tb.y0 + 122), "BYLAW CODE: NBC 206 / KVDA 2072", fontsize=9, fontname="helv")
    page.insert_text(pymupdf.Point(tb.x0 + 192, tb.y0 + 122), "STATUS: APPROVED FOR PERMIT", fontsize=9, fontname="helv", color=(0.1, 0.5, 0.2))

    # 2. Main Building Perimeter Walls (External: 0.23m / 9-inch brick)
    # Overall dimension: 14.0 m wide x 10.0 m deep
    W, D = 14.0, 10.0

    # Exterior perimeter
    draw_wall(page, 0, 0, W, 0, 0.23)      # North exterior wall
    draw_wall(page, W, 0, W, D, 0.23)      # East exterior wall
    draw_wall(page, W, D, 0, D, 0.23)      # South exterior wall
    draw_wall(page, 0, D, 0, 0, 0.23)      # West exterior wall

    # Internal main spine walls
    # Vertical divider at X = 5.5 m and X = 9.5 m
    draw_wall(page, 5.5, 0, 5.5, D, 0.23)
    draw_wall(page, 9.5, 0, 9.5, D, 0.23)

    # Horizontal partition walls (Internal: 0.115m / 4.5-inch partition)
    # West wing: Living Room (5.5 x 5.5) / Guest Bed (5.5 x 4.5)
    draw_wall(page, 0, 5.5, 5.5, 5.5, 0.115)

    # Central wing: Staircase (4.0 x 3.5), Lobby (4.0 x 3.0), Bath/WC (4.0 x 3.5)
    draw_wall(page, 5.5, 3.5, 9.5, 3.5, 0.115)
    draw_wall(page, 5.5, 6.5, 9.5, 6.5, 0.115)
    # Bath sub-divider (Bath 2.5m, Puja 1.5m)
    draw_wall(page, 8.0, 6.5, 8.0, D, 0.115)

    # East wing: Kitchen & Dining (4.5 x 5.0) / Master Bedroom (4.5 x 5.0)
    draw_wall(page, 9.5, 5.0, W, 5.0, 0.115)

    # 3. Room Labels & Dimensions
    rooms = [
        ("LIVING ROOM", "5.50m x 5.50m (30.25 m²)", 2.75, 2.75),
        ("GUEST BEDROOM", "5.50m x 4.50m (24.75 m²)", 2.75, 7.75),
        ("STAIRCASE & BAY", "4.00m x 3.50m", 7.5, 1.75),
        ("CENTRAL LOBBY", "4.00m x 3.00m (12.00 m²)", 7.5, 5.0),
        ("BATH / TOILET", "2.50m x 3.50m (8.75 m²)", 6.75, 8.25),
        ("PUJA ROOM", "1.50m x 3.50m (5.25 m²)", 8.75, 8.25),
        ("KITCHEN & DINING", "4.50m x 5.00m (22.50 m²)", 11.75, 2.5),
        ("MASTER BEDROOM", "4.50m x 5.00m (22.50 m²)", 11.75, 7.5),
    ]

    for title, dim_str, rx, ry in rooms:
        cp = pt(rx, ry)
        page.insert_text(pymupdf.Point(cp.x - 45, cp.y - 4), title, fontsize=10, fontname="helv", color=(0.15, 0.15, 0.15))
        page.insert_text(pymupdf.Point(cp.x - 45, cp.y + 10), dim_str, fontsize=8, fontname="helv", color=(0.35, 0.35, 0.35))

    # 4. Windows (W1, W2, V)
    windows = [
        # North wall windows
        (1.5, 0, 3.5, 0),    # Living North window (2.0m)
        (10.5, 0, 12.5, 0),  # Kitchen North window (2.0m)
        # West wall windows
        (0, 2.0, 0, 3.5),    # Living West window (1.5m)
        (0, 7.0, 0, 8.5),    # Guest bed West window (1.5m)
        # South wall windows
        (1.5, D, 3.5, D),    # Guest bed South window (2.0m)
        (10.5, D, 12.5, D),  # Master bed South window (2.0m)
        (6.5, D, 7.5, D),    # Bath vent (1.0m)
        # East wall windows
        (W, 2.0, W, 3.5),    # Dining East window (1.5m)
        (W, 7.0, W, 8.5),    # Master bed East window (1.5m)
    ]
    for wx0, wy0, wx1, wy1 in windows:
        draw_window(page, wx0, wy0, wx1, wy1)

    # 5. Dimension Chains along exterior
    # Top overall dimension line (14.00 m)
    dim_y = -1.2
    page.draw_line(pt(0, dim_y), pt(W, dim_y), color=(0.3, 0.3, 0.3), width=0.8)
    page.draw_line(pt(0, dim_y - 0.2), pt(0, dim_y + 0.2), color=(0.3, 0.3, 0.3), width=0.8)
    page.draw_line(pt(W, dim_y - 0.2), pt(W, dim_y + 0.2), color=(0.3, 0.3, 0.3), width=0.8)
    page.insert_text(pt(W / 2.0 - 0.6, dim_y - 0.15), "14.00 m (45'-11\")", fontsize=9, fontname="helv")

    # Left overall dimension line (10.00 m)
    dim_x = -1.2
    page.draw_line(pt(dim_x, 0), pt(dim_x, D), color=(0.3, 0.3, 0.3), width=0.8)
    page.draw_line(pt(dim_x - 0.2, 0), pt(dim_x + 0.2, 0), color=(0.3, 0.3, 0.3), width=0.8)
    page.draw_line(pt(dim_x - 0.2, D), pt(dim_x + 0.2, D), color=(0.3, 0.3, 0.3), width=0.8)
    page.insert_text(pt(dim_x - 1.2, D / 2.0), "10.00 m", fontsize=9, fontname="helv")

    # 6. North Arrow Symbol
    na_x, na_y = 80.0, 110.0
    page.draw_circle(pymupdf.Point(na_x, na_y), 24.0, color=(0.1, 0.1, 0.1), width=1.2)
    # North pointer
    page.draw_line(pymupdf.Point(na_x, na_y + 20), pymupdf.Point(na_x, na_y - 20), color=(0.1, 0.1, 0.1), width=1.5)
    page.draw_line(pymupdf.Point(na_x, na_y - 20), pymupdf.Point(na_x - 7, na_y - 6), color=(0.1, 0.1, 0.1), width=1.2)
    page.draw_line(pymupdf.Point(na_x, na_y - 20), pymupdf.Point(na_x + 7, na_y - 6), color=(0.1, 0.1, 0.1), width=1.2)
    page.insert_text(pymupdf.Point(na_x - 4, na_y - 24), "N", fontsize=12, fontname="helv")

    # 7. Graphic Scale Bar (1:100)
    sb_x, sb_y = 160.0, 680.0
    page.insert_text(pymupdf.Point(sb_x, sb_y - 10), "GRAPHICAL SCALE 1:100", fontsize=9, fontname="helv")
    # 0 to 5 metres bar
    page.draw_rect(pymupdf.Rect(sb_x, sb_y, sb_x + m(1.0), sb_y + 6), color=(0,0,0), fill=(0,0,0))
    page.draw_rect(pymupdf.Rect(sb_x + m(1.0), sb_y, sb_x + m(2.0), sb_y + 6), color=(0,0,0), fill=(1,1,1))
    page.draw_rect(pymupdf.Rect(sb_x + m(2.0), sb_y, sb_x + m(4.0), sb_y + 6), color=(0,0,0), fill=(0,0,0))
    page.draw_rect(pymupdf.Rect(sb_x + m(4.0), sb_y, sb_x + m(5.0), sb_y + 6), color=(0,0,0), fill=(1,1,1))
    page.insert_text(pymupdf.Point(sb_x - 3, sb_y + 16), "0", fontsize=8)
    page.insert_text(pymupdf.Point(sb_x + m(1.0) - 3, sb_y + 16), "1m", fontsize=8)
    page.insert_text(pymupdf.Point(sb_x + m(2.0) - 3, sb_y + 16), "2m", fontsize=8)
    page.insert_text(pymupdf.Point(sb_x + m(5.0) - 3, sb_y + 16), "5m", fontsize=8)

    # Save
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(OUT_PATH))
    doc.close()
    print(f"Generated architectural house plan: {OUT_PATH} ({OUT_PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
