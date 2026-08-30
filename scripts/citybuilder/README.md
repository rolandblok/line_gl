# citybuilder

Generates an isometric city as a `line_gl` scene: a square grid of blocks laid
out by a road network, each block optionally filled by a *model*, framed by an
isometric orthographic camera.

The camera is framed on the `--grid` city; the grid then keeps growing outwards
until buildings cover the entire frame, so the plot is city everywhere with no
empty corners. The renderer clips what falls off the canvas, which keeps the
SVG bounding box equal to the canvas - `svg_to_gcode.py` scales to that box, so
the plot fills the paper. `--no-extend` turns the growing off.

```sh
python scripts/citybuilder/gen_city.py            # -> scenes/city.json (portrait, shaded)
bin/line_gl scenes/city.json                      # -> svg/city.svg
python scripts/svg_to_gcode.py svg/city.svg       # -> gcode/city.gcode
```

## Layout

```
scripts/citybuilder/
    gen_city.py     road layout, model picking, camera framing, scene writing
    model_api.py    Lot + Geometry: what a model receives and what it returns
    models/
        __init__.py model discovery (every *.py here is auto-registered)
        box.py      simplest model: one box per lot
```

World convention, same as the rest of line_gl: **+Y is up**, the ground is the
XZ plane at `y = 0`, and the city is centred on the origin.

## Options

| Flag | Meaning |
|---|---|
| `--grid N` | `N x N` blocks the camera is framed on; sets the zoom (default 5) |
| `--cell S` | world size of one lot, default 1.0 |
| `--street F` | road corridor width as fraction of a cell, default 0.25 |
| `--pavement F` | pavement width as fraction of a cell, default 0.06 |
| `--plots N` | split each block into 1..N plots per axis (default 3) |
| `--dead-ends F` | chance a road corridor is closed off, default 0.15 |
| `--no-roads` | skip the road/pavement layout entirely |
| `--road-dashes N` | centre markings per road segment, 0 = none (default 3) |
| `--density D` | chance a lot gets a building, default 0.6 |
| `--seed S` | reproducible layout |
| `--models a,b:3` | which models to use, optional `:weight` |
| `--config FILE` | JSON with per-model parameter overrides |
| `--list-models` | show discovered models and their parameters |
| `--no-extend` | do not grow the grid past `--grid` (leaves empty corners) |
| `--max-lots N` | safety cap on lots visited while extending (default 20000) |
| `--ground` | draw a ground plane under the city |
| `--no-hatch` | leave faces blank instead of hatching them |
| `--hatch-spacing L D` | hatch spacing in px on the lightest / darkest face (default 12 2.5) |
| `--shade-cutoff C` | faces brighter than this stay unhatched (default 0.79) |
| `--light X Y Z` | light direction (default `-0.58 -0.8 -0.05`) |
| `--azimuth/--elevation` | camera angles, default 45° / 35.264° (true isometric) |
| `--margin`, `--zoom` | framing slack / extra zoom |
| `--canvas WxH` | output canvas in px, default `600x800` (portrait) |
| `--out PATH` | default `scenes/city.json` |

The camera is fitted to the nominal `--grid` city: every vertex is projected
onto the camera plane and `ortho_height` is set so that city just fits the
canvas. The extension then back-projects the four frame corners onto the ground
plane to find which further lots can still land in view (plus slack for tall
buildings poking in from below the bottom edge), builds them, and drops any
whose projection misses the frame entirely.

Each lot is seeded from `(seed, ix, iz)`, so a lot always looks the same however
far the grid grows - raising `--grid` extends the city instead of reshuffling it.

## Roads and pavement

The layout is built before anything else and decides where a building may
stand:

```
|<-------------------- cell -------------------->|
| pavement |     block (buildable)    | pavement | road |
            ^ building line          ^ kerb
```

The world is a lattice of alternating strips - block, road, block, road - in
both x and z, so every lattice tile is one of four things:

```
    (even, even)   a block
    (odd,  even)   the road corridor between two blocks, running along z
    (even, odd )   the same, running along x
    (odd,  odd )   a crossing
```

Everything else follows from one question per tile: is it part of a block, or
is it open road? A filled tile draws a **kerb** line on each side facing open
road, and a **pavement** line parallel to it, inset by `--pavement` and mitred
into its neighbours. Because that outline follows the block, the pavement wraps
every corner and stops there - so **crossings stay clear**. Centre markings run
along open corridors only, and so break at every junction too.

### Dead ends

A corridor can be *closed* (`--dead-ends`, chance per corridor). A closed
corridor merges the blocks on either side into one bigger block, so the road
leading to it simply stops and the pavement wraps around its end. Nothing else
needs to know: the outline extraction handles merged blocks of any shape.

### Plots

A block is rarely one building, so it is diced into `1..--plots` plots per axis
(up to 3x3 by default, 2x3 and friends included) and each plot is offered to a
model independently - `--density` then applies per plot. The strip left where a
corridor was closed stays open as a courtyard between the merged halves.

`--no-roads` drops the whole layout and gives models the full block.

## Shading

Faces are shaded by the renderer's hatching: the darker a face is under
`--light`, the tighter its hatch lines. The default light sits over the left
shoulder and just above `--shade-cutoff`, so roofs print white while the two
visible wall directions come out clearly different - one sparse, one dense.

`--hatch-spacing` is given in **px** and converted to world units through the
camera scale, so the shading keeps the same density on the page whether the city
is 5 lots or 40. Raise both numbers for a lighter drawing (fewer pen strokes),
lower them for a darker one.

The canvas is portrait by default (`600x800`); it is written into the scene as
`"canvas"`, so the renderer projects and writes the SVG at that size.

Per-model parameters are overridden with a config file:

```json
{ "box": { "max_height": 4.0, "min_footprint": 0.7 } }
```

## Writing a new model

Drop a `*.py` file in `models/`. It is picked up automatically.

```python
"""Tower - a box with a thinner box on top."""

from model_api import Geometry, Lot

NAME = "tower"          # required, unique; used by --models
WEIGHT = 0.5            # optional, relative pick probability (default 1.0)
DEFAULTS = {            # optional, tunable via --config
    "height": 3.0,
}

def build(lot: Lot) -> Geometry:      # required
    g = Geometry()
    h = lot.p("height")
    g.block([lot.x0, lot.y, lot.z0], lot.sx, h, lot.sz)
    inner = lot.inset(lot.size * 0.25)
    g.block([inner.x0, lot.y + h, inner.z0], inner.sx, h * 0.5, inner.sz)
    return g
```

`Lot` gives the plot to fill (`x0/z0/x1/z1`, `sx`/`sz`, `cx/cz`, ground level
`y`), the rng (seeded per plot from `--seed`, so keep all randomness on it) and
the resolved parameters via `lot.p(name)`.

A plot is a slice of a block and is **not square** - use `sx` and `sz`, not
`size` (which is only the largest square that fits). Two helpers:

- `lot.inset(margin)` - a smaller lot, shrunk on every side.
- `lot.place(w, d, jitter)` - the min corner for a `w x d` footprint inside the
  plot; `jitter` 0 centres it, 0.5 puts it anywhere the plot allows.

`Geometry` collects primitives in **world** coordinates: `block(origin, dx, dy,
dz, col, show_edges)`, `rect(a, b, c, d, ...)` and `line(a, b, col)` — the same
primitives the scene format documents. `show_edges` on a block is the 12-entry
list `[bottom x4, top x4, vertical x4]`; leave it out to draw all edges.

Every primitive returned by one `build()` call is stamped with a shared
`group_id`, so the renderer does not draw intersection seams *inside* a
building — stacked and overlapping parts of one model come out clean.
