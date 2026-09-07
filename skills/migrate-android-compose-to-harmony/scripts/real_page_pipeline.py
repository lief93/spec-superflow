#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections import Counter
from pathlib import Path
from typing import Any

from generate_source_attribute_inventory import call_attributes
from generate_harmony_theme_resources import MATERIAL3_LIGHT_COLOR_DEFAULTS, color_from_semantics
from component_required_facts import (
    size_arguments,
    build_required_facts,
    is_preview_only_placeholder_expression,
    normalized_layout_rules,
    numeric_literal,
    parsed_arguments,
    font_weight_expression,
    number_expression,
    simple_appbar_background,
    INPUT_TYPES, INPUT_ARGUMENTS, input_argument_values,
    constant_linear_gradient, constant_corner_radius,
    required_fact_gate,
)
from page_snapshot import empty_style


SOURCE_PAGE_SCHEMA = "android-to-harmony.source-page-spec.v1"
PAGE_SCHEMA = "android-to-harmony.page-snapshot.v2"
RUNTIME_SOURCE_MAP_SCHEMA = "android-to-harmony.runtime-source-map.v1"
SOURCE_COMPONENT_TREE_SCHEMA = "android-to-harmony.source-component-tree.v2"
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

SOURCE_LAYOUT_PRIMITIVES = {
    "Box",
    "BoxWithConstraints",
    "Column",
    "ConstraintLayout",
    "FlowColumn",
    "FlowRow",
    "LazyColumn",
    "LazyHorizontalGrid",
    "LazyRow",
    "LazyVerticalGrid",
    "ListItem",
    "Row",
    "Scaffold",
    "Spacer",
    "Surface",
}

COMPOSE_FRAMEWORK_PREFIXES = (
    "androidx.compose.",
    "androidx.constraintlayout.compose.",
)
PLATFORM_COMPONENT_IMPORT_MARKERS = (
    ".viewinterop.",
    ".interop.",
)


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


def definition_id(*parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:20]
    return f"definition-{digest}"


def kotlin_source_metadata(
    source_root: Path | None,
    relative_source: str,
    cache: dict[str, tuple[str | None, dict[str, str]]],
) -> tuple[str | None, dict[str, str]]:
    cached = cache.get(relative_source)
    if cached is not None:
        return cached
    package_name: str | None = None
    imports: dict[str, str] = {}
    if source_root is not None:
        path = source_root / relative_source
        if path.is_file() and not path.is_symlink() and path.suffix in {".kt", ".kts"}:
            text = path.read_text(encoding="utf-8")
            package_match = re.search(r"(?m)^\s*package\s+([A-Za-z_][A-Za-z0-9_.]*)", text)
            if package_match is not None:
                package_name = package_match.group(1)
            for match in re.finditer(
                r"(?m)^\s*import\s+([A-Za-z_][A-Za-z0-9_.]*)(?:\s+as\s+([A-Za-z_][A-Za-z0-9_]*))?\s*$",
                text,
            ):
                qualified_name, alias = match.groups()
                imports[alias or qualified_name.rsplit(".", 1)[-1]] = qualified_name
    result = (package_name, imports)
    cache[relative_source] = result
    return result


def component_definition(
    call: dict[str, Any],
    source_root: Path | None,
    metadata_cache: dict[str, tuple[str | None, dict[str, str]]],
) -> dict[str, Any]:
    component = str(call.get("component", "View"))
    source = str(call.get("source", ""))
    containing_composable = str(call.get("composable", ""))
    package_name, imports = kotlin_source_metadata(source_root, source, metadata_cache)
    custom = call.get("custom_composable")
    definitions = custom.get("definitions") if isinstance(custom, dict) else None
    target = definitions[0] if isinstance(definitions, list) and len(definitions) == 1 else None
    if isinstance(target, dict) and isinstance(target.get("source"), str) and isinstance(target.get("composable"), str):
        target_source = target["source"]
        target_composable = target["composable"]
        target_package, _target_imports = kotlin_source_metadata(
            source_root, target_source, metadata_cache
        )
        qualified_name = (
            f"{target_package}.{target_composable}" if target_package else target_composable
        )
        return {
            "id": definition_id("project_component", target_source, target_composable),
            "type": component,
            "component_kind": "project_component",
            "identity": {
                "status": "resolved_project_definition",
                "qualified_name": qualified_name,
                "source": target_source,
                "symbol": target_composable,
            },
            "dependency": None,
            "declared_from": {
                "source": source,
                "composable": containing_composable,
                "package": package_name,
            },
        }

    qualified_name = imports.get(component)
    if component == "Canvas":
        kind = "custom_draw"
    elif isinstance(qualified_name, str) and any(
        marker in qualified_name for marker in PLATFORM_COMPONENT_IMPORT_MARKERS
    ):
        kind = "platform_component"
    elif isinstance(qualified_name, str) and qualified_name.startswith(COMPOSE_FRAMEWORK_PREFIXES):
        kind = "compose_primitive"
    elif isinstance(qualified_name, str):
        kind = "third_party_component"
    else:
        kind = "compose_primitive"
    identity_status = "resolved_import" if qualified_name is not None else "inferred_primitive_name"
    stable_identity = qualified_name or component
    dependency = None
    if kind == "third_party_component":
        dependency = {
            "qualified_name": qualified_name,
            "package_root": ".".join(qualified_name.split(".")[:2]),
            "version": None,
            "version_status": "requires_resolved_dependency_graph",
        }
    return {
        "id": definition_id(kind, stable_identity),
        "type": component,
        "component_kind": kind,
        "identity": {
            "status": identity_status,
            "qualified_name": qualified_name,
            "source": None,
            "symbol": component,
        },
        "dependency": dependency,
        "declared_from": {
            "source": source,
            "composable": containing_composable,
            "package": package_name,
        },
    }


def kotlin_call_blocks(text: str) -> list[tuple[str, int, int, str]]:
    blocks: list[tuple[str, int, int, str]] = []
    for match in re.finditer(r"\b([A-Z][A-Za-z0-9_]*)\s*\(", text):
        open_index = text.find("(", match.start(), match.end())
        depth = 0
        quote: str | None = None
        escaped = False
        for index in range(open_index, min(len(text), open_index + 12000)):
            character = text[index]
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
                    blocks.append((match.group(1), match.start(), index + 1, text[open_index + 1:index]))
                    break
    return blocks


def runtime_asset_rules(
    source_root: Path | None,
    values: dict[tuple[str, str], str],
) -> list[dict[str, Any]]:
    if source_root is None or not source_root.is_dir() or source_root.is_symlink():
        return []

    rules: dict[tuple[str, str, str, str | None], dict[str, Any]] = {}
    available_symbols: set[str] = set()
    labeled_rule_models: set[str] = set()

    def asset(resource: str) -> dict[str, Any]:
        file = find_resource_file(source_root, resource)
        return {
            "resource": resource,
            "sha256": hashlib.sha256(file.read_bytes()).hexdigest() if file is not None else None,
        }

    for path in sorted(source_root.rglob("*.kt")):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            relative = path.relative_to(source_root).as_posix()
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError, ValueError):
            continue
        for available_match in re.finditer(
            r"\bavailable\s*=\s*listOf\s*\((.*?)\)", text, re.S
        ):
            available_symbols.update(
                re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)\b", available_match.group(1))
            )
        for call_name, start, _end, body in kotlin_call_blocks(text):
            line = text.count("\n", 0, start) + 1
            label_match = re.search(r"\blabel\s*=.*?R\.string\.([A-Za-z0-9_]+)", body, re.S)
            selected_match = re.search(r"\bselected\s*=\s*R\.(?:drawable|mipmap)\.([A-Za-z0-9_]+)", body)
            unselected_match = re.search(r"\bunselected\s*=\s*R\.(?:drawable|mipmap)\.([A-Za-z0-9_]+)", body)
            if label_match is not None and selected_match is not None and unselected_match is not None:
                label = values.get(("string", label_match.group(1)))
                if isinstance(label, str):
                    route_match = re.search(r"\broute\s*=\s*([A-Za-z_][A-Za-z0-9_.]*)", body)
                    route = route_match.group(1) if route_match is not None else None
                    key = ("navigation_item", label, unselected_match.group(1), selected_match.group(1))
                    rules[key] = {
                        "role": "navigation_item",
                        "label": label,
                        "model_type": call_name,
                        "asset": asset(unselected_match.group(1)),
                        "selected_asset": asset(selected_match.group(1)),
                        "route": route,
                        "source": {"source": relative, "line": line},
                    }

            title_match = re.search(r"\btitle\s*=\s*\"((?:[^\"\\]|\\.)*)\"", body)
            url_asset_match = re.search(
                r"(?:getMockImageUrl|drawableResource|imageResource)\s*\(\s*\"([a-z][a-z0-9_]*)\"\s*\)",
                body,
            )
            if title_match is not None and url_asset_match is not None:
                try:
                    label = json.loads(f'"{title_match.group(1)}"')
                except json.JSONDecodeError:
                    label = title_match.group(1)
                key = ("titled_asset_record", label, url_asset_match.group(1), None)
                rules[key] = {
                    "role": "titled_asset_record",
                    "label": label,
                    "model_type": call_name,
                    "asset": asset(url_asset_match.group(1)),
                    "selected_asset": None,
                    "route": None,
                    "source": {"source": relative, "line": line},
                }

            prefix = text[max(0, start - 160):start]
            object_match = re.search(
                r"\bobject\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*$",
                prefix,
            )
            drawable_match = re.search(r"R\.(?:drawable|mipmap)\.([A-Za-z0-9_]+)", body)
            string_match = re.search(r"R\.string\.([A-Za-z0-9_]+)", body)
            if object_match is not None and drawable_match is not None and string_match is not None:
                label = values.get(("string", string_match.group(1)))
                if isinstance(label, str):
                    model_symbol = f"{call_name}.{object_match.group(1)}"
                    labeled_rule_models.add(call_name)
                    key = ("labeled_asset_object", label, drawable_match.group(1), None)
                    rules[key] = {
                        "role": "labeled_asset_object",
                        "label": label,
                        "model_type": call_name,
                        "asset": asset(drawable_match.group(1)),
                        "selected_asset": None,
                        "route": None,
                        "model_symbol": model_symbol,
                        "source": {"source": relative, "line": line},
                    }
    for rule in rules.values():
        model_symbol = rule.get("model_symbol")
        if isinstance(model_symbol, str) and rule.get("model_type") in labeled_rule_models:
            rule["availability"] = (
                "available" if model_symbol in available_symbols else "unavailable"
            )
        else:
            rule["availability"] = "unknown"
        rule.pop("model_symbol", None)
    return sorted(rules.values(), key=lambda item: (item["role"], item["label"], item["source"]["source"]))


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


def bind_source_expression(
    expression: str,
    parameter_bindings: dict[str, str] | None,
) -> str:
    """Resolve a direct component parameter forwarding chain without evaluating Kotlin."""
    if not parameter_bindings:
        return expression
    current = expression.strip()
    visited: set[str] = set()
    for _ in range(16):
        match = re.fullmatch(
            r"([A-Za-z_][A-Za-z0-9_]*)(\.(?:asString\(\)|value))?",
            current,
        )
        if match is None:
            break
        name = match.group(1)
        replacement = parameter_bindings.get(name)
        if replacement is None or name in visited:
            break
        visited.add(name)
        current = replacement.strip() + (match.group(2) or '')
    return current


def resolved_dp_expression(
    expression: str,
    parameter_bindings: dict[str, str],
) -> float | None:
    candidate = expression.strip()
    sign = 1.0
    if candidate.startswith("-"):
        sign = -1.0
        candidate = candidate[1:].strip()
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", candidate):
        candidate = parameter_bindings.get(candidate, candidate).strip()
    candidate = candidate.strip("() ")
    match = re.fullmatch(r"(-?[0-9]+(?:\.[0-9]+)?)\.dp", candidate)
    return sign * float(match.group(1)) if match is not None else None


def resolved_shadow_elevation(
    expression: str,
    parameter_bindings: dict[str, str] | None,
) -> float | None:
    if re.search(r"(?:shadow|elevation)", expression, re.IGNORECASE) is None:
        return None
    value_pattern = r"(-?[0-9]+(?:\.[0-9]+)?\.dp|[A-Za-z_][A-Za-z0-9_]*)"
    patterns = [rf"\belevation\s*=\s*{value_pattern}"]
    if re.search(r"[A-Za-z_][A-Za-z0-9_]*Elevation\s*\(", expression):
        patterns.append(rf"\brequiredSize\s*=\s*{value_pattern}")
    patterns.append(rf"\.shadow\s*\(\s*{value_pattern}")
    for pattern in patterns:
        match = re.search(pattern, expression)
        if match is None:
            continue
        value = resolved_dp_expression(match.group(1), parameter_bindings or {})
        if value is not None and value >= 0:
            return round(value, 3)
    return None


def resolve_constraint_branch(
    expression: str,
    parameter_bindings: dict[str, str],
) -> tuple[str, str]:
    body = expression.strip()
    if body.startswith("{") and body.endswith("}"):
        body = body[1:-1].strip()
    branch_pattern = re.compile(
        r"if\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*(==|!=)\s*null\s*\)\s*"
        r"\{([^{}]*)\}\s*else\s*\{([^{}]*)\}"
    )
    resolved_any = False
    while True:
        match = branch_pattern.search(body)
        if match is None:
            break
        binding = parameter_bindings.get(match.group(1))
        if binding is None:
            return body, "unresolved_condition"
        is_null = binding.strip() == "null"
        condition = is_null if match.group(2) == "==" else not is_null
        selected = match.group(3) if condition else match.group(4)
        body = body[:match.start()] + selected.strip() + body[match.end():]
        resolved_any = True
    if re.search(r"\bif\s*\(", body):
        return body, "unresolved_condition"
    return body, "resolved_condition" if resolved_any else "not_conditional"


