#!/usr/bin/env python3
"""Convert one manifest-approved Android VectorDrawable to SVG locally."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from copy_local_asset import (
    AssetCopyError,
    load_asset,
    sha256_file,
    validate_target_and_destination,
)


ANDROID_NS = "http://schemas.android.com/apk/res/android"
ANDROID = f"{{{ANDROID_NS}}}"
AAPT_NS = "http://schemas.android.com/aapt"
AAPT = f"{{{AAPT_NS}}}"
LEDGER_SCHEMA = "android-to-harmony.vector-conversion-ledger.v1"
PATH_DATA_PATTERN = re.compile(r"[MmZzLlHhVvCcSsQqTtAa0-9eE+.,\s-]+\Z")
DIMENSION_PATTERN = re.compile(r"([0-9]+(?:\.[0-9]+)?)dp\Z")
NUMBER_PATTERN = re.compile(r"[0-9]+(?:\.[0-9]+)?\Z")
SIGNED_NUMBER_PATTERN = re.compile(r"-?[0-9]+(?:\.[0-9]+)?\Z")
ANDROID_PLATFORM_COLORS = {
    "black": "#000000",
    "transparent": "#00000000",
    "white": "#FFFFFF",
}


class VectorConversionError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert one safe-manifest Android vector into a Harmony SVG without "
            "printing protected vector data."
        )
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--asset-path", required=True)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def compact_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return format(value, ".12g")


def parse_dimension(value: str | None, field: str) -> float:
    match = DIMENSION_PATTERN.fullmatch(value or "")
    if match is None:
        raise VectorConversionError(f"Android vector {field} must be a positive dp value")
    parsed = float(match.group(1))
    if parsed <= 0:
        raise VectorConversionError(f"Android vector {field} must be positive")
    return parsed


def parse_number(value: str | None, field: str) -> float:
    if NUMBER_PATTERN.fullmatch(value or "") is None:
        raise VectorConversionError(f"Android vector {field} must be a positive number")
    parsed = float(value or "0")
    if parsed <= 0:
        raise VectorConversionError(f"Android vector {field} must be positive")
    return parsed


def parse_alpha(value: str | None, field: str) -> float:
    if NUMBER_PATTERN.fullmatch(value or "") is None:
        raise VectorConversionError(f"Android vector {field} must be a number from 0 to 1")
    parsed = float(value or "0")
    if parsed < 0 or parsed > 1:
        raise VectorConversionError(f"Android vector {field} must be a number from 0 to 1")
    return parsed


def parse_non_negative_number(value: str | None, field: str) -> float:
    if NUMBER_PATTERN.fullmatch(value or "") is None:
        raise VectorConversionError(f"Android vector {field} must be a non-negative number")
    parsed = float(value or "0")
    if parsed < 0:
        raise VectorConversionError(f"Android vector {field} must be a non-negative number")
    return parsed


def parse_signed_number(value: str | None, field: str) -> float:
    if SIGNED_NUMBER_PATTERN.fullmatch(value or "") is None:
        raise VectorConversionError(f"Android vector {field} must be a number")
    return float(value or "0")


def combined_opacity(color_opacity: str | None, explicit_alpha: float) -> str | None:
    combined = (float(color_opacity) if color_opacity is not None else 1.0) * explicit_alpha
    if combined == 1:
        return None
    return format(combined, ".6f").rstrip("0").rstrip(".")


def parse_color(
    value: str,
    color_resources: dict[str, str],
) -> tuple[str, str | None, bool, str | None, str | None]:
    resolved_resource = False
    platform_color_token: str | None = None
    active: set[str] = set()
    while value.startswith("@color/"):
        name = value.removeprefix("@color/")
        if name in active or name not in color_resources:
            raise VectorConversionError(
                "Android vector fillColor references an unresolved or cyclic color resource"
            )
        active.add(name)
        value = color_resources[name]
        resolved_resource = True
    if not value.startswith("#"):
        if value.startswith("?attr/") or value.startswith("?android:attr/"):
            if value.startswith("?android:attr/"):
                token = f"android:{value.removeprefix('?android:attr/')}"
            else:
                token = value.removeprefix("?attr/")
            if re.fullmatch(r"(?:android:)?[A-Za-z_][A-Za-z0-9_]*", token) is None:
                raise VectorConversionError("Android vector theme color token is invalid")
            return "currentColor", None, resolved_resource, token, None
        if value.startswith("@android:color/"):
            platform_color_token = value.removeprefix("@android:color/")
            platform_color = ANDROID_PLATFORM_COLORS.get(platform_color_token)
            if platform_color is None:
                raise VectorConversionError(
                    "Android vector fillColor is an unsupported Android platform color: "
                    f"{platform_color_token}"
                )
            value = platform_color
        else:
            raise VectorConversionError(
                "Android vector fillColor must be a literal #RGB, #ARGB, #RRGGBB, or #AARRGGBB color"
            )
    digits = value[1:]
    if re.fullmatch(r"[0-9A-Fa-f]+", digits) is None or len(digits) not in {3, 4, 6, 8}:
        raise VectorConversionError("Android vector fillColor has an unsupported literal format")
    if len(digits) in {3, 6}:
        return f"#{digits.upper()}", None, resolved_resource, None, platform_color_token
    if len(digits) == 4:
        alpha = int(digits[0] * 2, 16)
        rgb = "".join(character * 2 for character in digits[1:])
    else:
        alpha = int(digits[:2], 16)
        rgb = digits[2:]
    opacity = None if alpha == 255 else format(alpha / 255, ".6f").rstrip("0").rstrip(".")
    return f"#{rgb.upper()}", opacity, resolved_resource, None, platform_color_token


def load_safe_color_resources(
    manifest_path: Path,
    asset_path: str,
) -> dict[str, str]:
    manifest_path = manifest_path.expanduser().resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise VectorConversionError("safe-snapshot manifest is invalid") from error
    snapshot_value = manifest.get("snapshot_root")
    text_files = manifest.get("text_files")
    text_hashes = manifest.get("text_file_sha256")
    if (
        not isinstance(snapshot_value, str)
        or not isinstance(text_files, list)
        or not isinstance(text_hashes, dict)
    ):
        raise VectorConversionError("safe-snapshot text inventory is invalid")
    snapshot = Path(snapshot_value).expanduser().resolve()
    if manifest_path != snapshot / ".android-to-harmony-safe.json":
        raise VectorConversionError("manifest is not located at its recorded snapshot root")

    parts = Path(asset_path).parts
    try:
        source_index = parts.index("src")
    except ValueError as error:
        raise VectorConversionError("Android vector is not inside a module source set") from error
    module_prefix = "/".join(parts[:source_index])
    values_prefix = f"{module_prefix + '/' if module_prefix else ''}src/main/res/values/"
    resources: dict[str, str] = {}
    ambiguous: set[str] = set()
    for relative in text_files:
        if (
            not isinstance(relative, str)
            or not relative.startswith(values_prefix)
            or not relative.endswith(".xml")
        ):
            continue
        path = (snapshot / relative).resolve()
        if snapshot not in path.parents or path.is_symlink() or not path.is_file():
            raise VectorConversionError("safe color resource path is invalid")
        expected_hash = text_hashes.get(relative)
        if not isinstance(expected_hash, str) or sha256_file(path) != expected_hash:
            raise VectorConversionError("safe color resource changed after snapshot validation")
        try:
            root = ET.fromstring(path.read_bytes())
        except ET.ParseError as error:
            raise VectorConversionError("safe color resource XML is malformed") from error
        if root.tag.rsplit("}", 1)[-1] != "resources":
            continue
        for child in root:
            if child.tag.rsplit("}", 1)[-1] != "color":
                continue
            name = child.get("name")
            value = (child.text or "").strip()
            if not name or not value:
                continue
            if name in resources and resources[name] != value:
                ambiguous.add(name)
            else:
                resources[name] = value
    for name in ambiguous:
        resources.pop(name, None)
    return resources


def require_attributes(
    element: ET.Element,
    required: set[str],
    optional: set[str],
    role: str,
) -> None:
    allowed = {f"{ANDROID}{name}" for name in required | optional}
    unknown = sorted(attribute for attribute in element.attrib if attribute not in allowed)
    if unknown:
        unknown_names = sorted(attribute.rsplit("}", 1)[-1] for attribute in unknown)
        raise VectorConversionError(
            f"{role} uses unsupported attributes: {', '.join(unknown_names)}"
        )
    missing = sorted(name for name in required if f"{ANDROID}{name}" not in element.attrib)
    if missing:
        raise VectorConversionError(f"{role} is missing required fields: {', '.join(missing)}")


def parse_optional_group_number(
    element: ET.Element,
    name: str,
    default: float,
) -> float:
    value = element.get(f"{ANDROID}{name}")
    if value is None:
        return default
    return parse_signed_number(value, name)


def build_group_transform(element: ET.Element) -> tuple[str | None, set[str]]:
    require_attributes(
        element,
        set(),
        {
            "name",
            "pivotX",
            "pivotY",
            "rotation",
            "scaleX",
            "scaleY",
            "translateX",
            "translateY",
        },
        "Android vector group",
    )
    converted_fields = {
        f"group.{name.removeprefix(ANDROID)}"
        for name in element.attrib
        if name.startswith(ANDROID)
    }
    pivot_x = parse_optional_group_number(element, "pivotX", 0.0)
    pivot_y = parse_optional_group_number(element, "pivotY", 0.0)
    rotation = parse_optional_group_number(element, "rotation", 0.0)
    scale_x = parse_optional_group_number(element, "scaleX", 1.0)
    scale_y = parse_optional_group_number(element, "scaleY", 1.0)
    translate_x = parse_optional_group_number(element, "translateX", 0.0)
    translate_y = parse_optional_group_number(element, "translateY", 0.0)

    if (
        pivot_x == 0
        and pivot_y == 0
        and rotation == 0
        and scale_x == 1
        and scale_y == 1
        and translate_x == 0
        and translate_y == 0
    ):
        return None, converted_fields
    if rotation == 0 and scale_x == 1 and scale_y == 1:
        return (
            f"translate({compact_number(translate_x)} {compact_number(translate_y)})",
            converted_fields,
        )
    transforms = [
        (
            "translate("
            f"{compact_number(translate_x + pivot_x)} "
            f"{compact_number(translate_y + pivot_y)}"
            ")"
        )
    ]
    if rotation != 0:
        transforms.append(f"rotate({compact_number(rotation)})")
    if scale_x != 1 or scale_y != 1:
        transforms.append(f"scale({compact_number(scale_x)} {compact_number(scale_y)})")
    if pivot_x != 0 or pivot_y != 0:
        transforms.append(
            f"translate({compact_number(-pivot_x)} {compact_number(-pivot_y)})"
        )
    return " ".join(transforms), converted_fields


def convert_vector(
    source: Path,
    color_resources: dict[str, str],
) -> tuple[bytes, dict[str, Any]]:
    payload = source.read_bytes()
    if len(payload) > 2 * 1024 * 1024:
        raise VectorConversionError("Android vector exceeds the 2 MiB conversion limit")
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise VectorConversionError("Android vector declarations and entities are not supported")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as error:
        raise VectorConversionError("Android vector XML is malformed") from error
    if root.tag.rsplit("}", 1)[-1] != "vector":
        raise VectorConversionError("approved XML asset is not an Android vector")
    require_attributes(
        root,
        {"width", "height", "viewportWidth", "viewportHeight"},
        {"autoMirrored", "tint"},
        "Android vector",
    )
    width = parse_dimension(root.get(f"{ANDROID}width"), "width")
    height = parse_dimension(root.get(f"{ANDROID}height"), "height")
    viewport_width = parse_number(root.get(f"{ANDROID}viewportWidth"), "viewportWidth")
    viewport_height = parse_number(root.get(f"{ANDROID}viewportHeight"), "viewportHeight")
    auto_mirrored_value = root.get(f"{ANDROID}autoMirrored")
    if auto_mirrored_value not in {None, "true", "false"}:
        raise VectorConversionError("Android vector autoMirrored must be true or false")
    requires_auto_mirroring = auto_mirrored_value == "true"
    root_tint_value = root.get(f"{ANDROID}tint")
    root_tint: tuple[str, str | None, bool, str | None, str | None] | None = None
    if root_tint_value is not None:
        root_tint = parse_color(root_tint_value, color_resources)

    converted_fields = {"width", "height", "viewportWidth", "viewportHeight"}
    if auto_mirrored_value is not None:
        converted_fields.add("autoMirrored")
    if root_tint is not None:
        converted_fields.add("tint")
    definition_lines: list[str] = []
    path_lines: list[str] = []
    resolved_color_resource_count = 1 if root_tint is not None and root_tint[2] else 0
    dynamic_color_tokens: set[str] = set()
    resolved_platform_color_tokens: set[str] = set()
    if root_tint is not None and root_tint[3] is not None:
        dynamic_color_tokens.add(root_tint[3])
    if root_tint is not None and root_tint[4] is not None:
        resolved_platform_color_tokens.add(root_tint[4])

    path_count = 0
    clip_path_count = 0
    gradient_count = 0

    def visit_children(parent: ET.Element, indent: str) -> None:
        nonlocal path_count, resolved_color_resource_count
        current_indent = indent
        opened_clip_groups = 0
        for child in parent:
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "clip-path":
                clip_id = emit_clip_path(child)
                path_lines.append(f'{current_indent}<g clip-path="url(#{clip_id})">')
                current_indent += "  "
                opened_clip_groups += 1
                continue
            if tag == "group":
                transform, group_fields = build_group_transform(child)
                converted_fields.update(group_fields)
                if transform is None:
                    visit_children(child, current_indent)
                    continue
                path_lines.append(
                    f'{current_indent}<g transform="{html.escape(transform, quote=True)}">'
                )
                visit_children(child, current_indent + "  ")
                path_lines.append(f"{current_indent}</g>")
                continue
            if tag != "path":
                raise VectorConversionError("Android vector contains unsupported child elements")
            emit_path(child, current_indent)
        for _ in range(opened_clip_groups):
            current_indent = current_indent[:-2]
            path_lines.append(f"{current_indent}</g>")

    def emit_clip_path(child: ET.Element) -> str:
        nonlocal clip_path_count
        require_attributes(
            child,
            {"pathData"},
            {"fillType", "name"},
            "Android vector clip-path",
        )
        path_data = child.get(f"{ANDROID}pathData") or ""
        if not path_data or len(path_data) > 1_000_000 or PATH_DATA_PATTERN.fullmatch(path_data) is None:
            raise VectorConversionError("Android vector clip-path pathData is empty or unsupported")
        clip_path_attributes = [f'd="{html.escape(path_data, quote=True)}"']
        fill_type = child.get(f"{ANDROID}fillType")
        if fill_type is not None:
            fill_rules = {"evenOdd": "evenodd", "nonZero": "nonzero"}
            if fill_type not in fill_rules:
                raise VectorConversionError("Android vector clip-path fillType is unsupported")
            converted_fields.add("clip-path.fillType")
            clip_path_attributes.append(f'clip-rule="{fill_rules[fill_type]}"')
        clip_path_count += 1
        clip_id = f"clip_{clip_path_count}"
        converted_fields.add("clip-path.pathData")
        if child.get(f"{ANDROID}name") is not None:
            converted_fields.add("clip-path.name")
        definition_lines.extend(
            [
                f'    <clipPath id="{clip_id}">',
                f"      <path {' '.join(clip_path_attributes)} />",
                "    </clipPath>",
            ]
        )
        return clip_id

    def emit_path(child: ET.Element, indent: str) -> None:
        nonlocal path_count, resolved_color_resource_count, gradient_count
        require_attributes(
            child,
            {"pathData"},
            {
                "fillAlpha",
                "fillColor",
                "fillType",
                "strokeAlpha",
                "strokeColor",
                "strokeLineCap",
                "strokeLineJoin",
                "strokeMiterLimit",
                "strokeWidth",
            },
            "Android vector path",
        )
        path_data = child.get(f"{ANDROID}pathData") or ""
        if not path_data or len(path_data) > 1_000_000 or PATH_DATA_PATTERN.fullmatch(path_data) is None:
            raise VectorConversionError("Android vector pathData is empty or unsupported")
        fill, opacity, resolved_resource, dynamic_color_token, platform_color_token = parse_color(
            child.get(f"{ANDROID}fillColor") or "#00000000",
            color_resources,
        )
        if root_tint is not None:
            fill, opacity = root_tint[0], root_tint[1]
        else:
            if resolved_resource:
                resolved_color_resource_count += 1
            if dynamic_color_token is not None:
                dynamic_color_tokens.add(dynamic_color_token)
            if platform_color_token is not None:
                resolved_platform_color_tokens.add(platform_color_token)
        fill_alpha_value = child.get(f"{ANDROID}fillAlpha")
        if fill_alpha_value is not None:
            opacity = combined_opacity(
                opacity,
                parse_alpha(fill_alpha_value, "fillAlpha"),
            )
            converted_fields.add("fillAlpha")
        stroke_alpha_value = child.get(f"{ANDROID}strokeAlpha")
        if stroke_alpha_value is not None:
            parse_alpha(stroke_alpha_value, "strokeAlpha")
            converted_fields.add("strokeAlpha")
        attributes = [
            f'd="{html.escape(path_data, quote=True)}"',
            f'fill="{fill}"',
        ]
        if opacity is not None:
            attributes.append(f'fill-opacity="{opacity}"')
        stroke_color_value = child.get(f"{ANDROID}strokeColor")
        stroke_width_value = child.get(f"{ANDROID}strokeWidth")
        stroke_line_cap = child.get(f"{ANDROID}strokeLineCap")
        stroke_line_join = child.get(f"{ANDROID}strokeLineJoin")
        stroke_miter_limit = child.get(f"{ANDROID}strokeMiterLimit")
        stroke_line_cap = {
            "0": "butt",
            "1": "round",
            "2": "square",
        }.get(stroke_line_cap, stroke_line_cap)
        stroke_line_join = {
            "0": "miter",
            "1": "round",
            "2": "bevel",
        }.get(stroke_line_join, stroke_line_join)
        if stroke_line_cap is not None and stroke_line_cap not in {"butt", "round", "square"}:
            raise VectorConversionError("Android vector strokeLineCap is unsupported")
        if stroke_line_join is not None and stroke_line_join not in {"bevel", "miter", "round"}:
            raise VectorConversionError("Android vector strokeLineJoin is unsupported")
        parsed_miter_limit = (
            parse_number(stroke_miter_limit, "strokeMiterLimit")
            if stroke_miter_limit is not None
            else None
        )
        complex_colors: dict[str, str] = {}
        for complex_color in child:
            if complex_color.tag != f"{AAPT}attr":
                raise VectorConversionError(
                    "Android vector path contains an unsupported child element"
                )
            if set(complex_color.attrib) != {"name"}:
                raise VectorConversionError(
                    "Android vector complex color must declare only its name"
                )
            color_name = complex_color.get("name")
            if color_name not in {"android:fillColor", "android:strokeColor"}:
                raise VectorConversionError(
                    "Android vector path contains an unsupported complex color"
                )
            if color_name in complex_colors:
                raise VectorConversionError(
                    "Android vector path repeats a complex color"
                )
            gradient_children = list(complex_color)
            if len(gradient_children) != 1:
                raise VectorConversionError(
                    "Android vector complex color must contain one gradient"
                )
            gradient = gradient_children[0]
            if gradient.tag.rsplit("}", 1)[-1] != "gradient":
                raise VectorConversionError(
                    "Android vector complex color contains an unsupported value"
                )
            require_attributes(
                gradient,
                {"startX", "startY", "endX", "endY"},
                {"type", "tileMode"},
                "Android vector gradient",
            )
            gradient_type = gradient.get(f"{ANDROID}type", "linear")
            if gradient_type != "linear":
                raise VectorConversionError(
                    "Android vector complex color currently supports only linear gradients"
                )
            tile_mode = gradient.get(f"{ANDROID}tileMode", "clamp")
            spread_methods = {"clamp": "pad", "repeat": "repeat", "mirror": "reflect"}
            if tile_mode not in spread_methods:
                raise VectorConversionError("Android vector gradient tileMode is unsupported")
            coordinates = [
                parse_signed_number(gradient.get(f"{ANDROID}{name}"), name)
                for name in ("startX", "startY", "endX", "endY")
            ]
            stops: list[str] = []
            for item in gradient:
                if item.tag.rsplit("}", 1)[-1] != "item":
                    raise VectorConversionError(
                        "Android vector gradient contains an unsupported child"
                    )
                require_attributes(
                    item,
                    {"offset", "color"},
                    set(),
                    "Android vector gradient item",
                )
                offset = parse_non_negative_number(
                    item.get(f"{ANDROID}offset"), "gradient item offset"
                )
                if offset > 1:
                    raise VectorConversionError(
                        "Android vector gradient item offset must be from 0 to 1"
                    )
                (
                    stop_color,
                    stop_opacity,
                    stop_resolved_resource,
                    stop_dynamic_color_token,
                    stop_platform_color_token,
                ) = parse_color(item.get(f"{ANDROID}color") or "", color_resources)
                if stop_dynamic_color_token is not None:
                    raise VectorConversionError(
                        "Android vector gradient theme colors are not safely convertible"
                    )
                if stop_resolved_resource:
                    resolved_color_resource_count += 1
                if stop_platform_color_token is not None:
                    resolved_platform_color_tokens.add(stop_platform_color_token)
                stop_attributes = [
                    f'offset="{compact_number(offset)}"',
                    f'stop-color="{stop_color}"',
                ]
                if stop_opacity is not None:
                    stop_attributes.append(f'stop-opacity="{stop_opacity}"')
                stops.append(f"      <stop {' '.join(stop_attributes)} />")
            if len(stops) < 2:
                raise VectorConversionError(
                    "Android vector linear gradient must contain at least two items"
                )
            gradient_count += 1
            gradient_id = f"gradient_{gradient_count}"
            x1, y1, x2, y2 = (compact_number(value) for value in coordinates)
            spread = spread_methods[tile_mode]
            spread_attribute = "" if spread == "pad" else f' spreadMethod="{spread}"'
            definition_lines.append(
                f'    <linearGradient id="{gradient_id}" gradientUnits="userSpaceOnUse" '
                f'x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"{spread_attribute}>'
            )
            definition_lines.extend(stops)
            definition_lines.append("    </linearGradient>")
            complex_colors[color_name] = f"url(#{gradient_id})"
            converted_fields.add(f"{color_name.removeprefix('android:')}.gradient")

        complex_stroke = complex_colors.get("android:strokeColor")
        if stroke_color_value is not None and complex_stroke is not None:
            raise VectorConversionError(
                "Android vector path cannot declare two stroke colors"
            )
        if complex_stroke is not None:
            stroke_width = (
                parse_non_negative_number(stroke_width_value, "strokeWidth")
                if stroke_width_value is not None
                else 0.0
            )
            attributes.append(f'stroke="{complex_stroke}"')
            attributes.append(f'stroke-width="{compact_number(stroke_width)}"')
            if stroke_alpha_value is not None:
                stroke_opacity = combined_opacity(
                    None,
                    parse_alpha(stroke_alpha_value, "strokeAlpha"),
                )
                if stroke_opacity is not None:
                    attributes.append(f'stroke-opacity="{stroke_opacity}"')
            converted_fields.add("strokeColor")
        elif stroke_color_value is not None:
            (
                stroke,
                stroke_opacity,
                stroke_resolved_resource,
                stroke_dynamic_color_token,
                stroke_platform_color_token,
            ) = parse_color(stroke_color_value, color_resources)
            if root_tint is not None:
                stroke, stroke_opacity = root_tint[0], root_tint[1]
            else:
                if stroke_resolved_resource:
                    resolved_color_resource_count += 1
                if stroke_dynamic_color_token is not None:
                    dynamic_color_tokens.add(stroke_dynamic_color_token)
                if stroke_platform_color_token is not None:
                    resolved_platform_color_tokens.add(stroke_platform_color_token)
            if stroke_alpha_value is not None:
                stroke_opacity = combined_opacity(
                    stroke_opacity,
                    parse_alpha(stroke_alpha_value, "strokeAlpha"),
                )
            stroke_width = (
                parse_non_negative_number(stroke_width_value, "strokeWidth")
                if stroke_width_value is not None
                else 0.0
            )
            attributes.append(f'stroke="{stroke}"')
            attributes.append(f'stroke-width="{compact_number(stroke_width)}"')
            if stroke_opacity is not None:
                attributes.append(f'stroke-opacity="{stroke_opacity}"')
            if stroke_line_cap is not None:
                attributes.append(f'stroke-linecap="{stroke_line_cap}"')
            if stroke_line_join is not None:
                attributes.append(f'stroke-linejoin="{stroke_line_join}"')
            if parsed_miter_limit is not None:
                attributes.append(
                    f'stroke-miterlimit="{compact_number(parsed_miter_limit)}"'
                )
            converted_fields.add("strokeColor")
        elif stroke_width_value is not None:
            parse_non_negative_number(stroke_width_value, "strokeWidth")
        if stroke_width_value is not None:
            converted_fields.add("strokeWidth")
        if stroke_line_cap is not None:
            converted_fields.add("strokeLineCap")
        if stroke_line_join is not None:
            converted_fields.add("strokeLineJoin")
        if parsed_miter_limit is not None:
            converted_fields.add("strokeMiterLimit")
        fill_type = child.get(f"{ANDROID}fillType")
        if fill_type is not None:
            fill_rules = {"evenOdd": "evenodd", "nonZero": "nonzero"}
            if fill_type not in fill_rules:
                raise VectorConversionError("Android vector fillType is unsupported")
            attributes.append(f'fill-rule="{fill_rules[fill_type]}"')
            converted_fields.add("fillType")
        complex_fill = complex_colors.get("android:fillColor")
        if complex_fill is not None:
            if child.get(f"{ANDROID}fillColor") is not None:
                raise VectorConversionError(
                    "Android vector path cannot declare two fill colors"
                )
            attributes = [
                attribute
                for attribute in attributes
                if not attribute.startswith("fill-opacity=")
            ]
            attributes[1] = f'fill="{complex_fill}"'
            if fill_alpha_value is not None:
                fill_opacity = combined_opacity(
                    None,
                    parse_alpha(fill_alpha_value, "fillAlpha"),
                )
                if fill_opacity is not None:
                    attributes.append(f'fill-opacity="{fill_opacity}"')
            converted_fields.add("fillColor.gradient")
        converted_fields.update({"pathData", "fillColor"})
        path_lines.append(f"{indent}<path {' '.join(attributes)} />")
        path_count += 1

    visit_children(root, "  ")
    if path_count == 0:
        raise VectorConversionError("Android vector must contain at least one path")
    if len(dynamic_color_tokens) > 1:
        raise VectorConversionError(
            "Android vector uses multiple dynamic theme colors that cannot share one SVG tint"
        )

    body_lines: list[str] = []
    if definition_lines:
        body_lines.append("  <defs>")
        body_lines.extend(definition_lines)
        body_lines.append("  </defs>")
    body_lines.extend(path_lines)

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{compact_number(width)}" height="{compact_number(height)}" '
        f'viewBox="0 0 {compact_number(viewport_width)} {compact_number(viewport_height)}">\n'
        + "\n".join(body_lines)
        + "\n</svg>\n"
    ).encode("utf-8")
    return svg, {
        "viewport": [viewport_width, viewport_height],
        "path_count": path_count,
        "resolved_color_resource_count": resolved_color_resource_count,
        "resolved_platform_color_tokens": sorted(resolved_platform_color_tokens),
        "requires_target_tint": bool(dynamic_color_tokens),
        "requires_auto_mirroring": requires_auto_mirroring,
        "dynamic_color_tokens": sorted(dynamic_color_tokens),
        "converted_fields": sorted(converted_fields),
    }


def load_ledger(target: Path) -> tuple[Path, dict[str, Any]]:
    path = target / ".migration" / "vector-conversions.json"
    if not path.exists():
        return path, {"schema": LEDGER_SCHEMA, "conversions": {}}
    if not path.is_file() or path.is_symlink():
        raise VectorConversionError("vector conversion ledger is not a regular file")
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise VectorConversionError("vector conversion ledger is invalid") from error
    if (
        not isinstance(ledger, dict)
        or ledger.get("schema") != LEDGER_SCHEMA
        or not isinstance(ledger.get("conversions"), dict)
    ):
        raise VectorConversionError("vector conversion ledger has an unsupported schema")
    return path, ledger


def write_json(path: Path, payload: dict[str, Any]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.write-", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def install_conversion(
    source: Path,
    source_root: Path,
    source_asset: dict[str, Any],
    destination: Path,
    destination_relative: str,
    svg: bytes,
    metadata: dict[str, Any],
    ledger: dict[str, Any],
    force: bool,
) -> tuple[bool, str]:
    if destination.suffix.lower() != ".svg":
        raise VectorConversionError("Android vectors must be converted to an .svg destination")
    conversions = ledger["conversions"]
    previous = conversions.get(destination_relative)
    if previous is not None and not isinstance(previous, dict):
        raise VectorConversionError("vector conversion ledger entry is invalid")
    if destination.exists():
        if not destination.is_file() or destination.is_symlink() or previous is None:
            raise VectorConversionError("refusing to replace an unowned vector destination")
        current_hash = sha256_file(destination)
        if current_hash != previous.get("destination_sha256"):
            raise VectorConversionError("vector destination changed after conversion")
        expected_hash = hashlib.sha256(svg).hexdigest()
        if (
            previous.get("asset_path") == source_asset.get("path")
            and previous.get("source_sha256") == source_asset.get("sha256")
            and current_hash == expected_hash
        ):
            return False, current_hash
        if not force:
            raise VectorConversionError(
                "destination contains a different owned conversion; pass --force to replace it"
            )
    if destination == source_root or source_root in destination.parents:
        raise VectorConversionError("vector destination must be outside the Android source")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.convert-", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(svg)
        destination_hash = sha256_file(temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    conversions[destination_relative] = {
        "asset_path": source_asset["path"],
        "source_sha256": source_asset["sha256"],
        "destination_sha256": destination_hash,
        "converted_fields": metadata["converted_fields"],
        "path_count": metadata["path_count"],
        "resolved_color_resource_count": metadata[
            "resolved_color_resource_count"
        ],
        "resolved_platform_color_tokens": metadata[
            "resolved_platform_color_tokens"
        ],
        "requires_target_tint": metadata["requires_target_tint"],
        "requires_auto_mirroring": metadata["requires_auto_mirroring"],
        "dynamic_color_tokens": metadata["dynamic_color_tokens"],
        "viewport": metadata["viewport"],
    }
    return True, destination_hash


def main() -> int:
    args = parse_args()
    try:
        source, source_root, asset = load_asset(
            args.manifest,
            args.asset_path,
            allow_vector_xml=True,
        )
        if source.suffix.lower() != ".xml":
            raise VectorConversionError("approved asset is not an Android vector XML")
        target, destination, destination_relative = validate_target_and_destination(
            args.target, args.destination
        )
        color_resources = load_safe_color_resources(args.manifest, args.asset_path)
        svg, metadata = convert_vector(source, color_resources)
        ledger_path, ledger = load_ledger(target)
        changed, destination_hash = install_conversion(
            source,
            source_root,
            asset,
            destination,
            destination_relative,
            svg,
            metadata,
            ledger,
            args.force,
        )
        if changed:
            write_json(ledger_path, ledger)
    except (AssetCopyError, VectorConversionError, OSError, ValueError) as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "schema": "android-to-harmony.command-result.v1",
                    "error": str(error),
                },
                ensure_ascii=False,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "schema": "android-to-harmony.command-result.v1",
                "asset_path": args.asset_path,
                "destination": destination_relative,
                "source_sha256": asset["sha256"],
                "destination_sha256": destination_hash,
                "changed": changed,
                **metadata,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
