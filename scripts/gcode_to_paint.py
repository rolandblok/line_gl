#!/usr/bin/env python3
"""gcode_to_paint.py – Insert paint-reload stops into pen-plotter G-code.

For brush-based plotters that need to periodically re-load paint.  Reads an
existing G-code file, tracks pen-down travel distance, and at the first
pen-up that follows exceeding the reload threshold inserts a detour to the
paint pot:

  1. Rapid to paint centre (pen already up from end of stroke).
  2. Pen down into paint (configurable servo ramp).
  3. Move to circle edge, draw one full clockwise circle (G2), return to centre.
  4. Pen up.
  5. Continue with the original G0 rapid to the next stroke start.

Reloads are never inserted mid-stroke; they always land on an existing pen-up
point so the drawing is never interrupted.

Usage
-----
    python scripts/gcode_to_paint.py gcode/postcard_menger.gcode
    python scripts/gcode_to_paint.py gcode/postcard_menger.gcode --config gcode_paint.json
    python scripts/gcode_to_paint.py gcode/postcard_menger.gcode -o gcode/menger_paint.gcode

Config JSON keys  (all optional – built-in defaults used for missing keys)
--------------------------------------------------------------------------
    paint_x          (float) : paint pot X position in mm              [250.0]
    paint_y          (float) : paint pot Y position in mm              [10.0]
    paint_radius     (float) : radius of circle drawn in paint (mm)    [5.0]
    paint_distance_mm (float): pen-down travel before reload (mm)      [500.0]
    paint_feed       (int)   : feed rate for circle moves (mm/min)     [1000]
    paint_speed      (int)   : replaces the F value on all G1 drawing   [null]
                               moves in the source gcode; null = keep
                               original speed
    rapid_rate       (int)   : rapid rate for travel to/from paint     [6000]
    input_pen_up_cmd (str)   : G-code command to lift the pen          ["M5"]
    paint_pen_up_cmd (str)   : pen-up command used inside the reload   ["M5"]
                               block (may differ from input_pen_up_cmd)
    paint_dip_steps  (int)   : servo ramp step count for paint dip     [3]
    paint_dip_start  (int)   : servo PWM value at ramp start           [25]
    paint_dip_end    (int)   : servo PWM value at ramp end             [35]
    paint_dip_dwell  (float) : dwell between ramp steps (s)            [0.1]
    preferred_direction ([x,y]): normalize all strokes to this direction; [null]
                               strokes whose net direction has a negative
                               dot product with this vector are reversed.
                               null = disabled  example: [1, 0]
"""

import argparse
import json
import math
import os
import re
import sys


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict = {
    "paint_x":            250.0,
    "paint_y":            10.0,
    "paint_radius":       5.0,
    "paint_distance_mm":  500.0,
    "paint_feed":         1000,
    "paint_speed":        None,
    "rapid_rate":         6000,
    "input_pen_up_cmd":    "M5",
    "paint_pen_up_cmd":   "M5",
    "paint_dip_steps":    3,
    "paint_dip_start":    25,
    "paint_dip_end":      35,
    "paint_dip_dwell":    0.1,
    "preferred_direction": None,
}


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config(path: str | None) -> dict:
    """Load JSON config and merge over defaults."""
    cfg = dict(DEFAULT_CONFIG)
    if path:
        with open(path) as f:
            cfg.update(json.load(f))
    return cfg


# ---------------------------------------------------------------------------
# Paint-reload G-code block
# ---------------------------------------------------------------------------

def _paint_dip_cmds(cfg: dict) -> list[str]:
    """Servo ramp to press the brush into paint."""
    steps = max(int(cfg["paint_dip_steps"]), 1)
    s0    = cfg["paint_dip_start"]
    s1    = cfg["paint_dip_end"]
    dwell = cfg["paint_dip_dwell"]
    result: list[str] = []
    for i in range(steps):
        t  = i / max(steps - 1, 1)
        sv = int(round(s0 + (s1 - s0) * t))
        result.append(f"M3 S{sv}")
        result.append(f"G4 P{dwell}")
    return result


