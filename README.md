# line_gl

A C++17 hidden-line renderer that produces clean SVG output. Scenes are defined in JSON and rendered by projecting 3D geometry, removing hidden lines geometrically, and hatching visible surfaces.

## Build & run

```sh
make
bin/line_gl [scene.json ...]   # renders all scenes/**.json when no args given
```

Outputs go to `svg/`.

## Scene format (JSON)

```json
{
    "camera": { "position":[x,y,z], "target":[x,y,z], "projection":"orthographic", "ortho_height":5.0 },
    "light_direction": [x, y, z],
    "show_intersection_lines": true,
    "lines":      [{ "a":[x,y,z], "b":[x,y,z], "col":[r,g,b] }],
    "triangles":  [{ "a":[x,y,z], "b":[x,y,z], "c":[x,y,z], "col":[r,g,b] }],
    "rectangles": [{ "a":[x,y,z], "b":[x,y,z], "c":[x,y,z], "d":[x,y,z], "col":[r,g,b], "show_edges":[1,1,1,1] }],
    "blocks":     [{ "origin":[x,y,z], "dx":n, "dy":n, "dz":n, "col":[r,g,b] }]
}
```

`show_intersection_lines` (default `true`) controls whether triangle-plane intersection lines are drawn. Set to `false` for smooth meshes like spheres or terrain.  
`show_edges` on a rectangle is `[ab, bc, cd, da]` — each `0` or `1`.

## Python scene generators

```sh
python scripts/gen_sphere.py      [--subdivisions N] [--radius R] [--no-edges] [--out PATH]
python scripts/gen_heightfield.py [--size N] [--roughness R] [--seed S] [--height H] [--no-edges] [--out PATH]
```

| Script | Algorithm | Output |
|---|---|---|
| `gen_sphere.py` | Icosphere (subdivided icosahedron) — equal-size triangles | `scenes/sphere.json` |
| `gen_heightfield.py` | Diamond-square (plasma) — randomised terrain | `scenes/heightfield.json` |

## Layout

```
include/   header-only library
src/       main.cpp
scenes/    example JSON scenes
scripts/   Python scene generators
svg/       rendered output
```
