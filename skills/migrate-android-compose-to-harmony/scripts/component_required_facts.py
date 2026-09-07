#!/usr/bin/env python3
from __future__ import annotations

import re
from typing import Any


FACT_STATUSES = {
    "resolved",
    "default_resolved",
    "symbolic",
    "unresolved",
    "not_applicable",
}
FACT_PATH_PATTERN = re.compile(
    r"^(?:structure|style|source)(?:\.[a-z_][a-z0-9_]*)+$"
)
TEXT_TYPES = {"Text", "BasicText", "ClickableText"}
IMAGE_TYPES = {"Image", "Icon", "AsyncImage"}
BUTTON_TYPES = {
    "Button",
    "TextButton",
    "OutlinedButton",
    "IconButton",
    "FloatingActionButton",
    "SmallFloatingActionButton",
}
FONT_WEIGHTS = {
    "Thin": 100,
    "ExtraLight": 200,
    "Light": 300,
    "Normal": 400,
    "Regular": 400,
    "Medium": 500,
    "SemiBold": 600,
    "Bold": 700,
    "ExtraBold": 800,
    "Black": 900,
}
OVERFLOW_VALUES = {
    "TextOverflow.Clip": "clip",
    "TextOverflow.Ellipsis": "ellipsis",
    "TextOverflow.Visible": "visible",
}
DECORATION_VALUES = {
    "TextDecoration.None": "none",
    "TextDecoration.Underline": "underline",
    "TextDecoration.LineThrough": "line_through",
}
TEXT_ALIGN_VALUES = {
    "TextAlign.Start": "start",
    "TextAlign.Center": "center",
    "TextAlign.End": "end",
    "TextAlign.Justify": "justify",
}
CONTENT_SCALE_VALUES = {
    "ContentScale.Fit": "fit",
    "ContentScale.Crop": "crop",
    "ContentScale.FillBounds": "fill",
    "ContentScale.Inside": "inside",
    "ContentScale.None": "none",
}
INPUT_TYPES = {'BasicTextField', 'TextField', 'OutlinedTextField'}
INPUT_ARGUMENTS = {'singleLine', 'readOnly', 'visualTransformation', 'keyboardOptions'}


def input_argument_values(name: str, expression: str) -> dict[str, Any] | None:
    if name in {'singleLine', 'readOnly'}:
        value = {'true': True, 'false': False}.get(expression.strip())
        return None if value is None else {('single_line' if name == 'singleLine' else 'read_only'): value}
    if name == 'visualTransformation':
        value = {'PasswordVisualTransformation()': True, 'VisualTransformation.None': False}.get(expression.strip())
        return None if value is None else {'password': value}
    match = re.fullmatch(r'KeyboardOptions\((.*)\)', expression.strip(), re.S)
    if name != 'keyboardOptions' or not match:
        return None
    positional, named = parsed_arguments(match[1])
    if positional or set(named) - {'keyboardType', 'imeAction'}:
        return None
    keyboard = {'Text': 'text', 'Number': 'number', 'Phone': 'phone', 'Email': 'email',
                'Uri': 'url', 'Decimal': 'decimal', 'Password': 'password', 'NumberPassword': 'number_password'}
    action = {'Default': 'default', 'None': 'none', 'Go': 'go', 'Search': 'search',
              'Send': 'send', 'Next': 'next', 'Done': 'done', 'Previous': 'previous'}
    values = {'keyboard_type': {'KeyboardType.' + key: value for key, value in keyboard.items()}.get(named.get('keyboardType', 'KeyboardType.Text')),
              'ime_action': {'ImeAction.' + key: value for key, value in action.items()}.get(named.get('imeAction', 'ImeAction.Default'))}
    return None if None in values.values() else values


def constant_color(expression: str) -> str | None:
    value = {'Color.Black': '#FF000000', 'Color.White': '#FFFFFFFF', 'Color.Transparent': '#00000000',
             'Color.Red': '#FFFF0000', 'Color.Green': '#FF00FF00', 'Color.Blue': '#FF0000FF'}.get(expression.strip())
    match = re.fullmatch(r'Color\(0x([0-9A-Fa-f]{8})\)', expression.strip())
    return '#' + match[1].upper() if match else value


