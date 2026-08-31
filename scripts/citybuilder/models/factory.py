#!/usr/bin/env python3
"""Factory - a hall under a tiled gable roof, usually with a cylinder chimney."""

import math

from model_api import Geometry, Lot

NAME = "factory"
DENSITY = 0.08          # share of all plots that get one; see --density-factory

DEFAULTS = {
    "min_footprint": 0.6,     # fraction of the plot the hall covers, per axis
    "max_footprint": 0.95,
    "jitter": 0.3,            # 0 = centred on the plot, 0.5 = anywhere in it
    "min_wall": 0.45,         # wall height as a fraction of the roof span
    "max_wall": 0.85,
    "roof_pitch": 0.45,       # ridge height as a fraction of the roof span
    "eaves": 0.05,            # overhang at the eaves, as a fraction of the span
    "tile_rows": 4,           # courses of tiles drawn on each roof slope
    "chimney_chance": 0.7,    # 0 = never, 1 = always
    "chimney_facets": 8,      # sides of the prism standing in for a cylinder
    "chimney_radius": 0.13,   # fraction of the hall's short side
    "min_chimney": 1.3,       # chimney height as a multiple of the ridge height
    "max_chimney": 2.2,
    "crown": True,            # slightly wider band capping the chimney
    "flue": True,             # open the top, instead of capping it over solid
    "flue_width": 0.6,        # the opening, as a fraction of the top radius
    "hide_bottom": False,     # bottom ring of edges (useful with a ground plane)
    "color": [0, 0, 0],
}

# Tile courses and the chimney sit *on* a surface, so they are pushed a hair
# clear of it along its normal - exactly why the ground plane uses --ground-drop.
SKIN = 2.0e-3

# The roof plane runs through the wall head, so the hall's top ring of edges lies
# *in* the roof surface: draw it and the building outline is ruled across the
# tiles, as if the wall showed through. The roof draws that junction itself, at
# its own eaves and rakes. See EDGES_TOP in model_api for the index order.
EDGES_UNDER_ROOF = [1, 1, 0, 1, 1, 1, 0, 1, 1, 1, 0, 0]
EDGES_UNDER_ROOF_NO_BOTTOM = [0, 1, 0, 1, 0, 1, 0, 1, 0, 0, 0, 0]


def build(lot: Lot) -> Geometry:
    rng = lot.rng
    g = Geometry()
    col = lot.p("color")

    w = lot.sx * rng.uniform(lot.p("min_footprint"), lot.p("max_footprint"))
    d = lot.sz * rng.uniform(lot.p("min_footprint"), lot.p("max_footprint"))

    # The ridge runs along the hall's *long* axis, so the roof slopes face the
    # short one and the gable ends stay narrow, the way a real shed reads.
    along_x = w >= d
    span = d if along_x else w                    # eaves-to-eaves distance
    chimney = rng.random() < lot.p("chimney_chance")

    # A chimney standing free next to the gable end needs its own strip of the
    # plot, so the hall gives up that much of its length before it is placed.
    radius = span * lot.p("chimney_radius")
    strip = 2.2 * radius if chimney else 0.0
    if along_x:
        w = max(w - strip, span * 0.8)
        x, z = lot.place(w + strip, d, lot.p("jitter"))
    else:
        d = max(d - strip, span * 0.8)
        x, z = lot.place(w, d + strip, lot.p("jitter"))

    wall = span * rng.uniform(lot.p("min_wall"), lot.p("max_wall"))
    rise = span * lot.p("roof_pitch")
    eaves = span * lot.p("eaves")

    top = lot.y + wall
    ridge = top + rise
    # An overhang is the roof plane carried on past the wall, so the eaves hang
    # *below* the wall head by the pitch times the overhang. Holding them level
    # with it instead leaves the roof floating clear of the building on a wedge
    # of nothing - which is exactly what it looks like.
    eave = top - rise * eaves / (span / 2.0)
    # The verges stay flush with the gable. Overhanging them too would put each
    # gable's rake *inside* the slope instead of along its edge, and a crease
    # lying in the middle of a surface gets drawn - the far gable showing
    # through the roof. Flush, the slope's own edge is the rake.
    edges = (EDGES_UNDER_ROOF_NO_BOTTOM if lot.p("hide_bottom")
             else EDGES_UNDER_ROOF)
    g.block([x, lot.y, z], w, wall, d, col=col, show_edges=edges)

    inside = (x + w / 2.0, lot.y + wall / 2.0, z + d / 2.0)   # a point in the hall
    rows = int(lot.p("tile_rows"))

    if along_x:
        zc = z + d / 2.0
        _slope(g, [(x, eave, z - eaves), (x + w, eave, z - eaves),
                   (x + w, ridge, zc), (x, ridge, zc)],
               inside, rows, col)
        _slope(g, [(x + w, eave, z + d + eaves), (x, eave, z + d + eaves),
                   (x, ridge, zc), (x + w, ridge, zc)],
               inside, rows, col)
        _gable(g, [(x, top, z), (x, top, z + d)], (x, ridge, zc), span, col, inside)
        _gable(g, [(x + w, top, z + d), (x + w, top, z)], (x + w, ridge, zc), span,
               col, inside)
        cx, cz = x + w + strip / 2.0, zc
    else:
        xc = x + w / 2.0
        _slope(g, [(x - eaves, eave, z + d), (x - eaves, eave, z),
                   (xc, ridge, z), (xc, ridge, z + d)],
               inside, rows, col)
        _slope(g, [(x + w + eaves, eave, z), (x + w + eaves, eave, z + d),
                   (xc, ridge, z + d), (xc, ridge, z)],
               inside, rows, col)
        _gable(g, [(x + w, top, z), (x, top, z)], (xc, ridge, z), span, col, inside)
        _gable(g, [(x, top, z + d), (x + w, top, z + d)], (xc, ridge, z + d), span,
               col, inside)
        cx, cz = xc, z + d + strip / 2.0

    if chimney:
        height = rise * rng.uniform(lot.p("min_chimney"), lot.p("max_chimney"))
        _chimney(g, cx, cz, lot.y, top + height, radius,
                 int(lot.p("chimney_facets")), bool(lot.p("crown")), col,
                 base=not lot.p("hide_bottom"), flue=bool(lot.p("flue")),
                 flue_width=lot.p("flue_width"))
    return g


