#!/usr/bin/env python3
"""svg_to_gcode.py – Convert a renderer SVG to G-code for a pen plotter.

Current capabilities
--------------------
  - Reads <line> elements from the SVG (linear moves only).
  - Scales the drawing to fit a configurable paper size with an edge margin,
    preserving aspect ratio and centering the drawing.
  - Maps SVG coordinates (Y-down) to plotter coordinates (Y-up by default).
  - Generates G-code with a configurable pen-down servo ramp and pen-up command.
  - Travel optimisation: sort segments by closest next endpoint, optionally
    reverse segment direction, suppress pen up/down for connected endpoints.
  - Filters out segments shorter than a configurable minimum length (mm).

Planned (not yet implemented)
------------------------------
  - Bezier curve interpolation (<path> elements).

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
    min_segment_mm  (float) : discard segments shorter than this  [0.1]
                              value in plotter mm
    connect_epsilon (float) : max gap between endpoints to consider [0.5]
                              connected, in plotter mm
"""

import argparse
from collections import deque
import math
import json
import os
import re
import sys
import xml.etree.ElementTree as ET


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict = {
    "feed_rate":        3000,
    "rapid_rate":       6000,
    "pen_up_cmd":       "M5",
    "pen_down_steps":   5,
    "pen_down_start":   10,
    "pen_down_end":     30,
    "pen_down_dwell":   0.1,
    "paper_width_mm":   105.0,
    "paper_height_mm":  148.0,
    "margin_mm":        10.0,
    "flip_y":           True,
    "optimize_sort":    False,
    "optimize_connect": False,
    "optimize_reverse": False,
    "connect_epsilon":  0.5,
    "min_segment_mm":   0.1,
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

def parse_svg(path: str) -> list[list[tuple[float, float, float, float]]]:
    """Return a list of chains; each chain is a list of (x1, y1, x2, y2) segments.

    Each <line> element produces a 1-segment chain.
    Each <path> element produces one chain containing all its M/L segments.
    Unsupported path commands (C, Q, A, …) are skipped with a warning.
    """
    tree = ET.parse(path)
    root = tree.getroot()

    # Tokeniser for path d-attribute: command letters and numbers.
    _PATH_TOKEN = re.compile(
        r'([MmLlHhVvZz])|'
        r'([-+]?(?:[0-9]*\.[0-9]+|[0-9]+)(?:[eE][-+]?[0-9]+)?)'
    )
    _UNSUPPORTED = re.compile(r'[CcQqAaSsTt]')

    def _path_segments(d: str) -> list[tuple[float, float, float, float]]:
        if _UNSUPPORTED.search(d):
            print(f"  warning: skipping path with unsupported commands "
                  f"({_UNSUPPORTED.search(d).group()})", file=sys.stderr)
            return []
        segs: list[tuple[float, float, float, float]] = []
        tokens = [m.group() for m in _PATH_TOKEN.finditer(d)]
        cx = cy = 0.0
        i = 0
        while i < len(tokens):
            cmd = tokens[i]
            if cmd in ('M', 'm'):
                i += 1
                x = float(tokens[i]); i += 1
                y = float(tokens[i]); i += 1
                cx, cy = (x, y) if cmd == 'M' else (cx + x, cy + y)
                # Subsequent coordinate pairs after M are implicit L
                while i < len(tokens) and tokens[i] not in 'MmLlHhVvZzCcQqAaSsTt':
                    x = float(tokens[i]); i += 1
                    y = float(tokens[i]); i += 1
                    nx, ny = (x, y) if cmd == 'M' else (cx + x, cy + y)
                    if (cx, cy) != (nx, ny):
                        segs.append((cx, cy, nx, ny))
                    cx, cy = nx, ny
            elif cmd in ('L', 'l'):
                i += 1
                x = float(tokens[i]); i += 1
                y = float(tokens[i]); i += 1
                nx, ny = (x, y) if cmd == 'L' else (cx + x, cy + y)
                if (cx, cy) != (nx, ny):
                    segs.append((cx, cy, nx, ny))
                cx, cy = nx, ny
            elif cmd in ('H', 'h'):
                i += 1
                x = float(tokens[i]); i += 1
                nx = x if cmd == 'H' else cx + x
                if cx != nx:
                    segs.append((cx, cy, nx, cy))
                cx = nx
            elif cmd in ('V', 'v'):
                i += 1
                y = float(tokens[i]); i += 1
                ny = y if cmd == 'V' else cy + y
                if cy != ny:
                    segs.append((cx, cy, cx, ny))
                cy = ny
            elif cmd in ('Z', 'z'):
                i += 1  # close path – no segment needed for pen plotter
            else:
                i += 1
        return segs

    chains: list[list[tuple[float, float, float, float]]] = []
    for elem in root.iter():
        tag = elem.tag.split("}")[-1]   # strip XML namespace prefix if present
        if tag == "line":
            x1 = float(elem.attrib.get("x1", 0))
            y1 = float(elem.attrib.get("y1", 0))
            x2 = float(elem.attrib.get("x2", 0))
            y2 = float(elem.attrib.get("y2", 0))
            if (x1, y1) != (x2, y2):   # skip zero-length
                chains.append([(x1, y1, x2, y2)])
        elif tag == "path":
            d = elem.attrib.get("d", "").strip()
            if d:
                segs = _path_segments(d)
                if segs:
                    chains.append(segs)

    return chains


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
                      cfg: dict) -> tuple[float, float, float, float, float]:
    """Compute (scale, x_off, y_off, svg_y0, svg_y1).

    Scales the drawing bounding box uniformly to fit inside the printable
    area (paper minus margin) and centres it on the paper.

    Plotter coordinate system: origin bottom-left, Y up.
    SVG coordinate system:     origin top-left,    Y down.

    Returns scale and offsets so that a point (x, y) in SVG space maps to
    plotter space via ``to_plotter``.  svg_y0/svg_y1 are the raw SVG bbox
    min/max Y values needed for the correct flip-Y centring formula.
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

    return scale, x_off, y_off, by0, by1


def to_plotter(x_svg: float, y_svg: float,
               scale: float, x_off: float, y_off: float,
               svg_y0: float, svg_y1: float, flip_y: bool) -> tuple[float, float]:
    x = x_off + x_svg * scale
    # flip_y: SVG y_min -> plotter top, SVG y_max -> plotter bottom.
    # Correct centring: reflect around the bbox mid-point (svg_y0 + svg_y1).
    y = (y_off + (svg_y0 + svg_y1 - y_svg) * scale) if flip_y else (y_off + y_svg * scale)
    return round(x, 4), round(y, 4)


def transform_lines(
    lines: list[tuple[float, float, float, float]],
    scale: float, x_off: float, y_off: float,
    svg_y0: float, svg_y1: float, flip_y: bool,
) -> list[tuple[float, float, float, float]]:
    """Convert SVG-space lines to plotter mm coordinates in one pass."""
    result = []
    for x1, y1, x2, y2 in lines:
        px1, py1 = to_plotter(x1, y1, scale, x_off, y_off, svg_y0, svg_y1, flip_y)
        px2, py2 = to_plotter(x2, y2, scale, x_off, y_off, svg_y0, svg_y1, flip_y)
        result.append((px1, py1, px2, py2))
    return result


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
# Path optimisation
# ---------------------------------------------------------------------------

def _dist2(ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = ax - bx, ay - by
    return dx * dx + dy * dy


def _unit(x1: float, y1: float, x2: float, y2: float) -> tuple[float, float]:
    """Unit direction vector from (x1,y1) to (x2,y2).

    Returns (0, 0) for degenerate (zero-length) input so that dot-product
    scoring treats the direction as unknown rather than biasing toward (1, 0).
    """
    dx, dy = x2 - x1, y2 - y1
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-12:
        return 0.0, 0.0
    return dx / length, dy / length


def optimize_lines(
    lines: list[tuple[float, float, float, float]],
    epsilon: float,
) -> tuple[list[tuple[float, float, float, float]], int, int]:
    """Three-phase optimiser.

    Phase 1 – Collinear chain building:
        For each unused segment, greedily extend the chain by finding connected
        segments (within *epsilon*) whose direction matches the current chain
        direction (dot product >= DIR_THRESHOLD).  Produces straight-run chains.

    Phase 2 – Chain junction:
        Connect Phase-1 chains to each other wherever their endpoints meet
        within *epsilon*, regardless of direction.  Handles corners and
        direction changes between straight runs.

    Phase 3 – Chain ordering:
        Order the resulting super-chains with a nearest-neighbour greedy walk
        from the origin, optionally reversing whole chains to minimise travel.

    Returns (ordered_lines, n_reversed, n_connected).
      - n_reversed:  number of individual segments that were flipped.
      - n_connected: number of connections where the pen stays down.
    """
    # Dot-product threshold for "same direction" in Phase 1 (~8 degrees).
    DIR_THRESHOLD = 0.99

    if not lines:
        return [], 0, 0

    eps2 = epsilon * epsilon
    n_segs = len(lines)
    n_reversed = 0
    n_connected = 0

    # ---- Phase 1: collinear chain building (connected + same direction) ----
    used = [False] * n_segs
    seg_chains: list[list[tuple[float, float, float, float]]] = []

    for start_idx in range(n_segs):
        if used[start_idx]:
            continue

        used[start_idx] = True
        chain: deque[tuple[float, float, float, float]] = deque([lines[start_idx]])

        extended = True
        while extended:
            extended = False

            # --- extend tail ---
            cx, cy = chain[-1][2], chain[-1][3]
            cdx, cdy = _unit(chain[-1][0], chain[-1][1], cx, cy)
            best_score = -2.0
            best_li    = -1
            best_rev   = False
            for li in range(n_segs):
                if used[li]:
                    continue
                x1, y1, x2, y2 = lines[li]
                if _dist2(cx, cy, x1, y1) <= eps2:
                    dx, dy = _unit(x1, y1, x2, y2)
                    score = dx * cdx + dy * cdy
                    if score >= DIR_THRESHOLD and score > best_score:
                        best_score, best_li, best_rev = score, li, False
                if _dist2(cx, cy, x2, y2) <= eps2:
                    dx, dy = _unit(x2, y2, x1, y1)
                    score = dx * cdx + dy * cdy
                    if score >= DIR_THRESHOLD and score > best_score:
                        best_score, best_li, best_rev = score, li, True
            if best_li != -1:
                used[best_li] = True
                x1, y1, x2, y2 = lines[best_li]
                if best_rev:
                    chain.append((x2, y2, x1, y1))
                    n_reversed += 1
                else:
                    chain.append((x1, y1, x2, y2))
                n_connected += 1
                extended = True

            # --- extend head ---
            hx, hy = chain[0][0], chain[0][1]
            hdx, hdy = _unit(chain[0][0], chain[0][1], chain[0][2], chain[0][3])
            best_score = -2.0
            best_li    = -1
            best_rev   = False
            for li in range(n_segs):
                if used[li]:
                    continue
                x1, y1, x2, y2 = lines[li]
                # segment end attaches to head → prepend forward
                if _dist2(hx, hy, x2, y2) <= eps2:
                    dx, dy = _unit(x1, y1, x2, y2)
                    score = dx * hdx + dy * hdy
                    if score >= DIR_THRESHOLD and score > best_score:
                        best_score, best_li, best_rev = score, li, False
                # segment start attaches to head → prepend reversed
                if _dist2(hx, hy, x1, y1) <= eps2:
                    dx, dy = _unit(x2, y2, x1, y1)
                    score = dx * hdx + dy * hdy
                    if score >= DIR_THRESHOLD and score > best_score:
                        best_score, best_li, best_rev = score, li, True
            if best_li != -1:
                used[best_li] = True
                x1, y1, x2, y2 = lines[best_li]
                if best_rev:
                    chain.appendleft((x2, y2, x1, y1))
                    n_reversed += 1
                else:
                    chain.appendleft((x1, y1, x2, y2))
                n_connected += 1
                extended = True

        seg_chains.append(list(chain))

    # ---- Phase 2: chain junction (connected, any direction) ----
    n_chains = len(seg_chains)
    chain_used = [False] * n_chains
    super_chains: list[list[tuple[float, float, float, float]]] = []

    for start_ci in range(n_chains):
        if chain_used[start_ci]:
            continue

        chain_used[start_ci] = True
        super_segs: list[tuple[float, float, float, float]] = list(seg_chains[start_ci])

        while True:
            cx, cy = super_segs[-1][2], super_segs[-1][3]

            best_d2  = float("inf")
            best_ci  = -1
            best_rev = False

            for ci in range(n_chains):
                if chain_used[ci]:
                    continue
                sx, sy = seg_chains[ci][0][0],  seg_chains[ci][0][1]
                ex, ey = seg_chains[ci][-1][2], seg_chains[ci][-1][3]

                d_fwd = _dist2(cx, cy, sx, sy)
                if d_fwd <= eps2 and d_fwd < best_d2:
                    best_d2, best_ci, best_rev = d_fwd, ci, False

                d_rev = _dist2(cx, cy, ex, ey)
                if d_rev <= eps2 and d_rev < best_d2:
                    best_d2, best_ci, best_rev = d_rev, ci, True

            if best_ci == -1:
                break

            chain_used[best_ci] = True
            if best_rev:
                flipped = [(x2, y2, x1, y1)
                           for x1, y1, x2, y2 in reversed(seg_chains[best_ci])]
                super_segs.extend(flipped)
                n_reversed += len(seg_chains[best_ci])
            else:
                super_segs.extend(seg_chains[best_ci])
            n_connected += 1   # one new junction per attached chain

        super_chains.append(super_segs)

    # ---- Phase 3: order super-chains by nearest-neighbour from origin ----
    remaining = list(range(len(super_chains)))
    ordered: list[tuple[float, float, float, float]] = []
    cur_x, cur_y = 0.0, 0.0

    while remaining:
        best_ri   = 0
        best_d2   = float("inf")
        best_flip = False

        for ri, ci in enumerate(remaining):
            sx, sy = super_chains[ci][0][0],  super_chains[ci][0][1]
            ex, ey = super_chains[ci][-1][2], super_chains[ci][-1][3]

            d_fwd = _dist2(cur_x, cur_y, sx, sy)
            if d_fwd < best_d2:
                best_d2, best_ri, best_flip = d_fwd, ri, False

            d_rev = _dist2(cur_x, cur_y, ex, ey)
            if d_rev < best_d2:
                best_d2, best_ri, best_flip = d_rev, ri, True

        ci    = remaining.pop(best_ri)
        chain = super_chains[ci]

        if best_flip:
            chain = [(x2, y2, x1, y1) for x1, y1, x2, y2 in reversed(chain)]
            n_reversed += len(chain)

        ordered.extend(chain)
        cur_x, cur_y = ordered[-1][2], ordered[-1][3]

    return ordered, n_reversed, n_connected


# ---------------------------------------------------------------------------
# Fast chain-level nearest-neighbour sort
# ---------------------------------------------------------------------------

def _sort_chains_nn(
    chains: list[list[tuple[float, float, float, float]]],
    allow_reverse: bool,
) -> tuple[list[list[tuple[float, float, float, float]]], int]:
    """Nearest-neighbour greedy sort of chains.

    Picks the chain whose nearest endpoint is closest to the current pen
    position.  Optionally flips the chain so its far end becomes the start.

    Operates on *chains* (O(n_chains²)), not individual segments, making it
    fast even for large drawings made of a moderate number of long paths.

    Returns (sorted_chains, n_chains_reversed).
    """
    remaining = list(range(len(chains)))
    result: list[list[tuple[float, float, float, float]]] = []
    n_rev = 0
    cx, cy = 0.0, 0.0

    while remaining:
        best_ri, best_d2, best_flip = 0, float("inf"), False
        for ri, ci in enumerate(remaining):
            c = chains[ci]
            sx, sy = c[0][0],  c[0][1]
            ex, ey = c[-1][2], c[-1][3]
            d_fwd = _dist2(cx, cy, sx, sy)
            if d_fwd < best_d2:
                best_d2, best_ri, best_flip = d_fwd, ri, False
            if allow_reverse:
                d_rev = _dist2(cx, cy, ex, ey)
                if d_rev < best_d2:
                    best_d2, best_ri, best_flip = d_rev, ri, True

        ci = remaining.pop(best_ri)
        chain = chains[ci]
        if best_flip:
            chain = [(x2, y2, x1, y1) for x1, y1, x2, y2 in reversed(chain)]
            n_rev += 1
        result.append(chain)
        cx, cy = result[-1][-1][2], result[-1][-1][3]

    return result, n_rev


# ---------------------------------------------------------------------------
# Short-segment filter
# ---------------------------------------------------------------------------

def filter_short_chains(
    lines: list[tuple[float, float, float, float]],
    scale: float,
    min_mm: float,
    eps_svg: float,
) -> tuple[list[tuple[float, float, float, float]], int]:
    """Remove connected chains whose total plotter-space length is below *min_mm*.

    Consecutive segments that share an endpoint within *eps_svg* are treated
    as a single chain.  The entire chain is kept or discarded based on its
    cumulative length – individual short segments inside a longer chain are
    never removed.

    Returns (filtered_lines, n_removed).
    """
    if min_mm <= 0 or not lines:
        return lines, 0

    eps2 = eps_svg * eps_svg
    min_svg = min_mm / scale

    # Group consecutive segments into chains by shared endpoint proximity.
    chains: list[list[tuple[float, float, float, float]]] = []
    current: list[tuple[float, float, float, float]] = [lines[0]]
    for seg in lines[1:]:
        x1, y1 = seg[0], seg[1]
        px2, py2 = current[-1][2], current[-1][3]
        if _dist2(px2, py2, x1, y1) <= eps2:
            current.append(seg)
        else:
            chains.append(current)
            current = [seg]
    chains.append(current)

    # Keep chains whose total SVG-space length meets the threshold.
    result: list[tuple[float, float, float, float]] = []
    n_removed = 0
    for chain in chains:
        total = sum(math.sqrt(_dist2(x1, y1, x2, y2)) for x1, y1, x2, y2 in chain)
        if total >= min_svg:
            result.extend(chain)
        else:
            n_removed += len(chain)

    return result, n_removed


# ---------------------------------------------------------------------------
# G-code generation
# ---------------------------------------------------------------------------

def generate_gcode(svg_chains: list[list[tuple[float, float, float, float]]],
                   cfg: dict) -> list[str]:
    feed           = int(cfg["feed_rate"])
    rapid          = int(cfg.get("rapid_rate", feed))
    pen_up_cmd     = cfg["pen_up_cmd"].strip()
    flip_y         = bool(cfg["flip_y"])
    margin         = cfg["margin_mm"]
    do_sort        = bool(cfg.get("optimize_sort",    False))
    do_connect     = bool(cfg.get("optimize_connect", False))
    do_reverse     = bool(cfg.get("optimize_reverse", False))
    epsilon        = float(cfg.get("connect_epsilon", 0.5))
    min_seg        = float(cfg.get("min_segment_mm", 0.1))

    # Flatten all chains for bbox + transform computation
    svg_lines = [seg for chain in svg_chains for seg in chain]
    scale, x_off, y_off, svg_y0, svg_y1 = compute_transform(scene_bbox(svg_lines), cfg)

    # Transform each chain to plotter mm-space
    mm_chains: list[list[tuple[float, float, float, float]]] = [
        transform_lines(chain, scale, x_off, y_off, svg_y0, svg_y1, flip_y)
        for chain in svg_chains
    ]

    n_rev = n_conn = 0
    if do_connect:
        # Full 3-phase optimiser on the flat segment list
        flat = [seg for chain in mm_chains for seg in chain]
        flat, n_rev, n_conn = optimize_lines(flat, epsilon)
        mm_chains = [flat]
    elif do_sort:
        # Fast nearest-neighbour sort at chain level (O(n_chains²))
        mm_chains, n_rev = _sort_chains_nn(mm_chains, allow_reverse=do_reverse)

    # Flatten and filter short chains (scale=1.0 because lines are already in mm)
    mm_lines = [seg for chain in mm_chains for seg in chain]
    mm_lines, n_short = filter_short_chains(mm_lines, 1.0, min_seg, epsilon)

    bbox = scene_bbox(mm_lines)
    bx0, by0, bx1, by1 = bbox
    eps2 = epsilon * epsilon

    down = pen_down_cmds(cfg)

    out: list[str] = []

    # --- preamble ---
    out.append("; Generated by scripts/svg_to_gcode.py")
    out.append(f"; Drawing bbox: ({bx0:.2f},{by0:.2f}) - ({bx1:.2f},{by1:.2f}) mm"
               f"  ({len(mm_lines)} segments)")
    out.append(f"; Paper:  {cfg['paper_width_mm']} x {cfg['paper_height_mm']} mm"
               f"  margin: {margin} mm")
    out.append(f"; Scale:  {scale:.6f} px->mm")
    if n_short:
        out.append(f"; Short segments removed: {n_short} (< {min_seg} mm)")
    if do_connect:
        out.append(f"; Optimised: sort+connect  reversed={n_rev}  connected={n_conn}")
    elif do_sort:
        out.append(f"; Optimised: chain-sort  reversed={n_rev}")
    out.append("G21          ; units: mm")
    out.append("G90          ; absolute positioning")
    out.append(pen_up_cmd)
    out.append(f"G0 X0 Y0 F{rapid}     ; move to home")

    # --- line segments ---
    cur_x, cur_y = 0.0, 0.0   # current plotter position (mm)
    pen_down = False
    travel_up   = 0.0   # mm, pen lifted
    travel_down = 0.0   # mm, pen drawing
    n_lifts     = 0

    def _mm_dist(ax: float, ay: float, bx: float, by: float) -> float:
        return math.sqrt((bx - ax) ** 2 + (by - ay) ** 2)

    for x1, y1, x2, y2 in mm_lines:
        # Always suppress pen lift when the previous endpoint is within epsilon
        connected = _dist2(cur_x, cur_y, x1, y1) <= eps2

        if not connected:
            if pen_down:
                out.append(pen_up_cmd)
                pen_down = False
                n_lifts += 1
            travel_up += _mm_dist(cur_x, cur_y, x1, y1)
            out.append(f"G0 X{x1} Y{y1} F{rapid}")
            cur_x, cur_y = x1, y1

        if not pen_down:
            out.extend(down)
            pen_down = True

        out.append(f"G1 X{x2} Y{y2} F{feed}")
        travel_down += _mm_dist(cur_x, cur_y, x2, y2)
        cur_x, cur_y = x2, y2

    # --- footer ---
    out.append(pen_up_cmd)
    travel_up += _mm_dist(cur_x, cur_y, 0.0, 0.0)
    out.append(f"G0 X0 Y0 F{rapid}     ; return to home")

    # --- report ---
    draw_secs   = (travel_down / feed)  * 60.0
    travel_secs = (travel_up   / rapid) * 60.0
    dwell_secs  = n_lifts * cfg["pen_down_steps"] * cfg["pen_down_dwell"]
    total_secs  = draw_secs + travel_secs + dwell_secs

    def fmt_time(s: float) -> str:
        m, sec = divmod(int(s), 60)
        h, m   = divmod(m, 60)
        return f"{h}h {m:02d}m {sec:02d}s" if h else f"{m}m {sec:02d}s"

    out.append(f"; --- Travel report ---")
    out.append(f"; Pen-down travel : {travel_down:.1f} mm  @ {feed} mm/min  -> {fmt_time(draw_secs)}")
    out.append(f"; Pen-up travel   : {travel_up:.1f} mm  @ {rapid} mm/min  -> {fmt_time(travel_secs)}")
    out.append(f"; Pen lifts       : {n_lifts}  (dwell {fmt_time(dwell_secs)})")
    out.append(f"; Estimated total : {fmt_time(total_secs)}")

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
            # Look for gcode_config.json: beside the SVG, then in cwd
            for candidate_dir in [
                os.path.dirname(os.path.abspath(svg_path)),
                os.getcwd(),
            ]:
                candidate = os.path.join(candidate_dir, "gcode_config.json")
                if os.path.isfile(candidate):
                    cfg_path = candidate
                    break

        cfg = load_config(cfg_path)

        if not os.path.isfile(svg_path):
            print(f"Error: SVG file not found: {svg_path}", file=sys.stderr)
            sys.exit(1)

        svg_chains = parse_svg(svg_path)
        n_segs = sum(len(c) for c in svg_chains)
        flat_segs = [s for c in svg_chains for s in c]
        bbox = scene_bbox(flat_segs)
        print(f"{os.path.basename(svg_path)}: {len(svg_chains)} chain(s)  {n_segs} segment(s)  "
              f"bbox ({bbox[0]:.1f},{bbox[1]:.1f})-({bbox[2]:.1f},{bbox[3]:.1f})")

        gcode = generate_gcode(svg_chains, cfg)

        out_path = args.output
        if out_path is None:
            stem = os.path.splitext(os.path.basename(svg_path))[0]
            gcode_dir = os.path.join(os.path.dirname(os.path.abspath(svg_path)),
                                     "..", "gcode")
            out_path = os.path.normpath(os.path.join(gcode_dir, stem + ".gcode"))

        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(gcode) + "\n")

        # Extract report lines from end of gcode for console display
        report = [l.lstrip("; ") for l in gcode
                  if l.startswith("; Pen-") or l.startswith("; Pen lifts") or l.startswith("; Estimated")]
        print(f"  -> {out_path}  ({len(gcode)} lines)")
        for r in report:
            print(f"     {r}")
        out_path = None  # reset for next file


if __name__ == "__main__":
    main()
