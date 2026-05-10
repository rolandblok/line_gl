#!/usr/bin/env python3
"""
Generate an icosphere mesh (subdivided icosahedron) and write it as
scenes/sphere.json for rendering with line_gl.

All triangles are approximately the same size, unlike a UV sphere.

Usage:
    python scripts/gen_sphere.py [--subdivisions N] [--radius R] [--no-edges]

    --subdivisions N  Number of subdivision steps (default 3 → 1280 triangles)
    --radius R        Sphere radius (default 2.0)
    --no-edges        Do not draw triangle intersection lines (silhouette only)
    --out PATH        Output path (default scenes/sphere.json)
"""

import argparse
import json
import math
import sys
from pathlib import Path


def _normalize(v: tuple) -> tuple:
    x, y, z = v
    n = math.sqrt(x*x + y*y + z*z)
    return (x/n, y/n, z/n)


def _height_color(h: float) -> list:
    """Map normalised height [0,1] to an RGB colour list."""
    stops = [
        (0.0, (30,  60, 140)),
        (0.4, (40, 160, 160)),
        (0.7, (80, 200, 120)),
        (1.0, (240, 240, 240)),
    ]
    for k in range(len(stops) - 1):
        t0, c0 = stops[k]
        t1, c1 = stops[k + 1]
        if h <= t1:
            t = (h - t0) / (t1 - t0)
            return [int(c0[m] + t * (c1[m] - c0[m])) for m in range(3)]
    return list(stops[-1][1])


def build_icosphere(radius: float, subdivisions: int) -> dict:
    phi = (1.0 + math.sqrt(5.0)) / 2.0

    # 12 vertices of a regular icosahedron (unit length)
    raw = [
        (-1,  phi,  0), ( 1,  phi,  0), (-1, -phi,  0), ( 1, -phi,  0),
        ( 0, -1,  phi), ( 0,  1,  phi), ( 0, -1, -phi), ( 0,  1, -phi),
        ( phi,  0, -1), ( phi,  0,  1), (-phi,  0, -1), (-phi,  0,  1),
    ]
    verts = [_normalize(v) for v in raw]

    # 20 faces
    faces = [
        (0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11),
        (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
        (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9),
        (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1),
    ]

    # Subdivide: each triangle → 4 by splitting edges at midpoints
    midpoint_cache: dict = {}

    def midpoint(i: int, j: int) -> int:
        key = (min(i, j), max(i, j))
        if key in midpoint_cache:
            return midpoint_cache[key]
        v = _normalize((
            (verts[i][0] + verts[j][0]) / 2,
            (verts[i][1] + verts[j][1]) / 2,
            (verts[i][2] + verts[j][2]) / 2,
        ))
        new_idx = len(verts)
        verts.append(v)
        midpoint_cache[key] = new_idx
        return new_idx

    for _ in range(subdivisions):
        new_faces = []
        for a, b, c in faces:
            ab = midpoint(a, b)
            bc = midpoint(b, c)
            ca = midpoint(c, a)
            new_faces += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        faces = new_faces

    # Scale to radius
    verts = [(x * radius, y * radius, z * radius) for (x, y, z) in verts]

    triangles = []
    for a, b, c in faces:
        va, vb, vc = verts[a], verts[b], verts[c]
        avg_y = (va[1] + vb[1] + vc[1]) / 3.0
        h = (avg_y / radius + 1.0) / 2.0
        col = _height_color(h)
        triangles.append({"a": list(va), "b": list(vb), "c": list(vc), "col": col})

    cam_dist = 10
    scene = {
        "camera": {
            "position": [cam_dist * 0.6, cam_dist * 0.5, cam_dist * 0.8],
            "target": [0.0, 0.0, 0.0],
            "projection": "orthographic",
            "ortho_height": 8.0
        },
        "light_direction": [0.0, -1.0, -0.8],
        "hatching": { "max_spacing": 0.2, "min_spacing": 0.05, "shade_cutoff": 0.95, "epsilon": 0.001, "color": [180, 180, 180] },
        "triangles": triangles
    }
    return scene


def set_no_edges(scene: dict) -> dict:
    scene["show_intersection_lines"] = False
    return scene


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--subdivisions", type=int,   default=2,
                        help="Subdivision steps: 0=20 tris, 1=80, 2=320, 3=1280 (default 3)")
    parser.add_argument("--radius",       type=float, default=6.0, help="Sphere radius (default 2.0)")
    parser.add_argument("--out",          type=str,   default="scenes/sphere.json",
                        help="Output path (default scenes/sphere.json)")
    parser.add_argument("--no-edges",     action="store_true",
                        help="Do not draw triangle intersection lines (silhouette only)")
    args = parser.parse_args()

    if args.subdivisions < 0 or args.subdivisions > 6:
        print("--subdivisions must be between 0 and 6", file=sys.stderr)
        sys.exit(1)

    n_tris = 20 * (4 ** args.subdivisions)
    print(f"Generating icosphere: radius={args.radius}, subdivisions={args.subdivisions} ({n_tris} triangles)...")
    scene = build_icosphere(args.radius, args.subdivisions)
    if args.no_edges:
        set_no_edges(scene)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(scene, f, indent=4)

    print(f"Written {n_tris} triangles to {out_path}")


if __name__ == "__main__":
    main()