def _build_reload_block(cfg: dict) -> list[str]:
    """Return G-code lines for one complete paint reload.

    Sequence:
      - Rapid to paint centre  (pen is already up)
      - Pen down (servo ramp)
      - G1 to circle edge
      - G2 full clockwise circle (start == end == edge point)
      - G1 return to centre
      - Pen up
    """
    px    = cfg["paint_x"]
    py    = cfg["paint_y"]
    r     = cfg["paint_radius"]
    feed  = int(cfg["paint_feed"])
    rapid = int(cfg["rapid_rate"])
    pu    = cfg.get("paint_pen_up_cmd", cfg["input_pen_up_cmd"]).strip()

    edge_x = px + r   # circle edge: right of centre

    lines: list[str] = [
        "; --- paint reload ---",
        f"G0 X{px:.4f} Y{py:.4f} F{rapid}",              # rapid to centre
    ]
    lines.extend(_paint_dip_cmds(cfg))                   # pen down into paint
    lines.append(f"G1 X{edge_x:.4f} Y{py:.4f} F{feed}") # move to circle edge
    # G2 full circle: end == start, I = centre_x - start_x = -r, J = 0
    lines.append(f"G2 X{edge_x:.4f} Y{py:.4f} I{-r:.4f} J0 F{feed}")  # full CW circle
    lines.append(f"G1 X{px:.4f} Y{py:.4f} F{feed}")     # return to centre
    lines.append(f"{pu}")                                 # lift pen from paint
    lines.append("; --- end paint reload ---")
    return lines


# ---------------------------------------------------------------------------
# Stroke direction normalisation
# ---------------------------------------------------------------------------

def _normalize_stroke_directions(lines: list[str], cfg: dict) -> list[str]:
    """Pre-pass: reverse strokes whose net direction opposes preferred_direction.

    Each stroke (pen-down ramp → G1 moves → pen-up) is examined.  The net
    direction vector runs from the stroke's first point (G0 destination) to
    its last G1 endpoint.  If its dot product with preferred_direction is
    negative the G1 sequence is reversed and the preceding G0 travel target
    updated to the old stroke endpoint.  Strokes with no preceding G0
    (connected to previous stroke) are left unchanged.
    """
    pd = cfg.get("preferred_direction")
    if not pd:
        return list(lines)

    pd_x, pd_y = float(pd[0]), float(pd[1])
    pu_upper   = cfg["input_pen_up_cmd"].strip().upper()

    def _is_pu(s: str) -> bool:
        u = s.strip().upper()
        if not u.startswith(pu_upper):
            return False
        rest = u[len(pu_upper):]
        return not rest or rest[0] in ' \t;'

    out:         list[str]                    = []
    pending_g0:  str | None                   = None   # G0 line before stroke
    pendown_buf: list[str]                    = []     # M3/G4 ramp lines
    g1_lines:    list[str]                    = []     # G1 draw lines
    g1_pts:      list[tuple[float, float]]    = []     # G1 endpoints
    stroke_start: tuple[float, float] | None  = None   # position at pen-down
    cur_x = cur_y = 0.0
    in_ramp = False

    for raw in lines:
        line = raw.rstrip('\n').rstrip('\r')
        toks = line.strip().upper().split()
        fw   = toks[0] if toks else ""

        # ---- pen-up: finalise stroke, possibly reversed ----
        if _is_pu(line):
            if g1_pts and stroke_start is not None and pending_g0 is not None:
                dx  = g1_pts[-1][0] - stroke_start[0]
                dy  = g1_pts[-1][1] - stroke_start[1]
                dot = dx * pd_x + dy * pd_y
                if dot < 0:
                    all_pts = [stroke_start] + g1_pts
                    out.append(_replace_xy(pending_g0, g1_pts[-1][0], g1_pts[-1][1]))
                    out.extend(pendown_buf)
                    for i, orig in enumerate(reversed(g1_lines)):
                        tgt = all_pts[len(all_pts) - 2 - i]
                        out.append(_replace_xy(orig, tgt[0], tgt[1]))
                    cur_x, cur_y = stroke_start
                    out.append(line)
                    pending_g0 = None; pendown_buf = []; g1_lines = []; g1_pts = []
                    stroke_start = None; in_ramp = False
                    continue
            # no reversal
            if pending_g0 is not None:
                out.append(pending_g0)
                pending_g0 = None
            out.extend(pendown_buf)
            out.extend(g1_lines)
            out.append(line)
            pendown_buf = []; g1_lines = []; g1_pts = []; stroke_start = None; in_ramp = False
            continue

        if fw == "G0":
            if pending_g0 is not None:   # flush previous uncommitted G0
                out.append(pending_g0)
            pending_g0 = line
            nx, ny = _extract_xy(line)
            cur_x = nx if nx is not None else cur_x
            cur_y = ny if ny is not None else cur_y
            continue

        if fw == "M3" and not _is_pu(line):
            stroke_start = (cur_x, cur_y)
            pendown_buf  = [line]
            g1_lines     = []
            g1_pts       = []
            in_ramp      = True
            continue

        if in_ramp and fw == "G4":
            pendown_buf.append(line)
            continue

        if fw == "G1":
            in_ramp = False
            nx, ny  = _extract_xy(line)
            if nx is None: nx = cur_x
            if ny is None: ny = cur_y
            g1_lines.append(line)
            g1_pts.append((nx, ny))
            cur_x, cur_y = nx, ny
            continue

        # misc lines (comments, G21, G90, …)
        if pendown_buf or g1_lines:
            pendown_buf.append(line)   # buffer mid-stroke misc lines
        elif pending_g0 is not None:
            out.append(pending_g0)
            pending_g0 = None
            out.append(line)
        else:
            out.append(line)

    # flush any trailing buffered content
    if pending_g0 is not None:
        out.append(pending_g0)
    out.extend(pendown_buf)
    out.extend(g1_lines)
    return out


