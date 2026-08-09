"""Introspects pyobs-core processor classes to generate pipeline-builder form fields."""

import inspect
import types
import typing
from typing import Any

from pyobs.object import get_class_from_string

# Curated list of commonly used processors for the "Add step" dropdown. Not the only
# valid values for PipelineStep.step_class -- any importable dotted path works, this is
# just what's offered as a shortcut. See "custom step_class" entry in the template.
KNOWN_STEP_TEMPLATES = [
    "pyobs.images.processors.calibration.Calibration",
    "pyobs.images.processors.detection.SepSourceDetection",
    "pyobs.images.processors.detection.DaophotSourceDetection",
    "pyobs.images.processors.detection.SimpleDisk",
    "pyobs.images.processors.astrometry.AstrometryDotNet",
    "pyobs.images.processors.image.Flip",
    "pyobs.images.processors.image.SoftBin",
    "pyobs.images.processors.image.AddFitsHeaders",
    "pyobs.images.processors.image.SaveImage",
    "pyobs.images.processors.image.Smooth",
    "pyobs.images.processors.image.Grayscale",
]


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


def get_step_fields(step_class_path: str) -> list[dict[str, Any]]:
    """Introspect a processor class and return form field definitions.

    Example:
        get_step_fields("pyobs.images.processors.calibration.Calibration")
        -> [{"name": "archive", "type": "json", "default": None, "label": "Archive"},
            {"name": "max_cache_size", "type": "integer", "default": 20, "label": "Max Cache Size"},
            {"name": "require_bias", "type": "boolean", "default": True, "label": "Require Bias"},
            ...]
    """
    cls = get_class_from_string(step_class_path)
    # eval_str=True resolves string annotations from `from __future__ import annotations`
    # (used throughout pyobs-core) back into real type objects.
    sig = inspect.signature(cls.__init__, eval_str=True)
    fields = []
    for name, param in sig.parameters.items():
        if name in ("self", "kwargs", "args"):
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        default = param.default if param.default is not inspect.Parameter.empty else None
        fields.append(
            {
                "name": name,
                "type": _map_type(param.annotation),
                "default": default,
                "label": name.replace("_", " ").title(),
                "required": param.default is inspect.Parameter.empty,
            }
        )
    return fields
