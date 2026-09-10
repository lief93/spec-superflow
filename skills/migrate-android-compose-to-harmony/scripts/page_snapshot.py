#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import reprlib
import struct
import sys
import tempfile
from pathlib import Path
from typing import Any


PAGE_SCHEMA = "android-to-harmony.page-snapshot.v2"
COMPONENT_SCHEMA = "android-to-harmony.component-bounds.v1"
COMPONENT_SCHEMA_V2 = "android-to-harmony.component-bounds.v2"
SOURCE_ATTRIBUTE_SCHEMA = "android-to-harmony.source-attribute-inventory.v1"
VISUAL_FACTS_SCHEMA = "android-to-harmony.component-visual-facts.v1"
COMMAND_SCHEMA = "android-to-harmony.command-result.v1"
SAFE_TOKEN = re.compile(r"^[A-Za-z0-9._:/#@-]{1,120}$")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_JSON_BYTES = 10 * 1024 * 1024
COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
STYLE_SECTIONS: dict[str, tuple[str, ...]] = {
    "layout": (
        "padding_dp", "margin_dp", "layout_direction", "z_index", "alignment",
        "horizontal_arrangement", "vertical_arrangement", "aspect_ratio",
        "width_dp", "height_dp",
    ),
    "surface": ("background", "corner_radius_dp", "corner_sizes", "border", "shadows", "alpha", "clip"),
    "typography": (
        "font_size_sp", "font_weight", "font_style", "font_family", "letter_spacing_sp",
        "line_height_sp", "text_align", "max_lines", "overflow", "color", "decoration",
        "soft_wrap", "min_lines", "baseline_shift",
        "include_font_padding", "line_height_alignment", "line_height_trim",
        "line_break",
    ),
    "asset": (
        "resource", "sha256", "width_px", "height_px", "width_dp", "height_dp",
        "content_scale", "tint",
    ),
    "transform": (
        "translation_x_dp", "translation_y_dp", "scale_x", "scale_y", "rotation_degrees",
    ),
    "state": ("visible", "enabled", "selected", "checked", "clickable", "refreshing", "focusable"),
    "content": ("text", "placeholder", "content_description", "role", "locale"),
    "input": ("single_line", "read_only", "password", "keyboard_type", "ime_action"),
    "control": ("value", "minimum", "maximum", "steps", "active_color", "inactive_color", "stroke_width_dp"),
}


class PageSnapshotError(RuntimeError):
    pass


def actual_value(value: Any) -> str:
    preview = reprlib.Repr()
    preview.maxstring = preview.maxother = 240
    preview.maxlist = preview.maxtuple = preview.maxdict = 3
    preview.maxlevel = 2
    details = [f'type={type(value).__name__}']
    if isinstance(value, (str, list, tuple, dict)):
        details.append(f'length={len(value)}')
    if isinstance(value, str):
        positions = []
        for index, char in enumerate(value):
            if ord(char) < 32:
                positions.append(index)
                if len(positions) == 5:
                    break
        if positions:
            details.append(f'control_positions={positions}')
    return f'actual={preview.repr(value)} ({", ".join(details)}; preview may be truncated)'


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_input(path: Path, label: str, max_bytes: int | None = None) -> Path:
    resolved = Path(os.path.abspath(os.path.expanduser(str(path))))
    if resolved.is_symlink() or not resolved.is_file():
        raise PageSnapshotError(f"{label} must be an existing non-symbolic-link file")
    size = resolved.stat().st_size
    if size <= 0:
        raise PageSnapshotError(f"{label} must not be empty")
    if max_bytes is not None and size > max_bytes:
        raise PageSnapshotError(f"{label} exceeds {max_bytes} bytes")
    return resolved


