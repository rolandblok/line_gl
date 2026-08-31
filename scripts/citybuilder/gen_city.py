#!/usr/bin/env python3
"""
Isometric city generator for line_gl.

Lays out a square grid of lots, drops a randomly chosen model on some of them,
frames the whole thing with an isometric orthographic camera and writes a
line_gl scene JSON that the C++ renderer turns into plotter-ready SVG.

Roads and their pavement are laid out first and decide where a building may
stand; the models then fill what is left of each block. The camera is framed on
the `--grid` city, and then the grid keeps growing outwards until the city
covers the whole frame - corner to corner, no empty sky. The renderer clips
whatever falls off the canvas.

Usage:
    python scripts/citybuilder/gen_city.py [options]
    python scripts/citybuilder/gen_city.py --list-models
    bin/line_gl scenes/city.json

Options of note:
    --grid N          N x N lots the camera is framed on (default 5)
    --cell S          world size of one lot (default 1.0)
    --density-NAME D  share of plots that get that model, 0..1 (one per model)
    --density D       overall fill: rescale the whole mix to this total
    --models a,b      restrict/weight the models used (default: all discovered)
    --seed S          reproducible layout
    --no-extend       keep exactly N x N lots, leaving the frame corners empty
    --pavement F      pavement width as a fraction of a cell (default 0.06)
    --plots N         split each block into 1..N plots per axis (default 3)
    --dead-ends F     chance a road corridor is closed off (default 0.15)
    --no-roads        skip the road/pavement layout
    --config FILE     extra config file, layered on the auto-loaded one
    --no-config       ignore city_config.json, use the built-in defaults
    --dump-config     print the settings in force as JSON and exit

Settings come from three places, each overriding the one before it: the
built-in defaults, `scripts/citybuilder/city_config.json` if it exists (plus
any `--config FILE`), and finally the command line. A config file holds option
names and an optional `model_params` block:

    { "density": 0.85, "grid": 6, "model_params": { "box": { "max_height": 4.0 } } }

World convention: +Y is up, the ground is the XZ plane at y = 0, the city is
centred on the origin.
"""

import argparse
import json
import math
import random
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from model_api import Geometry, Lot          # noqa: E402
from models import ModelSpec, load_models    # noqa: E402

# Output canvas in px, written into the scene so the renderer matches it.
# Portrait suits a city: the isometric diamond is wide, and the extension fills
# the rest, so the taller page simply shows more town.
DEFAULT_CANVAS = (600.0, 800.0)

# True isometric: yaw 45 deg, pitch atan(1/sqrt(2)) = 35.264 deg -> view dir (1,1,1).
ISO_AZIMUTH = 45.0
ISO_ELEVATION = math.degrees(math.atan(1.0 / math.sqrt(2.0)))

# Picked up automatically when it sits next to this script; --no-config skips it.
CONFIG_PATH = Path(__file__).resolve().parent / "city_config.json"

# Config keys spelled as the negative flag, mapped to the option they invert.
NEGATED = {"no_roads": "roads", "no_hatch": "hatch", "no_extend": "extend"}

# Options that only make sense on the command line.
NOT_CONFIGURABLE = {"config", "no_config", "dump_config", "list_models"}


# ---------------------------------------------------------------------------
# Small vector helpers (world space, +Y up)
# ---------------------------------------------------------------------------

def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _norm(a):
    length = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / length, a[1] / length, a[2] / length)


# ---------------------------------------------------------------------------
# City layout
# ---------------------------------------------------------------------------

def pick_model(models, densities, rng):
    """Which model lands on this plot, or None to leave it empty.

    One draw decides both questions at once: the models take slices of [0, 1)
    the size of their own density, and whatever is left over is open ground.
    """
    r = rng.random()
    upto = 0.0
    for m in models:
        upto += densities[m.name]
        if r < upto:
            return m
    return None


def resolve_densities(models, args):
    """Per-model chance that any given plot gets that model.

    Each model brings its own default (its module DENSITY); --density-NAME or
    the matching config key overrides it, --models NAME:w scales it, and
    --density, when given at all, rescales the whole mix to that total fill.
    """
    out = {}
    for m in models:
        override = getattr(args, "density_" + m.name.replace("-", "_"), None)
        base = m.density if override is None else float(override)
        out[m.name] = max(0.0, base * m.weight)

    total = sum(out.values())
    if args.density is not None:
        if total <= 0.0:
            raise SystemExit("every model has density 0, --density has nothing to scale")
        out = {k: v * args.density / total for k, v in out.items()}
        total = args.density
    if total > 1.0:
        print(f"warning: model densities add up to {total:.2f} - scaled back to 1.0",
              file=sys.stderr)
        out = {k: v / total for k, v in out.items()}
    return out


