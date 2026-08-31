#!/usr/bin/env python3
"""
Single-model inspector for the citybuilder.

Builds one instance of one model on an empty plot and frames the camera on it,
so the model fills the page instead of being 40 px of a city. Everything else -
the isometric camera, the light, the hatching rule - is the same code
`gen_city.py` uses, so what you see here is what the city will draw.

Usage:
    python scripts/citybuilder/gen_model.py factory      # -> scenes/model.json
    bin/line_gl scenes/model.json                        # -> svg/model.svg

    python scripts/citybuilder/gen_model.py --list-models
    python scripts/citybuilder/gen_model.py factory --seed 7
    python scripts/citybuilder/gen_model.py factory -p chimney_chance=1 -p tile_rows=8
    python scripts/citybuilder/gen_model.py box --size 1.0 0.4 --ground

`--seed` picks which instance you get - a model is random, so step through a few
seeds before deciding it is right. `--param` overrides one of the model's own
DEFAULTS for this run only; `scripts/citybuilder/city_config.json` is read too,
but only for `model_params` and the camera/light/hatch settings, since grids and
densities mean nothing to a single building.

Hatch spacing is in px on the page, exactly as in the city. Filling the page
with one building therefore gives it far more hatch lines than it gets in a
city - raise `--hatch-spacing` to compare like with like.
"""

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gen_city                                    # noqa: E402
from model_api import Lot                          # noqa: E402
from models import load_models                     # noqa: E402

# What a shared city config may hand to this tool: the camera angles, the light
# and the shading rule, so a model looks here exactly as it will in the city.
# Framing (canvas, margin, zoom) is deliberately left out - a city is framed
# portrait around a grid, a single building is not - and so is everything about
# laying out a city: grid, roads, plots, densities, --out.
INHERIT = {"azimuth", "elevation", "light",
           "hatch", "hatch_spacing", "shade_cutoff", "ground", "ground_drop"}


def parse_param(text):
    """`tile_rows=8` -> ("tile_rows", 8). Values are JSON, or a bare string."""
    name, sep, raw = str(text).partition("=")
    if not sep:
        raise SystemExit(f"--param expects NAME=VALUE, got '{text}'")
    try:
        return name.strip(), json.loads(raw)
    except json.JSONDecodeError:
        return name.strip(), raw


def add_ground(geo, args, gid):
    """The same ground plane gen_city lays under a city, sized to one model."""
    xs = [p[0] for p in geo.vertices()]
    zs = [p[2] for p in geo.vertices()]
    pad = max(max(xs) - min(xs), max(zs) - min(zs)) * 0.08
    y = -args.ground_drop                  # just below y=0, avoids coplanar seams
    ground = geo.rect([min(xs) - pad, y, min(zs) - pad], [min(xs) - pad, y, max(zs) + pad],
                      [max(xs) + pad, y, max(zs) + pad], [max(xs) + pad, y, min(zs) - pad],
                      col=[0, 0, 0], show_edges=[1, 1, 1, 1])
    ground["group_id"] = gid


