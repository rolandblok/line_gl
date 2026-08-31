#!/usr/bin/env python3
"""Box - the simplest building: one axis-aligned box standing on its plot."""

from model_api import EDGES_ALL, EDGES_NO_BOTTOM, Geometry, Lot

NAME = "box"
DENSITY = 0.6           # share of all plots that get one; see --density-box

DEFAULTS = {
    # Height is a multiple of the footprint's short side, not a world distance:
    # a block split into 3x3 plots would otherwise produce needles.
    "min_aspect": 0.7,
    "max_aspect": 3.0,
    "min_footprint": 0.5,   # fraction of the plot the box covers, per axis
    "max_footprint": 0.9,
    "jitter": 0.5,          # 0 = centred on the plot, 0.5 = anywhere in it
    "hide_bottom": False,   # bottom ring of edges (useful with a ground plane)
    "color": [0, 0, 0],
}


def build(lot: Lot) -> Geometry:
    rng = lot.rng
    g = Geometry()

    # Footprint is drawn per axis, so a rectangular plot gives a rectangular
    # building rather than a square one floating in the middle of it.
    w = lot.sx * rng.uniform(lot.p("min_footprint"), lot.p("max_footprint"))
    d = lot.sz * rng.uniform(lot.p("min_footprint"), lot.p("max_footprint"))
    x, z = lot.place(w, d, lot.p("jitter"))
    height = min(w, d) * rng.uniform(lot.p("min_aspect"), lot.p("max_aspect"))

    edges = EDGES_NO_BOTTOM if lot.p("hide_bottom") else EDGES_ALL
    g.block([x, lot.y, z], w, height, d, col=lot.p("color"), show_edges=edges)
    return g