# ---------------------------------------------------------------------------
# Street layout
#
# The world is a lattice of alternating strips - block, road, block, road - in
# both x and z, so every lattice tile is one of four things:
#
#     (even, even)   a block
#     (odd,  even)   the road corridor between two blocks, running along z
#     (even, odd )   the same, running along x
#     (odd,  odd )   a crossing
#
# A corridor can be *closed*, which merges the blocks on either side of it into
# one bigger block. That is what produces dead ends: the road runs up to the
# closure and stops there, and the pavement wraps around its end. Kerbs,
# pavement and markings then all fall out of one question per tile - is it part
# of a block ("filled"), or is it open road?
# ---------------------------------------------------------------------------

# Lattice neighbours, and for each the two corners of that side of a tile plus
# the tangent running along it.
SIDES = {
    (-1, 0): ("x0z0", "x0z1", (0, 1)),
    (1, 0):  ("x1z0", "x1z1", (0, 1)),
    (0, -1): ("x0z0", "x1z0", (1, 0)),
    (0, 1):  ("x0z1", "x1z1", (1, 0)),
}


def strip_bounds(args, j):
    """World extent (lo, hi) of lattice strip `j` along one axis.

    Even j is the block strip of cell j/2, odd j the road corridor after it.
    """
    origin = -args.grid * args.cell / 2.0      # city centred on (0, *, 0)
    street = args.cell * args.street
    i = j // 2
    if j % 2 == 0:
        lo = origin + i * args.cell + street / 2.0
        return lo, lo + args.cell - street
    lo = origin + (i + 1) * args.cell - street / 2.0
    return lo, lo + street


def block_bounds(args, ix, iz):
    """World XZ square of one block: the cell minus the road corridor around it."""
    x0, x1 = strip_bounds(args, 2 * ix)
    z0, z1 = strip_bounds(args, 2 * iz)
    return x0, z0, x1 - x0


def corridor_closed(args, axis, ix, iz):
    """Is the corridor on the +x (or +z) side of cell (ix, iz) closed off?

    Seeded per corridor, so closures do not shift when the grid is extended.
    """
    if args.dead_ends <= 0.0:
        return False
    return random.Random(f"{args.seed}:road:{axis}:{ix}:{iz}").random() < args.dead_ends


def tile_filled(args, cells, jx, jz):
    """Is this lattice tile part of a block (rather than open road)?"""
    even_x, even_z = jx % 2 == 0, jz % 2 == 0
    ix, iz = jx // 2, jz // 2
    if even_x and even_z:
        return (ix, iz) in cells
    if even_z:                                  # corridor between ix and ix+1
        return ((ix, iz) in cells and (ix + 1, iz) in cells
                and corridor_closed(args, "x", ix, iz))
    if even_x:                                  # corridor between iz and iz+1
        return ((ix, iz) in cells and (ix, iz + 1) in cells
                and corridor_closed(args, "z", ix, iz))
    # A crossing is only swallowed when all four corridors meeting it are closed.
    return all(tile_filled(args, cells, jx + dx, jz + dz)
               for dx, dz in SIDES)


def _pavement_trim(filled, jx, jz, tangent, normal, pave):
    """How far to pull one end of a pavement line back from the tile corner.

    +pave at a convex corner (the pavement turns here), 0 where the block edge
    runs straight on into the next tile, -pave at a concave corner, where the
    line has to run past the corner to meet the pavement coming the other way.
    """
    if not filled(jx + tangent[0], jz + tangent[1]):
        return pave
    if not filled(jx + tangent[0] + normal[0], jz + tangent[1] + normal[1]):
        return 0.0
    return -pave


def _dashes(geo, a, b, count, y=0.0):
    """`count` dashes along the segment a-b, with equal gaps between them."""
    if count < 1:
        return
    steps = 2 * count - 1                      # dash, gap, dash, ... , dash
    for i in range(0, steps, 2):
        t0, t1 = i / steps, (i + 1) / steps
        geo.line([a[0] + (b[0] - a[0]) * t0, y, a[1] + (b[1] - a[1]) * t0],
                 [a[0] + (b[0] - a[0]) * t1, y, a[1] + (b[1] - a[1]) * t1])


