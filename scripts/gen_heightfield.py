#!/usr/bin/env python3
"""
Generate a heightfield using the plasma (diamond-square) algorithm and
write it as scenes/heightfield.json for rendering with line_gl.

Usage:
    python scripts/gen_heightfield.py [--size N] [--roughness R] [--seed S]

    --size N       Grid resolution: produces a (2^N + 1) x (2^N + 1) grid.
                   Default: 5  (33x33 = 1024 quads)
    --roughness R  Roughness in [0,1]. Higher = more jagged. Default: 0.6
    --seed S       Random seed for reproducibility. Default: 42
"""

import argparse
import json
import math
import random
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Diamond-square / plasma algorithm
# ---------------------------------------------------------------------------

def diamond_square(n: int, roughness: float, rng: random.Random) -> list[list[float]]:
    """Return a (2^n+1) x (2^n+1) height grid with values in [0, 1]."""
    size = (1 << n) + 1
    grid = [[0.0] * size for _ in range(size)]

    # Seed the four corners
    grid[0][0]             = rng.random()
    grid[0][size - 1]      = rng.random()
    grid[size - 1][0]      = rng.random()
    grid[size - 1][size - 1] = rng.random()

    scale = 1.0
    step = size - 1

    while step > 1:
        half = step // 2
        scale *= (2.0 ** (-roughness))

        # Diamond step: fill cell centres
        for y in range(0, size - 1, step):
            for x in range(0, size - 1, step):
                avg = (grid[y][x] + grid[y][x + step] +
                       grid[y + step][x] + grid[y + step][x + step]) / 4.0
                grid[y + half][x + half] = avg + rng.uniform(-scale, scale)

        # Square step: fill edge midpoints
        for y in range(0, size, half):
            for x in range((y + half) % step, size, step):
                count, total = 0, 0.0
                for dy, dx in [(-half, 0), (half, 0), (0, -half), (0, half)]:
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < size and 0 <= nx < size:
                        total += grid[ny][nx]
                        count += 1
                grid[y][x] = total / count + rng.uniform(-scale, scale)

        step = half

    # Normalise to [0, 1]
    flat = [v for row in grid for v in row]
    lo, hi = min(flat), max(flat)
    span = hi - lo if hi > lo else 1.0
    return [[(v - lo) / span for v in row] for row in grid]


# ---------------------------------------------------------------------------
# Colour mapping: low=deep blue, mid=green/brown, high=white
# ---------------------------------------------------------------------------

def height_color(h: float) -> tuple[int, int, int]:
    """Map normalised height [0,1] to an RGB colour."""
    stops = [
        (0.00, (30,  80, 180)),   # deep water
        (0.30, (60, 140,  80)),   # lowland green
        (0.55, (110, 100,  60)),  # highland brown
        (0.75, (150, 130,  90)),  # rocky
        (1.00, (240, 240, 240)),  # snow
    ]
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        if h <= t1:
            t = (h - t0) / (t1 - t0)
            r = int(c0[0] + t * (c1[0] - c0[0]))
            g = int(c0[1] + t * (c1[1] - c0[1]))
            b = int(c0[2] + t * (c1[2] - c0[2]))
            return (r, g, b)
    return stops[-1][1]


# ---------------------------------------------------------------------------
# Build scene JSON
# ---------------------------------------------------------------------------

def build_scene(grid: list[list[float]], height_scale: float, no_edges: bool = False) -> dict:
    size = len(grid)        # 2^n + 1
    n_cells = size - 1
    # Centre the grid around origin in XZ; Y is up
    offset = n_cells / 2.0

    rectangles = []
    for iz in range(n_cells):
        for ix in range(n_cells):
            x0, x1 = ix - offset, ix + 1 - offset
            z0, z1 = iz - offset, iz + 1 - offset
            y00 = grid[iz    ][ix    ] * height_scale
            y10 = grid[iz    ][ix + 1] * height_scale
            y11 = grid[iz + 1][ix + 1] * height_scale
            y01 = grid[iz + 1][ix    ] * height_scale

            # Average height of quad for colour
            h_avg = (grid[iz][ix] + grid[iz][ix+1] +
                     grid[iz+1][ix] + grid[iz+1][ix+1]) / 4.0
            col = list(height_color(h_avg))

            # Points wound counter-clockwise viewed from above (normal = +Y):
            # a=bottom-left, b=top-left, c=top-right, d=bottom-right
            rect = {
                "a": [x0, y00, z0],
                "b": [x0, y01, z1],
                "c": [x1, y11, z1],
                "d": [x1, y10, z0],
                "col": col
            }
            if no_edges:
                rect["show_edges"] = [0, 0, 0, 0]
            rectangles.append(rect)

    # Place camera to see the whole terrain from a nice angle
    cam_dist = n_cells * 1.2
    cam_pos = [cam_dist * 0.6, cam_dist * 0.7, cam_dist * 0.8]
    cam_target = [0.0, height_scale * 0.5, 0.0]
    cam_dir = [cam_target[i] - cam_pos[i] for i in range(3)]
    light_dir = cam_dir 
    light_dir[0] = light_dir[0] + 10.5  # Slightly offset light from camera direction for better shading
    scene = {
        "camera": {
            "position": cam_pos,
            "target": cam_target,
            "projection": "orthographic",
            "ortho_height": n_cells * 0.75
        },
        "light_direction": light_dir,
        "rectangles": rectangles
    }
    return scene


def set_no_edges(scene: dict) -> dict:
    scene["show_intersection_lines"] = False
    return scene


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--size",      type=int,   default=3,   help="Grid power (default 2 → 5x5)")
    parser.add_argument("--roughness", type=float, default=0.6, help="Roughness 0-1 (default 0.6)")
    parser.add_argument("--seed",      type=int,   default=42,  help="Random seed (default 42)")
    parser.add_argument("--height",    type=float, default=4.0, help="Max terrain height (default 4.0)")
    parser.add_argument("--out",       type=str,   default="scenes/heightfield.json",
                        help="Output path (default scenes/heightfield.json)")
    parser.add_argument("--edges",  action="store_true",
                        help="Draw quad/triangle intersection lines (hidden by default)")
    args = parser.parse_args()

    if args.size < 1 or args.size > 9:
        print("--size must be between 1 and 9", file=sys.stderr)
        sys.exit(1)

    rng = random.Random(args.seed)
    print(f"Generating {(1 << args.size) + 1}x{(1 << args.size) + 1} heightfield "
          f"(roughness={args.roughness}, seed={args.seed})...")

    grid = diamond_square(args.size, args.roughness, rng)
    no_edges = not args.edges
    scene = build_scene(grid, args.height, no_edges=no_edges)
    if no_edges:
        set_no_edges(scene)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(scene, f, indent=4)

    n_cells = (1 << args.size)
    print(f"Written {n_cells * n_cells} rectangles to {out_path}")


if __name__ == "__main__":
    main()
