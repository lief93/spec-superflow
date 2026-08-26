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

from generate_arkui_page import (
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


def semantic_keys(reached: list[tuple[str, str]]) -> dict[tuple[str, str], str]:
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
    keys = semantic_keys(reached)
    selected_calls = [
        call
        for call in all_calls
        if (call.get("source"), call.get("composable")) in reached_set
    ]
    calls_by_definition: dict[tuple[str, str], list[dict[str, Any]]] = {
        key: [] for key in reached
    }
    for call in selected_calls:
        calls_by_definition[(call["source"], call["composable"])].append(call)
    components: list[dict[str, Any]] = []
    for key in sorted(reached):
        attributes = [
            attribute
            for call in sorted(
                calls_by_definition[key], key=lambda item: (item["line"], item["call_id"])
            )
            for attribute in call_attributes(call)
        ]
        components.append(
            {
                "semantic_key": keys[key],
                "source": key[0],
                "composable": key[1],
                "attributes": attributes,
            }
        )
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
