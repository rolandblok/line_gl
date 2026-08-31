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

python scripts/citybuilder/gen_model.py factory   # -> scenes/model.json, one building
bin/line_gl scenes/model.json                     # -> svg/model.svg
```

## Layout

```
scripts/citybuilder/
    gen_city.py     road layout, model picking, camera framing, scene writing
    gen_model.py    one model on an empty plot, filling the page, for inspection
    model_api.py    Lot + Geometry: what a model receives and what it returns
    models/
        __init__.py model discovery (every *.py here is auto-registered)
        box.py      simplest model: one box per lot
        factory.py  hall + tiled gable roof + cylinder chimney
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
| `--density-NAME D` | share of plots that get that model, one flag per model |
| `--density D` | overall fill: rescale the whole mix to this total |
| `--seed S` | reproducible layout |
| `--models a,b:3` | which models to use, optional `:weight` |
| `--config FILE` | extra config file, layered on top of `city_config.json` |
| `--no-config` | ignore `city_config.json` and use the built-in defaults |
| `--dump-config` | print the settings in force as JSON and exit |
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

## Models and how often they appear

| Model | Default density | What it draws |
|---|---|---|
| `box` | 0.6 | one axis-aligned box per plot |
| `factory` | 0.08 | a hall under a tiled gable roof, usually with a chimney |

Every model carries its own frequency, declared as `DENSITY` in its module and
overridable per model:

```sh
python scripts/citybuilder/gen_city.py --density-factory 0.25   # an industrial quarter
python scripts/citybuilder/gen_city.py --density-box 0          # factories only
```

A density is the **share of all plots** that get that model, so they add up:
the defaults leave `0.6 + 0.08 = 0.68` of plots built and the remaining 32%
open. If the total goes over 1.0 it is scaled back and a warning is printed.

`--density` no longer decides on its own whether a plot is built - it is now an
optional **overall fill** that rescales the whole mix while keeping its
proportions. `--density 0.9` fills 90% of plots at the same box-to-factory
ratio. Left unset, each model simply uses its own number.

`--models NAME:w` still works and multiplies that model's density, so
`--models box,factory:3` triples how often a factory turns up.

### factory

The ridge runs along the hall's long axis, so the gable ends stay narrow. The
roof slopes carry `tile_rows` courses of tiles, drawn a hair off the surface -
coplanar lines are exactly what `--ground-drop` exists to avoid.

`eaves` overhangs the eaves only; the verges stay flush with the gable. That is
not just a style choice: an overhanging verge puts the gable's rake *inside* the
slope rather than along its edge, and a crease lying in the middle of a surface
gets drawn - so the far gable appears through the roof. Flush, the slope's own
side edge is the rake, and it is right from every angle. The chimney is
an N-sided prism standing in for a cylinder (`chimney_facets`, default 8);
hidden-line removal hides its back edges, so it reads as round. It stands free
beside one gable end, and the hall gives up that strip of the plot to make room
for it.

The top is open: `flue` cuts a real recess into the crown - a rim of brick, the
wall down the shaft, a floor - rather than drawing a ring on a solid cap. The
mouth is then a genuine silhouette edge and the far wall down the hole picks up
the hatching. `flue_width` sets the opening as a fraction of the top radius
(default 0.6); `flue: false` caps it over solid.

Its parameters are tuned like any other model's, through `model_params`:

```json
{ "model_params": { "factory": { "chimney_chance": 1.0, "tile_rows": 6 } } }
```

## Inspecting one model

A building is about 40 px of a city, which is no way to judge whether a roof
line is right. `gen_model.py` builds a single instance on an empty plot and
frames the camera on it, reusing `gen_city.py`'s camera, light and hatching
code - so what it draws is what the city will draw.

```sh
python scripts/citybuilder/gen_model.py factory
bin/line_gl scenes/model.json        # -> svg/model.svg
```

| Flag | Meaning |
|---|---|
| `--seed S` | which instance you get; step through a few before judging a model |
| `--param NAME=VALUE` | override one of the model's `DEFAULTS` for this run, repeatable (`-p`) |
| `--size SX SZ` | the plot handed to the model, default `1 1` |
| `--ground` | draw a ground plane under it |
| `--canvas`, `--margin`, `--zoom` | framing, default `600x600` and a little slack |
| `--no-hatch`, `--hatch-spacing`, `--shade-cutoff`, `--light` | shading, same defaults as the city |
| `--out PATH` | default `scenes/model.json` |