def source_layout_relationships(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {component["id"]: component for component in components}
    relationships: list[dict[str, Any]] = []
    link_pattern = re.compile(
        r"\b(start|end|top|bottom|baseline)\.linkTo\(\s*"
        r"([A-Za-z_][A-Za-z0-9_]*)\.(start|end|top|bottom|baseline)"
        r"(?:\s*,\s*margin\s*=\s*([^)]+?))?\s*\)"
    )
    center_pattern = re.compile(
        r"\bcenterAround\(\s*([A-Za-z_][A-Za-z0-9_]*)\."
        r"(start|end|top|bottom|baseline)\s*\)"
    )
    for container in components:
        if container["type"] != "ConstraintLayout":
            continue
        constrained: list[tuple[dict[str, Any], str, dict[str, Any]]] = []
        for child_id in container["children_ids"]:
            child = by_id[child_id]
            modifier = next(
                (
                    item
                    for item in child.get("modifiers", [])
                    if isinstance(item, dict) and item.get("name") == "constrainAs"
                ),
                None,
            )
            reference = str(modifier.get("arguments", "")).strip() if modifier else ""
            if modifier is not None and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", reference):
                constrained.append((child, reference, modifier))
        target_ids = {reference: child["id"] for child, reference, _modifier in constrained}
        target_ids["parent"] = container["id"]
        for child, reference, modifier in constrained:
            raw_expression = modifier.get("trailing_lambda")
            unresolved: list[dict[str, str]] = []
            active_constraints: list[dict[str, Any]] = []
            branch_resolution = "missing_constraint_body"
            active_expression = ""
            bindings = child.get("_parameter_bindings", {})
            if isinstance(raw_expression, str) and raw_expression.strip():
                active_expression, branch_resolution = resolve_constraint_branch(
                    raw_expression,
                    bindings if isinstance(bindings, dict) else {},
                )
                matches: list[tuple[int, dict[str, Any]]] = []
                for match in link_pattern.finditer(active_expression):
                    target_reference = match.group(2)
                    target_id = target_ids.get(target_reference)
                    if target_id is None:
                        unresolved.append({
                            "expression": match.group(0),
                            "reason": "constraint target reference is not a sibling or parent",
                        })
                        continue
                    margin_expression = match.group(4).strip() if match.group(4) else None
                    margin_dp = (
                        resolved_dp_expression(margin_expression, bindings)
                        if margin_expression is not None and isinstance(bindings, dict)
                        else 0.0
                    )
                    if margin_expression is not None and margin_dp is None:
                        unresolved.append({
                            "expression": margin_expression,
                            "reason": "constraint margin is not a resolved dp value",
                        })
                    matches.append((match.start(), {
                        "kind": "link_to",
                        "subject_anchor": match.group(1),
                        "target_id": target_id,
                        "target_reference": target_reference,
                        "target_anchor": match.group(3),
                        "margin_expression": margin_expression,
                        "margin_dp": margin_dp,
                    }))
                for match in center_pattern.finditer(active_expression):
                    target_reference = match.group(1)
                    target_id = target_ids.get(target_reference)
                    if target_id is None:
                        unresolved.append({
                            "expression": match.group(0),
                            "reason": "constraint target reference is not a sibling or parent",
                        })
                        continue
                    matches.append((match.start(), {
                        "kind": "center_around",
                        "subject_anchor": "center",
                        "target_id": target_id,
                        "target_reference": target_reference,
                        "target_anchor": match.group(2),
                        "margin_expression": None,
                        "margin_dp": 0.0,
                    }))
                active_constraints = [item for _position, item in sorted(matches)]
                if not active_constraints:
                    unresolved.append({
                        "expression": raw_expression,
                        "reason": "no supported active ConstraintLayout relationship was resolved",
                    })
            else:
                unresolved.append({
                    "expression": f"constrainAs({reference})",
                    "reason": "constraint body is missing from the source contract",
                })
            overlays_sibling = any(
                constraint["target_id"] != container["id"]
                and (
                    constraint["kind"] == "center_around"
                    or (
                        isinstance(constraint.get("margin_dp"), (int, float))
                        and constraint["margin_dp"] < 0
                    )
                )
                for constraint in active_constraints
            )
            relationships.append({
                "id": "layout-" + hashlib.sha256(
                    f"{container['id']}\0{child['id']}\0{reference}".encode("utf-8")
                ).hexdigest()[:20],
                "container_id": container["id"],
                "container_type": "ConstraintLayout",
                "subject_id": child["id"],
                "subject_reference": reference,
                "composition": "overlay" if overlays_sibling else "constraint",
                "draw_order": child["sibling_index"],
                "source_expression": raw_expression or "",
                "branch_resolution": branch_resolution,
                "active_constraints": active_constraints,
                "unresolved": unresolved,
            })
    return relationships


def select_most_specific_surface_owner(
    owner_matches: list[tuple[int, int, str, list[dict[str, Any]]]],
) -> tuple[int, int, str, list[dict[str, Any]]]:
    return max(owner_matches, key=lambda item: (item[1], item[0], item[2]))


def surface_height_matches_source(
    candidate_height_px: int,
    density: float,
    fixed_heights_dp: set[float],
) -> bool:
    if not fixed_heights_dp:
        return True
    candidate_height_dp = candidate_height_px / density
    return min(
        abs(candidate_height_dp - fixed_height_dp)
        for fixed_height_dp in fixed_heights_dp
    ) <= 2.0


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


def safe_asset_index(source_root: Path | None) -> dict[str, dict[str, Any]]:
    if source_root is None:
        return {}
    manifest = source_root / ".android-to-harmony-safe.json"
    if not manifest.is_file() or manifest.is_symlink():
        return {}
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    original_root = payload.get("source_root")
    original_root_path = Path(original_root) if isinstance(original_root, str) else None
    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in payload.get("local_only_assets") or []:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        sha256 = item.get("sha256")
        if not isinstance(path, str) or not isinstance(sha256, str):
            continue
        resource_path = Path(path)
        if resource_path.parent.name.split("-", 1)[0] not in {"drawable", "mipmap"}:
            continue
        evidence: dict[str, Any] = {"path": path, "sha256": sha256}
        original = original_root_path / path if original_root_path is not None else None
        if original is not None and original.is_file() and not original.is_symlink():
            if hashlib.sha256(original.read_bytes()).hexdigest() == sha256:
                dimensions = android_vector_dimensions(original)
                if dimensions is not None:
                    evidence["width_dp"], evidence["height_dp"] = dimensions
        candidates[resource_path.stem].append(evidence)
    return {
        name: items[0]
        for name, items in candidates.items()
        if len({item["sha256"] for item in items}) == 1
    }


def android_vector_dimensions(path: Path | None) -> tuple[float, float] | None:
    if path is None or path.suffix.lower() != ".xml":
        return None
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None
    if root.tag.rsplit("}", 1)[-1] != "vector":
        return None
    android_namespace = "{http://schemas.android.com/apk/res/android}"

    def dimension(name: str) -> float | None:
        raw = root.get(android_namespace + name)
        match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(?:dp|dip)", raw or "")
        return number(match.group(1)) if match is not None else None

    width, height = dimension("width"), dimension("height")
    return (width, height) if width is not None and height is not None else None


def bound_modifier_call(call: dict[str, Any], bindings: dict[str, str] | None) -> dict[str, Any]:
    expression = call.get('modifier_expression')
    if not isinstance(expression, str) or not bindings:
        return call
    match = re.match(r'^\s*([A-Za-z_]\w*)\b', expression)
    if match is None or match.group(1) not in bindings:
        return call
    receiver = bind_source_expression(match.group(1), bindings)
    if not re.match(r'^Modifier\b', receiver):
        return call
    from analyze_compose_project import ordered_modifier_chain
    resolved = receiver + expression[match.end():]
    return {**call, 'modifier_expression': resolved, 'ordered_modifier_chain': ordered_modifier_chain(resolved)}


def static_style_for_call(
    call: dict[str, Any],
    values: dict[tuple[str, str], str],
    source_root: Path | None,
    parameter_bindings: dict[str, str] | None = None,
    font_family_tokens: set[str] | None = None,
    theme_colors: dict[str, str] | None = None,
    asset_index: dict[str, dict[str, Any]] | None = None,
    theme_text_styles: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, str]]]:
    call = bound_modifier_call(call, parameter_bindings)
    style = empty_style()
    provenance_paths: list[str] = []
    asset_provenance: list[dict[str, Any]] = []
    unresolved: list[dict[str, str]] = []
    component = str(call.get("component", "View"))
    if component in INPUT_TYPES:
        style['input'].update(single_line=False, read_only=False, password=False,
                              keyboard_type='text', ime_action='default')
        for name in sorted(INPUT_ARGUMENTS):
            expression = semantic_expression(call, name)
            if expression is None:
                continue
            expression = bind_source_expression(expression, parameter_bindings)
            parsed = input_argument_values(name, expression)
            if parsed is None:
                fields = {'singleLine': ['single_line'], 'readOnly': ['read_only'],
                          'visualTransformation': ['password'], 'keyboardOptions': ['keyboard_type', 'ime_action']}[name]
                for field in fields:
                    style['input'][field] = None
                    unresolved.append({'path': 'style.input.' + field, 'expression': expression,
                                       'reason': 'input argument requires an explicit supported value'})
            else:
                style['input'].update(parsed)
                provenance_paths.extend('style.input.' + field for field in parsed)
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
    if component in {'TopAppBar', 'CenterAlignedTopAppBar'}:
        expression = semantic_expression(call, 'colors')
        if expression is not None:
            background = simple_appbar_background(bind_source_expression(expression, parameter_bindings))
            if background is not None:
                style['surface']['background'] = background
                provenance_paths.append('style.surface.background')
    if component == "Canvas" and not call.get("custom_draw_commands"):
        unresolved.append(
            {
                "path": "style.custom_draw",
                "expression": f"Canvas trailing lambda at {call['source']}:{call['line']}",
                "reason": "custom draw commands require structural extraction or a target renderer",
            }
        )
    text_expression = semantic_expression(call, "text") or (
        first_positional_expression(call) if component in {"Text", "BasicText", "ClickableText"} else None
    )
    if text_expression is not None:
        text_expression = bind_source_expression(text_expression, parameter_bindings)
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
        description_expression = bind_source_expression(
            description_expression, parameter_bindings
        )
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
    component_color_expression = semantic_expression(call, "color")
    if isinstance(component_color_expression, str):
        component_color_expression = bind_source_expression(
            component_color_expression, parameter_bindings
        )
        component_color = HEX_COLOR_PATTERN.search(component_color_expression)
        if component_color is not None:
            style["typography"]["color"] = component_color.group(1).replace(
                "0x", "#"
            ).upper()
            provenance_paths.append("style.typography.color")
        elif component_color_expression.strip() in {"Color.Black", "Color.White"}:
            style["typography"]["color"] = (
                "#FF000000"
                if component_color_expression.strip() == "Color.Black"
                else "#FFFFFFFF"
            )
            provenance_paths.append("style.typography.color")
    resolved_text_style = ''
    if component in {"Text", "BasicText", "ClickableText", "BasicTextField", "TextField", "OutlinedTextField"}:
        font_size_expression = semantic_expression(call, "fontSize")
        if font_size_expression is not None:
            match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\.sp\s*", font_size_expression)
            if match is not None:
                style["typography"]["font_size_sp"] = number(match.group(1))
                provenance_paths.append("style.typography.font_size_sp")
        color_expression = semantic_expression(call, "color")
        if color_expression is not None:
            color_expression = bind_source_expression(
                color_expression, parameter_bindings
            )
            match = HEX_COLOR_PATTERN.search(color_expression)
            if match is not None:
                style["typography"]["color"] = match.group(1).replace("0x", "#").upper()
                provenance_paths.append("style.typography.color")
        style_expression = semantic_expression(call, "style") or semantic_expression(call, "textStyle")
        if style_expression is not None:
            style_expression = bind_source_expression(style_expression, parameter_bindings)
            if style_expression.startswith('TextStyle(') and style_expression.endswith(')'):
                positional_style, named_style = parsed_arguments(style_expression[len('TextStyle('):-1])
                style_expression = 'TextStyle(' + ', '.join([
                    *positional_style,
                    *(f'{name} = {bind_source_expression(value, parameter_bindings)}'
                      for name, value in named_style.items()),
                ]) + ')'
        theme_role = re.fullmatch(r"MaterialTheme\.typography\.(\w+)", style_expression or "")
        if theme_role and theme_role.group(1) in (theme_text_styles or {}):
            selected_style = theme_text_styles[theme_role.group(1)]
            expression = selected_style.get("expression") if isinstance(selected_style, dict) else None
            if not isinstance(expression, str) or not expression.startswith("TextStyle("):
                raise RealPageError(f"project typography {theme_role.group(1)} needs a resolved TextStyle")
            style_expression = expression
        resolved_text_style = style_expression or ''
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
            elif re.search(r'\bcolor\s*=\s*Color\.(White|Black)\b', style_expression):
                color_name = re.search(r'\bcolor\s*=\s*Color\.(White|Black)\b', style_expression).group(1)
                style['typography']['color'] = '#FFFFFFFF' if color_name == 'White' else '#FF000000'
                provenance_paths.append('style.typography.color')
            family_match = re.search(
                r"\bfontFamily\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\b",
                style_expression,
            )
            if (
                family_match is not None
                and family_match.group(1) in (font_family_tokens or set())
            ):
                style["typography"]["font_family"] = family_match.group(1)
                provenance_paths.append("style.typography.font_family")
        font_family_expression = semantic_expression(call, "fontFamily")
        if (
            isinstance(font_family_expression, str)
            and font_family_expression.strip() in (font_family_tokens or set())
        ):
            style["typography"]["font_family"] = font_family_expression.strip()
            provenance_paths.append("style.typography.font_family")
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
        # Explicit Text parameters override values inherited from TextStyle.
        # Parse them after the style so the canonical facts retain Compose's
        # actual precedence instead of silently keeping a theme default.
        direct_font_size = semantic_expression(call, "fontSize")
        if isinstance(direct_font_size, str):
            match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\.sp\s*", direct_font_size)
            if match is not None:
                style["typography"]["font_size_sp"] = number(match.group(1))
                provenance_paths.append("style.typography.font_size_sp")
        direct_line_height = semantic_expression(call, "lineHeight")
        if isinstance(direct_line_height, str):
            match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\.sp\s*", direct_line_height)
            if match is not None:
                style["typography"]["line_height_sp"] = number(match.group(1))
                provenance_paths.append("style.typography.line_height_sp")
        direct_font_weight = semantic_expression(call, "fontWeight")
        if isinstance(direct_font_weight, str):
            weight = font_weight_expression(direct_font_weight)
            if weight is not None:
                style["typography"]["font_weight"] = weight
                provenance_paths.append("style.typography.font_weight")
        direct_color = semantic_expression(call, "color")
        if isinstance(direct_color, str):
            direct_color = bind_source_expression(direct_color, parameter_bindings)
            match = HEX_COLOR_PATTERN.search(direct_color)
            if match is not None:
                style["typography"]["color"] = match.group(1).replace("0x", "#").upper()
                provenance_paths.append("style.typography.color")
            elif direct_color.strip() in {"Color.Black", "Color.White"}:
                style["typography"]["color"] = (
                    "#FF000000" if direct_color.strip() == "Color.Black" else "#FFFFFFFF"
                )
                provenance_paths.append("style.typography.color")
        direct_text_align = semantic_expression(call, "textAlign")
        if isinstance(direct_text_align, str):
            text_align = {
                "TextAlign.Start": "start",
                "TextAlign.Center": "center",
                "TextAlign.End": "end",
                "TextAlign.Justify": "justify",
            }.get(direct_text_align.strip())
            if text_align is not None:
                style["typography"]["text_align"] = text_align
                provenance_paths.append("style.typography.text_align")
        max_lines_expression = semantic_expression(call, "maxLines")
        if isinstance(max_lines_expression, str):
            match = re.fullmatch(r"\s*([1-9][0-9]*)\s*", max_lines_expression)
            if match is not None:
                style["typography"]["max_lines"] = int(match.group(1))
                provenance_paths.append("style.typography.max_lines")
        overflow_expression = semantic_expression(call, "overflow")
        if isinstance(overflow_expression, str):
            overflow = {
                "TextOverflow.Clip": "clip",
                "TextOverflow.Ellipsis": "ellipsis",
                "TextOverflow.Visible": "visible",
            }.get(overflow_expression.strip())
            if overflow is not None:
                style["typography"]["overflow"] = overflow
                provenance_paths.append("style.typography.overflow")
        decoration_expression = semantic_expression(call, "textDecoration")
        if isinstance(decoration_expression, str):
            decoration = {
                "TextDecoration.None": "none",
                "TextDecoration.Underline": "underline",
                "TextDecoration.LineThrough": "line_through",
            }.get(decoration_expression.strip())
            if decoration is not None:
                style["typography"]["decoration"] = decoration
                provenance_paths.append("style.typography.decoration")
    _, style_arguments = parsed_arguments(resolved_text_style[10:-1]) if (
        resolved_text_style.startswith('TextStyle(') and resolved_text_style.endswith(')')
    ) else ([], {})
    for argument, field, parser in (
        ("fontStyle", "font_style", lambda value: {"FontStyle.Italic": "italic", "FontStyle.Normal": "normal"}.get(value)),
        ("letterSpacing", "letter_spacing_sp", lambda value: number_expression(value, 'sp')),
        ("fontSize", "font_size_sp", lambda value: number_expression(value, 'sp')),
        ("lineHeight", "line_height_sp", lambda value: number_expression(value, 'sp')),
        ("fontWeight", "font_weight", font_weight_expression),
        ("textAlign", "text_align", lambda value: {'TextAlign.Start': 'start', 'TextAlign.Center': 'center', 'TextAlign.End': 'end', 'TextAlign.Justify': 'justify'}.get(value)),
        ("textDecoration", "decoration", lambda value: {'TextDecoration.None': 'none', 'TextDecoration.Underline': 'underline', 'TextDecoration.LineThrough': 'line_through'}.get(value)),
    ):
        expression = semantic_expression(call, argument) or style_arguments.get(argument)
        if expression is not None:
            expression = bind_source_expression(expression, parameter_bindings).strip()
            parsed = parser(expression)
            path = f"style.typography.{field}"
            style["typography"][field] = parsed
            if parsed is not None:
                provenance_paths.append(path)
            else:
                unresolved.append({"path": path, "expression": expression, "reason": "unresolved explicit text attribute"})
    if component in {"BasicTextField", "TextField", "OutlinedTextField"} and content.get("text") is None:
        expression = semantic_expression(call, "value")
        if expression is not None:
            expression = bind_source_expression(expression, parameter_bindings)
            content["text"] = resolve_text(expression, values)
            if content["text"] is not None:
                provenance_paths.append("style.content.text")
            else:
                unresolved.append({"path": "style.content.text", "expression": expression, "reason": "unresolved input value"})
    placeholder_expression = semantic_expression(call, "placeholder")
    if (
        placeholder_expression is not None
        and not is_preview_only_placeholder_expression(placeholder_expression)
    ):
        placeholder_expression = bind_source_expression(
            placeholder_expression, parameter_bindings
        )
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
    from page_native_controls import CONTROL_TYPES, arguments_for, defaults_for, parse_argument
    if component in CONTROL_TYPES:
        style['control'].update(defaults_for(component))
        provenance_paths.extend('style.control.' + field for field in defaults_for(component))
        for argument in arguments_for(component):
            expression = semantic_expression(call, argument)
            if expression is None:
                continue
            expression = bind_source_expression(expression, parameter_bindings)
            parsed = parse_argument(argument, expression)
            if parsed is None:
                for field in {'valueRange': ('minimum', 'maximum'), 'steps': ('steps',)}.get(argument, ()):
                    style['control'][field] = None
                unresolved.append({'path': 'source.arguments.' + argument.lower(), 'expression': expression,
                                   'reason': 'control argument requires a resolved constant'})
            else:
                style['control'].update(parsed)
                provenance_paths.extend('style.control.' + field for field in parsed)
        # Color on these primitives paints their track/stroke, not text.
        style['typography']['color'] = None
        provenance_paths = [p for p in provenance_paths if p != 'style.typography.color']
    if component in {'Text', 'BasicText', 'ClickableText', 'TextField', 'BasicTextField', 'OutlinedTextField'}:
        for argument, field, parser in (
            ('softWrap', 'soft_wrap', lambda v: {'true': True, 'false': False}.get(v)),
            ('minLines', 'min_lines', lambda v: int(v) if re.fullmatch(r'[1-9][0-9]*', v) else None),
        ):
            expression = semantic_expression(call, argument)
            if expression is not None:
                parsed = parser(bind_source_expression(expression, parameter_bindings).strip())
                style['typography'][field] = parsed
                if parsed is not None:
                    provenance_paths.append('style.typography.' + field)
                else:
                    unresolved.append({'path': 'style.typography.' + field, 'expression': expression,
                                       'reason': 'text layout argument requires a resolved constant'})
    clickable = component in {
        "Button", "IconButton", "FloatingActionButton", "SmallFloatingActionButton"
    } or semantic_expression(call, "onClick") is not None
    state["clickable"] = clickable
    state["enabled"] = True
    state["visible"] = True
    provenance_paths.extend(("style.state.clickable", "style.state.enabled", "style.state.visible"))
    for field in ("enabled", "visible", "selected", "checked"):
        expression = semantic_expression(call, field)
        if expression is None:
            continue
        expression = bind_source_expression(expression, parameter_bindings).strip()
        state[field] = {"true": True, "false": False}.get(expression)
        path = f"style.state.{field}"
        if state[field] is not None:
            provenance_paths.append(path)
        else:
            provenance_paths = [item for item in provenance_paths if item != path]
            unresolved.append({"path": path, "expression": expression, "reason": "unresolved explicit state"})
    if component in {"Button", "IconButton", "FloatingActionButton", "SmallFloatingActionButton", "Card"}:
        style["surface"]["clip"] = True
        provenance_paths.append("style.surface.clip")

    if component in {'Button', 'TextButton', 'OutlinedButton', 'DecorationBox', 'Card'}:
        def surface_color(expression: str | None) -> str | None:
            expression = bind_source_expression(expression or '', parameter_bindings).strip()
            constant = {'Color.White': '#FFFFFFFF', 'Color.Black': '#FF000000',
                        'Color.Transparent': '#00000000'}.get(expression)
            if constant:
                return constant
            role = re.fullmatch(r'MaterialTheme\.colorScheme\.(\w+)', expression)
            if role:
                return (theme_colors or {}).get(role.group(1))
            match = re.fullmatch(r'Color\(\s*0x([0-9A-Fa-f]{8})\s*\)|#([0-9A-Fa-f]{8})', expression)
            return '#' + (match.group(1) or match.group(2)).upper() if match else None

        colors_expression = bind_source_expression(semantic_expression(call, 'colors') or '', parameter_bindings)
        color_factory = re.fullmatch(r'(?:ButtonDefaults|OutlinedTextFieldDefaults|TextFieldDefaults|CardDefaults)\.(\w+)\((.*)\)',
                                     colors_expression, re.DOTALL)
        if color_factory:
            _, colors = parsed_arguments(color_factory.group(2))
            enabled_expression = bind_source_expression(semantic_expression(call, 'enabled') or 'true', parameter_bindings)
            enabled = style['state'].get('enabled')
            roles = {'Button': ('primary', 'onPrimary'), 'TextButton': (None, 'primary'),
                     'OutlinedButton': (None, 'primary')}
            for path, property_name in [('style.surface.background', 'ContainerColor'),
                                        ('style.typography.color', 'ContentColor')]:
                normal_key = property_name[0].lower() + property_name[1:]
                if component == 'DecorationBox':
                    normal_key = 'unfocusedContainerColor' if property_name == 'ContainerColor' else 'unfocusedTextColor'
                active = surface_color(colors.get(normal_key))
                inactive = surface_color(colors.get('disabled' + property_name))
                if component in roles:
                    role = roles[component][0 if property_name == 'ContainerColor' else 1]
                    if active is None and normal_key not in colors:
                        active = (theme_colors or {}).get(role) if role else '#00000000'
                    on_surface = (theme_colors or {}).get('onSurface')
                    if inactive is None and 'disabled' + property_name not in colors and on_surface:
                        # Material 3 ButtonDefaults: disabled container/content alpha.
                        alpha = '1F' if property_name == 'ContainerColor' else '61'
                        inactive = (f'#{alpha}{on_surface[-6:]}' if role or property_name == 'ContentColor'
                                    else '#00000000')
                if component == 'Card' and property_name == 'ContentColor' and normal_key not in colors:
                    container = surface_color(colors.get('containerColor'))
                    content_role = next((on_role for role, on_role in (
                        ('primary', 'onPrimary'), ('secondary', 'onSecondary'), ('tertiary', 'onTertiary'),
                        ('background', 'onBackground'), ('surface', 'onSurface'),
                        ('surfaceContainerHighest', 'onSurface'))
                        if container is not None and (theme_colors or {}).get(role) == container), None)
                    active = (theme_colors or {}).get(content_role)
                color = active if enabled is True else inactive if enabled is False else None
                if color is not None:
                    section, field = path.split('.')[1:]
                    style[section][field] = {'type': 'solid', 'color': color} if field == 'background' else color
                    provenance_paths.append(path)
                elif active and inactive:
                    unresolved.append({'path': path, 'expression': f'if ({enabled_expression}) {{ "{active}" }} else {{ "{inactive}" }}',
                                       'reason': 'surface depends on the selected static enabled state'})
        shape_expression = semantic_expression(call, 'shape')
        if component == 'Card':
            elevation = bind_source_expression(semantic_expression(call, 'elevation') or 'CardDefaults.cardElevation()', parameter_bindings)
            if elevation not in {'CardDefaults.cardElevation()', 'CardDefaults.cardElevation(defaultElevation = 0.dp)'}:
                unresolved.append({'path': 'source.arguments.elevation', 'expression': elevation,
                                   'reason': 'non-default Material elevation needs a verified shadow mapping; content is retained'})
            shape_expression = shape_expression or 'RoundedCornerShape(12.dp)'
        if component == 'DecorationBox' and not shape_expression:
            container = semantic_expression(call, 'container') or ''
            match = re.fullmatch(r'\s*\{\s*OutlinedTextFieldDefaults\.ContainerBox\((.*)\)\s*\}\s*', container, re.DOTALL)
            if match:
                positional, named = parsed_arguments(match.group(1))
                shape_expression = named.get('shape') or (positional[4] if len(positional) > 4 else None)
                if color_factory:
                    # Material 3 OutlinedTextFieldDefaults.ContainerBox, initial unfocused state.
                    thickness = named.get('unfocusedBorderThickness') or (positional[6] if len(positional) > 6 else '1.dp')
                    width = re.fullmatch(r'([0-9]+(?:\.[0-9]+)?)\.dp', bind_source_expression(thickness, parameter_bindings))
                    normal = surface_color(colors.get('unfocusedIndicatorColor'))
                    error = surface_color(colors.get('errorIndicatorColor')) or (theme_colors or {}).get('error')
                    disabled = surface_color(colors.get('disabledIndicatorColor'))
                    error_expression = bind_source_expression(semantic_expression(call, 'isError') or 'false', parameter_bindings)
                    selected = (disabled if enabled is False else
                                error if enabled is True and error_expression == 'true' else
                                normal if enabled is True and error_expression == 'false' else None)
                    if width:
                        style['surface']['border'] = dict(width_dp=number(width.group(1)), color=selected, style='solid')
                        provenance_paths.extend(('style.surface.border.width_dp', 'style.surface.border.style'))
                        if selected:
                            provenance_paths.append('style.surface.border.color')
                        else:
                            expression = (f'if ({error_expression}) {{ "{error}" }} else {{ "{normal}" }}'
                                          if enabled is True and normal and error else 'unresolved outlined border state')
                            unresolved.append({'path': 'style.surface.border.color', 'expression': expression,
                                               'reason': 'outlined border color requires the selected enabled/error state'})
        if shape_expression:
            bound_shape = bind_source_expression(shape_expression, parameter_bindings)
            radius = constant_corner_radius(bound_shape, style['layout'].get('layout_direction'))
            if radius is not None:
                style['surface']['corner_radius_dp'] = radius
                provenance_paths.append('style.surface.corner_radius_dp')
            else:
                unresolved.append({'path': 'style.surface.corner_radius_dp', 'expression': bound_shape,
                                   'reason': 'native shape requires resolved corner values'})

    semantic_arguments = call.get("semantic_arguments")
    content_padding_argument = (
        semantic_arguments.get("contentPadding")
        if isinstance(semantic_arguments, dict)
        else None
    )
    if isinstance(content_padding_argument, dict):
        padding_expression = content_padding_argument.get("expression")
        dimensions = modifier_dimensions(content_padding_argument)
        if isinstance(padding_expression, str):
            padding = direct_padding(padding_expression, dimensions)
            if padding is not None:
                style["layout"]["padding_dp"] = padding
                provenance_paths.append("style.layout.padding_dp")

    alignment_expression = (
        semantic_expression(call, "contentAlignment")
        or semantic_expression(call, "alignment")
        or semantic_expression(call, "horizontalAlignment")
        or semantic_expression(call, "verticalAlignment")
    )
    if alignment_expression is not None:
        alignment = alignment_expression.strip().rsplit(".", 1)[-1]
        if alignment in {
            "TopStart", "TopCenter", "TopEnd",
            "CenterStart", "Center", "CenterEnd",
            "BottomStart", "BottomCenter", "BottomEnd",
        }:
            style["layout"]["alignment"] = alignment
            provenance_paths.append("style.layout.alignment")
        elif alignment in {"Start", "CenterHorizontally", "End", "Top", "CenterVertically", "Bottom"}:
            style["layout"]["alignment"] = alignment
            provenance_paths.append("style.layout.alignment")

    for semantic_name, style_field in (
        ("horizontalArrangement", "horizontal_arrangement"),
        ("verticalArrangement", "vertical_arrangement"),
    ):
        arrangement_expression = semantic_expression(call, semantic_name)
        if isinstance(arrangement_expression, str):
            style["layout"][style_field] = arrangement_expression.strip()
            provenance_paths.append(f"style.layout.{style_field}")

    painter_expression = (
        semantic_expression(call, "painter")
        or semantic_expression(call, "imageVector")
        or semantic_expression(call, "model")
        or (first_positional_expression(call) if component == "Icon" else None)
    )
    tint_expression = semantic_expression(call, 'tint')
    if tint_expression is not None:
        tint_expression = bind_source_expression(tint_expression, parameter_bindings).strip()
        color = HEX_COLOR_PATTERN.fullmatch(tint_expression.removeprefix('Color(').removesuffix(')'))
        tint = color.group(1).replace('0x', '#').upper() if color else {
            'Color.Black': '#FF000000', 'Color.White': '#FFFFFFFF',
            'Color.Transparent': '#00000000',
        }.get(tint_expression)
        style['asset']['tint'] = tint
        if tint is not None or tint_expression == 'Color.Unspecified':
            provenance_paths.append('style.asset.tint')
        else:
            unresolved.append({'path': 'style.asset.tint', 'expression': tint_expression, 'reason': 'unresolved tint color'})
    if painter_expression is not None:
        painter_expression = bind_source_expression(
            painter_expression, parameter_bindings
        )
        match = DRAWABLE_RESOURCE_PATTERN.search(painter_expression)
        if match is not None:
            resource = match.group(1)
            style["asset"]["resource"] = resource
            provenance_paths.append("style.asset.resource")
            file = find_resource_file(source_root, resource)
            if file is not None:
                style["asset"]["sha256"] = hashlib.sha256(file.read_bytes()).hexdigest()
                provenance_paths.append("style.asset.sha256")
                intrinsic_size = android_vector_dimensions(file)
                if intrinsic_size is not None:
                    style["asset"]["width_dp"], style["asset"]["height_dp"] = intrinsic_size
                    provenance_paths.extend(
                        ("style.asset.width_dp", "style.asset.height_dp")
                    )
            elif resource in (asset_index or {}):
                evidence = asset_index[resource]
                style["asset"]["sha256"] = evidence["sha256"]
                provenance_paths.append("style.asset.sha256")
                if isinstance(evidence.get("width_dp"), (int, float)):
                    style["asset"]["width_dp"] = evidence["width_dp"]
                    provenance_paths.append("style.asset.width_dp")
                if isinstance(evidence.get("height_dp"), (int, float)):
                    style["asset"]["height_dp"] = evidence["height_dp"]
                    provenance_paths.append("style.asset.height_dp")
                asset_provenance.append(
                    {
                        "paths": ["style.asset.sha256"],
                        "origin": "source_resolved",
                        "source": evidence["path"],
                    }
                )
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

    style_modifiers = []
    for modifier in call.get('ordered_modifier_chain', []):
        style_modifiers.append(modifier)
        if isinstance(modifier, dict) and modifier.get('name') == 'then':
            from analyze_compose_project import ordered_modifier_chain
            style_modifiers.extend(ordered_modifier_chain(bind_source_expression(
                str(modifier.get('arguments') or ''), parameter_bindings)))
    for modifier in style_modifiers:
        if not isinstance(modifier, dict) or not isinstance(modifier.get("name"), str):
            continue
        name = modifier["name"]
        arguments = str(modifier.get("arguments", ""))
        dimensions = modifier_dimensions(modifier)
        dp_values = [value for value, unit in dimensions if unit == "dp"]
        shadow_elevation = resolved_shadow_elevation(arguments, parameter_bindings)
        if shadow_elevation is not None:
            style["surface"]["shadows"] = [{
                "color": "#1A000000",
                "offset_x_dp": 0.0,
                "offset_y_dp": round(shadow_elevation * 0.2, 3),
                "blur_radius_dp": shadow_elevation,
                "spread_radius_dp": 0.0,
            }]
            provenance_paths.append("style.surface.shadows")
        size_section = style["layout"]
        size_prefix = "style.layout"
        if name == "size":
            for axis, value in zip(("width", "height"), size_arguments(arguments)):
                if value is not None:
                    size_section[f"{axis}_dp"] = value
                    provenance_paths.append(f"{size_prefix}.{axis}_dp")
        elif name in {"width", "requiredWidth"} and dp_values:
            size_section["width_dp"] = dp_values[0]
            provenance_paths.append(f"{size_prefix}.width_dp")
        elif name in {"height", "requiredHeight"} and dp_values:
            size_section["height_dp"] = dp_values[0]
            provenance_paths.append(f"{size_prefix}.height_dp")
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
        elif name in {"rotate", "scale"}:
            positional, named = parsed_arguments(arguments)
            common = named.get("scale") or (positional[0] if len(positional) == 1 else None)
            expressions = {"rotation_degrees": named.get("degrees") or common} if name == "rotate" else {
                f"scale_{axis}": named.get(f"scale{axis.upper()}") or
                (positional[index] if len(positional) > 1 else common)
                for index, axis in enumerate(("x", "y"))
            }
            for field, expression in expressions.items():
                value = numeric_literal(expression)
                style["transform"][field] = value
                path = f"style.transform.{field}"
                if value is not None:
                    provenance_paths.append(path)
                else:
                    unresolved.append({"path": path, "expression": arguments, "reason": "unresolved transform"})
        elif name == "background":
            match = HEX_COLOR_PATTERN.search(arguments)
            if 'Brush.' in arguments:
                positional, named = parsed_arguments(arguments)
                brush = named.get('brush') or (positional[0] if len(positional) == 1 else '')
                gradient = constant_linear_gradient(brush) if not (set(named) - {'brush'}) else None
                style['surface']['background'] = gradient
                if gradient is not None:
                    provenance_paths.append('style.surface.background')
                else:
                    unresolved.append({'path': 'style.surface.background', 'expression': arguments,
                                       'reason': 'gradient endpoints, colors or brush kind are not resolved'})
            elif match is not None:
                raw = match.group(1).replace("0x", "#")
                style["surface"]["background"] = {"type": "solid", "color": raw.upper()}
                provenance_paths.append("style.surface.background")
            elif (
                match := re.fullmatch(
                    r"MaterialTheme\.colorScheme\.([A-Za-z_][A-Za-z0-9_]*)",
                    arguments.strip(),
                )
            ) and match.group(1) in (theme_colors or {}):
                style["surface"]["background"] = {
                    "type": "solid",
                    "color": theme_colors[match.group(1)],
                }
                provenance_paths.append("style.surface.background")
            elif arguments:
                unresolved.append(
                    {"path": "style.surface.background", "expression": arguments, "reason": "theme or dynamic source expression"}
                )
        elif name == "clip":
            radius = constant_corner_radius(arguments, style['layout'].get('layout_direction'))
            if radius is not None:
                style["surface"]["corner_radius_dp"] = radius
                style["surface"]["clip"] = True
                provenance_paths.extend(("style.surface.corner_radius_dp", "style.surface.clip"))
            elif arguments.strip() == "CircleShape":
                style["surface"]["clip"] = True
                provenance_paths.append("style.surface.clip")
            else:
                unresolved.append({'path': 'style.surface.clip', 'expression': arguments,
                                   'reason': 'shape needs resolved corners and layout direction'})
        elif name == "border":
            width = re.search(
                r"\bwidth\s*=\s*([0-9]+(?:\.[0-9]+)?)\.dp",
                arguments,
            )
            color = HEX_COLOR_PATTERN.search(arguments)
            theme_role = re.search(
                r"\bcolor\s*=\s*MaterialTheme\.colorScheme\.([A-Za-z_][A-Za-z0-9_]*)",
                arguments,
            )
            border_color = (
                color.group(1).replace("0x", "#").upper()
                if color is not None
                else (theme_colors or {}).get(theme_role.group(1))
                if theme_role is not None
                else None
            )
            if width is not None and border_color is not None:
                style["surface"]["border"] = {
                    "width_dp": number(width.group(1)),
                    "color": border_color,
                    "style": "solid",
                }
                provenance_paths.append("style.surface.border")
            radius = re.search(
                r"RoundedCornerShape\s*\([^)]*?([0-9]+(?:\.[0-9]+)?)\.dp",
                arguments,
            )
            if radius is not None:
                value = number(radius.group(1))
                style["surface"]["corner_radius_dp"] = {
                    "top_left": value,
                    "top_right": value,
                    "bottom_right": value,
                    "bottom_left": value,
                }
                provenance_paths.append("style.surface.corner_radius_dp")
        elif name == "dashedBorder" or (name == "then" and "dashedBorder" in arguments):
            width = re.search(
                r"strokeWidth\s*=\s*([0-9]+(?:\.[0-9]+)?)\.dp",
                arguments,
            )
            radius = re.search(
                r"cornerRadiusDp\s*=\s*([0-9]+(?:\.[0-9]+)?)\.dp",
                arguments,
            )
            color = HEX_COLOR_PATTERN.search(arguments)
            theme_role = re.search(
                r"color\s*=\s*MaterialTheme\.colorScheme\.([A-Za-z_][A-Za-z0-9_]*)",
                arguments,
            )
            border_color = (
                color.group(1).replace("0x", "#").upper()
                if color is not None
                else (theme_colors or {}).get(theme_role.group(1))
                if theme_role is not None
                else None
            )
            if width is not None and border_color is not None:
                style["surface"]["border"] = {
                    "width_dp": number(width.group(1)),
                    "color": border_color,
                    "style": "dashed",
                }
                provenance_paths.append("style.surface.border")
            if radius is not None:
                value = number(radius.group(1))
                style["surface"]["corner_radius_dp"] = {
                    "top_left": value,
                    "top_right": value,
                    "bottom_right": value,
                    "bottom_left": value,
                }
                provenance_paths.append("style.surface.corner_radius_dp")
    provenance = []
    if provenance_paths:
        provenance.append(
            {
                "paths": sorted(set(provenance_paths)),
                "origin": "source_resolved",
                "source": f"{call['source']}:{call['line']}",
            }
        )
    provenance.extend(asset_provenance)
    return style, provenance, unresolved


