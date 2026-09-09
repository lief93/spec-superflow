from __future__ import annotations
import math
import re
from typing import Any


SOURCE_SCHEMA = "android-to-harmony.source-page-spec.v1"


MANIFEST_SCHEMA = "android-to-harmony.lanhu-component-manifest.v1"


STATE_SCHEMA = "android-to-harmony.page-state-manifest.v1"


VERTICAL_TYPES = {"Column", "LazyColumn", "Card"}


HORIZONTAL_TYPES = {"Row", "LazyRow", "BottomAppBar"}


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
