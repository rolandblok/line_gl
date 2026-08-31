#!/usr/bin/env python3
"""
Shared API for city models.

A *model* is a python module in `scripts/citybuilder/models/` that describes one
kind of thing standing on a grid cell (a house, a skyscraper, a tree, ...).

Each model module must define:

    NAME     = "box"                  # unique name, used on the command line
    DENSITY  = 0.6                    # optional, share of plots this model gets
    DEFAULTS = {"min_height": 0.4}    # optional, tunable parameters
    def build(lot: Lot) -> Geometry:  # required
        ...

`build` receives a Lot (the cell to fill, plus an rng and the resolved
parameters) and returns a Geometry holding primitives in *world* coordinates.
The city builder stamps every primitive of one model instance with a shared
`group_id` so the renderer does not draw intersection lines inside a building.

World convention (same as the rest of line_gl): +Y is up, the ground is the
XZ plane at y = 0.
"""

from dataclasses import dataclass, field
from typing import Any, Iterator, Sequence
import random

Vec3 = Sequence[float]

BLACK = [0, 0, 0]

# show_edges on a block is 12 flags, and they are *not* grouped by ring: the
# renderer walks the z=0 face (0-3), the z=dz face (4-7), then the four edges
# joining them (8-11), so each group mixes heights. These masks pick out the
# rings properly - see add_block in include/scene.h for the vertex order.
EDGES_BOTTOM = (0, 4, 8, 9)     # the ring at y = origin.y
EDGES_TOP = (2, 6, 10, 11)      # the ring at y = origin.y + dy
EDGES_VERTICAL = (1, 3, 5, 7)   # the four corner posts


def edges_without(*rings):
    """All 12 edges on, minus the given rings: edges_without(EDGES_BOTTOM)."""
    off = {i for ring in rings for i in ring}
    return [0 if i in off else 1 for i in range(12)]


EDGES_ALL = [1] * 12
# A building standing on the ground rarely needs its bottom edges - they sit
# inside the ground plane.
EDGES_NO_BOTTOM = edges_without(EDGES_BOTTOM)


@dataclass
class Lot:
    """One plot of the city grid, handed to a model to be filled.

    A block between streets is divided into plots, so a lot is usually a
    fraction of a block and is **not** square: use `sx`/`sz`, not `size`.
    """
    ix: int                     # grid index of the block along X
    iz: int                     # grid index of the block along Z
    x0: float                   # world min corner X
    z0: float                   # world min corner Z
    sx: float                   # world size along X
    sz: float                   # world size along Z
    y: float = 0.0              # ground level
    plot: int = 0               # index of this plot within its block
    rng: random.Random = field(default_factory=random.Random)
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def x1(self) -> float:
        return self.x0 + self.sx

    @property
    def z1(self) -> float:
        return self.z0 + self.sz

    @property
    def cx(self) -> float:
        return self.x0 + self.sx / 2.0

    @property
    def cz(self) -> float:
        return self.z0 + self.sz / 2.0

    @property
    def size(self) -> float:
        """The largest square that fits the plot - handy for square models."""
        return min(self.sx, self.sz)

    def inset(self, margin: float) -> "Lot":
        """A smaller lot, shrunk by `margin` on every side."""
        return Lot(self.ix, self.iz, self.x0 + margin, self.z0 + margin,
                   max(self.sx - 2.0 * margin, 0.0), max(self.sz - 2.0 * margin, 0.0),
                   self.y, self.plot, self.rng, self.params)

    def place(self, w: float, d: float, jitter: float) -> tuple[float, float]:
        """Min corner for a w x d footprint inside this plot.

        `jitter` 0 centres it, 0.5 puts it anywhere in the plot; anything in
        between keeps it near the middle.
        """
        j = max(0.0, min(jitter, 0.5))
        return (self.x0 + (self.sx - w) * self.rng.uniform(0.5 - j, 0.5 + j),
                self.z0 + (self.sz - d) * self.rng.uniform(0.5 - j, 0.5 + j))

    def p(self, name: str, default: Any = None) -> Any:
        """Read a model parameter."""
        return self.params.get(name, default)


@dataclass
class Geometry:
    """A bag of line_gl scene primitives in world space."""
    blocks: list[dict] = field(default_factory=list)
    rectangles: list[dict] = field(default_factory=list)
    lines: list[dict] = field(default_factory=list)

    # -- emitters ----------------------------------------------------------
    def block(self, origin: Vec3, dx: float, dy: float, dz: float,
              col: Vec3 = BLACK, show_edges: Sequence[int] | None = None) -> dict:
        b = {"origin": _v3(origin), "dx": _r(dx), "dy": _r(dy), "dz": _r(dz),
             "col": list(col)}
        if show_edges is not None:
            b["show_edges"] = list(show_edges)
        self.blocks.append(b)
        return b

    def rect(self, a: Vec3, b: Vec3, c: Vec3, d: Vec3,
             col: Vec3 = BLACK, show_edges: Sequence[int] | None = None) -> dict:
        r = {"a": _v3(a), "b": _v3(b), "c": _v3(c), "d": _v3(d), "col": list(col)}
        if show_edges is not None:
            r["show_edges"] = list(show_edges)
        self.rectangles.append(r)
        return r

    def line(self, a: Vec3, b: Vec3, col: Vec3 = BLACK) -> dict:
        ln = {"a": _v3(a), "b": _v3(b), "col": list(col)}
        self.lines.append(ln)
        return ln

    # -- bookkeeping -------------------------------------------------------
    def extend(self, other: "Geometry") -> "Geometry":
        self.blocks.extend(other.blocks)
        self.rectangles.extend(other.rectangles)
        self.lines.extend(other.lines)
        return self

    def stamp_group(self, gid: int) -> None:
        """Tag every primitive with a shared group id (kills inner seam lines)."""
        for prim in (*self.blocks, *self.rectangles):
            prim["group_id"] = gid

    def vertices(self) -> Iterator[tuple[float, float, float]]:
        """Every corner point, for camera framing."""
        for b in self.blocks:
            ox, oy, oz = b["origin"]
            for sx in (0.0, b["dx"]):
                for sy in (0.0, b["dy"]):
                    for sz in (0.0, b["dz"]):
                        yield (ox + sx, oy + sy, oz + sz)
        for r in self.rectangles:
            for k in "abcd":
                yield tuple(r[k])
        for ln in self.lines:
            yield tuple(ln["a"])
            yield tuple(ln["b"])

    def is_empty(self) -> bool:
        return not (self.blocks or self.rectangles or self.lines)

    def __len__(self) -> int:
        return len(self.blocks) + len(self.rectangles) + len(self.lines)


def _r(x: float) -> float:
    return round(float(x), 9)


def _v3(v: Vec3) -> list[float]:
    return [_r(v[0]), _r(v[1]), _r(v[2])]