# ---------------------------------------------------------------------------
# G-code processing
# ---------------------------------------------------------------------------

_COORD_RE    = re.compile(r'([XY])([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)')
_F_RE        = re.compile(r'\bF[\d.]+', re.IGNORECASE)
_XY_REPLACE  = re.compile(r'([XY])([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)', re.IGNORECASE)


def _extract_xy(line: str) -> tuple[float | None, float | None]:
    """Return (x, y) extracted from a G0/G1 line; None for absent axes."""
    coords = {m.group(1): float(m.group(2)) for m in _COORD_RE.finditer(line.upper())}
    return coords.get('X'), coords.get('Y')


def _replace_xy(line: str, x: float, y: float) -> str:
    """Return line with X and Y coordinate values replaced."""
    def _sub(m: re.Match) -> str:
        return f'X{x:.4f}' if m.group(1).upper() == 'X' else f'Y{y:.4f}'
    return _XY_REPLACE.sub(_sub, line)


def process_gcode(
    lines: list[str],
    cfg: dict,
) -> tuple[list[str], int, float]:
    """Scan gcode and insert paint reloads at pen-up points.

    Distance is accumulated only for G1 moves while the pen is down.
    When it exceeds cfg["paint_distance_mm"] a reload flag is set; the
    reload block is injected immediately after the *next* pen-up command so
    strokes are never cut mid-line.

    Pen-up is matched by a full-string prefix of input_pen_up_cmd (e.g. "M3 S20"
    or "M5").  Any other M3 command is treated as transitioning to pen-down.

    Returns (output_lines, n_reloads, total_pen_down_mm).
    """
    lines = _normalize_stroke_directions(lines, cfg)
    pu_cmd       = cfg["input_pen_up_cmd"].strip().upper()
    paint_pu_out = cfg.get("paint_pen_up_cmd", cfg["input_pen_up_cmd"]).strip()
    paint_dist   = float(cfg["paint_distance_mm"])
    paint_speed  = cfg.get("paint_speed")
    if paint_speed is not None:
        paint_speed = int(paint_speed)
    reload_block = _build_reload_block(cfg)

    def _is_pen_up(line: str) -> bool:
        u = line.strip().upper()
        if not u.startswith(pu_cmd):
            return False
        # ensure it's not a longer command like "M3 S200" matching "M3 S20"
        rest = u[len(pu_cmd):]
        return not rest or rest[0] in ' \t;'

    cur_x = cur_y = 0.0
    pen_down              = False
    accumulated           = 0.0
    needs_reload          = False
    initial_reload_done   = False   # inject one reload after the first G0 (home move)
    n_reloads             = 0
    total_down            = 0.0

    out: list[str] = []

    for raw in lines:
        line       = raw.rstrip('\n').rstrip('\r')
        first_word = line.strip().upper().split()[0] if line.strip() else ""

        # ---- initial reload: inject once after the first G0 (home move) ----
        if not initial_reload_done and first_word == "G0":
            out.append(line)
            out.extend(reload_block)
            n_reloads           += 1
            initial_reload_done  = True
            nx, ny = _extract_xy(line)
            cur_x = nx if nx is not None else cur_x
            cur_y = ny if ny is not None else cur_y
            continue

        # ---- pen-up: replace with paint_pen_up_cmd, then inject reload if needed ----
        if _is_pen_up(line):
            out.append(paint_pu_out)
            pen_down = False
            if needs_reload:
                out.extend(reload_block)
                accumulated  = 0.0
                needs_reload = False
                n_reloads   += 1
            continue

        # ---- track position and pen-down distance ----
        if first_word in ("G0", "G1"):
            nx, ny = _extract_xy(line)
            if nx is None: nx = cur_x
            if ny is None: ny = cur_y

            if first_word == "G1" and pen_down:
                dist         = math.sqrt((nx - cur_x) ** 2 + (ny - cur_y) ** 2)
                accumulated += dist
                total_down  += dist
                if accumulated >= paint_dist:
                    needs_reload = True
                if paint_speed is not None:
                    line = _F_RE.sub(f"F{paint_speed}", line)

            cur_x, cur_y = nx, ny

        # any M3 that is not the pen-up command means pen is going down
        if first_word == "M3" and not _is_pen_up(line):
            pen_down = True

        out.append(line)

    return out, n_reloads, total_down


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Insert paint-reload stops into pen-plotter G-code.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("gcode", help="Input G-code file.")
    parser.add_argument("--config", "-c", default=None,
                        help="JSON config file.  Default: looks for gcode_paint.json "
                             "next to the G-code file, then in cwd.")
    parser.add_argument("--output", "-o", default=None,
                        help="Output path.  Default: <stem>_paint.gcode alongside input.")
    args = parser.parse_args()

    # Config resolution: explicit > gcode_paint.json beside gcode > cwd
    cfg_path = args.config
    if cfg_path is None:
        for candidate_dir in [
            os.path.dirname(os.path.abspath(args.gcode)),
            os.getcwd(),
        ]:
            candidate = os.path.join(candidate_dir, "gcode_paint.json")
            if os.path.isfile(candidate):
                cfg_path = candidate
                break

    cfg = load_config(cfg_path)

    if not os.path.isfile(args.gcode):
        print(f"Error: G-code file not found: {args.gcode}", file=sys.stderr)
        sys.exit(1)

    with open(args.gcode, encoding="utf-8") as f:
        lines = f.readlines()

    print(f"{os.path.basename(args.gcode)}: {len(lines)} input lines")
    print(f"  Paint pot  : ({cfg['paint_x']}, {cfg['paint_y']}) mm  "
          f"radius={cfg['paint_radius']} mm")
    print(f"  Reload every: {cfg['paint_distance_mm']} mm pen-down travel")

    out_lines, n_reloads, total_down = process_gcode(lines, cfg)

    # Prepend summary header
    header = [
        f"; Processed by scripts/gcode_to_paint.py",
        f"; Source         : {os.path.basename(args.gcode)}",
        f"; Paint pot      : ({cfg['paint_x']}, {cfg['paint_y']}) mm  "
        f"radius={cfg['paint_radius']} mm",
        f"; Reload threshold: {cfg['paint_distance_mm']} mm",
        f"; Reloads inserted: {n_reloads}",
        f"; Total pen-down  : {total_down:.1f} mm",
        "",
    ]
    out_lines = header + out_lines

    out_path = args.output
    if out_path is None:
        stem     = os.path.splitext(os.path.basename(args.gcode))[0]
        gcode_dir = os.path.dirname(os.path.abspath(args.gcode))
        out_path  = os.path.join(gcode_dir, stem + "_paint.gcode")

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out_lines) + "\n")

    print(f"  -> {out_path}  ({len(out_lines)} lines)")
    print(f"     Total pen-down travel : {total_down:.1f} mm")
    print(f"     Paint reloads inserted: {n_reloads}")


if __name__ == "__main__":
    main()