def constant_linear_gradient(expression: str) -> dict[str, Any] | None:
    match = re.fullmatch(r'Brush\.(horizontalGradient|verticalGradient)\((.*)\)', expression.strip(), re.S)
    if not match:
        return None
    positional, named = parsed_arguments(match[2])
    if set(named) - {'colors', 'tileMode'} or named.get('tileMode', 'TileMode.Clamp') != 'TileMode.Clamp':
        return None
    colors_expression = named.get('colors') or (positional[0] if len(positional) == 1 else '')
    colors_match = re.fullmatch(r'listOf\((.*)\)', colors_expression, re.S)
    if not colors_match or (positional and 'colors' in named):
        return None
    colors = [constant_color(value) for value in split_top_level_arguments(colors_match[1])]
    if len(colors) < 2 or None in colors:
        return None
    return {'type': 'linear_gradient', 'colors': colors,
            'angle_degrees': 90 if match[1] == 'horizontalGradient' else 180, 'tile_mode': 'clamp'}


def constant_corner_radius(expression: str, direction: str | None = None) -> dict[str, float] | None:
    match = re.fullmatch(r'(AbsoluteRoundedCornerShape|RoundedCornerShape)\((.*)\)', expression.strip(), re.S)
    if not match:
        return None
    positional, named = parsed_arguments(match[2])
    keys = ['top_left', 'top_right', 'bottom_right', 'bottom_left']
    if len(positional) == 1 and not named:
        value = number_expression(positional[0], 'dp')
        return dict.fromkeys(keys, value) if value is not None and value >= 0 else None
    names = ['topLeft', 'topRight', 'bottomRight', 'bottomLeft'] if match[1].startswith('Absolute') else ['topStart', 'topEnd', 'bottomEnd', 'bottomStart']
    if positional or not named or set(named) - set(names):
        return None
    values = [number_expression(named.get(name, '0.dp'), 'dp') for name in names]
    if any(value is None or value < 0 for value in values):
        return None
    if not match[1].startswith('Absolute'):
        if len(set(values)) > 1 and direction not in {'ltr', 'rtl'}:
            return None
        if direction == 'rtl':
            values = [values[1], values[0], values[3], values[2]]
    return dict(zip(keys, values))


def is_preview_only_placeholder_expression(expression: str | None) -> bool:
    if not isinstance(expression, str):
        return False
    return re.fullmatch(
        r"\s*debugPlaceholder\s*\((?:[^()]|R\.(?:drawable|mipmap)\.[A-Za-z0-9_]+)*\)\s*",
        expression,
    ) is not None


def split_top_level_arguments(expression: str) -> list[str]:
    result: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escaped = False
    for index, character in enumerate(expression):
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            quote = character
        elif character in "([{":
            depth += 1
        elif character in ")]}":
            depth -= 1
        elif character == "," and depth == 0:
            result.append(expression[start:index].strip())
            start = index + 1
    tail = expression[start:].strip()
    if tail:
        result.append(tail)
    return result


def parsed_arguments(expression: str) -> tuple[list[str], dict[str, str]]:
    positional: list[str] = []
    named: dict[str, str] = {}
    for item in split_top_level_arguments(expression):
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$", item, re.S)
        if match is None:
            positional.append(item)
        else:
            named[match.group(1)] = match.group(2).strip()
    return positional, named


def numeric_literal(expression: str | None) -> float | None:
    match = re.fullmatch(
        r"\s*(-?[0-9]+(?:\.[0-9]+)?)\s*[fF]?\s*",
        expression or "",
    )
    return float(match.group(1)) if match is not None else None


def normalized_offset_value(expression: str | None) -> dict[str, Any] | None:
    if not isinstance(expression, str):
        return None
    candidate = re.sub(r"\s+", "", expression)
    dp = re.fullmatch(r"(-?[0-9]+(?:\.[0-9]+)?)\.dp", candidate)
    if dp is not None:
        return {"kind": "dp", "value": float(dp.group(1))}
    relative = re.fullmatch(
        r"(-)?max(Width|Height)(?:([/*])([0-9]+(?:\.[0-9]+)?)[fF]?)?",
        candidate,
    )
    if relative is None:
        return None
    operand = float(relative.group(4) or 1)
    if relative.group(3) == '/' and operand == 0:
        return None
    fraction = 1.0 / operand if relative.group(3) == '/' else operand
    if relative.group(1):
        fraction = -fraction
    return {
        "kind": "parent_fraction",
        "axis": relative.group(2).lower(),
        "fraction": fraction,
    }


