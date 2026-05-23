#!/usr/bin/env python3
"""gcode_to_svg.py – Visualise a plotter G-code file as an SVG.

  - G1 (draw) moves are rendered as solid coloured lines.
    Successive draw segments that share the same pen-down event get the same
    colour; the colour cycles through a small palette so separate strokes are
    visually distinct.
  - G0 (rapid / pen-up) moves are rendered as thin dotted grey lines.
  - The output SVG is scaled so the plotter mm coordinates map 1 mm -> 2 px
    (configurable via --scale).

Usage
-----
    python scripts/gcode_to_svg.py gcode/postcard_menger.gcode
    python scripts/gcode_to_svg.py gcode/postcard_menger.gcode -o svg/debug_menger.svg
    python scripts/gcode_to_svg.py gcode/postcard_menger.gcode --scale 3
"""

import argparse
import math
import os
import re
import sys
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# Palette for draw strokes (cycles per pen-down group)
# ---------------------------------------------------------------------------

PALETTE = [
    "#e41a1c", "#377eb8", "#4daf4a", "#984ea3",
    "#ff7f00", "#a65628", "#f781bf", "#999999",
]

# ---------------------------------------------------------------------------
# G-code parser
# ---------------------------------------------------------------------------

_COORD_RE = re.compile(r"([XYZF])([-+]?\d*\.?\d+)", re.IGNORECASE)


def _parse_coords(line: str) -> dict[str, float]:
    return {m.group(1).upper(): float(m.group(2)) for m in _COORD_RE.finditer(line)}


def parse_gcode(path: str):
    """Parse G-code and return two lists of polylines.

    Returns
    -------
    draw_groups : list[list[tuple[float,float]]]
        One entry per pen-down stroke; each entry is a list of (x, y) points.
    travel_segs : list[tuple[float,float,float,float]]
        Each entry is (x1, y1, x2, y2) for a rapid move.
    paper_w, paper_h : float | None
        Paper dimensions in mm, parsed from the header comment if present.
    """
    draw_groups: list[list[tuple[float, float]]] = []
    travel_segs: list[tuple[float, float, float, float]] = []

    cur_x = cur_y = 0.0
    pen_down = False
    current_group: list[tuple[float, float]] | None = None
    paper_w = paper_h = None

    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.split(";")[0].strip()   # strip comments

            # Parse paper size from header comment
            if paper_w is None:
                m = re.search(r"Paper:\s+([\d.]+)\s*x\s*([\d.]+)\s*mm", raw)
                if m:
                    paper_w, paper_h = float(m.group(1)), float(m.group(2))

            if not line:
                continue

            cmd = line.split()[0].upper()

            if cmd == "G0":
                coords = _parse_coords(line)
                nx = coords.get("X", cur_x)
                ny = coords.get("Y", cur_y)
                # Record rapid travel
                travel_segs.append((cur_x, cur_y, nx, ny))
                # Pen up: close current draw group
                if current_group is not None and len(current_group) >= 2:
                    draw_groups.append(current_group)
                current_group = None
                pen_down = False
                cur_x, cur_y = nx, ny

            elif cmd == "G1":
                coords = _parse_coords(line)
                nx = coords.get("X", cur_x)
                ny = coords.get("Y", cur_y)
                if pen_down:
                    if current_group is None:
                        current_group = [(cur_x, cur_y)]
                    current_group.append((nx, ny))
                cur_x, cur_y = nx, ny

            elif cmd in ("M3",):
                # Pen down
                pen_down = True
                if current_group is None:
                    current_group = [(cur_x, cur_y)]

            elif cmd in ("M5",):
                # Pen up
                if current_group is not None and len(current_group) >= 2:
                    draw_groups.append(current_group)
                current_group = None
                pen_down = False

    # Flush any open group
    if current_group is not None and len(current_group) >= 2:
        draw_groups.append(current_group)

    return draw_groups, travel_segs, paper_w, paper_h


# ---------------------------------------------------------------------------
# SVG generation
# ---------------------------------------------------------------------------

SVG_NS = "http://www.w3.org/2000/svg"


def _drawing_bbox(
    draw_groups: list[list[tuple[float, float]]],
) -> tuple[float, float, float, float] | None:
    """Return (x0, y0, x1, y1) mm bounding box of all draw strokes, or None."""
    xs = [x for g in draw_groups for x, y in g]
    ys = [y for g in draw_groups for x, y in g]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def pts_to_str(points: list[tuple[float, float]], scale: float, h: float) -> str:
    """Convert plotter (x, y) mm coordinates to SVG pixel space.

    Plotter: origin bottom-left, Y up.
    SVG:     origin top-left,    Y down.
    """
    return " ".join(f"{x * scale:.3f},{(h - y) * scale:.3f}" for x, y in points)


