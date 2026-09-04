#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections import Counter
from pathlib import Path
from typing import Any

from generate_source_attribute_inventory import call_attributes
from page_snapshot import empty_style


SOURCE_PAGE_SCHEMA = "android-to-harmony.source-page-spec.v1"
PAGE_SCHEMA = "android-to-harmony.page-snapshot.v2"
RUNTIME_SOURCE_MAP_SCHEMA = "android-to-harmony.runtime-source-map.v1"
BOUNDS_PATTERN = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
STRING_RESOURCE_PATTERN = re.compile(r"(?:stringResource\s*\(\s*)?(?:id\s*=\s*)?R\.string\.([A-Za-z0-9_]+)")
DRAWABLE_RESOURCE_PATTERN = re.compile(r"R\.(?:drawable|mipmap)\.([A-Za-z0-9_]+)")
HEX_COLOR_PATTERN = re.compile(r"(?:Color\s*\(\s*)?(0x[0-9A-Fa-f]{8}|#[0-9A-Fa-f]{6,8})")
QUOTED_STRING_PATTERN = re.compile(r'^"((?:[^"\\]|\\.)*)"$')
MATERIAL3_TYPOGRAPHY: dict[str, tuple[float, float, int]] = {
    "displayLarge": (57.0, 64.0, 400),
    "displayMedium": (45.0, 52.0, 400),
    "displaySmall": (36.0, 44.0, 400),
    "headlineLarge": (32.0, 40.0, 400),
    "headlineMedium": (28.0, 36.0, 400),
    "headlineSmall": (24.0, 32.0, 400),
    "titleLarge": (22.0, 28.0, 400),
    "titleMedium": (16.0, 24.0, 500),
    "titleSmall": (14.0, 20.0, 500),
    "bodyLarge": (16.0, 24.0, 400),
    "bodyMedium": (14.0, 20.0, 400),
    "bodySmall": (12.0, 16.0, 400),
    "labelLarge": (14.0, 20.0, 500),
    "labelMedium": (12.0, 16.0, 500),
    "labelSmall": (11.0, 16.0, 500),
}


class RealPageError(RuntimeError):
    pass


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_runtime_source_map_file(path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    if path is None:
        return None, None
    resolved = path.expanduser().resolve()
    if path.is_symlink() or not resolved.is_file():
        raise RealPageError("runtime source map must be a regular non-symbolic-link JSON file")
    raw = resolved.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RealPageError(f"runtime source map is invalid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise RealPageError("runtime source map root must be an object")
    return payload, hashlib.sha256(raw).hexdigest()


def source_component_id(instance_path: str, call_id: str) -> str:
    digest = hashlib.sha256(f"{instance_path}\0{call_id}".encode("utf-8")).hexdigest()[:20]
    return f"source-{digest}"


def source_semantic_key(call: dict[str, Any]) -> str:
    call_id = str(call.get("call_id", ""))
    try:
        _source, line, component, ordinal = call_id.rsplit(":", 3)
    except ValueError:
        line = str(call.get("line", 0))
        component = str(call.get("component", "View"))
        ordinal = "0"
    composable = str(call.get("composable", "Page"))
    tokens = [re.sub(r"[^A-Za-z0-9_]", "_", value).strip("_") for value in (composable, component, line, ordinal)]
    return "_".join(value or "unknown" for value in tokens)[:120]


def resource_values(contract: dict[str, Any]) -> dict[tuple[str, str], str]:
    ui = contract.get("ui")
    inventory = ui.get("android_value_resource_inventory") if isinstance(ui, dict) else None
    raw = inventory.get("resources") if isinstance(inventory, dict) else None
    result: dict[tuple[str, str], str] = {}
    if not isinstance(raw, list):
        return result
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind, name, value = item.get("type"), item.get("name"), item.get("value")
        qualifier = item.get("qualifier")
        if isinstance(kind, str) and isinstance(name, str) and isinstance(value, str):
            key = (kind, name)
            if key not in result or qualifier == "values":
                result[key] = value
    return result


def decode_literal(expression: str) -> str | None:
    match = QUOTED_STRING_PATTERN.fullmatch(expression.strip())
    if match is None:
        return None
    try:
        return json.loads(expression.strip())
    except json.JSONDecodeError:
        return match.group(1)


def resolve_text(expression: str, values: dict[tuple[str, str], str]) -> str | None:
    literal = decode_literal(expression)
    if literal is not None:
        return literal
    match = STRING_RESOURCE_PATTERN.search(expression)
    if match is not None:
        return values.get(("string", match.group(1)))
    return None


def semantic_expression(call: dict[str, Any], name: str) -> str | None:
    semantic = call.get("semantic_arguments")
    value = semantic.get(name) if isinstance(semantic, dict) else None
    expression = value.get("expression") if isinstance(value, dict) else None
    return expression if isinstance(expression, str) and expression.strip() else None


def first_positional_expression(call: dict[str, Any]) -> str | None:
    return positional_expression(call, 0)


def positional_expression(call: dict[str, Any], index: int) -> str | None:
    positional = call.get("positional_arguments")
    if (
        not isinstance(positional, list)
        or index < 0
        or index >= len(positional)
        or not isinstance(positional[index], dict)
    ):
        return None
    expression = positional[index].get("expression")
    return expression if isinstance(expression, str) and expression.strip() else None


def number(value: str) -> float:
    return round(float(value), 3)


def modifier_dimensions(modifier: dict[str, Any]) -> list[tuple[float, str]]:
    raw = modifier.get("dimensions")
    if not isinstance(raw, list):
        return []
    result: list[tuple[float, str]] = []
    for item in raw:
        if not isinstance(item, dict) or item.get("unit") not in {"dp", "sp"}:
            continue
        value = item.get("value")
        if isinstance(value, str) and re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", value):
            result.append((number(value), item["unit"]))
    return result


def direct_padding(arguments: str, dimensions: list[tuple[float, str]]) -> dict[str, float] | None:
    dp_values = [value for value, unit in dimensions if unit == "dp"]
    if not dp_values:
        return None
    named: dict[str, float] = {}
    for name, value in re.findall(
        r"(start|end|left|right|top|bottom|horizontal|vertical|all)\s*=\s*(-?[0-9]+(?:\.[0-9]+)?)\.dp",
        arguments,
    ):
        named[name] = number(value)
    if not named:
        if len(dp_values) == 1:
            return {edge: dp_values[0] for edge in ("left", "top", "right", "bottom")}
        return None
    all_value = named.get("all", 0.0)
    horizontal = named.get("horizontal", all_value)
    vertical = named.get("vertical", all_value)
    return {
        "left": named.get("left", named.get("start", horizontal)),
        "top": named.get("top", vertical),
        "right": named.get("right", named.get("end", horizontal)),
        "bottom": named.get("bottom", vertical),
    }


def find_resource_file(source_root: Path | None, resource: str) -> Path | None:
    if source_root is None or not source_root.is_dir():
        return None
    resource_roots = [source_root / "src" / "main" / "res"]
    resource_roots.extend(
        child / "src" / "main" / "res"
        for child in source_root.iterdir()
        if child.is_dir() and not child.is_symlink()
    )
    candidates = sorted(
        path
        for resource_root in resource_roots
        if resource_root.is_dir()
        for path in resource_root.glob(f"*/{resource}.*")
        if path.is_file() and not path.is_symlink()
    )
    defaults = [path for path in candidates if path.parent.name in {"drawable", "mipmap"}]
    return (defaults or candidates or [None])[0]


def static_style_for_call(
    call: dict[str, Any],
    values: dict[tuple[str, str], str],
    source_root: Path | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, str]]]:
    style = empty_style()
    provenance_paths: list[str] = []
    unresolved: list[dict[str, str]] = []
    component = str(call.get("component", "View"))
    content = style["content"]
    state = style["state"]
    role = {
        "Text": "text",
        "BasicText": "text",
        "Button": "button",
        "IconButton": "button",
        "FloatingActionButton": "button",
        "SmallFloatingActionButton": "button",
        "Image": "image",
        "Icon": "image",
        "TextField": "textbox",
        "OutlinedTextField": "textbox",
        "BasicTextField": "textbox",
        "Checkbox": "checkbox",
        "Switch": "switch",
    }.get(component)
    if role is not None:
        content["role"] = role
        provenance_paths.append("style.content.role")
    text_expression = semantic_expression(call, "text") or (
        first_positional_expression(call) if component in {"Text", "BasicText", "ClickableText"} else None
    )
    if text_expression is not None:
        text = resolve_text(text_expression, values)
        if text is not None:
            content["text"] = text
            provenance_paths.append("style.content.text")
        else:
            unresolved.append(
                {"path": "style.content.text", "expression": text_expression, "reason": "dynamic source expression"}
            )
    description_expression = semantic_expression(call, "contentDescription") or (
        positional_expression(call, 1) if component == "Icon" else None
    )
    if description_expression is not None:
        if description_expression.strip() == "null":
            provenance_paths.append("style.content.content_description")
        else:
            description = resolve_text(description_expression, values)
            if description is not None:
                content["content_description"] = description
                provenance_paths.append("style.content.content_description")
            else:
                unresolved.append(
                    {
                        "path": "style.content.content_description",
                        "expression": description_expression,
                        "reason": "dynamic source expression",
                    }
                )
    if component in {"Text", "BasicText", "ClickableText"}:
        font_size_expression = semantic_expression(call, "fontSize")
        if font_size_expression is not None:
            match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\.sp\s*", font_size_expression)
            if match is not None:
                style["typography"]["font_size_sp"] = number(match.group(1))
                provenance_paths.append("style.typography.font_size_sp")
        color_expression = semantic_expression(call, "color")
        if color_expression is not None:
            match = HEX_COLOR_PATTERN.search(color_expression)
            if match is not None:
                style["typography"]["color"] = match.group(1).replace("0x", "#").upper()
                provenance_paths.append("style.typography.color")
        style_expression = semantic_expression(call, "style")
        if style_expression is not None:
            typography_patterns = {
                "font_size_sp": r"\bfontSize\s*=\s*([0-9]+(?:\.[0-9]+)?)\.sp\b",
                "line_height_sp": r"\blineHeight\s*=\s*([0-9]+(?:\.[0-9]+)?)\.sp\b",
            }
            for field, pattern in typography_patterns.items():
                match = re.search(pattern, style_expression)
                if match is not None:
                    style["typography"][field] = number(match.group(1))
                    provenance_paths.append(f"style.typography.{field}")
            weight_match = re.search(
                r"\bfontWeight\s*=\s*FontWeight(?:\(\s*([1-9][0-9]{2})\s*\)|\.(Normal|Medium|SemiBold|Bold))",
                style_expression,
            )
            if weight_match is not None:
                named_weights = {"Normal": 400, "Medium": 500, "SemiBold": 600, "Bold": 700}
                style["typography"]["font_weight"] = (
                    int(weight_match.group(1))
                    if weight_match.group(1) is not None
                    else named_weights[weight_match.group(2)]
                )
                provenance_paths.append("style.typography.font_weight")
            color_match = HEX_COLOR_PATTERN.search(style_expression)
            if color_match is not None:
                style["typography"]["color"] = color_match.group(1).replace("0x", "#").upper()
                provenance_paths.append("style.typography.color")
        style_name = style_expression.rsplit(".", 1)[-1] if style_expression else None
        if style_name in MATERIAL3_TYPOGRAPHY:
            font_size, line_height, font_weight = MATERIAL3_TYPOGRAPHY[style_name]
            style["typography"].update(
                {
                    "font_size_sp": font_size,
                    "line_height_sp": line_height,
                    "font_weight": font_weight,
                }
            )
            provenance_paths.extend(
                (
                    "style.typography.font_size_sp",
                    "style.typography.line_height_sp",
                    "style.typography.font_weight",
                )
            )
    placeholder_expression = semantic_expression(call, "placeholder") or semantic_expression(call, "label")
    if placeholder_expression is not None:
        placeholder = resolve_text(placeholder_expression, values)
        if placeholder is not None:
            content["placeholder"] = placeholder
            provenance_paths.append("style.content.placeholder")
        else:
            unresolved.append(
                {
                    "path": "style.content.placeholder",
                    "expression": placeholder_expression,
                    "reason": "slot or dynamic source expression",
                }
            )
    clickable = component in {
        "Button", "IconButton", "FloatingActionButton", "SmallFloatingActionButton"
    } or semantic_expression(call, "onClick") is not None
    state["clickable"] = clickable
    state["enabled"] = True
    state["visible"] = True
    provenance_paths.extend(("style.state.clickable", "style.state.enabled", "style.state.visible"))
    if component in {"Button", "IconButton", "FloatingActionButton", "SmallFloatingActionButton"}:
        style["surface"]["clip"] = True
        provenance_paths.append("style.surface.clip")

    painter_expression = (
        semantic_expression(call, "painter")
        or semantic_expression(call, "imageVector")
        or (first_positional_expression(call) if component == "Icon" else None)
    )
    if painter_expression is not None:
        match = DRAWABLE_RESOURCE_PATTERN.search(painter_expression)
        if match is not None:
            resource = match.group(1)
            style["asset"]["resource"] = resource
            provenance_paths.append("style.asset.resource")
            file = find_resource_file(source_root, resource)
            if file is not None:
                style["asset"]["sha256"] = hashlib.sha256(file.read_bytes()).hexdigest()
                provenance_paths.append("style.asset.sha256")
        elif "Icons." in painter_expression:
            style["asset"]["resource"] = painter_expression.strip()
            provenance_paths.append("style.asset.resource")
        else:
            unresolved.append(
                {"path": "style.asset.resource", "expression": painter_expression, "reason": "dynamic source expression"}
            )
        content_scale = semantic_expression(call, "contentScale")
        content_scale_name = content_scale.rsplit(".", 1)[-1].lower() if content_scale else "fit"
        style["asset"]["content_scale"] = {
            "fit": "fit",
            "crop": "crop",
            "fillbounds": "fill",
            "inside": "inside",
            "none": "none",
        }.get(content_scale_name)
        if style["asset"]["content_scale"] is not None:
            provenance_paths.append("style.asset.content_scale")

    for modifier in call.get("ordered_modifier_chain", []):
        if not isinstance(modifier, dict) or not isinstance(modifier.get("name"), str):
            continue
        name = modifier["name"]
        arguments = str(modifier.get("arguments", ""))
        dimensions = modifier_dimensions(modifier)
        dp_values = [value for value, unit in dimensions if unit == "dp"]
        if name == "size" and dp_values:
            style["asset"]["width_dp"] = dp_values[0]
            style["asset"]["height_dp"] = dp_values[0]
            provenance_paths.extend(("style.asset.width_dp", "style.asset.height_dp"))
        elif name in {"width", "requiredWidth"} and dp_values:
            style["asset"]["width_dp"] = dp_values[0]
            provenance_paths.append("style.asset.width_dp")
        elif name in {"height", "requiredHeight"} and dp_values:
            style["asset"]["height_dp"] = dp_values[0]
            provenance_paths.append("style.asset.height_dp")
        elif name == "padding":
            padding = direct_padding(arguments, dimensions)
            if padding is not None:
                style["layout"]["padding_dp"] = padding
                provenance_paths.append("style.layout.padding_dp")
        elif name == "aspectRatio":
            match = re.search(r"-?[0-9]+(?:\.[0-9]+)?", arguments)
            if match is not None:
                style["layout"]["aspect_ratio"] = number(match.group(0))
                provenance_paths.append("style.layout.aspect_ratio")
        elif name == "alpha":
            match = re.search(r"[0-9]+(?:\.[0-9]+)?", arguments)
            if match is not None:
                style["surface"]["alpha"] = number(match.group(0))
                provenance_paths.append("style.surface.alpha")
        elif name == "background":
            match = HEX_COLOR_PATTERN.search(arguments)
            if match is not None:
                raw = match.group(1).replace("0x", "#")
                style["surface"]["background"] = {"type": "solid", "color": raw.upper()}
                provenance_paths.append("style.surface.background")
            elif arguments:
                unresolved.append(
                    {"path": "style.surface.background", "expression": arguments, "reason": "theme or dynamic source expression"}
                )
        elif name == "clip":
            radius = re.search(r"RoundedCornerShape\s*\(\s*([0-9]+(?:\.[0-9]+)?)\.dp", arguments)
            if radius is not None:
                value = number(radius.group(1))
                style["surface"]["corner_radius_dp"] = {
                    "top_left": value,
                    "top_right": value,
                    "bottom_right": value,
                    "bottom_left": value,
                }
                style["surface"]["clip"] = True
                provenance_paths.extend(("style.surface.corner_radius_dp", "style.surface.clip"))
    provenance = []
    if provenance_paths:
        provenance.append(
            {
                "paths": sorted(set(provenance_paths)),
                "origin": "source_resolved",
                "source": f"{call['source']}:{call['line']}",
            }
        )
    return style, provenance, unresolved


