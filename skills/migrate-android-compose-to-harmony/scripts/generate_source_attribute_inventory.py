#!/usr/bin/env python3
"""Create a display-content-free source attribute index for visual diagnostics."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from ui_migration.common import named_arguments
from ui_migration.contracts.identity import (
    canonical_sha256,
    require_contract_ui,
    require_safe_relative_source,
)
from init_harmony_project import load_contract, sha256_file


INVENTORY_SCHEMA = "android-to-harmony.source-attribute-inventory.v1"
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RESOURCE_PATTERN = re.compile(r"^[A-Za-z0-9_.:/#@-]{1,240}$")


class SourceAttributeError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a sanitized source-attribute inventory for one exact Compose closure."
        )
    )
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--root-source", required=True)
    parser.add_argument("--root-composable", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def safe_dimensions(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise SourceAttributeError("source attribute dimensions must be a list")
    result: list[dict[str, str]] = []
    for item in value:
        if (
            not isinstance(item, dict)
            or set(item) != {"value", "unit"}
            or not isinstance(item.get("value"), str)
            or re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", item["value"]) is None
            or item.get("unit") not in {"dp", "sp"}
        ):
            raise SourceAttributeError("source attribute dimension is invalid")
        result.append({"value": item["value"], "unit": item["unit"]})
    return result


def safe_resources(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise SourceAttributeError("source attribute dimension resources must be a list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or RESOURCE_PATTERN.fullmatch(item) is None:
            raise SourceAttributeError("source attribute dimension resource is invalid")
        result.append(item)
    return result


def attribute_groups(component: str, origin: str, name: str) -> list[str]:
    geometry = {
        "width", "height", "size", "requiredWidth", "requiredHeight", "requiredSize",
        "fillMaxWidth", "fillMaxHeight", "fillMaxSize", "wrapContentWidth",
        "wrapContentHeight", "padding", "offset", "absoluteOffset", "weight", "align",
        "defaultMinSize", "sizeIn", "widthIn", "heightIn", "aspectRatio",
        "horizontalAlignment", "verticalAlignment", "horizontalArrangement",
        "verticalArrangement", "contentAlignment", "contentPadding", "constraints",
        "maxLines", "minLines",
    }
    typography = {
        "style", "fontSize", "fontWeight", "fontFamily", "fontStyle", "letterSpacing",
        "lineHeight", "textAlign", "maxLines", "overflow", "softWrap",
    }
    colors = {
        "color", "contentColor", "containerColor", "backgroundColor", "tint",
        "trackColor", "selectedContentColor", "unselectedContentColor",
    }
    surfaces = {
        "background", "border", "clip", "shadow", "shape", "elevation",
        "tonalElevation", "shadowElevation", "alpha",
    }
    assets = {
        "painter", "imageVector", "bitmap", "contentScale", "colorFilter", "filterQuality",
    }
    transforms = {"offset", "absoluteOffset", "rotate", "scale", "graphicsLayer"}
    state = {
        "state", "value", "checked", "selected", "enabled", "expanded", "isError",
        "visible", "progress", "items", "list", "data",
    }
    behavior = {
        "onClick", "onValueChange", "onCheckedChange", "onDismissRequest",
        "onClosePress", "onSubmitPress", "onSelectPress", "onTransactionPress",
        "onContactPress", "sendMoneyPress", "payBillsPress", "logoutPress",
    }
    groups: set[str] = set()
    if name in geometry:
        groups.add("geometry")
    if name in typography:
        groups.add("typography")
    if name in colors:
        groups.add("color")
    if name in surfaces:
        groups.add("surface")
    if name in assets:
        groups.add("asset")
    if name in transforms:
        groups.add("transform")
    if name in state or name.lower().endswith("state"):
        groups.add("state")
    if name in behavior or name.startswith("on") or name.endswith("Press"):
        groups.add("behavior")
    if name in {"text", "contentDescription", "label", "placeholder", "title"}:
        groups.add("content")
    if origin == "state_slot":
        groups.add("state")
    if component in {"Column", "Row", "Box", "Spacer", "LazyColumn", "LazyRow", "ConstraintLayout"} and not groups:
        groups.add("geometry")
    if component == "Text" and not groups:
        groups.add("typography")
    if component in {"Image", "Icon"} and not groups:
        groups.add("asset")
    if not groups:
        groups.add("component_semantics")
    return sorted(groups)


def sanitized_attribute(
    call: dict[str, Any],
    origin: str,
    name: str,
    semantics: dict[str, Any],
    modifier_index: int | None = None,
) -> dict[str, Any]:
    if IDENTIFIER_PATTERN.fullmatch(name) is None and re.fullmatch(r"position_[0-9]+", name) is None:
        raise SourceAttributeError("source attribute name is not a safe identifier")
    item: dict[str, Any] = {
        "call_id": call["call_id"],
        "line": call["line"],
        "component": call["component"],
        "origin": origin,
        "name": name,
        "groups": attribute_groups(call["component"], origin, name),
        "dimensions": safe_dimensions(semantics.get("dimensions", [])),
        "dimension_resources": safe_resources(semantics.get("dimension_resources", [])),
    }
    if modifier_index is not None:
        item["modifier_index"] = modifier_index
    return item


def call_attributes(call: dict[str, Any]) -> list[dict[str, Any]]:
    attributes: list[dict[str, Any]] = []
    semantic = call.get("semantic_arguments")
    positional = call.get("positional_arguments")
    modifiers = call.get("ordered_modifier_chain")
    slots = call.get("state_slots")
    if not isinstance(semantic, dict) or not isinstance(positional, list) or not isinstance(modifiers, list) or not isinstance(slots, list):
        raise SourceAttributeError("semantic call attribute inventory is malformed")
    for name, value in semantic.items():
        if not isinstance(name, str) or not isinstance(value, dict):
            raise SourceAttributeError("semantic argument inventory is malformed")
        attributes.append(sanitized_attribute(call, "semantic_argument", name, value))
    if not isinstance(call.get("custom_composable"), dict):
        for index, value in enumerate(positional):
            if not isinstance(value, dict):
                raise SourceAttributeError("positional argument inventory is malformed")
            attributes.append(
                sanitized_attribute(call, "positional_argument", f"position_{index}", value)
            )
    for index, modifier in enumerate(modifiers):
        if not isinstance(modifier, dict) or not isinstance(modifier.get("name"), str):
            raise SourceAttributeError("Modifier inventory is malformed")
        attributes.append(
            sanitized_attribute(call, "modifier", modifier["name"], modifier, index)
        )
    for slot in slots:
        if not isinstance(slot, dict) or not isinstance(slot.get("name"), str):
            raise SourceAttributeError("state-slot inventory is malformed")
        attributes.append(sanitized_attribute(call, "state_slot", slot["name"], {}))
    custom = call.get("custom_composable")
    invocation = custom.get("arguments") if isinstance(custom, dict) else None
    if invocation is not None:
        if not isinstance(invocation, list):
            raise SourceAttributeError("project invocation argument inventory is malformed")
        for index, value in enumerate(invocation):
            if not isinstance(value, dict):
                raise SourceAttributeError("project invocation argument is malformed")
            raw_name = value.get("name")
            name = raw_name if isinstance(raw_name, str) else f"position_{index}"
            if not str(value.get("expression", "")).strip():
                continue
            attributes.append(
                sanitized_attribute(call, "invocation_argument", name, value)
            )
    return attributes


def composable_semantic_keys(reached: list[tuple[str, str]]) -> dict[tuple[str, str], str]:
    counts: dict[str, int] = {}
    for _, name in reached:
        counts[name] = counts.get(name, 0) + 1
    result: dict[tuple[str, str], str] = {}
    for source, name in reached:
        if counts[name] == 1:
            result[(source, name)] = name
        else:
            suffix = hashlib.sha256(f"{source}#{name}".encode("utf-8")).hexdigest()[:8]
            result[(source, name)] = f"{name}_{suffix}"
    return result


def call_semantic_key(
    composable_key: str,
    call: dict[str, Any],
) -> str:
    call_id = call.get("call_id")
    component = call.get("component")
    line = call.get("line")
    if (
        not isinstance(call_id, str)
        or not call_id
        or not isinstance(component, str)
        or IDENTIFIER_PATTERN.fullmatch(component) is None
        or type(line) is not int
        or line <= 0
    ):
        raise SourceAttributeError("semantic call identity is malformed")
    ordinal = call_id.rsplit(":", 1)[-1]
    if not ordinal.isdigit():
        raise SourceAttributeError("semantic call ordinal is malformed")
    readable = f"{composable_key}_{component}_{line}_{ordinal}"
    if len(readable) <= 120:
        return readable
    suffix = hashlib.sha256(call_id.encode("utf-8")).hexdigest()[:12]
    prefix_length = 120 - len(suffix) - 1
    return f"{readable[:prefix_length]}_{suffix}"


def static_dp_value(expression: str) -> float | None:
    match = re.fullmatch(
        r"\s*\(?\s*(-?[0-9]+(?:\.[0-9]+)?)\s*\)?\.dp\s*",
        expression,
    )
    return float(match.group(1)) if match is not None else None


def static_number_value(expression: str) -> float | None:
    match = re.fullmatch(
        r"\s*\(?\s*(-?[0-9]+(?:\.[0-9]+)?)\s*\)?(?:[fF])?\s*",
        expression,
    )
    return float(match.group(1)) if match is not None else None


def resolved_visual_geometry(call: dict[str, Any]) -> dict[str, Any] | None:
    """Retain only compile-time numeric geometry; never retain display content."""
    modifiers = call.get("ordered_modifier_chain")
    if not isinstance(modifiers, list):
        raise SourceAttributeError("Modifier inventory is malformed")
    layout: dict[str, float] = {}
    transform: dict[str, float] = {}
    transform_seen = False
    for modifier in modifiers:
        if not isinstance(modifier, dict):
            raise SourceAttributeError("Modifier inventory is malformed")
        name = modifier.get("name")
        arguments = modifier.get("arguments")
        if not isinstance(name, str) or not isinstance(arguments, str):
            raise SourceAttributeError("Modifier inventory is malformed")
        positional, named = named_arguments(arguments)
        if name in {"width", "requiredWidth", "height", "requiredHeight"} and len(positional) == 1 and not named:
            value = static_dp_value(positional[0])
            if value is not None:
                layout["width_dp" if "Width" in name or name == "width" else "height_dp"] = value
        elif name in {"size", "requiredSize"}:
            if len(positional) == 1 and not named:
                value = static_dp_value(positional[0])
                if value is not None:
                    layout.update({"width_dp": value, "height_dp": value})
            elif not positional and set(named) <= {"width", "height"}:
                for axis in ("width", "height"):
                    value = static_dp_value(named[axis]) if axis in named else None
                    if value is not None:
                        layout[f"{axis}_dp"] = value
        elif name in {"offset", "absoluteOffset"}:
            x_source = named.get("x") or (positional[0] if positional else None)
            y_source = named.get("y") or (positional[1] if len(positional) > 1 else None)
            x = static_dp_value(x_source) if x_source is not None else 0.0
            y = static_dp_value(y_source) if y_source is not None else 0.0
            if x is not None and y is not None:
                transform["translation_x_dp"] = x
                transform["translation_y_dp"] = y
                transform_seen = True
        elif name == "rotate" and len(positional) == 1 and not named:
            angle = static_number_value(positional[0])
            if angle is not None:
                transform["rotation_degrees"] = angle
                transform_seen = True
    if transform_seen:
        transform.setdefault("translation_x_dp", 0.0)
        transform.setdefault("translation_y_dp", 0.0)
        transform.setdefault("scale_x", 1.0)
        transform.setdefault("scale_y", 1.0)
        transform.setdefault("rotation_degrees", 0.0)
    if not layout and not transform:
        return None
    return {"layout": layout, "transform": transform}


def resolved_definition_targets(call: dict[str, Any]) -> list[tuple[str, str]]:
    custom = call.get("custom_composable")
    raw_definitions = custom.get("definitions") if isinstance(custom, dict) else None
    if custom is None or raw_definitions is None:
        return []
    if not isinstance(raw_definitions, list):
        raise SourceAttributeError("project component definition inventory is malformed")
    targets: list[tuple[str, str]] = []
    for definition in raw_definitions:
        if (
            not isinstance(definition, dict)
            or not isinstance(definition.get("source"), str)
            or not isinstance(definition.get("composable"), str)
        ):
            raise SourceAttributeError("project component definition inventory is malformed")
        targets.append((definition["source"], definition["composable"]))
    return targets


def source_hierarchy(
    selected_calls: list[dict[str, Any]],
    keys: dict[tuple[str, str], str],
    root: tuple[str, str],
) -> dict[str, dict[str, Any]]:
    call_by_id = {call["call_id"]: call for call in selected_calls}
    key_by_id = {
        call_id: call_semantic_key(keys[(call["source"], call["composable"])], call)
        for call_id, call in call_by_id.items()
    }
    calls_by_definition: dict[tuple[str, str], list[dict[str, Any]]] = {}
    invocations_by_definition: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for call in selected_calls:
        definition_key = (call["source"], call["composable"])
        calls_by_definition.setdefault(definition_key, []).append(call)
        for target in resolved_definition_targets(call):
            if target in keys:
                invocations_by_definition.setdefault(target, []).append(call)
    for calls in calls_by_definition.values():
        calls.sort(key=lambda item: (item["line"], item["call_id"]))

    parent_by_key: dict[str, str | None] = {}
    mapping_by_key: dict[str, str] = {}
    children_by_id: dict[str | None, list[dict[str, Any]]] = {}
    roots_by_definition: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for definition_key, calls in calls_by_definition.items():
        ids = {call["call_id"] for call in calls}
        for call in calls:
            parent_id = call.get("parent_call_id")
            if isinstance(parent_id, str) and parent_id in ids:
                parent_by_key[key_by_id[call["call_id"]]] = key_by_id[parent_id]
                mapping_by_key[key_by_id[call["call_id"]]] = "resolved_static_call_graph"
                children_by_id.setdefault(parent_id, []).append(call)
            else:
                roots_by_definition.setdefault(definition_key, []).append(call)
                invocations = invocations_by_definition.get(definition_key, [])
                parent_by_key[key_by_id[call["call_id"]]] = (
                    key_by_id[invocations[0]["call_id"]]
                    if definition_key != root and len(invocations) == 1
                    else None
                )
                mapping_by_key[key_by_id[call["call_id"]]] = (
                    "ambiguous_runtime_fallback"
                    if definition_key != root and len(invocations) != 1
                    else "resolved_static_call_graph"
                )
    for calls in children_by_id.values():
        calls.sort(key=lambda item: (item["line"], item["call_id"]))

    order: dict[str, int] = {}
    active_definitions: set[tuple[str, str]] = set()

    def visit_call(call: dict[str, Any]) -> None:
        semantic_key = key_by_id[call["call_id"]]
        if semantic_key in order:
            return
        order[semantic_key] = len(order)
        for target in resolved_definition_targets(call):
            if target in keys and len(invocations_by_definition.get(target, [])) == 1:
                visit_definition(target)
        for child in children_by_id.get(call["call_id"], []):
            visit_call(child)

    def visit_definition(definition_key: tuple[str, str]) -> None:
        if definition_key in active_definitions:
            return
        active_definitions.add(definition_key)
        for call in roots_by_definition.get(definition_key, []):
            visit_call(call)
        active_definitions.remove(definition_key)

    visit_definition(root)
    for call in sorted(
        selected_calls,
        key=lambda item: (item["source"], item["composable"], item["line"], item["call_id"]),
    ):
        visit_call(call)
    return {
        semantic_key: {
            "parent_semantic_key": parent_by_key.get(semantic_key),
            "preorder_index": order[semantic_key],
            "mapping": mapping_by_key[semantic_key],
        }
        for semantic_key in order
    }


def write_new_file(path: Path, payload: bytes) -> None:
    requested = Path(os.path.abspath(os.path.expanduser(str(path))))
    if requested.exists() or requested.is_symlink():
        raise SourceAttributeError("source attribute output already exists")
    parent = requested.parent
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink():
        raise SourceAttributeError("source attribute output parent must not be a symbolic link")
    with tempfile.NamedTemporaryFile(dir=parent, prefix=f".{requested.name}.", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, requested)
    finally:
        temporary.unlink(missing_ok=True)


def generate(
    contract_path: Path,
    root_source: str,
    root_composable: str,
    output: Path,
) -> dict[str, Any]:
    root_source = require_safe_relative_source(root_source)
    contract, resolved_contract = load_contract(contract_path)
    if contract is None or resolved_contract is None:
        raise SourceAttributeError("migration contract is required")
    try:
        closure, all_calls, definitions = require_contract_ui(
            contract, root_source, root_composable
        )
    except (TypeError, ValueError, RuntimeError) as error:
        raise SourceAttributeError(str(error)) from error
    reached_items = closure.get("reached_definitions")
    if not isinstance(reached_items, list):
        raise SourceAttributeError("selected closure reached definitions are malformed")
    reached = [(item["source"], item["composable"]) for item in reached_items]
    reached_set = set(reached)
    keys = composable_semantic_keys(reached)
    selected_calls = [
        call
        for call in all_calls
        if (call.get("source"), call.get("composable")) in reached_set
    ]
    hierarchy = source_hierarchy(
        selected_calls,
        keys,
        (root_source, root_composable),
    )
    components: list[dict[str, Any]] = []
    for call in sorted(
        selected_calls,
        key=lambda item: (
            item["source"], item["composable"], item["line"], item["call_id"]
        ),
    ):
        key = (call["source"], call["composable"])
        attributes = call_attributes(call)
        if not attributes:
            attributes = [sanitized_attribute(call, "call_site", "component", {})]
        semantic_key = call_semantic_key(keys[key], call)
        component = {
            "semantic_key": semantic_key,
            "source": key[0],
            "composable": key[1],
            "source_hierarchy": hierarchy[semantic_key],
            "attributes": attributes,
        }
        geometry = resolved_visual_geometry(call)
        if geometry is not None:
            component["resolved_visual_geometry"] = geometry
        components.append(component)
    semantic_input = {
        "root": {"source": root_source, "composable": root_composable},
        "closure": closure,
        "definitions": [definitions[key] for key in reached],
        "calls": selected_calls,
    }
    payload = {
        "schema": INVENTORY_SCHEMA,
        "status": "candidate_requires_review",
        "authoritative": False,
        "root": {"source": root_source, "composable": root_composable},
        "contract_sha256": sha256_file(resolved_contract),
        "semantic_input_sha256": canonical_sha256(semantic_input),
        "components": components,
        "limitations": [
            "Only structural attribute names, locations, units, and resource keys are retained; source values and display content are excluded.",
            "Static call and component resolution remains candidate-only and requires source reconciliation.",
            "Each semantic key identifies one exact source call so a runtime component can drive one ArkUI call without an ambiguous composable-wide mapping.",
            "Source hierarchy expands uniquely invoked project composables and supplies a stable preorder; ambiguous repeated invocations remain runtime-mapped.",
            "Only compile-time numeric dp sizes, offsets, scales, and rotations are retained as source-resolved visual geometry; display values remain excluded.",
            "A mapped visual hotspot ranks attributes to inspect; it does not identify a proven defect or prescribe a fix.",
        ],
    }
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    write_new_file(output, encoded)
    return {
        "output": str(Path(os.path.abspath(os.path.expanduser(str(output))))),
        "output_sha256": hashlib.sha256(encoded).hexdigest(),
        "component_count": len(components),
        "attribute_count": sum(len(item["attributes"]) for item in components),
    }


def main() -> int:
    args = parse_args()
    try:
        result = generate(
            args.contract,
            args.root_source,
            args.root_composable,
            args.output,
        )
    except (SourceAttributeError, OSError, TypeError, ValueError) as error:
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
                **result,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
