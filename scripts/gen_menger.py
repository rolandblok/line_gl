#!/usr/bin/env python3
"""
Generate a Menger sponge (Sierpinski sponge) scene for pen-plotter postcard.

A Menger sponge is a 3D fractal: start with a cube, subdivide 3x3x3,
remove cubes where 2 or more coordinates are at the middle index, repeat.

Usage:
    python scripts/gen_menger.py [--level N] [--out PATH]

    --level N   Recursion depth: 1=20 blocks, 2=400 blocks (default), 3=8000 blocks
    --out PATH  Output path (default scenes/postcard_menger.json)
"""

import argparse
import json
import sys
from pathlib import Path


def menger_blocks(level: int, origin: tuple, size: float):
    """Yield (origin, size) tuples for all leaf cubes of a Menger sponge."""
    if level == 0:
        yield (origin, size)
        return
    sub = size / 3.0
    for ix in range(3):
        for iy in range(3):
            for iz in range(3):
                # Keep cube if at most one coordinate is the middle index (1)
                if sum(1 for c in [ix, iy, iz] if c == 1) <= 1:
                    sub_origin = (
                        origin[0] + ix * sub,
                        origin[1] + iy * sub,
                        origin[2] + iz * sub,
                    )
                    yield from menger_blocks(level - 1, sub_origin, sub)



def build_scene(level: int) -> dict:
    total_size = 3.0  # world-space side length
    # Centre sponge at origin
    half = total_size / 2.0
    origin = (-half, -half, -half)

    all_blocks = list(menger_blocks(level, origin, total_size))

    # Build a lookup set for neighbour detection (round to avoid float noise)
    block_set = {(round(ox, 6), round(oy, 6), round(oz, 6))
                 for (ox, oy, oz), _ in all_blocks}

    def has_nb(ox, oy, oz, ddx, ddy, ddz, s):
        return (round(ox + ddx * s, 6),
                round(oy + ddy * s, 6),
                round(oz + ddz * s, 6)) in block_set

    blocks = []
    for (ox, oy, oz), size in all_blocks:
        # Is each of the 6 faces exterior? (True = no neighbour on that side)
        ext_xn = not has_nb(ox, oy, oz, -1,  0,  0, size)
        ext_xp = not has_nb(ox, oy, oz,  1,  0,  0, size)
        ext_yn = not has_nb(ox, oy, oz,  0, -1,  0, size)
        ext_yp = not has_nb(ox, oy, oz,  0,  1,  0, size)
        ext_zn = not has_nb(ox, oy, oz,  0,  0, -1, size)
        ext_zp = not has_nb(ox, oy, oz,  0,  0,  1, size)

        # An edge is visible when the count of solid cells around its axis is odd
        # (1 = convex corner, 3 = concave corner). Even counts mean a flat seam or
        # interior edge and should be skipped.
        # The 4 cells around each edge axis are: current block, the two face-direction
        # neighbours, and the diagonal (face1+face2 direction) neighbour.
        # Formula: draw if (int(ext_F1) + int(ext_F2) + int(has_diag)) % 2 == 0
        #
        # Edge → (face_A, face_B, diag_dx, diag_dy, diag_dz):
        #   0:z-,y-  1:z-,x+  2:z-,y+  3:z-,x-
        #   4:z+,y-  5:z+,x+  6:z+,y+  7:z+,x-
        #   8:x-,y-  9:x+,y-  10:x+,y+  11:x-,y+
        def ev(ext_f1, ext_f2, ddx, ddy, ddz):
            has_diag = has_nb(ox, oy, oz, ddx, ddy, ddz, size)
            return int((int(ext_f1) + int(ext_f2) + int(has_diag)) % 2 == 0)

        se = [
            ev(ext_zn, ext_yn,  0, -1, -1),  # e0:  z-, y-
            ev(ext_zn, ext_xp,  1,  0, -1),  # e1:  z-, x+
            ev(ext_zn, ext_yp,  0,  1, -1),  # e2:  z-, y+
            ev(ext_zn, ext_xn, -1,  0, -1),  # e3:  z-, x-
            ev(ext_zp, ext_yn,  0, -1,  1),  # e4:  z+, y-
            ev(ext_zp, ext_xp,  1,  0,  1),  # e5:  z+, x+
            ev(ext_zp, ext_yp,  0,  1,  1),  # e6:  z+, y+
            ev(ext_zp, ext_xn, -1,  0,  1),  # e7:  z+, x-
            ev(ext_xn, ext_yn, -1, -1,  0),  # e8:  x-, y-
            ev(ext_xp, ext_yn,  1, -1,  0),  # e9:  x+, y-
            ev(ext_xp, ext_yp,  1,  1,  0),  # e10: x+, y+
            ev(ext_xn, ext_yp, -1,  1,  0),  # e11: x-, y+
        ]

        blocks.append({
            "origin": [round(ox, 9), round(oy, 9), round(oz, 9)],
            "dx": round(size, 9),
            "dy": round(size, 9),
            "dz": round(size, 9),
            "col": [0, 0, 0],
            "show_edges": se,
            "group_id": 0,
        })

    # Camera: elevated 3/4 view to show three faces
    scene = {
        "camera": {
            "position": [5.5, 4.5, 7.0],
            "target":   [0.0, 0.0, 0.0],
            "projection": "orthographic",
            "ortho_height": 2.8
        },
        "light_direction": [1.0, -2.0, -0.5],
        "hatching": { "max_spacing": 0.2, "min_spacing": 0.05, "shade_cutoff": 0.95, "epsilon": 0.001, "color": [180, 180, 180] },
        "blocks": blocks
    }
    return scene


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--level", type=int, default=2,
                        help="Recursion depth: 1=20, 2=400 (default), 3=8000 blocks")
    parser.add_argument("--out", type=str, default="scenes/postcard_menger.json",
                        help="Output path (default scenes/postcard_menger.json)")
    args = parser.parse_args()

    if args.level < 1 or args.level > 3:
        print("--level must be 1, 2, or 3", file=sys.stderr)
        sys.exit(1)

    n_blocks = 20 ** args.level
    print(f"Generating Menger sponge level {args.level} ({n_blocks} blocks)...")
    scene = build_scene(args.level)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(scene, f, indent=4)
    print(f"Written {n_blocks} blocks to {out_path}")


if __name__ == "__main__":
    main()
