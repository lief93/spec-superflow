#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from component_required_facts import (
    build_required_facts,
    is_preview_only_placeholder_expression,
    normalized_layout_rules,
    required_fact_gate,
    parsed_arguments, number_expression,
)
from page_snapshot import empty_style


SOURCE_SCHEMA = "android-to-harmony.source-page-spec.v1"
MANIFEST_SCHEMA = "android-to-harmony.lanhu-component-manifest.v1"
STATE_SCHEMA = "android-to-harmony.page-state-manifest.v1"

VERTICAL_TYPES = {"Column", "LazyColumn", "Card"}
HORIZONTAL_TYPES = {"Row", "LazyRow"}
OVERLAY_TYPES = {
    "Box",
    "BoxWithConstraints",
    "ConstraintLayout",
    "PrimaryCard",
    "Surface",
}
TEXT_TYPES = {"Text", "BasicText"}
IMAGE_TYPES = {"Image", "AsyncImage", "Icon", "ImageView"}
OVERLAY_NAME_MARKERS = ("Dialog", "Popup", "Modal", "BottomSheet", "Snackbar")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a Lanhu-compatible version_json and source sidecars from an "
            "Android source-page specification. Runtime captures are not inputs."
        )
    )
    parser.add_argument("--source-page", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--viewport-width-dp", required=True, type=float)
    parser.add_argument("--viewport-height-dp", required=True, type=float)
    parser.add_argument("--slice-scale", type=float, default=2.0)
    parser.add_argument("--device", default="Android source layout")
    parser.add_argument(
        "--state-fixture",
        type=Path,
        help="Optional explicit page-state values used to select source branches and expand lists.",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def clean_number(value: float) -> int | float:
    rounded = round(value, 4)
    if rounded == int(rounded):
        return int(rounded)
    return rounded


def edge_values(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {"left": 0.0, "top": 0.0, "right": 0.0, "bottom": 0.0}
    return {
        edge: finite_number(value.get(edge)) or 0.0
        for edge in ("left", "top", "right", "bottom")
    }


def style_group(node: dict[str, Any], group: str) -> dict[str, Any]:
    style = node.get("style")
    if not isinstance(style, dict):
        return {}
    value = style.get(group)
    return value if isinstance(value, dict) else {}


def has_modifier(node: dict[str, Any], name: str) -> bool:
    return any(
        isinstance(modifier, dict) and modifier.get("name") == name
        for modifier in node.get("modifiers") or []
    )


def modifier_argument(node: dict[str, Any], name: str) -> str | None:
    for modifier in node.get("modifiers") or []:
        if isinstance(modifier, dict) and modifier.get("name") == name:
            value = modifier.get("arguments")
            if isinstance(value, str):
                return value
    return None


def uses_parent_width(node: dict[str, Any]) -> bool:
    if has_modifier(node, "fillMaxWidth") or has_modifier(node, "fillMaxSize"):
        return True
    argument = modifier_argument(node, "width") or ""
    return "maxWidth" in argument or "matchParent" in argument


def parse_padding_expression(expression: str) -> dict[str, float] | None:
    values: dict[str, float] = {}
    for name, raw_value in re.findall(
        r"\b(top|bottom|start|end|left|right|horizontal|vertical)\s*=\s*(-?\d+(?:\.\d+)?)\.dp",
        expression,
    ):
        values[name] = float(raw_value)
    if not values:
        match = re.search(r"PaddingValues\(\s*(-?\d+(?:\.\d+)?)\.dp\s*\)", expression)
        if not match:
            return None
        value = float(match.group(1))
        return {"left": value, "top": value, "right": value, "bottom": value}
    horizontal = values.get("horizontal", 0.0)
    vertical = values.get("vertical", 0.0)
    return {
        "left": values.get("left", values.get("start", horizontal)),
        "top": values.get("top", vertical),
        "right": values.get("right", values.get("end", horizontal)),
        "bottom": values.get("bottom", vertical),
    }


def arrangement_spacing(node: dict[str, Any], axis: str) -> float:
    layout = style_group(node, "layout")
    normalized = layout.get(f"{axis}_arrangement")
    if isinstance(normalized, dict):
        for key in ("spacing_dp", "space_dp", "spacing"):
            number = finite_number(normalized.get(key))
            if number is not None:
                return number
    if isinstance(normalized, (int, float)):
        return float(normalized)
    semantic = ((node.get("arguments") or {}).get("semantic") or {}).get(
        f"{axis}Arrangement"
    )
    expression = semantic.get("expression") if isinstance(semantic, dict) else None
    if isinstance(expression, str):
        match = re.search(r"spacedBy\(\s*(-?\d+(?:\.\d+)?)\.dp", expression)
        if match:
            return float(match.group(1))
    return 0.0


def semantic_expression(node: dict[str, Any], name: str) -> str:
    semantic = ((node.get("arguments") or {}).get("semantic") or {}).get(name)
    expression = semantic.get("expression") if isinstance(semantic, dict) else None
    return expression if isinstance(expression, str) else ""


def resolved_alignment(node: dict[str, Any]) -> str:
    configured = style_group(node, "layout").get("alignment")
    if isinstance(configured, str) and configured:
        return configured
    component_type = str(node.get("type") or "")
    if component_type in {"Box", "BoxWithConstraints"}:
        positional = (node.get("arguments") or {}).get("positional") or []
        for argument in positional:
            expression = argument.get("expression") if isinstance(argument, dict) else None
            if isinstance(expression, str) and re.fullmatch(
                r"(?:Alignment\.)?(?:Top|Bottom|Center)(?:Start|Center|End)?",
                expression.strip(),
            ):
                return expression.strip().removeprefix("Alignment.")
        return "TopStart"
    if component_type == "Column":
        return "Start"
    if component_type == "Row":
        return "Top"
    return ""


def relative_dimension(expression: str, width: float, height: float | None) -> float | None:
    value = expression.strip()
    direct = re.fullmatch(r"(-?\d+(?:\.\d+)?)\.dp", value)
    if direct:
        return float(direct.group(1))
    relative = re.fullmatch(
        r"(-)?\s*(maxWidth|maxHeight)\s*(?:/\s*(\d+(?:\.\d+)?))?",
        value,
    )
    if relative is None:
        return None
    base = width if relative.group(2) == "maxWidth" else height
    if base is None:
        return None
    divisor = float(relative.group(3) or 1)
    result = base / divisor
    return -result if relative.group(1) else result


def offset_values(
    node: dict[str, Any], parent_width: float, parent_height: float | None
) -> tuple[float, float]:
    transform = style_group(node, "transform")
    x = finite_number(transform.get("translation_x_dp"))
    y = finite_number(transform.get("translation_y_dp"))
    if x is not None or y is not None:
        return x or 0.0, y or 0.0
    argument = modifier_argument(node, "offset") or ""
    x_match = re.search(r"x\s*=\s*([^,]+)", argument)
    y_match = re.search(r"y\s*=\s*([^,]+)", argument)
    return (
        relative_dimension(x_match.group(1), parent_width, parent_height) or 0.0
        if x_match else 0.0,
        relative_dimension(y_match.group(1), parent_width, parent_height) or 0.0
        if y_match else 0.0,
    )


UNRESOLVED = object()


def split_top_level(expression: str, delimiter: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    in_string = False
    escaped = False
    index = 0
    while index < len(expression):
        char = expression[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            index += 1
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        if depth == 0 and expression.startswith(delimiter, index):
            parts.append(expression[start:index].strip())
            index += len(delimiter)
            start = index
            continue
        index += 1
    parts.append(expression[start:].strip())
    return parts


def nested_modifier_arguments(node: dict[str, Any], name: str) -> list[str]:
    results: list[str] = []
    marker = f".{name}("
    for modifier in node.get("modifiers") or []:
        if not isinstance(modifier, dict):
            continue
        arguments = modifier.get("arguments")
        if not isinstance(arguments, str):
            continue
        if modifier.get("name") == name:
            results.append(arguments)
        start = 0
        while True:
            marker_index = arguments.find(marker, start)
            if marker_index < 0:
                break
            open_index = marker_index + len(marker) - 1
            depth = 0
            in_string = False
            escaped = False
            for index in range(open_index, len(arguments)):
                char = arguments[index]
                if in_string:
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == '"':
                        in_string = False
                    continue
                if char == '"':
                    in_string = True
                elif char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
                    if depth == 0:
                        results.append(arguments[open_index + 1:index].strip())
                        start = index + 1
                        break
            else:
                break
    return results


def call_arguments(expression: str) -> tuple[list[str], dict[str, str]]:
    positional: list[str] = []
    named: dict[str, str] = {}
    for item in split_top_level(expression, ","):
        assignment = split_top_level(item, "=")
        if len(assignment) == 2 and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", assignment[0]):
            named[assignment[0]] = assignment[1]
        elif item:
            positional.append(item)
    return positional, named


def uniform_corner_radius(radius: float) -> dict[str, float]:
    return {
        "top_left": radius,
        "top_right": radius,
        "bottom_right": radius,
        "bottom_left": radius,
    }


def component_dimensions(component: dict[str, Any]) -> list[float]:
    layout = style_group(component, "layout")
    asset = style_group(component, "asset")
    return [
        float(value)
        for value in (
            layout.get("width_dp") or asset.get("width_dp"),
            layout.get("height_dp") or asset.get("height_dp"),
        )
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]


def lookup_path(expression: str, environment: dict[str, Any]) -> Any:
    expression = expression.strip()
    if expression in environment:
        return environment[expression]
    parts = expression.split(".")
    if not parts or parts[0] not in environment:
        return UNRESOLVED
    value: Any = environment[parts[0]]
    for part in parts[1:]:
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return UNRESOLVED
    return value


def evaluate_static_call(expression: str, environment: dict[str, Any]) -> Any:
    inventory = environment.get('__source_value_inventory') or {}
    match = re.fullmatch(r'(.+)\.(\w+)\((.*)\)', expression, re.S)
    if not match:
        return UNRESOLVED
    owner, method, arguments = match.groups()
    active = environment.get('__static_calls', ())
    if expression in active:
        return UNRESOLVED
    positional, named = call_arguments(arguments)

    def bindings(parameters, local):
        for index, parameter in enumerate(parameters):
            name = parameter['name']
            value = named.get(name, positional[index] if index < len(positional) else parameter.get('default'))
            local[name] = evaluate_expression(value, environment) if isinstance(value, str) else UNRESOLVED

    classes = [item for item in inventory.get('classes', []) if item.get('name') == owner]
    if len(classes) == 1:
        factories = [f for f in classes[0].get('factories', []) if f.get('name') == method and f.get('static_record') is True]
        if len(factories) != 1:
            return UNRESOLVED
        factory = factories[0]
        local = dict(environment, __static_calls=active + (expression,))
        bindings(factory.get('parameters', []), local)
        for name, value in factory.get('local_values', {}).items():
            local[name] = evaluate_expression(value, local)
        constructor = re.fullmatch(re.escape(owner) + r'\((.*)\)', factory['return_expression'], re.S)
        if not constructor:
            return UNRESOLVED
        values, fields = call_arguments(constructor.group(1))
        record = {}
        for index, field in enumerate(classes[0].get('properties', [])):
            value = fields.get(field['name'], values[index] if index < len(values) else field.get('default'))
            record[field['name']] = evaluate_expression(value, local) if isinstance(value, str) else UNRESOLVED
        return record
    helpers = [item for item in inventory.get('string_helpers', []) if item.get('name') == method]
    if len(helpers) == 1 and helpers[0].get('kind') == 'group_string':
        helper = helpers[0]
        value = evaluate_expression(owner, dict(environment, __static_calls=active + (expression,)))
        local = {}
        bindings(helper.get('parameters', []), local)
        group, separator = local.get(helper['group_parameter']), local.get(helper['separator_parameter'])
        if isinstance(value, str) and isinstance(group, int) and group > 0 and isinstance(separator, str):
            return separator.join(value[i:i + group] for i in range(0, len(value), group))
    return UNRESOLVED


def evaluate_expression(expression: str, environment: dict[str, Any]) -> Any:
    value = re.sub(r"\s+", " ", expression.strip()).strip()
    while value.startswith("(") and value.endswith(")"):
        depth = 0
        closes_at_end = False
        for index, char in enumerate(value):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    closes_at_end = index == len(value) - 1
                    break
        if not closes_at_end:
            break
        value = value[1:-1].strip()
    disjunction = split_top_level(value, "||")
    if len(disjunction) > 1:
        for part in disjunction:
            resolved = evaluate_expression(part, environment)
            if not isinstance(resolved, bool):
                return UNRESOLVED
            if resolved is True:
                return True
        return False
    conjunction = split_top_level(value, "&&")
    if len(conjunction) > 1:
        for part in conjunction:
            resolved = evaluate_expression(part, environment)
            if not isinstance(resolved, bool):
                return UNRESOLVED
            if resolved is False:
                return False
        return True
    if value.startswith("!"):
        resolved = evaluate_expression(value[1:].strip(), environment)
        return not resolved if isinstance(resolved, bool) else UNRESOLVED
    for suffix, result in ((".isNotEmpty()", True), (".isEmpty()", False)):
        if value.endswith(suffix):
            resolved = evaluate_expression(value[: -len(suffix)], environment)
            if not isinstance(resolved, (list, tuple, dict, str)):
                return UNRESOLVED
            return bool(resolved) is result
    membership = split_top_level(value, " in ")
    if len(membership) == 2:
        left = evaluate_expression(membership[0], environment)
        right = evaluate_expression(membership[1], environment)
        if left is UNRESOLVED or right is UNRESOLVED:
            return UNRESOLVED
        return left in right
    type_check = re.fullmatch(
        r"(.+?)\s+(!?is)\s+([A-Za-z_][A-Za-z0-9_.]*)",
        value,
    )
    if type_check:
        resolved = evaluate_expression(type_check.group(1), environment)
        if not isinstance(resolved, dict) or not isinstance(resolved.get("__type"), str):
            return UNRESOLVED
        matches = resolved["__type"] == type_check.group(3)
        return not matches if type_check.group(2) == "!is" else matches
    comparison = re.fullmatch(r"(.+?)\s*(==|!=|<=|>=|<|>)\s*(.+)", value)
    if comparison and not value.startswith('if'):
        left = evaluate_expression(comparison.group(1), environment)
        right = evaluate_expression(comparison.group(3), environment)
        if left is UNRESOLVED or right is UNRESOLVED:
            return UNRESOLVED
        operator = comparison.group(2)
        if operator == "==":
            return left == right
        if operator == "!=":
            return left != right
        if operator == "<":
            return left < right
        if operator == ">":
            return left > right
        if operator == "<=":
            return left <= right
        return left >= right
    conditional = re.fullmatch(r"if\s*\((.+)\)\s*\{\s*(.+?)\s*}\s*else\s*\{\s*(.+?)\s*}", value)
    if conditional:
        condition = evaluate_expression(conditional.group(1), environment)
        if condition is UNRESOLVED:
            return UNRESOLVED
        return evaluate_expression(conditional.group(2 if condition else 3), environment)
    inline_conditional = re.fullmatch(
        r"if\s*\(([^()]*)\)\s*(.+?)\s+else\s+(.+)", value
    )
    if inline_conditional:
        condition = evaluate_expression(inline_conditional.group(1), environment)
        if condition is UNRESOLVED:
            return UNRESOLVED
        return evaluate_expression(
            inline_conditional.group(2 if condition else 3), environment
        )
    as_string = re.fullmatch(r"(.+?)(\?)?\.asString\s*\(\s*\)", value)
    if as_string:
        resolved = evaluate_expression(as_string.group(1), environment)
        if resolved is None and as_string.group(2):
            return None
        if isinstance(resolved, str):
            return resolved
        if isinstance(resolved, dict) and isinstance(resolved.get("__string__"), str):
            return resolved["__string__"]
        return UNRESOLVED
    list_match = re.fullmatch(r"listOf\s*\((.*)\)", value)
    if list_match:
        return [
            evaluate_expression(item, environment)
            for item in split_top_level(list_match.group(1), ",")
            if item
        ]
    constructor = re.fullmatch(
        r"([A-Za-z_][A-Za-z0-9_.]*)\s*\((.*)\)",
        value,
    )
    constructor_specs = environment.get("__constructors__")
    if constructor and isinstance(constructor_specs, dict):
        constructor_name = constructor.group(1)
        constructor_spec = constructor_specs.get(constructor_name)
        if isinstance(constructor_spec, dict):
            fields = constructor_spec.get("fields")
            if not isinstance(fields, list) or not all(isinstance(field, str) for field in fields):
                return UNRESOLVED
            positional, named = call_arguments(constructor.group(2))
            result: dict[str, Any] = {"__type": constructor_name}
            for index, field in enumerate(fields):
                field_expression = named.get(field)
                if field_expression is None and index < len(positional):
                    field_expression = positional[index]
                if field_expression is None:
                    return UNRESOLVED
                resolved = evaluate_expression(field_expression, environment)
                if resolved is UNRESOLVED:
                    return UNRESOLVED
                result[field] = resolved
            string_field = constructor_spec.get("string_field")
            if isinstance(string_field, str) and isinstance(result.get(string_field), str):
                result["__string__"] = result[string_field]
            return result
    string_resource = re.fullmatch(r"stringResource\s*\(\s*(?:id\s*=\s*)?(.+)\)", value)
    if string_resource:
        return evaluate_expression(string_resource.group(1), environment)
    painter_resource = re.fullmatch(r"painterResource\s*\(\s*(?:id\s*=\s*)?(.+)\)", value)
    if painter_resource:
        return evaluate_expression(painter_resource.group(1), environment)
    ui_string_resource = re.fullmatch(r"UiText\.StringResource\s*\(\s*(.+)\)", value)
    if ui_string_resource:
        resolved = evaluate_expression(ui_string_resource.group(1), environment)
        return resolved if resolved is not UNRESOLVED else ui_string_resource.group(1)
    if value.startswith("ImageRequest.Builder(") and value.endswith(".build()"):
        data = re.search(r"\.data\s*\(([^()]+)\)", value)
        if data is not None:
            return evaluate_expression(data.group(1), environment)
    collected_state = re.fullmatch(
        r"(.+)\.collectAsStateWithLifecycle\s*\(.*\)\.value", value
    )
    if collected_state:
        return evaluate_expression(collected_state.group(1), environment)
    color_filter = re.fullmatch(r"ColorFilter\.tint\s*\(\s*(.+)\s*\)", value)
    if color_filter:
        return evaluate_expression(color_filter.group(1), environment)
    color = re.fullmatch(r"Color\s*\(\s*0x([0-9A-Fa-f]{8})\s*\)", value)
    if color:
        return f"#{color.group(1).upper()}"
    if value == "Color.White":
        return "#FFFFFFFF"
    if value == "Color.Gray":
        return "#FF888888"
    if value == "Color.Transparent":
        return "#00000000"
    if re.fullmatch(r"#[0-9A-Fa-f]{8}", value):
        return value.upper()
    if value in {"null", "None"}:
        return None
    if value in {"true", "false"}:
        return value == "true"
    dimension = re.fullmatch(r"(-?\d+(?:\.\d+)?)\.dp", value)
    if dimension:
        return float(dimension.group(1))
    rounded_shape = re.fullmatch(r"RoundedCornerShape\s*\((.+)\)", value)
    if rounded_shape:
        radius = evaluate_expression(rounded_shape.group(1), environment)
        return (
            {"kind": "rounded_corner", "radius_dp": radius}
            if isinstance(radius, (int, float))
            else UNRESOLVED
        )
    if value == "CircleShape":
        return {"kind": "circle"}
    if re.fullmatch(r"-?\d+(?:\.\d+)?[fFL]?", value):
        return float(value.rstrip("fFL")) if "." in value else int(value.rstrip("fFL"))
    multiplication = split_top_level(value, "*")
    if len(multiplication) > 1:
        factors = [evaluate_expression(part, environment) for part in multiplication]
        if all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in factors):
            result = 1.0
            for factor in factors:
                result *= float(factor)
            return result
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        try:
            literal = json.loads('"' + value[1:-1].replace('\\$', '$') + '"')
        except json.JSONDecodeError:
            return UNRESOLVED
        if "${" not in literal:
            return literal
        def replace_literal(match: re.Match[str]) -> str:
            resolved = evaluate_expression(match.group(1), environment)
            return match.group(0) if resolved is UNRESOLVED else str(resolved)
        rendered = re.sub(r"\$\{([^}]+)}", replace_literal, literal)
        return rendered if "${" not in rendered else UNRESOLVED
    size_match = re.fullmatch(r"(.+)\.size", value)
    if size_match:
        resolved = evaluate_expression(size_match.group(1), environment)
        return len(resolved) if isinstance(resolved, (list, tuple, dict, str)) else UNRESOLVED
    percent_match = re.fullmatch(
        r"\((.+)\s*\*\s*100\)\.toInt\(\)\.toString\(\)", value
    )
    if percent_match:
        resolved = evaluate_expression(percent_match.group(1), environment)
        return str(int(float(resolved) * 100)) if isinstance(resolved, (int, float)) else UNRESOLVED
    floor_percent = re.fullmatch(
        r"floor\s*\(\s*(.+)\s*\*\s*100\s*\)\.roundToInt\(\)", value
    )
    if floor_percent:
        resolved = evaluate_expression(floor_percent.group(1), environment)
        return int(float(resolved) * 100) if isinstance(resolved, (int, float)) else UNRESOLVED
    if "${" in value:
        def replace(match: re.Match[str]) -> str:
            resolved = evaluate_expression(match.group(1), environment)
            return match.group(0) if resolved is UNRESOLVED else str(resolved)
        rendered = re.sub(r"\$\{([^}]+)}", replace, value.strip('"'))
        return rendered if "${" not in rendered else UNRESOLVED
    resolved = lookup_path(value, environment)
    return evaluate_static_call(value, environment) if resolved is UNRESOLVED else resolved


def stroke_width(expression: str, environment: dict[str, Any]) -> float | None:
    match = re.fullmatch(r"Stroke\s*\(\s*(.+?)\s*\)", expression.strip())
    if match is None:
        return None
    width_expression = re.sub(r"\.toPx\(\)\s*$", "", match.group(1).strip())
    resolved = evaluate_expression(width_expression, environment)
    if isinstance(resolved, (int, float)) and not isinstance(resolved, bool) and resolved > 0:
        return float(resolved)
    return None


def project_progress_ring(
    component: dict[str, Any], environment: dict[str, Any]
) -> bool:
    commands = component.get("custom_draw_commands")
    if not isinstance(commands, list) or len(commands) != 2:
        return False
    resolved: list[dict[str, Any]] = []
    for command in commands:
        arguments = command.get("arguments") if isinstance(command, dict) else None
        if (
            not isinstance(command, dict)
            or command.get("kind") != "arc"
            or not isinstance(arguments, dict)
        ):
            return False
        required = {"color", "startAngle", "sweepAngle", "useCenter", "style"}
        if not required.issubset(arguments):
            return False
        color = evaluate_expression(str(arguments["color"]), environment)
        start = evaluate_expression(str(arguments["startAngle"]), environment)
        sweep = evaluate_expression(str(arguments["sweepAngle"]), environment)
        use_center = evaluate_expression(str(arguments["useCenter"]), environment)
        width = stroke_width(str(arguments["style"]), environment)
        if (
            not isinstance(color, str)
            or re.fullmatch(r"#[0-9A-F]{8}", color) is None
            or not isinstance(start, (int, float))
            or not isinstance(sweep, (int, float))
            or use_center is not False
            or width is None
        ):
            return False
        resolved.append(
            {
                "color": color,
                "start": float(start),
                "sweep": float(sweep),
                "width": width,
            }
        )
    track, active = resolved
    if (
        abs(track["sweep"] - 360.0) > 0.001
        or abs(track["start"] - active["start"]) > 0.001
        or abs(track["width"] - active["width"]) > 0.001
        or active["sweep"] < 0
        or active["sweep"] > 360
    ):
        return False
    value = round(active["sweep"] / 3.6)
    component["type"] = "ProgressRing"
    style_group(component, "content")["text"] = f"{value}%"
    component["custom_draw"] = {
        "kind": "ring_progress",
        "value": value,
        "total": 100,
        "start_angle_degrees": clean_number(track["start"]),
        "stroke_width_dp": clean_number(track["width"]),
        "track_color": track["color"],
        "active_color": active["color"],
    }
    component["unresolved"] = [
        item
        for item in component.get("unresolved") or []
        if not isinstance(item, dict) or item.get("path") != "style.custom_draw"
    ]
    return True


def set_path(target: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = target
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


def resolve_input_decoration(node: dict[str, Any], environment: dict[str, Any]) -> None:
    source = node.get('source') or {}
    if source.get('decoration_kind') != 'material3-outlined':
        return
    expression = semantic_expression(node, 'supportingText').strip()
    if not expression or expression == 'null':
        present = False
    elif expression.startswith('{') and expression.endswith('}'):
        # A non-null composable lambda reserves space even when its body emits nothing.
        present = True
    else:
        value = evaluate_expression(expression, environment)
        present = False if value is None else None
    source['input_decoration'] = {
        'kind': 'material3-outlined', 'text_min_height_dp': 24,
        'supporting_text': present, 'supporting_min_height_dp': 16,
        'supporting_padding_dp': dict(left=16, right=16, top=4, bottom=0),
    }
    if present is None:
        node.setdefault('unresolved', []).append({
            'path': 'source.input_decoration.supporting_text', 'expression': expression,
            'reason': 'supporting slot nullability is unresolved; no empty-slot assumption',
        })


def project_source_page(
    payload: dict[str, Any], fixture: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    if fixture.get("schema") != "android-to-harmony.page-state-fixture.v1":
        raise ValueError(f"unsupported state fixture schema: {fixture.get('schema')!r}")
    if fixture.get("page") != payload.get("page"):
        raise ValueError("state fixture page/state must match source page")
    original = {
        component["id"]: component
        for component in payload.get("components") or []
        if isinstance(component, dict) and isinstance(component.get("id"), str)
    }
    children: dict[str, list[str]] = defaultdict(list)
    root_ids: list[str] = []
    for component in original.values():
        parent_id = component.get("parent_id")
        if isinstance(parent_id, str):
            children[parent_id].append(component["id"])
        else:
            root_ids.append(component["id"])
    for child_ids in children.values():
        child_ids.sort(key=lambda item: original[item].get("sibling_index", 0))
    root_ids.sort(key=lambda item: original[item].get("sibling_index", 0))

    base_environment = dict(fixture.get("values") or {})
    base_environment.update(fixture.get("symbols") or {})
    base_environment['__source_value_inventory'] = payload.get('source_value_inventory') or {}
    source_assets = {
        item["resource"]: item
        for item in payload.get("source_assets") or []
        if isinstance(item, dict) and isinstance(item.get("resource"), str)
    }
    emitted: list[dict[str, Any]] = []
    inactive: list[str] = []
    expanded_count = 0

    def inactive_subtree(component_id: str) -> None:
        inactive.append(component_id)
        for child_id in children.get(component_id, []):
            inactive_subtree(child_id)

    def resolve_environment(node: dict[str, Any], environment: dict[str, Any]) -> dict[str, Any]:
        local = dict(environment)
        for name, expression in (node.get("parameter_bindings") or {}).items():
            resolved = evaluate_expression(str(expression), local)
            local[str(name)] = resolved
        pending = dict(node.get("local_values") or {})
        for _ in range(len(pending) + 1):
            progressed = False
            for name, expression in list(pending.items()):
                resolved = evaluate_expression(str(expression), local)
                if resolved is UNRESOLVED:
                    local[str(name)] = UNRESOLVED
                    continue
                local[str(name)] = resolved
                del pending[name]
                progressed = True
            if not progressed:
                break
        return local

    def visibility_value(node: dict[str, Any], environment: dict[str, Any]) -> Any:
        condition = node.get("visibility_condition")
        expression = condition.get("expression") if isinstance(condition, dict) else None
        return evaluate_expression(expression, environment) if isinstance(expression, str) else True

    def resolve_node(node: dict[str, Any], local: dict[str, Any]) -> dict[str, Any]:
        result = copy.deepcopy(node)
        project_progress_ring(result, local)
        unresolved = []
        for item in result.get("unresolved") or []:
            if not isinstance(item, dict):
                unresolved.append(item)
                continue
            expression = str(item.get("expression") or "")
            path = item.get("path")
            expression_parts = split_top_level(expression, ",")
            value_expression = (
                expression_parts[0]
                if path == "style.surface.background" and expression_parts
                else expression
            )
            resolved = evaluate_expression(value_expression, local)
            if resolved is UNRESOLVED or not isinstance(item.get("path"), str):
                unresolved.append(item)
            else:
                projected_value = (
                    {"type": "solid", "color": resolved}
                    if path == "style.surface.background"
                    and isinstance(resolved, str)
                    and re.fullmatch(r"#[0-9A-Fa-f]{8}", resolved)
                    else resolved
                )
                set_path(result, item["path"], projected_value)
                if (
                    path == "style.surface.background"
                    and any(part.strip() == "CircleShape" for part in expression_parts[1:])
                ):
                    dimensions = component_dimensions(result)
                    if dimensions:
                        radius = min(dimensions) / 2
                        style_group(result, "surface")["corner_radius_dp"] = {
                            "top_left": radius,
                            "top_right": radius,
                            "bottom_right": radius,
                            "bottom_left": radius,
                        }
        result["unresolved"] = [
            item
            for item in unresolved
            if not (
                item.get("path") == "style.content.placeholder"
                and is_preview_only_placeholder_expression(item.get("expression"))
            )
        ]
        surface = style_group(result, "surface")
        for arguments in nested_modifier_arguments(result, "background"):
            positional, named = call_arguments(arguments)
            applied = False
            color_expression = named.get("color") or (positional[0] if positional else None)
            if surface.get("background") is None and isinstance(color_expression, str):
                color_value = evaluate_expression(color_expression, local)
                if (
                    isinstance(color_value, str)
                    and re.fullmatch(r"#[0-9A-Fa-f]{8}", color_value)
                ):
                    surface["background"] = {"type": "solid", "color": color_value}
                    applied = True
            shape_expression = named.get("shape") or (
                positional[1] if len(positional) > 1 else None
            )
            shape_value = (
                evaluate_expression(shape_expression, local)
                if isinstance(shape_expression, str)
                else None
            )
            if surface.get("corner_radius_dp") is None and isinstance(shape_value, dict):
                if shape_value.get("kind") == "rounded_corner" and isinstance(
                    shape_value.get("radius_dp"), (int, float)
                ):
                    surface["corner_radius_dp"] = uniform_corner_radius(
                        float(shape_value["radius_dp"])
                    )
                    applied = True
                elif shape_value.get("kind") == "circle":
                    dimensions = component_dimensions(result)
                    if dimensions:
                        surface["corner_radius_dp"] = uniform_corner_radius(
                            min(dimensions) / 2
                        )
                        applied = True
            if applied:
                break
        content = style_group(result, "content")
        if (
            content.get("text") is None
            or isinstance(content.get("text"), str) and "${" in content["text"]
        ) and result.get("type") in TEXT_TYPES:
            semantic = (result.get("arguments") or {}).get("semantic") or {}
            candidates = [semantic.get("text")]
            candidates.extend((result.get("arguments") or {}).get("positional") or [])
            for candidate in candidates:
                expression = candidate.get("expression") if isinstance(candidate, dict) else None
                if not isinstance(expression, str):
                    continue
                resolved = evaluate_expression(expression, local)
                if resolved is not UNRESOLVED:
                    result["style"]["content"]["text"] = str(resolved)
                    break
        typography = style_group(result, "typography")
        semantic = (result.get("arguments") or {}).get("semantic") or {}
        color_argument = semantic.get("color")
        color_expression = (
            color_argument.get("resolved_local_expression")
            or color_argument.get("expression")
            if isinstance(color_argument, dict)
            else None
        )
        if isinstance(color_expression, str):
            resolved_color = evaluate_expression(color_expression, local)
            if (
                isinstance(resolved_color, str)
                and re.fullmatch(r"#[0-9A-Fa-f]{8}", resolved_color)
            ):
                typography["color"] = resolved_color.upper()
        asset = style_group(result, "asset")
        if asset.get("resource") is None and result.get("type") in IMAGE_TYPES:
            painter = semantic.get("painter") or semantic.get("model")
            expression = painter.get("expression") if isinstance(painter, dict) else None
            if isinstance(expression, str):
                resolved = evaluate_expression(expression, local)
                if isinstance(resolved, str):
                    result["style"]["asset"]["resource"] = resolved
        semantic = (result.get("arguments") or {}).get("semantic") or {}
        color_filter = semantic.get("colorFilter")
        color_filter_expression = (
            color_filter.get("resolved_local_expression")
            or color_filter.get("expression")
            if isinstance(color_filter, dict)
            else None
        )
        if isinstance(color_filter_expression, str):
            resolved_tint = evaluate_expression(color_filter_expression, local)
            if (
                isinstance(resolved_tint, str)
                and re.fullmatch(r"#[0-9A-Fa-f]{8}", resolved_tint)
            ):
                asset["tint"] = resolved_tint.upper()
        resource = result["style"]["asset"].get("resource")
        if isinstance(resource, str):
            local_resource = re.fullmatch(r'android\.resource://[A-Za-z0-9_.]+/(?:drawable|mipmap)/([a-z][a-z0-9_]*)', resource)
            if local_resource and local_resource.group(1) in source_assets:
                resource = local_resource.group(1)
                result['style']['asset']['resource'] = resource
        evidence = source_assets.get(resource) if isinstance(resource, str) else None
        if (
            result["style"]["asset"].get("sha256") is None
            and isinstance(evidence, dict)
            and isinstance(evidence.get("sha256"), str)
        ):
            result["style"]["asset"]["sha256"] = evidence["sha256"]
            result.setdefault("provenance", []).append(
                {
                    "paths": ["style.asset.sha256"],
                    "origin": "source_resolved",
                    "source": evidence.get("path"),
                }
            )
        result["layout_rules"] = normalized_layout_rules(result)
        resolve_input_decoration(result, local)
        result["required_facts"] = build_required_facts(result)
        return result

    def emit_single(
        component_id: str,
        parent_id: str | None,
        environment: dict[str, Any],
        suffix: str,
    ) -> str | None:
        source = original[component_id]
        local = resolve_environment(source, environment)
        visible = visibility_value(source, local)
        if visible is False:
            inactive_subtree(component_id)
            return None
        if visible is not True:
            expression = (source.get("visibility_condition") or {}).get("expression")
            raise ValueError(
                f"state condition requires a resolved boolean for {component_id}: {expression}"
            )
        node = resolve_node(source, local)
        new_id = component_id + suffix
        node["id"] = new_id
        if suffix and isinstance(node.get("semantic_key"), str):
            match = re.fullmatch(r"(.+?)(?:__(\d+))?", node["semantic_key"])
            base_key = match.group(1) if match else node["semantic_key"]
            static_instance = match.group(2) if match else None
            instance_parts = [
                part
                for part in (static_instance, suffix.lstrip("_").replace("__", "-"))
                if part
            ]
            node["semantic_key"] = (
                f"{base_key}__instance_{'-'.join(instance_parts)}"
            )
        node["source_component_id"] = component_id
        node["parent_id"] = parent_id
        node["children_ids"] = []
        node["sibling_index"] = 0
        emitted.append(node)
        for child_id in children.get(component_id, []):
            emit(child_id, new_id, local, suffix)
        return new_id

    def emit(
        component_id: str,
        parent_id: str | None,
        environment: dict[str, Any],
        suffix: str,
    ) -> list[str]:
        nonlocal expanded_count
        source = original[component_id]
        local = resolve_environment(source, environment)
        if visibility_value(source, local) is False:
            inactive_subtree(component_id)
            return []
        context = source.get("list_item_context")
        collection_expression = context.get("collection") if isinstance(context, dict) else None
        item_parameter = context.get("item_parameter") if isinstance(context, dict) else None
        if isinstance(collection_expression, str) and isinstance(item_parameter, str):
            collection = evaluate_expression(collection_expression, local)
            if not isinstance(collection, list):
                raise ValueError(
                    f"state collection requires a resolved list for {component_id}: {collection_expression}"
                )
            if not collection:
                inactive_subtree(component_id)
                return []
            ids = []
            for index, item in enumerate(collection, start=1):
                item_environment = dict(local)
                item_environment[item_parameter] = item
                item_suffix = f"{suffix}__item{index}"
                emitted_id = emit_single(component_id, parent_id, item_environment, item_suffix)
                if emitted_id is not None:
                    ids.append(emitted_id)
                    expanded_count += 1
            return ids
        emitted_id = emit_single(component_id, parent_id, environment, suffix)
        return [emitted_id] if emitted_id is not None else []

    # Source siblings can belong to different states. Select the state before
    # requiring the single, layout-owned tree consumed by the renderer.
    active_roots = []
    for root_id in root_ids:
        active_roots.extend(emit(root_id, None, base_environment, ""))
    if not active_roots:
        raise ValueError("selected page state has no active root")
    if len(active_roots) != 1:
        raise ValueError(
            "selected page state has multiple active roots; an explicit source parent layout "
            f"is required: {', '.join(active_roots)}"
        )
    emitted_by_id = {component["id"]: component for component in emitted}
    emitted_children: dict[str, list[str]] = defaultdict(list)
    for component in emitted:
        parent_id = component.get("parent_id")
        if isinstance(parent_id, str):
            emitted_children[parent_id].append(component["id"])
    for parent_id, child_ids in emitted_children.items():
        emitted_by_id[parent_id]["children_ids"] = child_ids
        for index, child_id in enumerate(child_ids):
            emitted_by_id[child_id]["sibling_index"] = index
    projected = copy.deepcopy(payload)
    projected["components"] = emitted
    inactive_only = set(original) - {node["source_component_id"] for node in emitted}
    projected["layout_relationships"] = [
        relationship for relationship in payload.get("layout_relationships") or []
        if relationship.get("container_id") not in inactive_only
    ]
    projected["required_fact_gate"] = required_fact_gate(emitted)
    projected["state_projection"] = {
        "fixture_schema": fixture["schema"],
        "source_component_count": len(original),
        "active_component_count": len(emitted),
        "active_root_id": active_roots[0],
        "inactive_source_ids": sorted(set(inactive)),
        "expanded_list_instances": expanded_count,
    }
    return projected, projected["state_projection"]


class SourceTree:
    def __init__(self, payload: dict[str, Any]) -> None:
        if payload.get("schema") != SOURCE_SCHEMA:
            raise ValueError(f"unsupported source page schema: {payload.get('schema')!r}")
        raw_components = payload.get("components")
        if not isinstance(raw_components, list) or not raw_components:
            raise ValueError("source page must contain components")
        self.payload = payload
        self.nodes: dict[str, dict[str, Any]] = {}
        self.order: list[str] = []
        for raw in raw_components:
            if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
                raise ValueError("every source component must have a string id")
            component_id = raw["id"]
            if component_id in self.nodes:
                raise ValueError(f"duplicate source component id: {component_id}")
            self.nodes[component_id] = raw
            self.order.append(component_id)

        roots = [node for node in self.nodes.values() if node.get("parent_id") is None]
        if len(roots) != 1:
            raise ValueError(f"source page must have exactly one root; found {len(roots)}")
        self.root_id = roots[0]["id"]
        derived_children: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for node in self.nodes.values():
            parent_id = node.get("parent_id")
            if parent_id is None:
                continue
            if parent_id not in self.nodes:
                raise ValueError(f"unknown parent {parent_id!r} for {node['id']!r}")
            derived_children[parent_id].append(node)
        for children in derived_children.values():
            children.sort(
                key=lambda item: (
                    finite_number(item.get("sibling_index")) or 0,
                    self.order.index(item["id"]),
                )
            )
        self.children = {
            parent_id: [child["id"] for child in children]
            for parent_id, children in derived_children.items()
        }
        self._validate_declared_children()
        self._validate_connected()

    def _validate_declared_children(self) -> None:
        for node in self.nodes.values():
            declared = node.get("children_ids")
            if declared is None:
                continue
            if not isinstance(declared, list):
                raise ValueError(f"children_ids must be a list for {node['id']!r}")
            actual = self.children.get(node["id"], [])
            if declared and declared != actual:
                raise ValueError(
                    f"child order mismatch for {node['id']!r}: declared={declared}, actual={actual}"
                )

    def _validate_connected(self) -> None:
        visited: set[str] = set()

        def visit(component_id: str, active: set[str]) -> None:
            if component_id in active:
                raise ValueError(f"source component cycle at {component_id!r}")
            if component_id in visited:
                return
            visited.add(component_id)
            for child_id in self.children.get(component_id, []):
                visit(child_id, active | {component_id})

        visit(self.root_id, set())
        if visited != set(self.nodes):
            missing = sorted(set(self.nodes) - visited)
            raise ValueError(f"source components are disconnected: {missing}")


class SourceLayout:
    def __init__(self, tree: SourceTree, viewport_width: float, viewport_height: float) -> None:
        self.tree = tree
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.frames: dict[str, dict[str, float]] = {}
        self.measured_sizes: dict[str, dict[str, float]] = {}
        self.geometry_status: dict[str, str] = {}
        self.geometry_reasons: dict[str, list[str]] = defaultdict(list)
        self.consumed_relationship_ids: set[str] = set()
        self.phase_failures: list[dict[str, str]] = []
        self.drawn_component_ids: set[str] = set()
        self.draw_output_paths: dict[str, list[str]] = {}
        self.measure_complete = False
        self.layout_complete = False
        self._measure_cache: dict[tuple[str, float], tuple[float, float]] = {}
        self.dimension_tokens: dict[str, float] = {}
        for token in tree.payload.get("source_tokens") or []:
            if not isinstance(token, dict) or not isinstance(token.get("name"), str):
                continue
            for dimension in token.get("dimensions") or []:
                if not isinstance(dimension, dict) or dimension.get("unit") != "dp":
                    continue
                raw = dimension.get("value")
                try:
                    resolved = finite_number(float(raw))
                except (TypeError, ValueError):
                    resolved = None
                if resolved is not None:
                    self.dimension_tokens[token["name"]] = resolved
                    break
        self.relationships_by_container: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for relationship in tree.payload.get("layout_relationships") or []:
            if isinstance(relationship, dict) and isinstance(
                relationship.get("container_id"), str
            ):
                self.relationships_by_container[relationship["container_id"]].append(
                    relationship
                )

    def calculate(self) -> dict[str, dict[str, float]]:
        # Keep the same phase boundary as Android/Compose: measure the complete
        # source tree first, then place it. Drawing is performed by lanhu_layer.
        self._measure(self.tree.root_id, self.viewport_width)
        self.measure_complete = len(self.measured_sizes) == len(self.tree.nodes)
        self._layout(
            self.tree.root_id,
            0.0,
            0.0,
            self.viewport_width,
            self.viewport_height,
            force_size=(self.viewport_width, self.viewport_height),
        )
        self.layout_complete = len(self.frames) == len(self.tree.nodes)
        return self.frames

    def _explicit_size(self, node: dict[str, Any]) -> tuple[float | None, float | None]:
        layout = style_group(node, "layout")
        width = finite_number(layout.get("width_dp"))
        height = finite_number(layout.get("height_dp"))
        for modifier in node.get("modifiers") or []:
            if not isinstance(modifier, dict) or modifier.get("name") not in {
                "width", "requiredWidth", "height", "requiredHeight"
            }:
                continue
            argument = str(modifier.get("arguments") or "").strip()
            resolved = self.dimension_tokens.get(argument)
            if resolved is None:
                match = re.fullmatch(r"(-?\d+(?:\.\d+)?)\.dp", argument)
                resolved = float(match.group(1)) if match else None
            if modifier["name"] in {"width", "requiredWidth"} and width is None:
                width = resolved
            elif modifier["name"] in {"height", "requiredHeight"} and height is None:
                height = resolved
        return width, height

    def _intrinsic_image_size(self, node: dict[str, Any], width: float, height: float | None = None) -> tuple[float, float] | None:
        if node.get("type") not in IMAGE_TYPES:
            return None
        asset = style_group(node, "asset")
        intrinsic_width = finite_number(asset.get("width_dp"))
        intrinsic_height = finite_number(asset.get("height_dp"))
        if not intrinsic_width or not intrinsic_height:
            return None
        scale = min(1.0, width / intrinsic_width, height / intrinsic_height if height is not None else 1.0)
        if asset.get("content_scale") not in {None, "fit", "inside"}:
            return min(width, intrinsic_width), min(height, intrinsic_height) if height is not None else intrinsic_height
        return intrinsic_width * scale, intrinsic_height * scale

    def effective_padding(self, node: dict[str, Any]) -> dict[str, float]:
        raw = style_group(node, "layout").get("padding_dp")
        if isinstance(raw, dict):
            children = self.tree.children.get(node["id"], [])
            if (
                len(children) == 1
                and str(node.get("component_kind") or "").startswith("project")
                and "modifier"
                in " ".join(
                    str(modifier.get("arguments") or "")
                    for modifier in self.tree.nodes[children[0]].get("modifiers") or []
                    if isinstance(modifier, dict)
                )
            ):
                self.geometry_reasons[node["id"]].append(
                    "invocation padding is applied by the project component internal root"
                )
                return edge_values(None)
            return edge_values(raw)
        parent_id = node.get("parent_id")
        if not isinstance(parent_id, str):
            return edge_values(None)
        parent = self.tree.nodes[parent_id]
        modifier_text = " ".join(
            str(modifier.get("arguments") or "")
            for modifier in node.get("modifiers") or []
            if isinstance(modifier, dict)
        )
        for invocation in (parent.get("arguments") or {}).get("invocation") or []:
            if not isinstance(invocation, dict):
                continue
            name = invocation.get("name")
            expression = invocation.get("expression")
            if (
                isinstance(name, str)
                and isinstance(expression, str)
                and name in modifier_text
            ):
                parsed = parse_padding_expression(expression)
                if parsed is not None:
                    self.geometry_reasons[node["id"]].append(
                        f"padding propagated from parent parameter {name}"
                    )
                    return parsed
        return edge_values(None)

    def _measure(self, component_id: str, available_width: float) -> tuple[float, float]:
        cache_key = (component_id, round(max(0.0, available_width), 4))
        if cache_key in self._measure_cache:
            return self._measure_cache[cache_key]
        node = self.tree.nodes[component_id]
        component_type = str(node.get("type") or "Group")
        children = self.tree.children.get(component_id, [])
        layout = style_group(node, "layout")
        padding = self.effective_padding(node)
        explicit_width, explicit_height = self._explicit_size(node)
        fill_width = uses_parent_width(node)
        if component_type in {"TopAppBar", "CenterAlignedTopAppBar"}:
            fill_width = True
        width = explicit_width if explicit_width is not None else (available_width if fill_width else None)
        for rule in normalized_layout_rules(node):
            if rule.get("kind") == "sizing" and "width" in rule.get("axes", []) and rule.get("mode") == "fill_parent":
                width = available_width * rule["fraction"]
        inner_width = max(
            0.0,
            (width if width is not None else available_width) - padding["left"] - padding["right"],
        )

        child_sizes = [(child_id, self._measure(child_id, inner_width)) for child_id in children]
        if component_type == "ConstraintLayout":
            content_width, content_height = self._measure_constraint(
                component_id, child_sizes, inner_width
            )
        elif component_type in VERTICAL_TYPES:
            spacing = arrangement_spacing(node, "vertical")
            content_width = max((size[0] for _, size in child_sizes), default=0.0)
            content_height = sum(size[1] for _, size in child_sizes)
            content_height += spacing * max(0, len(child_sizes) - 1)
        elif component_type in HORIZONTAL_TYPES:
            spacing = arrangement_spacing(node, "horizontal")
            if width is None and any(
                has_modifier(self.tree.nodes[child_id], "weight") for child_id in children
            ):
                width = available_width
            content_width = sum(size[0] for _, size in child_sizes)
            content_width += spacing * max(0, len(child_sizes) - 1)
            content_height = max((size[1] for _, size in child_sizes), default=0.0)
        elif children:
            content_width = max((size[0] for _, size in child_sizes), default=0.0)
            content_height = max((size[1] for _, size in child_sizes), default=0.0)
            if component_type not in OVERLAY_TYPES and len(children) > 1:
                self.geometry_reasons[component_id].append(
                    "custom multi-child component measured as overlay"
                )
        else:
            content_width, content_height = self._measure_leaf(node, inner_width)

        if component_type == "CenterAlignedTopAppBar" and explicit_height is None:
            content_height = max(content_height, 64.0)
            self.geometry_reasons[component_id].append("Material3 small top app bar content height 64dp, excluding modifier padding")
        if component_type == "IconButton":
            if width is None:
                width = 48.0
            if explicit_height is None:
                content_height = max(content_height, 48.0)
            self.geometry_reasons[component_id].append("Material IconButton default 48dp touch target")
        elif component_type in {"Button", "TextButton"}:
            if width is None:
                width = content_width + 24.0
            if explicit_height is None:
                content_height = max(content_height, 48.0)
            self.geometry_reasons[component_id].append("Material button minimum touch target")
        if width is None:
            width = content_width + padding["left"] + padding["right"]
        if explicit_height is not None:
            height = explicit_height
        else:
            height = content_height + padding["top"] + padding["bottom"]
        ratio = finite_number(layout.get("aspect_ratio"))
        if ratio is not None and ratio > 0:
            if explicit_height is None:
                height = width / ratio
            elif explicit_width is None:
                width = height * ratio
        for rule in normalized_layout_rules(node):
            if rule.get("kind") == "constraints":
                limits = rule["limits"]
                width = max(limits.get("minWidth", 0), min(width, limits.get("maxWidth", float("inf"))))
                height = max(limits.get("minHeight", 0), min(height, limits.get("maxHeight", float("inf"))))
        width = max(0.0, min(width, max(0.0, available_width)))
        height = max(0.0, height)
        self._measure_cache[cache_key] = (width, height)
        self.measured_sizes[component_id] = {"width": width, "height": height}
        return width, height

    def _constraint_vertical_positions(
        self,
        container_id: str,
        child_sizes: dict[str, tuple[float, float]],
        parent_height: float | None,
    ) -> dict[str, float]:
        relationships = {
            relationship.get("subject_id"): relationship
            for relationship in self.relationships_by_container.get(container_id, [])
        }
        positions: dict[str, float] = {}
        pending = list(child_sizes)
        while pending:
            progress = False
            for child_id in list(pending):
                relationship = relationships.get(child_id)
                constraints = (relationship or {}).get("active_constraints") or []
                unsupported = [
                    constraint
                    for constraint in constraints
                    if not (
                        constraint.get("kind") == "link_to"
                        and constraint.get("subject_anchor") in {"top", "start", "end"}
                        and constraint.get("target_anchor") in {"top", "bottom", "start", "end"}
                    )
                    and not (
                        constraint.get("kind") == "center_around"
                        and constraint.get("subject_anchor") == "center"
                        and constraint.get("target_anchor") in {"top", "center", "bottom"}
                    )
                ]
                if unsupported:
                    for constraint in unsupported:
                        failure = {
                            "phase": "layout",
                            "component_id": child_id,
                            "relationship_id": str((relationship or {}).get("id") or ""),
                            "reason": (
                                "unsupported constraint "
                                f"{constraint.get('kind')}:{constraint.get('subject_anchor')}"
                                f"->{constraint.get('target_anchor')}"
                            ),
                        }
                        if failure not in self.phase_failures:
                            self.phase_failures.append(failure)
                    positions[child_id] = 0.0
                    pending.remove(child_id)
                    progress = True
                    continue
                top = next(
                    (
                        constraint
                        for constraint in constraints
                        if constraint.get("kind") == "link_to"
                        and constraint.get("subject_anchor") == "top"
                    ),
                    None,
                )
                center = next(
                    (
                        constraint
                        for constraint in constraints
                        if constraint.get("kind") == "center_around"
                        and constraint.get("subject_anchor") == "center"
                    ),
                    None,
                )
                dependency = center or top
                if (
                    isinstance(dependency, dict)
                    and dependency.get("target_reference") != "parent"
                    and str(dependency.get("target_id")) not in positions
                ):
                    continue
                if isinstance(center, dict):
                    if center.get("target_reference") == "parent":
                        if parent_height is None:
                            positions[child_id] = 0.0
                            self.geometry_reasons[container_id].append(
                                "parent-centered child extent requires the layout phase"
                            )
                        else:
                            target_position = 0.0
                            target_height = parent_height
                            target_anchor = center.get("target_anchor")
                            if target_anchor == "bottom":
                                target_position = target_height
                            elif target_anchor == "center":
                                target_position = target_height / 2
                            positions[child_id] = (
                                target_position
                                - child_sizes[child_id][1] / 2
                                + (finite_number(center.get("margin_dp")) or 0.0)
                            )
                    else:
                        target_id = str(center.get("target_id"))
                        target_position = positions[target_id]
                        target_height = child_sizes.get(target_id, (0.0, 0.0))[1]
                        target_anchor = center.get("target_anchor")
                        if target_anchor == "bottom":
                            target_position += target_height
                        elif target_anchor == "center":
                            target_position += target_height / 2
                        positions[child_id] = (
                            target_position
                            - child_sizes[child_id][1] / 2
                            + (finite_number(center.get("margin_dp")) or 0.0)
                        )
                elif isinstance(top, dict) and top.get("target_reference") != "parent":
                    target_id = str(top.get("target_id"))
                    target_position = positions[target_id]
                    if top.get("target_anchor") == "bottom":
                        target_position += child_sizes.get(target_id, (0.0, 0.0))[1]
                    positions[child_id] = target_position + (
                        finite_number(top.get("margin_dp")) or 0.0
                    )
                else:
                    positions[child_id] = (
                        finite_number(top.get("margin_dp")) or 0.0
                        if isinstance(top, dict)
                        else 0.0
                    )
                if isinstance(relationship, dict) and isinstance(relationship.get("id"), str):
                    self.consumed_relationship_ids.add(relationship["id"])
                pending.remove(child_id)
                progress = True
            if not progress:
                for child_id in pending:
                    positions[child_id] = 0.0
                    relationship = relationships.get(child_id) or {}
                    failure = {
                        "phase": "layout",
                        "component_id": child_id,
                        "relationship_id": str(relationship.get("id") or ""),
                        "reason": "constraint dependency could not be resolved",
                    }
                    if failure not in self.phase_failures:
                        self.phase_failures.append(failure)
                self.geometry_reasons[container_id].append(
                    "constraint extent contains unresolved dependency"
                )
                break
        return positions

    def _measure_constraint(
        self,
        container_id: str,
        child_sizes: list[tuple[str, tuple[float, float]]],
        available_width: float,
    ) -> tuple[float, float]:
        sizes = dict(child_sizes)
        relationships = {
            relationship.get("subject_id"): relationship
            for relationship in self.relationships_by_container.get(container_id, [])
        }
        positions = self._constraint_vertical_positions(container_id, sizes, None)
        content_height = max(
            (positions[child_id] + sizes[child_id][1] for child_id in sizes),
            default=0.0,
        )
        content_width = max((size[0] for size in sizes.values()), default=0.0)
        if any(
            {constraint.get("subject_anchor") for constraint in relationship.get("active_constraints") or []}
            >= {"start", "end"}
            for relationship in relationships.values()
        ):
            content_width = available_width
        return content_width, content_height

    def _measure_leaf(self, node: dict[str, Any], available_width: float) -> tuple[float, float]:
        component_type = str(node.get("type") or "")
        if component_type in TEXT_TYPES:
            typography = style_group(node, "typography")
            content = style_group(node, "content")
            font_size = finite_number(typography.get("font_size_sp")) or 14.0
            line_height = finite_number(typography.get("line_height_sp")) or font_size * 1.25
            text = content.get("text")
            text_length = len(text) if isinstance(text, str) and text else 1
            estimated_width = min(available_width, max(font_size * 0.55 * text_length, font_size))
            self.geometry_reasons[node["id"]].append("text width estimated from source typography")
            return estimated_width, line_height
        if component_type in IMAGE_TYPES:
            intrinsic = self._intrinsic_image_size(node, available_width)
            if intrinsic is not None:
                self.geometry_reasons[node["id"]].append("image intrinsic size constrained by available layout space")
                return intrinsic
            self.geometry_reasons[node["id"]].append("image has no resolved source dimensions")
            return 24.0, 24.0
        if component_type in {"HorizontalDivider", "Divider"}:
            return available_width, 1.0
        self.geometry_reasons[node["id"]].append("leaf has no source-resolved dimensions")
        return 0.0, 0.0

    def _layout(
        self,
        component_id: str,
        x: float,
        y: float,
        available_width: float,
        available_height: float | None,
        *,
        force_size: tuple[float, float] | None = None,
    ) -> tuple[float, float]:
        node = self.tree.nodes[component_id]
        component_type = str(node.get("type") or "Group")
        width, height = force_size or self._measure(component_id, available_width)
        offset_x, offset_y = offset_values(node, available_width, available_height)
        x += offset_x
        y += offset_y
        self.frames[component_id] = {"x": x, "y": y, "width": width, "height": height}
        explicit_width, explicit_height = self._explicit_size(node)
        reasons = self.geometry_reasons.get(component_id, [])
        if component_id == self.tree.root_id or (explicit_width is not None and explicit_height is not None):
            status = "source_resolved"
        elif any("no source-resolved" in reason for reason in reasons):
            status = "unresolved"
        else:
            status = "source_inferred"
        self.geometry_status[component_id] = status

        children = self.tree.children.get(component_id, [])
        if not children:
            return width, height
        padding = self.effective_padding(node)
        content_x = x + padding["left"]
        content_y = y + padding["top"]
        content_width = max(0.0, width - padding["left"] - padding["right"])
        content_height = max(0.0, height - padding["top"] - padding["bottom"])
        if component_type in VERTICAL_TYPES:
            self._layout_vertical(node, children, content_x, content_y, content_width, content_height)
        elif component_type in HORIZONTAL_TYPES:
            self._layout_horizontal(node, children, content_x, content_y, content_width, content_height)
        elif component_type == "TopAppBar":
            self._layout_top_app_bar(children, content_x, content_y, content_width, content_height)
        elif component_type in {"IconButton", "Button", "TextButton"}:
            self._layout_center(children, content_x, content_y, content_width, content_height)
        elif component_type == "ConstraintLayout":
            self._layout_constraint(component_id, children, content_x, content_y, content_width, content_height)
        else:
            self._layout_overlay(
                children,
                content_x,
                content_y,
                content_width,
                content_height,
                container_node=node,
            )
        return width, height

    def _layout_vertical(
        self,
        node: dict[str, Any],
        children: list[str],
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        spacing = arrangement_spacing(node, "vertical")
        cursor = y
        weighted = [child for child in children if has_modifier(self.tree.nodes[child], "weight")]
        measured = {child: self._measure(child, width) for child in children}
        occupied = sum(size[1] for child, size in measured.items() if child not in weighted)
        occupied += spacing * max(0, len(children) - 1)
        weights = {child: next(rule for rule in normalized_layout_rules(self.tree.nodes[child]) if rule["kind"] == "weight") for child in weighted}
        total_weight = sum(rule["value"] for rule in weights.values())
        weight_height = max(0.0, height - occupied) / total_weight if total_weight else None
        container_alignment = (
            semantic_expression(node, "horizontalAlignment")
            or resolved_alignment(node)
        )
        for child in children:
            child_node = self.tree.nodes[child]
            child_width, child_height = measured[child]
            if has_modifier(child_node, "fillMaxWidth") or has_modifier(child_node, "fillMaxSize"):
                rule = next((rule for rule in normalized_layout_rules(child_node) if rule["kind"] == "sizing" and "width" in rule.get("axes", [])), {})
                child_width = width * rule.get("fraction", 1)
            if child in weighted and weight_height is not None:
                allocated = weight_height * weights[child]["value"]
                child_height = allocated if weights[child]["fill"] else min(child_height, allocated)
            alignment = self._alignment(child_node) or container_alignment
            child_x = self._aligned_x(
                child_node, x, width, child_width, alignment
            )
            self._layout(
                child,
                child_x,
                cursor,
                width,
                child_height,
                force_size=(child_width, child_height),
            )
            cursor += child_height + spacing

    def _layout_horizontal(
        self,
        node: dict[str, Any],
        children: list[str],
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        spacing = arrangement_spacing(node, "horizontal")
        measured = {child: self._measure(child, width) for child in children}
        weighted = [child for child in children if has_modifier(self.tree.nodes[child], "weight")]
        occupied = sum(size[0] for child, size in measured.items() if child not in weighted)
        occupied += spacing * max(0, len(children) - 1)
        weights = {child: next(rule for rule in normalized_layout_rules(self.tree.nodes[child]) if rule["kind"] == "weight") for child in weighted}
        total_weight = sum(rule["value"] for rule in weights.values())
        weight_width = max(0.0, width - occupied) / total_weight if total_weight else None
        arrangement = semantic_expression(node, "horizontalArrangement").lower()
        if not weighted and len(children) > 1 and "spacebetween" in arrangement:
            spacing = max(0.0, width - sum(size[0] for size in measured.values())) / (len(children) - 1)
        cursor = x
        vertical_alignment = (
            semantic_expression(node, "verticalAlignment")
            or resolved_alignment(node)
        ).lower()
        for child in children:
            child_node = self.tree.nodes[child]
            child_width, child_height = measured[child]
            if child in weighted and weight_width is not None:
                allocated = weight_width * weights[child]["value"]
                child_width = allocated if weights[child]["fill"] else min(child_width, allocated)
            if has_modifier(child_node, "fillMaxHeight") or has_modifier(child_node, "fillMaxSize"):
                rule = next((rule for rule in normalized_layout_rules(child_node) if rule["kind"] == "sizing" and "height" in rule.get("axes", [])), {})
                child_height = height * rule.get("fraction", 1)
            if "center" in vertical_alignment:
                child_y = y + max(0.0, (height - child_height) / 2)
            elif "bottom" in vertical_alignment:
                child_y = y + max(0.0, height - child_height)
            else:
                child_y = self._aligned_y(child_node, y, height, child_height)
            self._layout(
                child,
                cursor,
                child_y,
                child_width,
                height,
                force_size=(child_width, child_height),
            )
            cursor += child_width + spacing

    def _layout_top_app_bar(
        self,
        children: list[str],
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        if not children:
            return
        action_ids = [
            child_id
            for child_id in children
            if self.tree.nodes[child_id].get("type") in {"IconButton", "Button", "TextButton"}
        ]
        title_ids = [child_id for child_id in children if child_id not in action_ids]
        cursor = x + width - 4.0
        for child_id in reversed(action_ids):
            child_width, child_height = self._measure(child_id, width)
            cursor -= child_width
            child_y = y + max(0.0, (height - child_height) / 2)
            self._layout(
                child_id,
                cursor,
                child_y,
                child_width,
                height,
                force_size=(child_width, child_height),
            )
        for child_id in title_ids:
            child_width, child_height = self._measure(child_id, max(0.0, cursor - x - 16.0))
            child_y = y + max(0.0, (height - child_height) / 2)
            self._layout(
                child_id,
                x + 16.0,
                child_y,
                max(0.0, cursor - x - 16.0),
                height,
                force_size=(child_width, child_height),
            )

    def _layout_center(
        self,
        children: list[str],
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        for child_id in children:
            child_width, child_height = self._measure(child_id, width)
            self._layout(
                child_id,
                x + max(0.0, (width - child_width) / 2),
                y + max(0.0, (height - child_height) / 2),
                width,
                height,
                force_size=(child_width, child_height),
            )

    def _layout_overlay(
        self,
        children: list[str],
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        container_node: dict[str, Any] | None = None,
    ) -> None:
        explicit_width, explicit_height = (
            self._explicit_size(container_node) if container_node else (None, None)
        )
        forwards_modifier_width = bool(
            container_node
            and len(children) == 1
            and str(container_node.get("component_kind") or "").startswith("project")
            and (uses_parent_width(container_node) or explicit_width is not None)
        )
        container_alignment = resolved_alignment(container_node) if container_node else ""
        for child in children:
            child_node = self.tree.nodes[child]
            child_width, child_height = self._measure(child, width)
            if self._explicit_size(child_node) == (None, None):
                intrinsic = self._intrinsic_image_size(child_node, width, height)
                if intrinsic is not None:
                    child_width, child_height = intrinsic
            if (
                forwards_modifier_width
                or self._forwarded_modifier_fills_axis(container_node, child_node, "width")
                or has_modifier(child_node, "fillMaxWidth")
                or has_modifier(child_node, "fillMaxSize")
            ):
                rule = next((rule for rule in normalized_layout_rules(child_node) if rule["kind"] == "sizing" and "width" in rule.get("axes", [])), {})
                child_width = width * rule.get("fraction", 1)
            if (
                self._forwarded_modifier_fills_axis(container_node, child_node, "height")
                or has_modifier(child_node, "fillMaxHeight")
                or has_modifier(child_node, "fillMaxSize")
            ):
                rule = next((rule for rule in normalized_layout_rules(child_node) if rule["kind"] == "sizing" and "height" in rule.get("axes", [])), {})
                child_height = height * rule.get("fraction", 1)
            elif (
                container_node
                and len(children) == 1
                and str(container_node.get("component_kind") or "").startswith("project")
                and explicit_height is not None
            ):
                child_height = height
            alignment = self._alignment(child_node) or container_alignment
            child_x = self._aligned_x(child_node, x, width, child_width, alignment)
            child_y = self._aligned_y(child_node, y, height, child_height, alignment)
            self._layout(
                child,
                child_x,
                child_y,
                width,
                height,
                force_size=(child_width, child_height),
            )

    def _forwarded_modifier_fills_axis(
        self,
        container_node: dict[str, Any] | None,
        child_node: dict[str, Any],
        axis: str,
    ) -> bool:
        if (
            not isinstance(container_node, dict)
            or len(self.tree.children.get(container_node["id"], [])) != 1
            or not str(container_node.get("component_kind") or "").startswith("project")
        ):
            return False
        bindings = child_node.get("parameter_bindings")
        expression = bindings.get("modifier") if isinstance(bindings, dict) else None
        if not isinstance(expression, str):
            return False
        compact = re.sub(r"\s+", "", expression)
        if ".fillMaxSize(" in compact:
            return True
        if axis == "width" and ".fillMaxWidth(" in compact:
            return True
        if axis == "height" and ".fillMaxHeight(" in compact:
            return True
        if ".weight(" not in compact:
            return False
        ancestor_id = container_node.get("parent_id")
        while isinstance(ancestor_id, str):
            ancestor = self.tree.nodes[ancestor_id]
            ancestor_type = str(ancestor.get("type") or "")
            if ancestor_type in HORIZONTAL_TYPES:
                return axis == "width"
            if ancestor_type in VERTICAL_TYPES:
                return axis == "height"
            ancestor_id = ancestor.get("parent_id")
        return False

    def _layout_constraint(
        self,
        container_id: str,
        children: list[str],
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        relationships = {
            relationship.get("subject_id"): relationship
            for relationship in self.relationships_by_container.get(container_id, [])
        }
        measured = {child: self._measure(child, width) for child in children}
        anchors_by_child = {
            child: {
                constraint.get("subject_anchor"): constraint
                for constraint in (relationships.get(child) or {}).get("active_constraints") or []
                if constraint.get("kind") == "link_to"
            }
            for child in children
        }
        for child, anchors in anchors_by_child.items():
            start = anchors.get("start")
            end = anchors.get("end")
            child_width, child_height = measured[child]
            if (
                isinstance(start, dict)
                and isinstance(end, dict)
            ):
                start_margin = finite_number(start.get("margin_dp")) or 0.0
                end_margin = finite_number(end.get("margin_dp")) or 0.0
                measured[child] = (
                    max(0.0, width - start_margin - end_margin),
                    child_height,
                )
        positions = self._constraint_vertical_positions(container_id, measured, height)
        for child in children:
            child_width, child_height = measured[child]
            anchors = anchors_by_child[child]
            start = anchors.get("start")
            end = anchors.get("end")
            child_x = x
            if isinstance(start, dict) and start.get("target_reference") == "parent":
                child_x += finite_number(start.get("margin_dp")) or 0.0
            elif isinstance(start, dict) and isinstance(end, dict):
                child_x += finite_number(start.get("margin_dp")) or 0.0
            elif isinstance(end, dict) and end.get("target_reference") == "parent":
                child_x += width - child_width - (finite_number(end.get("margin_dp")) or 0.0)
            self._layout(
                child,
                child_x,
                y + positions[child],
                width,
                height,
                force_size=(child_width, child_height),
            )

    def _alignment(self, node: dict[str, Any]) -> str:
        modifier = modifier_argument(node, "align")
        return modifier or ""

    def _aligned_x(
        self,
        node: dict[str, Any],
        x: float,
        width: float,
        child_width: float,
        alignment: str | None = None,
    ) -> float:
        alignment = (alignment if alignment is not None else self._alignment(node)).lower()
        if "end" in alignment or "right" in alignment:
            return x + max(0.0, width - child_width)
        if "center" in alignment:
            return x + max(0.0, (width - child_width) / 2)
        return x

    def _aligned_y(
        self,
        node: dict[str, Any],
        y: float,
        height: float,
        child_height: float,
        alignment: str | None = None,
    ) -> float:
        alignment = (alignment if alignment is not None else self._alignment(node)).lower()
        if "top" in alignment:
            return y
        if "bottom" in alignment:
            return y + max(0.0, height - child_height)
        if "center" in alignment:
            return y + max(0.0, (height - child_height) / 2)
        return y


def rgba_fill(color: str, opacity: float = 1.0) -> dict[str, Any]:
    normalized = color.lstrip("#")
    if len(normalized) == 8:
        alpha = int(normalized[0:2], 16) / 255
        red = int(normalized[2:4], 16) / 255
        green = int(normalized[4:6], 16) / 255
        blue = int(normalized[6:8], 16) / 255
    elif len(normalized) == 6:
        alpha = 1.0
        red = int(normalized[0:2], 16) / 255
        green = int(normalized[2:4], 16) / 255
        blue = int(normalized[4:6], 16) / 255
    else:
        raise ValueError(f"unsupported color: {color}")
    alpha *= opacity
    return {
        "type": "color",
        "color": {
            "a": alpha,
            "r": red,
            "g": green,
            "b": blue,
            "value": f"rgba({round(red * 255)},{round(green * 255)},{round(blue * 255)},{alpha:g})",
            "type": "percentage",
            "boundVariables": {},
        },
        "opacity": alpha,
        "isEnabled": True,
        "blendMode": 0,
        "boundVariables": {},
    }


def lanhu_frame(frame_dp: dict[str, float], scale: float) -> dict[str, int | float]:
    return {
        "left": clean_number(frame_dp["x"] * scale),
        "top": clean_number(frame_dp["y"] * scale),
        "width": clean_number(frame_dp["width"] * scale),
        "height": clean_number(frame_dp["height"] * scale),
    }


def radius_value(value: Any, scale: float) -> dict[str, int | float]:
    if isinstance(value, dict):
        return {
            "topLeft": clean_number((finite_number(value.get("top_left")) or 0.0) * scale),
            "topRight": clean_number((finite_number(value.get("top_right")) or 0.0) * scale),
            "bottomRight": clean_number((finite_number(value.get("bottom_right")) or 0.0) * scale),
            "bottomLeft": clean_number((finite_number(value.get("bottom_left")) or 0.0) * scale),
        }
    number = finite_number(value) or 0.0
    scaled = clean_number(number * scale)
    return {"topLeft": scaled, "topRight": scaled, "bottomRight": scaled, "bottomLeft": scaled}


def layer_type(component_type: str, surface: dict[str, Any]) -> str:
    if component_type in TEXT_TYPES:
        return "text"
    if component_type in IMAGE_TYPES:
        return "image"
    if surface.get("background") or surface.get("border"):
        return "shapeLayer"
    return "group"


def required_phase_paths(node: dict[str, Any], phase: str) -> list[str]:
    paths = [
        str(item.get("path"))
        for item in node.get("required_facts") or []
        if isinstance(item, dict)
        and item.get("status") in {"resolved", "default_resolved"}
        and isinstance(item.get("path"), str)
    ]
    if phase == "measure":
        return sorted(path for path in paths if path.startswith("style.layout."))
    if phase == "layout":
        return sorted(path for path in paths if path.startswith("structure."))
    return sorted(
        path
        for path in paths
        if path.startswith("style.") and not path.startswith("style.layout.")
    )


def draw_output_paths(node: dict[str, Any], layer: dict[str, Any]) -> list[str]:
    emitted: set[str] = {"structure.type", "style.state.visible"}
    style = layer["style"]
    if style.get("fills"):
        emitted.add("style.surface.background")
    if style.get("borders"):
        emitted.add("style.surface.border")
    if layer.get("clipped"):
        emitted.add("style.surface.clip")
    if layer.get("opacity") is not None:
        emitted.add("style.surface.alpha")
    for source_name, lanhu_name in (
        ("font_size_sp", "fontSize"),
        ("font_weight", "fontWeight"),
        ("color", "color"),
    ):
        if lanhu_name in style:
            emitted.add(f"style.typography.{source_name}")
    if "text" in layer:
        emitted.add("style.content.text")
    if "exportImageUrl" in layer:
        emitted.add("style.asset.resource")
    if finite_number(style_group(node, "transform").get("rotation_degrees")) is not None:
        emitted.add("style.transform.rotation_degrees")
    return sorted(emitted)


def component_phase_trace(
    tree: SourceTree,
    layout: SourceLayout,
    component_id: str,
    layer: dict[str, Any],
) -> dict[str, Any]:
    node = tree.nodes[component_id]
    relationship_ids = sorted(
        relationship["id"]
        for relationships in layout.relationships_by_container.values()
        for relationship in relationships
        if relationship.get("subject_id") == component_id
        and isinstance(relationship.get("id"), str)
    )
    consumed_relationship_ids = sorted(
        set(relationship_ids) & layout.consumed_relationship_ids
    )
    emitted = draw_output_paths(node, layer)
    layout.drawn_component_ids.add(component_id)
    layout.draw_output_paths[component_id] = emitted
    return {
        "schema": "android-to-harmony.render-phase-trace.v1",
        "phaseOrder": ["measure", "layout", "draw"],
        "measure": {
            "status": "consumed" if component_id in layout.measured_sizes else "missing",
            "inputPaths": required_phase_paths(node, "measure"),
            "outputSizeDp": {
                key: clean_number(value)
                for key, value in layout.measured_sizes.get(component_id, {}).items()
            },
        },
        "layout": {
            "status": "consumed" if component_id in layout.frames else "missing",
            "inputPaths": required_phase_paths(node, "layout"),
            "relationshipIds": relationship_ids,
            "consumedRelationshipIds": consumed_relationship_ids,
            "outputFrameDp": {
                key: clean_number(value)
                for key, value in layout.frames.get(component_id, {}).items()
            },
        },
        "draw": {
            "status": "consumed",
            "inputPaths": required_phase_paths(node, "draw"),
            "emittedPaths": emitted,
        },
    }


def build_phase_consumption_gate(layout: SourceLayout) -> dict[str, Any]:
    failures = list(layout.phase_failures)
    component_count = len(layout.tree.nodes)
    if not layout.measure_complete or len(layout.measured_sizes) != component_count:
        failures.append({
            "phase": "measure",
            "component_id": layout.tree.root_id,
            "relationship_id": "",
            "reason": "not every source component produced a measured size",
        })
    if not layout.layout_complete or len(layout.frames) != component_count:
        failures.append({
            "phase": "layout",
            "component_id": layout.tree.root_id,
            "relationship_id": "",
            "reason": "not every measured component produced a layout frame",
        })
    if len(layout.drawn_component_ids) != component_count:
        failures.append({
            "phase": "draw",
            "component_id": layout.tree.root_id,
            "relationship_id": "",
            "reason": "not every laid-out component produced a draw node",
        })
    expected_relationship_ids = {
        relationship["id"]
        for relationships in layout.relationships_by_container.values()
        for relationship in relationships
        if relationship.get("active_constraints")
        and isinstance(relationship.get("id"), str)
    }
    missing_relationship_ids = sorted(
        expected_relationship_ids - layout.consumed_relationship_ids
    )
    for relationship_id in missing_relationship_ids:
        failures.append({
            "phase": "layout",
            "component_id": layout.tree.root_id,
            "relationship_id": relationship_id,
            "reason": "active layout relationship was parsed but not consumed",
        })
    return {
        "schema": "android-to-harmony.render-phase-gate.v1",
        "verdict": "pass" if not failures else "fail",
        "phase_order": ["measure", "layout", "draw"],
        "component_count": component_count,
        "measured_component_count": len(layout.measured_sizes),
        "laid_out_component_count": len(layout.frames),
        "drawn_component_count": len(layout.drawn_component_ids),
        "consumed_relationship_ids": sorted(layout.consumed_relationship_ids),
        "failure_count": len(failures),
        "failures": failures,
    }


def lanhu_layer(
    tree: SourceTree,
    layout: SourceLayout,
    component_id: str,
    scale: float,
) -> dict[str, Any]:
    node = tree.nodes[component_id]
    component_type = str(node.get("type") or "Group")
    surface = style_group(node, "surface")
    typography = style_group(node, "typography")
    content = style_group(node, "content")
    asset = style_group(node, "asset")
    frame = lanhu_frame(layout.frames[component_id], scale)
    opacity = finite_number(surface.get("alpha"))
    if opacity is None:
        opacity = 1.0
    background = surface.get("background")
    fills: list[dict[str, Any]] = []
    if isinstance(background, dict) and isinstance(background.get("color"), str):
        try:
            fills.append(rgba_fill(background["color"], opacity))
        except ValueError:
            pass
    borders: list[dict[str, Any]] = []
    border = surface.get("border")
    if isinstance(border, dict):
        width = finite_number(border.get("width_dp"))
        color = border.get("color")
        if width is not None and width >= 0 and isinstance(color, str):
            try:
                scaled_width = clean_number(width * scale)
                borders.append(
                    {
                        "blendMode": 0,
                        "isEnabled": True,
                        "opacity": 1,
                        "lineAlignment": "inside",
                        "style": str(border.get("style") or "solid"),
                        "width": scaled_width,
                        "lineCap": "none",
                        "lineJoin": "miter",
                        "miterLimit": 4,
                        "widths": {
                            "left": scaled_width,
                            "right": scaled_width,
                            "top": scaled_width,
                            "bottom": scaled_width,
                        },
                        "color": rgba_fill(color, 1)["color"],
                    }
                )
            except ValueError:
                pass
    source_radius = surface.get("corner_radius_dp")
    if source_radius is None and surface.get("clip") is True:
        if any(
            arguments.strip() == "CircleShape"
            for arguments in nested_modifier_arguments(node, "clip")
        ):
            component_frame = layout.frames[component_id]
            source_radius = uniform_corner_radius(
                min(component_frame["width"], component_frame["height"]) / 2
            )
    radius = radius_value(source_radius, scale)
    style: dict[str, Any] = {
        "isEnabled": True,
        "opacity": opacity,
        "blendMode": 0,
        "fills": fills,
        "borders": borders,
        "shadows": surface.get("shadows") or [],
        "blurs": [],
    }
    font_size = finite_number(typography.get("font_size_sp"))
    if font_size is not None:
        style["fontSize"] = clean_number(font_size * scale)
    if typography.get("font_weight") is not None:
        style["fontWeight"] = typography["font_weight"]
    if isinstance(typography.get("color"), str):
        style["color"] = typography["color"]
    text = content.get("text")
    has_asset = isinstance(asset.get("resource"), str) and bool(asset["resource"])
    migration_source = copy.deepcopy(node.get("source") or {})
    migration_source["modifiers"] = copy.deepcopy(node.get("modifiers") or [])
    if node.get('slot_argument_name'):
        migration_source['slot_argument_name'] = node['slot_argument_name']
    migration_source["layoutRules"] = copy.deepcopy(
        node.get("layout_rules") or normalized_layout_rules(node)
    )
    migration_style = copy.deepcopy(node.get("style") or {})
    source_alignment = resolved_alignment(node)
    if source_alignment:
        migration_style.setdefault("layout", {})["alignment"] = source_alignment
    resolved_padding = layout.effective_padding(node)
    migration_layout = migration_style.setdefault("layout", {})
    if migration_layout.get("padding_dp") is None and any(
        abs(value) > 0.001 for value in resolved_padding.values()
    ):
        migration_layout["padding_dp"] = {
            edge: clean_number(value) for edge, value in resolved_padding.items()
        }
    result: dict[str, Any] = {
        "id": component_id,
        "name": str(node.get("semantic_key") or component_type),
        "type": layer_type(component_type, surface),
        "visible": style_group(node, "state").get("visible") is not False,
        "clipped": bool(surface.get("clip")),
        "isMask": False,
        "opacity": opacity,
        "rotation": finite_number(style_group(node, "transform").get("rotation_degrees")) or 0,
        "frame": frame,
        "realFrame": dict(frame),
        "combinedFrame": dict(frame),
        "radius": radius,
        "paths": [],
        "style": style,
        "hasExportImage": has_asset,
        "hasExportDDSImage": False,
        "layers": [
            lanhu_layer(tree, layout, child_id, scale)
            for child_id in tree.children.get(component_id, [])
        ],
        "origin": "android-source",
        "migration": {
            "schema": "android-to-harmony.lanhu-node.v1",
            "componentType": component_type,
            "semanticKey": node.get("semantic_key"),
            "source": migration_source,
            "style": migration_style,
            "customDraw": copy.deepcopy(node.get("custom_draw")),
            "provenance": copy.deepcopy(node.get("provenance") or []),
            "unresolved": copy.deepcopy(node.get("unresolved") or []),
            "requiredFacts": copy.deepcopy(node.get("required_facts") or []),
            "geometryStatus": layout.geometry_status[component_id],
            "geometryEvidence": copy.deepcopy(
                layout.geometry_reasons.get(component_id, [])
            ),
        },
    }
    if isinstance(text, str) or result["type"] == "text":
        result["text"] = text
    if has_asset:
        result["exportImageUrl"] = asset["resource"]
    if result["type"] == "shapeLayer":
        result["paths"] = [{"type": "rect", "frame": dict(frame), "radius": radius}]
    result["migration"]["phaseTrace"] = component_phase_trace(
        tree, layout, component_id, result
    )
    return result


def source_assets(tree: SourceTree) -> list[str]:
    return sorted(
        {
            resource
            for node in tree.nodes.values()
            if isinstance((resource := style_group(node, "asset").get("resource")), str)
            and resource
        }
    )


def component_manifest(tree: SourceTree, layout: SourceLayout) -> dict[str, Any]:
    definitions_by_id = {
        definition.get("id"): definition
        for definition in tree.payload.get("component_definitions") or []
        if isinstance(definition, dict) and isinstance(definition.get("id"), str)
    }
    instances_by_definition: dict[str, list[str]] = defaultdict(list)
    for component_id in tree.order:
        definition_id = tree.nodes[component_id].get("definition_id")
        if isinstance(definition_id, str):
            instances_by_definition[definition_id].append(component_id)
    definitions = []
    for definition_id, definition in definitions_by_id.items():
        item = dict(definition)
        item["instance_ids"] = instances_by_definition.get(definition_id, [])
        definitions.append(item)
    for definition_id in sorted(set(instances_by_definition) - set(definitions_by_id)):
        definitions.append(
            {
                "id": definition_id,
                "type": None,
                "identity": None,
                "component_kind": "unresolved",
                "declared_from": None,
                "dependency": None,
                "instance_ids": instances_by_definition[definition_id],
            }
        )
    instances = []
    for component_id in tree.order:
        node = tree.nodes[component_id]
        instances.append(
            {
                "id": component_id,
                "type": node.get("type"),
                "semantic_key": node.get("semantic_key"),
                "definition_id": node.get("definition_id"),
                "parent_id": node.get("parent_id"),
                "children_ids": tree.children.get(component_id, []),
                "sibling_index": node.get("sibling_index"),
                "frame_dp": {
                    key: clean_number(value) for key, value in layout.frames[component_id].items()
                },
                "resolved_layout": {
                    "padding_dp": {
                        key: clean_number(value)
                        for key, value in layout.effective_padding(node).items()
                    }
                },
                "layout_rules": copy.deepcopy(
                    node.get("layout_rules") or normalized_layout_rules(node)
                ),
                "geometry_status": layout.geometry_status[component_id],
                "geometry_evidence": layout.geometry_reasons.get(component_id, []),
                "style": node.get("style") or {},
                "custom_draw": node.get("custom_draw"),
                "source": node.get("source") or {},
                "provenance": node.get("provenance") or [],
                "unresolved": node.get("unresolved") or [],
                "required_facts": node.get("required_facts") or [],
            }
        )
    return {
        "schema": MANIFEST_SCHEMA,
        "page": tree.payload.get("page") or {},
        "source_schema": tree.payload.get("schema"),
        "source_status": tree.payload.get("status"),
        "root_instance_id": tree.root_id,
        "source_instance_count": len(tree.nodes),
        "definitions": definitions,
        "instances": instances,
        "layout_relationships": tree.payload.get("layout_relationships") or [],
        "limitations": tree.payload.get("limitations") or [],
        "state_projection": tree.payload.get("state_projection"),
        "geometry_summary": {
            status: sum(1 for value in layout.geometry_status.values() if value == status)
            for status in ("source_resolved", "source_inferred", "unresolved")
        },
    }


def state_manifest(tree: SourceTree) -> dict[str, Any]:
    page = tree.payload.get("page") or {}
    overlay_ids = [
        component_id
        for component_id in tree.order
        if any(marker in str(tree.nodes[component_id].get("type") or "") for marker in OVERLAY_NAME_MARKERS)
    ]
    return {
        "schema": STATE_SCHEMA,
        "page_id": page.get("id"),
        "source_root": tree.payload.get("root") or {},
        "states": [
            {
                "id": page.get("state"),
                "version_json": "version_json.json",
                "base_state_id": None,
                "overlay_layer_ids": overlay_ids,
                "classification": "overlay" if overlay_ids else "full_page",
            }
        ],
    }


def page_font_faces(source: dict[str, Any]) -> list[dict[str, Any]]:
    used = {style_group(c, "typography").get("font_family") for c in source.get("components", [])}
    result = []
    weights = {"Normal": 400, "Medium": 500, "SemiBold": 600, "Bold": 700, "Light": 300, "Thin": 100, "ExtraLight": 200, "ExtraBold": 800, "Black": 900}
    for token in source.get("source_tokens", []):
        if token.get("kind") not in {"font", "font_family"} or token.get("name") not in used:
            continue
        for resource, weight_name in re.findall(r"R\.font\.(\w+)\s*,\s*FontWeight\.(\w+)", token.get("expression", "")):
            if weight_name in weights:
                result.append({"family": token["name"], "resource": resource, "weight": weights[weight_name]})
    return result


def non_rendering_argument_calls(source: dict[str, Any]) -> list[str]:
    nodes = {node["id"]: node for node in source.get("components", [])}
    result = []
    for node in nodes.values():
        parent = nodes.get(node.get("parent_id"))
        if node.get("children_ids") or not parent or parent.get("type") not in {"Image", "Icon", "AsyncImage"}:
            continue
        for name in ("painter", "imageVector", "model", "placeholder", "error", "fallback"):
            expression = semantic_expression(parent, name)
            if re.match(rf"^{re.escape(node['type'])}\s*\(", expression.strip()):
                result.append(node["id"])
                break
    return result


def expand_surface_padding(payload: dict[str, Any]) -> None:
    """Keep modifier padding outside a native surface, not in its content padding."""
    from analyze_compose_project import ordered_modifier_chain
    from real_page_pipeline import bind_source_expression, direct_padding, static_style_for_call

    additions = []
    by_id = {node['id']: node for node in payload['components']}
    native_surfaces = {'Button', 'TextButton', 'OutlinedButton', 'Card', 'Surface'}
    layout_modifiers = {'padding', 'fillMaxWidth', 'fillMaxHeight', 'fillMaxSize',
                        'wrapContentWidth', 'wrapContentHeight', 'wrapContentSize',
                        'width', 'height', 'size', 'widthIn', 'heightIn', 'sizeIn', 'weight', 'align'}
    for node in list(payload['components']):
        if node.get('component_kind') == 'project' or (node.get('source') or {}).get('custom_component'):
            continue
        bindings = {**(node.get('parameter_bindings') or {}), **(node.get('local_values') or {})}

        def flatten(modifiers):
            result = []
            for modifier in modifiers:
                expression = bind_source_expression(str(modifier.get('arguments') or ''), bindings)
                if modifier.get('name') == 'then' and re.match(r'^Modifier\b', expression):
                    result.extend(flatten(ordered_modifier_chain(expression)))
                else:
                    result.extend(ordered_modifier_chain(f"Modifier.{modifier['name']}({expression})"))
            return result

        chain = flatten(node.get('modifiers') or [])
        boundary = next((i for i, m in enumerate(chain) if m['name'] not in layout_modifiers), len(chain))
        prefix, rest = chain[:boundary], chain[boundary:]
        if not any(m['name'] == 'padding' for m in prefix):
            continue
        if node['type'] not in native_surfaces and not any(
            m['name'] in {'background', 'border', 'dashedBorder', 'shadow'} for m in rest
        ):
            continue
        # More layout changes after drawing need their own ordered lowering.
        if any(m['name'] in layout_modifiers - {'padding'} for m in rest):
            continue

        def modifier_style(modifiers):
            call = {'component': 'Box', 'source': node.get('source', {}).get('source', ''),
                    'line': node.get('source', {}).get('line', 0),
                    'ordered_modifier_chain': modifiers}
            return static_style_for_call(call, {}, None, bindings)[0]['layout']

        layers = []
        for modifier in prefix:
            layout = modifier_style([modifier])
            if modifier['name'] == 'padding' and layout.get('padding_dp') is None:
                break
            rules = normalized_layout_rules({'modifiers': [modifier]})
            if modifier['name'] != 'padding' and not rules and not any(
                layout.get(axis + '_dp') is not None for axis in ('width', 'height')
            ):
                break
            layers.append((layout, modifier))
        if len(layers) != len(prefix):
            continue

        body = copy.deepcopy(node)
        body.update(id=node['id'] + '--surface', semantic_key=node['semantic_key'] + '--surface',
                    sibling_index=0, modifiers=rest)
        body['layout_rules'] = normalized_layout_rules(body)
        body_layout = body['style']['layout']
        for axis in ('width', 'height'):
            if any(layout.get(axis + '_dp') is not None for layout, _ in layers):
                body_layout[axis + '_dp'] = None
        if node['type'] in native_surfaces:
            expression = bind_source_expression(semantic_expression(node, 'contentPadding'), bindings)
            dimensions = [(float(value), unit) for value, unit in re.findall(r'(-?\d+(?:\.\d+)?)\.(dp|sp)\b', expression)]
            body_layout['padding_dp'] = direct_padding(expression, dimensions) if expression else None
        else:
            body_layout['padding_dp'] = modifier_style(rest).get('padding_dp')

        wrappers = []
        fill_axes = set()
        for i, (layout, modifier) in enumerate(layers):
            wrapper_id = node['id'] if i == 0 else node['id'] + f'--outer-{i}'
            wrapper = {'id': wrapper_id, 'semantic_key': node['semantic_key'] if i == 0 else wrapper_id,
                       'type': 'Box', 'component_kind': 'platform', 'arguments': {},
                       'parent_id': node['parent_id'] if i == 0 else wrappers[-1]['id'],
                       'sibling_index': node.get('sibling_index', 0) if i == 0 else 0,
                       'children_ids': [], 'style': empty_style(),
                       'source': {**node.get('source', {}), 'attributes': [], 'surface_padding_layer': i},
                       'modifiers': [{'name': 'fillMax' + axis.title(), 'arguments': ''} for axis in sorted(fill_axes)] + [modifier]}
            wrapper['style']['layout'].update(layout, alignment='TopStart')
            if wrappers:
                wrappers[-1]['children_ids'] = [wrapper_id]
            wrappers.append(wrapper)
            for rule in normalized_layout_rules(wrapper):
                if rule['kind'] == 'sizing' and rule['mode'] == 'fill_parent':
                    fill_axes.update(rule['axes'])
            fill_axes.update(axis for axis in ('width', 'height') if layout.get(axis + '_dp') is not None)
        body['modifiers'] = [{'name': 'fillMax' + axis.title(), 'arguments': ''} for axis in sorted(fill_axes)] + rest
        body['layout_rules'] = normalized_layout_rules(body)
        body['parent_id'] = wrappers[-1]['id']
        wrappers[-1]['children_ids'] = [body['id']]
        for child_id in body['children_ids']:
            by_id[child_id]['parent_id'] = body['id']
        node.clear()
        node.update(wrappers[0])
        additions.extend([*wrappers[1:], body])
    payload['components'].extend(additions)


def expand_ordered_layout_modifiers(payload: dict[str, Any]) -> None:
    """Retain constant layout modifier nesting; never reconstruct it from frames."""
    additions = []
    original_nodes = list(payload['components'])
    by_id = {node['id']: node for node in original_nodes}
    for node in original_nodes:
        if not any(f['path'] == 'source.modifiers.order' for f in build_required_facts(node)):
            continue
        chain = node.get('modifiers') or []
        if node.get('component_kind') == 'project' or node.get('layout_rules') or semantic_expression(node, 'contentPadding'):
            continue
        layers = []
        sized_axes = set()
        for modifier in chain:
            name, expression = modifier.get('name'), str(modifier.get('arguments') or '')
            positional, named = parsed_arguments(expression)
            fields = {}
            if name == 'padding':
                if len(positional) == 1 and not named:
                    amount = number_expression(positional[0], 'dp')
                    values = dict.fromkeys(('left', 'top', 'right', 'bottom'), amount)
                elif not positional and named and not set(named) - {'horizontal', 'vertical', 'start', 'end', 'top', 'bottom'}:
                    values = {side: number_expression(named.get(key, named.get(axis, '0.dp')), 'dp')
                              for side, key, axis in [('left', 'start', 'horizontal'), ('right', 'end', 'horizontal'),
                                                      ('top', 'top', 'vertical'), ('bottom', 'bottom', 'vertical')]}
                    if values['left'] != values['right'] and style_group(node, 'layout').get('layout_direction') not in {'ltr', 'rtl'}:
                        break
                    if style_group(node, 'layout').get('layout_direction') == 'rtl':
                        values['left'], values['right'] = values['right'], values['left']
                else:
                    break
                if any(v is None or v < 0 for v in values.values()):
                    break
                fields['padding_dp'] = values
            elif name in {'size', 'width', 'height'}:
                axes = ['width', 'height'] if name == 'size' else [name]
                if sized_axes.intersection(axes):
                    break
                if len(positional) == 1 and not named:
                    fields = {axis + '_dp': number_expression(positional[0], 'dp') for axis in axes}
                elif not positional and set(named) == set(axes):
                    fields = {axis + '_dp': number_expression(named[axis], 'dp') for axis in axes}
                else:
                    break
                if any(value is None or value <= 0 for value in fields.values()):
                    break
                sized_axes.update(axes)
            else:
                break
            layers.append(fields)
        if len(layers) != len(chain):
            continue
        body = copy.deepcopy(node)
        body['id'] = node['id'] + '--content'
        body['semantic_key'] = str(node.get('semantic_key') or node['id']) + '--content'
        body['modifiers'] = []
        body.pop('required_facts', None)
        for key in ('width_dp', 'height_dp', 'padding_dp'):
            body['style']['layout'][key] = None
        for child in body.get('children_ids') or []:
            by_id[child]['parent_id'] = body['id']
        inherited_axes = set()
        wrapper_nodes = []
        for index, fields in enumerate(layers):
            wrapper_id = node['id'] if index == 0 else node['id'] + f'--modifier-{index}'
            wrapper = {'id': wrapper_id, 'type': 'Box', 'semantic_key': wrapper_id,
                       'parent_id': node['parent_id'] if index == 0 else wrapper_nodes[-1]['id'],
                       'sibling_index': node.get('sibling_index', 0) if index == 0 else 0,
                       'children_ids': [], 'arguments': {}, 'component_kind': 'platform',
                       'source': {**node.get('source', {}), 'modifier_layer': index},
                       'style': empty_style(), 'modifiers': []}
            wrapper['style']['layout'].update(fields, alignment='TopStart')
            wrapper['style']['layout']['layout_direction'] = style_group(node, 'layout').get('layout_direction')
            wrapper['modifiers'] = [{'name': 'fillMax' + axis.title(), 'arguments': ''}
                                    for axis in sorted(inherited_axes) if axis + '_dp' not in fields]
            if wrapper_nodes:
                wrapper_nodes[-1]['children_ids'] = [wrapper_id]
            wrapper_nodes.append(wrapper)
            inherited_axes.update(axis for axis in ('width', 'height') if axis + '_dp' in fields)
        body['parent_id'] = wrapper_nodes[-1]['id']
        body['sibling_index'] = 0
        body['modifiers'] = [{'name': 'fillMax' + axis.title(), 'arguments': ''} for axis in sorted(inherited_axes)]
        wrapper_nodes[-1]['children_ids'] = [body['id']]
        node.clear()
        node.update(wrapper_nodes[0])
        additions.extend([*wrapper_nodes[1:], body])
    payload['components'].extend(additions)


def resolve_scaffold_padding(payload: dict[str, Any]) -> None:
    """Retain the bar-height relationship; only literal extra padding is evaluated."""
    nodes = {node['id']: node for node in payload.get('components', [])}
    for node in nodes.values():
        ancestor = nodes.get(node.get('parent_id'))
        while ancestor and ancestor.get('type') != 'Scaffold':
            ancestor = nodes.get(ancestor.get('parent_id'))
        if not ancestor:
            continue
        parameters = ancestor.get('source', {}).get('trailing_lambda_parameters', [])
        if len(parameters) != 1:
            continue
        for expression in nested_modifier_arguments(node, 'padding'):
            positional, named = parsed_arguments(expression)
            if positional or not named:
                continue
            edges, offsets = {}, {}
            for name, value in named.items():
                edge = {'start': 'left', 'end': 'right'}.get(name, name)
                if edge not in {'left', 'right', 'top', 'bottom'}:
                    break
                match = re.fullmatch(re.escape(parameters[0]) + r'\.calculate(Top|Bottom)Padding\(\)(?:\s*\+\s*(\d+(?:\.\d+)?)\.dp)?', value.strip())
                if match:
                    edges[edge] = 'topBar' if match.group(1) == 'Top' else 'bottomBar'
                    offsets[edge] = float(match.group(2) or 0)
                else:
                    offset = number_expression(value, 'dp')
                    if offset is None:
                        break
                    offsets[edge] = offset
            else:
                if not edges:
                    continue
                padding = dict.fromkeys(('left', 'right', 'top', 'bottom'), 0.0)
                padding.update(offsets)
                node['style']['layout']['padding_dp'] = padding
                node['source']['scaffold_padding'] = {'owner_id': ancestor['id'], 'edges': edges}
                node['unresolved'] = [u for u in node.get('unresolved', []) if u.get('path') != 'style.layout.padding_dp']


def resolve_native_content_colors(payload: dict[str, Any]) -> None:
    # Compose Button provides LocalContentColor through intervening layout/function nodes.
    nodes = {node['id']: node for node in payload.get('components', [])}
    providers = {'Button', 'TextButton', 'OutlinedButton', 'Card'}
    for node in nodes.values():
        if node.get('type') not in {'Text', 'BasicText', 'ClickableText'}:
            continue
        typography = style_group(node, 'typography')
        if typography.get('color') is not None:
            continue
        pending = [item for item in node.get('unresolved', []) if item.get('path') == 'style.typography.color']
        if any(item.get('expression') not in {'LocalContentColor.current', 'Color.Unspecified'} for item in pending):
            continue
        parent = nodes.get(node.get('parent_id'))
        while parent is not None:
            if parent.get('type') in providers:
                color = style_group(parent, 'typography').get('color')
                if isinstance(color, str):
                    typography['color'] = color
                    node['unresolved'] = [item for item in node.get('unresolved', []) if item not in pending]
                    node.setdefault('provenance', []).append({
                        'paths': ['style.typography.color'], 'origin': 'source_resolved',
                        'source': parent['id'] + ':LocalContentColor'})
                break
            parent = nodes.get(parent.get('parent_id'))


def generate(args: argparse.Namespace) -> dict[str, Any]:
    if args.viewport_width_dp <= 0 or args.viewport_height_dp <= 0:
        raise ValueError("viewport dimensions must be positive")
    if args.slice_scale <= 0:
        raise ValueError("slice scale must be positive")
    source_payload = read_json(args.source_page)
    state_projection = None
    if args.state_fixture is not None:
        source_payload, state_projection = project_source_page(
            source_payload, read_json(args.state_fixture)
        )
    elif any(
        isinstance(node, dict) and (node.get("visibility_condition") or node.get("list_item_context"))
        for node in source_payload.get("components") or []
    ):
        source_payload, state_projection = project_source_page(source_payload, {
            "schema": "android-to-harmony.page-state-fixture.v1",
            "page": source_payload.get("page"),
            "values": {},
        })
    resolve_native_content_colors(source_payload)
    for node in source_payload.get('components', []):
        if 'input_decoration' not in (node.get('source') or {}):
            resolve_input_decoration(node, {})
    property_calls = non_rendering_argument_calls(source_payload)
    resolve_scaffold_padding(source_payload)
    source_payload["components"] = [node for node in source_payload.get("components", []) if node["id"] not in property_calls]
    for node in source_payload["components"]:
        node["children_ids"] = [child for child in node.get("children_ids", []) if child not in property_calls]
    expand_surface_padding(source_payload)
    expand_ordered_layout_modifiers(source_payload)
    for component in source_payload.get("components") or []:
        if isinstance(component, dict):
            content = style_group(component, "content")
            text = content.get("text")
            if not isinstance(text, str) and (
                text is not None or component.get("type") in TEXT_TYPES | {"ClickableText", "BasicTextField", "TextField", "OutlinedTextField"}
            ):
                content["text"] = None
                expression = (semantic_expression(component, "text")
                              or semantic_expression(component, "value")
                              or f"{component.get('type')}.text")
                for item in component.get("unresolved") or []:
                    if item.get("path") == "style.content.text" and not item.get("expression"):
                        item["expression"] = expression
                if not any(item.get("path") == "style.content.text" for item in component.get("unresolved") or []):
                    component.setdefault("unresolved", []).append({
                        "path": "style.content.text", "expression": expression,
                        "reason": "text did not resolve to a string; no placeholder or object stringification",
                    })
            component["required_facts"] = build_required_facts(component)
    tree = SourceTree(source_payload)
    layout = SourceLayout(tree, args.viewport_width_dp, args.viewport_height_dp)
    layout.calculate()
    # Parameter-forwarded padding is resolved during measurement; retain that
    # same value in the final facts rather than leaving the original symbol.
    for component in tree.nodes.values():
        if nested_modifier_arguments(component, "padding"):
            resolved_padding = layout.effective_padding(component)
            if any(resolved_padding.values()) or style_group(component, "layout").get("padding_dp") is not None:
                style_group(component, "layout")["padding_dp"] = resolved_padding
                component["required_facts"] = build_required_facts(component)
    artboard_frame = {
        "left": 0,
        "top": 0,
        "width": clean_number(args.viewport_width_dp * args.slice_scale),
        "height": clean_number(args.viewport_height_dp * args.slice_scale),
    }
    page = tree.payload.get("page") or {}
    fact_gate = required_fact_gate(list(tree.nodes.values()))
    root_layer = lanhu_layer(tree, layout, tree.root_id, args.slice_scale)
    phase_gate = build_phase_consumption_gate(layout)
    manifest = component_manifest(tree, layout)
    unresolved = []
    for component in tree.nodes.values():
        for item in component.get("unresolved") or []:
            unresolved.append({"component_id": component["id"], **item})
        for item in component.get("required_facts") or []:
            if item["status"] in {"symbolic", "unresolved"} and not any(
                existing["component_id"] == component["id"]
                and existing.get("path") == item.get("path")
                and existing.get("expression") == item.get("expression")
                for existing in unresolved
            ):
                unresolved.append({"component_id": component["id"], **item})
    unresolved.extend({"kind": "source_phase_unconsumed", **item}
                      for item in phase_gate["failures"])
    generation_complete = not unresolved
    version_json = {
        "meta": {
            "device": args.device,
            "sliceScale": clean_number(args.slice_scale),
            "host": {"name": "android-source", "version": "1"},
            "plugin": {"name": "android-to-harmony", "version": "1"},
            "migration": {
                "schema": "android-to-harmony.lanhu-document.v1",
                "fontFaces": page_font_faces(source_payload),
                "page": {
                    "id": page.get("id"),
                    "state": page.get("state"),
                },
            },
            "sourceGeneration": {
                "generationComplete": generation_complete,
                "verdict": "pass" if generation_complete else "fail",
                "unresolved": unresolved,
                "sourceInstanceCount": len(tree.nodes),
                "geometrySummary": manifest["geometry_summary"],
                "layoutRelationships": tree.payload.get("layout_relationships") or [],
                "requiredFactGate": fact_gate,
                "phaseConsumptionGate": phase_gate,
                "stateProjection": state_projection,
            },
        },
        "assets": source_assets(tree),
        "artboard": {
            "id": f"{page.get('id') or 'page'}--{page.get('state') or 'default'}",
            "name": str(page.get("id") or "page"),
            "type": "artboard",
            "visible": True,
            "clipped": True,
            "opacity": 1,
            "frame": artboard_frame,
            "realFrame": dict(artboard_frame),
            "combinedFrame": dict(artboard_frame),
            "style": {
                "isEnabled": True,
                "opacity": 1,
                "blendMode": 0,
                "fills": [],
                "borders": [],
                "shadows": [],
                "blurs": [],
            },
            "layers": [root_layer],
            "origin": "android-source",
        },
    }
    output_dir = args.output_dir.resolve()
    write_json(output_dir / "version_json.json", version_json)
    write_json(output_dir / "component-manifest.json", manifest)
    write_json(output_dir / "page-state-manifest.json", state_manifest(tree))
    return {
        "status": "generated_requires_screenshot_validation" if generation_complete else "partial_generation",
        "generation_complete": generation_complete,
        "verdict": "pass" if generation_complete else "fail",
        "unresolved_count": len(unresolved),
        "unresolved": unresolved,
        "source_page": str(args.source_page.resolve()),
        "output_dir": str(output_dir),
        "source_instances": len(tree.nodes),
        "required_fact_gate": fact_gate,
        "phase_consumption_gate": phase_gate,
        "definitions": len(tree.payload.get("component_definitions") or []),
        "geometry": manifest["geometry_summary"],
        "state_projection": state_projection,
        "non_rendering_argument_call_ids": property_calls,
    }


def main() -> int:
    try:
        result = generate(parse_args())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