def build_roads(args, cells, view=None):
    """The road network and its pavement, laid down before any building.

    Every filled tile contributes a kerb line for each side that faces open
    road, and a pavement line parallel to it, inset by `--pavement` and mitred
    into its neighbours. Since the pavement follows the block outline it wraps
    every corner and stops there, so crossings - and the open end of a dead end
    - stay clear. Centre markings run along each open corridor only, so they
    break at every junction too.
    """
    geo = Geometry()
    if not args.roads:
        return geo
    cells = set(cells)
    pave = args.cell * args.pavement

    def filled(jx, jz):
        return tile_filled(args, cells, jx, jz)

    # Every lattice tile touched by a built cell, including its corridors.
    tiles = {(2 * ix + dx, 2 * iz + dz)
             for ix, iz in cells for dx in (-1, 0, 1) for dz in (-1, 0, 1)}

    for jx, jz in sorted(tiles):
        x0, x1 = strip_bounds(args, jx)
        z0, z1 = strip_bounds(args, jz)
        if view is not None and not view.contains(
                [(x0, 0.0, z0), (x1, 0.0, z0), (x1, 0.0, z1), (x0, 0.0, z1)]):
            continue
        corner = {"x0z0": (x0, z0), "x0z1": (x0, z1),
                  "x1z0": (x1, z0), "x1z1": (x1, z1)}

        if not filled(jx, jz):
            # Open road: centre markings, but only in a corridor that actually
            # runs between two blocks (never in a crossing).
            if args.road_dashes and (jx % 2) != (jz % 2):
                if filled(jx - 1, jz) and filled(jx + 1, jz):
                    cx = (x0 + x1) / 2.0
                    _dashes(geo, (cx, z0), (cx, z1), args.road_dashes)
                elif filled(jx, jz - 1) and filled(jx, jz + 1):
                    cz = (z0 + z1) / 2.0
                    _dashes(geo, (x0, cz), (x1, cz), args.road_dashes)
            continue

        for normal, (c0, c1, tangent) in SIDES.items():
            if filled(jx + normal[0], jz + normal[1]):
                continue                        # not an outside edge
            p0, p1 = corner[c0], corner[c1]
            geo.line([p0[0], 0.0, p0[1]], [p1[0], 0.0, p1[1]])      # kerb
            if pave <= 0.0:
                continue
            # The pavement line: the kerb moved inward, its ends mitred to meet
            # the pavement of the neighbouring sides.
            inward = (-normal[0] * pave, -normal[1] * pave)
            back = (-tangent[0], -tangent[1])
            t0 = _pavement_trim(filled, jx, jz, back, normal, pave)
            t1 = _pavement_trim(filled, jx, jz, tangent, normal, pave)
            q0 = (p0[0] + inward[0] + tangent[0] * t0,
                  p0[1] + inward[1] + tangent[1] * t0)
            q1 = (p1[0] + inward[0] - tangent[0] * t1,
                  p1[1] + inward[1] - tangent[1] * t1)
            geo.line([q0[0], 0.0, q0[1]], [q1[0], 0.0, q1[1]])
    return geo


def block_plots(args, ix, iz):
    """Split a block into plots: 1..--plots of them along each axis.

    A block is rarely one building - 2x3 terraced plots, an L of shops, a
    single tower - so the block is diced first and each plot is then offered to
    a model. Seeded per block, so the division survives the grid growing.
    """
    x0, z0, size = block_bounds(args, ix, iz)
    pave = args.cell * args.pavement if args.roads else 0.0
    x0, z0, size = x0 + pave, z0 + pave, size - 2.0 * pave
    if size <= 0.0:
        return
    rng = random.Random(f"{args.seed}:plots:{ix}:{iz}")
    nx = rng.randint(1, max(args.plots, 1))
    nz = rng.randint(1, max(args.plots, 1))
    for kz in range(nz):
        for kx in range(nx):
            yield (x0 + size * kx / nx, z0 + size * kz / nz, size / nx, size / nz)


def build_block(models, densities, params, args, ix, iz):
    """Build every plot of one block. Yields (spec, geometry) per building.

    The rng is seeded per plot, so a plot always looks the same no matter how
    far the grid is extended around it - the inner city does not reshuffle when
    the outskirts grow. Seeds are strings: random.Random hashes a tuple, and
    tuple hashing is salted per process (and rejected outright since 3.11), so
    a tuple seed would make --seed meaningless.
    """
    for k, (px, pz, sx, sz) in enumerate(block_plots(args, ix, iz)):
        rng = random.Random(f"{args.seed}:lot:{ix}:{iz}:{k}")
        spec = pick_model(models, densities, rng)
        if spec is None:
            continue
        lot = Lot(ix=ix, iz=iz, plot=k, x0=px, z0=pz, sx=sx, sz=sz,
                  y=0.0, rng=rng, params=params[spec.name])
        piece = spec.build(lot)
        if not piece.is_empty():
            yield spec, piece