def build_source_page_spec(
    contract: dict[str, Any],
    root_source: str,
    root_composable: str,
    page_id: str,
    state_id: str,
    contract_sha256: str,
    source_root: Path | None = None,
) -> dict[str, Any]:
    ui = contract.get("ui")
    semantic = ui.get("semantic_translation_candidates") if isinstance(ui, dict) else None
    graph = ui.get("custom_composable_call_graph") if isinstance(ui, dict) else None
    calls = semantic.get("calls") if isinstance(semantic, dict) else None
    closures = graph.get("transitive_closures") if isinstance(graph, dict) else None
    if not isinstance(calls, list) or not isinstance(closures, list):
        raise RealPageError("contract has no Compose semantic call graph")
    closure = next(
        (
            item
            for item in closures
            if isinstance(item, dict)
            and item.get("root") == {"source": root_source, "composable": root_composable}
        ),
        None,
    )
    if closure is None:
        raise RealPageError("exact root source/composable closure was not found")
    reached = closure.get("reached_definitions")
    if not isinstance(reached, list):
        raise RealPageError("selected closure has no reached definitions")
    reached_keys = {
        (item.get("source"), item.get("composable"))
        for item in reached
        if isinstance(item, dict)
    }
    calls_by_definition: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    selected_calls: list[dict[str, Any]] = []
    for call in calls:
        if not isinstance(call, dict):
            continue
        key = (call.get("source"), call.get("composable"))
        if key not in reached_keys:
            continue
        calls_by_definition[key].append(call)
        selected_calls.append(call)
    for definition_calls in calls_by_definition.values():
        definition_calls.sort(key=lambda item: (int(item.get("line", 0)), str(item.get("call_id", ""))))
    values = resource_values(contract)
    components: list[dict[str, Any]] = []
    expansion_unresolved: list[dict[str, str]] = []
    semantic_key_counts: dict[str, int] = defaultdict(int)

    def expand_definition(
        definition: tuple[str, str],
        attach_parent: str | None,
        instance_path: str,
        stack: tuple[tuple[str, str], ...],
    ) -> None:
        if definition in stack:
            expansion_unresolved.append(
                {"path": instance_path, "expression": f"{definition[0]}#{definition[1]}", "reason": "recursive composable cycle"}
            )
            return
        definition_calls = calls_by_definition.get(definition, [])
        local_ids = {
            str(call["call_id"]): source_component_id(instance_path, str(call["call_id"]))
            for call in definition_calls
            if isinstance(call.get("call_id"), str)
        }
        created: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for call in definition_calls:
            call_id = call.get("call_id")
            if not isinstance(call_id, str):
                continue
            raw_parent = call.get("parent_call_id")
            parent_id = local_ids.get(raw_parent) if isinstance(raw_parent, str) else attach_parent
            style, provenance, unresolved = static_style_for_call(call, values, source_root)
            custom = call.get("custom_composable")
            base_semantic_key = source_semantic_key(call)
            semantic_key_counts[base_semantic_key] += 1
            semantic_key = (
                base_semantic_key
                if semantic_key_counts[base_semantic_key] == 1
                else f"{base_semantic_key}__{semantic_key_counts[base_semantic_key]}"
            )
            component = {
                "id": local_ids[call_id],
                "type": str(call.get("component", "View")),
                "semantic_key": semantic_key,
                "parent_id": parent_id,
                "children_ids": [],
                "sibling_index": 0,
                "source": {
                    "source": str(call.get("source", "")),
                    "composable": str(call.get("composable", "")),
                    "line": int(call.get("line", 0)),
                    "call_id": call_id,
                    "attributes": call_attributes(call),
                    "custom_component": isinstance(custom, dict),
                },
                "arguments": {
                    "semantic": copy.deepcopy(call.get("semantic_arguments", {})),
                    "positional": copy.deepcopy(call.get("positional_arguments", [])),
                    "state_slots": copy.deepcopy(call.get("state_slots", [])),
                },
                "modifiers": copy.deepcopy(call.get("ordered_modifier_chain", [])),
                "style": style,
                "provenance": provenance,
                "unresolved": unresolved,
            }
            components.append(component)
            created.append((component, call))
        for component, call in created:
            custom = call.get("custom_composable")
            definitions = custom.get("definitions") if isinstance(custom, dict) else None
            if not isinstance(definitions, list) or len(definitions) != 1 or not isinstance(definitions[0], dict):
                continue
            target = (definitions[0].get("source"), definitions[0].get("composable"))
            if not all(isinstance(item, str) for item in target) or target not in reached_keys:
                continue
            expand_definition(
                (str(target[0]), str(target[1])),
                component["id"],
                f"{instance_path}/{call['call_id']}",
                stack + (definition,),
            )

    expand_definition((root_source, root_composable), None, "root", ())
    by_id = {item["id"]: item for item in components}
    children: dict[str | None, list[str]] = defaultdict(list)
    for component in components:
        children[component["parent_id"]].append(component["id"])
    for parent_id, child_ids in children.items():
        for index, child_id in enumerate(child_ids):
            by_id[child_id]["sibling_index"] = index
        if parent_id is not None and parent_id in by_id:
            by_id[parent_id]["children_ids"] = child_ids
    for component in components:
        if component["type"] not in {"Text", "BasicText", "ClickableText"}:
            continue
        typography = component["style"]["typography"]
        if typography["font_size_sp"] is not None:
            continue
        parent = by_id.get(component["parent_id"] or "")
        token = "labelLarge" if parent is not None and parent["type"] in {"Button", "IconButton"} else "bodyLarge"
        font_size, line_height, font_weight = MATERIAL3_TYPOGRAPHY[token]
        typography.update(
            {"font_size_sp": font_size, "line_height_sp": line_height, "font_weight": font_weight}
        )
        component["provenance"].append(
            {
                "paths": [
                    "style.typography.font_size_sp",
                    "style.typography.line_height_sp",
                    "style.typography.font_weight",
                ],
                "origin": "source_resolved",
                "source": f"Material3 {token} default selected from source component context",
            }
        )
    selected_call_ids = {
        str(call["call_id"])
        for call in selected_calls
        if isinstance(call.get("call_id"), str)
    }
    emitted_call_ids = {
        str(component["source"]["call_id"])
        for component in components
        if isinstance(component.get("source"), dict)
        and isinstance(component["source"].get("call_id"), str)
    }
    return {
        "schema": SOURCE_PAGE_SCHEMA,
        "status": "candidate_requires_runtime_verification",
        "authoritative": False,
        "page": {"id": page_id, "state": state_id},
        "root": {"source": root_source, "composable": root_composable},
        "contract_sha256": contract_sha256,
        "components": components,
        "coverage": {
            "source_call_count": len(selected_call_ids),
            "emitted_call_count": len(emitted_call_ids),
            "emitted_call_ratio": round(len(emitted_call_ids) / len(selected_call_ids), 6) if selected_call_ids else 1.0,
            "expanded_instance_count": len(components),
        },
        "unresolved": expansion_unresolved,
        "limitations": [
            "All calls in the selected closure are retained; runtime state decides which conditional branches are visible.",
            "Source expressions are retained verbatim. A null style value is not guessed from pixels.",
            "Runtime bounds, rendered colors, and rendered typography must come from a bound runtime capture.",
        ],
    }


