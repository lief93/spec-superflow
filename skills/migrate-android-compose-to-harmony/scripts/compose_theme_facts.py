"""Validation for one runtime-resolved Android Compose Material theme."""
from __future__ import annotations

import re
from typing import Any

from page_snapshot import PageSnapshotError


SCHEMA = "android-to-harmony.compose-theme-facts.v1"
TOKEN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,119}$")
COLOR = re.compile(r"^#[0-9A-F]{8}$")
TYPOGRAPHY_FIELDS = {
    "font_size_sp",
    "font_weight",
    "font_style",
    "font_family",
    "letter_spacing_sp",
    "line_height_sp",
}


def _token(value: Any, label: str) -> str:
    if not isinstance(value, str) or TOKEN.fullmatch(value) is None:
        raise PageSnapshotError(f"{label} must be a bounded identifier")
    return value


def _number(value: Any, label: str, *, minimum: float = 0.0) -> float | None:
    if value is None:
        return None
    if type(value) not in {int, float} or not minimum <= float(value) < 10000:
        raise PageSnapshotError(f"{label} must be a finite number >= {minimum}")
    return round(float(value), 3)


def _text(value: Any, label: str, maximum: int = 500) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise PageSnapshotError(f"{label} must be non-empty bounded text")
    if any(ord(character) < 32 and character not in "\r\n\t" for character in value):
        raise PageSnapshotError(f"{label} contains unsupported control characters")
    return value


def validate_compose_theme_facts(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != {
        "schema", "platform", "theme_id", "capture", "theme", "provenance", "unresolved"
    }:
        raise PageSnapshotError("Compose theme facts have unsupported root fields")
    if payload["schema"] != SCHEMA:
        raise PageSnapshotError("Compose theme facts schema is unsupported")
    if payload["platform"] != "android":
        raise PageSnapshotError("Compose theme facts platform must be android")
    theme_id = _token(payload["theme_id"], "theme_id")

    capture = payload["capture"]
    if not isinstance(capture, dict) or set(capture) != {
        "sdk_int", "density", "font_scale", "layout_direction"
    }:
        raise PageSnapshotError("Compose theme facts capture is malformed")
    sdk_int = capture["sdk_int"]
    if type(sdk_int) is not int or not 1 <= sdk_int <= 1000:
        raise PageSnapshotError("capture.sdk_int must be a positive integer")
    density = _number(capture["density"], "capture.density", minimum=0.001)
    font_scale = _number(capture["font_scale"], "capture.font_scale", minimum=0.001)
    layout_direction = capture["layout_direction"]
    if layout_direction not in {"ltr", "rtl"}:
        raise PageSnapshotError("capture.layout_direction must be ltr or rtl")

    theme = payload["theme"]
    if not isinstance(theme, dict) or set(theme) != {"colors", "typography", "shapes"}:
        raise PageSnapshotError("Compose theme facts theme is malformed")
    colors = theme["colors"]
    if not isinstance(colors, dict) or len(colors) > 100:
        raise PageSnapshotError("theme.colors must be a bounded object")
    normalized_colors: dict[str, str] = {}
    for name, color in colors.items():
        role = _token(name, "theme color role")
        if not isinstance(color, str) or COLOR.fullmatch(color) is None:
            raise PageSnapshotError("theme color must use #AARRGGBB")
        normalized_colors[role] = color

    typography = theme["typography"]
    if not isinstance(typography, dict) or len(typography) > 100:
        raise PageSnapshotError("theme.typography must be a bounded object")
    normalized_typography: dict[str, dict[str, Any]] = {}
    for name, style in typography.items():
        role = _token(name, "theme typography role")
        if not isinstance(style, dict) or set(style) != TYPOGRAPHY_FIELDS:
            raise PageSnapshotError(f"theme typography role {role} is malformed")
        weight = style["font_weight"]
        if weight is not None and (type(weight) is not int or not 1 <= weight <= 1000):
            raise PageSnapshotError(f"theme typography role {role} font_weight is invalid")
        normalized_typography[role] = {
            "font_size_sp": _number(style["font_size_sp"], f"{role}.font_size_sp"),
            "font_weight": weight,
            "font_style": _text(style["font_style"], f"{role}.font_style", 120),
            "font_family": _text(style["font_family"], f"{role}.font_family", 240),
            "letter_spacing_sp": _number(style["letter_spacing_sp"], f"{role}.letter_spacing_sp", minimum=-1000),
            "line_height_sp": _number(style["line_height_sp"], f"{role}.line_height_sp"),
        }

    shapes = theme["shapes"]
    if not isinstance(shapes, dict) or len(shapes) > 100:
        raise PageSnapshotError("theme.shapes must be a bounded object")
    normalized_shapes: dict[str, dict[str, str]] = {}
    for name, shape in shapes.items():
        role = _token(name, "theme shape role")
        if not isinstance(shape, dict) or set(shape) != {"runtime_type", "description"}:
            raise PageSnapshotError(f"theme shape role {role} is malformed")
        normalized_shapes[role] = {
            "runtime_type": _token(shape["runtime_type"], f"{role}.runtime_type"),
            "description": _text(shape["description"], f"{role}.description", 500),
        }

    provenance = payload["provenance"]
    if not isinstance(provenance, list) or len(provenance) > 100:
        raise PageSnapshotError("Compose theme provenance must be a bounded list")
    normalized_provenance = []
    for item in provenance:
        if not isinstance(item, dict) or set(item) != {"paths", "origin", "source"}:
            raise PageSnapshotError("Compose theme provenance entry is malformed")
        paths = item["paths"]
        if not isinstance(paths, list) or not paths or any(
            path not in {"theme.colors", "theme.typography", "theme.shapes"} for path in paths
        ):
            raise PageSnapshotError("Compose theme provenance paths are malformed")
        if item["origin"] != "runtime":
            raise PageSnapshotError("Compose theme provenance origin must be runtime")
        normalized_provenance.append({
            "paths": list(paths),
            "origin": "runtime",
            "source": _text(item["source"], "Compose theme provenance source", 240),
        })

    unresolved = payload["unresolved"]
    if not isinstance(unresolved, list) or len(unresolved) > 1000:
        raise PageSnapshotError("Compose theme unresolved must be a bounded list")
    normalized_unresolved = []
    for item in unresolved:
        if not isinstance(item, dict) or set(item) != {"path", "expression", "reason"}:
            raise PageSnapshotError("Compose theme unresolved entry is malformed")
        path = item["path"]
        if not isinstance(path, str) or not path.startswith("theme.") or len(path) > 240:
            raise PageSnapshotError("Compose theme unresolved path is malformed")
        normalized_unresolved.append({
            "path": path,
            "expression": _text(item["expression"], "Compose theme unresolved expression"),
            "reason": _text(item["reason"], "Compose theme unresolved reason", 1000),
        })

    return {
        "schema": SCHEMA,
        "platform": "android",
        "theme_id": theme_id,
        "capture": {
            "sdk_int": sdk_int,
            "density": density,
            "font_scale": font_scale,
            "layout_direction": layout_direction,
        },
        "theme": {
            "colors": normalized_colors,
            "typography": normalized_typography,
            "shapes": normalized_shapes,
        },
        "provenance": normalized_provenance,
        "unresolved": normalized_unresolved,
    }
