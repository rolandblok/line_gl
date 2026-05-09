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

        # An edge is visible when at least one of its two adjacent faces is exterior.
        # Edge → (face_A, face_B):
        #   0:z-,y-  1:z-,x+  2:z-,y+  3:z-,x-
        #   4:z+,y-  5:z+,x+  6:z+,y+  7:z+,x-
        #   8:x-,y-  9:x+,y-  10:x+,y+  11:x-,y+
        se = [
            int(ext_zn or ext_yn),   # e0
            int(ext_zn or ext_xp),   # e1
            int(ext_zn or ext_yp),   # e2
            int(ext_zn or ext_xn),   # e3
            int(ext_zp or ext_yn),   # e4
            int(ext_zp or ext_xp),   # e5
            int(ext_zp or ext_yp),   # e6
            int(ext_zp or ext_xn),   # e7
            int(ext_xn or ext_yn),   # e8
            int(ext_xp or ext_yn),   # e9
            int(ext_xp or ext_yp),   # e10
            int(ext_xn or ext_yp),   # e11
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