def selected_theme_colors(inventory: dict[str, Any] | None) -> dict[str, str]:
    selected = next((scheme for scheme in (inventory or {}).get('color_schemes', [])
                     if isinstance(scheme, dict) and scheme.get('variant') == 'light'), None)
    if selected is None:
        return {}
    roles = selected.get('roles') or {}
    colors = {role: value for role, value in MATERIAL3_LIGHT_COLOR_DEFAULTS.items()
              if selected.get('constructor') == 'lightColorScheme' and role not in roles}
    for role, semantics in roles.items():
        value = color_from_semantics(semantics)
        if value is not None:
            colors[str(role)] = value
    return colors


def selected_theme_text_styles(inventory: dict[str, Any] | None) -> dict[str, Any]:
    if not inventory:
        return {}
    names = {
        item.get("arguments", {}).get("typography", {}).get("expression")
        for item in inventory.get("theme_applications", [])
        if isinstance(item, dict)
    } - {None}
    if not names:
        return {}
    if len(names) != 1:
        raise RealPageError("multiple project typography providers require an explicit page theme")
    matches = [item for item in inventory.get("typography_sets", []) if item.get("name") in names]
    if len(matches) != 1:
        raise RealPageError("project typography provider is unresolved or ambiguous")
    return copy.deepcopy(matches[0].get("styles", {}))


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
    raw_composables = ui.get("composables") if isinstance(ui, dict) else None
    parameters_by_definition = {
        (str(item["source"]), str(item["name"])): copy.deepcopy(item.get("parameters", []))
        for item in raw_composables or []
        if isinstance(item, dict)
        and isinstance(item.get("source"), str)
        and isinstance(item.get("name"), str)
        and isinstance(item.get("parameters"), list)
    }
    theme_inventory = ui.get("compose_theme_token_inventory") if isinstance(ui, dict) else None
    theme_tokens = theme_inventory.get("tokens") if isinstance(theme_inventory, dict) else None
    theme_text_styles = selected_theme_text_styles(theme_inventory)
    theme_colors = selected_theme_colors(theme_inventory)
    font_family_tokens = {
        str(token["name"])
        for token in theme_tokens or []
        if isinstance(token, dict)
        and token.get("kind") == "font_family"
        and isinstance(token.get("name"), str)
    }
    manifest_assets = safe_asset_index(source_root)
    components: list[dict[str, Any]] = []
    component_definitions: dict[str, dict[str, Any]] = {}
    metadata_cache: dict[str, tuple[str | None, dict[str, str]]] = {}
    expansion_unresolved: list[dict[str, str]] = []
    semantic_key_counts: dict[str, int] = defaultdict(int)

    def expand_definition(
        definition: tuple[str, str],
        attach_parent: str | None,
        instance_path: str,
        stack: tuple[tuple[str, str], ...],
        parameter_bindings: dict[str, str],
    ) -> dict[str, str]:
        if definition in stack:
            expansion_unresolved.append(
                {"path": instance_path, "expression": f"{definition[0]}#{definition[1]}", "reason": "recursive composable cycle"}
            )
            return {}
        definition_calls = calls_by_definition.get(definition, [])
        local_ids = {
            str(call["call_id"]): source_component_id(instance_path, str(call["call_id"]))
            for call in definition_calls
            if isinstance(call.get("call_id"), str)
        }
        created: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for call in definition_calls:
            call = bound_modifier_call(call, parameter_bindings)
            call_id = call.get("call_id")
            if not isinstance(call_id, str):
                continue
            raw_parent = call.get("parent_call_id")
            parent_id = local_ids.get(raw_parent) if isinstance(raw_parent, str) else attach_parent
            style, provenance, unresolved = static_style_for_call(
                call,
                values,
                source_root,
                parameter_bindings,
                font_family_tokens,
                theme_colors,
                manifest_assets,
                theme_text_styles,
            )
            custom = call.get("custom_composable")
            definition = component_definition(call, source_root, metadata_cache)
            component_definitions.setdefault(definition["id"], definition)
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
                "definition_id": definition["id"],
                "component_kind": definition["component_kind"],
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
                    "trailing_lambda_parameters": copy.deepcopy(call.get('trailing_lambda_parameters') or []),
                },
                "arguments": {
                    "semantic": copy.deepcopy(call.get("semantic_arguments", {})),
                    "positional": copy.deepcopy(call.get("positional_arguments", [])),
                    "state_slots": copy.deepcopy(call.get("state_slots", [])),
                    "invocation": copy.deepcopy(custom.get("arguments", [])) if isinstance(custom, dict) else [],
                },
                "visibility_condition": copy.deepcopy(call.get("visibility_condition")),
                "list_item_context": copy.deepcopy(call.get("list_item_context")),
                "local_values": copy.deepcopy(call.get("local_values", {})),
                "modifiers": copy.deepcopy(call.get("ordered_modifier_chain", [])),
                "custom_draw_commands": [
                    {
                        "kind": str(command.get("kind")),
                        "arguments": {
                            str(name): re.sub(
                                r"MaterialTheme\.colorScheme\.([A-Za-z_][A-Za-z0-9_]*)",
                                lambda match: (theme_colors or {}).get(
                                    match.group(1), match.group(0)
                                ),
                                bind_source_expression(str(expression), parameter_bindings),
                            )
                            for name, expression in (command.get("arguments") or {}).items()
                        },
                    }
                    for command in call.get("custom_draw_commands") or []
                    if isinstance(command, dict)
                ],
                "slot_argument_name": (
                    str(call["slot_argument_name"])
                    if isinstance(call.get("slot_argument_name"), str)
                    else None
                ),
                "slot_invocation": (
                    copy.deepcopy(call["slot_invocation"])
                    if isinstance(call.get("slot_invocation"), dict)
                    else None
                ),
                "style": style,
                "provenance": provenance,
                "unresolved": unresolved,
                "parameter_bindings": copy.deepcopy(parameter_bindings),
                "_parameter_bindings": copy.deepcopy(parameter_bindings),
            }
            component["layout_rules"] = normalized_layout_rules(component)
            if call.get('decoration_kind'):
                component['source']['decoration_kind'] = call['decoration_kind']
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
            parameters = parameters_by_definition.get(
                (str(target[0]), str(target[1])), []
            )
            child_bindings = {
                str(parameter["name"]): bind_source_expression(
                    str(parameter["default"]), parameter_bindings
                )
                for parameter in parameters
                if isinstance(parameter, dict)
                and isinstance(parameter.get("name"), str)
                and isinstance(parameter.get("default"), str)
            }
            positional_index = 0
            for argument in custom.get("arguments", []):
                if not isinstance(argument, dict) or not isinstance(argument.get("expression"), str):
                    continue
                argument_name = argument.get("name")
                if not isinstance(argument_name, str):
                    if positional_index < len(parameters):
                        candidate_name = parameters[positional_index].get("name")
                        argument_name = candidate_name if isinstance(candidate_name, str) else None
                        positional_index += 1
                if isinstance(argument_name, str):
                    child_bindings[argument_name] = bind_source_expression(
                        str(argument["expression"]), parameter_bindings
                    )
            slot_hosts = expand_definition(
                (str(target[0]), str(target[1])),
                component["id"],
                f"{instance_path}/{call['call_id']}",
                stack + (definition,),
                child_bindings,
            )
            for child_component, child_call in created:
                if child_call.get("parent_call_id") != call.get("call_id"):
                    continue
                slot_name = child_call.get("slot_argument_name")
                slot_host = slot_hosts.get(slot_name) if isinstance(slot_name, str) else None
                if slot_host is not None:
                    child_component["parent_id"] = slot_host
                elif isinstance(slot_name, str):
                    expansion_unresolved.append({
                        "path": child_component["id"],
                        "expression": slot_name,
                        "reason": "custom component slot invocation was not uniquely resolved",
                    })

        slot_ids: dict[str, list[str]] = defaultdict(list)
        for component, call in created:
            invocation = call.get("slot_invocation")
            slot_name = invocation.get("name") if isinstance(invocation, dict) else None
            if isinstance(slot_name, str):
                slot_ids[slot_name].append(component["id"])
            if call.get('component') in {'DecorationBox', 'Scaffold', 'TopAppBar', 'CenterAlignedTopAppBar'}:
                for argument_name, argument in (call.get('semantic_arguments') or {}).items():
                    expression = argument.get('expression') if isinstance(argument, dict) else None
                    if isinstance(expression, str) and re.fullmatch(r'[A-Za-z_]\w*', expression.strip()):
                        if any(p.get('name') == expression.strip() and '@Composable' in str(p.get('type'))
                               for p in parameters_by_definition.get((str(call['source']), str(call['composable'])), [])):
                            slot_ids[expression.strip()].append(component['id'])
        return {
            name: ids[0]
            for name, ids in slot_ids.items()
            if len(ids) == 1
        }

    expand_definition((root_source, root_composable), None, "root", (), {})
    by_id = {item["id"]: item for item in components}
    children: dict[str | None, list[str]] = defaultdict(list)
    for component in components:
        children[component["parent_id"]].append(component["id"])
    for parent_id, child_ids in children.items():
        for index, child_id in enumerate(child_ids):
            by_id[child_id]["sibling_index"] = index
        if parent_id is not None and parent_id in by_id:
            by_id[parent_id]["children_ids"] = child_ids
    layout_relationships = source_layout_relationships(components)
    for component in components:
        component.pop("_parameter_bindings", None)
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
    for component in components:
        component["required_facts"] = build_required_facts(component)
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
        "source_tokens": copy.deepcopy(theme_tokens or []),
        "source_text_styles": copy.deepcopy(theme_text_styles),
        "source_value_inventory": copy.deepcopy(ui.get('kotlin_data_class_inventory') or {}),
        "source_color_schemes": copy.deepcopy(
            theme_inventory.get("color_schemes", [])
            if isinstance(theme_inventory, dict)
            else []
        ),
        "source_assets": [
            {
                "resource": resource,
                **{
                    key: value
                    for key, value in evidence.items()
                    if key in {"path", "sha256", "width_dp", "height_dp"}
                },
            }
            for resource, evidence in sorted(manifest_assets.items())
        ],
        "component_definitions": sorted(
            component_definitions.values(), key=lambda item: item["id"]
        ),
        "layout_relationships": layout_relationships,
        "runtime_asset_rules": runtime_asset_rules(source_root, values),
        "components": components,
        "required_fact_gate": required_fact_gate(components),
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
    except ImportError as error:
        raise RealPageError(
            "Pillow is unavailable in the current Python interpreter "
            f"({sys.executable}); run this high-fidelity capture with an interpreter "
            "where `import PIL` succeeds"
        ) from error
    image = Image.open(screenshot_path).convert("RGB")
    runtime_by_id = {component["id"]: component for component in runtime_components}
    sampled = 0

    def inherits_parent_pixels(
        component: dict[str, Any], dominant: tuple[int, int, int]
    ) -> bool:
        parent = runtime_by_id.get(component.get("parent_id", ""))
        parent_bounds = parent.get("bounds_px") if isinstance(parent, dict) else None
        bounds = component["bounds_px"]
        if not isinstance(parent_bounds, dict):
            return False
        child_left = bounds["x"]
        child_top = bounds["y"]
        child_right = child_left + bounds["width"]
        child_bottom = child_top + bounds["height"]
        parent_left = parent_bounds["x"]
        parent_top = parent_bounds["y"]
        parent_right = parent_left + parent_bounds["width"]
        parent_bottom = parent_top + parent_bounds["height"]
        if (
            child_left < parent_left
            or child_top < parent_top
            or child_right > parent_right
            or child_bottom > parent_bottom
        ):
            return False
        sample_points: set[tuple[int, int]] = set()
        step_x = max(1, bounds["width"] // 12)
        step_y = max(1, bounds["height"] // 12)
        if child_top > parent_top:
            sample_points.update(
                (x, child_top - 1)
                for x in range(child_left, child_right, step_x)
            )
        if child_bottom < parent_bottom:
            sample_points.update(
                (x, child_bottom)
                for x in range(child_left, child_right, step_x)
            )
        if child_left > parent_left:
            sample_points.update(
                (child_left - 1, y)
                for y in range(child_top, child_bottom, step_y)
            )
        if child_right < parent_right:
            sample_points.update(
                (child_right, y)
                for y in range(child_top, child_bottom, step_y)
            )
        if len(sample_points) < 4:
            return False
        matching = sum(
            color_distance(image.getpixel(point), dominant) <= 8
            for point in sample_points
        )
        return matching / len(sample_points) >= 0.8

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
            border_band = min(8, max(1, min(crop.width, crop.height) // 8))
            border_pixels = [
                pixels[x, y]
                for y in range(crop.height)
                for x in range(crop.width)
                if (
                    x < border_band
                    or y < border_band
                    or x >= crop.width - border_band
                    or y >= crop.height - border_band
                )
                and color_distance(pixels[x, y], dominant) >= 24
            ]
            border_area = max(
                1,
                2 * border_band * (crop.width + crop.height - 2 * border_band),
            )
            if len(border_pixels) / border_area >= 0.05:
                border_color, _border_count = Counter(border_pixels).most_common(1)[0]
                top_flags = [
                    any(
                        color_distance(pixels[x, y], border_color) <= 8
                        for y in range(border_band)
                    )
                    for x in range(crop.width)
                ]
                run_count = 0
                in_run = False
                for flag in top_flags:
                    if flag and not in_run:
                        run_count += 1
                    in_run = flag
                border_style = "dashed" if run_count >= 3 else "solid"
                component["style"]["surface"]["border"] = {
                    "width_dp": round(max(1, min(3, border_band // 2)) / density, 3),
                    "color": "#FF" + "".join(f"{channel:02X}" for channel in border_color),
                    "style": border_style,
                    **({"dash_dp": [4.0, 4.0]} if border_style == "dashed" else {}),
                }
                pixel_paths.append("style.surface.border")
                if border_style == "dashed":
                    component["style"]["surface"]["corner_radius_dp"] = {
                        "top_left": 10.0,
                        "top_right": 10.0,
                        "bottom_right": 10.0,
                        "bottom_left": 10.0,
                    }
                    pixel_paths.append("style.surface.corner_radius_dp")
            shadow_pad = min(24, bounds["x"], bounds["y"], image.width - bounds["x"] - bounds["width"], image.height - bounds["y"] - bounds["height"])
            if shadow_pad >= 4 and bounds["width"] >= image.width * 0.5:
                outer = image.crop((
                    bounds["x"] - shadow_pad,
                    bounds["y"] - shadow_pad,
                    bounds["x"] + bounds["width"] + shadow_pad,
                    bounds["y"] + bounds["height"] + shadow_pad,
                ))
                outer_pixels = outer.load()
                shadow_ring = [
                    outer_pixels[x, y]
                    for y in range(outer.height)
                    for x in range(outer.width)
                    if (
                        x < shadow_pad
                        or y < shadow_pad
                        or x >= outer.width - shadow_pad
                        or y >= outer.height - shadow_pad
                    )
                ]
                darker_fraction = sum(
                    sum(pixel) / 3 < 248 for pixel in shadow_ring
                ) / max(1, len(shadow_ring))
                if darker_fraction >= 0.2:
                    component["style"]["surface"]["shadows"] = [{
                        "color": "#1A000000",
                        "offset_x_dp": 0.0,
                        "offset_y_dp": 4.0,
                        "blur_radius_dp": 12.0,
                        "spread_radius_dp": 0.0,
                    }]
                    pixel_paths.append("style.surface.shadows")
                    sampled_radius = component["style"]["surface"].get("corner_radius_dp")
                    if isinstance(sampled_radius, dict):
                        radius = max(float(value) for value in sampled_radius.values())
                        component["style"]["surface"]["corner_radius_dp"] = {
                            edge: radius
                            for edge in ("top_left", "top_right", "bottom_right", "bottom_left")
                        }
            pixel_paths.append("style.surface.background")
        elif (
            dominant_count > bounds["width"] * bounds["height"] * 0.25
            and not inherits_parent_pixels(component, dominant)
        ):
            component["style"]["surface"]["background"] = {
                "type": "solid",
                "color": "#FF" + "".join(f"{channel:02X}" for channel in dominant),
            }
            pixel_paths.append("style.surface.background")
            parent = runtime_by_id.get(component.get("parent_id", ""))
            parent_bounds = parent.get("bounds_px") if isinstance(parent, dict) else None
            if (
                isinstance(parent_bounds, dict)
                and bounds["x"] == parent_bounds["x"]
                and bounds["width"] == parent_bounds["width"]
            ):
                sample_x = sorted({
                    bounds["x"],
                    bounds["x"] + bounds["width"] // 4,
                    bounds["x"] + bounds["width"] // 2,
                    bounds["x"] + (bounds["width"] * 3) // 4,
                    bounds["x"] + bounds["width"] - 1,
                })

                def row_matches(row: int) -> bool:
                    return sum(
                        color_distance(image.getpixel((x, row)), dominant) <= 8
                        for x in sample_x
                    ) >= max(1, len(sample_x) - 2)

                top = bounds["y"]
                bottom = bounds["y"] + bounds["height"]
                while top > parent_bounds["y"] and row_matches(top - 1):
                    top -= 1
                parent_bottom = parent_bounds["y"] + parent_bounds["height"]
                while bottom < parent_bottom and row_matches(bottom):
                    bottom += 1
                if top != bounds["y"] or bottom != bounds["y"] + bounds["height"]:
                    component["visual_bounds_px"] = {
                        "x": bounds["x"],
                        "y": top,
                        "width": bounds["width"],
                        "height": bottom - top,
                    }
                    component["visual_bounds_dp"] = {
                        name: round(value / density, 3)
                        for name, value in component["visual_bounds_px"].items()
                    }
        if pixel_paths:
            component["pixel_provenance_paths"] = pixel_paths
            sampled += 1
    return {
        "available": True,
        "method": "component-bounded exact-color frequency and contrast sampling",
        "sampled_component_count": sampled,
    }


def screenshot_surface_regions(
    screenshot_path: Path,
    dimensions: tuple[int, int],
    density: float,
) -> list[dict[str, Any]]:
    """Find large screenshot-proven surfaces omitted by the runtime tree.

    Accessibility trees often flatten a project Card into its text/control
    descendants.  This detector retains only long, centered, solid-color runs;
    source-component ownership is established separately before a region enters
    the page snapshot.
    """
    from PIL import Image, ImageChops

    image = Image.open(screenshot_path).convert("RGB")
    width, height = dimensions
    if image.size != dimensions:
        raise RealPageError("screenshot dimensions changed during surface analysis")
    pixels = image.load()
    pixel_data = image.get_flattened_data() if hasattr(image, "get_flattened_data") else image.getdata()
    common_colors = [
        color
        for color, count in Counter(pixel_data).most_common(12)
        if count >= width * height * 0.01
    ]
    minimum_run = round(width * 0.5)
    maximum_run = round(width * 0.95)
    maximum_gap = round(80 * density)
    boundary_tolerance = round(width * 0.1)
    candidates: list[dict[str, Any]] = []

    for color in common_colors:
        difference = ImageChops.difference(
            image, Image.new("RGB", image.size, color)
        )
        channel_masks = [
            channel.point([255, 255, 255] + [0] * 253)
            for channel in difference.split()
        ]
        color_mask = ImageChops.multiply(
            ImageChops.multiply(channel_masks[0], channel_masks[1]),
            channel_masks[2],
        ).tobytes()
        groups: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for y in range(height):
            row = color_mask[y * width:(y + 1) * width]
            best = max(
                re.finditer(b"\xff+", row),
                key=lambda match: match.end() - match.start(),
                default=None,
            )
            best_left = best.start() if best is not None else 0
            best_right = best.end() if best is not None else 0
            run_width = best_right - best_left
            centered = abs((best_left + best_right) / 2 - width / 2) <= width * 0.12
            bounded = best_left >= width * 0.02 and best_right <= width * 0.98
            edge_anchor = (
                "left"
                if best_left <= width * 0.02 and run_width >= minimum_run
                else "right"
                if best_right >= width * 0.98 and run_width >= minimum_run
                else None
            )
            qualifies = (
                minimum_run <= run_width <= maximum_run and centered and bounded
            ) or edge_anchor is not None
            if not qualifies:
                continue
            if (
                current is None
                or y - current["last_y"] > maximum_gap
                or edge_anchor != current["edge_anchor"]
                or abs(best_left - current["reference_left"]) > boundary_tolerance
                or abs(best_right - current["reference_right"]) > boundary_tolerance
            ):
                if current is not None:
                    groups.append(current)
                current = {
                    "first_y": y,
                    "last_y": y,
                    "left": best_left,
                    "right": best_right,
                    "reference_left": best_left,
                    "reference_right": best_right,
                    "first_left": best_left,
                    "qualified_rows": 1,
                    "edge_anchor": edge_anchor,
                }
            else:
                current["last_y"] = y
                current["left"] = min(current["left"], best_left)
                current["right"] = max(current["right"], best_right)
                current["qualified_rows"] += 1
                if current["qualified_rows"] == 8:
                    current["reference_left"] = best_left
                    current["reference_right"] = best_right
        if current is not None:
            groups.append(current)

        for group in groups:
            region_height = group["last_y"] - group["first_y"] + 1
            region_width = group["right"] - group["left"]
            if region_height < round(40 * density) or group["qualified_rows"] < round(8 * density):
                continue
            radius = max(
                0.0,
                min(24.0, round(2 * max(0, group["first_left"] - group["left"]) / density, 3)),
            )
            candidate = {
                "bounds_px": {
                    "x": group["left"],
                    "y": group["first_y"],
                    "width": region_width,
                    "height": region_height,
                },
                "background": "#FF" + "".join(f"{channel:02X}" for channel in color),
                "corner_radius_dp": radius,
                "qualified_rows": group["qualified_rows"],
            }
            if group["edge_anchor"] is not None:
                candidate["edge_anchor"] = group["edge_anchor"]
            candidates.append(candidate)

    def intersection_over_union(left: dict[str, int], right: dict[str, int]) -> float:
        left_x2, left_y2 = left["x"] + left["width"], left["y"] + left["height"]
        right_x2, right_y2 = right["x"] + right["width"], right["y"] + right["height"]
        intersection = max(0, min(left_x2, right_x2) - max(left["x"], right["x"])) * max(
            0, min(left_y2, right_y2) - max(left["y"], right["y"])
        )
        union = left["width"] * left["height"] + right["width"] * right["height"] - intersection
        return intersection / union if union else 0.0

    def refine_vertical_bounds(candidate: dict[str, Any]) -> None:
        bounds = candidate["bounds_px"]
        color = tuple(
            int(candidate["background"][index:index + 2], 16)
            for index in (3, 5, 7)
        )
        search_pad = round(64 * density)
        search_top = max(0, bounds["y"] - search_pad)
        search_bottom = min(height, bounds["y"] + bounds["height"] + search_pad)
        candidate_top = bounds["y"]
        candidate_bottom = bounds["y"] + bounds["height"]
        candidate_height = bounds["height"]
        segments: list[tuple[int, int, int]] = []
        maximum_internal_gap = max(2, round(4 * density))
        probe_fractions = (
            (0.01, 0.05, 0.1, 0.25, 0.4)
            if candidate.get("edge_anchor") == "left"
            else (0.6, 0.75, 0.9, 0.95, 0.99)
            if candidate.get("edge_anchor") == "right"
            else (0.25, 0.4, 0.5, 0.6, 0.75)
        )
        for fraction in probe_fractions:
            probe_x = bounds["x"] + round(bounds["width"] * fraction)
            start: int | None = None
            last_match: int | None = None
            for row in range(search_top, search_bottom + 1):
                matches = (
                    row < search_bottom
                    and color_distance(pixels[probe_x, row], color) <= 2
                )
                if matches and start is None:
                    start = row
                    last_match = row
                elif matches:
                    last_match = row
                elif (
                    start is not None
                    and last_match is not None
                    and row - last_match > maximum_internal_gap
                ):
                    end = last_match + 1
                    overlap = max(0, min(end, candidate_bottom) - max(start, candidate_top))
                    if (
                        overlap >= candidate_height * 0.6
                        and end - start >= candidate_height * 0.75
                        and end - start <= candidate_height + round(64 * density)
                    ):
                        segments.append((start, end, overlap))
                    start = None
                    last_match = None
        if not segments:
            return
        refined_top, refined_bottom, _ = max(
            segments,
            key=lambda segment: (
                segment[2],
                segment[1] - segment[0],
                -abs(segment[0] - candidate_top),
            ),
        )
        bounds["y"] = refined_top
        bounds["height"] = refined_bottom - refined_top
        inset_x = max(1, round(bounds["width"] * 0.1))
        inset_y = max(1, round(bounds["height"] * 0.1))
        interior = image.crop((
            bounds["x"] + inset_x,
            bounds["y"] + inset_y,
            bounds["x"] + bounds["width"] - inset_x,
            bounds["y"] + bounds["height"] - inset_y,
        ))
        interior_pixels = (
            interior.get_flattened_data()
            if hasattr(interior, "get_flattened_data")
            else interior.getdata()
        )
        interior_color, _ = Counter(interior_pixels).most_common(1)[0]
        candidate["background"] = "#FF" + "".join(
            f"{channel:02X}" for channel in interior_color
        )

    for candidate in candidates:
        refine_vertical_bounds(candidate)

    deduplicated: list[dict[str, Any]] = []
    for candidate in sorted(
        candidates,
        key=lambda item: (
            -item["qualified_rows"],
            -(item["bounds_px"]["width"] * item["bounds_px"]["height"]),
        ),
    ):
        if any(
            intersection_over_union(candidate["bounds_px"], existing["bounds_px"]) >= 0.75
            for existing in deduplicated
        ):
            continue
        deduplicated.append(candidate)
    return deduplicated


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


def stable_runtime_fallback_key(component: dict[str, Any]) -> str | None:
    runtime_key = runtime_semantic_key(component)
    if not isinstance(runtime_key, str):
        return None
    generated_key_patterns = (
        r"runtime\.[0-9a-f]{20}",
        r"runtime\.(?:asset|progress)\.[0-9a-f]{20}",
        r"[A-Za-z0-9_.:@#-]+__instance_[A-Za-z0-9_.:@#-]+",
        r"[A-Za-z0-9_.:@#-]+__surface_[0-9a-f]{20}",
    )
    return runtime_key if any(
        re.fullmatch(pattern, runtime_key)
        for pattern in generated_key_patterns
    ) else None


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
    identified_runtime_ids = {
        runtime["id"]
        for runtime in runtime_components
        if isinstance(runtime_semantic_key(runtime), str)
    }
    source_to_runtime = dict(explicit_source_to_runtime or {})
    used_runtime = set(source_to_runtime.values())
    mapping_methods = {source_id: "explicit_runtime_source_map" for source_id in source_to_runtime}
    checks = {
        "explicit_runtime_source_map_matches": len(source_to_runtime),
        "stable_runtime_id_matches": 0,
        "exact_text_matches": 0,
        "exact_content_description_matches": 0,
        "scoped_hierarchy_order_matches": 0,
        "same_row_dynamic_text_matches": 0,
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
            and runtime["id"] not in identified_runtime_ids
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

    # Dynamic labels and fields often have no stable runtime ID. Resolve them only inside a
    # mapped source/runtime boundary, preserving compatible preorder and never crossing a nested
    # mapped boundary. Run this again after common-ancestor discovery because flattened runtime
    # trees may not expose a usable container until their static leaves have been joined.
    def match_scoped_hierarchy_order() -> None:
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
                and item not in identified_runtime_ids
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
                    if (
                        isinstance(source_text, str)
                        and isinstance(runtime_text, str)
                        and source_text != runtime_text
                    ):
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

    def source_business_owner(component_id: str) -> str:
        current = component_id
        root_id = component_id
        while current in source_by_id:
            source = source_by_id[current]
            root_id = current
            if source["source"]["custom_component"]:
                return current
            parent_id = source.get("parent_id")
            if not isinstance(parent_id, str):
                break
            current = parent_id
        return root_id

    def match_business_anchor_order() -> None:
        source_order = {component["id"]: index for index, component in enumerate(source_components)}
        runtime_order = {component["id"]: index for index, component in enumerate(runtime_components)}
        changed = True
        while changed:
            changed = False
            mapped_source_ids = set(source_to_runtime)
            for source in source_components:
                source_id = source["id"]
                if (
                    source_id in source_to_runtime
                    or source_id in excluded_source_ids
                    or source["source"]["custom_component"]
                    or not semantic_source_component(source)
                ):
                    continue
                owner_id = source_business_owner(source_id)
                preceding_anchors = [
                    anchor_id
                    for anchor_id in mapped_source_ids
                    if source_business_owner(anchor_id) == owner_id
                    and source_order[anchor_id] < source_order[source_id]
                    and semantic_source_component(source_by_id[anchor_id])
                ]
                if not preceding_anchors:
                    continue
                previous_source_id = max(preceding_anchors, key=source_order.get)
                previous_runtime_index = runtime_order[source_to_runtime[previous_source_id]]
                following_anchors = [
                    anchor_id
                    for anchor_id in mapped_source_ids
                    if source_order[anchor_id] > source_order[source_id]
                    and runtime_order[source_to_runtime[anchor_id]] > previous_runtime_index
                ]
                next_runtime_index = (
                    runtime_order[source_to_runtime[min(following_anchors, key=source_order.get)]]
                    if following_anchors
                    else len(runtime_components)
                )
                candidates = [
                    runtime
                    for runtime in runtime_components
                    if runtime["id"] not in used_runtime
                    and runtime["id"] not in identified_runtime_ids
                    and previous_runtime_index < runtime_order[runtime["id"]] < next_runtime_index
                    and semantic_runtime_component(runtime)
                    and source_runtime_type_compatible(source["type"], runtime)
                ]
                source_text = source["style"]["content"].get("text")
                if isinstance(source_text, str):
                    candidates = [
                        runtime
                        for runtime in candidates
                        if runtime["style"]["content"].get("text") == source_text
                    ]
                if len(candidates) != 1:
                    continue
                runtime = candidates[0]
                source_to_runtime[source_id] = runtime["id"]
                used_runtime.add(runtime["id"])
                mapping_methods[source_id] = "scoped_hierarchy_order"
                checks["scoped_hierarchy_order_matches"] += 1
                changed = True
                break

    def match_same_row_dynamic_text() -> None:
        for source in source_components:
            source_id = source["id"]
            parent_id = source.get("parent_id")
            parent = source_by_id.get(parent_id or "")
            if (
                source_id in source_to_runtime
                or source_id in excluded_source_ids
                or source["source"]["custom_component"]
                or source["type"] not in {"Text", "BasicText", "ClickableText"}
                or source["style"]["content"].get("text") is not None
                or not any(
                    item.get("path") == "style.content.text"
                    for item in source.get("unresolved", [])
                )
                or parent is None
                or parent["type"] != "Row"
            ):
                continue

            sibling_ids = parent["children_ids"]
            source_index = sibling_ids.index(source_id)
            anchors = [
                (sibling_ids.index(sibling_id), runtime_by_id[source_to_runtime[sibling_id]])
                for sibling_id in sibling_ids
                if sibling_id in source_to_runtime
                and source_by_id[sibling_id]["type"] in {"Text", "BasicText", "ClickableText"}
            ]
            if not anchors:
                continue
            runtime_parent_ids = {anchor.get("parent_id") for _index, anchor in anchors}
            if len(runtime_parent_ids) != 1 or None in runtime_parent_ids:
                continue
            runtime_parent_id = next(iter(runtime_parent_ids))

            def vertically_aligned(candidate: dict[str, Any]) -> bool:
                candidate_bounds = candidate.get("bounds_px")
                if not isinstance(candidate_bounds, dict):
                    return False
                candidate_top = candidate_bounds.get("y")
                candidate_height = candidate_bounds.get("height")
                if not isinstance(candidate_top, (int, float)) or not isinstance(
                    candidate_height, (int, float)
                ) or candidate_height <= 0:
                    return False
                candidate_bottom = candidate_top + candidate_height
                for _index, anchor in anchors:
                    anchor_bounds = anchor.get("bounds_px")
                    if not isinstance(anchor_bounds, dict):
                        return False
                    anchor_top = anchor_bounds.get("y")
                    anchor_height = anchor_bounds.get("height")
                    if not isinstance(anchor_top, (int, float)) or not isinstance(
                        anchor_height, (int, float)
                    ) or anchor_height <= 0:
                        return False
                    overlap = min(candidate_bottom, anchor_top + anchor_height) - max(
                        candidate_top, anchor_top
                    )
                    if overlap < min(candidate_height, anchor_height) * 0.5:
                        return False
                return True

            def horizontally_ordered(candidate: dict[str, Any]) -> bool:
                candidate_bounds = candidate.get("bounds_px")
                if not isinstance(candidate_bounds, dict):
                    return False
                candidate_x = candidate_bounds.get("x")
                if not isinstance(candidate_x, (int, float)):
                    return False
                for anchor_index, anchor in anchors:
                    anchor_bounds = anchor.get("bounds_px")
                    anchor_x = anchor_bounds.get("x") if isinstance(anchor_bounds, dict) else None
                    if not isinstance(anchor_x, (int, float)):
                        return False
                    if anchor_index < source_index and candidate_x < anchor_x:
                        return False
                    if anchor_index > source_index and candidate_x > anchor_x:
                        return False
                return True

            candidates = [
                runtime
                for runtime in runtime_components
                if runtime["id"] not in used_runtime
                and runtime["id"] not in identified_runtime_ids
                and runtime.get("parent_id") == runtime_parent_id
                and source_runtime_type_compatible(source["type"], runtime)
                and semantic_runtime_component(runtime)
                and vertically_aligned(runtime)
                and horizontally_ordered(runtime)
            ]
            if len(candidates) != 1:
                continue
            runtime = candidates[0]
            source_to_runtime[source_id] = runtime["id"]
            used_runtime.add(runtime["id"])
            mapping_methods[source_id] = "same_row_dynamic_text"
            checks["same_row_dynamic_text_matches"] += 1

    match_scoped_hierarchy_order()
    match_same_row_dynamic_text()

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
        if runtime["id"] not in used_runtime
        and runtime["id"] not in identified_runtime_ids
        and runtime["type"] == "TextField"
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
            if runtime["id"] not in used_runtime
            and runtime["id"] not in identified_runtime_ids
            and source_runtime_type_compatible(source["type"], runtime)
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
            # One mapped leaf is not enough evidence to identify a platform container as
            # the corresponding source container.  That guess can turn a full-screen
            # Android View into a business component and hide unrelated siblings in the
            # generated Stack.  Require a real common ancestor relationship instead.
            if len(set(mapped_descendants)) < 2:
                continue
            candidate_id = lowest_common_runtime_ancestor(mapped_descendants, runtime_by_id)
            if candidate_id in mapped_descendants:
                candidate_id = runtime_by_id[candidate_id].get("parent_id")
            if (
                candidate_id is not None
                and candidate_id not in used_runtime
                and candidate_id not in identified_runtime_ids
                and source_runtime_type_compatible(source["type"], runtime_by_id[candidate_id])
            ):
                source_to_runtime[source_id] = candidate_id
                used_runtime.add(candidate_id)
                mapping_methods[source_id] = "hierarchy_common_ancestor"
                checks["hierarchy_matches"] += 1
                changed = True

    match_business_anchor_order()

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
    return [
        str(item["path"])
        for item in component.get("required_facts") or []
        if isinstance(item, dict) and item.get("status") == "unresolved"
    ]


def dp_bounds(bounds: dict[str, int], density: float) -> dict[str, float]:
    return {name: round(value / density, 3) for name, value in bounds.items()}


def clip_projected_layout_bounds(
    layout_bounds: dict[str, float], content_bounds: dict[str, float]
) -> dict[str, float] | None:
    left = max(layout_bounds["x"], content_bounds["x"])
    top = max(layout_bounds["y"], content_bounds["y"])
    right = min(
        layout_bounds["x"] + layout_bounds["width"],
        content_bounds["x"] + content_bounds["width"],
    )
    bottom = min(
        layout_bounds["y"] + layout_bounds["height"],
        content_bounds["y"] + content_bounds["height"],
    )
    if right <= left or bottom <= top:
        return None
    return {
        "x": round(left, 3),
        "y": round(top, 3),
        "width": round(right - left, 3),
        "height": round(bottom - top, 3),
    }


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

    source_root_ids = [item["id"] for item in source_components if item["parent_id"] is None]
    observed_source_root_ids = [
        root_id
        for root_id in source_root_ids
        if any(source_id in mapped_source_ids for source_id in (root_id, *source_descendants(root_id, source_by_id)))
    ]
    active_source_ids: set[str] = set()
    for root_id in observed_source_root_ids:
        active_source_ids.add(root_id)
        active_source_ids.update(source_descendants(root_id, source_by_id))
    if not active_source_ids:
        active_source_ids.update(source_by_id)
    selected_source_root_ids = observed_source_root_ids or source_root_ids

    active_source_ids.difference_update(inactive_source_ids | elided_source_ids)
    source_node_kinds: dict[str, str] = {}
    for source in source_components:
        source_id = source["id"]
        if source_id not in active_source_ids:
            continue
        if source["parent_id"] is None:
            kind = "screen_root"
        elif source["component_kind"] == "project_component":
            kind = "project_component"
        elif source["component_kind"] == "third_party_component":
            kind = "third_party_component"
        elif source["component_kind"] == "platform_component":
            kind = "platform_component"
        elif source["component_kind"] == "custom_draw":
            kind = "custom_draw"
        elif source["type"] == "content":
            kind = "content_slot"
        elif source["type"] in SOURCE_LAYOUT_PRIMITIVES:
            kind = "layout_primitive"
        else:
            kind = "visual_primitive"
        source_node_kinds[source_id] = kind

    business_source_ids = {
        source_id
        for source_id, kind in source_node_kinds.items()
        if kind in {"screen_root", "project_component"}
    }

    def source_business_path(source_id: str) -> list[str]:
        path: list[str] = []
        current: str | None = source_id
        while isinstance(current, str) and current in source_by_id:
            if current in business_source_ids:
                path.append(current)
            current = source_by_id[current]["parent_id"]
        path.reverse()
        return path

    business_parent_by_source: dict[str, str | None] = {}
    business_children_by_source: dict[str | None, list[str]] = defaultdict(list)
    for source in source_components:
        source_id = source["id"]
        if source_id not in business_source_ids:
            continue
        path = source_business_path(source_id)
        parent_id = path[-2] if len(path) >= 2 else None
        business_parent_by_source[source_id] = parent_id
        business_children_by_source[parent_id].append(source_id)

    source_tree_components: list[dict[str, Any]] = []
    for source in source_components:
        source_id = source["id"]
        if source_id not in active_source_ids:
            continue
        parent_id = source["parent_id"] if source["parent_id"] in active_source_ids else None
        children_ids = [child_id for child_id in source["children_ids"] if child_id in active_source_ids]
        runtime_id = source_to_runtime.get(source_id)
        method = mapping_methods.get(source_id)
        runtime_instances = []
        if runtime_id is not None:
            runtime_instances.append({
                "runtime_component_id": runtime_id,
                "mapping_method": method,
                "mapping_status": (
                    "proven"
                    if method in {"stable_runtime_id", "explicit_runtime_source_map"}
                    else "candidate"
                ),
            })
        source_tree_components.append({
            "id": source_id,
            "semantic_key": source["semantic_key"],
            "type": source["type"],
            "definition_id": source["definition_id"],
            "component_kind": source["component_kind"],
            "node_kind": source_node_kinds[source_id],
            "parent_id": parent_id,
            "children_ids": children_ids,
            "business_parent_id": business_parent_by_source.get(source_id),
            "business_owner_id": (
                source_id
                if source_id in business_source_ids
                else source_business_path(source_id)[-1]
                if source_business_path(source_id)
                else None
            ),
            "business_children_ids": business_children_by_source.get(source_id, []),
            "sibling_index": (
                [child_id for child_id in source_by_id[parent_id]["children_ids"] if child_id in active_source_ids].index(source_id)
                if parent_id is not None
                else selected_source_root_ids.index(source_id)
                if source_id in selected_source_root_ids
                else 0
            ),
            "capture_membership": "observed_instance" if runtime_id is not None else "candidate_active_descendant",
            "source": copy.deepcopy(source["source"]),
            "arguments": copy.deepcopy(source["arguments"]),
            "modifiers": copy.deepcopy(source["modifiers"]),
            "slot_argument_name": source.get("slot_argument_name"),
            "slot_invocation": copy.deepcopy(source.get("slot_invocation")),
            "style": copy.deepcopy(source["style"]),
            "provenance": copy.deepcopy(source["provenance"]),
            "unresolved": copy.deepcopy(source["unresolved"]),
            "required_facts": copy.deepcopy(source.get("required_facts") or []),
            "runtime_instances": runtime_instances,
            "runtime_descendant_ids": [
                source_to_runtime[descendant_id]
                for descendant_id in (source_id, *source_descendants(source_id, source_by_id))
                if descendant_id in source_to_runtime
            ],
        })

    source_text_typography_candidates = [
        item
        for item in source_tree_components
        if item["type"] in {"Text", "BasicText", "ClickableText"}
        and item["style"]["typography"]["font_size_sp"] is not None
    ]
    candidate_typography_fields = (
        "font_size_sp", "font_weight", "font_style", "font_family",
        "letter_spacing_sp", "line_height_sp", "text_align", "max_lines",
        "overflow", "decoration",
    )

    def candidate_text_typography(
        runtime: dict[str, Any],
        business_owner_id: str | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        if runtime["type"] != "Text" or not source_text_typography_candidates:
            return None, None
        runtime_color = runtime["style"]["typography"].get("color")
        candidates = source_text_typography_candidates
        if isinstance(business_owner_id, str):
            candidates = [
                item
                for item in candidates
                if item.get("business_owner_id") == business_owner_id
            ]
            if not candidates:
                return None, None
        color_matches = [
            item
            for item in candidates
            if runtime_color is not None
            and item["style"]["typography"].get("color") == runtime_color
        ]
        if color_matches:
            candidates = color_matches
        runtime_height = runtime["bounds_px"]["height"] / density

        def expected_height(item: dict[str, Any]) -> float:
            typography = item["style"]["typography"]
            line_height = typography.get("line_height_sp")
            if line_height is not None:
                return float(line_height) * font_scale
            return float(typography["font_size_sp"]) * font_scale * 1.4

        selected = min(
            candidates,
            key=lambda item: (
                abs(expected_height(item) - runtime_height),
                abs(float(item["style"]["typography"]["font_size_sp"]) - runtime_height),
                item["semantic_key"],
            ),
        )
        return copy.deepcopy(selected["style"]["typography"]), selected["semantic_key"]

    semantic_runtime_ids = {
        item["id"] for item in runtime_components if semantic_runtime_component(item)
    }
    runtime_by_id = {item["id"]: item for item in runtime_components}
    visual_surface_ids: set[str] = set()
    for runtime in runtime_components:
        if runtime["id"] in semantic_runtime_ids:
            continue
        background = runtime["style"]["surface"].get("background")
        parent = runtime_by_id.get(runtime.get("parent_id", ""))
        parent_background = (
            parent["style"]["surface"].get("background")
            if isinstance(parent, dict)
            else None
        )
        if (
            isinstance(background, dict)
            and background.get("type") == "solid"
            and isinstance(parent_background, dict)
            and parent_background.get("type") == "solid"
            and background.get("color") != parent_background.get("color")
            and runtime["bounds_px"]["width"] >= dimensions[0] * 0.5
        ):
            visual_surface_ids.add(runtime["id"])
    visual_runtime_ids = set(runtime_to_source) | semantic_runtime_ids | visual_surface_ids

    def nearest_visual_runtime_ancestor(runtime_id: str) -> str | None:
        parent_id = runtime_by_id[runtime_id].get("parent_id")
        while isinstance(parent_id, str) and parent_id in runtime_by_id:
            if parent_id in visual_runtime_ids:
                return parent_id
            parent_id = runtime_by_id[parent_id].get("parent_id")
        return None

    visual_parent_by_runtime = {
        runtime_id: nearest_visual_runtime_ancestor(runtime_id)
        for runtime_id in visual_runtime_ids
    }
    visual_children_by_runtime: dict[str | None, list[str]] = defaultdict(list)
    for runtime in runtime_components:
        if runtime["id"] in visual_runtime_ids:
            visual_children_by_runtime[visual_parent_by_runtime[runtime["id"]]].append(runtime["id"])

    def common_business_path(paths: list[list[str]]) -> list[str]:
        if not paths:
            return []
        prefix = list(paths[0])
        for path in paths[1:]:
            shared_length = 0
            for left, right in zip(prefix, path):
                if left != right:
                    break
                shared_length += 1
            prefix = prefix[:shared_length]
            if not prefix:
                break
        return prefix

    component_context_by_runtime: dict[str, dict[str, Any]] = {}
    for runtime in runtime_components:
        runtime_id = runtime["id"]
        if runtime_id not in visual_runtime_ids:
            continue
        source_id = runtime_to_source.get(runtime_id)
        if source_id is not None:
            method = mapping_methods[source_id]
            business_path = source_business_path(source_id)
            component_context_by_runtime[runtime_id] = {
                "status": (
                    "proven"
                    if method in {"stable_runtime_id", "explicit_runtime_source_map"}
                    else "candidate"
                ),
                "method": method,
                "source_component_id": source_id,
                "business_component_id": business_path[-1] if business_path else None,
                "business_component_path": business_path,
                "evidence_runtime_ids": [runtime_id],
            }
            continue

        descendant_paths: list[list[str]] = []
        descendant_evidence: list[str] = []
        for descendant_id in tree_descendants(runtime_id, runtime_by_id):
            descendant_source_id = runtime_to_source.get(descendant_id)
            if descendant_source_id is None:
                continue
            if mapping_methods.get(descendant_source_id) == "hierarchy_common_ancestor":
                continue
            path = source_business_path(descendant_source_id)
            if path:
                descendant_paths.append(path)
                descendant_evidence.append(descendant_id)
        business_path = common_business_path(descendant_paths)
        method = "runtime_descendant_source_context"
        evidence_runtime_ids = descendant_evidence
        if not business_path:
            parent_id = visual_parent_by_runtime[runtime_id]
            parent_context = component_context_by_runtime.get(parent_id or "")
            if isinstance(parent_context, dict) and parent_context.get("business_component_path"):
                business_path = list(parent_context["business_component_path"])
                method = "runtime_parent_component_context"
                evidence_runtime_ids = list(parent_context["evidence_runtime_ids"])
        component_context_by_runtime[runtime_id] = {
            "status": "candidate" if business_path else "unbound",
            "method": method if business_path else "no_component_context",
            "source_component_id": None,
            "business_component_id": business_path[-1] if business_path else None,
            "business_component_path": business_path,
            "evidence_runtime_ids": evidence_runtime_ids,
        }

    output_components: list[dict[str, Any]] = []
    for runtime in runtime_components:
        if runtime["id"] not in visual_runtime_ids:
            continue
        source = source_by_id.get(runtime_to_source.get(runtime["id"], ""))
        runtime_style = copy.deepcopy(runtime["style"])
        pixel_provenance_paths = list(runtime.get("pixel_provenance_paths", []))
        if source is not None and mapping_methods.get(source["id"]) == "hierarchy_common_ancestor":
            runtime_style["surface"]["background"] = None
            runtime_style["surface"]["corner_radius_dp"] = None
            pixel_provenance_paths = [
                path
                for path in pixel_provenance_paths
                if path not in {"style.surface.background", "style.surface.corner_radius_dp"}
            ]
        if (
            source is not None
            and source["type"] in {"Image", "Icon", "AsyncImage"}
            and runtime["type"] != "Image"
            and runtime.get("runtime_class") == "android.view.View"
        ):
            runtime_style["surface"]["background"] = None
            pixel_provenance_paths = [
                path for path in pixel_provenance_paths if not path.startswith("style.surface.background")
            ]
        if source is not None and source["type"] in {"Checkbox", "CheckBox", "Switch", "RadioButton"}:
            runtime_style["surface"]["background"] = None
            runtime_style["surface"]["corner_radius_dp"] = None
            pixel_provenance_paths = [
                path
                for path in pixel_provenance_paths
                if path not in {"style.surface.background", "style.surface.corner_radius_dp"}
            ]
        merged_style = (
            merge_style(source["style"], runtime_style)
            if source is not None
            else runtime_style
        )
        candidate_typography_key: str | None = None
        candidate_typography_paths: list[str] = []
        if source is None:
            candidate_typography, candidate_typography_key = candidate_text_typography(
                runtime,
                component_context_by_runtime[runtime["id"]].get("business_component_id"),
            )
            if candidate_typography is not None:
                for field in candidate_typography_fields:
                    value = candidate_typography.get(field)
                    if merged_style["typography"].get(field) is None and value is not None:
                        merged_style["typography"][field] = value
                        candidate_typography_paths.append(f"style.typography.{field}")
        component_source_facts = resolved_source_facts.get(source["id"], []) if source is not None else []
        for fact in component_source_facts:
            existing = path_value(merged_style, fact["path"])
            if existing is not None and existing != fact["value"]:
                raise RealPageError(
                    f"resolved source fact conflicts with existing value: {source['semantic_key']} {fact['path']}"
                )
            set_path_value(merged_style, fact["path"], fact["value"])
        source_unresolved = copy.deepcopy(source["unresolved"]) if source is not None else [{
            "path": "source_binding",
            "expression": str(runtime.get("runtime_class") or runtime["type"]),
            "reason": "visible runtime component is preserved for visual generation but is not yet bound to one source component",
        }]
        source_unresolved = [
            unresolved
            for unresolved in source_unresolved
            if not str(unresolved.get("path", "")).startswith("style.")
            or path_value(merged_style, str(unresolved.get("path", ""))) is None
        ]
        item = {
            "id": runtime["id"],
            "type": source["type"] if source is not None else runtime["type"],
            "bounds_px": runtime["bounds_px"],
            "bounds_dp": dp_bounds(runtime["bounds_px"], density),
            "parent_id": visual_parent_by_runtime[runtime["id"]],
            "parent_mapping": (
                "source-semantic-ancestor"
                if source is not None
                and (
                    visual_parent_by_runtime[runtime["id"]] is None
                    or visual_parent_by_runtime[runtime["id"]] in runtime_to_source
                )
                else "runtime-semantic-ancestor"
            ),
            "children_ids": visual_children_by_runtime[runtime["id"]],
            "sibling_index": visual_children_by_runtime[visual_parent_by_runtime[runtime["id"]]].index(runtime["id"]),
            "style": merged_style,
            "provenance": copy.deepcopy(source["provenance"]) if source is not None else [],
            "unresolved": source_unresolved,
            "runtime_evidence": {
                "runtime_component_id": runtime["id"],
                "runtime_class": str(runtime.get("runtime_class") or runtime["type"]),
            },
            "component_context": copy.deepcopy(component_context_by_runtime[runtime["id"]]),
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
        if candidate_typography_key is not None and candidate_typography_paths:
            item["provenance"].append({
                "paths": candidate_typography_paths,
                "origin": "source_expression",
                "source": f"candidate typography role from {candidate_typography_key} selected by runtime line box",
            })
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
        runtime_key = stable_runtime_fallback_key(runtime)
        item["semantic_key"] = (
            source["semantic_key"]
            if source is not None
            else runtime_key
            if isinstance(runtime_key, str)
            else f"runtime.{hashlib.sha256(runtime['id'].encode('utf-8')).hexdigest()[:20]}"
        )
        if source is not None:
            mapping_status = component_context_by_runtime[runtime["id"]]["status"]
            item["source_mapping"] = {
                "status": mapping_status,
                "method": mapping_methods[source["id"]],
                "source_call_id": source["source"]["call_id"],
            }
            item["source"] = {
                "source": source["source"]["source"],
                "composable": source["source"]["composable"],
                "attributes": source["source"]["attributes"],
            }
        else:
            item["source_mapping"] = {
                "status": "unbound",
                "method": "runtime_visual_fallback",
            }
        output_components.append(item)

    output_by_id = {item["id"]: item for item in output_components}
    source_tree_by_id = {item["id"]: item for item in source_tree_components}

    def visual_descendant_texts(component_id: str) -> list[str]:
        ids = [component_id, *tree_descendants(component_id, output_by_id)]
        return [
            str(output_by_id[item_id]["style"]["content"]["text"])
            for item_id in ids
            if isinstance(output_by_id[item_id]["style"]["content"].get("text"), str)
        ]

    def business_path_for_owner(owner_id: str | None) -> list[str]:
        if not isinstance(owner_id, str) or owner_id not in business_source_ids:
            return []
        path: list[str] = []
        current: str | None = owner_id
        while isinstance(current, str):
            path.append(current)
            current = business_parent_by_source.get(current)
        path.reverse()
        return path

    def assign_candidate_business_context(
        component: dict[str, Any],
        business_path: list[str],
        evidence_runtime_id: str,
    ) -> None:
        if not business_path or component["source_mapping"].get("status") == "proven":
            return
        current_path = component["component_context"].get("business_component_path", [])
        if len(current_path) >= len(business_path):
            return
        component["component_context"] = {
            "status": "candidate",
            "method": "source_runtime_data_component_context",
            "source_component_id": None,
            "business_component_id": business_path[-1],
            "business_component_path": list(business_path),
            "evidence_runtime_ids": [evidence_runtime_id],
        }

    def source_visual_for_rule(rule: dict[str, Any]) -> dict[str, Any] | None:
        role = rule.get("role")
        candidates: list[dict[str, Any]] = []
        for source in source_tree_components:
            if source["type"] not in {"Image", "Icon", "AsyncImage"}:
                continue
            asset_unresolved = next(
                (
                    item
                    for item in source["unresolved"]
                    if item.get("path") == "style.asset.resource"
                ),
                None,
            )
            expression = str(asset_unresolved.get("expression", "")) if asset_unresolved else ""
            if role == "labeled_asset_object" and re.search(r"\.\s*icon\b", expression):
                candidates.append(source)
            elif role == "titled_asset_record" and source["type"] == "AsyncImage":
                candidates.append(source)
        return candidates[0] if len(candidates) == 1 else None

    def source_text_for_rule(
        rule: dict[str, Any],
        source_visual: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if source_visual is None:
            return None
        role = rule.get("role")
        expression_pattern = (
            r"\.\s*title\b"
            if role == "titled_asset_record"
            else r"\.\s*(?:uiTitle|label)\b"
            if role == "labeled_asset_object"
            else None
        )
        if expression_pattern is None:
            return None
        owner_id = source_visual.get("business_owner_id")
        candidates = []
        for source in source_text_typography_candidates:
            if source.get("business_owner_id") != owner_id:
                continue
            text_unresolved = next(
                (
                    item
                    for item in source["unresolved"]
                    if item.get("path") == "style.content.text"
                ),
                None,
            )
            if text_unresolved is not None and re.search(
                expression_pattern, str(text_unresolved.get("expression", ""))
            ):
                candidates.append(source)
        return candidates[0] if len(candidates) == 1 else None

    def apply_rule_text_typography(
        component: dict[str, Any],
        source_text: dict[str, Any] | None,
    ) -> None:
        if source_text is None or component["source_mapping"].get("status") == "proven":
            return
        component["provenance"] = [
            record
            for record in component["provenance"]
            if not (
                record.get("origin") == "source_expression"
                and str(record.get("source", "")).startswith("candidate typography role from ")
            )
        ]
        applied_paths = []
        source_typography = source_text["style"]["typography"]
        for field in candidate_typography_fields:
            value = source_typography.get(field)
            if value is not None:
                component["style"]["typography"][field] = copy.deepcopy(value)
                applied_paths.append(f"style.typography.{field}")
        if applied_paths:
            component["provenance"].append({
                "paths": applied_paths,
                "origin": "source_expression",
                "source": (
                    f"component-scoped typography from {source_text['semantic_key']} "
                    "selected by component-scoped runtime asset data"
                ),
            })

    def source_asset_label_layout(
        source_visual: dict[str, Any] | None,
    ) -> dict[str, float] | None:
        if source_visual is None:
            return None
        owner_id = source_visual.get("business_owner_id")
        current_id = source_visual["id"]
        matches: list[dict[str, float]] = []
        while current_id in source_tree_by_id:
            parent_id = source_tree_by_id[current_id].get("parent_id")
            parent = source_tree_by_id.get(parent_id or "")
            if not isinstance(parent, dict):
                break
            child_ids = [
                child_id
                for child_id in parent.get("children_ids", [])
                if child_id in source_tree_by_id
            ]
            if parent.get("type") == "Column" and current_id in child_ids:
                index = child_ids.index(current_id)
                if index + 2 < len(child_ids):
                    image_branch = source_tree_by_id[current_id]
                    spacer = source_tree_by_id[child_ids[index + 1]]
                    label_branch_id = child_ids[index + 2]
                    label_ids = [
                        label_branch_id,
                        *tree_descendants(label_branch_id, source_tree_by_id),
                    ]
                    label_nodes = [
                        source_tree_by_id[item_id]
                        for item_id in label_ids
                        if source_tree_by_id[item_id]["type"]
                        in {"Text", "BasicText", "ClickableText"}
                        and source_tree_by_id[item_id].get("business_owner_id") == owner_id
                    ]
                    layout = image_branch["style"]["layout"]
                    asset = image_branch["style"]["asset"]
                    outer_width = layout.get("width_dp") or asset.get("width_dp")
                    outer_height = layout.get("height_dp") or asset.get("height_dp")
                    spacer_height = spacer["style"]["layout"].get("height_dp")
                    inner_width = source_visual["style"]["asset"].get("width_dp")
                    inner_height = source_visual["style"]["asset"].get("height_dp")
                    if (
                        spacer.get("type") == "Spacer"
                        and len(label_nodes) == 1
                        and isinstance(outer_width, (int, float))
                        and isinstance(outer_height, (int, float))
                        and abs(float(outer_width) - float(outer_height)) <= 0.001
                        and isinstance(spacer_height, (int, float))
                        and isinstance(inner_width, (int, float))
                        and isinstance(inner_height, (int, float))
                        and abs(float(inner_width) - float(inner_height)) <= 0.001
                        and float(inner_width) <= float(outer_width)
                    ):
                        padding = (float(outer_width) - float(inner_width)) / 2
                        matches.append({
                            "outer_size": float(outer_width),
                            "spacer_height": float(spacer_height),
                            "padding": float(padding),
                        })
            current_id = parent["id"]
            if current_id == owner_id:
                break
        return matches[0] if len(matches) == 1 else None

    def page_asset_selected(rule: dict[str, Any]) -> bool:
        route = rule.get("route")
        page_id = str(source_spec["page"]["id"]).lower()
        label = str(rule.get("label", "")).lower()
        route_name = str(route or "").rsplit(".", 1)[-1].lower()
        return page_id in {label.replace(" ", "_"), route_name}

    used_asset_anchors: set[tuple[str, str]] = set()
    for rule in source_spec.get("runtime_asset_rules", []):
        if not isinstance(rule, dict) or not isinstance(rule.get("label"), str):
            continue
        label = rule["label"]
        labels = [
            item
            for item in output_components
            if item["style"]["content"].get("text") == label
        ]
        for label_component in labels:
            parent = output_by_id.get(label_component.get("parent_id") or "")
            anchor = parent if isinstance(parent, dict) and parent["type"] == "Button" else label_component
            identity = (anchor["id"], rule["role"])
            if identity in used_asset_anchors:
                continue
            used_asset_anchors.add(identity)
            chosen_asset = (
                rule.get("selected_asset")
                if rule.get("role") == "navigation_item" and page_asset_selected(rule)
                else rule.get("asset")
            )
            if not isinstance(chosen_asset, dict) or not isinstance(chosen_asset.get("resource"), str):
                continue

            role = rule["role"]
            source_visual = source_visual_for_rule(rule)
            source_text = source_text_for_rule(rule, source_visual)
            source_layout = (
                source_asset_label_layout(source_visual)
                if role == "labeled_asset_object"
                else None
            )
            anchor_bounds = anchor["bounds_dp"]
            label_bounds = label_component["bounds_dp"]
            if role == "navigation_item":
                outer_size = 24.0
                padding = 0.0
                center_x = label_bounds["x"] + label_bounds["width"] / 2
                top = (
                    anchor_bounds["y"] + 4.0
                    if anchor["type"] == "Button"
                    else label_bounds["y"] - 36.0
                )
                left = center_x - outer_size / 2
                background = None
                tint = None
            elif role == "titled_asset_record":
                outer_size = 48.0
                padding = 8.0
                left = anchor_bounds["x"] + 16.0
                top = anchor_bounds["y"] + max(0.0, (anchor_bounds["height"] - outer_size) / 2)
                background = "#FFF2F2F2"
                tint = None
            else:
                outer_size = (
                    source_layout["outer_size"]
                    if source_layout is not None
                    else 48.0
                )
                padding = (
                    source_layout["padding"]
                    if source_layout is not None
                    else 8.0
                )
                center_x = label_bounds["x"] + label_bounds["width"] / 2
                left = center_x - outer_size / 2
                top = (
                    label_bounds["y"]
                    - source_layout["spacer_height"]
                    - outer_size
                    if source_layout is not None
                    else anchor_bounds["y"] + 8.0
                    if anchor["type"] == "Button"
                    else label_bounds["y"] - 66.0
                )
                available = rule.get("availability")
                background = "#FFECE7FF" if available != "unavailable" else "#FFDEDEDE"
                tint = "#FF858585" if available == "unavailable" else None

            derived_id = "derived-" + hashlib.sha256(
                f"{anchor['id']}\0{role}\0{chosen_asset['resource']}".encode("utf-8")
            ).hexdigest()[:20]
            semantic_key = (
                f"{source_visual['semantic_key']}__instance_{derived_id[8:]}"
                if source_visual is not None
                else f"runtime.asset.{derived_id[8:]}"
            )
            style = empty_style()
            style["content"].update({"role": "image"})
            style["state"].update({"visible": True, "enabled": True, "clickable": False})
            style["asset"].update({
                "resource": chosen_asset["resource"],
                "sha256": chosen_asset.get("sha256"),
                "width_dp": outer_size - padding * 2,
                "height_dp": outer_size - padding * 2,
                "content_scale": "fit",
                "tint": tint,
            })
            if padding:
                style["layout"]["padding_dp"] = {
                    "left": padding, "top": padding, "right": padding, "bottom": padding,
                }
            if background is not None:
                style["surface"]["background"] = {"type": "solid", "color": background}
                style["surface"]["corner_radius_dp"] = {
                    "top_left": outer_size / 2,
                    "top_right": outer_size / 2,
                    "bottom_right": outer_size / 2,
                    "bottom_left": outer_size / 2,
                }
            parent_id = anchor["id"] if anchor["type"] == "Button" else anchor.get("parent_id")
            siblings = output_by_id[parent_id]["children_ids"] if isinstance(parent_id, str) else [
                item["id"] for item in output_components if item.get("parent_id") is None
            ]
            owner_id = source_visual.get("business_owner_id") if source_visual is not None else None
            business_path = business_path_for_owner(owner_id)
            if business_path:
                assign_candidate_business_context(
                    anchor, business_path, label_component["id"]
                )
                assign_candidate_business_context(
                    label_component, business_path, label_component["id"]
                )
                apply_rule_text_typography(label_component, source_text)
            source_mapping = {
                "status": "candidate" if source_visual is not None else "unbound",
                "method": "source_runtime_data_join" if source_visual is not None else "runtime_label_asset_join",
            }
            source_payload = None
            if source_visual is not None:
                source_mapping["source_call_id"] = source_visual["source"]["call_id"]
                source_payload = {
                    "source": source_visual["source"]["source"],
                    "composable": source_visual["source"]["composable"],
                    "attributes": copy.deepcopy(source_visual["source"]["attributes"]),
                }
            derived = {
                "id": derived_id,
                "type": "Image",
                "bounds_px": {
                    "x": round(left * density),
                    "y": round(top * density),
                    "width": round(outer_size * density),
                    "height": round(outer_size * density),
                },
                "bounds_dp": {"x": round(left, 3), "y": round(top, 3), "width": outer_size, "height": outer_size},
                "parent_id": parent_id,
                "parent_mapping": "source-semantic-ancestor" if source_visual is not None else "runtime-semantic-ancestor",
                "children_ids": [],
                "sibling_index": len(siblings),
                "style": style,
                "provenance": [{
                    "paths": [
                        "style.asset.resource", "style.asset.content_scale",
                        "style.asset.width_dp", "style.asset.height_dp",
                    ] + (["style.asset.sha256"] if chosen_asset.get("sha256") is not None else []),
                    "origin": "source_resolved",
                    "source": f"{rule['source']['source']}:{rule['source']['line']} joined to runtime label",
                }],
                "unresolved": [],
                "runtime_evidence": {
                    "runtime_component_id": anchor["runtime_evidence"]["runtime_component_id"],
                    "runtime_class": anchor["runtime_evidence"]["runtime_class"],
                },
                "component_context": {
                    "status": "candidate" if business_path else "unbound",
                    "method": source_mapping["method"] if business_path else "no_component_context",
                    "source_component_id": source_visual["id"] if source_visual is not None else None,
                    "business_component_id": business_path[-1] if business_path else None,
                    "business_component_path": business_path,
                    "evidence_runtime_ids": [anchor["id"]] if business_path else [],
                },
                "semantic_key": semantic_key,
                "source_mapping": source_mapping,
            }
            if source_payload is not None:
                derived["source"] = source_payload
            if isinstance(parent_id, str):
                output_by_id[parent_id]["children_ids"].append(derived_id)
            output_components.append(derived)
            output_by_id[derived_id] = derived

    # Runtime accessibility trees frequently expose an IconButton as a button but
    # omit its static image child.  Rejoin that runtime geometry with the exact
    # source Icon/Image only when the source asset and dimensions are resolved,
    # the source parent is a button primitive, and one otherwise-empty runtime
    # button occupies the same visual band as the active business component.
    derived_parent_ids = {
        item["parent_id"]
        for item in output_components
        if item["type"] == "Image" and isinstance(item.get("parent_id"), str)
    }
    for source_visual in source_tree_components:
        if source_visual["type"] not in {"Image", "Icon"} or source_visual["runtime_instances"]:
            continue
        asset_style = source_visual["style"]["asset"]
        resource = asset_style.get("resource")
        width = asset_style.get("width_dp")
        height = asset_style.get("height_dp")
        parent_source = source_tree_by_id.get(source_visual.get("parent_id") or "")
        if (
            not isinstance(resource, str)
            or not isinstance(width, (int, float))
            or not isinstance(height, (int, float))
            or not isinstance(parent_source, dict)
            or parent_source["type"] not in {
                "Button", "IconButton", "FloatingActionButton", "SmallFloatingActionButton"
            }
        ):
            continue
        business_path = business_path_for_owner(source_visual.get("business_owner_id"))
        owner_runtime_ids = set(source_visual.get("runtime_descendant_ids", []))
        owner = source_tree_by_id.get(source_visual.get("business_owner_id") or "")
        if isinstance(owner, dict):
            owner_runtime_ids.update(owner.get("runtime_descendant_ids", []))
        owner_runtime_components = [
            output_by_id[runtime_id]
            for runtime_id in owner_runtime_ids
            if runtime_id in output_by_id
        ]
        if not owner_runtime_components:
            continue
        owner_top = min(item["bounds_dp"]["y"] for item in owner_runtime_components)
        owner_bottom = max(
            item["bounds_dp"]["y"] + item["bounds_dp"]["height"]
            for item in owner_runtime_components
        )
        vertical_slack = max(float(height), 24.0)
        button_candidates = []
        for candidate in output_components:
            if candidate["type"] not in {
                "Button", "IconButton", "FloatingActionButton", "SmallFloatingActionButton"
            } or candidate["id"] in derived_parent_ids:
                continue
            if visual_descendant_texts(candidate["id"]):
                continue
            bounds = candidate["bounds_dp"]
            center_y = bounds["y"] + bounds["height"] / 2
            if owner_top - vertical_slack <= center_y <= owner_bottom + vertical_slack:
                button_candidates.append(candidate)
        if len(button_candidates) != 1:
            continue
        anchor = button_candidates[0]
        derived_id = "derived-" + hashlib.sha256(
            f"{anchor['id']}\0static_source_asset\0{source_visual['id']}".encode("utf-8")
        ).hexdigest()[:20]
        left = anchor["bounds_dp"]["x"] + (anchor["bounds_dp"]["width"] - float(width)) / 2
        top = anchor["bounds_dp"]["y"] + (anchor["bounds_dp"]["height"] - float(height)) / 2
        style = copy.deepcopy(source_visual["style"])
        style["content"]["role"] = "image"
        style["state"].update({"visible": True, "enabled": True, "clickable": False})
        derived = {
            "id": derived_id,
            "type": "Image",
            "bounds_px": {
                "x": round(left * density),
                "y": round(top * density),
                "width": round(float(width) * density),
                "height": round(float(height) * density),
            },
            "bounds_dp": {
                "x": round(left, 3),
                "y": round(top, 3),
                "width": float(width),
                "height": float(height),
            },
            "parent_id": anchor["id"],
            "parent_mapping": "runtime-semantic-ancestor",
            "children_ids": [],
            "sibling_index": len(anchor["children_ids"]),
            "style": style,
            "provenance": copy.deepcopy(source_visual["provenance"]) + [{
                "paths": [
                    "style.asset.resource", "style.asset.width_dp", "style.asset.height_dp"
                ],
                "origin": "source_resolved",
                "source": (
                    f"{source_visual['source']['source']}:{source_visual['source']['line']} "
                    "joined to runtime button geometry"
                ),
            }],
            "unresolved": [
                item for item in copy.deepcopy(source_visual["unresolved"])
                if item.get("path") != "style.asset.resource"
            ],
            "runtime_evidence": copy.deepcopy(anchor["runtime_evidence"]),
            "component_context": {
                "status": "candidate",
                "method": "source_runtime_parent_join",
                "source_component_id": source_visual["id"],
                "business_component_id": business_path[-1] if business_path else None,
                "business_component_path": business_path,
                "evidence_runtime_ids": [anchor["id"]],
            },
            "semantic_key": source_visual["semantic_key"],
            "source_mapping": {
                "status": "candidate",
                "method": "source_runtime_parent_join",
                "source_call_id": source_visual["source"]["call_id"],
            },
            "source": {
                "source": source_visual["source"]["source"],
                "composable": source_visual["source"]["composable"],
                "attributes": copy.deepcopy(source_visual["source"]["attributes"]),
            },
        }
        anchor["children_ids"].append(derived_id)
        output_components.append(derived)
        output_by_id[derived_id] = derived
        derived_parent_ids.add(anchor["id"])

    progress_owner_ids = {
        item["id"]
        for item in source_tree_components
        if item["component_kind"] == "project_component"
        and any(
            attribute.get("name") in {"percentage", "progress"}
            for attribute in item["source"].get("attributes", [])
            if isinstance(attribute, dict)
        )
    }
    canvas_candidates = [
        item for item in source_tree_components
        if item["component_kind"] == "custom_draw"
        and item["type"] == "Canvas"
        and item.get("business_owner_id") in progress_owner_ids
    ]
    progress_canvas = canvas_candidates[0] if len(canvas_candidates) == 1 else None
    for label_component in list(output_components):
        text = label_component["style"]["content"].get("text")
        if not isinstance(text, str) or re.fullmatch(r"(?:100|[0-9]{1,2})%", text) is None:
            continue
        parent = output_by_id.get(label_component.get("parent_id") or "")
        if not isinstance(parent, dict) or parent["type"] != "Button" or parent["bounds_dp"]["width"] < 200:
            continue
        outer_size = 48.0
        left = parent["bounds_dp"]["x"] + parent["bounds_dp"]["width"] - 16.0 - outer_size
        top = parent["bounds_dp"]["y"] + max(0.0, (parent["bounds_dp"]["height"] - outer_size) / 2)
        derived_id = "derived-" + hashlib.sha256(
            f"{parent['id']}\0progress_ring\0{text}".encode("utf-8")
        ).hexdigest()[:20]
        style = empty_style()
        style["content"].update({"text": text, "role": "progressbar"})
        style["state"].update({"visible": True, "enabled": True, "clickable": False})
        source_payload = None
        business_path: list[str] = []
        semantic_key = f"runtime.progress.{derived_id[8:]}"
        if progress_canvas is not None:
            semantic_key = f"{progress_canvas['semantic_key']}__instance_{derived_id[8:]}"
            business_path = business_path_for_owner(progress_canvas.get("business_owner_id"))
            source_payload = {
                "source": progress_canvas["source"]["source"],
                "composable": progress_canvas["source"]["composable"],
                "attributes": copy.deepcopy(progress_canvas["source"]["attributes"]),
            }
        derived = {
            "id": derived_id,
            "type": "ProgressRing",
            "bounds_px": {"x": round(left * density), "y": round(top * density), "width": round(outer_size * density), "height": round(outer_size * density)},
            "bounds_dp": {"x": round(left, 3), "y": round(top, 3), "width": outer_size, "height": outer_size},
            "parent_id": parent["id"],
            "parent_mapping": "source-semantic-ancestor" if source_payload is not None else "runtime-semantic-ancestor",
            "children_ids": [],
            "sibling_index": len(parent["children_ids"]),
            "style": style,
            "provenance": [{"paths": ["style.content.text", "style.content.role"], "origin": "runtime", "source": runtime_origin}],
            "unresolved": [],
            "runtime_evidence": copy.deepcopy(parent["runtime_evidence"]),
            "component_context": {
                "status": "candidate" if business_path else "unbound",
                "method": "source_runtime_data_join" if business_path else "no_component_context",
                "source_component_id": progress_canvas["id"] if progress_canvas is not None else None,
                "business_component_id": business_path[-1] if business_path else None,
                "business_component_path": business_path,
                "evidence_runtime_ids": [parent["id"]] if business_path else [],
            },
            "semantic_key": semantic_key,
            "source_mapping": {
                "status": "candidate" if source_payload is not None else "unbound",
                "method": "source_runtime_data_join" if source_payload is not None else "runtime_percentage_fallback",
                **(
                    {"source_call_id": progress_canvas["source"]["call_id"]}
                    if progress_canvas is not None else {}
                ),
            },
        }
        if source_payload is not None:
            derived["source"] = source_payload
        parent["children_ids"].append(derived_id)
        output_components.append(derived)
        output_by_id[derived_id] = derived

    # Runtime accessibility bounds can flatten or clip project-owned surfaces.
    # First let source-bound visual descendants refine an otherwise generic
    # runtime container's business ownership.  Repeated instances with the same
    # child structure can then repair a clipped visual height from a complete
    # sibling without inventing a project-specific dimension.
    for component in output_components:
        current_path = component["component_context"].get("business_component_path", [])
        descendant_paths = [
            output_by_id[child_id]["component_context"].get("business_component_path", [])
            for child_id in component["children_ids"]
            if child_id in output_by_id
            and len(output_by_id[child_id]["component_context"].get("business_component_path", []))
            > len(current_path)
        ]
        refined_path = common_business_path(descendant_paths)
        if len(descendant_paths) >= 2 and len(refined_path) > len(current_path):
            component["component_context"] = {
                "status": "candidate",
                "method": "source_bound_visual_descendant_context",
                "source_component_id": None,
                "business_component_id": refined_path[-1],
                "business_component_path": refined_path,
                "evidence_runtime_ids": [
                    child_id
                    for child_id in component["children_ids"]
                    if child_id in output_by_id
                    and refined_path
                    == output_by_id[child_id]["component_context"].get(
                        "business_component_path", []
                    )[:len(refined_path)]
                ],
            }

    context_changed = True
    while context_changed:
        context_changed = False
        for component in output_components:
            parent = output_by_id.get(component.get("parent_id") or "")
            if not isinstance(parent, dict):
                continue
            parent_path = parent["component_context"].get("business_component_path", [])
            current_path = component["component_context"].get("business_component_path", [])
            if (
                component["source_mapping"].get("status") == "unbound"
                and len(parent_path) > len(current_path)
            ):
                evidence_ids = parent["component_context"].get("evidence_runtime_ids", [])
                assign_candidate_business_context(
                    component,
                    parent_path,
                    str(evidence_ids[0] if evidence_ids else parent["id"]),
                )
                context_changed = True

    for component in output_components:
        if (
            component["type"] != "Text"
            or component["source_mapping"].get("method") != "runtime_visual_fallback"
        ):
            continue
        owner_id = component["component_context"].get("business_component_id")
        if not isinstance(owner_id, str):
            continue
        prior_candidate_records = [
            record
            for record in component["provenance"]
            if record.get("origin") == "source_expression"
            and str(record.get("source", "")).startswith("candidate typography role from ")
        ]
        prior_candidate_paths = {
            path
            for record in prior_candidate_records
            for path in record.get("paths", [])
            if isinstance(path, str)
        }
        candidate_typography, candidate_key = candidate_text_typography(
            component, owner_id
        )
        component["provenance"] = [
            record
            for record in component["provenance"]
            if record not in prior_candidate_records
        ]
        if candidate_typography is None or candidate_key is None:
            for path in prior_candidate_paths:
                set_path_value(component["style"], path, None)
            continue
        applied_paths: list[str] = []
        for field in candidate_typography_fields:
            path = f"style.typography.{field}"
            value = candidate_typography.get(field)
            if path in prior_candidate_paths or component["style"]["typography"].get(field) is None:
                component["style"]["typography"][field] = value
                if value is not None:
                    applied_paths.append(path)
        if applied_paths:
            component["provenance"].append({
                "paths": applied_paths,
                "origin": "source_expression",
                "source": (
                    f"candidate typography role from {candidate_key} selected inside "
                    f"business component {owner_id} by runtime line box"
                ),
            })

    repeated_visuals: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for component in output_components:
        owner_id = component["component_context"].get("business_component_id")
        if (
            component["type"] != "Button"
            or not isinstance(owner_id, str)
            or component["bounds_dp"]["width"] < dimensions[0] / density * 0.5
        ):
            continue
        child_signature = tuple(sorted(
            output_by_id[child_id]["type"]
            for child_id in component["children_ids"]
            if child_id in output_by_id
        ))
        repeated_visuals[(
            component.get("parent_id"),
            owner_id,
            round(component["bounds_dp"]["width"], 1),
            child_signature,
        )].append(component)
    for repeated in repeated_visuals.values():
        if len(repeated) < 2:
            continue
        heights = [float(component["bounds_dp"]["height"]) for component in repeated]
        canonical_height = max(heights)
        if min(heights) < canonical_height * 0.8 or canonical_height - min(heights) <= 1.0:
            continue
        for component in repeated:
            old_height = float(component["bounds_dp"]["height"])
            if canonical_height - old_height <= 1.0:
                continue
            component["visual_bounds_dp"] = {
                **component["bounds_dp"],
                "height": round(canonical_height, 3),
            }
            component["visual_bounds_px"] = {
                **component["bounds_px"],
                "height": round(canonical_height * density),
            }
            for child_id in component["children_ids"]:
                child = output_by_id.get(child_id)
                if child is None or child["type"] not in {"Image", "ProgressRing"}:
                    continue
                child_height = float(child["bounds_dp"]["height"])
                relative_y = float(child["bounds_dp"]["y"]) - float(component["bounds_dp"]["y"])
                if abs(relative_y - (old_height - child_height) / 2) > 1.0:
                    continue
                corrected_y = float(component["bounds_dp"]["y"]) + (
                    canonical_height - child_height
                ) / 2
                child["bounds_dp"]["y"] = round(corrected_y, 3)
                child["bounds_px"]["y"] = round(corrected_y * density)

    source_surface_evidence: dict[str, dict[str, Any]] = {}
    for source in source_tree_components:
        expression = " ".join(
            f"{modifier.get('name', '')} {modifier.get('arguments', '')}"
            for modifier in source.get("modifiers", [])
            if isinstance(modifier, dict)
        )
        if re.search(r"(?:background|border|shadow|elevation)", expression, re.IGNORECASE) is None:
            continue
        owner_id = source.get("business_owner_id")
        owner = source_tree_by_id.get(owner_id or "")
        if not isinstance(owner, dict) or owner.get("component_kind") != "project_component":
            continue
        flags = source_surface_evidence.setdefault(
            owner_id,
            {
                "elevation": False,
                "full_width": False,
                "fixed_heights_dp": set(),
                "shadow": None,
                "shadow_source": None,
            },
        )
        flags["elevation"] = flags["elevation"] or bool(
            re.search(r"(?:shadow|elevation)", expression, re.IGNORECASE)
        )
        flags["full_width"] = flags["full_width"] or any(
            modifier.get("name") == "fillMaxWidth"
            and str(modifier.get("arguments", "")).strip() in {"", "1f", "1.0f"}
            for modifier in source.get("modifiers", [])
            if isinstance(modifier, dict)
        )
        source_shadows = source["style"]["surface"].get("shadows")
        if isinstance(source_shadows, list) and source_shadows:
            source_shadow = source_shadows[0]
            current_shadow = flags["shadow"]
            if (
                not isinstance(current_shadow, dict)
                or float(source_shadow.get("blur_radius_dp", 0))
                > float(current_shadow.get("blur_radius_dp", 0))
            ):
                flags["shadow"] = copy.deepcopy(source_shadow)
                flags["shadow_source"] = (
                    f"{source['source']['source']}:{source['source']['line']}"
                )
        for modifier in source.get("modifiers", []):
            if not isinstance(modifier, dict) or modifier.get("name") not in {
                "height", "requiredHeight", "size", "requiredSize"
            }:
                continue
            flags["fixed_heights_dp"].update(
                value
                for value, unit in modifier_dimensions(modifier)
                if unit == "dp"
            )

    def intersection_area(left: dict[str, int], right: dict[str, int]) -> int:
        return max(
            0,
            min(left["x"] + left["width"], right["x"] + right["width"])
            - max(left["x"], right["x"]),
        ) * max(
            0,
            min(left["y"] + left["height"], right["y"] + right["height"])
            - max(left["y"], right["y"]),
        )

    def apply_source_shadow(
        component: dict[str, Any], evidence: dict[str, Any]
    ) -> None:
        source_shadow = evidence["shadow"]
        if not isinstance(source_shadow, dict):
            return
        component["style"]["surface"]["shadows"] = [copy.deepcopy(source_shadow)]
        for provenance in component["provenance"]:
            provenance["paths"] = [
                path
                for path in provenance["paths"]
                if path != "style.surface.shadows"
            ]
        component["provenance"] = [
            provenance
            for provenance in component["provenance"]
            if provenance["paths"]
        ]
        component["provenance"].append({
            "paths": ["style.surface.shadows"],
            "origin": "source_resolved",
            "source": evidence["shadow_source"],
        })

    for owner_id, evidence in source_surface_evidence.items():
        if not isinstance(evidence["shadow"], dict):
            continue
        rendered_surfaces = [
            component
            for component in output_components
            if component["component_context"].get("business_component_id") == owner_id
            and isinstance(component["style"]["surface"].get("background"), dict)
            and component["style"]["surface"]["background"].get("type") == "solid"
        ]
        if not rendered_surfaces:
            continue
        largest_area = max(
            (component.get("visual_bounds_px") or component["bounds_px"])["width"]
            * (component.get("visual_bounds_px") or component["bounds_px"])["height"]
            for component in rendered_surfaces
        )
        for component in rendered_surfaces:
            bounds = component.get("visual_bounds_px") or component["bounds_px"]
            area = bounds["width"] * bounds["height"]
            if area >= largest_area * 0.95:
                apply_source_shadow(component, evidence)

    surface_candidates = (
        screenshot_surface_regions(screenshot_path, dimensions, density)
        if screenshot_path.is_file()
        else []
    )
    for candidate in surface_candidates:
        candidate_bounds = copy.deepcopy(candidate["bounds_px"])
        edge_anchor = candidate.get("edge_anchor")
        if edge_anchor is not None:
            content_top = insets_px["top"]
            content_bottom = dimensions[1] - insets_px["bottom"]
            clipped_top = max(candidate_bounds["y"], content_top)
            clipped_bottom = min(
                candidate_bounds["y"] + candidate_bounds["height"], content_bottom
            )
            candidate_bounds = {
                "x": 0,
                "y": clipped_top,
                "width": dimensions[0],
                "height": max(0, clipped_bottom - clipped_top),
            }
            if candidate_bounds["height"] == 0:
                continue
        candidate_area = candidate_bounds["width"] * candidate_bounds["height"]
        duplicate_surface = any(
            isinstance(component["style"]["surface"].get("background"), dict)
            and component["style"]["surface"]["background"].get("type") == "solid"
            and component["bounds_px"]["width"] >= dimensions[0] * 0.5
            and component["bounds_px"]["width"] * component["bounds_px"]["height"]
            <= candidate_area * 3
            and intersection_area(candidate_bounds, component["bounds_px"])
            >= candidate_area * 0.75
            for component in output_components
        )
        if duplicate_surface:
            continue
        owner_matches: list[tuple[int, int, str, list[dict[str, Any]]]] = []
        for owner_id in source_surface_evidence:
            evidence = source_surface_evidence[owner_id]
            if not surface_height_matches_source(
                candidate_bounds["height"], density, evidence["fixed_heights_dp"]
            ):
                continue
            if edge_anchor is not None:
                candidate_height_dp = candidate_bounds["height"] / density
                if (
                    not evidence["full_width"]
                    or not evidence["fixed_heights_dp"]
                    or min(
                        abs(candidate_height_dp - height_dp)
                        for height_dp in evidence["fixed_heights_dp"]
                    ) > 2.0
                ):
                    continue
            members = []
            for component in output_components:
                if owner_id not in component["component_context"].get("business_component_path", []):
                    continue
                bounds = component.get("visual_bounds_px") or component["bounds_px"]
                center_x = bounds["x"] + bounds["width"] / 2
                center_y = bounds["y"] + bounds["height"] / 2
                if (
                    candidate_bounds["x"] <= center_x <= candidate_bounds["x"] + candidate_bounds["width"]
                    and candidate_bounds["y"] <= center_y <= candidate_bounds["y"] + candidate_bounds["height"]
                ):
                    members.append(component)
            if len(members) < 2:
                continue
            owner_path_depth = max(
                component["component_context"]["business_component_path"].index(owner_id)
                for component in members
            )
            owner_matches.append((len(members), owner_path_depth, owner_id, members))
        if not owner_matches:
            continue
        _, _, owner_id, members = select_most_specific_surface_owner(owner_matches)
        # A runtime control can already expose the complete rendered surface
        # even when the project wrapper that created it is absent from the
        # accessibility tree.  Do not add a second screenshot-derived surface
        # for the same business-component instance: solid runs interrupted by
        # text or icons can otherwise look like a smaller detached card.
        existing_owner_surfaces = [
            component["component_context"].get("business_component_id") == owner_id
            and isinstance(component["style"]["surface"].get("background"), dict)
            and component["style"]["surface"]["background"].get("type") == "solid"
            and (component.get("visual_bounds_px") or component["bounds_px"])["width"]
            >= candidate_bounds["width"] * 0.8
            and intersection_area(
                candidate_bounds,
                component.get("visual_bounds_px") or component["bounds_px"],
            )
            >= candidate_area * 0.5
            for component in output_components
        ]
        existing_owner_surfaces = [
            component
            for component, matches in zip(output_components, existing_owner_surfaces, strict=True)
            if matches
        ]
        if existing_owner_surfaces:
            for component in existing_owner_surfaces:
                apply_source_shadow(component, source_surface_evidence[owner_id])
            continue
        owner = source_tree_by_id[owner_id]
        containing_parents = [
            component
            for component in output_components
            if component["id"] not in {member["id"] for member in members}
            and component["bounds_px"]["x"] <= candidate_bounds["x"]
            and component["bounds_px"]["y"] <= candidate_bounds["y"]
            and component["bounds_px"]["x"] + component["bounds_px"]["width"]
            >= candidate_bounds["x"] + candidate_bounds["width"]
            and component["bounds_px"]["y"] + component["bounds_px"]["height"]
            >= candidate_bounds["y"] + candidate_bounds["height"]
        ]
        parent = min(
            containing_parents,
            key=lambda component: component["bounds_px"]["width"] * component["bounds_px"]["height"],
            default=None,
        )
        parent_id = parent["id"] if parent is not None else None
        derived_id = "derived-" + hashlib.sha256(
            f"{owner_id}\0screenshot_surface\0{candidate_bounds}".encode("utf-8")
        ).hexdigest()[:20]
        if derived_id in output_by_id:
            continue
        business_path = business_path_for_owner(owner_id)
        style = empty_style()
        style["content"]["role"] = "surface"
        style["state"].update({"visible": True, "enabled": True, "clickable": False})
        style["surface"]["background"] = {
            "type": "solid",
            "color": candidate["background"],
        }
        radius = float(candidate["corner_radius_dp"])
        style["surface"]["corner_radius_dp"] = {
            edge: radius
            for edge in ("top_left", "top_right", "bottom_right", "bottom_left")
        }
        surface_paths = ["style.surface.background", "style.surface.corner_radius_dp"]
        shadow_provenance: dict[str, Any] | None = None
        if source_surface_evidence[owner_id]["elevation"]:
            source_shadow = source_surface_evidence[owner_id]["shadow"]
            if isinstance(source_shadow, dict):
                style["surface"]["shadows"] = [copy.deepcopy(source_shadow)]
                shadow_provenance = {
                    "paths": ["style.surface.shadows"],
                    "origin": "source_resolved",
                    "source": source_surface_evidence[owner_id]["shadow_source"],
                }
            else:
                style["surface"]["shadows"] = [{
                    "color": "#1A000000",
                    "offset_x_dp": 0.0,
                    "offset_y_dp": 4.0,
                    "blur_radius_dp": 12.0,
                    "spread_radius_dp": 0.0,
                }]
                surface_paths.append("style.surface.shadows")
        derived = {
            "id": derived_id,
            "type": owner["type"],
            "bounds_px": copy.deepcopy(candidate_bounds),
            "bounds_dp": dp_bounds(candidate_bounds, density),
            "parent_id": parent_id,
            "parent_mapping": "source-semantic-ancestor",
            "children_ids": [],
            "sibling_index": 0,
            "style": style,
            "provenance": [{
                "paths": surface_paths,
                "origin": "pixel_sampled",
                "source": "screenshot surface boundary joined to source-owned surface modifiers",
            }] + ([shadow_provenance] if shadow_provenance is not None else []),
            "unresolved": [],
            "runtime_evidence": copy.deepcopy(members[0]["runtime_evidence"]),
            "component_context": {
                "status": "candidate",
                "method": "source_screenshot_surface_join",
                "source_component_id": owner_id,
                "business_component_id": owner_id,
                "business_component_path": business_path,
                "evidence_runtime_ids": [member["id"] for member in members],
            },
            "semantic_key": f"{owner['semantic_key']}__surface_{derived_id[8:]}",
            "source_mapping": {
                "status": "candidate",
                "method": "source_screenshot_surface_join",
                "source_call_id": owner["source"]["call_id"],
            },
            "source": {
                "source": owner["source"]["source"],
                "composable": owner["source"]["composable"],
                "attributes": copy.deepcopy(owner["source"]["attributes"]),
            },
        }
        if parent is not None:
            parent["children_ids"].insert(0, derived_id)
        output_components.append(derived)
        output_by_id[derived_id] = derived

    def source_alignment(source: dict[str, Any]) -> str | None:
        semantic = source.get("arguments", {}).get("semantic", {})
        alignment = semantic.get("contentAlignment") if isinstance(semantic, dict) else None
        expression = alignment.get("expression") if isinstance(alignment, dict) else None
        return expression.rsplit(".", 1)[-1] if isinstance(expression, str) else None

    def source_offset(
        source: dict[str, Any], container_width: float, container_height: float
    ) -> tuple[float, float] | None:
        modifier = next(
            (
                item
                for item in source.get("modifiers", [])
                if isinstance(item, dict) and item.get("name") == "offset"
            ),
            None,
        )
        if modifier is None:
            return 0.0, 0.0
        arguments = str(modifier.get("arguments", ""))
        values = {
            name: expression.strip()
            for name, expression in re.findall(r"\b(x|y)\s*=\s*([^,]+)", arguments)
        }
        if not values:
            return None

        def resolve(expression: str) -> float | None:
            literal = re.fullmatch(r"(-?[0-9]+(?:\.[0-9]+)?)\.dp", expression)
            if literal is not None:
                return number(literal.group(1))
            relative = re.fullmatch(
                r"(-?)\s*(maxWidth|maxHeight)\s*/\s*([0-9]+(?:\.[0-9]+)?)",
                expression,
            )
            if relative is None:
                return None
            base = container_width if relative.group(2) == "maxWidth" else container_height
            value = base / float(relative.group(3))
            return -value if relative.group(1) == "-" else value

        x = resolve(values.get("x", "0.dp"))
        y = resolve(values.get("y", "0.dp"))
        return (x, y) if x is not None and y is not None else None

    source_only_images = [
        source
        for source in source_tree_components
        if source["type"] in {"Image", "Icon", "AsyncImage"}
        and not source["runtime_instances"]
        and isinstance(source["style"]["asset"].get("resource"), str)
        and isinstance(source["style"]["asset"].get("width_dp"), (int, float))
        and isinstance(source["style"]["asset"].get("height_dp"), (int, float))
    ]
    for source_image in source_only_images:
        owner_id = source_image.get("business_owner_id")
        surfaces = [
            component
            for component in output_components
            if component["style"]["content"].get("role") == "surface"
            and component["component_context"].get("business_component_id") == owner_id
        ]
        parent_source = source_tree_by_id.get(source_image.get("parent_id") or "")
        if len(surfaces) != 1 or not isinstance(parent_source, dict):
            continue
        alignment = source_alignment(parent_source)
        if alignment not in {"TopStart", "TopCenter", "TopEnd", "CenterStart", "Center", "CenterEnd", "BottomStart", "BottomCenter", "BottomEnd"}:
            continue
        surface = surfaces[0]
        surface_bounds = surface["bounds_dp"]
        asset = source_image["style"]["asset"]
        image_width = float(asset["width_dp"])
        image_height = float(asset["height_dp"])
        offset = source_offset(
            source_image, float(surface_bounds["width"]), float(surface_bounds["height"])
        )
        if offset is None:
            continue
        horizontal = (
            0.0
            if alignment.endswith("Start")
            else (float(surface_bounds["width"]) - image_width) / 2
            if alignment in {"TopCenter", "Center", "BottomCenter"}
            else float(surface_bounds["width"]) - image_width
        )
        vertical = (
            0.0
            if alignment.startswith("Top")
            else (float(surface_bounds["height"]) - image_height) / 2
            if alignment.startswith("Center") or alignment == "Center"
            else float(surface_bounds["height"]) - image_height
        )
        source_layout_bounds_dp = {
            "x": round(float(surface_bounds["x"]) + horizontal + offset[0], 3),
            "y": round(float(surface_bounds["y"]) + vertical + offset[1], 3),
            "width": round(image_width, 3),
            "height": round(image_height, 3),
        }
        content_bounds_dp = {
            "x": round(insets_px["left"] / density, 3),
            "y": round(insets_px["top"] / density, 3),
            "width": round(
                (dimensions[0] - insets_px["left"] - insets_px["right"]) / density,
                3,
            ),
            "height": round(
                (dimensions[1] - insets_px["top"] - insets_px["bottom"]) / density,
                3,
            ),
        }
        bounds_dp = clip_projected_layout_bounds(
            source_layout_bounds_dp, content_bounds_dp
        )
        if bounds_dp is None:
            continue
        derived_id = "derived-" + hashlib.sha256(
            f"{source_image['id']}\0source_layout_image\0{source_layout_bounds_dp}".encode("utf-8")
        ).hexdigest()[:20]
        if derived_id in output_by_id:
            continue
        business_path = business_path_for_owner(owner_id)
        derived = {
            "id": derived_id,
            "type": source_image["type"],
            "bounds_px": {
                name: round(value * density) for name, value in bounds_dp.items()
            },
            "bounds_dp": bounds_dp,
            "source_layout_bounds_dp": source_layout_bounds_dp,
            "parent_id": surface["id"],
            "parent_mapping": "source-semantic-ancestor",
            "children_ids": [],
            "sibling_index": 0,
            "style": copy.deepcopy(source_image["style"]),
            "provenance": copy.deepcopy(source_image["provenance"]),
            "unresolved": copy.deepcopy(source_image["unresolved"]),
            "runtime_evidence": copy.deepcopy(surface["runtime_evidence"]),
            "component_context": {
                "status": "candidate",
                "method": "source_layout_projection",
                "source_component_id": source_image["id"],
                "business_component_id": owner_id,
                "business_component_path": business_path,
                "evidence_runtime_ids": copy.deepcopy(
                    surface["component_context"].get("evidence_runtime_ids", [])
                ),
            },
            "semantic_key": source_image["semantic_key"],
            "source_mapping": {
                "status": "candidate",
                "method": "source_layout_projection",
                "source_call_id": source_image["source"]["call_id"],
            },
            "source": {
                "source": source_image["source"]["source"],
                "composable": source_image["source"]["composable"],
                "attributes": copy.deepcopy(source_image["source"]["attributes"]),
            },
        }
        surface["children_ids"].insert(0, derived_id)
        output_components.append(derived)
        output_by_id[derived_id] = derived

    root_components = [component for component in output_components if component["parent_id"] is None]
    root_components.sort(key=lambda component: component["sibling_index"])
    for index, component in enumerate(root_components):
        component["sibling_index"] = index
    for parent in output_components:
        for index, child_id in enumerate(parent["children_ids"]):
            output_by_id[child_id]["sibling_index"] = index

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
        "source_component_tree": {
            "schema": SOURCE_COMPONENT_TREE_SCHEMA,
            "definitions": copy.deepcopy(source_spec["component_definitions"]),
            "root_ids": [root_id for root_id in selected_source_root_ids if root_id in active_source_ids],
            "business_root_ids": business_children_by_source.get(None, []),
            "business_component_ids": [
                source["id"]
                for source in source_components
                if source["id"] in business_source_ids
            ],
            "third_party_component_ids": [
                source["id"]
                for source in source_components
                if source["id"] in active_source_ids
                and source["component_kind"] == "third_party_component"
            ],
            "layout_relationships": copy.deepcopy(
                source_spec.get("layout_relationships", [])
            ),
            "components": source_tree_components,
        },
        "components": output_components,
        "inactive_source_components": inactive_source_entries,
        "runtime_elided_source_components": elided_source_entries,
        "unmapped_source_components": unmatched,
        "unmapped_visual_fact_components": [],
        "limitations": [
            "The source_component_tree is the business/source hierarchy; components are captured runtime visual instances.",
            "Visible semantic runtime instances remain available to first-pass generation when source binding is unresolved.",
            "Generic platform wrappers are compressed and never promoted to source/business component identity.",
            "Rendered typography, gradients, corner radii, and shadows remain unresolved unless source or instrumentation proves them.",
            "Candidate active source descendants share an observed root but still require source-state reconciliation.",
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
            "visual_component_count": len(output_components),
            "unbound_visual_component_count": sum(
                item["source_mapping"]["status"] == "unbound" for item in output_components
            ),
            "candidate_visual_component_count": sum(
                item["source_mapping"]["status"] == "candidate" for item in output_components
            ),
            "proven_visual_component_count": sum(
                item["source_mapping"]["status"] == "proven" for item in output_components
            ),
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