def bool_attribute(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.lower() == "true"


def runtime_type(class_name: str, clickable: bool) -> str:
    simple = class_name.rsplit(".", 1)[-1]
    if simple in {"TextView"}:
        return "Text"
    if simple in {"EditText", "AutoCompleteTextView"}:
        return "TextField"
    if simple in {"ImageView", "ImageButton"}:
        return "Image"
    if simple in {"Button", "CheckBox", "Switch", "RadioButton"}:
        return simple
    if simple == "View" and clickable:
        return "Button"
    return simple or "View"


def parse_bounds(raw: str, dimensions: tuple[int, int]) -> dict[str, int] | None:
    match = BOUNDS_PATTERN.fullmatch(raw)
    if match is None:
        return None
    left, top, right, bottom = (int(value) for value in match.groups())
    left = max(0, min(left, dimensions[0]))
    right = max(0, min(right, dimensions[0]))
    top = max(0, min(top, dimensions[1]))
    bottom = max(0, min(bottom, dimensions[1]))
    if right <= left or bottom <= top:
        return None
    return {"x": left, "y": top, "width": right - left, "height": bottom - top}


def parse_uiautomator_xml(
    xml_bytes: bytes,
    dimensions: tuple[int, int],
    package_name: str | None = None,
) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as error:
        raise RealPageError(f"UIAutomator XML is invalid: {error}") from error
    components: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}

    def walk(element: ET.Element, path: tuple[int, ...], nearest_parent: str | None) -> None:
        if element.tag != "node":
            for index, child in enumerate(element):
                walk(child, path + (index,), nearest_parent)
            return
        bounds = parse_bounds(element.attrib.get("bounds", ""), dimensions)
        package = element.attrib.get("package", "")
        resource_id = element.attrib.get("resource-id", "")
        system_bar = resource_id in {
            "android:id/statusBarBackground",
            "android:id/navigationBarBackground",
        }
        keep = bounds is not None and not system_bar and (not package_name or not package or package == package_name)
        parent_id = nearest_parent
        if keep:
            component_id = "runtime-" + "-".join(str(index) for index in path)
            clickable = bool_attribute(element.attrib.get("clickable"))
            style = empty_style()
            style["state"].update(
                {
                    "visible": True,
                    "enabled": bool_attribute(element.attrib.get("enabled"), True),
                    "selected": bool_attribute(element.attrib.get("selected")),
                    "checked": bool_attribute(element.attrib.get("checked")),
                    "clickable": clickable,
                }
            )
            text = element.attrib.get("text", "")
            description = element.attrib.get("content-desc", "")
            class_name = element.attrib.get("class", "android.view.View")
            kind = runtime_type(class_name, clickable)
            style["content"].update(
                {
                    "text": text or None,
                    "content_description": description or None,
                    "role": (
                        "textbox" if kind == "TextField"
                        else "checkbox" if kind == "CheckBox"
                        else "switch" if kind == "Switch"
                        else "radio" if kind == "RadioButton"
                        else "button" if clickable or kind in {"Button", "ImageButton"}
                        else "image" if kind == "Image"
                        else "text" if kind == "Text"
                        else None
                    ),
                }
            )
            component = {
                "id": component_id,
                "runtime_class": class_name,
                "resource_id": resource_id or None,
                "type": kind,
                "bounds_px": bounds,
                "parent_id": parent_id,
                "children_ids": [],
                "sibling_index": 0,
                "style": style,
            }
            components.append(component)
            by_id[component_id] = component
            if parent_id is not None:
                parent = by_id[parent_id]
                component["sibling_index"] = len(parent["children_ids"])
                parent["children_ids"].append(component_id)
            parent_id = component_id
        for index, child in enumerate(element):
            walk(child, path + (index,), parent_id)

    walk(root, (), None)
    return components


def parse_harmony_layout_json(
    layout_bytes: bytes,
    dimensions: tuple[int, int],
    bundle_name: str | None = None,
) -> list[dict[str, Any]]:
    try:
        root = json.loads(layout_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RealPageError(f"OpenHarmony uitest layout is invalid: {error}") from error
    if not isinstance(root, dict):
        raise RealPageError("OpenHarmony uitest layout root must be an object")
    components: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}

    def walk(node: Any, path: tuple[int, ...], nearest_parent: str | None) -> None:
        if not isinstance(node, dict):
            return
        attributes = node.get("attributes")
        children = node.get("children")
        parent_id = nearest_parent
        if isinstance(attributes, dict):
            bounds = parse_bounds(str(attributes.get("bounds", "")), dimensions)
            kind = str(attributes.get("type", "")).strip()
            visible = bool_attribute(str(attributes.get("visible", "true")), True)
            keep = bounds is not None and visible and bool(kind)
            if keep:
                component_id = "runtime-h-" + "-".join(str(index) for index in path)
                runtime_id = str(attributes.get("id") or attributes.get("key") or "").strip() or None
                clickable = bool_attribute(str(attributes.get("clickable", "false"))) or kind == "Button"
                style = empty_style()
                style["state"].update(
                    {
                        "visible": True,
                        "enabled": bool_attribute(str(attributes.get("enabled", "true")), True),
                        "selected": bool_attribute(str(attributes.get("selected", "false"))),
                        "checked": bool_attribute(str(attributes.get("checked", "false"))),
                        "clickable": clickable,
                    }
                )
                text = str(attributes.get("text") or attributes.get("originalText") or "")
                description = str(attributes.get("description") or "")
                hint = str(attributes.get("hint") or "")
                normalized_kind = "TextField" if kind == "TextInput" else kind
                style["content"].update(
                    {
                        "text": text or None,
                        "placeholder": hint or None,
                        "content_description": description or None,
                        "role": (
                            "textbox" if normalized_kind == "TextField"
                            else "checkbox" if normalized_kind in {"Checkbox", "CheckBox"}
                            else "switch" if normalized_kind == "Switch"
                            else "radio" if normalized_kind == "RadioButton"
                            else "button" if clickable or normalized_kind == "Button"
                            else "image" if normalized_kind == "Image"
                            else "text" if normalized_kind == "Text"
                            else None
                        ),
                    }
                )
                background = str(attributes.get("backgroundColor") or "")
                if re.fullmatch(r"#[0-9A-Fa-f]{8}", background) and background.upper() != "#00000000":
                    style["surface"]["background"] = {"type": "solid", "color": background.upper()}
                opacity = str(attributes.get("opacity") or "")
                if re.fullmatch(r"(?:0(?:\.\d+)?|1(?:\.0+)?)", opacity) and float(opacity) != 1.0:
                    style["surface"]["alpha"] = round(float(opacity), 3)
                clip = attributes.get("clip")
                if str(clip).lower() == "true":
                    style["surface"]["clip"] = True
                z_index = str(attributes.get("zIndex") or "")
                if re.fullmatch(r"-?[0-9]+(?:\.\d+)?", z_index) and float(z_index) != 0.0:
                    style["layout"]["z_index"] = round(float(z_index), 3)
                background_image = str(attributes.get("backgroundImage") or "")
                if background_image and background_image != "empty source":
                    style["asset"]["resource"] = background_image
                component = {
                    "id": component_id,
                    "runtime_id": runtime_id,
                    "runtime_class": kind,
                    "resource_id": None,
                    "type": normalized_kind,
                    "bounds_px": bounds,
                    "parent_id": parent_id,
                    "children_ids": [],
                    "sibling_index": 0,
                    "style": style,
                    "runtime_attributes": {
                        key: attributes.get(key)
                        for key in ("accessibilityId", "hierarchy", "pagePath", "origBounds", "layoutDirection")
                        if attributes.get(key) not in {None, ""}
                    },
                }
                components.append(component)
                by_id[component_id] = component
                if parent_id is not None:
                    parent = by_id[parent_id]
                    component["sibling_index"] = len(parent["children_ids"])
                    parent["children_ids"].append(component_id)
                parent_id = component_id
        if isinstance(children, list):
            for index, child in enumerate(children):
                walk(child, path + (index,), parent_id)

    if bundle_name:
        root_children = root.get("children")
        matching_roots = [
            child
            for child in root_children
            if isinstance(root_children, list)
            and isinstance(child, dict)
            and isinstance(child.get("attributes"), dict)
            and child["attributes"].get("bundleName") == bundle_name
        ] if isinstance(root_children, list) else []
        if not matching_roots:
            raise RealPageError(f"OpenHarmony uitest layout has no root for bundle: {bundle_name}")
        if len(matching_roots) != 1:
            raise RealPageError(f"OpenHarmony uitest layout has ambiguous roots for bundle: {bundle_name}")
        walk(matching_roots[0], (0,), None)
    else:
        walk(root, (), None)
    return components


def color_distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> int:
    return max(abs(left[index] - right[index]) for index in range(3))