def nested_modifier_calls(expression: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for match in re.finditer(r"(?:\bModifier|\.)\.?(\w+)\s*\(", expression):
        name = match.group(1)
        open_index = expression.find("(", match.start(), match.end())
        depth = 0
        quote: str | None = None
        escaped = False
        for index in range(open_index, len(expression)):
            character = expression[index]
            if quote is not None:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    quote = None
                continue
            if character in {'"', "'"}:
                quote = character
            elif character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0:
                    result.append((name, expression[open_index + 1:index].strip()))
                    break
    return result


def size_arguments(expression: str) -> tuple[float | None, float | None]:
    positional, named = parsed_arguments(expression)
    common = named.get("size") or (positional[0] if len(positional) == 1 else None)
    width = named.get("width") or (positional[0] if len(positional) > 1 else common)
    height = named.get("height") or (positional[1] if len(positional) > 1 else common)
    return (number_expression(width or "", "dp"), number_expression(height or "", "dp"))


def normalized_layout_rules(component: dict[str, Any]) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    modifiers = component.get("modifiers") or []
    for index, modifier in enumerate(modifiers):
        if not isinstance(modifier, dict) or not isinstance(modifier.get("name"), str):
            continue
        entries = [(modifier["name"], str(modifier.get("arguments") or ""))]
        if modifier["name"] == "then":
            entries = nested_modifier_calls(entries[0][1])
        for name, expression in entries:
            rule_start = len(rules)
            positional, named = parsed_arguments(expression)
            if name in {"fillMaxWidth", "fillMaxHeight", "fillMaxSize"}:
                fraction_expression = named.get("fraction") or (positional[0] if positional else "1")
                fraction = numeric_literal(fraction_expression)
                if fraction is None or not 0 <= fraction <= 1:
                    continue
                rules.append({
                    "kind": "sizing",
                    "axes": (
                        ["width", "height"] if name == "fillMaxSize"
                        else ["width"] if name == "fillMaxWidth" else ["height"]
                    ),
                    "mode": "fill_parent",
                    "fraction": fraction,
                    "source_modifier_index": index,
                })
            elif name == "matchParentSize":
                rules.append({
                    "kind": "sizing",
                    "axes": ["width", "height"],
                    "mode": "match_parent",
                    "fraction": 1.0,
                    "source_modifier_index": index,
                })
            elif name in {"wrapContentWidth", "wrapContentHeight", "wrapContentSize"}:
                rules.append({
                    "kind": "sizing",
                    "axes": (
                        ["width", "height"] if name == "wrapContentSize"
                        else ["width"] if name == "wrapContentWidth" else ["height"]
                    ),
                    "mode": "wrap_content",
                    "source_modifier_index": index,
                })
            elif name in {"width", "height"}:
                intrinsic_expression = named.get("intrinsicSize") or (
                    positional[0] if positional else None
                )
                if intrinsic_expression not in {
                    "IntrinsicSize.Max", "IntrinsicSize.Min"
                }:
                    continue
                rules.append({
                    "kind": "intrinsic_size",
                    "axis": name,
                    "mode": intrinsic_expression.rsplit(".", 1)[-1].lower(),
                    "source_modifier_index": index,
                })
            elif name in {"widthIn", "heightIn", "sizeIn"}:
                axes = ["width", "height"] if name == "sizeIn" else [name[:-2]]
                limits: dict[str, float] = {}
                valid = True
                keys = ["minWidth", "minHeight", "maxWidth", "maxHeight"] if name == "sizeIn" else ["min", "max"]
                for argument_index, key in enumerate(keys):
                    value = named.get(key) or (positional[argument_index] if len(positional) > argument_index else None)
                    if value is None or value == "Dp.Unspecified":
                        continue
                    parsed = number_expression(value, "dp")
                    if parsed is None or parsed < 0:
                        valid = False
                        break
                    if name == "sizeIn":
                        limits[key] = parsed
                    else:
                        limits[key + axes[0].title()] = parsed
                if valid and limits:
                    rules.append({"kind": "constraints", "limits": limits, "source_modifier_index": index})
            elif name in {"verticalScroll", "horizontalScroll"}:
                enabled = named.get("enabled", "true")
                reverse = named.get("reverseScrolling", "false")
                if enabled in {"true", "false"} and reverse == "false":
                    rules.append({"kind": "scroll", "axis": "vertical" if name == "verticalScroll" else "horizontal",
                                  "enabled": enabled == "true", "source_modifier_index": index})
            elif name == "weight":
                value = numeric_literal(named.get("weight") or (positional[0] if positional else None))
                fill_expression = named.get("fill") or (positional[1] if len(positional) > 1 else "true")
                if value is not None and value > 0 and fill_expression.strip() in {"true", "false"}:
                    rules.append({
                        "kind": "weight",
                        "value": value,
                        "fill": fill_expression.strip() == "true",
                        "source_modifier_index": index,
                    })
            elif name == "offset":
                x = normalized_offset_value(named.get("x") or (positional[0] if positional else None))
                y = normalized_offset_value(named.get("y") or (positional[1] if len(positional) > 1 else None))
                if x is not None or y is not None:
                    rule: dict[str, Any] = {
                        "kind": "offset",
                        "source_modifier_index": index,
                    }
                    if x is not None:
                        rule["x"] = x
                    if y is not None:
                        rule["y"] = y
                    rules.append(rule)
            elif name == "constrainAs":
                reference = named.get("ref") or (positional[0] if positional else None)
                if isinstance(reference, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", reference.strip()):
                    rules.append({
                        "kind": "constraint_reference",
                        "reference": reference.strip(),
                        "source_modifier_index": index,
                    })
            elif name == "align":
                value = positional[0].strip() if len(positional) == 1 else ""
                if re.fullmatch(r"Alignment\.[A-Za-z]+", value):
                    rules.append({
                        "kind": "alignment",
                        "value": value,
                        "source_modifier_index": index,
                    })
            elif name == "zIndex":
                value = numeric_literal(positional[0] if len(positional) == 1 else None)
                if value is not None:
                    rules.append({
                        "kind": "z_index",
                        "value": value,
                        "source_modifier_index": index,
                    })
            for rule in rules[rule_start:]:
                if modifier["name"] == "then":
                    rule["source_modifier_name"] = name
    return rules


def nested_value(component: dict[str, Any], path: str) -> Any:
    current: Any = component
    for segment in path.split("."):
        if not isinstance(current, dict) or segment not in current:
            return None
        current = current[segment]
    return current


def semantic_expression(component: dict[str, Any], name: str) -> str | None:
    arguments = component.get("arguments")
    semantic = arguments.get("semantic") if isinstance(arguments, dict) else None
    value = semantic.get(name) if isinstance(semantic, dict) else None
    expression = value.get("expression") if isinstance(value, dict) else None
    return expression.strip() if isinstance(expression, str) and expression.strip() else None


def number_expression(expression: str, unit: str) -> float | None:
    match = re.fullmatch(rf"\s*(-?[0-9]+(?:\.[0-9]+)?)\s*\.\s*{unit}\s*", expression)
    return float(match.group(1)) if match is not None else None


def integer_expression(expression: str) -> int | None:
    match = re.fullmatch(r"\s*([1-9][0-9]*)\s*", expression)
    return int(match.group(1)) if match is not None else None


def font_weight_expression(expression: str) -> int | None:
    match = re.fullmatch(
        r"\s*FontWeight(?:\(\s*([1-9][0-9]{2})\s*\)|\.([A-Za-z]+))\s*",
        expression,
    )
    if match is None:
        return None
    return int(match.group(1)) if match.group(1) is not None else FONT_WEIGHTS.get(match.group(2))


def style_font_weight(expression: str) -> int | None:
    match = re.search(
        r"\bfontWeight\s*=\s*(FontWeight(?:\(\s*[1-9][0-9]{2}\s*\)|\.[A-Za-z]+))",
        expression,
    )
    return font_weight_expression(match.group(1)) if match is not None else None


def style_number(expression: str, name: str, unit: str) -> float | None:
    match = re.search(
        rf"\b{re.escape(name)}\s*=\s*(-?[0-9]+(?:\.[0-9]+)?)\s*\.\s*{unit}\b",
        expression,
    )
    return float(match.group(1)) if match is not None else None


def style_hex_color(expression: str) -> str | None:
    match = re.search(r"(?:Color\s*\(\s*)?(0x[0-9A-Fa-f]{8}|#[0-9A-Fa-f]{6,8})", expression)
    return match.group(1).replace("0x", "#").upper() if match is not None else None


def simple_appbar_background(expression: str) -> dict[str, str] | None:
    match = re.fullmatch(r'TopAppBarDefaults\.topAppBarColors\((.*)\)', expression.strip(), re.S)
    if match is None:
        return None
    positional, named = parsed_arguments(match.group(1))
    if positional or set(named) != {'containerColor'}:
        return None
    value = named['containerColor'].strip()
    color = {'Color.Transparent': '#00000000', 'Color.Black': '#FF000000',
             'Color.White': '#FFFFFFFF'}.get(value)
    if re.fullmatch(r'Color\(0x[0-9A-Fa-f]{8}\)', value):
        color = style_hex_color(value)
    return {'type': 'solid', 'color': color} if color is not None else None


def fact(
    path: str,
    status: str,
    origin: str,
    source_name: str,
    expression: str | None,
    reason: str,
) -> dict[str, str | None]:
    return {
        "path": path,
        "status": status,
        "origin": origin,
        "source_name": source_name,
        "expression": expression,
        "reason": reason,
    }


def explicit_fact(
    component: dict[str, Any],
    path: str,
    origin: str,
    source_name: str,
    expression: str,
    expected: Any = None,
    *,
    expected_known: bool = False,
    explicit_null: bool = False,
) -> dict[str, str | None]:
    actual = nested_value(component, path)
    if explicit_null:
        return fact(path, "resolved", origin, source_name, expression, "explicit null is preserved")
    if expected_known:
        if actual is None:
            return fact(
                path,
                "symbolic",
                origin,
                source_name,
                expression,
                "constant expression is retained for the target translator",
            )
        status = "resolved" if actual == expected else "unresolved"
        reason = (
            "constant source value is parsed"
            if status == "resolved"
            else f"expected parsed value {expected!r}, found {actual!r}"
        )
        return fact(path, status, origin, source_name, expression, reason)
    if actual is not None:
        return fact(path, "resolved", origin, source_name, expression, "source value is parsed")
    unresolved = component.get("unresolved") or []
    if any(
        isinstance(item, dict)
        and item.get("path") == path
        and item.get("expression") == expression
        for item in unresolved
    ):
        return fact(
            path,
            "symbolic",
            origin,
            source_name,
            expression,
            "dynamic expression is retained without inventing a value",
        )
    return fact(
        path,
        "symbolic",
        origin,
        source_name,
        expression,
        "exact source expression is retained for the target translator",
    )


def build_required_facts(component: dict[str, Any]) -> list[dict[str, str | None]]:
    component_type = str(component.get("type") or "View")
    result = [
        fact("structure.type", "resolved", "structure", "type", component_type, "component type is retained"),
        fact("structure.parent_id", "resolved", "structure", "parent_id", None, "parent relationship is retained"),
        fact("structure.children_ids", "resolved", "structure", "children_ids", None, "child order is retained"),
        fact("structure.sibling_index", "resolved", "structure", "sibling_index", None, "sibling order is retained"),
    ]
    # These affect native UI, but cannot be reconstructed from a generic frame/style.
    # Retain an explicit failure instead of silently ignoring a recognized argument.
    unsupported_arguments = {
        'visualTransformation', 'keyboardOptions', 'readOnly',
        'singleLine', 'isError', 'leadingIcon', 'trailingIcon', 'prefix', 'suffix',
        'supportingText', 'colors', 'filterQuality', 'propagateMinConstraints',
        'windowInsets', 'reverseLayout', 'userScrollEnabled', 'thumb', 'track', 'thumbContent',
        'strokeCap', 'gapSize', 'drawStopIndicator', 'startIndent',
    }
    from page_component_catalog import NATIVE_CONTAINERS, NATIVE_LEAVES, NATIVE_BUTTONS
    from page_native_controls import CONTROL_TYPES, PROGRESS_TYPES, SELECTION_FIELDS, arguments_for, parse_argument
    if component_type in CONTROL_TYPES:
        for name in arguments_for(component_type):
            expression = semantic_expression(component, name)
            if expression is None:
                continue
            parsed = parse_argument(name, expression)
            if parsed is None:
                result.append(fact('source.arguments.' + name.lower(), 'unresolved', 'semantic_argument', name,
                                   expression, 'control argument is not a supported constant'))
            else:
                result.extend(explicit_fact(component, 'style.control.' + field, 'semantic_argument', name,
                    expression, value, expected_known=True) for field, value in parsed.items())
        required = ('state', SELECTION_FIELDS[component_type]) if component_type in SELECTION_FIELDS else (
            ('control', 'value') if component_type in PROGRESS_TYPES | {'Slider'} else None)
        if required and (component.get('style', {}).get(required[0]) or {}).get(required[1]) is None:
            result.append(fact('style.' + '.'.join(required), 'unresolved', 'semantic_argument', required[1], None,
                               'a resolved visual state is required; no default demo state'))
    if component_type in NATIVE_CONTAINERS | NATIVE_LEAVES | NATIVE_BUTTONS:
        for name in sorted(unsupported_arguments):
            expression = semantic_expression(component, name)
            if expression is not None:
                if component_type in INPUT_TYPES and name in INPUT_ARGUMENTS:
                    values = input_argument_values(name, expression)
                    if values is not None:
                        result.extend(explicit_fact(component, 'style.input.' + field,
                            'semantic_argument', name, expression, value, expected_known=True)
                            for field, value in values.items())
                        continue
                if name == 'colors' and component_type in {'TopAppBar', 'CenterAlignedTopAppBar'}:
                    background = simple_appbar_background(expression)
                    if background is not None:
                        result.append(explicit_fact(component, 'style.surface.background',
                            'semantic_argument', name, expression, background, expected_known=True))
                        continue
                if name == 'colors' and component_type == 'Card' and re.fullmatch(r'CardDefaults\.cardColors\(.*\)', expression, re.S):
                    _, color_args = parsed_arguments(expression[expression.index('(') + 1:-1])
                    paths = ['style.surface.background']
                    if 'contentColor' in color_args or 'disabledContentColor' in color_args:
                        paths.append('style.typography.color')
                    result.extend(explicit_fact(component, path, 'semantic_argument', name, expression)
                                  for path in paths)
                    continue
                result.append(fact(f'source.arguments.{name.lower()}', 'unresolved',
                    'semantic_argument', name, expression, 'native argument has no complete single-JSON mapping'))
        if component_type in {'BasicTextField', 'TextField', 'OutlinedTextField'}:
            expression = semantic_expression(component, 'label')
            if expression is not None:
                result.append(fact('source.arguments.label', 'unresolved', 'semantic_argument',
                    'label', expression, 'a floating label or composable slot is not a placeholder'))
    sequence = []
    for modifier in component.get("modifiers") or []:
        if not isinstance(modifier, dict):
            continue
        name, expression = modifier.get("name"), str(modifier.get("arguments") or "")
        sequence.extend(nested_modifier_calls(expression) if name == "then" else [(name, expression)])
    padding_seen = False
    for name, expression in sequence:
        if (name == "padding" and padding_seen) or (padding_seen and name in {"width", "height", "size", "requiredWidth", "requiredHeight"} and "IntrinsicSize" not in expression):
            result.append(fact("source.modifiers.order", "unresolved", "modifier", "order", str(sequence),
                               "ordered size/padding wrappers are not yet represented; flattening would change measurement"))
            break
        padding_seen |= name == "padding"

    semantic_rules: dict[str, tuple[str, Any]] = {
        "fontStyle": ("style.typography.font_style", lambda value: {"FontStyle.Normal": "normal", "FontStyle.Italic": "italic"}.get(value)),
        "letterSpacing": ("style.typography.letter_spacing_sp", lambda value: number_expression(value, "sp")),
        "fontSize": ("style.typography.font_size_sp", lambda value: number_expression(value, "sp")),
        "lineHeight": ("style.typography.line_height_sp", lambda value: number_expression(value, "sp")),
        "fontWeight": ("style.typography.font_weight", font_weight_expression),
        "maxLines": ("style.typography.max_lines", integer_expression),
        "minLines": ("style.typography.min_lines", integer_expression),
        "softWrap": ("style.typography.soft_wrap", lambda value: {'true': True, 'false': False}.get(value)),
        "overflow": ("style.typography.overflow", lambda value: OVERFLOW_VALUES.get(value)),
        "textDecoration": ("style.typography.decoration", lambda value: DECORATION_VALUES.get(value)),
        "textAlign": ("style.typography.text_align", lambda value: TEXT_ALIGN_VALUES.get(value)),
        "contentScale": ("style.asset.content_scale", lambda value: CONTENT_SCALE_VALUES.get(value)),
        **{name: (f"style.state.{name}", lambda value: {"true": True, "false": False}.get(value))
           for name in ("enabled", "visible", "selected", "checked")},
    }
    for name, (path, parser) in semantic_rules.items():
        expression = semantic_expression(component, name)
        if expression is None:
            continue
        expected = parser(expression)
        result.append(
            explicit_fact(
                component,
                path,
                "semantic_argument",
                name,
                expression,
                expected,
                expected_known=expected is not None,
            )
        )

    style_expression = semantic_expression(component, "style") or semantic_expression(component, "textStyle")
    if style_expression is not None:
        style_rules = (
            ("style.typography.font_size_sp", "style.fontSize", style_number(style_expression, "fontSize", "sp")),
            ("style.typography.line_height_sp", "style.lineHeight", style_number(style_expression, "lineHeight", "sp")),
            ("style.typography.font_weight", "style.fontWeight", style_font_weight(style_expression)),
            ("style.typography.color", "style.color", style_hex_color(style_expression)),
        )
        for path, name, expected in style_rules:
            if expected is not None and not any(item['path'] == path for item in result):
                result.append(
                    explicit_fact(
                        component,
                        path,
                        "semantic_style",
                        name,
                        style_expression,
                        expected,
                        expected_known=True,
                    )
                )

    for name, path in (
        ("text", "style.content.text"),
        ("placeholder", "style.content.placeholder"),
        ("color", "style.typography.color"),
        ("fontFamily", "style.typography.font_family"),
        ("contentPadding", "style.layout.padding_dp"),
        ("contentAlignment", "style.layout.alignment"),
        ("alignment", "style.layout.alignment"),
        ("horizontalAlignment", "style.layout.alignment"),
        ("verticalAlignment", "style.layout.alignment"),
        ("horizontalArrangement", "style.layout.horizontal_arrangement"),
        ("verticalArrangement", "style.layout.vertical_arrangement"),
    ):
        expression = semantic_expression(component, name)
        if component_type in CONTROL_TYPES and name == 'color':
            continue
        if expression is not None and not (
            name in {"placeholder", "label"}
            and is_preview_only_placeholder_expression(expression)
        ):
            result.append(explicit_fact(component, path, "semantic_argument", name, expression))

    description = semantic_expression(component, "contentDescription")
    if description is not None:
        result.append(
            explicit_fact(
                component,
                "style.content.content_description",
                "semantic_argument",
                "contentDescription",
                description,
                explicit_null=description == "null",
            )
        )

    tint = semantic_expression(component, 'tint')
    if tint is not None:
        result.append(explicit_fact(component, 'style.asset.tint', 'semantic_argument', 'tint',
                                    tint, explicit_null=tint == 'Color.Unspecified'))

    painter = next(
        (
            semantic_expression(component, name)
            for name in ("painter", "imageVector", "model")
            if semantic_expression(component, name) is not None
        ),
        None,
    )
    if painter is not None:
        result.append(
            explicit_fact(component, "style.asset.resource", "semantic_argument", "asset", painter)
        )

    layout_rules = component.get("layout_rules")
    if not isinstance(layout_rules, list):
        layout_rules = normalized_layout_rules(component)
    normalized_modifier_indexes = {
        rule.get("source_modifier_index")
        for rule in layout_rules
        if isinstance(rule, dict)
        and type(rule.get("source_modifier_index")) is int
    }
    for index, modifier in enumerate(component.get("modifiers") or []):
        if not isinstance(modifier, dict) or not isinstance(modifier.get("name"), str):
            continue
        name = modifier["name"]
        expression = str(modifier.get("arguments") or "").strip()
        if name == "then":
            for nested_name, nested_arguments in nested_modifier_calls(expression):
                if nested_name == "then":
                    continue
                nested = dict(component, modifiers=[{"name": nested_name, "arguments": nested_arguments}])
                nested.pop("layout_rules", None)
                result.extend(item for item in build_required_facts(nested) if item["origin"] == "modifier")
            continue
        path = None
        expected: Any = None
        expected_known = False
        if name == "size":
            for axis, size in zip(("width", "height"), size_arguments(expression)):
                result.append(
                    explicit_fact(
                        component,
                        f"style.layout.{axis}_dp",
                        "modifier",
                        name,
                        expression,
                        size,
                        expected_known=size is not None,
                    )
                )
            continue
        if name in {"width", "height"} and any(
            isinstance(rule, dict)
            and rule.get("kind") == "intrinsic_size"
            and rule.get("axis") == name
            and rule.get("source_modifier_index") == index
            for rule in layout_rules
        ):
            result.append(
                fact(
                    f"source.modifiers.{name.lower()}",
                    "resolved",
                    "modifier",
                    name,
                    expression,
                    "layout operation is normalized in layout_rules",
                )
            )
            continue
        if name in {"width", "requiredWidth", "height", "requiredHeight"}:
            axis = "width" if "Width" in name or name == "width" else "height"
            path = f"style.layout.{axis}_dp"
            expected = number_expression(expression, "dp")
            expected_known = expected is not None
        elif name == "padding":
            path = "style.layout.padding_dp"
        elif name == "background":
            path = "style.surface.background"
        elif name == "border" or name == "dashedBorder":
            path = "style.surface.border"
        elif name in {"shadow", "requireCardElevation"}:
            path = "style.surface.shadows"
        elif name == "clip":
            path = "style.surface.clip"
            expected = True
            expected_known = True
        elif name == "alpha":
            path = "style.surface.alpha"
            try:
                expected = float(expression)
                expected_known = True
            except ValueError:
                pass
        elif name == "rotate":
            path = "style.transform.rotation_degrees"
            expected = numeric_literal(expression)
            expected_known = expected is not None
        elif name == "scale":
            positional, named = parsed_arguments(expression)
            common = named.get("scale") or (positional[0] if len(positional) == 1 else None)
            for axis, offset in (("x", 0), ("y", 1)):
                value = numeric_literal(named.get(f"scale{axis.upper()}") or
                                        (positional[offset] if len(positional) > 1 else common))
                result.append(explicit_fact(component, f"style.transform.scale_{axis}",
                    "modifier", name, expression, value, expected_known=value is not None))
            continue
        elif name == "aspectRatio":
            path = "style.layout.aspect_ratio"
            try:
                expected = float(expression.split(",", 1)[0].rstrip("fF"))
                expected_known = True
            except ValueError:
                pass
        elif name in {
            "weight", "offset", "fillMaxWidth", "fillMaxHeight", "fillMaxSize",
            "wrapContentWidth", "wrapContentHeight", "wrapContentSize", "matchParentSize",
            "constrainAs", "align", "zIndex",
            "widthIn", "heightIn", "sizeIn", "verticalScroll", "horizontalScroll",
        }:
            result.append(
                fact(
                    f"source.modifiers.{name.lower()}",
                    "resolved" if index in normalized_modifier_indexes else "symbolic",
                    "modifier",
                    name,
                    expression or name,
                    (
                        "layout operation is normalized in layout_rules"
                        if index in normalized_modifier_indexes
                        else "layout relationship expression is retained for target translation"
                    ),
                )
            )
            continue
        if path is not None:
            result.append(
                explicit_fact(
                    component,
                    path,
                    "modifier",
                    name,
                    expression or name,
                    expected,
                    expected_known=expected_known,
                )
            )
        elif name not in {"clickable", "selectable", "testTag", "semantics", "onGloballyPositioned"}:
            result.append(fact(f"source.modifiers.{name.lower()}", "unresolved", "modifier", name,
                               expression or name, "modifier has no declared page-layout mapping"))

    if component_type in TEXT_TYPES:
        for path, default in (
            ("style.typography.font_size_sp", "Material3 contextual text style"),
            ("style.typography.font_weight", "Material3 contextual text style"),
            ("style.typography.color", "LocalContentColor.current"),
        ):
            if not any(item["path"] == path for item in result):
                status = "default_resolved" if nested_value(component, path) is not None else "symbolic"
                result.append(fact(path, status, "component_default", component_type, default, "framework default is explicit"))
    if component_type in IMAGE_TYPES and not any(
        item["path"] == "style.asset.content_scale" for item in result
    ):
        result.append(fact("style.asset.content_scale", "default_resolved", "component_default", component_type, "ContentScale.Fit", "framework image default is explicit"))
    if component_type in BUTTON_TYPES:
        result.append(
            fact(
                "style.state.clickable",
                "default_resolved",
                "component_default",
                component_type,
                "true",
                "button semantics provide the click boundary",
            )
        )
    return result


def normalize_required_facts(value: Any, label: str) -> list[dict[str, str | None]]:
    if not isinstance(value, list) or len(value) > 5000:
        raise ValueError(f"{label} must be a list")
    required = {"path", "status", "origin", "source_name", "expression", "reason"}
    result: list[dict[str, str | None]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != required:
            raise ValueError(f"{label}[{index}] is malformed")
        path = item["path"]
        status = item["status"]
        if not isinstance(path, str) or FACT_PATH_PATTERN.fullmatch(path) is None:
            raise ValueError(f"{label}[{index}].path is malformed")
        if status not in FACT_STATUSES:
            raise ValueError(f"{label}[{index}].status is unsupported")
        for field in ("origin", "source_name", "reason"):
            if not isinstance(item[field], str) or not item[field]:
                raise ValueError(f"{label}[{index}].{field} is malformed")
        expression = item["expression"]
        if expression is not None and not isinstance(expression, str):
            raise ValueError(f"{label}[{index}].expression is malformed")
        result.append(dict(item))
    return result


def required_fact_gate(components: list[dict[str, Any]]) -> dict[str, Any]:
    facts = [
        {"component_id": component.get("id"), **item}
        for component in components
        for item in component.get("required_facts") or []
    ]
    failures = [item for item in facts if item["status"] == "unresolved"]
    counts = {
        status: sum(item["status"] == status for item in facts)
        for status in sorted(FACT_STATUSES)
    }
    return {
        "verdict": "pass" if not failures else "fail",
        "required_count": len(facts),
        "failure_count": len(failures),
        "status_counts": counts,
        "failures": failures,
    }