# ---------------------------------------------------------------------------
# Faces
#
# The renderer reads a triangle normal as (b - a) x (c - a) and back-face culls
# before it hatches, so a quad wound the wrong way round still draws its edges
# but is never shaded. Every surface here goes through _face, which winds it
# outwards - blocks are safe already, the renderer builds those itself.
# ---------------------------------------------------------------------------

def _face(g, quad, edges, col, inside):
    """Emit a quad facing away from `inside`, and return that outward normal."""
    a, b, c, d = quad
    n = _unit(_cross(_sub(b, a), _sub(c, a)))
    mid = tuple((a[i] + b[i] + c[i] + d[i]) / 4.0 for i in range(3))
    if _dot(n, _sub(mid, inside)) < 0.0:
        # Reversing a, b, c, d -> d, c, b, a renames the edges as well: what was
        # a-b is now the third edge, so the flags have to travel with it.
        quad = (d, c, b, a)
        edges = [edges[2], edges[1], edges[0], edges[3]]
        n = tuple(-k for k in n)
    g.rect(quad[0], quad[1], quad[2], quad[3], col=col, show_edges=edges)
    return n


# ---------------------------------------------------------------------------
# Roof
# ---------------------------------------------------------------------------

def _slope(g, quad, inside, rows, col):
    """One roof plane, eaves edge first, plus its courses of tiles."""
    a, b, c, d = quad
    normal = _face(g, quad, [1, 1, 1, 1], col, inside)
    if rows <= 0:
        return
    # Courses run parallel to the ridge, lifted off the plane so the renderer
    # does not have to decide between two coplanar things.
    for i in range(1, rows + 1):
        t = i / (rows + 1.0)
        g.line(_lift(_lerp(a, d, t), normal), _lift(_lerp(b, c, t), normal), col=col)


def _gable(g, eave, apex, span, col, inside):
    """The triangular wall closing one end of the roof.

    Drawn as a very shallow trapezoid rather than a true triangle: a quad with
    two coincident corners collapses to a zero-area second triangle, whose
    shading normal is undefined.
    """
    (ax, ay, az), (bx, by, bz) = eave
    apex_x, apex_y, apex_z = apex
    # Split the apex a hair along the ridge, which runs at right angles to the
    # eaves - the resulting top edge is far under a plotted pen width.
    ex, ez = bx - ax, bz - az
    length = math.hypot(ex, ez) or 1.0
    ux, uz = -ez / length, ex / length
    nudge = span * 2.0e-3
    _face(g, ([ax, ay, az], [bx, by, bz],
              [apex_x + ux * nudge, apex_y, apex_z + uz * nudge],
              [apex_x - ux * nudge, apex_y, apex_z - uz * nudge]),
          # No edges of its own: with a flush verge the slope's side edge is
          # already exactly this triangle's rake, and drawing both doubles it.
          [0, 0, 0, 0], col, inside)


# ---------------------------------------------------------------------------
# Chimney - an N-sided prism reads as a cylinder once it is drawn in lines
# ---------------------------------------------------------------------------