def build_city(models, densities, params, args):
    """Lay out the city; return the world geometry, the camera and stats.

    Order of work, which is also the order the primitives end up in the scene:
    the road network and its pavement go down first and decide where a building
    may stand, then the buildings are dropped on what is left of each block.

    The nominal `--grid` city sets the camera framing; after that - unless
    --no-extend - the grid grows outwards until every part of the viewport is
    covered, so the plot has no empty corners.
    """
    counts = {m.name: 0 for m in models}
    nominal_cells = [(ix, iz) for iz in range(args.grid) for ix in range(args.grid)]

    # Pass 1 - roads and pavement of the nominal grid, then its buildings.
    # Both frame the camera, so an empty corner lot cannot shift the view.
    roads = build_roads(args, nominal_cells)
    buildings = Geometry()
    gid = 0
    for ix, iz in nominal_cells:
        for spec, piece in build_block(models, densities, params, args, ix, iz):
            piece.stamp_group(gid)             # no seam lines inside one building
            gid += 1
            buildings.extend(piece)
            counts[spec.name] += 1

    framing = Geometry().extend(roads).extend(buildings)
    if framing.is_empty():
        return framing, None, {"lots": args.grid ** 2, "buildings": 0, "extra": 0,
                               "per_model": counts, "span": args.grid * args.cell,
                               "elevation": args.elevation}

    cam, view = fit_camera(framing, args)

    # Pass 2 - the same two steps for every further lot that lands in the frame.
    extra = 0
    if args.extend:
        outer = [(ix, iz) for ix, iz in extension_lots(buildings, view, args)
                 if not (0 <= ix < args.grid and 0 <= iz < args.grid)]
        # The road layout needs the whole extended cell set at once: a corridor
        # only closes when the blocks on both sides of it exist.
        roads = build_roads(args, nominal_cells + outer, view)
        for ix, iz in outer:
            for spec, piece in build_block(models, densities, params, args, ix, iz):
                if not view.contains(piece.vertices()):
                    continue                   # projects entirely off-canvas
                piece.stamp_group(gid)
                gid += 1
                buildings.extend(piece)
                counts[spec.name] += 1
                extra += 1

    geo = Geometry().extend(roads).extend(buildings)

    if args.ground:
        # Ground covers everything that was built, not just the nominal city.
        xs = [p[0] for p in geo.vertices()]
        zs = [p[2] for p in geo.vertices()]
        x0, x1, z0, z1 = min(xs), max(xs), min(zs), max(zs)
        y = -args.ground_drop                  # just below y=0, avoids coplanar seams
        ground = geo.rect([x0, y, z0], [x0, y, z1], [x1, y, z1], [x1, y, z0],
                          col=[0, 0, 0], show_edges=[1, 1, 1, 1])
        ground["group_id"] = gid
        gid += 1

    stats = {"lots": args.grid ** 2, "buildings": sum(counts.values()), "extra": extra,
             "per_model": counts, "span": args.grid * args.cell,
             "elevation": args.elevation, "road_lines": len(roads.lines)}
    return geo, cam, stats


# ---------------------------------------------------------------------------
# Isometric camera, framed around the geometry
# ---------------------------------------------------------------------------

def aspect(args):
    return args.canvas[0] / args.canvas[1]


def camera_basis(azimuth_deg, elevation_deg):
    """Return (to_cam, fwd, right, cam_up) for a yaw/pitch pair, +Y world up."""
    az = math.radians(azimuth_deg)
    el = math.radians(elevation_deg)
    # Direction from the target towards the camera.
    to_cam = _norm((math.cos(el) * math.sin(az), math.sin(el), math.cos(el) * math.cos(az)))
    fwd = _mul(to_cam, -1.0)
    right = _norm(_cross(fwd, (0.0, 1.0, 0.0)))
    cam_up = _norm(_cross(right, fwd))
    return to_cam, fwd, right, cam_up


