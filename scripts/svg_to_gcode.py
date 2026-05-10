#!/usr/bin/env python3
"""svg_to_gcode.py – Convert a renderer SVG to G-code for a pen plotter.

Current capabilities
--------------------
  - Reads <line> elements from the SVG (linear moves only).
  - Scales the drawing to fit a configurable paper size with an edge margin,
    preserving aspect ratio and centering the drawing.
  - Maps SVG coordinates (Y-down) to plotter coordinates (Y-up by default).
  - Generates G-code with a configurable pen-down servo ramp and pen-up command.

Planned (not yet implemented)
------------------------------
  - Bezier curve interpolation (<path> elements).
  - Travel optimisation: sort lines by closest next endpoint, reverse line
    direction when beneficial, suppress pen up/down for connected lines.

Usage
-----
    python scripts/svg_to_gcode.py svg/postcard_menger.svg
    python scripts/svg_to_gcode.py svg/postcard_menger.svg --config gcode_config.json
    python scripts/svg_to_gcode.py svg/postcard_menger.svg -o output/menger.gcode

Config JSON keys (all optional – built-in defaults used for missing keys)
-------------------------------------------------------------------------
    feed_rate       (int)   : G1 feed rate in mm/min           [3000]
    pen_up_cmd      (str)   : G-code command to lift the pen   ["M5"]
    pen_down_steps  (int)   : servo ramp step count            [5]
    pen_down_start  (int)   : servo PWM value at ramp start    [10]
    pen_down_end    (int)   : servo PWM value at ramp end      [30]
    pen_down_dwell  (float) : dwell between ramp steps (s)     [0.1]
    paper_width_mm  (float) : plotter paper width in mm        [210.0]
    paper_height_mm (float) : plotter paper height in mm       [297.0]
    margin_mm       (float) : blank border around drawing (mm) [10.0]
    flip_y          (bool)  : flip Y axis (SVG Y-down ->        [true]
                              plotter Y-up)
"""

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict = {
    "feed_rate":       3000,
    "pen_up_cmd":      "M5",
    "pen_down_steps":  5,
    "pen_down_start":  10,
    "pen_down_end":    30,
    "pen_down_dwell":  0.1,
    "paper_width_mm":  105.0,
    "paper_height_mm": 148.0,
    "margin_mm":       10.0,
    "flip_y":          True,
}


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config(path: str | None) -> dict:
    """Load JSON config and merge over defaults. Unknown keys are kept."""
    cfg = dict(DEFAULT_CONFIG)
    if path:
        with open(path) as f:
            cfg.update(json.load(f))
    return cfg


# ---------------------------------------------------------------------------
# SVG parsing
# ---------------------------------------------------------------------------

def parse_svg(path: str) -> list[tuple[float, float, float, float]]:
    """Return a list of (x1, y1, x2, y2) tuples in SVG pixel units."""
    tree = ET.parse(path)
    root = tree.getroot()

    lines: list[tuple[float, float, float, float]] = []
    for elem in root.iter():
        tag = elem.tag.split("}")[-1]   # strip XML namespace prefix if present
        if tag == "line":
            x1 = float(elem.attrib.get("x1", 0))
            y1 = float(elem.attrib.get("y1", 0))
            x2 = float(elem.attrib.get("x2", 0))
            y2 = float(elem.attrib.get("y2", 0))
            if (x1, y1) != (x2, y2):   # skip zero-length
                lines.append((x1, y1, x2, y2))

    return lines


def scene_bbox(lines: list[tuple[float, float, float, float]]
               ) -> tuple[float, float, float, float]:
    """Return (min_x, min_y, max_x, max_y) of all line endpoints."""
    xs = [x for x1, y1, x2, y2 in lines for x in (x1, x2)]
    ys = [y for x1, y1, x2, y2 in lines for y in (y1, y2)]
    return min(xs), min(ys), max(xs), max(ys)


# ---------------------------------------------------------------------------
# Coordinate transform
# ---------------------------------------------------------------------------

def compute_transform(bbox: tuple[float, float, float, float],
                      cfg: dict) -> tuple[float, float, float, float]:
    """Compute (scale, x_off, y_off, bbox_h).

    Scales the drawing bounding box uniformly to fit inside the printable
    area (paper minus margin) and centres it on the paper.

    Plotter coordinate system: origin bottom-left, Y up.
    SVG coordinate system:     origin top-left,    Y down.

    Returns scale and offsets so that a point (x, y) in SVG space maps to
    plotter space via ``to_plotter``.
    """
    bx0, by0, bx1, by1 = bbox
    draw_w = bx1 - bx0
    draw_h = by1 - by0

    margin      = cfg["margin_mm"]
    paper_w     = cfg["paper_width_mm"]
    paper_h     = cfg["paper_height_mm"]
    printable_w = paper_w  - 2.0 * margin
    printable_h = paper_h  - 2.0 * margin

    scale  = min(printable_w / draw_w, printable_h / draw_h)

    # centre the scaled drawing on the printable area
    x_off  = margin + (printable_w - draw_w * scale) / 2.0 - bx0 * scale
    y_off  = margin + (printable_h - draw_h * scale) / 2.0 - by0 * scale

    return scale, x_off, y_off, draw_h


def to_plotter(x_svg: float, y_svg: float,
               scale: float, x_off: float, y_off: float,
               draw_h: float, flip_y: bool) -> tuple[float, float]:
    x = x_off + x_svg * scale
    # flip_y: SVG y=by0 (top of drawing) -> plotter top; SVG y grows down
    y = (y_off + (draw_h - (y_svg)) * scale) if flip_y else (y_off + y_svg * scale)
    return round(x, 4), round(y, 4)