def load_json(path: Path, label: str) -> tuple[dict[str, Any], Path]:
    resolved = resolve_input(path, label, MAX_JSON_BYTES)
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PageSnapshotError(f"{label} is not valid UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise PageSnapshotError(f"{label} root must be an object")
    return payload, resolved


def require_token(value: Any, label: str) -> str:
    if not isinstance(value, str) or SAFE_TOKEN.fullmatch(value) is None:
        raise PageSnapshotError(f"{label} must use 1 to 120 identifier characters; {actual_value(value)}")
    return value


def finite_number(value: Any, label: str, minimum: float | None = None) -> float:
    if type(value) not in {int, float} or not isinstance(value, (int, float)):
        raise PageSnapshotError(f"{label} must be a finite number; {actual_value(value)}")
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")}:
        raise PageSnapshotError(f"{label} must be a finite number; {actual_value(value)}")
    if minimum is not None and number < minimum:
        raise PageSnapshotError(f"{label} must be at least {minimum}; {actual_value(value)}")
    return round(number, 3)


def optional_number(value: Any, label: str, minimum: float | None = None) -> float | None:
    return None if value is None else finite_number(value, label, minimum)


def bounded_string(value: Any, label: str, maximum: int = 500) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise PageSnapshotError(f"{label} must be a non-empty printable string (maximum {maximum}); {actual_value(value)}")
    return value


def display_string(value: Any, label: str, maximum: int = 10000) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > maximum or "\x00" in value:
        raise PageSnapshotError(f"{label} must be a bounded UTF-8 display string (maximum {maximum}); {actual_value(value)}")
    return value


def optional_enum(value: Any, label: str, choices: set[str]) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or value not in choices:
        raise PageSnapshotError(f"{label} is unsupported; {actual_value(value)}")
    return value


def optional_color(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or COLOR_PATTERN.fullmatch(value) is None:
        raise PageSnapshotError(f"{label} must be #RRGGBB or #AARRGGBB; {actual_value(value)}")
    return value.upper()


def normalize_edges(value: Any, label: str) -> dict[str, float] | None:
    if value is None:
        return None
    fields = {"left", "top", "right", "bottom"}
    if not isinstance(value, dict) or set(value) != fields:
        raise PageSnapshotError(f"{label} must contain left, top, right, and bottom")
    return {field: finite_number(value[field], f"{label}.{field}") for field in fields}


def normalize_corner_radius(value: Any, label: str) -> dict[str, float] | None:
    if value is None:
        return None
    fields = {"top_left", "top_right", "bottom_right", "bottom_left"}
    if not isinstance(value, dict) or set(value) != fields:
        raise PageSnapshotError(f"{label} must contain all four corners")
    return {
        field: finite_number(value[field], f"{label}.{field}", 0.0)
        for field in fields
    }


def normalize_point(value: Any, label: str) -> dict[str, float] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"x", "y"}:
        raise PageSnapshotError(f"{label} must contain x and y")
    return {axis: finite_number(value[axis], f"{label}.{axis}") for axis in ("x", "y")}


def normalize_background(value: Any, label: str) -> dict[str, Any] | None:
    if value is None:
        return None
    allowed = {
        "type", "color", "colors", "stops", "angle_degrees", "center", "radius_dp",
        "resource", "tile_mode", "direction",
    }
    if not isinstance(value, dict) or "type" not in value or not set(value).issubset(allowed):
        raise PageSnapshotError(f"{label} is malformed")
    kind = optional_enum(
        value["type"], f"{label}.type",
        {"none", "solid", "linear_gradient", "radial_gradient", "sweep_gradient", "image", "resource"},
    )
    if kind is None:
        raise PageSnapshotError(f"{label}.type is required")
    result: dict[str, Any] = {"type": kind}
    if "color" in value:
        result["color"] = optional_color(value["color"], f"{label}.color")
    if "colors" in value:
        colors = value["colors"]
        if not isinstance(colors, list) or len(colors) < 2 or len(colors) > 32:
            raise PageSnapshotError(f"{label}.colors must contain 2 to 32 colors")
        result["colors"] = [optional_color(color, f"{label}.colors") for color in colors]
    if "stops" in value:
        stops = value["stops"]
        if not isinstance(stops, list) or not 2 <= len(stops) <= 32:
            raise PageSnapshotError(f"{label}.stops must contain 2 to 32 values")
        result["stops"] = [finite_number(stop, f"{label}.stops", 0.0) for stop in stops]
        if any(stop > 1 for stop in result["stops"]):
            raise PageSnapshotError(f"{label}.stops must be between 0 and 1")
    if "angle_degrees" in value:
        result["angle_degrees"] = optional_number(value["angle_degrees"], f"{label}.angle_degrees")
    if 'direction' in value:
        result['direction'] = optional_enum(value['direction'], f'{label}.direction', {'right_bottom'})
        if 'angle_degrees' in value:
            raise PageSnapshotError(f'{label} cannot mix gradient direction and angle')
    if "center" in value:
        result["center"] = normalize_point(value["center"], f"{label}.center")
    if "radius_dp" in value:
        result["radius_dp"] = optional_number(value["radius_dp"], f"{label}.radius_dp", 0.0)
    if "resource" in value:
        result["resource"] = bounded_string(value["resource"], f"{label}.resource", 240)
    if "tile_mode" in value:
        result["tile_mode"] = optional_enum(
            value["tile_mode"], f"{label}.tile_mode", {"clamp", "repeat", "mirror", "decal"}
        )
    if kind == "solid" and result.get("color") is None:
        raise PageSnapshotError(f"{label}.color is required for a solid background")
    if kind in {"linear_gradient", "radial_gradient", "sweep_gradient"} and "colors" not in result:
        raise PageSnapshotError(f"{label}.colors are required for a gradient background")
    if kind in {"linear_gradient", "radial_gradient", "sweep_gradient"}:
        if None in result['colors']:
            raise PageSnapshotError(f"{label}.colors cannot contain null")
        stops = result.get('stops')
        if stops is not None and (len(stops) != len(result['colors']) or stops != sorted(stops)):
            raise PageSnapshotError(f"{label}.stops must be ordered and match colors")
    if kind in {"image", "resource"} and "resource" not in result:
        raise PageSnapshotError(f"{label}.resource is required for a resource background")
    return result


def normalize_border(value: Any, label: str) -> dict[str, Any] | None:
    if value is None:
        return None
    allowed = {"width_dp", "color", "style", "dash_dp", "edges"}
    if not isinstance(value, dict) or not set(value).issubset(allowed):
        raise PageSnapshotError(f"{label} is malformed")
    result: dict[str, Any] = {}
    if "width_dp" in value:
        result["width_dp"] = optional_number(value["width_dp"], f"{label}.width_dp", 0.0)
    if "color" in value:
        result["color"] = optional_color(value["color"], f"{label}.color")
    if "style" in value:
        result["style"] = optional_enum(value["style"], f"{label}.style", {"solid", "dashed", "dotted", "none"})
    if "dash_dp" in value:
        dash = value["dash_dp"]
        if not isinstance(dash, list) or not dash or len(dash) > 16:
            raise PageSnapshotError(f"{label}.dash_dp must be a non-empty list")
        result["dash_dp"] = [finite_number(item, f"{label}.dash_dp", 0.0) for item in dash]
    if "edges" in value:
        edges = value["edges"]
        if not isinstance(edges, dict) or not set(edges).issubset({"left", "top", "right", "bottom"}):
            raise PageSnapshotError(f"{label}.edges is malformed")
        result["edges"] = {
            edge: normalize_border(edge_value, f"{label}.edges.{edge}")
            for edge, edge_value in edges.items()
        }
    return result


def normalize_shadows(value: Any, label: str) -> list[dict[str, Any]] | None:
    if value is None:
        return None
    fields = {"color", "offset_x_dp", "offset_y_dp", "blur_radius_dp", "spread_radius_dp"}
    if not isinstance(value, list) or len(value) > 16:
        raise PageSnapshotError(f"{label} must be a list")
    result: list[dict[str, Any]] = []
    for index, shadow in enumerate(value):
        if not isinstance(shadow, dict) or set(shadow) != fields:
            raise PageSnapshotError(f"{label}[{index}] is malformed")
        result.append(
            {
                "color": optional_color(shadow["color"], f"{label}[{index}].color"),
                "offset_x_dp": finite_number(shadow["offset_x_dp"], f"{label}[{index}].offset_x_dp"),
                "offset_y_dp": finite_number(shadow["offset_y_dp"], f"{label}[{index}].offset_y_dp"),
                "blur_radius_dp": finite_number(shadow["blur_radius_dp"], f"{label}[{index}].blur_radius_dp", 0.0),
                "spread_radius_dp": finite_number(shadow["spread_radius_dp"], f"{label}[{index}].spread_radius_dp"),
            }
        )
    return result


def empty_style() -> dict[str, dict[str, Any]]:
    return {
        section: {field: None for field in fields}
        for section, fields in STYLE_SECTIONS.items()
    }


def normalize_style(value: Any, label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict) or not set(value).issubset(STYLE_SECTIONS):
        raise PageSnapshotError(f"{label} has unsupported sections")
    result = empty_style()
    for section, raw_section in value.items():
        if not isinstance(raw_section, dict) or not set(raw_section).issubset(STYLE_SECTIONS[section]):
            raise PageSnapshotError(f"{label}.{section} has unsupported fields")
        target = result[section]
        for field, raw in raw_section.items():
            path = f"{label}.{section}.{field}"
            if field in {"padding_dp", "margin_dp"}:
                target[field] = normalize_edges(raw, path)
            elif field == "corner_radius_dp":
                target[field] = normalize_corner_radius(raw, path)
            elif field == 'corner_sizes':
                if raw is None:
                    continue
                if not isinstance(raw, dict) or set(raw) != {'top_left', 'top_right', 'bottom_right', 'bottom_left'}:
                    raise PageSnapshotError(f'{path} must contain four physical corners')
                corners = {}
                for name, size in raw.items():
                    if not isinstance(size, dict) or set(size) != {'unit', 'value'} or size['unit'] not in {'dp', 'px', 'percent'}:
                        raise PageSnapshotError(f'{path}.{name} has an invalid corner unit')
                    number = finite_number(size['value'], f'{path}.{name}.value', 0)
                    if size['unit'] == 'percent' and number > 100:
                        raise PageSnapshotError(f'{path}.{name} percent exceeds 100')
                    corners[name] = {'unit': size['unit'], 'value': number}
                target[field] = corners
            elif field == "background":
                target[field] = normalize_background(raw, path)
            elif field == "border":
                target[field] = normalize_border(raw, path)
            elif field == "shadows":
                target[field] = normalize_shadows(raw, path)
            elif field in {"visible", "enabled", "selected", "checked", "clickable", "refreshing", "focusable", "clip", "single_line", "read_only", "password", "soft_wrap", "include_font_padding"}:
                if raw is not None and type(raw) is not bool:
                    raise PageSnapshotError(f"{path} must be a boolean")
                target[field] = raw
            elif field == "alpha":
                target[field] = optional_number(raw, path, 0.0)
                if target[field] is not None and target[field] > 1:
                    raise PageSnapshotError(f"{path} must be between 0 and 1")
            elif section == 'control':
                if field in {'active_color', 'inactive_color'}:
                    target[field] = optional_color(raw, path)
                else:
                    target[field] = optional_number(raw, path, 0 if field in {'steps', 'stroke_width_dp'} else None)
                    if field == 'steps' and raw is not None and float(raw) != int(raw):
                        raise PageSnapshotError(f'{path} must be an integer')
            elif field == "layout_direction":
                target[field] = optional_enum(raw, path, {"ltr", "rtl"})
            elif field == 'keyboard_type':
                target[field] = optional_enum(raw, path, {'text', 'number', 'phone', 'email', 'url', 'decimal', 'password', 'number_password'})
            elif field == 'ime_action':
                target[field] = optional_enum(raw, path, {'default', 'none', 'go', 'search', 'send', 'next', 'done', 'previous'})
            elif field in {"font_style"}:
                target[field] = optional_enum(raw, path, {"normal", "italic"})
            elif field == 'line_height_alignment':
                target[field] = optional_enum(raw, path, {'center', 'top', 'bottom', 'proportional'})
            elif field == 'line_height_trim':
                target[field] = optional_enum(raw, path, {'none', 'both', 'first_line_top', 'last_line_bottom'})
            elif field == 'line_break':
                target[field] = optional_enum(raw, path, {'simple', 'heading', 'paragraph'})
            elif field in {"text_align"}:
                target[field] = optional_enum(raw, path, {"start", "center", "end", "justify"})
            elif field in {"overflow"}:
                target[field] = optional_enum(raw, path, {"clip", "ellipsis", "visible"})
            elif field in {"content_scale"}:
                target[field] = optional_enum(raw, path, {"fit", "crop", "fill", "inside", "none"})
            elif field in {"color", "tint"}:
                target[field] = optional_color(raw, path)
            elif field == "sha256":
                if raw is not None and (not isinstance(raw, str) or SHA256_PATTERN.fullmatch(raw) is None):
                    raise PageSnapshotError(f"{path} must be a lowercase SHA-256")
                target[field] = raw
            elif field in {"resource", "font_family"}:
                target[field] = None if raw is None else bounded_string(raw, path, 240)
            elif section == "content" and field in {"text", "placeholder", "content_description"}:
                target[field] = display_string(raw, path)
            elif section == "content" and field in {"role", "locale"}:
                target[field] = None if raw is None else bounded_string(raw, path, 120)
            elif field in {
                "alignment", "horizontal_arrangement", "vertical_arrangement", "decoration"
            }:
                target[field] = None if raw is None else bounded_string(raw, path, 120)
            elif field in {"width_px", "height_px", "max_lines", "min_lines"}:
                if raw is not None and (type(raw) is not int or raw <= 0):
                    raise PageSnapshotError(f"{path} must be a positive integer")
                target[field] = raw
            elif field == "font_weight":
                if raw is not None and (type(raw) is not int or not 1 <= raw <= 1000):
                    raise PageSnapshotError(f"{path} must be an integer from 1 to 1000")
                target[field] = raw
            else:
                minimum = 0.001 if field in {"width_dp", "height_dp"} else None
                if field in {"font_size_sp", "line_height_sp"}:
                    minimum = 0.0
                if field == "aspect_ratio":
                    minimum = 0.001
                target[field] = optional_number(raw, path, minimum)
    control = result['control']
    if control['minimum'] is not None and control['maximum'] is not None and control['minimum'] >= control['maximum']:
        raise PageSnapshotError(f'{label}.control requires minimum < maximum')
    typography = result['typography']
    if typography['min_lines'] is not None and typography['max_lines'] is not None and typography['min_lines'] > typography['max_lines']:
        raise PageSnapshotError(f'{label}.typography requires min_lines <= max_lines')
    return result


def normalize_provenance(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 1000:
        raise PageSnapshotError(f"{label} must be a list")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != {"paths", "origin", "source"}:
            raise PageSnapshotError(f"{label}[{index}] is malformed")
        paths = item["paths"]
        if not isinstance(paths, list) or not paths or not all(
            isinstance(path, str) and re.fullmatch(r"style(?:\.[a-z_][a-z0-9_]*)+", path)
            for path in paths
        ):
            raise PageSnapshotError(f"{label}[{index}].paths is malformed")
        origin = optional_enum(
            item["origin"], f"{label}[{index}].origin",
            {"runtime", "source_resolved", "source_expression", "pixel_sampled", "manual_verified", "ui_preview_sample"},
        )
        result.append(
            {
                "paths": paths,
                "origin": origin,
                "source": bounded_string(item["source"], f"{label}[{index}].source"),
            }
        )
    return result


def normalize_unresolved(value: Any, label: str) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > 1000:
        raise PageSnapshotError(f"{label} must be a list")
    result: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != {"path", "expression", "reason"}:
            raise PageSnapshotError(f"{label}[{index}] is malformed")
        expression = display_string(item['expression'], f'{label}[{index}].expression')
        if not expression or any(ord(c) < 32 and c not in '\r\n\t' for c in expression):
            raise PageSnapshotError(f'{label}[{index}].expression must be non-empty source text; {actual_value(expression)}')
        # Diagnostics may contain source excerpts; identifier limits do not apply.
        reason = item['reason']
        if (not isinstance(reason, str) or not reason.strip()
                or any(ord(c) < 32 and c not in '\r\n\t' for c in reason)):
            raise PageSnapshotError(f'{label}[{index}].reason must be non-empty diagnostic text; {actual_value(reason)}')
        result.append(
            {
                "path": bounded_string(item["path"], f"{label}[{index}].path", 240),
                "expression": expression,
                "reason": reason,
            }
        )
    return result


def validate_visual_facts_payload(
    payload: Any,
    platform: str,
) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict) or set(payload) != {"schema", "platform", "components"}:
        raise PageSnapshotError("visual facts inventory has unsupported root fields")
    if payload["schema"] != VISUAL_FACTS_SCHEMA:
        raise PageSnapshotError("visual facts inventory schema is unsupported")
    if payload["platform"] != platform:
        raise PageSnapshotError("visual facts platform does not match page generator")
    components = payload["components"]
    if not isinstance(components, list) or len(components) > 10000:
        raise PageSnapshotError("visual facts inventory must contain at most 10000 components")
    result: dict[str, dict[str, Any]] = {}
    for index, component in enumerate(components):
        if not isinstance(component, dict) or set(component) != {
            "semantic_key", "style", "provenance", "unresolved"
        }:
            raise PageSnapshotError("visual facts inventory contains a malformed component")
        semantic_key = require_token(component["semantic_key"], "visual facts semantic_key")
        if semantic_key in result:
            raise PageSnapshotError("visual facts inventory contains duplicate semantic keys")
        result[semantic_key] = {
            "style": normalize_style(component["style"], f"visual facts component {index}.style"),
            "provenance": normalize_provenance(component["provenance"], f"visual facts component {index}.provenance"),
            "unresolved": normalize_unresolved(component["unresolved"], f"visual facts component {index}.unresolved"),
        }
    return result


def load_visual_facts(
    path: Path | None,
    platform: str,
) -> tuple[dict[str, dict[str, Any]], Path | None]:
    if path is None:
        return {}, None
    payload, resolved = load_json(path, "visual facts inventory")
    return validate_visual_facts_payload(payload, platform), resolved


def parse_insets(value: str) -> dict[str, int]:
    try:
        values = [int(item) for item in value.split(",")]
    except ValueError as error:
        raise PageSnapshotError("insets-px must be left,top,right,bottom integers") from error
    if len(values) != 4 or any(item < 0 for item in values):
        raise PageSnapshotError("insets-px must be left,top,right,bottom non-negative integers")
    return dict(zip(("left", "top", "right", "bottom"), values, strict=True))


def png_dimensions(path: Path) -> tuple[int, int]:
    resolved = resolve_input(path, "screenshot")
    with resolved.open("rb") as handle:
        header = handle.read(24)
    if len(header) != 24 or header[:8] != PNG_SIGNATURE or header[12:16] != b"IHDR":
        raise PageSnapshotError("screenshot must be a PNG with an IHDR header")
    width, height = struct.unpack(">II", header[16:24])
    if width <= 0 or height <= 0:
        raise PageSnapshotError("screenshot dimensions must be positive")
    return width, height


def validate_bounds(bounds: Any, dimensions: tuple[int, int], component_id: str) -> dict[str, int]:
    if not isinstance(bounds, dict) or set(bounds) != {"x", "y", "width", "height"}:
        raise PageSnapshotError(f"component {component_id} bounds are malformed")
    if any(type(bounds[field]) is not int for field in ("x", "y", "width", "height")):
        raise PageSnapshotError(f"component {component_id} bounds must be integers")
    x, y, width, height = (bounds[field] for field in ("x", "y", "width", "height"))
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise PageSnapshotError(f"component {component_id} bounds must be positive")
    if x + width > dimensions[0] or y + height > dimensions[1]:
        raise PageSnapshotError(f"component {component_id} bounds exceed screenshot dimensions")
    return {"x": x, "y": y, "width": width, "height": height}


def validate_components(
    payload: dict[str, Any],
) -> tuple[tuple[int, int], list[dict[str, Any]], dict[str, int] | None]:
    schema = payload.get("schema")
    expected_fields = {"schema", "screenshot_dimensions", "components"}
    if schema == COMPONENT_SCHEMA_V2:
        expected_fields.add("content_insets_px")
    elif schema != COMPONENT_SCHEMA:
        raise PageSnapshotError("component inventory schema is unsupported")
    if set(payload) != expected_fields:
        raise PageSnapshotError("component inventory has unsupported root fields")
    dimensions = payload["screenshot_dimensions"]
    if not isinstance(dimensions, dict) or set(dimensions) != {"width", "height"}:
        raise PageSnapshotError("component inventory dimensions are malformed")
    width = dimensions["width"]
    height = dimensions["height"]
    if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
        raise PageSnapshotError("component inventory dimensions must be positive integers")
    runtime_insets: dict[str, int] | None = None
    if schema == COMPONENT_SCHEMA_V2:
        raw_insets = payload["content_insets_px"]
        inset_fields = {"left", "top", "right", "bottom"}
        if (
            not isinstance(raw_insets, dict)
            or set(raw_insets) != inset_fields
            or any(
                type(raw_insets[field]) is not int or raw_insets[field] < 0
                for field in inset_fields
            )
            or raw_insets["left"] + raw_insets["right"] >= width
            or raw_insets["top"] + raw_insets["bottom"] >= height
        ):
            raise PageSnapshotError("component inventory content insets are malformed")
        runtime_insets = {field: raw_insets[field] for field in inset_fields}
    raw_components = payload["components"]
    if not isinstance(raw_components, list) or len(raw_components) > 10000:
        raise PageSnapshotError("component inventory must contain at most 10000 components")
    seen: set[str] = set()
    components: list[dict[str, Any]] = []
    for raw in raw_components:
        if not isinstance(raw, dict) or not {"id", "type", "bounds"}.issubset(raw):
            raise PageSnapshotError("component inventory contains a malformed component")
        if not set(raw).issubset({"id", "type", "semantic_key", "bounds"}):
            raise PageSnapshotError("component inventory contains unsupported component fields")
        component_id = require_token(raw["id"], "component id")
        if component_id in seen:
            raise PageSnapshotError("component inventory contains duplicate component ids")
        seen.add(component_id)
        item = {
            "id": component_id,
            "type": require_token(raw["type"], "component type"),
            "bounds": validate_bounds(raw["bounds"], (width, height), component_id),
        }
        if "semantic_key" in raw:
            item["semantic_key"] = require_token(raw["semantic_key"], "component semantic_key")
        components.append(item)
    return (width, height), components, runtime_insets


def load_source_attributes(path: Path | None) -> tuple[dict[str, dict[str, Any]], Path | None]:
    if path is None:
        return {}, None
    payload, resolved = load_json(path, "source attribute inventory")
    if payload.get("schema") != SOURCE_ATTRIBUTE_SCHEMA or not isinstance(payload.get("components"), list):
        raise PageSnapshotError("source attribute inventory schema is unsupported")
    result: dict[str, dict[str, Any]] = {}
    for component in payload["components"]:
        if not isinstance(component, dict):
            raise PageSnapshotError("source attribute inventory contains a malformed component")
        semantic_key = require_token(component.get("semantic_key"), "source semantic_key")
        if semantic_key in result:
            raise PageSnapshotError("source attribute inventory contains duplicate semantic keys")
        source = component.get("source")
        composable = component.get("composable")
        attributes = component.get("attributes")
        if not isinstance(source, str) or not source or not isinstance(composable, str) or not composable:
            raise PageSnapshotError("source attribute component location is malformed")
        if not isinstance(attributes, list):
            raise PageSnapshotError("source attribute component attributes are malformed")
        source_component: dict[str, Any] = {
            "source": source,
            "composable": composable,
            "attributes": attributes,
        }
        hierarchy = component.get("source_hierarchy")
        if hierarchy is not None:
            if not isinstance(hierarchy, dict) or set(hierarchy) != {
                "parent_semantic_key", "preorder_index", "mapping"
            }:
                raise PageSnapshotError("source attribute component hierarchy is malformed")
            parent_semantic_key = hierarchy["parent_semantic_key"]
            if parent_semantic_key is not None:
                parent_semantic_key = require_token(
                    parent_semantic_key, "source parent semantic_key"
                )
            preorder_index = hierarchy["preorder_index"]
            if type(preorder_index) is not int or preorder_index < 0:
                raise PageSnapshotError("source hierarchy preorder_index is malformed")
            mapping = hierarchy["mapping"]
            if mapping not in {
                "resolved_static_call_graph", "ambiguous_runtime_fallback"
            }:
                raise PageSnapshotError("source hierarchy mapping is unsupported")
            source_component["source_hierarchy"] = {
                "parent_semantic_key": parent_semantic_key,
                "preorder_index": preorder_index,
                "mapping": mapping,
            }
        geometry = component.get("resolved_visual_geometry")
        if geometry is not None:
            if not isinstance(geometry, dict) or set(geometry) != {"layout", "transform"}:
                raise PageSnapshotError("source resolved visual geometry is malformed")
            layout = geometry["layout"]
            transform = geometry["transform"]
            if (
                not isinstance(layout, dict)
                or not set(layout).issubset({"width_dp", "height_dp"})
                or not isinstance(transform, dict)
                or not set(transform).issubset(STYLE_SECTIONS["transform"])
            ):
                raise PageSnapshotError("source resolved visual geometry is malformed")
            source_component["resolved_visual_geometry"] = {
                "layout": {
                    field: finite_number(value, f"source geometry layout.{field}", 0.001)
                    for field, value in layout.items()
                },
                "transform": {
                    field: finite_number(value, f"source geometry transform.{field}")
                    for field, value in transform.items()
                },
            }
        result[semantic_key] = source_component
    return result, resolved


def contains(parent: dict[str, int], child: dict[str, int]) -> bool:
    return (
        parent["x"] <= child["x"]
        and parent["y"] <= child["y"]
        and parent["x"] + parent["width"] >= child["x"] + child["width"]
        and parent["y"] + parent["height"] >= child["y"] + child["height"]
    )


def infer_parent(component: dict[str, Any], components: list[dict[str, Any]]) -> str | None:
    child_bounds = component["bounds"]
    child_area = child_bounds["width"] * child_bounds["height"]
    candidates: list[tuple[int, str]] = []
    for candidate in components:
        if candidate["id"] == component["id"]:
            continue
        bounds = candidate["bounds"]
        area = bounds["width"] * bounds["height"]
        if area > child_area and contains(bounds, child_bounds):
            candidates.append((area, candidate["id"]))
    return min(candidates)[1] if candidates else None


def source_parent_id(
    component: dict[str, Any],
    source_components: dict[str, dict[str, Any]],
    runtime_ids_by_semantic_key: dict[str, list[str]],
) -> tuple[bool, str | None]:
    semantic_key = component.get("semantic_key")
    source = source_components.get(semantic_key) if isinstance(semantic_key, str) else None
    hierarchy = source.get("source_hierarchy") if isinstance(source, dict) else None
    if not isinstance(hierarchy, dict) or hierarchy.get("mapping") != "resolved_static_call_graph":
        return False, None
    parent_semantic_key = hierarchy.get("parent_semantic_key")
    visited: set[str] = set()
    while parent_semantic_key is not None:
        if parent_semantic_key in visited:
            return False, None
        visited.add(parent_semantic_key)
        runtime_ids = runtime_ids_by_semantic_key.get(parent_semantic_key, [])
        if len(runtime_ids) == 1:
            return True, runtime_ids[0]
        if len(runtime_ids) > 1:
            return False, None
        parent_source = source_components.get(parent_semantic_key)
        parent_hierarchy = (
            parent_source.get("source_hierarchy")
            if isinstance(parent_source, dict)
            else None
        )
        if (
            not isinstance(parent_hierarchy, dict)
            or parent_hierarchy.get("mapping") != "resolved_static_call_graph"
        ):
            return False, None
        parent_semantic_key = parent_hierarchy.get("parent_semantic_key")
    return True, None


def apply_source_resolved_visual_geometry(
    item: dict[str, Any],
    source: dict[str, Any],
) -> None:
    geometry = source.get("resolved_visual_geometry")
    if not isinstance(geometry, dict):
        return
    proven_paths: list[str] = []
    for section in ("layout", "transform"):
        values = geometry.get(section)
        if not isinstance(values, dict):
            continue
        for field, value in values.items():
            target = item["style"][section]
            path = f"style.{section}.{field}"
            if target.get(field) is None:
                target[field] = value
                proven_paths.append(path)
            elif abs(float(target[field]) - float(value)) > 0.001:
                item["unresolved"].append(
                    {
                        "path": path,
                        "expression": f"runtime={target[field]},source={value}",
                        "reason": "runtime and source-resolved visual geometry disagree",
                    }
                )
    if proven_paths:
        item["provenance"].append(
            {
                "paths": sorted(proven_paths),
                "origin": "source_resolved",
                "source": "source-attribute-inventory",
            }
        )


def dp_bounds(bounds: dict[str, int], density: float) -> dict[str, float]:
    return {name: round(value / density, 3) for name, value in bounds.items()}


def build_snapshot(
    platform: str,
    page_id: str,
    state_id: str,
    screenshot_path: Path,
    component_path: Path,
    density: float,
    source_attribute_path: Path | None,
    visual_facts_path: Path | None,
    font_scale: float,
    orientation: str,
    insets_px: dict[str, int] | None,
    device_id: str | None,
    device_model: str | None,
    os_version: str | None,
) -> dict[str, Any]:
    screenshot = resolve_input(screenshot_path, "screenshot")
    screenshot_size = png_dimensions(screenshot)
    component_payload, component_file = load_json(component_path, "component inventory")
    inventory_size, components, runtime_insets = validate_components(component_payload)
    if screenshot_size != inventory_size:
        raise PageSnapshotError(
            "screenshot dimensions do not match component inventory: "
            f"{screenshot_size[0]}x{screenshot_size[1]} != {inventory_size[0]}x{inventory_size[1]}"
        )
    if density <= 0:
        raise PageSnapshotError("density must be greater than zero")
    source_components, source_file = load_source_attributes(source_attribute_path)
    visual_components, visual_file = load_visual_facts(visual_facts_path, platform)
    if font_scale <= 0:
        raise PageSnapshotError("font-scale must be greater than zero")
    expected_orientation = "landscape" if screenshot_size[0] > screenshot_size[1] else "portrait"
    if orientation != expected_orientation:
        raise PageSnapshotError("orientation does not match screenshot dimensions")
    if insets_px is not None:
        effective_insets = insets_px
        insets_source = "explicit"
    elif runtime_insets is not None:
        effective_insets = runtime_insets
        insets_source = "component_inventory"
    else:
        effective_insets = {"left": 0, "top": 0, "right": 0, "bottom": 0}
        insets_source = "default_zero"
    if (
        effective_insets["left"] + effective_insets["right"] >= screenshot_size[0]
        or effective_insets["top"] + effective_insets["bottom"] >= screenshot_size[1]
    ):
        raise PageSnapshotError("insets-px leave no visible content area")
    output_components: list[dict[str, Any]] = []
    mapped_source_keys: set[str] = set()
    order_by_id = {component["id"]: index for index, component in enumerate(components)}
    component_by_id = {component["id"]: component for component in components}
    runtime_ids_by_semantic_key: dict[str, list[str]] = {}
    for component in components:
        semantic_key = component.get("semantic_key")
        if isinstance(semantic_key, str):
            runtime_ids_by_semantic_key.setdefault(semantic_key, []).append(component["id"])
    parent_mapping_by_id: dict[str, str] = {}
    parent_by_id: dict[str, str | None] = {}
    for component in components:
        source_mapped, source_parent = source_parent_id(
            component, source_components, runtime_ids_by_semantic_key
        )
        if source_mapped:
            parent_by_id[component["id"]] = source_parent
            parent_mapping_by_id[component["id"]] = "source-semantic-ancestor"
        else:
            parent_by_id[component["id"]] = infer_parent(component, components)
            parent_mapping_by_id[component["id"]] = "smallest-containing-runtime-component"
    root_ids = [component["id"] for component in components if parent_by_id[component["id"]] is None]
    children_by_parent: dict[str, list[str]] = {}
    for component in components:
        parent_id = parent_by_id[component["id"]]
        if parent_id is not None:
            children_by_parent.setdefault(parent_id, []).append(component["id"])
    def component_order(component_id: str) -> tuple[int, int]:
        component = component_by_id[component_id]
        semantic_key = component.get("semantic_key")
        source = source_components.get(semantic_key) if isinstance(semantic_key, str) else None
        hierarchy = source.get("source_hierarchy") if isinstance(source, dict) else None
        if (
            parent_mapping_by_id[component_id] == "source-semantic-ancestor"
            and isinstance(hierarchy, dict)
        ):
            return 0, hierarchy["preorder_index"]
        return 1, order_by_id[component_id]

    root_ids.sort(key=component_order)
    for sibling_ids in children_by_parent.values():
        sibling_ids.sort(key=component_order)
    for component_index, component in enumerate(components):
        parent_id = parent_by_id[component["id"]]
        siblings = children_by_parent.get(parent_id, []) if parent_id is not None else root_ids
        item: dict[str, Any] = {
            "id": component["id"],
            "type": component["type"],
            "bounds_px": component["bounds"],
            "bounds_dp": dp_bounds(component["bounds"], density),
            "parent_id": parent_id,
            "parent_mapping": parent_mapping_by_id[component["id"]],
            "children_ids": children_by_parent.get(component["id"], []),
            "sibling_index": siblings.index(component["id"]) if component["id"] in siblings else component_index,
            "style": empty_style(),
            "provenance": [],
            "unresolved": [],
        }
        semantic_key = component.get("semantic_key")
        if semantic_key is not None:
            item["semantic_key"] = semantic_key
            source = source_components.get(semantic_key)
            if source is not None:
                item["source"] = source
                mapped_source_keys.add(semantic_key)
            visual = visual_components.get(semantic_key)
            if visual is not None:
                item.update(visual)
                asset = item["style"]["asset"]
                for axis in ("width", "height"):
                    pixel_field = f"{axis}_px"
                    logical_field = f"{axis}_dp"
                    if asset[logical_field] is None and asset[pixel_field] is not None:
                        asset[logical_field] = round(asset[pixel_field] / density, 3)
            if source is not None:
                apply_source_resolved_visual_geometry(item, source)
        output_components.append(item)
    capture: dict[str, Any] = {
        "screenshot": {
            "file": screenshot.name,
            "byte_count": screenshot.stat().st_size,
            "sha256": sha256_file(screenshot),
        }
    }
    device = {
        name: value
        for name, value in (
            ("id", device_id),
            ("model", device_model),
            ("os_version", os_version),
        )
        if value
    }
    if device:
        capture["device"] = device
    input_hashes = {
        "component_inventory_sha256": sha256_file(component_file),
    }
    if source_file is not None:
        input_hashes["source_attribute_inventory_sha256"] = sha256_file(source_file)
    if visual_file is not None:
        input_hashes["visual_facts_inventory_sha256"] = sha256_file(visual_file)
    safe_area_dp = {name: round(value / density, 3) for name, value in effective_insets.items()}
    content_x = effective_insets["left"]
    content_y = effective_insets["top"]
    content_width = screenshot_size[0] - effective_insets["left"] - effective_insets["right"]
    content_height = screenshot_size[1] - effective_insets["top"] - effective_insets["bottom"]
    return {
        "schema": PAGE_SCHEMA,
        "status": "candidate_requires_review",
        "authoritative": False,
        "platform": platform,
        "page": {"id": page_id, "state": state_id},
        "viewport": {
            "width_px": screenshot_size[0],
            "height_px": screenshot_size[1],
            "density": density,
            "font_scale": round(font_scale, 3),
            "orientation": orientation,
            "width_dp": round(screenshot_size[0] / density, 3),
            "height_dp": round(screenshot_size[1] / density, 3),
            "insets_source": insets_source,
            "safe_area_px": effective_insets,
            "safe_area_dp": safe_area_dp,
            "content_bounds_px": {
                "x": content_x, "y": content_y, "width": content_width, "height": content_height,
            },
            "content_bounds_dp": dp_bounds(
                {"x": content_x, "y": content_y, "width": content_width, "height": content_height},
                density,
            ),
        },
        "capture": capture,
        "input_hashes": input_hashes,
        "components": output_components,
        "unmapped_source_components": sorted(set(source_components) - mapped_source_keys),
        "unmapped_visual_fact_components": sorted(set(visual_components) - mapped_source_keys - {
            component.get("semantic_key") for component in components if component.get("semantic_key")
        }),
        "limitations": [
            "Source-resolved call hierarchy is preferred and compresses uncaptured wrappers to the nearest captured ancestor; ambiguous call sites fall back to runtime containment.",
            "Null style fields and unresolved expressions mean the value was not proven; values are never invented.",
            "Canvas, WebView, video, maps, and custom shaders still require local pixel comparison even when their container style is known.",
        ],
    }


def write_new_json(path: Path, payload: dict[str, Any]) -> tuple[Path, str]:
    output = Path(os.path.abspath(os.path.expanduser(str(path))))
    if output.exists() or output.is_symlink():
        raise PageSnapshotError("output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.parent.is_symlink():
        raise PageSnapshotError("output parent must not be a symbolic link")
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with tempfile.NamedTemporaryFile(dir=output.parent, prefix=f".{output.name}.", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return output, hashlib.sha256(encoded).hexdigest()


def parser_for_platform(platform: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"Generate one canonical {platform} page snapshot JSON bound to a runtime screenshot."
    )
    parser.add_argument("--page-id", required=True)
    parser.add_argument("--state-id", required=True)
    parser.add_argument("--screenshot", required=True, type=Path)
    parser.add_argument("--components", required=True, type=Path)
    parser.add_argument("--source-attributes", type=Path)
    parser.add_argument("--visual-facts", type=Path)
    parser.add_argument("--density", required=True, type=float)
    parser.add_argument("--font-scale", type=float, default=1.0)
    parser.add_argument("--orientation", choices=("portrait", "landscape"))
    parser.add_argument(
        "--insets-px",
        help="left,top,right,bottom override; defaults to v2 component inventory runtime insets",
    )
    parser.add_argument("--device-id")
    parser.add_argument("--device-model")
    parser.add_argument("--os-version")
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main_for_platform(platform: str) -> int:
    args = parser_for_platform(platform).parse_args()
    try:
        screenshot_size = png_dimensions(args.screenshot)
        orientation = args.orientation or ("landscape" if screenshot_size[0] > screenshot_size[1] else "portrait")
        snapshot = build_snapshot(
            platform=platform,
            page_id=require_token(args.page_id, "page id"),
            state_id=require_token(args.state_id, "state id"),
            screenshot_path=args.screenshot,
            component_path=args.components,
            density=args.density,
            source_attribute_path=args.source_attributes,
            visual_facts_path=args.visual_facts,
            font_scale=args.font_scale,
            orientation=orientation,
            insets_px=parse_insets(args.insets_px) if args.insets_px is not None else None,
            device_id=args.device_id,
            device_model=args.device_model,
            os_version=args.os_version,
        )
        output, digest = write_new_json(args.output, snapshot)
    except (OSError, PageSnapshotError, TypeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "schema": COMMAND_SCHEMA,
                "platform": platform,
                "output": str(output),
                "sha256": digest,
                "component_count": len(snapshot["components"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0