def frame_geometry(pts, azimuth_deg, elevation_deg):
    """Bounding box of `pts` in the camera plane: (half_w, half_h, umid, vmid, depth)."""
    _, fwd, right, cam_up = camera_basis(azimuth_deg, elevation_deg)
    us = [_dot(p, right) for p in pts]
    vs = [_dot(p, cam_up) for p in pts]
    ds = [_dot(p, fwd) for p in pts]
    return ((max(us) - min(us)) / 2.0, (max(vs) - min(vs)) / 2.0,
            (min(us) + max(us)) / 2.0, (min(vs) + max(vs)) / 2.0,
            (min(ds) + max(ds)) / 2.0)


class View:
    """The visible rectangle, in the camera's own (u = right, v = up) plane."""

    def __init__(self, right, cam_up, umid, vmid, half_u, half_v):
        self.right, self.cam_up = right, cam_up
        self.u0, self.u1 = umid - half_u, umid + half_u
        self.v0, self.v1 = vmid - half_v, vmid + half_v

    def project(self, p):
        return _dot(p, self.right), _dot(p, self.cam_up)

    def contains(self, pts):
        """True if the projected bounding box of `pts` overlaps the viewport."""
        us, vs = zip(*(self.project(p) for p in pts))
        return (min(us) <= self.u1 and max(us) >= self.u0 and
                min(vs) <= self.v1 and max(vs) >= self.v0)

    def ground_of(self, u, v):
        """Back-project a viewport point onto the ground plane y = 0 -> (x, z)."""
        rx, rz = self.right[0], self.right[2]
        ux, uz = self.cam_up[0], self.cam_up[2]
        det = rx * uz - rz * ux
        if abs(det) < 1e-12:                # camera looking along the horizon
            return 0.0, 0.0
        return (u * uz - v * rz) / det, (v * rx - u * ux) / det