def _chimney(g, cx, cz, y0, y1, r, facets, crown, col, base=True,
             flue=True, flue_width=0.6):
    top_r = r
    if crown:
        band = max((y1 - y0) * 0.05, r * 0.35)
        # The shaft stops half way up the crown rather than level with it: two
        # caps at the same height are a coplanar tie the renderer cannot
        # resolve, and it draws the shaft's rim inside the crown's as a ghost.
        _prism(g, cx, cz, y0, y1 - band * 0.5, r, facets, col, base_ring=base)
        # The crown ends in mid-air, so it always draws the ring underneath it.
        _prism(g, cx, cz, y1 - band, y1, r * 1.18, facets, col,
               base_ring=True, cap=not flue)
        top_r = r * 1.18
    else:
        _prism(g, cx, cz, y0, y1, r, facets, col, base_ring=base, cap=not flue)
    if flue:
        _flue(g, cx, cz, y1, top_r, facets, flue_width, col)


def _ring(cx, cz, r, n):
    """N points round a circle, half a facet off so one face meets the camera."""
    return [(cx + r * math.cos(2.0 * math.pi * i / n + math.pi / n),
             cz + r * math.sin(2.0 * math.pi * i / n + math.pi / n))
            for i in range(n)]


def _prism(g, cx, cz, y0, y1, r, facets, col, base_ring=True, cap=True):
    n = max(4, facets + facets % 2)          # even, so the cap tiles into quads
    inside = (cx, (y0 + y1) / 2.0, cz)       # on the axis: every face faces away
    ring = _ring(cx, cz, r, n)
    for i in range(n):
        ax, az = ring[i]
        bx, bz = ring[(i + 1) % n]
        # One vertical per facet - the other belongs to the neighbour - plus the
        # rims. Without the bottom rim the shaft would just stop in mid-air.
        _face(g, ([ax, y0, az], [bx, y0, bz], [bx, y1, bz], [ax, y1, az]),
              [1 if base_ring else 0, 1, 1, 0], col, inside)
    if not cap:
        return
    for i in range(1, n - 2, 2):             # cap, as a fan of quads
        # Every edge off: the rim is already drawn by the sides, and the chords
        # across the cap are not real edges of anything.
        _face(g, ([ring[0][0], y1, ring[0][1]], [ring[i][0], y1, ring[i][1]],
                  [ring[i + 1][0], y1, ring[i + 1][1]],
                  [ring[i + 2][0], y1, ring[i + 2][1]]),
              [0, 0, 0, 0], col, inside)


def _flue(g, cx, cz, y_top, r_out, facets, width, col):
    """The chimney mouth: a rim of brick, the shaft of the flue, and its floor.

    A real opening rather than a line drawn on a solid cap - so the inner rim
    is a genuine silhouette, the far wall down the hole catches the hatching,
    and none of it depends on two surfaces landing at the same height.
    """
    n = max(4, facets + facets % 2)
    r_in = r_out * max(0.05, min(width, 0.9))
    depth = r_in * 1.3
    y_floor = y_top - depth
    outer, inner = _ring(cx, cz, r_out, n), _ring(cx, cz, r_in, n)

    below = (cx, y_top - r_out, cz)          # under the rim: it must face up
    for i in range(n):
        j = (i + 1) % n
        # Rim. Outer edge is the prism's top rim already; the inner one is the
        # mouth, and the radial joins between bricks are not edges of anything.
        _face(g, ([outer[i][0], y_top, outer[i][1]], [outer[j][0], y_top, outer[j][1]],
                  [inner[j][0], y_top, inner[j][1]], [inner[i][0], y_top, inner[i][1]]),
              [0, 0, 1, 0], col, below)

        # Down the flue. The solid is the brickwork *outside* this face, so the
        # reference point is pushed out past it and the normal turns inwards.
        mx, mz = (inner[i][0] + inner[j][0]) / 2.0, (inner[i][1] + inner[j][1]) / 2.0
        out = _unit((mx - cx, 0.0, mz - cz))
        brick = (cx + out[0] * r_out * 2.0, (y_top + y_floor) / 2.0,
                 cz + out[2] * r_out * 2.0)
        _face(g, ([inner[i][0], y_floor, inner[i][1]], [inner[j][0], y_floor, inner[j][1]],
                  [inner[j][0], y_top, inner[j][1]], [inner[i][0], y_top, inner[i][1]]),
              [0, 1, 0, 0], col, brick)

    deeper = (cx, y_floor - r_out, cz)       # under the floor: it must face up
    for i in range(1, n - 2, 2):
        _face(g, ([inner[0][0], y_floor, inner[0][1]], [inner[i][0], y_floor, inner[i][1]],
                  [inner[i + 1][0], y_floor, inner[i + 1][1]],
                  [inner[i + 2][0], y_floor, inner[i + 2][1]]),
              [0, 0, 0, 0], col, deeper)


# ---------------------------------------------------------------------------
# Small vector helpers
# ---------------------------------------------------------------------------

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _unit(a):
    length = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / length, a[1] / length, a[2] / length)


def _lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def _lift(p, n):
    return [p[0] + n[0] * SKIN, p[1] + n[1] * SKIN, p[2] + n[2] * SKIN]