def detect_text_field_surface(
    crop: Any,
    dominant: tuple[int, int, int],
    density: float,
) -> dict[str, Any] | None:
    pixels = crop.load()
    row_counts = [
        sum(color_distance(pixels[x, y], dominant) >= 8 for x in range(crop.width))
        for y in range(crop.height)
    ]
    horizontal_threshold = max(4, round(crop.width * 0.45))
    horizontal_edges = [
        index for index, count in enumerate(row_counts) if count >= horizontal_threshold
    ]
    if len(horizontal_edges) < 2:
        return None
    top = horizontal_edges[0]
    bottom = horizontal_edges[-1]
    surface_height = bottom - top + 1
    if surface_height < 8:
        return None
    column_counts = [
        sum(color_distance(pixels[x, y], dominant) >= 8 for y in range(top, bottom + 1))
        for x in range(crop.width)
    ]
    vertical_threshold = max(4, round(surface_height * 0.45))
    vertical_edges = [
        index for index, count in enumerate(column_counts) if count >= vertical_threshold
    ]
    if len(vertical_edges) < 2:
        return None
    left = vertical_edges[0]
    right = vertical_edges[-1]
    surface_width = right - left + 1
    if surface_width < crop.width * 0.5:
        return None

    edge_pixels = []
    for x in range(left, right + 1):
        edge_pixels.extend((pixels[x, top], pixels[x, bottom]))
    for y in range(top, bottom + 1):
        edge_pixels.extend((pixels[left, y], pixels[right, y]))
    border_colors = Counter(
        color for color in edge_pixels if color_distance(color, dominant) >= 8
    )
    if not border_colors:
        return None
    border_color, _count = border_colors.most_common(1)[0]

    border_width_px = 1
    while border_width_px < min(8, surface_height // 2):
        sample_y = top + border_width_px
        matching = sum(
            color_distance(pixels[x, sample_y], border_color) <= 3
            for x in range(left, right + 1)
        )
        if matching < surface_width * 0.45:
            break
        border_width_px += 1

    inner_left = min(right, left + border_width_px + 1)
    inner_top = min(bottom, top + border_width_px + 1)
    inner_right = max(inner_left + 1, right - border_width_px)
    inner_bottom = max(inner_top + 1, bottom - border_width_px)
    inner = crop.crop((inner_left, inner_top, inner_right, inner_bottom))
    inner_data = inner.get_flattened_data() if hasattr(inner, "get_flattened_data") else inner.getdata()
    background, _background_count = Counter(inner_data).most_common(1)[0]

    foreground_points = [
        (x, y)
        for y in range(top + border_width_px, bottom - border_width_px + 1)
        for x in range(left + border_width_px, right - border_width_px + 1)
        if color_distance(pixels[x, y], background) >= 32
        and color_distance(pixels[x, y], border_color) >= 16
    ]
    content_padding_dp = None
    if len(foreground_points) >= 5:
        content_left = min(x for x, _y in foreground_points)
        horizontal = round((content_left - left) / density, 3)
        if horizontal >= 0:
            content_padding_dp = {
                "left": horizontal,
                "right": horizontal,
                "top": 0.0,
                "bottom": 0.0,
            }

    top_edge_x = [
        x for x in range(left, right + 1)
        if color_distance(pixels[x, top], border_color) <= 3
    ]
    radius_px = min(top_edge_x) - left if top_edge_x else 0
    radius_dp = round(radius_px / density, 3)
    return {
        "bounds_px": {
            "x": left,
            "y": top,
            "width": surface_width,
            "height": surface_height,
        },
        "background": "#FF" + "".join(f"{channel:02X}" for channel in background),
        "border": {
            "width_dp": round(border_width_px / density, 3),
            "color": "#FF" + "".join(f"{channel:02X}" for channel in border_color),
            "style": "solid",
        },
        "corner_radius_dp": {
            "top_left": radius_dp,
            "top_right": radius_dp,
            "bottom_right": radius_dp,
            "bottom_left": radius_dp,
        },
        "content_padding_dp": content_padding_dp,
    }


def apply_screenshot_visual_facts(
    screenshot_path: Path,
    runtime_components: list[dict[str, Any]],
    density: float,
    font_scale: float,
) -> dict[str, Any]:
    try:
        from PIL import Image
    except ImportError:
        return {"available": False, "reason": "Pillow is not installed", "sampled_component_count": 0}
    image = Image.open(screenshot_path).convert("RGB")
    sampled = 0
    for component in runtime_components:
        component_type = component["type"]
        if component_type not in {
            "Text", "TextField", "Button", "View", "FrameLayout", "LinearLayout", "RelativeLayout",
            "ConstraintLayout", "root", "Stack", "Column", "Row", "Flex", "Grid",
            "List", "Scroll", "Scroller", "Refresh", "RelativeContainer", "Surface",
            "Card", "Box",
        }:
            continue
        bounds = component["bounds_px"]
        crop = image.crop(
            (
                bounds["x"],
                bounds["y"],
                bounds["x"] + bounds["width"],
                bounds["y"] + bounds["height"],
            )
        )
        pixel_data = (
            crop.get_flattened_data()
            if hasattr(crop, "get_flattened_data")
            else crop.getdata()
        )
        colors = Counter(pixel_data).most_common(24)
        if not colors:
            continue
        dominant, dominant_count = colors[0]
        pixel_paths: list[str] = []
        if component_type == "Text":
            minimum_count = max(5, int(bounds["width"] * bounds["height"] * 0.001))
            foreground = next(
                (
                    color
                    for color, count in colors[1:]
                    if count >= minimum_count and color_distance(color, dominant) >= 24
                ),
                None,
            )
            if foreground is not None:
                component["style"]["typography"]["color"] = "#FF" + "".join(f"{channel:02X}" for channel in foreground)
                pixel_paths.append("style.typography.color")
        elif component_type == "TextField":
            surface = detect_text_field_surface(crop, dominant, density)
            if surface is not None:
                local_bounds = surface["bounds_px"]
                visual_bounds_px = {
                    "x": bounds["x"] + local_bounds["x"],
                    "y": bounds["y"] + local_bounds["y"],
                    "width": local_bounds["width"],
                    "height": local_bounds["height"],
                }
                component["visual_bounds_px"] = visual_bounds_px
                component["visual_bounds_dp"] = {
                    name: round(value / density, 3)
                    for name, value in visual_bounds_px.items()
                }
                component["style"]["surface"]["background"] = {
                    "type": "solid",
                    "color": surface["background"],
                }
                component["style"]["surface"]["border"] = surface["border"]
                component["style"]["surface"]["corner_radius_dp"] = surface["corner_radius_dp"]
                if surface["content_padding_dp"] is not None:
                    component["style"]["layout"]["padding_dp"] = surface["content_padding_dp"]
                pixel_paths.extend((
                    "style.surface.background",
                    "style.surface.border",
                    "style.surface.corner_radius_dp",
                ))
                if surface["content_padding_dp"] is not None:
                    pixel_paths.append("style.layout.padding_dp")
        elif (
            component_type == "Button" or component["style"]["state"].get("clickable") is True
        ) and dominant_count > bounds["width"] * bounds["height"] * 0.25:
            component["style"]["surface"]["background"] = {
                "type": "solid",
                "color": "#FF" + "".join(f"{channel:02X}" for channel in dominant),
            }
            matching_pixels: list[tuple[int, int]] = []
            pixels = crop.load()
            for y in range(crop.height):
                for x in range(crop.width):
                    if color_distance(pixels[x, y], dominant) <= 3:
                        matching_pixels.append((x, y))
            if matching_pixels:
                min_x = min(x for x, _ in matching_pixels)
                max_x = max(x for x, _ in matching_pixels)
                min_y = min(y for _, y in matching_pixels)
                max_y = max(y for _, y in matching_pixels)
                top_x = [x for x, y in matching_pixels if y == min_y]
                bottom_x = [x for x, y in matching_pixels if y == max_y]
                left_y = [y for x, y in matching_pixels if x == min_x]
                right_y = [y for x, y in matching_pixels if x == max_x]
                top_left = round(((min(top_x) - min_x) + (min(left_y) - min_y)) / 2 / density, 3)
                top_right = round(((max_x - max(top_x)) + (min(right_y) - min_y)) / 2 / density, 3)
                bottom_right = round(((max_x - max(bottom_x)) + (max_y - max(right_y))) / 2 / density, 3)
                bottom_left = round(((min(bottom_x) - min_x) + (max_y - max(left_y))) / 2 / density, 3)
                component["style"]["surface"]["corner_radius_dp"] = {
                    "top_left": top_left,
                    "top_right": top_right,
                    "bottom_right": bottom_right,
                    "bottom_left": bottom_left,
                }
                pixel_paths.append("style.surface.corner_radius_dp")
            pixel_paths.append("style.surface.background")
        elif dominant_count > bounds["width"] * bounds["height"] * 0.25:
            component["style"]["surface"]["background"] = {
                "type": "solid",
                "color": "#FF" + "".join(f"{channel:02X}" for channel in dominant),
            }
            pixel_paths.append("style.surface.background")
        if pixel_paths:
            component["pixel_provenance_paths"] = pixel_paths
            sampled += 1
    return {
        "available": True,
        "method": "component-bounded exact-color frequency and contrast sampling",
        "sampled_component_count": sampled,
    }


def source_runtime_type_compatible(source_type: str, runtime: dict[str, Any]) -> bool:
    runtime_kind = runtime["type"]
    if source_type in {"Text", "BasicText", "ClickableText"}:
        return runtime_kind == "Text"
    if source_type in {"Image", "Icon", "AsyncImage"}:
        return runtime_kind == "Image" or runtime.get("runtime_class") == "android.view.View"
    if source_type in {"Button", "IconButton", "FloatingActionButton", "SmallFloatingActionButton"}:
        return runtime_kind == "Button" or bool(runtime["style"]["state"]["clickable"])
    if source_type in {"TextField", "OutlinedTextField", "BasicTextField"}:
        return runtime_kind == "TextField"
    return runtime_kind not in {"Text", "Image", "TextField"}


def ancestors(component_id: str, runtime_by_id: dict[str, dict[str, Any]]) -> list[str]:
    result: list[str] = []
    current = runtime_by_id[component_id].get("parent_id")
    while isinstance(current, str) and current in runtime_by_id:
        result.append(current)
        current = runtime_by_id[current].get("parent_id")
    return result


def lowest_common_runtime_ancestor(
    component_ids: list[str], runtime_by_id: dict[str, dict[str, Any]]
) -> str | None:
    if not component_ids:
        return None
    chains = [[component_id] + ancestors(component_id, runtime_by_id) for component_id in component_ids]
    common = set(chains[0])
    for chain in chains[1:]:
        common.intersection_update(chain)
    return next((item for item in chains[0] if item in common), None)


def source_descendants(component_id: str, source_by_id: dict[str, dict[str, Any]]) -> list[str]:
    result: list[str] = []
    queue = list(source_by_id[component_id]["children_ids"])
    while queue:
        current = queue.pop(0)
        result.append(current)
        queue[0:0] = source_by_id[current]["children_ids"]
    return result


def tree_descendants(component_id: str, by_id: dict[str, dict[str, Any]]) -> list[str]:
    result: list[str] = []

    def visit(current: str) -> None:
        for child in by_id[current]["children_ids"]:
            result.append(child)
            visit(child)

    visit(component_id)
    return result


def semantic_source_component(component: dict[str, Any]) -> bool:
    return component["type"] in {
        "Text", "BasicText", "ClickableText", "Image", "Icon", "AsyncImage",
        "Button", "IconButton", "FloatingActionButton", "SmallFloatingActionButton", "TextField", "OutlinedTextField",
        "BasicTextField", "CheckBox", "Switch", "RadioButton",
    }


def runtime_semantic_key(component: dict[str, Any]) -> str | None:
    runtime_id = component.get("runtime_id")
    if isinstance(runtime_id, str) and runtime_id:
        return runtime_id
    resource_id = component.get("resource_id")
    if not isinstance(resource_id, str) or not resource_id or resource_id.startswith("android:id/"):
        return None
    return resource_id.rsplit("/", 1)[-1]


def expand_runtime_source_instances(
    source_components: list[dict[str, Any]],
    payload: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Expand one statically declared component definition into proven runtime instances."""
    if payload is None or not isinstance(payload, dict):
        return source_components, payload
    mappings = payload.get("mappings")
    if not isinstance(mappings, list):
        return source_components, payload

    source_by_semantic_key = {
        item["semantic_key"]: item
        for item in source_components
        if isinstance(item.get("semantic_key"), str)
        and isinstance(item.get("source"), dict)
    }
    definition_instances: dict[tuple[str, str], list[str]] = defaultdict(list)
    mapping_definitions: list[tuple[dict[str, Any], tuple[str, str] | None, str | None]] = []
    for mapping in mappings:
        if not isinstance(mapping, dict):
            mapping_definitions.append((mapping, None, None))
            continue
        instance_key = mapping.get("source_instance_key")
        if instance_key is not None and (
            not isinstance(instance_key, str)
            or re.fullmatch(r"[A-Za-z0-9._:@#-]{1,80}", instance_key) is None
        ):
            raise RealPageError("runtime source map source_instance_key is malformed")
        semantic_key = mapping.get("source_semantic_key")
        source = source_by_semantic_key.get(semantic_key) if isinstance(semantic_key, str) else None
        definition = None
        if source is not None:
            definition = (
                str(source["source"].get("source", "")),
                str(source["source"].get("composable", "")),
            )
            if instance_key is not None and instance_key not in definition_instances[definition]:
                definition_instances[definition].append(instance_key)
        mapping_definitions.append((mapping, definition, instance_key))
    if not definition_instances:
        return source_components, payload

    for _mapping, definition, instance_key in mapping_definitions:
        if definition in definition_instances and instance_key is None:
            raise RealPageError(
                "runtime source map must provide source_instance_key for every mapping from an instanced definition"
            )

    components_by_definition: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for component in source_components:
        source = component.get("source")
        if not isinstance(source, dict):
            continue
        definition = (str(source.get("source", "")), str(source.get("composable", "")))
        components_by_definition[definition].append(component)

    clone_keys: dict[tuple[str, str, str], dict[str, tuple[str, str]]] = {}
    expanded_components: list[dict[str, Any]] = []
    emitted_definitions: set[tuple[str, str]] = set()
    for component in source_components:
        source = component.get("source")
        definition = (
            str(source.get("source", "")), str(source.get("composable", ""))
        ) if isinstance(source, dict) else ("", "")
        instances = definition_instances.get(definition)
        if not instances:
            expanded_components.append(component)
            continue
        if definition in emitted_definitions:
            continue
        emitted_definitions.add(definition)
        definition_components = components_by_definition[definition]
        for instance_key in instances:
            ids = {
                item["id"]: source_component_id(
                    f"runtime-instance:{instance_key}", str(item["source"]["call_id"])
                )
                for item in definition_components
            }
            semantic_keys = {
                item["semantic_key"]: f"{item['semantic_key']}__instance_{instance_key}"
                for item in definition_components
            }
            if any(len(value) > 120 for value in semantic_keys.values()):
                raise RealPageError("runtime source map expanded semantic key exceeds 120 characters")
            clone_keys[(definition[0], definition[1], instance_key)] = {
                base: (ids[item["id"]], semantic_keys[base])
                for base, item in (
                    (candidate["semantic_key"], candidate) for candidate in definition_components
                )
            }
            for item in definition_components:
                clone = copy.deepcopy(item)
                clone["id"] = ids[item["id"]]
                clone["semantic_key"] = semantic_keys[item["semantic_key"]]
                parent_id = item.get("parent_id")
                clone["parent_id"] = ids.get(parent_id, parent_id)
                clone["children_ids"] = [ids.get(child_id, child_id) for child_id in item["children_ids"]]
                expanded_components.append(clone)

    replacement_children: dict[str, list[str]] = defaultdict(list)
    for definition, instances in definition_instances.items():
        for item in components_by_definition[definition]:
            replacement_children[item["id"]] = [
                clone_keys[(definition[0], definition[1], instance_key)][item["semantic_key"]][0]
                for instance_key in instances
            ]
    for component in expanded_components:
        children: list[str] = []
        for child_id in component["children_ids"]:
            children.extend(replacement_children.get(child_id, [child_id]))
        component["children_ids"] = children

    normalized_payload = copy.deepcopy(payload)
    normalized_mappings: list[Any] = []
    for mapping, definition, instance_key in mapping_definitions:
        normalized = copy.deepcopy(mapping)
        if isinstance(normalized, dict) and instance_key is not None and definition is not None:
            base_semantic_key = normalized["source_semantic_key"]
            clone = clone_keys[(definition[0], definition[1], instance_key)].get(base_semantic_key)
            if clone is None:
                raise RealPageError(
                    f"runtime source map cannot expand source_semantic_key: {base_semantic_key}"
                )
            normalized["source_semantic_key"] = clone[1]
            normalized.pop("source_instance_key", None)
        normalized_mappings.append(normalized)
    normalized_payload["mappings"] = normalized_mappings

    for field in (
        "inactive_source_components",
        "runtime_elided_source_components",
        "resolved_source_facts",
    ):
        entries = normalized_payload.get(field)
        if not isinstance(entries, list):
            continue
        expanded_entries: list[Any] = []
        for entry in entries:
            semantic_key = entry.get("source_semantic_key") if isinstance(entry, dict) else None
            source = source_by_semantic_key.get(semantic_key) if isinstance(semantic_key, str) else None
            if source is None:
                expanded_entries.append(entry)
                continue
            definition = (
                str(source["source"].get("source", "")),
                str(source["source"].get("composable", "")),
            )
            instances = definition_instances.get(definition)
            if not instances:
                expanded_entries.append(entry)
                continue
            for instance_key in instances:
                clone = copy.deepcopy(entry)
                clone["source_semantic_key"] = clone_keys[
                    (definition[0], definition[1], instance_key)
                ][semantic_key][1]
                expanded_entries.append(clone)
        normalized_payload[field] = expanded_entries
    return expanded_components, normalized_payload


def resolve_runtime_source_map(
    payload: dict[str, Any] | None,
    platform: str,
    page: dict[str, Any],
    source_components: list[dict[str, Any]],
    runtime_components: list[dict[str, Any]],
    runtime_tree_sha256: str | None,
) -> tuple[
    dict[str, str],
    set[str],
    list[dict[str, str]],
    set[str],
    list[dict[str, str]],
    dict[str, list[dict[str, Any]]],
]:
    if payload is None:
        return {}, set(), [], set(), [], {}
    if not {"schema", "platform", "page", "mappings"}.issubset(payload) or not set(payload).issubset(
        {
            "schema", "platform", "page", "runtime_tree_sha256", "mappings",
            "inactive_source_components", "runtime_elided_source_components", "resolved_source_facts",
        }
    ):
        raise RealPageError("runtime source map contains unsupported or missing fields")
    if payload.get("schema") != RUNTIME_SOURCE_MAP_SCHEMA:
        raise RealPageError("runtime source map schema is unsupported")
    if payload.get("platform") != platform:
        raise RealPageError("runtime source map platform does not match the capture")
    if payload.get("page") != page:
        raise RealPageError("runtime source map page/state does not match the capture")
    mappings = payload.get("mappings")
    if not isinstance(mappings, list) or len(mappings) > 10000:
        raise RealPageError("runtime source map mappings must be a bounded list")
    bound_tree_sha256 = payload.get("runtime_tree_sha256")
    if bound_tree_sha256 is not None:
        if not isinstance(bound_tree_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", bound_tree_sha256):
            raise RealPageError("runtime source map runtime_tree_sha256 is malformed")
        if bound_tree_sha256 != runtime_tree_sha256:
            raise RealPageError("runtime source map runtime tree SHA-256 does not match the capture")
    source_by_semantic_key = {
        item["semantic_key"]: item
        for item in source_components
        if isinstance(item.get("source"), dict)
        and isinstance(item["source"].get("call_id"), str)
        and isinstance(item.get("semantic_key"), str)
    }
    inactive_entries = payload.get("inactive_source_components", [])
    if not isinstance(inactive_entries, list) or len(inactive_entries) > 10000:
        raise RealPageError("runtime source map inactive_source_components must be a bounded list")
    inactive_source_ids: set[str] = set()
    normalized_inactive_entries: list[dict[str, str]] = []
    used_inactive_keys: set[str] = set()
    for entry in inactive_entries:
        if not isinstance(entry, dict) or set(entry) != {
            "source_semantic_key", "source_call_id", "reason"
        }:
            raise RealPageError("inactive source entry fields are invalid")
        semantic_key = entry.get("source_semantic_key")
        call_id = entry.get("source_call_id")
        reason = entry.get("reason")
        if (
            not isinstance(semantic_key, str)
            or not semantic_key
            or not isinstance(call_id, str)
            or not call_id
            or reason != "inactive_source_branch"
        ):
            raise RealPageError("inactive source entry values are invalid")
        if semantic_key in used_inactive_keys:
            raise RealPageError(f"runtime source map repeats inactive source_semantic_key: {semantic_key}")
        source = source_by_semantic_key.get(semantic_key)
        if source is None:
            raise RealPageError(f"runtime source map references unknown inactive source_semantic_key: {semantic_key}")
        if source["source"]["call_id"] != call_id:
            raise RealPageError(
                f"runtime source map inactive source_call_id does not match source_semantic_key: {semantic_key}"
            )
        inactive_source_ids.add(source["id"])
        used_inactive_keys.add(semantic_key)
        normalized_inactive_entries.append({
            "source_semantic_key": semantic_key,
            "source_call_id": call_id,
            "reason": reason,
        })
    elided_entries = payload.get("runtime_elided_source_components", [])
    if not isinstance(elided_entries, list) or len(elided_entries) > 10000:
        raise RealPageError("runtime source map runtime_elided_source_components must be a bounded list")
    elided_source_ids: set[str] = set()
    normalized_elided_entries: list[dict[str, str]] = []
    used_elided_keys: set[str] = set()
    for entry in elided_entries:
        if not isinstance(entry, dict) or set(entry) != {
            "source_semantic_key", "source_call_id", "reason"
        }:
            raise RealPageError("runtime-elided source entry fields are invalid")
        semantic_key = entry.get("source_semantic_key")
        call_id = entry.get("source_call_id")
        reason = entry.get("reason")
        if (
            not isinstance(semantic_key, str)
            or not semantic_key
            or not isinstance(call_id, str)
            or not call_id
            or reason not in {
                "runtime_nonsemantic_layout_elision",
                "runtime_flattened_semantic_descendant",
            }
        ):
            raise RealPageError("runtime-elided source entry values are invalid")
        if semantic_key in used_elided_keys:
            raise RealPageError(f"runtime source map repeats runtime-elided source_semantic_key: {semantic_key}")
        source = source_by_semantic_key.get(semantic_key)
        if source is None:
            raise RealPageError(f"runtime source map references unknown runtime-elided source_semantic_key: {semantic_key}")
        if source["source"]["call_id"] != call_id:
            raise RealPageError(
                f"runtime source map runtime-elided source_call_id does not match source_semantic_key: {semantic_key}"
            )
        is_semantic = semantic_source_component(source)
        is_clickable = source["style"]["state"].get("clickable") is True
        if reason == "runtime_nonsemantic_layout_elision" and (is_semantic or is_clickable):
            raise RealPageError(
                f"runtime source map cannot nonsemantically elide a semantic or clickable source component: {semantic_key}"
            )
        if reason == "runtime_flattened_semantic_descendant":
            if not is_semantic or is_clickable:
                raise RealPageError(
                    f"runtime source map can flatten only a non-clickable semantic descendant: {semantic_key}"
                )
            mapped_semantic_keys = {
                mapping.get("source_semantic_key")
                for mapping in payload["mappings"]
                if isinstance(mapping, dict)
            }
            source_by_id = {item["id"]: item for item in source_components}
            parent_id = source.get("parent_id")
            has_mapped_ancestor = False
            while isinstance(parent_id, str) and parent_id in source_by_id:
                parent = source_by_id[parent_id]
                if parent.get("semantic_key") in mapped_semantic_keys:
                    has_mapped_ancestor = True
                    break
                parent_id = parent.get("parent_id")
            if not has_mapped_ancestor:
                raise RealPageError(
                    f"runtime source map flattened semantic component has no explicitly mapped ancestor: {semantic_key}"
                )
        if source["id"] in inactive_source_ids:
            raise RealPageError(
                f"runtime source map cannot mark a source component both inactive and runtime-elided: {semantic_key}"
            )
        elided_source_ids.add(source["id"])
        used_elided_keys.add(semantic_key)
        normalized_elided_entries.append({
            "source_semantic_key": semantic_key,
            "source_call_id": call_id,
            "reason": reason,
        })
    fact_entries = payload.get("resolved_source_facts", [])
    if not isinstance(fact_entries, list) or len(fact_entries) > 10000:
        raise RealPageError("runtime source map resolved_source_facts must be a bounded list")
    resolved_source_facts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    used_fact_paths: set[tuple[str, str]] = set()
    for fact in fact_entries:
        if not isinstance(fact, dict) or set(fact) != {
            "source_semantic_key", "source_call_id", "path", "value", "origin", "source"
        }:
            raise RealPageError("resolved source fact fields are invalid")
        semantic_key = fact.get("source_semantic_key")
        call_id = fact.get("source_call_id")
        path = fact.get("path")
        value = fact.get("value")
        origin = fact.get("origin")
        evidence_source = fact.get("source")
        if (
            not isinstance(semantic_key, str)
            or not semantic_key
            or not isinstance(call_id, str)
            or not call_id
            or path not in {"style.asset.resource", "style.asset.sha256"}
            or origin != "source_resolved"
            or not isinstance(evidence_source, str)
            or not evidence_source
            or evidence_source.startswith("/")
            or ".." in Path(evidence_source).parts
        ):
            raise RealPageError("resolved source fact values are invalid")
        if path == "style.asset.resource" and (
            not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]+", value)
        ):
            raise RealPageError("resolved asset resource fact is malformed")
        if path == "style.asset.sha256" and (
            not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
        ):
            raise RealPageError("resolved asset SHA-256 fact is malformed")
        source = source_by_semantic_key.get(semantic_key)
        if source is None:
            raise RealPageError(f"runtime source map references unknown resolved source_semantic_key: {semantic_key}")
        if source["source"]["call_id"] != call_id:
            raise RealPageError(
                f"runtime source map resolved source_call_id does not match source_semantic_key: {semantic_key}"
            )
        fact_key = (semantic_key, str(path))
        if fact_key in used_fact_paths:
            raise RealPageError(f"runtime source map repeats resolved source fact: {semantic_key} {path}")
        used_fact_paths.add(fact_key)
        resolved_source_facts[source["id"]].append({
            "path": path,
            "value": value,
            "origin": origin,
            "source": evidence_source,
        })
    runtime_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    runtime_by_component_id = {component["id"]: component for component in runtime_components}
    for component in runtime_components:
        runtime_id = runtime_semantic_key(component)
        if isinstance(runtime_id, str):
            runtime_by_key[runtime_id].append(component)
    source_to_runtime: dict[str, str] = {}
    used_runtime_selectors: set[tuple[str, str]] = set()
    used_runtime_component_ids: set[str] = set()
    used_source_semantic_keys: set[str] = set()
    for mapping in mappings:
        if not isinstance(mapping, dict):
            raise RealPageError(
                "runtime source map entry must be an object"
            )
        selector_fields = {field for field in ("runtime_id", "runtime_component_id") if field in mapping}
        if (
            len(selector_fields) != 1
            or set(mapping) != selector_fields | {"source_semantic_key", "source_call_id"}
        ):
            raise RealPageError(
                "runtime source map entry must contain one runtime selector plus source_semantic_key and source_call_id"
            )
        selector_field = next(iter(selector_fields))
        runtime_selector = mapping.get(selector_field)
        source_semantic_key = mapping.get("source_semantic_key")
        source_call_id = mapping.get("source_call_id")
        if (
            not isinstance(runtime_selector, str) or not runtime_selector
            or not isinstance(source_semantic_key, str) or not source_semantic_key
            or not isinstance(source_call_id, str) or not source_call_id
        ):
            raise RealPageError("runtime source map entry IDs must be non-empty strings")
        selector = (selector_field, runtime_selector)
        if selector in used_runtime_selectors:
            raise RealPageError(f"runtime source map repeats {selector_field}: {runtime_selector}")
        if source_semantic_key in used_source_semantic_keys:
            raise RealPageError(f"runtime source map repeats source_semantic_key: {source_semantic_key}")
        if selector_field == "runtime_component_id":
            if bound_tree_sha256 is None:
                raise RealPageError("runtime_component_id mappings require runtime_tree_sha256")
            runtime = runtime_by_component_id.get(runtime_selector)
            if runtime is None:
                raise RealPageError(
                    f"runtime source map references unknown runtime_component_id: {runtime_selector}"
                )
        else:
            runtime_matches = runtime_by_key.get(runtime_selector, [])
            if not runtime_matches:
                raise RealPageError(f"runtime source map references unknown runtime_id: {runtime_selector}")
            if len(runtime_matches) != 1:
                raise RealPageError(f"runtime source map references ambiguous runtime_id: {runtime_selector}")
            runtime = runtime_matches[0]
        if runtime["id"] in used_runtime_component_ids:
            raise RealPageError(f"runtime source map repeats runtime component: {runtime['id']}")
        source = source_by_semantic_key.get(source_semantic_key)
        if source is None:
            raise RealPageError(
                f"runtime source map references unknown source_semantic_key: {source_semantic_key}"
            )
        if source["source"]["call_id"] != source_call_id:
            raise RealPageError(
                f"runtime source map source_call_id does not match source_semantic_key: {source_semantic_key}"
            )
        if source["id"] in inactive_source_ids:
            raise RealPageError(
                f"runtime source map maps an inactive source component: {source_semantic_key}"
            )
        if source["id"] in elided_source_ids:
            raise RealPageError(
                f"runtime source map maps a runtime-elided source component: {source_semantic_key}"
            )
        if not source_runtime_type_compatible(source["type"], runtime):
            raise RealPageError(
                f"runtime source map type mismatch for {selector_field} {runtime_selector} and source_call_id {source_call_id}"
            )
        source_to_runtime[source["id"]] = runtime["id"]
        used_runtime_selectors.add(selector)
        used_runtime_component_ids.add(runtime["id"])
        used_source_semantic_keys.add(source_semantic_key)
    return (
        source_to_runtime,
        inactive_source_ids,
        normalized_inactive_entries,
        elided_source_ids,
        normalized_elided_entries,
        dict(resolved_source_facts),
    )


def semantic_runtime_component(component: dict[str, Any]) -> bool:
    content = component["style"]["content"]
    state = component["style"]["state"]
    has_semantic_content = any(
        content.get(field) for field in ("text", "placeholder", "content_description")
    )
    if component["type"] in {"Button", "ImageButton"}:
        return bool(runtime_semantic_key(component) or has_semantic_content or state.get("clickable"))
    return bool(
        runtime_semantic_key(component)
        or has_semantic_content
        or component["type"] in {"TextField", "Image", "CheckBox", "Switch", "RadioButton"}
    )


def match_source_to_runtime(
    source_components: list[dict[str, Any]],
    runtime_components: list[dict[str, Any]],
    explicit_source_to_runtime: dict[str, str] | None = None,
    excluded_source_ids: set[str] | None = None,
) -> tuple[dict[str, str], dict[str, int], set[str], dict[str, str]]:
    excluded_source_ids = excluded_source_ids or set()
    source_by_id = {item["id"]: item for item in source_components}
    runtime_by_id = {item["id"]: item for item in runtime_components}
    source_to_runtime = dict(explicit_source_to_runtime or {})
    used_runtime = set(source_to_runtime.values())
    mapping_methods = {source_id: "explicit_runtime_source_map" for source_id in source_to_runtime}
    checks = {
        "explicit_runtime_source_map_matches": len(source_to_runtime),
        "stable_runtime_id_matches": 0,
        "exact_text_matches": 0,
        "exact_content_description_matches": 0,
        "scoped_hierarchy_order_matches": 0,
        "ordered_text_field_matches": 0,
        "hierarchy_matches": 0,
    }

    source_by_semantic_key = {
        item["semantic_key"]: item
        for item in source_components
        if isinstance(item.get("semantic_key"), str)
    }
    for runtime in runtime_components:
        runtime_key = runtime_semantic_key(runtime)
        source = source_by_semantic_key.get(runtime_key) if isinstance(runtime_key, str) else None
        if source is None or source["id"] in source_to_runtime or source["id"] in excluded_source_ids:
            continue
        source_to_runtime[source["id"]] = runtime["id"]
        used_runtime.add(runtime["id"])
        mapping_methods[source["id"]] = "stable_runtime_id"
        checks["stable_runtime_id_matches"] += 1

    def choose_unique(source: dict[str, Any], field: str) -> str | None:
        value = source["style"]["content"].get(field)
        if not isinstance(value, str):
            return None
        candidates = [
            runtime
            for runtime in runtime_components
            if runtime["id"] not in used_runtime
            and runtime["style"]["content"].get(field) == value
            and source_runtime_type_compatible(source["type"], runtime)
        ]
        return candidates[0]["id"] if len(candidates) == 1 else None

    for field, counter in (("text", "exact_text_matches"), ("content_description", "exact_content_description_matches")):
        for source in source_components:
            if (
                source["id"] in source_to_runtime
                or source["id"] in excluded_source_ids
                or source["source"]["custom_component"]
            ):
                continue
            runtime_id = choose_unique(source, field)
            if runtime_id is not None:
                source_to_runtime[source["id"]] = runtime_id
                used_runtime.add(runtime_id)
                mapping_methods[source["id"]] = f"exact_{field}"
                checks[counter] += 1

    def nearest_mapped_ancestor(
        component_id: str,
        by_id: dict[str, dict[str, Any]],
        mapped_ids: set[str],
    ) -> str | None:
        current = by_id[component_id].get("parent_id")
        while isinstance(current, str) and current in by_id:
            if current in mapped_ids:
                return current
            current = by_id[current].get("parent_id")
        return None

    # Generated ArkUI exposes stable IDs on major boundaries. Dynamic labels and text fields
    # inside those boundaries often have no ID, so bind them by compatible preorder without
    # crossing another already-mapped source/runtime boundary.
    mapped_source_ids = set(source_to_runtime)
    mapped_runtime_ids = set(source_to_runtime.values())
    source_preorder = {
        parent_id: tree_descendants(parent_id, source_by_id)
        for parent_id in mapped_source_ids
    }
    runtime_preorder = {
        parent_id: tree_descendants(parent_id, runtime_by_id)
        for parent_id in mapped_runtime_ids
    }
    source_depths = {
        component_id: len(ancestors(component_id, source_by_id))
        for component_id in mapped_source_ids
    }
    for source_parent_id in sorted(mapped_source_ids, key=source_depths.get, reverse=True):
        runtime_parent_id = source_to_runtime[source_parent_id]
        source_candidates = [
            source_by_id[item]
            for item in source_preorder[source_parent_id]
            if item not in source_to_runtime
            and item not in excluded_source_ids
            and nearest_mapped_ancestor(item, source_by_id, mapped_source_ids) == source_parent_id
            and not source_by_id[item]["source"]["custom_component"]
            and semantic_source_component(source_by_id[item])
        ]
        runtime_candidates = [
            runtime_by_id[item]
            for item in runtime_preorder[runtime_parent_id]
            if item not in used_runtime
            and nearest_mapped_ancestor(item, runtime_by_id, mapped_runtime_ids) == runtime_parent_id
            and semantic_runtime_component(runtime_by_id[item])
        ]
        cursor = 0
        for runtime in runtime_candidates:
            matched_index: int | None = None
            for index in range(cursor, len(source_candidates)):
                source = source_candidates[index]
                if not source_runtime_type_compatible(source["type"], runtime):
                    continue
                source_text = source["style"]["content"].get("text")
                runtime_text = runtime["style"]["content"].get("text")
                if isinstance(source_text, str) and isinstance(runtime_text, str) and source_text != runtime_text:
                    continue
                matched_index = index
                break
            if matched_index is None:
                continue
            source = source_candidates[matched_index]
            source_to_runtime[source["id"]] = runtime["id"]
            used_runtime.add(runtime["id"])
            mapping_methods[source["id"]] = "scoped_hierarchy_order"
            checks["scoped_hierarchy_order_matches"] += 1
            cursor = matched_index + 1

    remaining_text_fields = [
        source
        for source in source_components
        if source["id"] not in source_to_runtime
        and source["id"] not in excluded_source_ids
        and not source["source"]["custom_component"]
        and source["type"] in {"TextField", "OutlinedTextField", "BasicTextField"}
    ]
    remaining_runtime_text_fields = [
        runtime
        for runtime in runtime_components
        if runtime["id"] not in used_runtime and runtime["type"] == "TextField"
    ]
    if len(remaining_text_fields) == len(remaining_runtime_text_fields):
        for source, runtime in zip(remaining_text_fields, remaining_runtime_text_fields, strict=True):
            source_to_runtime[source["id"]] = runtime["id"]
            used_runtime.add(runtime["id"])
            mapping_methods[source["id"]] = "ordered_text_field"
            checks["ordered_text_field_matches"] += 1

    active_definitions = {
        (source_by_id[source_id]["source"]["source"], source_by_id[source_id]["source"]["composable"])
        for source_id in source_to_runtime
    }
    for source in source_components:
        source_id = source["id"]
        definition = (source["source"]["source"], source["source"]["composable"])
        if (
            source_id in source_to_runtime
            or source_id in excluded_source_ids
            or source["source"]["custom_component"]
            or definition not in active_definitions
        ):
            continue
        candidates = [
            runtime
            for runtime in runtime_components
            if runtime["id"] not in used_runtime and source_runtime_type_compatible(source["type"], runtime)
        ]
        remaining_same_type = [
            item
            for item in source_components
            if (item["source"]["source"], item["source"]["composable"]) == definition
            and not item["source"]["custom_component"]
            and item["type"] == source["type"]
            and item["id"] not in source_to_runtime
            and item["id"] not in excluded_source_ids
        ]
        if len(candidates) == len(remaining_same_type) == 1:
            source_to_runtime[source_id] = candidates[0]["id"]
            used_runtime.add(candidates[0]["id"])
            mapping_methods[source_id] = "single_remaining_type"

    depth_cache: dict[str, int] = {}

    def source_depth(component_id: str) -> int:
        if component_id in depth_cache:
            return depth_cache[component_id]
        parent = source_by_id[component_id]["parent_id"]
        depth_cache[component_id] = 0 if parent is None else source_depth(parent) + 1
        return depth_cache[component_id]

    changed = True
    while changed:
        changed = False
        for source in sorted(source_components, key=lambda item: source_depth(item["id"]), reverse=True):
            source_id = source["id"]
            if (
                source_id in source_to_runtime
                or source_id in excluded_source_ids
                or source["source"]["custom_component"]
            ):
                continue
            mapped_descendants = [
                source_to_runtime[item]
                for item in source_descendants(source_id, source_by_id)
                if item in source_to_runtime
            ]
            if not mapped_descendants:
                continue
            candidate_id = lowest_common_runtime_ancestor(mapped_descendants, runtime_by_id)
            if candidate_id in mapped_descendants:
                candidate_id = runtime_by_id[candidate_id].get("parent_id")
            if (
                candidate_id is not None
                and candidate_id not in used_runtime
                and source_runtime_type_compatible(source["type"], runtime_by_id[candidate_id])
            ):
                source_to_runtime[source_id] = candidate_id
                used_runtime.add(candidate_id)
                mapping_methods[source_id] = "hierarchy_common_ancestor"
                checks["hierarchy_matches"] += 1
                changed = True

    active_definitions = {
        (source_by_id[source_id]["source"]["source"], source_by_id[source_id]["source"]["composable"])
        for source_id in source_to_runtime
    }
    roots = [item for item in source_components if item["parent_id"] is None]
    active_definitions.update(
        (item["source"]["source"], item["source"]["composable"]) for item in roots
    )
    active_definitions.update(
        (source_by_id[source_id]["source"]["source"], source_by_id[source_id]["source"]["composable"])
        for source_id in source_to_runtime
    )
    return source_to_runtime, checks, active_definitions, mapping_methods


def merge_style(source_style: dict[str, Any], runtime_style: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(source_style)
    for section in result:
        for field, value in runtime_style[section].items():
            if value is not None:
                result[section][field] = value
    return result


def path_value(style: dict[str, Any], path: str) -> Any:
    value: Any = style
    for part in path.split(".")[1:]:
        value = value.get(part) if isinstance(value, dict) else None
    return value


def set_path_value(style: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    if len(parts) != 3 or parts[0] != "style" or not isinstance(style.get(parts[1]), dict):
        raise RealPageError(f"resolved source fact path is unsupported: {path}")
    style[parts[1]][parts[2]] = value


def required_visual_paths(component: dict[str, Any]) -> list[str]:
    kind = component["type"]
    if kind in {"Text", "BasicText", "ClickableText"}:
        return ["style.content.text", "style.typography.font_size_sp", "style.typography.color"]
    if kind in {"Image", "Icon", "AsyncImage"}:
        return ["style.asset.resource", "style.asset.content_scale"]
    if kind in {"Button", "IconButton", "FloatingActionButton", "SmallFloatingActionButton"}:
        return ["style.state.clickable", "style.surface.background", "style.surface.corner_radius_dp"]
    return []


def dp_bounds(bounds: dict[str, int], density: float) -> dict[str, float]:
    return {name: round(value / density, 3) for name, value in bounds.items()}


def build_runtime_page_snapshot(
    source_spec: dict[str, Any],
    runtime_components: list[dict[str, Any]],
    screenshot_path: Path,
    screenshot_sha256: str,
    screenshot_byte_count: int,
    dimensions: tuple[int, int],
    density: float,
    font_scale: float,
    insets_px: dict[str, int],
    device: dict[str, str],
    timings_ms: dict[str, float],
    platform: str = "android",
    runtime_origin: str = "UIAutomator hierarchy from bound capture",
    runtime_source_map: dict[str, Any] | None = None,
    runtime_source_map_sha256: str | None = None,
    runtime_tree_sha256: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if platform not in {"android", "harmony"}:
        raise RealPageError("platform must be android or harmony")
    source_components, runtime_source_map = expand_runtime_source_instances(
        source_spec["components"], runtime_source_map
    )
    source_by_id = {item["id"]: item for item in source_components}
    (
        explicit_source_to_runtime,
        inactive_source_ids,
        inactive_source_entries,
        elided_source_ids,
        elided_source_entries,
        resolved_source_facts,
    ) = resolve_runtime_source_map(
        runtime_source_map,
        platform,
        source_spec["page"],
        source_components,
        runtime_components,
        runtime_tree_sha256,
    )
    source_to_runtime, checks, active_definitions, mapping_methods = match_source_to_runtime(
        source_components,
        runtime_components,
        explicit_source_to_runtime,
        inactive_source_ids | elided_source_ids,
    )
    runtime_to_source = {runtime_id: source_id for source_id, runtime_id in source_to_runtime.items()}
    mapped_source_ids = set(source_to_runtime)

    def nearest_mapped_source_ancestor(source_id: str) -> str | None:
        parent_id = source_by_id[source_id]["parent_id"]
        while isinstance(parent_id, str) and parent_id in source_by_id:
            if parent_id in mapped_source_ids:
                return parent_id
            parent_id = source_by_id[parent_id]["parent_id"]
        return None

    mapped_parent_by_source = {
        source_id: nearest_mapped_source_ancestor(source_id) for source_id in mapped_source_ids
    }
    mapped_children_by_source: dict[str | None, list[str]] = defaultdict(list)
    for source in source_components:
        if source["id"] in mapped_source_ids:
            mapped_children_by_source[mapped_parent_by_source[source["id"]]].append(source["id"])
    output_components: list[dict[str, Any]] = []
    for runtime in runtime_components:
        source = source_by_id.get(runtime_to_source.get(runtime["id"], ""))
        if source is None:
            continue
        runtime_style = copy.deepcopy(runtime["style"])
        pixel_provenance_paths = list(runtime.get("pixel_provenance_paths", []))
        if (
            source["type"] in {"Image", "Icon", "AsyncImage"}
            and runtime["type"] != "Image"
            and runtime.get("runtime_class") == "android.view.View"
        ):
            runtime_style["surface"]["background"] = None
            pixel_provenance_paths = [
                path for path in pixel_provenance_paths if not path.startswith("style.surface.background")
            ]
        if source["type"] in {"Checkbox", "CheckBox", "Switch", "RadioButton"}:
            runtime_style["surface"]["background"] = None
            runtime_style["surface"]["corner_radius_dp"] = None
            pixel_provenance_paths = [
                path
                for path in pixel_provenance_paths
                if path not in {"style.surface.background", "style.surface.corner_radius_dp"}
            ]
        merged_style = merge_style(source["style"], runtime_style)
        component_source_facts = resolved_source_facts.get(source["id"], [])
        for fact in component_source_facts:
            existing = path_value(merged_style, fact["path"])
            if existing is not None and existing != fact["value"]:
                raise RealPageError(
                    f"resolved source fact conflicts with existing value: {source['semantic_key']} {fact['path']}"
                )
            set_path_value(merged_style, fact["path"], fact["value"])
        source_unresolved = copy.deepcopy(source["unresolved"])
        source_unresolved = [
            unresolved
            for unresolved in source_unresolved
            if path_value(merged_style, str(unresolved.get("path", ""))) is None
        ]
        item = {
            "id": runtime["id"],
            "type": source["type"],
            "bounds_px": runtime["bounds_px"],
            "bounds_dp": dp_bounds(runtime["bounds_px"], density),
            "parent_id": (
                source_to_runtime[mapped_parent_by_source[source["id"]]]
                if mapped_parent_by_source[source["id"]] is not None
                else None
            ),
            "parent_mapping": "source-semantic-ancestor",
            "children_ids": [
                source_to_runtime[child_id] for child_id in mapped_children_by_source[source["id"]]
            ],
            "sibling_index": mapped_children_by_source[mapped_parent_by_source[source["id"]]].index(source["id"]),
            "style": merged_style,
            "provenance": copy.deepcopy(source["provenance"]),
            "unresolved": source_unresolved,
        }
        if isinstance(runtime.get("visual_bounds_px"), dict):
            item["visual_bounds_px"] = copy.deepcopy(runtime["visual_bounds_px"])
            item["visual_bounds_dp"] = copy.deepcopy(runtime["visual_bounds_dp"])
        runtime_paths = [
            "style.state.visible",
            "style.state.enabled",
            "style.state.selected",
            "style.state.checked",
            "style.state.clickable",
            "style.content.role",
        ]
        if runtime["style"]["content"]["text"] is not None:
            runtime_paths.append("style.content.text")
        if runtime["style"]["content"]["content_description"] is not None:
            runtime_paths.append("style.content.content_description")
        item["provenance"].append(
            {"paths": runtime_paths, "origin": "runtime", "source": runtime_origin}
        )
        if pixel_provenance_paths:
            item["provenance"].append(
                {
                    "paths": pixel_provenance_paths,
                    "origin": "pixel_sampled",
                    "source": "bound screenshot component crop",
                }
            )
        for fact in component_source_facts:
            item["provenance"].append({
                "paths": [fact["path"]],
                "origin": fact["origin"],
                "source": fact["source"],
            })
        item["semantic_key"] = source["semantic_key"]
        item["source_mapping"] = {
            "method": mapping_methods[source["id"]],
            "source_call_id": source["source"]["call_id"],
        }
        item["source"] = {
            "source": source["source"]["source"],
            "composable": source["source"]["composable"],
            "attributes": source["source"]["attributes"],
        }
        output_components.append(item)
    primitive_candidates = [
        item
        for item in source_components
        if not item["source"]["custom_component"]
        and item["type"] not in {"Surface", "Spacer"}
        and (item["source"]["source"], item["source"]["composable"]) in active_definitions
        and item["id"] not in inactive_source_ids
        and item["id"] not in elided_source_ids
    ]
    inactive_primitive = [
        item
        for item in source_components
        if item["id"] in inactive_source_ids
        and not item["source"]["custom_component"]
        and item["type"] not in {"Surface", "Spacer"}
    ]
    elided_primitive = [
        item
        for item in source_components
        if item["id"] in elided_source_ids
        and not item["source"]["custom_component"]
        and item["type"] not in {"Surface", "Spacer"}
    ]
    mapped_primitive = [item for item in primitive_candidates if item["id"] in source_to_runtime]
    proven_methods = {"stable_runtime_id", "explicit_runtime_source_map"}
    proven_mapped_primitive = [
        item for item in mapped_primitive if mapping_methods.get(item["id"]) in proven_methods
    ]
    output_by_runtime_id = {item["id"]: item for item in output_components}
    unmatched = [item["semantic_key"] for item in primitive_candidates if item["id"] not in source_to_runtime]
    semantic_runtime = [item for item in runtime_components if semantic_runtime_component(item)]
    mapped_runtime_ids = set(source_to_runtime.values())
    mapped_semantic_runtime = [item for item in semantic_runtime if item["id"] in mapped_runtime_ids]
    proven_runtime_ids = {
        runtime_id
        for source_id, runtime_id in source_to_runtime.items()
        if mapping_methods.get(source_id) in proven_methods
    }
    proven_mapped_semantic_runtime = [item for item in semantic_runtime if item["id"] in proven_runtime_ids]
    semantic_runtime_ratio = (
        round(len(mapped_semantic_runtime) / len(semantic_runtime), 6)
        if semantic_runtime
        else 1.0
    )
    proven_semantic_runtime_ratio = (
        round(len(proven_mapped_semantic_runtime) / len(semantic_runtime), 6)
        if semantic_runtime
        else 1.0
    )
    unmapped_runtime_semantic_ids = [
        str(runtime_semantic_key(item) or item["id"])
        for item in semantic_runtime
        if item["id"] not in mapped_runtime_ids
    ]
    content_x, content_y = insets_px["left"], insets_px["top"]
    content_width = dimensions[0] - insets_px["left"] - insets_px["right"]
    content_height = dimensions[1] - insets_px["top"] - insets_px["bottom"]
    viewport = {
        "width_px": dimensions[0],
        "height_px": dimensions[1],
        "density": density,
        "font_scale": font_scale,
        "orientation": "landscape" if dimensions[0] > dimensions[1] else "portrait",
        "width_dp": round(dimensions[0] / density, 3),
        "height_dp": round(dimensions[1] / density, 3),
        "insets_source": "explicit_or_device",
        "safe_area_px": insets_px,
        "safe_area_dp": {name: round(value / density, 3) for name, value in insets_px.items()},
        "content_bounds_px": {"x": content_x, "y": content_y, "width": content_width, "height": content_height},
        "content_bounds_dp": dp_bounds(
            {"x": content_x, "y": content_y, "width": content_width, "height": content_height}, density
        ),
    }
    snapshot = {
        "schema": PAGE_SCHEMA,
        "status": "candidate_requires_review",
        "authoritative": False,
        "platform": platform,
        "page": copy.deepcopy(source_spec["page"]),
        "viewport": viewport,
        "capture": {
            "screenshot": {
                "file": screenshot_path.name,
                "byte_count": screenshot_byte_count,
                "sha256": screenshot_sha256,
            },
            "device": device,
        },
        "input_hashes": {
            "source_page_spec_sha256": canonical_sha256(source_spec),
            **(
                {"runtime_source_map_sha256": runtime_source_map_sha256}
                if runtime_source_map_sha256 is not None
                else {}
            ),
            **({"runtime_tree_sha256": runtime_tree_sha256} if runtime_tree_sha256 is not None else {}),
        },
        "components": output_components,
        "inactive_source_components": inactive_source_entries,
        "runtime_elided_source_components": elided_source_entries,
        "unmapped_source_components": unmatched,
        "unmapped_visual_fact_components": [],
        "limitations": [
            "The raw runtime tree is retained separately; the page contains only source-mapped semantic components.",
            "Page hierarchy compresses unmapped platform wrappers to the nearest mapped source-semantic ancestor.",
            "Rendered typography, gradients, corner radii, and shadows remain unresolved unless source or instrumentation proves them.",
            "Conditional visibility is inferred from the captured state and exact content/hierarchy matches.",
        ],
    }
    ratio = round(len(mapped_primitive) / len(primitive_candidates), 6) if primitive_candidates else 1.0
    proven_ratio = (
        round(len(proven_mapped_primitive) / len(primitive_candidates), 6)
        if primitive_candidates
        else 1.0
    )
    unresolved_count = sum(
        len(output_by_runtime_id[source_to_runtime[item["id"]]]["unresolved"])
        for item in mapped_primitive
    )
    unresolved_required_paths = [
        {"component_id": item["id"], "type": item["type"], "path": path}
        for item in mapped_primitive
        for path in required_visual_paths(item)
        if path_value(output_by_runtime_id[source_to_runtime[item["id"]]]["style"], path) is None
    ]
    verdict = (
        "pass"
        if ratio == 1.0
        and proven_ratio == 1.0
        and semantic_runtime_ratio == 1.0
        and proven_semantic_runtime_ratio == 1.0
        and unresolved_count == 0
        and not unresolved_required_paths
        else "fail"
    )
    normalized_timings = {name: round(float(value), 3) for name, value in timings_ms.items()}
    normalized_timings["total"] = round(sum(normalized_timings.values()), 3)
    metrics = {
        "schema": "android-to-harmony.real-page-metrics.v1",
        "verdict": verdict,
        "page": copy.deepcopy(source_spec["page"]),
        "source": {
            "call_count": source_spec["coverage"]["source_call_count"],
            "emitted_call_count": source_spec["coverage"]["emitted_call_count"],
            "emitted_call_ratio": source_spec["coverage"]["emitted_call_ratio"],
            "primitive_visible_candidate_count": len(primitive_candidates),
            "inactive_primitive_count": len(inactive_primitive),
            "runtime_elided_primitive_count": len(elided_primitive),
            "primitive_mapped_count": len(mapped_primitive),
            "primitive_mapping_ratio": ratio,
            "proven_primitive_mapping_count": len(proven_mapped_primitive),
            "proven_primitive_mapping_ratio": proven_ratio,
            "unmapped_primitive_ids": unmatched,
            "mapped_unresolved_fact_count": unresolved_count,
            "unresolved_required_visual_fact_count": len(unresolved_required_paths),
            "unresolved_required_visual_facts": unresolved_required_paths,
        },
        "runtime": {
            "component_count": len(runtime_components),
            "source_mapped_count": len(source_to_runtime),
            "source_mapped_ratio": round(len(source_to_runtime) / len(runtime_components), 6) if runtime_components else 1.0,
            "semantic_component_count": len(semantic_runtime),
            "semantic_mapped_count": len(mapped_semantic_runtime),
            "semantic_mapping_ratio": semantic_runtime_ratio,
            "proven_semantic_mapping_count": len(proven_mapped_semantic_runtime),
            "proven_semantic_mapping_ratio": proven_semantic_runtime_ratio,
            "unmapped_semantic_ids": unmapped_runtime_semantic_ids,
            "tree_parent_count": sum(item["parent_id"] is not None for item in runtime_components),
        },
        "checks": checks,
        "timings_ms": normalized_timings,
        "claims": {
            "source_call_inventory_complete": source_spec["coverage"]["emitted_call_ratio"] == 1.0,
            "visible_primitive_mapping_complete": ratio == 1.0,
            "visible_primitive_mapping_independently_proven": proven_ratio == 1.0,
            "runtime_semantic_mapping_complete": semantic_runtime_ratio == 1.0,
            "runtime_semantic_mapping_independently_proven": proven_semantic_runtime_ratio == 1.0,
            "all_visual_styles_resolved": unresolved_count == 0 and not unresolved_required_paths,
        },
    }
    return snapshot, metrics