def extension_lots(geo, view, args):
    """Grid indices whose lots can possibly land in the viewport.

    The four viewport corners are back-projected onto the ground plane; that
    quad is the ground the camera actually sees. Its bottom edge is pushed out
    by the tallest building, because a tower whose base sits below the frame
    can still poke into it. The result is a world-space box, converted here to
    the grid indices covering it.
    """
    max_y = max((p[1] for p in geo.vertices()), default=args.cell * 3.0)
    # A building of height max_y shifts its top up by max_y * cam_up.y in the
    # camera plane; look that much further "down" for lots that reach into view.
    slack = max_y * max(view.cam_up[1], 1e-6)

    corners = [view.ground_of(u, v)
               for u in (view.u0, view.u1)
               for v in (view.v0 - slack, view.v1)]
    xs = [c[0] for c in corners]
    zs = [c[1] for c in corners]

    span = args.grid * args.cell
    origin = -span / 2.0
    lo_x = int(math.floor((min(xs) - origin) / args.cell)) - 1
    hi_x = int(math.ceil((max(xs) - origin) / args.cell)) + 1
    lo_z = int(math.floor((min(zs) - origin) / args.cell)) - 1
    hi_z = int(math.ceil((max(zs) - origin) / args.cell)) + 1

    total = (hi_x - lo_x) * (hi_z - lo_z)
    if total > args.max_lots:
        print(f"warning: extension would visit {total} lots, capped at "
              f"--max-lots {args.max_lots}; the frame may not fill completely",
              file=sys.stderr)
        shrink = math.sqrt(args.max_lots / total)
        cx, cz = (lo_x + hi_x) // 2, (lo_z + hi_z) // 2
        hx = max(int((hi_x - lo_x) * shrink / 2), args.grid // 2)
        hz = max(int((hi_z - lo_z) * shrink / 2), args.grid // 2)
        lo_x, hi_x, lo_z, hi_z = cx - hx, cx + hx, cz - hz, cz + hz

    for iz in range(lo_z, hi_z):
        for ix in range(lo_x, hi_x):
            yield ix, iz


def fit_camera(geo, args):
    """Isometric ortho camera that exactly frames the geometry (plus margin)."""
    pts = list(geo.vertices()) or [(0.0, 0.0, 0.0)]
    to_cam, fwd, right, cam_up = camera_basis(args.azimuth, args.elevation)
    half_w, half_h, umid, vmid, depth = frame_geometry(pts, args.azimuth, args.elevation)

    # ortho_height is the half-height of the view volume; the renderer widens it
    # by the aspect ratio, so the width constraint is half_w / aspect.
    ortho_height = max(half_h, half_w / aspect(args), 1e-3) * args.margin * args.zoom

    target = _add(_add(_mul(right, umid), _mul(cam_up, vmid)), _mul(fwd, depth))
    dist = max(half_w, half_h, 1.0) * 4.0 + 10.0
    position = _add(target, _mul(to_cam, dist))

    cam = {
        "position": [round(c, 6) for c in position],
        "target": [round(c, 6) for c in target],
        "up": [0.0, 1.0, 0.0],
        "projection": "orthographic",
        "ortho_height": round(ortho_height, 6),
        "near": 0.01,
        "far": round(dist * 3.0 + 10.0, 6),
    }
    view = View(right, cam_up, umid, vmid, ortho_height * aspect(args), ortho_height)
    return cam, view


# ---------------------------------------------------------------------------
# Scene assembly
# ---------------------------------------------------------------------------

def build_scene(geo, cam, args):
    scene = {
        "camera": cam,
        "canvas": {"width": args.canvas[0], "height": args.canvas[1]},
        # Sun over the left shoulder: roofs stay above the cutoff and print
        # white, the two visible wall directions get clearly different shades.
        "light_direction": list(args.light),
        "show_intersection_lines": True,
    }
    # Hatch spacing is a world distance, but what should stay constant is how
    # dense it looks on the page - so convert from px through the camera scale.
    px = 2.0 * cam["ortho_height"] / args.canvas[1]
    scene["hatching"] = {
        "max_spacing": round(args.hatch_spacing[0] * px, 6),
        "min_spacing": round(args.hatch_spacing[1] * px, 6),
        "shade_cutoff": args.shade_cutoff,
        "epsilon": round(px * 0.05, 6),
        "min_color": [140, 140, 140],
        "max_color": [60, 60, 60],
    }
    if not args.hatch:
        # Cutoff 0 means every face counts as bright enough -> no hatching at all.
        scene["hatching"]["shade_cutoff"] = 0.0
    if geo.blocks:
        scene["blocks"] = geo.blocks
    if geo.rectangles:
        scene["rectangles"] = geo.rectangles
    if geo.lines:
        scene["lines"] = geo.lines
    return scene


def resolve_params(models, config):
    """Merge each model's DEFAULTS with the user's config overrides."""
    out = {}
    for m in models:
        merged = dict(m.defaults)
        overrides = config.get(m.name, {})
        unknown = set(overrides) - set(merged)
        if unknown:
            print(f"warning: model '{m.name}' has no parameter(s) "
                  f"{sorted(unknown)} - passing them through anyway", file=sys.stderr)
        merged.update(overrides)
        out[m.name] = merged
    return out


def parse_canvas(text):
    """`600x800` -> (600.0, 800.0). A JSON config may also give `[600, 800]`."""
    try:
        parts = text if isinstance(text, (list, tuple)) else str(text).lower().split("x")
        w, h = (float(v) for v in parts)
        if w <= 0 or h <= 0:
            raise ValueError
    except (ValueError, TypeError):
        raise SystemExit(f"--canvas expects WxH in px, got '{text}'")
    return w, h


def _short(path):
    """Path relative to the working directory when that is shorter."""
    try:
        rel = Path(path).resolve().relative_to(Path.cwd())
        return str(rel)
    except ValueError:
        return str(path)


def load_config(path, known, extra_ok=False):
    """Read one config file -> (option defaults, per-model parameter overrides).

    `extra_ok` keeps unrecognised option keys instead of rejecting them, for
    tools that share this file but only understand part of it (gen_model.py).

    Keys are option names, with `-` or a leading `--` allowed instead of `_`,
    so `"dead_ends"` and `"--dead-ends"` land on the same option. Per-model
    parameters go under `"model_params"`; a bare `{"box": {...}}` at the top
    level is still understood, which is what --config took before.
    """
    try:
        raw = json.loads(Path(path).read_text())
    except FileNotFoundError:
        raise SystemExit(f"config: no such file '{path}'")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path}: invalid JSON - {exc}")
    if not isinstance(raw, dict):
        raise SystemExit(f"{path}: top level must be a JSON object")

    opts, model_params = {}, {}
    for key, value in raw.items():
        name = str(key).lstrip("-").replace("-", "_")
        if name == "model_params":
            if not isinstance(value, dict):
                raise SystemExit(f"{path}: 'model_params' must be an object")
            for model, over in value.items():
                model_params.setdefault(model, {}).update(over)
        elif name in NEGATED:
            opts[NEGATED[name]] = not value
        elif name in NOT_CONFIGURABLE:
            print(f"warning: {path}: '{key}' is command line only - ignored",
                  file=sys.stderr)
        elif name in known:
            opts[name] = value
        elif isinstance(value, dict):
            model_params.setdefault(key, {}).update(value)   # legacy per-model form
        elif extra_ok:
            opts[name] = value                               # the other tool's key
        else:
            raise SystemExit(f"{path}: unknown option '{key}'")
    return opts, model_params


def read_configs(explicit, use_default, known, extra_ok=False):
    """Layer the auto-loaded file, then --config. Later files win."""
    sources = []
    if use_default and CONFIG_PATH.exists():
        sources.append(CONFIG_PATH)
    if explicit:
        sources.append(Path(explicit))

    opts, model_params = {}, {}
    for src in sources:
        file_opts, file_models = load_config(src, known, extra_ok)
        opts.update(file_opts)
        for model, over in file_models.items():
            model_params.setdefault(model, {}).update(over)
    return opts, model_params, sources


def dump_config(args, available, model_params, known):
    """The settings in force, as a config file, so they can be saved and re-used."""
    out = {k: v for k, v in sorted(vars(args).items())
           if k in known and k not in NOT_CONFIGURABLE}
    # Per-model densities are written out resolved rather than as null, so the
    # file shows the numbers a reader would otherwise have to go and look up.
    for spec in available.values():
        key = "density_" + spec.name.replace("-", "_")
        if out.get(key) is None:
            out[key] = spec.density
    out["canvas"] = f"{args.canvas[0]:g}x{args.canvas[1]:g}"
    out["light"] = list(args.light)
    out["hatch_spacing"] = list(args.hatch_spacing)
    out["model_params"] = model_params
    print(json.dumps(out, indent=4))


def select_models(available, selection):
    """--models box,tower:3  ->  [box (weight 1), tower (weight 3)]."""
    if not selection:
        return list(available.values())
    chosen = []
    for token in selection.split(","):
        token = token.strip()
        if not token:
            continue
        name, _, weight = token.partition(":")
        if name not in available:
            raise SystemExit(f"unknown model '{name}'. Available: "
                             + (", ".join(available) or "(none)"))
        spec = available[name]
        if weight:
            spec = replace(spec, weight=float(weight))
        chosen.append(spec)
    if not chosen:
        raise SystemExit("--models selected nothing")
    return chosen


def main():
    available = load_models()

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--grid", type=int, default=5,
                        help="grid is N x N lots; sets the zoom (default 5)")
    parser.add_argument("--cell", type=float, default=1.0,
                        help="world size of one lot (default 1.0)")
    parser.add_argument("--street", type=float, default=0.25,
                        help="road corridor width as a fraction of a cell (default 0.25)")
    parser.add_argument("--pavement", type=float, default=0.06,
                        help="pavement width as a fraction of a cell, taken off the "
                             "buildable block (default 0.06)")
    parser.add_argument("--no-roads", dest="roads", action="store_false",
                        help="skip the road and pavement layout entirely")
    parser.add_argument("--road-dashes", type=int, default=3,
                        help="centre markings per road segment, 0 = none (default 3)")
    parser.add_argument("--dead-ends", type=float, default=0.15,
                        help="chance a road corridor is closed off, merging the two "
                             "blocks and ending the street, 0..1 (default 0.15)")
    parser.add_argument("--plots", type=int, default=3,
                        help="a block is split into 1..N plots per axis, so up to "
                             "NxN buildings per block (default 3)")
    parser.add_argument("--density", type=float, default=None,
                        help="overall fill: rescale every model density so they add "
                             "up to this, 0..1 (default: leave them as they are)")
    parser.add_argument("--seed", type=int, default=42, help="random seed (default 42)")
    parser.add_argument("--models", type=str, default=None,
                        help="comma list of models, optional :weight (default: all)")
    parser.add_argument("--config", type=str, default=None,
                        help="extra config file, layered on top of "
                             f"{CONFIG_PATH.name} if that exists")
    parser.add_argument("--no-config", dest="no_config", action="store_true",
                        help=f"ignore {CONFIG_PATH.name} and use the built-in defaults")
    parser.add_argument("--dump-config", action="store_true",
                        help="print the settings in force as JSON and exit; redirect "
                             f"into {CONFIG_PATH.name} to make them the defaults")
    parser.add_argument("--list-models", action="store_true",
                        help="print the discovered models with their parameters and exit")
    parser.add_argument("--ground", action="store_true",
                        help="draw a ground plane under the city")
    parser.add_argument("--ground-drop", type=float, default=0.001,
                        help="how far the ground sits below y=0 (default 0.001)")
    parser.add_argument("--no-hatch", dest="hatch", action="store_false",
                        help="leave faces blank instead of shading them with hatching")
    parser.add_argument("--hatch-spacing", type=float, nargs=2, default=(12.0, 2.5),
                        metavar=("LIGHT", "DARK"),
                        help="hatch line spacing in px, brightest and darkest face "
                             "(default 12 2.5)")
    parser.add_argument("--shade-cutoff", type=float, default=0.79,
                        help="faces brighter than this stay unhatched, 0..1 (default 0.79); "
                             "the default light puts roofs just above it")
    parser.add_argument("--light", type=float, nargs=3, default=(-0.58, -0.8, -0.05),
                        metavar=("X", "Y", "Z"),
                        help="light direction (default -0.58 -0.8 -0.05)")
    parser.add_argument("--azimuth", type=float, default=ISO_AZIMUTH,
                        help="camera yaw in degrees (default 45)")
    parser.add_argument("--elevation", type=float, default=ISO_ELEVATION,
                        help="camera pitch in degrees (default 35.264 = true isometric)")
    parser.add_argument("--no-extend", dest="extend", action="store_false",
                        help="do not grow the grid past --grid; leaves the frame "
                             "corners empty")
    parser.add_argument("--max-lots", type=int, default=20000,
                        help="safety cap on lots visited while extending (default 20000)")
    parser.add_argument("--canvas", type=str, default="600x800",
                        help="output canvas in px, WxH (default 600x800, portrait)")
    parser.add_argument("--margin", type=float, default=1.0,
                        help="framing slack around the city, 1.0 = edge to edge (default 1.0)")
    parser.add_argument("--zoom", type=float, default=1.0,
                        help="extra zoom factor; >1 zooms out (default 1.0)")
    parser.add_argument("--out", type=str, default="scenes/city.json",
                        help="output scene path (default scenes/city.json)")
    # One per discovered model, so a new model file brings its own knob with it.
    for spec in available.values():
        parser.add_argument(f"--density-{spec.name}", type=float, default=None,
                            metavar="D",
                            help=f"share of plots that get a {spec.name}, 0..1 "
                                 f"(default {spec.density:g})")
    # Defaults < config file < command line. set_defaults slides the config
    # values in underneath argparse, so anything typed still overrides them.
    known = set(vars(parser.parse_args([])))
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config")
    pre.add_argument("--no-config", dest="no_config", action="store_true")
    pre_args, _ = pre.parse_known_args()
    file_opts, model_params, sources = read_configs(
        pre_args.config, not pre_args.no_config, known)
    parser.set_defaults(**file_opts)

    args = parser.parse_args()
    args.canvas = parse_canvas(args.canvas)

    if args.list_models:
        if not available:
            print("no models found in scripts/citybuilder/models/")
        for spec in available.values():
            print(f"{spec.name}  (density {spec.density:g})  [{spec.path.name}]")
            if spec.doc:
                print(f"    {spec.doc}")
            for k, v in spec.defaults.items():
                print(f"    {k:<16} = {v}")
        return

    if args.dump_config:
        dump_config(args, available, model_params, known)
        return

    if not available:
        raise SystemExit("no models found in scripts/citybuilder/models/")

    strays = sorted(set(model_params) - set(available))
    if strays:
        print(f"warning: config has parameters for unknown model(s) {strays}",
              file=sys.stderr)

    models = select_models(available, args.models)
    params = resolve_params(models, model_params)
    densities = resolve_densities(models, args)

    geo, cam, stats = build_city(models, densities, params, args)
    if geo.is_empty() or cam is None:
        raise SystemExit("nothing was generated - raise a --density-NAME or check "
                         "the models")
    scene = build_scene(geo, cam, args)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(scene, indent=4))

    used = ", ".join(f"{n}:{c} ({densities[n]:.0%})"
                     for n, c in stats["per_model"].items() if c)
    inner = stats["buildings"] - stats["extra"]
    print(f"{inner} buildings on the {args.grid}x{args.grid} grid of blocks, "
          f"+{stats['extra']} outside it to fill the frame ({used})")
    if stats["road_lines"]:
        print(f"Roads: {stats['road_lines']} ground lines "
              f"(kerb + pavement + markings), laid before the buildings")
    print(f"Camera: azimuth {args.azimuth:g}, elevation {stats['elevation']:.3f} deg, "
          f"canvas {args.canvas[0]:g}x{args.canvas[1]:g} px"
          f"{'' if args.hatch else ', no hatching'}")
    if sources:
        print("Config: " + ", ".join(_short(s) for s in sources))
    print(f"Written {len(geo)} primitives to {out_path}")


if __name__ == "__main__":
    main()