# ---------------------------------------------------------------------------
# Pen-down ramp
# ---------------------------------------------------------------------------

def pen_down_cmds(cfg: dict) -> list[str]:
    """Return G-code lines for the servo pen-down ramp.

    Ramps the servo PWM value from pen_down_start to pen_down_end over
    pen_down_steps steps, with a G4 dwell between each step.

    Example with defaults (steps=5, start=10, end=30, dwell=0.1):
        M3 S10 / G4 P0.1 / M3 S15 / G4 P0.1 / ... / M3 S30 / G4 P0.1
    """
    steps = max(int(cfg["pen_down_steps"]), 1)
    s0    = cfg["pen_down_start"]
    s1    = cfg["pen_down_end"]
    dwell = cfg["pen_down_dwell"]

    result: list[str] = []
    for i in range(steps):
        t  = i / max(steps - 1, 1)
        sv = int(round(s0 + (s1 - s0) * t))
        result.append(f"M3 S{sv}")
        result.append(f"G4 P{dwell}")
    return result


# ---------------------------------------------------------------------------
# G-code generation
# ---------------------------------------------------------------------------

def generate_gcode(svg_lines: list[tuple[float, float, float, float]],
                   cfg: dict) -> list[str]:
    feed    = int(cfg["feed_rate"])
    pen_up  = cfg["pen_up_cmd"].strip()
    flip_y  = bool(cfg["flip_y"])
    margin  = cfg["margin_mm"]

    bbox = scene_bbox(svg_lines)
    bx0, by0, bx1, by1 = bbox
    scale, x_off, y_off, draw_h = compute_transform(bbox, cfg)

    def pt(x_svg: float, y_svg: float) -> tuple[float, float]:
        return to_plotter(x_svg, y_svg, scale, x_off, y_off, draw_h, flip_y)

    down = pen_down_cmds(cfg)

    out: list[str] = []

    # --- preamble ---
    out.append("; Generated by scripts/svg_to_gcode.py")
    out.append(f"; Drawing bbox: ({bx0:.2f},{by0:.2f}) - ({bx1:.2f},{by1:.2f}) px"
               f"  ({len(svg_lines)} segments)")
    out.append(f"; Paper:  {cfg['paper_width_mm']} x {cfg['paper_height_mm']} mm"
               f"  margin: {margin} mm")
    out.append(f"; Scale:  {scale:.6f} px->mm")
    out.append("G21          ; units: mm")
    out.append("G90          ; absolute positioning")
    out.append(pen_up)
    out.append("G0 X0 Y0     ; move to home")

    # --- line segments ---
    for x1, y1, x2, y2 in svg_lines:
        px1, py1 = pt(x1, y1)
        px2, py2 = pt(x2, y2)

        out.append(pen_up)
        out.append(f"G0 X{px1} Y{py1}")
        out.extend(down)
        out.append(f"G1 X{px2} Y{py2} F{feed}")

    # --- footer ---
    out.append(pen_up)
    out.append("G0 X0 Y0     ; return to home")

    return out


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert an SVG line-art file to G-code for a pen plotter.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("svg", nargs="?", default=None,
                        help="Input SVG file.  Omit to convert all files in svg/.")
    parser.add_argument("--config", "-c", default=None,
                        help="JSON config file.  Defaults: looks for "
                             "gcode_config.json next to the SVG, then uses "
                             "built-in defaults.")
    parser.add_argument("--output", "-o", default=None,
                        help="Output .gcode path.  Default: gcode/<stem>.gcode.")
    args = parser.parse_args()

    # Build list of SVGs to process
    if args.svg is None:
        svg_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "svg")
        svg_files = sorted(
            os.path.join(svg_dir, f)
            for f in os.listdir(svg_dir)
            if f.lower().endswith(".svg")
        )
        if not svg_files:
            print(f"No SVG files found in {svg_dir}", file=sys.stderr)
            sys.exit(1)
        if args.output is not None:
            print("Error: --output cannot be used when converting all SVGs.", file=sys.stderr)
            sys.exit(1)
    else:
        svg_files = [args.svg]

    for svg_path in svg_files:
        # Config resolution: explicit > gcode_config.json beside SVG > built-ins
        cfg_path = args.config
        if cfg_path is None:
            candidate = os.path.join(os.path.dirname(os.path.abspath(svg_path)),
                                     "gcode_config.json")
            if os.path.isfile(candidate):
                cfg_path = candidate

        cfg = load_config(cfg_path)

        if not os.path.isfile(svg_path):
            print(f"Error: SVG file not found: {svg_path}", file=sys.stderr)
            sys.exit(1)

        svg_lines = parse_svg(svg_path)
        bbox = scene_bbox(svg_lines)
        print(f"{os.path.basename(svg_path)}: {len(svg_lines)} segment(s)  "
              f"bbox ({bbox[0]:.1f},{bbox[1]:.1f})-({bbox[2]:.1f},{bbox[3]:.1f})")

        gcode = generate_gcode(svg_lines, cfg)

        out_path = args.output
        if out_path is None:
            stem = os.path.splitext(os.path.basename(svg_path))[0]
            gcode_dir = os.path.join(os.path.dirname(os.path.abspath(svg_path)),
                                     "..", "gcode")
            out_path = os.path.normpath(os.path.join(gcode_dir, stem + ".gcode"))

        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(gcode) + "\n")

        print(f"  -> {out_path}  ({len(gcode)} lines)")
        out_path = None  # reset for next file


if __name__ == "__main__":
    main()
