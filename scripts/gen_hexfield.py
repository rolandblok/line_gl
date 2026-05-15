#!/usr/bin/env python3
"""gen_hexfield.py – Generate an N×M hex-grid of hexagonal prisms.

Heights follow a bell-curve profile (tallest at centre) with per-hex
random variation.  Intended for rendering with line_gl + hatching.

Usage examples
--------------
    python scripts/gen_hexfield.py
    python scripts/gen_hexfield.py --cols 11 --rows 9 --seed 7
    python scripts/gen_hexfield.py --max-height 3.0 --noise 0.5 --out scenes/hexfield.json
"""

import argparse
import json
import math
import random
from pathlib import Path


# ---------------------------------------------------------------------------
# Hex grid geometry (pointy-top hexagons)
# ---------------------------------------------------------------------------

def hex_verts_xz(cx: float, cz: float, r: float) -> list[tuple[float, float]]:
    """Return 6 (x,z) corner positions of a pointy-top hexagon."""
    verts = []
    for i in range(6):
        a = math.pi / 6 + i * math.pi / 3   # 30° + 60°*i
        verts.append((cx + r * math.cos(a), cz + r * math.sin(a)))
    return verts


def hex_center(col: int, row: int, r: float) -> tuple[float, float]:
    """World-space (x, z) centre of hex at grid position (col, row).

    Pointy-top layout:
      - horizontal spacing = sqrt(3)*r
      - vertical spacing   = 1.5*r
      - odd rows are offset right by sqrt(3)/2*r
    """
    dx = math.sqrt(3) * r
    dz = 1.5 * r
    x = col * dx + (dx / 2.0 if row % 2 else 0.0)
    z = row * dz
    return x, z


# ---------------------------------------------------------------------------
# Prism builder
# ---------------------------------------------------------------------------