```sh
python scripts/citybuilder/gen_model.py factory --seed 7
python scripts/citybuilder/gen_model.py factory -p chimney_chance=1 -p tile_rows=8
python scripts/citybuilder/gen_model.py box --size 1.0 0.4 --ground
```

`--size` is worth using: a plot is a slice of a block and is rarely square, and
a model that only ever gets tested on `1 1` will look wrong the moment the city
hands it a `1.0 0.4` strip.

`city_config.json` is read here too, but only for `model_params` and the
camera/light/hatch settings. Framing and everything about laying out a city -
grid, roads, plots, densities, `--out` - is ignored, since none of it means
anything to a single building.

One caveat: hatch spacing is in px **on the page**, exactly as in the city. A
building blown up to fill the sheet therefore gets far more hatch lines across
it than it ever gets in a city, so raise `--hatch-spacing` if you want to judge
the shading as it will actually plot.

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

## Configuration

Every option above can live in a JSON file instead of on the command line.
Settings are resolved in three layers, each overriding the one before it:

```
built-in defaults  <  city_config.json (then any --config FILE)  <  command line
```

`scripts/citybuilder/city_config.json` is picked up automatically whenever it
exists - no flag needed. Keys are the option names without the leading dashes;
`-` and `_` are interchangeable, so `"dead-ends"` and `"dead_ends"` both work.
Per-model parameters go under `model_params`:

```json
{
    "grid": 6,
    "density_box": 0.45,
    "density_factory": 0.2,
    "dead-ends": 0.2,
    "canvas": "600x800",
    "model_params": {
        "box": { "max_footprint": 0.95, "min_footprint": 0.7 },
        "factory": { "chimney_chance": 1.0 }
    }
}
```

The three negative flags are written either way round - `"roads": false` and
`"no_roads": true` mean the same thing. `canvas` takes `"600x800"` or
`[600, 800]`. An unrecognised key is an error rather than a silent no-op.

Anything typed on the command line still wins, so the config file sets the
house style and a flag overrides it for one run:

```sh
python scripts/citybuilder/gen_city.py                  # config file's density
python scripts/citybuilder/gen_city.py --density 0.3    # overridden for this run
python scripts/citybuilder/gen_city.py --no-config      # built-in defaults
```

`--dump-config` prints the settings actually in force, which is both a way to
see what a run resolved to and a way to seed the file in the first place:

```sh
python scripts/citybuilder/gen_city.py --no-config --dump-config     > scripts/citybuilder/city_config.json
```

`--config FILE` still accepts the old per-model-only form, `{ "box": { ... } }`,
and layers on top of `city_config.json`.

## Writing a new model

Drop a `*.py` file in `models/`. It is picked up automatically, and it brings
its own `--density-NAME` flag and config key with it - nothing in `gen_city.py`
needs to know the model exists.

```python
"""Tower - a box with a thinner box on top."""

from model_api import Geometry, Lot

NAME = "tower"          # required, unique; used by --models
DENSITY = 0.1           # optional, share of plots it gets (default 0.3)
DEFAULTS = {            # optional, tunable via model_params
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

`gen_model.py tower` will draw it on its own from the moment the file exists.

A plot is a slice of a block and is **not square** - use `sx` and `sz`, not
`size` (which is only the largest square that fits). Two helpers:

- `lot.inset(margin)` - a smaller lot, shrunk on every side.
- `lot.place(w, d, jitter)` - the min corner for a `w x d` footprint inside the
  plot; `jitter` 0 centres it, 0.5 puts it anywhere the plot allows.

`Geometry` collects primitives in **world** coordinates: `block(origin, dx, dy,
dz, col, show_edges)`, `rect(a, b, c, d, ...)` and `line(a, b, col)` — the same
primitives the scene format documents.

**Wind your quads outwards.** The renderer reads a triangle normal as
`(b - a) x (c - a)` and back-face culls before hatching, so a `rect` wound the
wrong way round draws all its edges but is never shaded — it comes out blank
next to correctly wound faces, which is easy to miss until you look at one
model on its own. `block` is safe (the renderer builds those itself); `rect` is
yours to get right. `factory.py` routes every quad through a `_face` helper
that flips the winding, and the edge flags with it, whenever the normal ends up
pointing into the solid. `show_edges` on a block is the 12-entry
list `[bottom x4, top x4, vertical x4]`; leave it out to draw all edges.

Every primitive returned by one `build()` call is stamped with a shared
`group_id`, so the renderer does not draw intersection seams *inside* a
building — stacked and overlapping parts of one model come out clean.