def generate_svg(
    draw_groups: list[list[tuple[float, float]]],
    travel_segs: list[tuple[float, float, float, float]],
    paper_w: float,
    paper_h: float,
    scale: float,
) -> ET.Element:
    w_px = paper_w * scale
    h_px = paper_h * scale

    svg = ET.Element("svg", {
        "xmlns": SVG_NS,
        "width":  f"{w_px:.1f}",
        "height": f"{h_px:.1f}",
        "viewBox": f"0 0 {w_px:.1f} {h_px:.1f}",
    })

    # Background
    ET.SubElement(svg, "rect", {
        "width": "100%", "height": "100%", "fill": "white",
    })

    # --- travel moves (pen-up) ---
    g_travel = ET.SubElement(svg, "g", {
        "id": "travel",
        "stroke": "#aaaaaa",
        "stroke-width": "0.5",
        "stroke-dasharray": "3,3",
        "fill": "none",
        "opacity": "0.6",
    })
    for x1, y1, x2, y2 in travel_segs:
        if (x1, y1) == (x2, y2):
            continue
        ET.SubElement(g_travel, "line", {
            "x1": f"{x1 * scale:.3f}",
            "y1": f"{(paper_h - y1) * scale:.3f}",
            "x2": f"{x2 * scale:.3f}",
            "y2": f"{(paper_h - y2) * scale:.3f}",
        })

    # --- draw strokes (pen-down) ---
    g_draw = ET.SubElement(svg, "g", {
        "id": "draw",
        "fill": "none",
        "stroke-width": "1",
        "stroke-linecap": "round",
        "stroke-linejoin": "round",
    })
    for i, group in enumerate(draw_groups):
        colour = PALETTE[i % len(PALETTE)]
        ET.SubElement(g_draw, "polyline", {
            "stroke": colour,
            "points": pts_to_str(group, scale, paper_h),
        })

    # --- ruler ticks around drawing bounding box ---
    bbox_mm = _drawing_bbox(draw_groups)
    if bbox_mm:
        bx0, by0, bx1, by1 = bbox_mm
        tick_sm = 1.0 * scale   # 1 mm tick length in px
        tick_lg = 2.0 * scale   # 5 mm tick length in px

        g_ruler = ET.SubElement(svg, "g", {
            "id": "ruler",
            "stroke": "#555555",
            "stroke-width": "0.5",
            "fill": "none",
        })

        # Tick range: drawing bbox extended by RULER_MARGIN, clamped to paper.
        RULER_MARGIN = 10.0
        rx0 = max(0.0, bx0 - RULER_MARGIN)
        rx1 = min(paper_w, bx1 + RULER_MARGIN)
        ry0 = max(0.0, by0 - RULER_MARGIN)
        ry1 = min(paper_h, by1 + RULER_MARGIN)

        # X ruler: horizontal baseline RULER_MARGIN above the drawing top.
        # Ticks point further upward.
        svg_y_x_ruler = (paper_h - (by1 + RULER_MARGIN)) * scale
        ET.SubElement(g_ruler, "line", {
            "x1": f"{rx0 * scale:.3f}", "y1": f"{svg_y_x_ruler:.3f}",
            "x2": f"{rx1 * scale:.3f}", "y2": f"{svg_y_x_ruler:.3f}",
        })
        for xi in range(math.ceil(rx0 - 1e-9), math.floor(rx1 + 1e-9) + 1):
            t = tick_lg if xi % 5 == 0 else tick_sm
            sx = f"{xi * scale:.3f}"
            ET.SubElement(g_ruler, "line", {
                "x1": sx, "y1": f"{svg_y_x_ruler:.3f}",
                "x2": sx, "y2": f"{svg_y_x_ruler + t:.3f}",
            })

        # Y ruler: vertical baseline RULER_MARGIN to the left of the drawing.
        # Ticks point further leftward.
        svg_x_y_ruler = (bx0 - RULER_MARGIN) * scale
        ET.SubElement(g_ruler, "line", {
            "x1": f"{svg_x_y_ruler:.3f}", "y1": f"{(paper_h - ry1) * scale:.3f}",
            "x2": f"{svg_x_y_ruler:.3f}", "y2": f"{(paper_h - ry0) * scale:.3f}",
        })
        for yi in range(math.ceil(ry0 - 1e-9), math.floor(ry1 + 1e-9) + 1):
            t = tick_lg if yi % 5 == 0 else tick_sm
            sy = f"{(paper_h - yi) * scale:.3f}"
            ET.SubElement(g_ruler, "line", {
                "x1": f"{svg_x_y_ruler:.3f}",     "y1": sy,
                "x2": f"{svg_x_y_ruler + t:.3f}", "y2": sy,
            })

    return svg


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a plotter G-code file to a debug SVG.",
    )
    parser.add_argument("gcode", help="Input .gcode file.")
    parser.add_argument("--output", "-o", default=None,
                        help="Output SVG path.  Default: svg/<stem>.svg")
    parser.add_argument("--scale", "-s", type=float, default=10.0,
                        help="Pixels per mm (default: 10).")
    parser.add_argument("--paper-width",  type=float, default=None,
                        help="Paper width  in mm (overrides value from G-code header).")
    parser.add_argument("--paper-height", type=float, default=None,
                        help="Paper height in mm (overrides value from G-code header).")
    args = parser.parse_args()

    if not os.path.isfile(args.gcode):
        print(f"Error: file not found: {args.gcode}", file=sys.stderr)
        sys.exit(1)

    draw_groups, travel_segs, paper_w, paper_h = parse_gcode(args.gcode)

    paper_w  = args.paper_width  or paper_w  or 105.0
    paper_h  = args.paper_height or paper_h  or 148.0

    print(f"{os.path.basename(args.gcode)}: "
          f"{len(draw_groups)} stroke(s), {len(travel_segs)} travel move(s)  "
          f"paper {paper_w} x {paper_h} mm")

    svg_root = generate_svg(draw_groups, travel_segs, paper_w, paper_h, args.scale)

    out_path = args.output
    if out_path is None:
        stem = os.path.splitext(os.path.basename(args.gcode))[0]
        svg_dir = os.path.join(os.path.dirname(os.path.abspath(args.gcode)),
                               "..", "svg")
        out_path = os.path.normpath(os.path.join(svg_dir, stem + "_tst.svg"))

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    tree = ET.ElementTree(svg_root)
    ET.indent(tree, space="  ")
    tree.write(out_path, encoding="unicode", xml_declaration=False)
    print(f"  -> {out_path}")


if __name__ == "__main__":
    main()
