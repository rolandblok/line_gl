#!/usr/bin/env python3
"""
Model registry: discovers every model module in this directory.

A model module is any `*.py` file here that does not start with `_`, and that
defines NAME and build() as described in `model_api.py`.
"""

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

_HERE = Path(__file__).resolve().parent
_PARENT = _HERE.parent
if str(_PARENT) not in sys.path:          # so models can `from model_api import ...`
    sys.path.insert(0, str(_PARENT))

from model_api import Geometry, Lot  # noqa: E402


@dataclass
class ModelSpec:
    name: str
    build: Callable[[Lot], Geometry]
    density: float = 0.3          # module DENSITY: share of plots this model gets
    weight: float = 1.0           # multiplier from `--models name:weight`
    defaults: dict[str, Any] = field(default_factory=dict)
    doc: str = ""
    path: Path = _HERE


def _load_module(path: Path):
    mod_name = f"citymodels.{path.stem}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load model module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def load_models(directory: Path | None = None) -> dict[str, ModelSpec]:
    """Import every model module and return {name: ModelSpec}, sorted by name."""
    directory = Path(directory) if directory else _HERE
    models: dict[str, ModelSpec] = {}

    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module = _load_module(path)
        name = getattr(module, "NAME", None)
        build = getattr(module, "build", None)
        if name is None or build is None:
            continue  # not a model module
        if name in models:
            raise ValueError(f"duplicate model name '{name}' in {path}")
        models[name] = ModelSpec(
            name=name,
            build=build,
            density=float(getattr(module, "DENSITY", 0.3)),
            defaults=dict(getattr(module, "DEFAULTS", {})),
            doc=(module.__doc__ or "").strip().splitlines()[0] if module.__doc__ else "",
            path=path,
        )
    return models