def main():
    available = load_models()

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("model", nargs="?", default=None,
                        help="which model to build (see --list-models)")
    parser.add_argument("--param", "-p", action="append", default=[], metavar="NAME=VALUE",
                        help="override one of the model's DEFAULTS; repeatable")
    parser.add_argument("--size", type=float, nargs=2, default=(1.0, 1.0),
                        metavar=("SX", "SZ"),
                        help="plot the model is handed, in world units (default 1 1); "
                             "models react to the shape of a plot, not just its area")
    parser.add_argument("--seed", type=int, default=42,
                        help="which instance you get (default 42)")
    parser.add_argument("--config", type=str, default=None,
                        help=f"extra config file, layered on top of "
                             f"{gen_city.CONFIG_PATH.name} if that exists")
    parser.add_argument("--no-config", dest="no_config", action="store_true",
                        help=f"ignore {gen_city.CONFIG_PATH.name}")
    parser.add_argument("--list-models", action="store_true",
                        help="print the discovered models with their parameters and exit")
    parser.add_argument("--ground", action="store_true",
                        help="draw a ground plane under the model")
    parser.add_argument("--ground-drop", type=float, default=0.001,
                        help="how far the ground sits below y=0 (default 0.001)")
    parser.add_argument("--no-hatch", dest="hatch", action="store_false",
                        help="leave faces blank instead of shading them with hatching")
    parser.add_argument("--hatch-spacing", type=float, nargs=2, default=(12.0, 2.5),
                        metavar=("LIGHT", "DARK"),
                        help="hatch line spacing in px, brightest and darkest face "
                             "(default 12 2.5)")
    parser.add_argument("--shade-cutoff", type=float, default=0.79,
                        help="faces brighter than this stay unhatched, 0..1 (default 0.79)")
    parser.add_argument("--light", type=float, nargs=3, default=(-0.58, -0.8, -0.05),
                        metavar=("X", "Y", "Z"),
                        help="light direction (default -0.58 -0.8 -0.05)")
    parser.add_argument("--azimuth", type=float, default=gen_city.ISO_AZIMUTH,
                        help="camera yaw in degrees (default 45)")
    parser.add_argument("--elevation", type=float, default=gen_city.ISO_ELEVATION,
                        help="camera pitch in degrees (default 35.264 = true isometric)")
    parser.add_argument("--canvas", type=str, default="600x600",
                        help="output canvas in px, WxH (default 600x600)")
    parser.add_argument("--margin", type=float, default=1.12,
                        help="framing slack around the model, 1.0 = edge to edge "
                             "(default 1.12)")
    parser.add_argument("--zoom", type=float, default=1.0,
                        help="extra zoom factor; >1 zooms out (default 1.0)")
    parser.add_argument("--out", type=str, default="scenes/model.json",
                        help="output scene path (default scenes/model.json)")

    # Defaults < config file < command line, same as gen_city. Only the settings
    # in INHERIT are taken; --out especially must not come from a city config.
    known = set(vars(parser.parse_args([])))
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config")
    pre.add_argument("--no-config", dest="no_config", action="store_true")
    pre_args, _ = pre.parse_known_args()
    file_opts, model_params, sources = gen_city.read_configs(
        pre_args.config, not pre_args.no_config, known, extra_ok=True)
    parser.set_defaults(**{k: v for k, v in file_opts.items() if k in INHERIT})

    args = parser.parse_args()
    args.canvas = gen_city.parse_canvas(args.canvas)

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

    if not available:
        raise SystemExit("no models found in scripts/citybuilder/models/")
    if args.model is None:
        raise SystemExit("which model? one of: " + ", ".join(available))
    if args.model not in available:
        raise SystemExit(f"unknown model '{args.model}'. Available: "
                         + ", ".join(available))

    spec = available[args.model]
    params = gen_city.resolve_params([spec], model_params)[spec.name]
    overrides = dict(parse_param(p) for p in args.param)
    unknown = set(overrides) - set(params)
    if unknown:
        print(f"warning: model '{spec.name}' has no parameter(s) {sorted(unknown)} "
              f"- passing them through anyway", file=sys.stderr)
    params.update(overrides)

    sx, sz = args.size
    lot = Lot(ix=0, iz=0, plot=0, x0=-sx / 2.0, z0=-sz / 2.0, sx=sx, sz=sz, y=0.0,
              rng=random.Random(f"{args.seed}:model:{spec.name}"), params=params)
    geo = spec.build(lot)
    if geo.is_empty():
        raise SystemExit(f"model '{spec.name}' built nothing on a {sx:g}x{sz:g} plot")
    geo.stamp_group(0)                     # no seam lines inside the building

    cam, _view = gen_city.fit_camera(geo, args)
    if args.ground:
        add_ground(geo, args, 1)
    scene = gen_city.build_scene(geo, cam, args)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(scene, indent=4))

    shown = ", ".join(f"{k}={v}" for k, v in sorted(params.items()))
    print(f"{spec.name} seed {args.seed} on a {sx:g}x{sz:g} plot: {len(geo)} primitives")
    print(f"    {shown}")
    print(f"Camera: azimuth {args.azimuth:g}, elevation {args.elevation:.3f} deg, "
          f"canvas {args.canvas[0]:g}x{args.canvas[1]:g} px"
          f"{'' if args.hatch else ', no hatching'}")
    if sources:
        print("Config: " + ", ".join(gen_city._short(s) for s in sources))
    print(f"Written to {out_path}")


if __name__ == "__main__":
    main()
