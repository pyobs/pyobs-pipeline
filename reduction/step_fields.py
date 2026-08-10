"""Introspects pyobs-core processor classes to generate pipeline-builder form fields."""

import functools
import importlib
import inspect
import pkgutil
import types
import typing
from typing import Any

from pyobs.images.processor import ImageProcessor
from pyobs.object import get_class_from_string

# Fields with a fixed set of allowed values that inspect.signature can't recover on its
# own (their annotation is just `str`) -- rendered as a <select> instead of a text input.
_CHOICE_FIELDS = {"on_error": sorted(ImageProcessor.VALID_ERROR_MODES)}

# Builder-only default overrides for a freshly-added (not yet configured) step -- the
# value pre-selected in the form, not a change to pyobs-core's own ImageProcessor
# default ("raise"). A step only gets this value if it's actually saved with it.
_DEFAULT_OVERRIDES = {"on_error": "error"}


@functools.lru_cache(maxsize=1)
def discover_step_templates() -> list[str]:
    """All concrete (non-abstract) pyobs.images.ImageProcessor subclasses under
    pyobs.images.processors, for the "Add step" dropdown. Not the only valid values for
    PipelineStep.step_class -- any importable dotted path works (see "custom step_class"
    in the template), this just saves hunting for one.

    Walks the package tree rather than hardcoding a list, so it stays in sync with
    pyobs-core as processors are added/removed. Each processors subpackage's __init__.py
    already re-exports its concrete classes with a matching __module__ override (e.g.
    Flip.__module__ == "pyobs.images.processors.image", which really does import Flip --
    unlike pyobs.utils.archive's __module__ trick, see reduction/tasks.py's note), so no
    separate registry is needed in pyobs-core for this.
    """
    import pyobs.images.processors as processors_pkg
    from pyobs.images.processor import ImageProcessor

    found: set[str] = set()
    for _, name, _ in pkgutil.walk_packages(processors_pkg.__path__, processors_pkg.__name__ + "."):
        if name.rsplit(".", 1)[-1].startswith("_"):
            continue
        try:
            module = importlib.import_module(name)
        except ImportError:
            continue  # an optional pyobs-core extra isn't installed -- skip, not fatal
        for obj in vars(module).values():
            if (
                inspect.isclass(obj)
                and issubclass(obj, ImageProcessor)
                and obj is not ImageProcessor
                and not inspect.isabstract(obj)
            ):
                found.add(f"{obj.__module__}.{obj.__name__}")
    return sorted(found)


def _unwrap_optional(annotation: Any) -> Any:
    """`X | None` / `Optional[X]` -> X. Anything else passes through unchanged."""
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def _map_type(annotation: Any) -> str:
    if annotation is inspect.Parameter.empty:
        return "json"
    annotation = _unwrap_optional(annotation)
    if annotation is bool:
        return "boolean"
    if annotation is int:
        return "integer"
    if annotation is float:
        return "number"
    if annotation is str:
        return "text"
    return "json"


def _base_processor_params() -> dict[str, inspect.Parameter]:
    """ImageProcessor.__init__'s own params (currently just on_error). Most concrete
    processors declare their own __init__ ending in **kwargs and never redeclare these
    themselves -- inspect.signature(cls.__init__) alone would then miss them entirely,
    since they're swallowed into that **kwargs rather than appearing in the signature.
    A few processors (e.g. AstrometryDotNet) do redeclare on_error explicitly; those
    keep their own declaration, see get_step_fields's use of setdefault below."""
    sig = inspect.signature(ImageProcessor.__init__, eval_str=True)
    return {name: param for name, param in sig.parameters.items() if name != "self"}


def get_step_fields(step_class_path: str) -> list[dict[str, Any]]:
    """Introspect a processor class and return form field definitions.

    Example:
        get_step_fields("pyobs.images.processors.calibration.Calibration")
        -> [{"name": "max_cache_size", "type": "integer", "default": 20, "label": "Max Cache Size"},
            {"name": "require_bias", "type": "boolean", "default": True, "label": "Require Bias"},
            ...,
            {"name": "on_error", "type": "choices", "choices": ["error", "ignore", "info", "raise"], ...}]
    """
    cls = get_class_from_string(step_class_path)
    # eval_str=True resolves string annotations from `from __future__ import annotations`
    # (used throughout pyobs-core) back into real type objects.
    sig = inspect.signature(cls.__init__, eval_str=True)
    params = dict(sig.parameters)
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        for name, param in _base_processor_params().items():
            params.setdefault(name, param)

    fields = []
    for name, param in params.items():
        if name in ("self", "kwargs", "args"):
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        if name == "archive":
            # Not user-configurable here -- pyobs-core's Pipeline auto-fills a step's
            # archive from the site's own configured archive when the step doesn't set
            # one itself (see reduction/tasks.py's build_reduction_config, which never
            # writes an "archive" key into a step's config). Hide it rather than let an
            # operator redundantly (or inconsistently) re-specify it per step.
            continue
        default = param.default if param.default is not inspect.Parameter.empty else None
        default = _DEFAULT_OVERRIDES.get(name, default)
        field = {
            "name": name,
            "type": _map_type(param.annotation),
            "default": default,
            "label": name.replace("_", " ").title(),
            "required": param.default is inspect.Parameter.empty,
        }
        if name in _CHOICE_FIELDS:
            field["type"] = "choices"
            field["choices"] = _CHOICE_FIELDS[name]
        fields.append(field)
    return fields