def make_prism(
    cx: float,
    h: float,
    cz: float,
    r: float,
    edge_col: list[int],
) -> tuple[list[dict], list[dict]]:
    """Return (triangles, lines) for one hex prism of height *h*.

    Winding convention (matches line_gl):
      normal = (b-a) × (c-a)  pointing outward / upward.

    Top face   → normal +Y  : fan (T[0], T[i+1], T[i])  i = 1..4
    Side faces → normal outward: (T[i], T[j], B[j]) + (T[i], B[j], B[i])
    """
    vxz = hex_verts_xz(cx, cz, r)
    T = [[vx, h,   vz] for vx, vz in vxz]   # top ring
    B = [[vx, 0.0, vz] for vx, vz in vxz]   # bottom ring

    tris: list[dict] = []
    lines: list[dict] = []

    # --- Top face (4 triangles, fan from T[0]) ---
    for i in range(1, 5):
        tris.append({"a": T[0], "b": T[i + 1], "c": T[i]})

    # --- Six side faces (2 triangles each) ---
    for i in range(6):
        j = (i + 1) % 6
        tris.append({"a": T[i], "b": T[j], "c": B[j]})
        tris.append({"a": T[i], "b": B[j], "c": B[i]})

    # --- Edges ---
    for i in range(6):
        j = (i + 1) % 6
        lines.append({"a": T[i], "b": T[j], "col": edge_col})   # top hexagon edge
        lines.append({"a": T[i], "b": B[i], "col": edge_col})   # vertical corner edge

    return tris, lines


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate an N×M hex-grid of hexagonal prisms.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--cols",       type=int,   default=9,
                        help="Number of hex columns [9]")
    parser.add_argument("--rows",       type=int,   default=7,
                        help="Number of hex rows [7]")
    parser.add_argument("--radius",     type=float, default=0.5,
                        help="Hex circumradius in scene units [0.5]")
    parser.add_argument("--max-height", type=float, default=2.0,
                        help="Peak prism height at grid centre [2.0]")
    parser.add_argument("--min-height", type=float, default=0.05,
                        help="Minimum prism height (floor) [0.05]")
    parser.add_argument("--noise",      type=float, default=0.25,
                        help="Height noise amplitude (fraction of local base height) [0.25]")
    parser.add_argument("--sigma",      type=float, default=0.40,
                        help="Bell-curve width as fraction of grid half-diagonal [0.40]")
    parser.add_argument("--seed",       type=int,   default=42,
                        help="Random seed [42]")
    parser.add_argument("--zoom",       type=float, default=1.5,
                        help="Ortho zoom factor: smaller = bigger drawing [1.5]")
    parser.add_argument("--scale",      type=float, default=1.0,
                        help="Prism radius scale (< 1.0 adds gaps between hexes) [1.0]")
    parser.add_argument("--out",        type=str,   default="scenes/hexfield.json",
                        help="Output JSON path [scenes/hexfield.json]")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    r   = args.radius

    # ---- Build grid positions ----
    grid = [(col, row) for row in range(args.rows) for col in range(args.cols)]
    centers_all = [hex_center(col, row, r) for col, row in grid]

    all_x = [c[0] for c in centers_all]
    all_z = [c[1] for c in centers_all]
    cx_mid = (max(all_x) + min(all_x)) / 2.0
    cz_mid = (max(all_z) + min(all_z)) / 2.0

    # Ellipse semi-axes: fit the full grid extent
    a_ellipse = (max(all_x) - min(all_x)) / 2.0 + r * 0.5   # x semi-axis
    b_ellipse = (max(all_z) - min(all_z)) / 2.0 + r * 0.5   # z semi-axis

    # Keep only hex centers inside the ellipse
    centers = [
        (hx, hz) for (hx, hz) in centers_all
        if ((hx - cx_mid) / a_ellipse) ** 2 + ((hz - cz_mid) / b_ellipse) ** 2 <= 1.0
    ]

    half_diag = math.sqrt(a_ellipse ** 2 + b_ellipse ** 2)

    sigma = args.sigma * half_diag
    h_max = args.max_height
    h_min = args.min_height

    # ---- Build geometry ----
    all_tris:  list[dict] = []
    all_lines: list[dict] = []
    edge_col = [0, 0, 0]

    for (hx, hz) in centers:
        d      = math.sqrt((hx - cx_mid) ** 2 + (hz - cz_mid) ** 2)
        base_h = h_max * math.exp(-0.5 * (d / sigma) ** 2) if sigma > 0 else h_min
        noise  = rng.gauss(0.0, args.noise * base_h)
        h      = max(h_min, min(h_max, base_h + noise))

        t, ln = make_prism(hx - cx_mid, h, hz - cz_mid, r * args.scale, edge_col)
        all_tris.extend(t)
        all_lines.extend(ln)

    # ---- Scene parameters ----
    scene_radius = half_diag + r
    ortho_h      = scene_radius * args.zoom
    cam_d        = scene_radius * 2.4

    # Camera position is a point in world space the camera sits at.
    # For orthographic projection, only the *direction* from position to target
    # matters (not the distance) — zoom is controlled by ortho_height instead.
    #
    # position = [cam_d * X, cam_d * Y, cam_d * Z]
    #   X:  left/right rotation around scene  (0 = centred, + = right, - = left)
    #   Y:  elevation / height above scene    (larger = steeper top-down view)
    #   Z:  front/back distance from scene    (larger = more frontal perspective)
    #
    # Example angles (X=0 keeps the scene left-right symmetric):
    #   [0.0, 0.6, 0.4]  → steep, nearly top-down
    #   [0.0, 0.4, 0.5]  → moderate isometric-style (current)
    #   [0.0, 0.2, 0.8]  → low, almost side-on

    scene = {
        "camera": {
            "position":    [round(cam_d * 0.1, 4), round(cam_d * 0.4, 4), round(cam_d * 0.5, 4)],
            "target":      [0.0, round(h_max * 0.25, 4), 0.0],
            "projection":  "orthographic",
            "ortho_height": round(ortho_h, 4),  # smaller = bigger/closer drawing (use --zoom)
        },
        "light_direction":        [0.6, -1.5, -0.8],
        "show_intersection_lines": False,
        "hatching": {
            "max_spacing":  0.2,
            "min_spacing":  0.05,
            "shade_cutoff": 0.95,
            "epsilon":      0.001,
            "color":        [100, 120, 160],
        },
        "triangles": all_tris,
        "lines":     all_lines,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(scene, f, indent=2)

    print(f"Generated {args.cols}x{args.rows} hex grid (oval, "
          f"{len(centers)} prisms, {len(all_tris)} triangles, {len(all_lines)} lines)"
          f"  -> {out_path}")


if __name__ == "__main__":
    main()
