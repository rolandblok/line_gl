# line_gl

A fully vectorized 3D-to-2D projection renderer written in C++17.

Unlike rasterizers, this renderer works entirely in geometric/vector space
and produces clean vector output (SVG). Hidden-line removal is solved by
geometric analysis: lines are clipped against occluding triangles, split
into sub-segments, and each segment is individually tested for visibility.

## Pipeline

```
3D scene → MVP matrix transform → perspective divide → hidden-line removal → SVG
```

## Math convention

Column-major matrices, column vectors (OpenGL convention).
Transforms apply as: `v' = Projection * View * Model * v`

## SVG output

Y axis is flipped on final output to match SVG coordinate system (Y-down).

## Features (integrated step by step)

- [x] Step 1 — Math library: Vec3, Vec4, Mat4, basic operations
- [x] Step 2 — Scene primitives: Line3D, Triangle3D
- [x] Step 3 — MVP matrix pipeline: model, view, projection (OpenGL convention)
- [x] Step 4 — SVG output of projected lines (no depth yet)
- [x] Step 5 — Camera system: position, look-at, field of view
- [ ] Step 6 — Hidden-line removal
  - [x] 6a — Interval set: manage visible sub-ranges of [0,1] on a line segment
  - [x] 6b — 2D geometry helpers: segment intersection, point-in-triangle
  - [x] 6c — Depth interpolation: NDC depth along a segment and inside a triangle
  - [x] 6d — Per-triangle occlusion: find the interval a triangle occludes on a line
  - [x] 6e — Full pipeline: apply all triangles to all lines, output visible sub-segments
- [x] Step 6 — Hidden-line removal
- [ ] Step 7 — TBD after step 6

## Build

Requires a C++17-capable compiler (g++ or clang++).

```sh
make                  # build both binaries
make clean            # remove build artifacts
bin/line_gl           # run the renderer
bin/test_line_gl      # run the test suite
```

## Project layout

```
include/   header-only library (math, scene, transform, ...)
src/       main.cpp and test.cpp
bin/       compiled binaries
```
