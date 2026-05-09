#!/usr/bin/env python3
"""
Generate a set of pen-plotter postcard scenes (A6 landscape, 148x105mm).

The renderer outputs 800x600 SVG (ratio 1.33), close to A6 landscape (1.41).
Scale to exact A6 in your plotter software.

Usage:
    python scripts/gen_postcards.py
    bin/line_gl scenes/postcard_*.json
"""

import json
import subprocess
import sys
from pathlib import Path

Path("scenes").mkdir(exist_ok=True)
SCRIPTS = Path(__file__).parent


def write(name: str, scene: dict) -> None:
    path = Path("scenes") / f"{name}.json"
    with open(path, "w") as f:
        json.dump(scene, f, indent=4)
    print(f"  wrote {path}")


# ---------------------------------------------------------------------------
# 1. Columns — three blocks of different heights on a shared platform
# ---------------------------------------------------------------------------
write("postcard_columns", {
    "camera": {
        "position": [5.0, 3.5, 7.0],
        "target":   [0.0, 1.0, 0.0],
        "projection": "orthographic",
        "ortho_height": 4.0
    },
    "light_direction": [1.0, -2.5, -0.5],
    "blocks": [
        # platform
        {"origin": [-2.8, -0.5, -0.9], "dx": 5.6, "dy": 0.5, "dz": 1.8},
        # left column — tallest
        {"origin": [-2.2,  0.0, -0.7], "dx": 1.1, "dy": 3.2, "dz": 1.4},
        # centre column — medium
        {"origin": [-0.5,  0.0, -0.7], "dx": 1.1, "dy": 2.0, "dz": 1.4},
        # right column — shortest, wider
        {"origin": [ 1.2,  0.0, -0.7], "dx": 1.5, "dy": 1.1, "dz": 1.4},
    ]
})

# ---------------------------------------------------------------------------
# 2. Planes — four intersecting planar rectangles (shows crossing lines)
# ---------------------------------------------------------------------------
write("postcard_planes", {
    "camera": {
        "position": [5.5, 4.0, 6.5],
        "target":   [0.0, 1.2, 0.0],
        "projection": "orthographic",
        "ortho_height": 4.5
    },
    "light_direction": [0.8, -1.5, -0.6],
    "rectangles": [
        # horizontal ground plane (y = 0)
        {"a": [-3.0, 0.0, -3.0], "b": [3.0, 0.0, -3.0],
         "c": [3.0, 0.0,  3.0], "d": [-3.0, 0.0,  3.0], "col": [140, 150, 200]},
        # vertical slab parallel to XY (z = 0)
        {"a": [-2.0, 0.0, 0.0], "b": [2.0, 0.0, 0.0],
         "c": [2.0, 3.0, 0.0], "d": [-2.0, 3.0, 0.0], "col": [200, 140, 120]},
        # vertical slab parallel to YZ (x = 0)
        {"a": [0.0, 0.0, -2.0], "b": [0.0, 0.0, 2.0],
         "c": [0.0, 3.0,  2.0], "d": [0.0, 3.0, -2.0], "col": [130, 200, 150]},
        # diagonal slab (lies on plane x + z = 0)
        {"a": [-2.0, 0.0,  2.0], "b": [2.0, 0.0, -2.0],
         "c": [2.0, 3.0, -2.0], "d": [-2.0, 3.0,  2.0], "col": [210, 190, 90]},
    ]
})

# ---------------------------------------------------------------------------
# 3. Sphere — icosphere, no edge lines, hatching only
# ---------------------------------------------------------------------------
print("  generating postcard_sphere.json...")
subprocess.run([
    sys.executable, str(SCRIPTS / "gen_sphere.py"),
    "--subdivisions", "3",
    "--radius", "5",
    "--no-edges",
    "--out", "scenes/postcard_sphere.json",
], check=True)

# ---------------------------------------------------------------------------
# 4. Terrain — plasma heightfield, no edge lines, hatching only
# ---------------------------------------------------------------------------
print("  generating postcard_terrain.json...")
subprocess.run([
    sys.executable, str(SCRIPTS / "gen_heightfield.py"),
    "--size", "5",
    "--roughness", "0.55",
    "--height", "5",
    "--seed", "7",
    "--no-edges",
    "--out", "scenes/postcard_terrain.json",
], check=True)

print("\nDone. Render with:")
print("  .\\bin\\line_gl.exe scenes\\postcard_columns.json scenes\\postcard_planes.json "
      "scenes\\postcard_sphere.json scenes\\postcard_terrain.json")
print("\nSVGs are in svg/  — scale to 148x105mm (A6 landscape) in your plotter software.")
