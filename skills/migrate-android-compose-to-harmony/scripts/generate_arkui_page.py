#!/usr/bin/env python3
"""Generate a conservative ArkUI page from one exact Compose closure."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
import re
import sys
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from generate_harmony_theme_resources import commit_payloads, json_bytes
from init_harmony_project import has_external_ownership_proof, load_contract, sha256_file
from page_snapshot import (
    PAGE_SCHEMA as PAGE_SNAPSHOT_SCHEMA,
    PageSnapshotError,
    normalize_provenance,
    normalize_style,
    normalize_unresolved,
    require_token,
)


MANIFEST_SCHEMA = "android-to-harmony.arkui-page-generation.v1"
TARGET_STATE_SCHEMA = "android-to-harmony.project-state.v1"
MODULE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RESOURCE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
PAGE_INPUT_MAX_BYTES = 10 * 1024 * 1024
FONT_WEIGHT_VALUES = {
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
FONT_KEY_SUFFIXES = {
    "thin": 100,
    "extralight": 200,
    "light": 300,
    "regular": 400,
    "normal": 400,
    "medium": 500,
    "semibold": 600,
    "bold": 700,
    "extrabold": 800,
    "black": 900,
}
DIMENSION_PATTERN = re.compile(r"^(-?[0-9]+(?:\.[0-9]+)?)\s*\.\s*(dp|sp)$")
EXPANDABLE_THEN_MODIFIERS = {
    "width",
    "height",
    "size",
    "fillMaxWidth",
    "fillMaxHeight",
    "fillMaxSize",
    "padding",
    "background",
    "weight",
    "wrapContentWidth",
    "wrapContentHeight",
    "wrapContentSize",
    "matchParentSize",
    "widthIn",
    "requiredWidthIn",
    "heightIn",
    "sizeIn",
    "alpha",
    "offset",
    "rotate",
    "clickable",
}
OPTIONAL_FONT_COLOR_PREFIX = "__optional_font_color__:"
FALLBACK_LIST_ITEM_TYPE = "GeneratedFallbackListItem"
ROOT_PUBLIC_PARAMETER_ALIASES = {
    "enabled": "enabledValue",
}
BUTTON_CONTAINER_COMPONENTS = {
    "Button", "TextButton", "OutlinedButton", "IconButton", "FloatingActionButton",
    "SmallFloatingActionButton",
}
STACK_RENDERED_COMPONENTS = {
    "Box",
    "BoxWithConstraints",
    "Canvas",
    "DatePickerDialog",
    "AnimatedVisibility",
    "ModalBottomSheet",
    "PullToRefreshBox",
    "Surface",
    "TopAppBar",
    "CenterAlignedTopAppBar",
}
BLANK_UNSAFE_PARENT_COMPONENTS = BUTTON_CONTAINER_COMPONENTS | STACK_RENDERED_COMPONENTS | {"ListItem", "Stack"}


class ArkUIPageError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate one candidate ArkUI page from an exact Compose component closure."
    )
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--module", default="entry")
    parser.add_argument("--root-source", required=True)
    parser.add_argument("--root-composable", required=True)
    parser.add_argument(
        "--android-page-json",
        type=Path,
        help="optional Android page-snapshot.v2 whose proven visual facts override static visual defaults",
    )
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def normalize_target(path: Path) -> Path:
    absolute = Path(os.path.abspath(os.path.expanduser(str(path))))
    if absolute.is_symlink():
        raise ArkUIPageError(f"target must not be a symbolic link: {absolute}")
    target = absolute.resolve()
    if not target.is_dir():
        raise ArkUIPageError(f"target project does not exist: {target}")
    state_path = target / ".migration" / "state.json"
    if not state_path.is_file() or state_path.is_symlink():
        raise ArkUIPageError("target project marker is missing")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ArkUIPageError(f"target project marker is invalid: {error}") from error
    if (
        not isinstance(state, dict)
        or state.get("schema") != TARGET_STATE_SCHEMA
        or state.get("generator") != "migrate-android-compose-to-harmony"
        or not has_external_ownership_proof(target, state)
    ):
        raise ArkUIPageError("target project ownership proof is invalid")
    return target


def require_module(target: Path, module: str) -> Path:
    if MODULE_PATTERN.fullmatch(module) is None:
        raise ArkUIPageError(
            "module must start with a letter and contain only letters, digits, underscores, or hyphens"
        )
    module_root = target / module
    main_root = module_root / "src" / "main"
    if module_root.is_symlink() or not module_root.is_dir():
        raise ArkUIPageError(f"target module does not exist: {module}")
    if main_root.is_symlink() or not main_root.is_dir():
        raise ArkUIPageError(f"target module main source set is missing: {module}")
    return module_root


def require_safe_relative_source(value: str) -> str:
    candidate = Path(value)
    if (
        not value
        or candidate.is_absolute()
        or ".." in candidate.parts
        or candidate.as_posix() != value
    ):
        raise ArkUIPageError("root source must be a normalized contract-relative path")
    return value


def require_contract_ui(
    contract: dict[str, Any], root_source: str, root_composable: str
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    if IDENTIFIER_PATTERN.fullmatch(root_composable) is None:
        raise ArkUIPageError("root composable must be a Kotlin identifier")
    ui = contract.get("ui")
    semantic = ui.get("semantic_translation_candidates") if isinstance(ui, dict) else None
    graph = ui.get("custom_composable_call_graph") if isinstance(ui, dict) else None
    composables = ui.get("composables") if isinstance(ui, dict) else None
    if not isinstance(semantic, dict) or not isinstance(semantic.get("calls"), list):
        raise ArkUIPageError("contract has no semantic Compose call inventory")
    if not isinstance(graph, dict) or not isinstance(graph.get("transitive_closures"), list):
        raise ArkUIPageError("contract has no transitive custom composable closures")
    if not isinstance(composables, list):
        raise ArkUIPageError("contract has no Compose definition inventory")
    matches = [
        item
        for item in graph["transitive_closures"]
        if isinstance(item, dict)
        and item.get("root")
        == {"source": root_source, "composable": root_composable}
    ]
    if len(matches) != 1:
        raise ArkUIPageError(
            "exact root source/composable closure was not found"
            if not matches
            else "exact root source/composable closure is not unique"
        )
    definitions: dict[tuple[str, str], dict[str, Any]] = {}
    for item in composables:
        if not isinstance(item, dict):
            raise ArkUIPageError("Compose definition inventory is invalid")
        source = item.get("source")
        name = item.get("name")
        parameters = item.get("parameters")
        if not isinstance(source, str) or not isinstance(name, str) or not isinstance(parameters, list):
            raise ArkUIPageError("Compose definition inventory entry is invalid")
        key = (source, name)
        if key in definitions:
            raise ArkUIPageError(f"duplicate Compose definition: {source}#{name}")
        definitions[key] = item
    return matches[0], semantic["calls"], definitions


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_android_page_input(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    requested = Path(os.path.abspath(os.path.expanduser(str(path))))
    if requested.is_symlink() or not requested.is_file():
        raise ArkUIPageError("Android page JSON must be an existing non-symbolic-link file")
    byte_count = requested.stat().st_size
    if byte_count <= 0 or byte_count > PAGE_INPUT_MAX_BYTES:
        raise ArkUIPageError("Android page JSON must contain 1 byte to 10 MiB")
    try:
        payload = json.loads(requested.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ArkUIPageError(f"Android page JSON is invalid: {error}") from error
    required_fields = {
        "schema",
        "status",
        "authoritative",
        "platform",
        "page",
        "viewport",
        "capture",
        "input_hashes",
        "components",
        "unmapped_source_components",
        "unmapped_visual_fact_components",
        "limitations",
    }
    if not isinstance(payload, dict) or set(payload) != required_fields:
        raise ArkUIPageError("Android page JSON has unsupported root fields")
    if payload.get("schema") != PAGE_SNAPSHOT_SCHEMA:
        raise ArkUIPageError("Android page JSON must use android-to-harmony.page-snapshot.v2")
    if payload.get("platform") != "android":
        raise ArkUIPageError("Android page JSON platform must be android")
    if payload.get("status") != "candidate_requires_review" or payload.get("authoritative") is not False:
        raise ArkUIPageError("Android page JSON must retain candidate, non-authoritative status")
    page = payload.get("page")
    if not isinstance(page, dict) or set(page) != {"id", "state"}:
        raise ArkUIPageError("Android page JSON page identity is malformed")
    try:
        normalized_page = {
            "id": require_token(page["id"], "Android page id"),
            "state": require_token(page["state"], "Android page state"),
        }
    except PageSnapshotError as error:
        raise ArkUIPageError(str(error)) from error
    viewport = payload.get("viewport")
    if not isinstance(viewport, dict):
        raise ArkUIPageError("Android page JSON viewport is malformed")
    density = viewport.get("density")
    font_scale = viewport.get("font_scale")
    orientation = viewport.get("orientation")
    if (
        type(density) not in {int, float}
        or not math.isfinite(float(density))
        or float(density) <= 0
        or type(font_scale) not in {int, float}
        or not math.isfinite(float(font_scale))
        or float(font_scale) <= 0
        or orientation not in {"portrait", "landscape"}
    ):
        raise ArkUIPageError("Android page JSON viewport scale or orientation is malformed")
    capture = payload.get("capture")
    screenshot = capture.get("screenshot") if isinstance(capture, dict) else None
    if (
        not isinstance(screenshot, dict)
        or not isinstance(screenshot.get("file"), str)
        or not screenshot["file"]
        or Path(screenshot["file"]).name != screenshot["file"]
        or type(screenshot.get("byte_count")) is not int
        or screenshot["byte_count"] <= 0
        or not isinstance(screenshot.get("sha256"), str)
        or SHA256_PATTERN.fullmatch(screenshot["sha256"]) is None
    ):
        raise ArkUIPageError("Android page JSON screenshot binding is malformed")
    raw_components = payload.get("components")
    if not isinstance(raw_components, list) or len(raw_components) > 10000:
        raise ArkUIPageError("Android page JSON components must contain at most 10000 entries")
    components: list[dict[str, Any]] = []
    component_ids: set[str] = set()
    call_id_owners: dict[str, str] = {}
    by_call_id: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(raw_components):
        if not isinstance(raw, dict):
            raise ArkUIPageError("Android page JSON contains a non-object component")
        try:
            component_id = require_token(raw.get("id"), "Android page component id")
            component_type = require_token(raw.get("type"), "Android page component type")
        except PageSnapshotError as error:
            raise ArkUIPageError(str(error)) from error
        if component_id in component_ids:
            raise ArkUIPageError("Android page JSON contains duplicate component IDs")
        component_ids.add(component_id)
        bounds_dp = raw.get("bounds_dp")
        if (
            not isinstance(bounds_dp, dict)
            or set(bounds_dp) != {"x", "y", "width", "height"}
            or any(type(bounds_dp[field]) not in {int, float} for field in bounds_dp)
            or any(not math.isfinite(float(bounds_dp[field])) for field in bounds_dp)
            or bounds_dp["x"] < 0
            or bounds_dp["y"] < 0
            or bounds_dp["width"] <= 0
            or bounds_dp["height"] <= 0
        ):
            raise ArkUIPageError(f"Android page component {component_id} has malformed logical bounds")
        try:
            style = normalize_style(raw.get("style"), f"Android page component {component_id}.style")
            provenance = normalize_provenance(
                raw.get("provenance"), f"Android page component {component_id}.provenance"
            )
            unresolved = normalize_unresolved(
                raw.get("unresolved"), f"Android page component {component_id}.unresolved"
            )
        except PageSnapshotError as error:
            raise ArkUIPageError(str(error)) from error
        source = raw.get("source")
        parent_id = raw.get("parent_id")
        children_ids = raw.get("children_ids")
        sibling_index = raw.get("sibling_index")
        parent_mapping = raw.get("parent_mapping")
        try:
            if parent_id is not None:
                parent_id = require_token(parent_id, "Android page component parent_id")
            if (
                not isinstance(children_ids, list)
                or len(children_ids) > 10000
            ):
                raise ArkUIPageError(
                    f"Android page component {component_id} children_ids are malformed"
                )
            normalized_children = [
                require_token(child_id, "Android page component children_ids")
                for child_id in children_ids
            ]
        except PageSnapshotError as error:
            raise ArkUIPageError(str(error)) from error
        if len(normalized_children) != len(set(normalized_children)):
            raise ArkUIPageError(
                f"Android page component {component_id} contains duplicate children_ids"
            )
        if type(sibling_index) is not int or sibling_index < 0:
            raise ArkUIPageError(
                f"Android page component {component_id} sibling_index is malformed"
            )
        if parent_mapping not in {
            "smallest-containing-runtime-component", "source-semantic-ancestor"
        }:
            raise ArkUIPageError(
                f"Android page component {component_id} parent_mapping is unsupported"
            )
        call_ids: list[str] = []
        if source is not None:
            if not isinstance(source, dict) or not isinstance(source.get("attributes"), list):
                raise ArkUIPageError(f"Android page component {component_id} source mapping is malformed")
            for attribute in source["attributes"]:
                if not isinstance(attribute, dict) or not isinstance(attribute.get("call_id"), str):
                    raise ArkUIPageError(
                        f"Android page component {component_id} source attribute has no call_id"
                    )
                call_ids.append(attribute["call_id"])
        component = {
            "id": component_id,
            "type": component_type,
            "semantic_key": raw.get("semantic_key"),
            "bounds_dp": {name: float(bounds_dp[name]) for name in ("x", "y", "width", "height")},
            "parent_id": parent_id,
            "children_ids": normalized_children,
            "sibling_index": sibling_index,
            "parent_mapping": parent_mapping,
            "style": style,
            "provenance": provenance,
            "unresolved": unresolved,
            "call_ids": sorted(set(call_ids)),
        }
        if component["semantic_key"] is not None:
            try:
                component["semantic_key"] = require_token(
                    component["semantic_key"], "Android page component semantic_key"
                )
            except PageSnapshotError as error:
                raise ArkUIPageError(str(error)) from error
        components.append(component)
        if len(component["call_ids"]) == 1:
            call_id = component["call_ids"][0]
            if call_id in call_id_owners:
                raise ArkUIPageError(
                    "Android page JSON maps multiple runtime components to one source call: "
                    + call_id
                )
            call_id_owners[call_id] = component_id
            by_call_id[call_id] = component
    by_id = {component["id"]: component for component in components}
    for component in components:
        parent_id = component["parent_id"]
        if parent_id is not None and parent_id not in by_id:
            raise ArkUIPageError("Android page component parent_id references an unknown component")
        if any(child_id not in by_id for child_id in component["children_ids"]):
            raise ArkUIPageError("Android page component children_ids reference an unknown component")
        if parent_id is not None and component["id"] not in by_id[parent_id]["children_ids"]:
            raise ArkUIPageError("Android page component parent/child relationship is inconsistent")
        for child_id in component["children_ids"]:
            if by_id[child_id]["parent_id"] != component["id"]:
                raise ArkUIPageError("Android page component parent/child relationship is inconsistent")
            if by_id[child_id]["sibling_index"] != component["children_ids"].index(child_id):
                raise ArkUIPageError("Android page component sibling order is inconsistent")
    return {
        "file": requested.name,
        "byte_count": byte_count,
        "sha256": sha256_file(requested),
        "page": normalized_page,
        "viewport": {
            "density": float(density),
            "font_scale": float(font_scale),
            "orientation": orientation,
        },
        "screenshot": {
            "file": screenshot["file"],
            "byte_count": screenshot["byte_count"],
            "sha256": screenshot["sha256"],
        },
        "components": components,
        "by_id": by_id,
        "by_call_id": by_call_id,
    }


def pascal_identifier(value: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", value)
    candidate = "".join(word[:1].upper() + word[1:] for word in words) or "Page"
    if candidate[0].isdigit():
        candidate = f"Page{candidate}"
    return candidate


def builder_name(source: str, composable: str) -> str:
    suffix = hashlib.sha256(f"{source}#{composable}".encode("utf-8")).hexdigest()[:8]
    return f"{pascal_identifier(composable)}_{suffix}"


def data_class_interface_name(base_type: str) -> str:
    return f"GeneratedDataClass{pascal_identifier(base_type)}"


def split_arguments(value: str) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    depth = 0
    quote: str | None = None
    escaped = False
    for character in value:
        if quote is not None:
            current.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            quote = character
            current.append(character)
        elif character in "([{<":
            depth += 1
            current.append(character)
        elif character in ")]}>":
            depth = max(0, depth - 1)
            current.append(character)
        elif character == "," and depth == 0:
            chunks.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    if current or value.strip():
        chunks.append("".join(current).strip())
    return [chunk for chunk in chunks if chunk]


def split_top_level_elvis(value: str) -> tuple[str, str] | None:
    depth = 0
    quote: str | None = None
    escaped = False
    for index, character in enumerate(value):
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
        elif character in "([{<":
            depth += 1
        elif character in ")]}>":
            depth = max(0, depth - 1)
        elif character == "?" and depth == 0 and index + 1 < len(value) and value[index + 1] == ":":
            return value[:index].strip(), value[index + 2 :].strip()
    return None


def split_top_level_operator(value: str, operator: str) -> tuple[str, str] | None:
    depth = 0
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(value):
        character = value[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            index += 1
            continue
        if character in {'"', "'"}:
            quote = character
        elif character in "([{<":
            depth += 1
        elif character in ")]}>":
            depth = max(0, depth - 1)
        elif depth == 0 and value.startswith(operator, index):
            return value[:index].strip(), value[index + len(operator) :].strip()
        index += 1
    return None


def kotlin_if_else_parts(expression: str) -> tuple[str, str, str] | None:
    stripped = expression.strip()
    if stripped.startswith("if"):
        condition_open = stripped.find("(")
        condition_close = closing_parenthesis(stripped, condition_open)
        if condition_open >= 0 and condition_close is not None:
            condition = stripped[condition_open + 1 : condition_close].strip()
            remainder = stripped[condition_close + 1 :].strip()
            if remainder.startswith("{"):
                true_close = closing_brace(remainder, 0)
                if true_close is not None:
                    true_branch = remainder[1:true_close].strip()
                    else_part = remainder[true_close + 1 :].strip()
                    if else_part.startswith("else"):
                        false_branch = else_part[len("else") :].strip()
                        if false_branch.startswith("{"):
                            false_close = closing_brace(false_branch, 0)
                            if false_close is not None and not false_branch[false_close + 1 :].strip():
                                return condition, true_branch, false_branch[1:false_close].strip()
                        elif false_branch.startswith("if"):
                            return condition, true_branch, false_branch
    unbraced = re.fullmatch(
        r"if\s*\((.+?)\)\s+(.+?)\s+else\s+(.+)",
        stripped,
        re.S,
    )
    if unbraced is not None:
        return unbraced.group(1).strip(), unbraced.group(2).strip(), unbraced.group(3).strip()
    return None


def strip_top_level_trailing_comma(value: str) -> str:
    stripped = value.strip()
    if not stripped.endswith(","):
        return stripped
    depth = 0
    quote: str | None = None
    escaped = False
    for character in stripped[:-1]:
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
        elif character in "([{<":
            depth += 1
        elif character in ")]}>":
            depth = max(0, depth - 1)
    return stripped[:-1].rstrip() if depth == 0 and quote is None else stripped


def strip_wrapping_parentheses(value: str) -> str:
    stripped = value.strip()
    while stripped.startswith("("):
        closing = closing_parenthesis(stripped, 0)
        if closing != len(stripped) - 1:
            break
        stripped = stripped[1:-1].strip()
    return stripped


def simple_when_branch_token_pattern() -> str:
    string_literal = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    identifier_path = r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*"
    color_literal = r"Color\s*\(\s*0x[0-9A-Fa-f]{8}\s*\)"
    return rf"(?:{string_literal}|{color_literal}|{identifier_path})"


def kotlin_subject_when_parts(expression: str) -> tuple[str, list[tuple[list[str], str]], str | None] | None:
    stripped = strip_top_level_trailing_comma(expression)
    if not stripped.startswith("when"):
        return None
    subject_opening = stripped.find("(")
    subject_closing = closing_parenthesis(stripped, subject_opening)
    if subject_opening < 0 or subject_closing is None:
        return None
    subject = stripped[subject_opening + 1 : subject_closing].strip()
    body_opening = stripped.find("{", subject_closing + 1)
    body_closing = closing_brace(stripped, body_opening) if body_opening >= 0 else None
    if body_opening < 0 or body_closing is None or stripped[body_closing + 1 :].strip():
        return None
    body = stripped[body_opening + 1 : body_closing].strip()
    token = simple_when_branch_token_pattern()
    branch_pattern = re.compile(
        rf"\s*(?P<cases>else|{token}(?:\s*,\s*{token})*)\s*->\s*"
        rf"(?P<value>.*?)"
        rf"(?=\s*(?:else|{token}(?:\s*,\s*{token})*)\s*->|\s*$)",
        re.S,
    )
    branches: list[tuple[list[str], str]] = []
    else_value: str | None = None
    cursor = 0
    while cursor < len(body):
        match = branch_pattern.match(body, cursor)
        if match is None:
            return None
        cases = match.group("cases").strip()
        value = strip_top_level_trailing_comma(match.group("value").strip())
        if not value:
            return None
        if cases == "else":
            if else_value is not None:
                return None
            else_value = value
        else:
            branches.append(([case.strip() for case in split_arguments(cases)], value))
        cursor = match.end()
    if not branches:
        return None
    return subject, branches, else_value


def named_arguments(value: str) -> tuple[list[str], dict[str, str]]:
    positional: list[str] = []
    named: dict[str, str] = {}
    for chunk in split_arguments(value):
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$", chunk, re.S)
        if match is None:
            positional.append(chunk)
        else:
            named[match.group(1)] = match.group(2).strip()
    return positional, named


def dimension_value(expression: str) -> str | None:
    stripped = expression.strip()
    parenthesized_number = re.fullmatch(
        r"\((-?[0-9]+(?:\.[0-9]+)?)\)\s*\.\s*(dp|sp)", stripped
    )
    if parenthesized_number is not None:
        return parenthesized_number.group(1)
    match = DIMENSION_PATTERN.fullmatch(stripped)
    if match is None:
        return None
    return match.group(1)


def number_value(expression: str) -> str | None:
    match = re.fullmatch(r"(-?[0-9]+(?:\.[0-9]+)?)(?:[fFdDlL])?", expression.strip())
    if match is None:
        return None
    return match.group(1)


def number_or_boolean_conditional_value(
    expression: str,
    parameters: dict[str, str],
) -> str | None:
    literal = number_value(expression)
    if literal is not None:
        return literal
    conditional = kotlin_if_else_parts(expression)
    if conditional is None:
        return None
    condition, true_branch, false_branch = conditional
    condition_expression = condition
    if parameters.get(condition) != "boolean":
        negated = re.fullmatch(r"!\s*([A-Za-z_][A-Za-z0-9_]*)", condition)
        if negated is None or parameters.get(negated.group(1)) != "boolean":
            return None
        condition_expression = f"!{negated.group(1)}"
    true_value = number_value(true_branch)
    false_value = number_value(false_branch)
    if true_value is None or false_value is None:
        return None
    return f"({condition_expression} ? {true_value} : {false_value})"


def modifier_let_conditional_modifier_expression(
    expression: str,
) -> list[dict[str, Any]] | None:
    conditional = kotlin_if_else_parts(expression)
    if conditional is None:
        return None
    condition, true_branch, false_branch = conditional

    def modifier_call(branch: str) -> tuple[str, str] | None:
        match = re.fullmatch(r"it\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)", branch.strip(), re.S)
        if match is None:
            return None
        return match.group(1), match.group(2).strip()

    def dp_unspecified_check(argument: str, operator: str) -> bool:
        argument = argument.strip()
        escaped = re.escape(argument)
        return (
            re.fullmatch(rf"{escaped}\s*{re.escape(operator)}\s*Dp\.Unspecified", condition) is not None
            or re.fullmatch(rf"Dp\.Unspecified\s*{re.escape(operator)}\s*{escaped}", condition) is not None
        )

    true_alpha = re.fullmatch(r"it\s*\.\s*alpha\s*\((.*)\)", true_branch, re.S)
    false_alpha = re.fullmatch(r"it\s*\.\s*alpha\s*\((.*)\)", false_branch, re.S)
    true_pointer_blocker = re.fullmatch(
        r"it\s*\.\s*pointerInput\s*\([^)]*\)\s*\{\s*detectTapGestures\s*\{\s*\}\s*\}",
        true_branch.strip(),
        re.S,
    )
    false_pointer_blocker = re.fullmatch(
        r"it\s*\.\s*pointerInput\s*\([^)]*\)\s*\{\s*detectTapGestures\s*\{\s*\}\s*\}",
        false_branch.strip(),
        re.S,
    )
    if true_pointer_blocker is not None and false_branch.strip() == "it":
        return [
            {
                "name": "hitTestBehavior",
                "arguments": f"if ({condition}) HitTestMode.Block else HitTestMode.Transparent",
            }
        ]
    if true_branch.strip() == "it" and false_pointer_blocker is not None:
        return [
            {
                "name": "hitTestBehavior",
                "arguments": f"if ({condition}) HitTestMode.Transparent else HitTestMode.Block",
            }
        ]
    if true_alpha is not None and false_branch.strip() == "it":
        return [
            {
                "name": "alpha",
                "arguments": f"if ({condition}) {true_alpha.group(1).strip()} else 1f",
            }
        ]
    if true_branch.strip() == "it" and false_alpha is not None:
        return [
            {
                "name": "alpha",
                "arguments": f"if ({condition}) 1f else {false_alpha.group(1).strip()}",
            }
        ]
    true_modifier = modifier_call(true_branch)
    false_modifier = modifier_call(false_branch)
    if true_modifier is not None and false_branch.strip() == "it":
        name, arguments = true_modifier
        if name in {"width", "height", "size"} and dp_unspecified_check(arguments, "!="):
            return [{"name": f"optional_{name}", "arguments": arguments}]
        if name == "background":
            positional, named = named_arguments(arguments)
            color_source = named.get("color") or (positional[0] if positional else None)
            shape_source = named.get("shape") or (positional[1] if len(positional) >= 2 else None)
            if color_source is None:
                return None
            translated_arguments = f"if ({condition}) {color_source} else Color.Transparent"
            if shape_source is not None:
                translated_arguments = f"{translated_arguments}, {shape_source}"
            return [{"name": "background", "arguments": translated_arguments}]
        if name == "clip" and IDENTIFIER_PATTERN.fullmatch(arguments) is not None:
            if re.fullmatch(rf"{re.escape(arguments)}\s*!=\s*null", condition) is None:
                return None
            return [{"name": "clip", "arguments": arguments}]
    if true_branch.strip() == "it" and false_modifier is not None:
        name, arguments = false_modifier
        if name in {"width", "height", "size"} and dp_unspecified_check(arguments, "=="):
            return [{"name": f"optional_{name}", "arguments": arguments}]
        if name == "background":
            positional, named = named_arguments(arguments)
            color_source = named.get("color") or (positional[0] if positional else None)
            shape_source = named.get("shape") or (positional[1] if len(positional) >= 2 else None)
            if color_source is None:
                return None
            translated_arguments = f"if ({condition}) Color.Transparent else {color_source}"
            if shape_source is not None:
                translated_arguments = f"{translated_arguments}, {shape_source}"
            return [{"name": "background", "arguments": translated_arguments}]
        if name == "clip" and IDENTIFIER_PATTERN.fullmatch(arguments) is not None:
            if re.fullmatch(rf"{re.escape(arguments)}\s*==\s*null", condition) is None:
                return None
            return [{"name": "clip", "arguments": arguments}]
    return None


def decimal_literal(value: Decimal) -> str:
    rendered = format(value.normalize(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def decimal_from_literal(value: str) -> Decimal | None:
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def decimal_binary(left: str, operator: str, right: str) -> str | None:
    left_value = decimal_from_literal(left)
    right_value = decimal_from_literal(right)
    if left_value is None or right_value is None:
        return None
    if operator == "*":
        return decimal_literal(left_value * right_value)
    if operator == "/":
        if right_value == 0:
            return None
        return decimal_literal(left_value / right_value)
    return None


def font_weight_expression(expression: str) -> str | None:
    stripped = expression.strip()
    constructor = re.fullmatch(r"FontWeight\s*\(\s*([0-9]+)\s*\)", stripped)
    if constructor is not None:
        return constructor.group(1)
    named = re.fullmatch(r"FontWeight\.([A-Za-z_][A-Za-z0-9_]*)", stripped)
    if named is None:
        return None
    weights = {
        "Thin": "100",
        "ExtraLight": "200",
        "Light": "300",
        "Normal": "400",
        "Regular": "400",
        "Medium": "500",
        "SemiBold": "600",
        "Bold": "700",
        "ExtraBold": "800",
        "Black": "900",
    }
    return weights.get(named.group(1))


def closing_parenthesis(value: str, opening: int) -> int | None:
    if opening < 0 or opening >= len(value) or value[opening] != "(":
        return None
    depth = 0
    for index in range(opening, len(value)):
        if value[index] == "(":
            depth += 1
        elif value[index] == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def closing_brace(value: str, opening: int) -> int | None:
    if opening < 0 or opening >= len(value) or value[opening] != "{":
        return None
    depth = 0
    for index in range(opening, len(value)):
        if value[index] == "{":
            depth += 1
        elif value[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def modifier_chain_expression(expression: str) -> list[dict[str, Any]]:
    stripped = expression.strip()
    if not stripped.startswith("Modifier"):
        return []
    result: list[dict[str, Any]] = []
    index = len("Modifier")
    while index < len(stripped):
        match = re.match(r"\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(", stripped[index:])
        if match is None:
            lambda_match = re.match(r"\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*\{", stripped[index:])
            if lambda_match is None:
                break
            opening = index + lambda_match.end() - 1
            closing = closing_brace(stripped, opening)
            if closing is None:
                break
            result.append(
                {
                    "name": lambda_match.group(1),
                    "arguments": stripped[opening + 1 : closing],
                }
            )
            index = closing + 1
            continue
        opening = index + match.end() - 1
        closing = closing_parenthesis(stripped, opening)
        if closing is None:
            break
        result.append(
            {
                "name": match.group(1),
                "arguments": stripped[opening + 1 : closing],
            }
        )
        index = closing + 1
    return result


def is_supported_vertical_scroll(modifier: dict[str, Any]) -> bool:
    if modifier.get("name") != "verticalScroll":
        return False
    arguments = modifier.get("arguments")
    return isinstance(arguments, str) and re.fullmatch(
        r"\s*rememberScrollState\s*\(\s*\)\s*",
        arguments,
    ) is not None


def is_supported_horizontal_scroll(modifier: dict[str, Any]) -> bool:
    if modifier.get("name") != "horizontalScroll":
        return False
    arguments = modifier.get("arguments")
    return isinstance(arguments, str) and re.fullmatch(
        r"\s*rememberScrollState\s*\(\s*\)\s*",
        arguments,
    ) is not None


def expand_then_containing_supported_scroll(chain: list[Any]) -> list[Any]:
    expanded: list[Any] = []
    for modifier in chain:
        if not isinstance(modifier, dict) or modifier.get("name") != "then":
            expanded.append(modifier)
            continue
        arguments = modifier.get("arguments")
        if not isinstance(arguments, str):
            expanded.append(modifier)
            continue
        nested = modifier_chain_expression(arguments)
        if nested and any(
            is_supported_vertical_scroll(item) or is_supported_horizontal_scroll(item)
            for item in nested
        ):
            expanded.extend(nested)
        else:
            expanded.append(modifier)
    return expanded


def chain_has_supported_scroll(chain: list[Any]) -> bool:
    return any(
        isinstance(item, dict) and (is_supported_vertical_scroll(item) or is_supported_horizontal_scroll(item))
        for item in chain
    )


def kotlin_string(expression: str) -> str | None:
    value = kotlin_string_value(expression)
    return arkts_string(value) if value is not None else None


def kotlin_string_value(expression: str) -> str | None:
    stripped = expression.strip()
    if not (stripped.startswith('"') and stripped.endswith('"')):
        return None
    if "${" in stripped or re.search(r"(?<!\\)\$[A-Za-z_]", stripped):
        return None
    try:
        value = json.loads(stripped.replace("\\$", "$"))
    except json.JSONDecodeError:
        return None
    if not isinstance(value, str):
        return None
    return value


def kotlin_char_value(expression: str) -> str | None:
    stripped = expression.strip()
    if not (stripped.startswith("'") and stripped.endswith("'")):
        return None
    content = stripped[1:-1]
    escapes = {
        "\\t": "\t",
        "\\b": "\b",
        "\\n": "\n",
        "\\r": "\r",
        "\\'": "'",
        '\\"': '"',
        "\\\\": "\\",
        "\\$": "$",
    }
    if content in escapes:
        return escapes[content]
    return content if len(content) == 1 else None


def kotlin_string_template(expression: str, parameters: dict[str, str]) -> str | None:
    stripped = expression.strip()
    if not (stripped.startswith('"') and stripped.endswith('"')):
        return None
    content = stripped[1:-1]
    parts: list[str] = []
    literal: list[str] = []
    saw_parameter = False

    def flush_literal() -> bool:
        if not literal:
            return True
        try:
            value = json.loads('"' + "".join(literal) + '"')
        except json.JSONDecodeError:
            return False
        if not isinstance(value, str):
            return False
        if value:
            parts.append(arkts_string(value))
        literal.clear()
        return True

    index = 0
    while index < len(content):
        char = content[index]
        if char == "\\":
            literal.append(char)
            index += 1
            if index < len(content):
                literal.append(content[index])
                index += 1
            continue
        if char != "$":
            literal.append(char)
            index += 1
            continue
        if index + 1 < len(content) and content[index + 1] == "{":
            closing = content.find("}", index + 2)
            if closing < 0:
                return None
            name = content[index + 2 : closing].strip()
            if IDENTIFIER_PATTERN.fullmatch(name) is None or parameters.get(name) != "string":
                return None
            if not flush_literal():
                return None
            parts.append(name)
            saw_parameter = True
            index = closing + 1
            continue
        match = re.match(r"\$([A-Za-z_][A-Za-z0-9_]*)", content[index:])
        if match is not None:
            name = match.group(1)
            if parameters.get(name) != "string":
                return None
            if not flush_literal():
                return None
            parts.append(name)
            saw_parameter = True
            index += len(match.group(0))
            continue
        literal.append(char)
        index += 1
    if not flush_literal() or not saw_parameter:
        return None
    return " + ".join(parts) if parts else None


def arkts_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def commentless_kotlin_block_body(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        stripped = stripped[1:-1]
    stripped = re.sub(r"/\*.*?\*/", "", stripped, flags=re.S)
    stripped = re.sub(r"//[^\n\r]*", "", stripped)
    return stripped.strip()


def normalize_kotlin_type(value: str) -> str:
    stripped = re.sub(r"/\*.*?\*/", "", value, flags=re.S)
    stripped = re.sub(r"//[^\n\r]*", "", stripped)
    return re.sub(r"\s+", " ", stripped.strip())


def target_parameter_type(
    kotlin_type: str,
    annotations: list[str] | None = None,
) -> str | None:
    compact = normalize_kotlin_type(kotlin_type)
    if compact in {"(() -> Unit)?", "Function0<Unit>?"}:
        return "(() => void) | null"
    if compact == "(() -> Unit)":
        return "() => void"
    if compact.rsplit(".", 1)[-1] in {"Shape?", "RoundedCornerShape?"}:
        return "number | null"
    normalized = compact
    state_inner_type = state_wrapper_inner_type(normalized)
    if state_inner_type is not None:
        return target_parameter_type(state_inner_type, annotations)
    nullable = normalized.endswith("?")
    normalized = normalized[:-1].strip() if nullable else normalized
    base_type = normalized.rsplit(".", 1)[-1]
    collection = re.fullmatch(
        r"(?:[A-Za-z_][A-Za-z0-9_]*\.)*(?:List|MutableList|ArrayList|Set|MutableSet)<\s*(.+?)\s*>",
        normalized,
        re.S,
    )
    if collection is not None:
        element_source_type = re.sub(r"\s+", " ", collection.group(1).strip())
        element_nullable = element_source_type.endswith("?")
        element_source_type = element_source_type[:-1].strip() if element_nullable else element_source_type
        element_base_type = element_source_type.rsplit(".", 1)[-1]
        if element_base_type in {"Int", "Long", "Float", "Double", "Short", "Byte"}:
            element_type = "number"
        elif element_base_type == "String":
            element_type = "string"
        elif element_base_type == "Boolean":
            element_type = "boolean"
        elif element_base_type == "BigDecimal":
            element_type = "string"
        else:
            return None
        if element_nullable:
            element_type = f"{element_type} | null"
        target_type = f"Array<{element_type}>"
        return f"{target_type} | null" if nullable else target_type
    if "DrawableRes" in (annotations or []) and normalized in {"Int", "Long"}:
        return "Resource"
    if "StringRes" in (annotations or []) and normalized in {"Int", "Long"}:
        return "ResourceStr"
    if normalized == "String":
        return "string"
    if base_type == "UiText":
        return "ResourceStr | null" if nullable else "ResourceStr"
    if base_type == "BigDecimal":
        return "string | null" if nullable else "string"
    if normalized == "Boolean":
        return "boolean | null" if nullable else "boolean"
    if normalized in {"Int", "Long", "Float", "Double", "Short", "Byte"}:
        return "number | null" if nullable else "number"
    if base_type in {"Date", "LocalDate", "LocalTime"}:
        return "Date | null" if nullable else "Date"
    if base_type == "Dp":
        return "number"
    if base_type == "TextUnit":
        return "number"
    if base_type == "FontWeight":
        return "number"
    if base_type == "Color":
        return "ResourceColor | null" if nullable else "ResourceColor"
    if base_type == "ColorFilter":
        return "boolean"
    if base_type == "PaddingValues":
        return "Padding"
    if base_type in {"KeyboardType", "KeyboardOptions"}:
        return "InputType"
    if base_type == "VisualTransformation":
        return "InputType"
    if base_type in {"Shape", "RoundedCornerShape"}:
        return "number"
    if normalized == "Alignment.Vertical":
        return "VerticalAlign"
    if normalized == "Alignment.Horizontal":
        return "HorizontalAlign"
    if base_type == "TextAlign":
        return "TextAlign"
    if normalized in {"() -> Unit", "Function0<Unit>"}:
        return "() => void"
    callback_match = re.fullmatch(r"\(\s*(.*?)\s*\)\s*->\s*Unit", normalized, re.S)
    if callback_match is not None:
        raw_parameters = callback_match.group(1).strip()
        if not raw_parameters:
            return "() => void"
        target_parameters: list[str] = []
        raw_chunks = split_arguments(raw_parameters)
        for index, chunk in enumerate(raw_chunks, start=1):
            match = re.fullmatch(
                r"(?:(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*)?(?P<type>[A-Za-z_][A-Za-z0-9_\.?]*)",
                chunk.strip(),
            )
            if match is None:
                return None
            raw_type = match.group("type")
            target_type = {
                "String": "string",
                "Boolean": "boolean",
                "Int": "number",
                "Long": "number",
                "Float": "number",
                "Double": "number",
                "Short": "number",
                "Byte": "number",
            }.get(raw_type)
            if target_type is None:
                normalized_type = target_parameter_type(raw_type)
                if normalized_type is None:
                    return None
                target_type = normalized_type
            name = match.group("name") or ("value" if len(raw_chunks) == 1 else f"value{index}")
            target_parameters.append(f"{name}: {target_type}")
        return f"({', '.join(target_parameters)}) => void"
    return None


def has_dp_unspecified_default(kotlin_type: str, default_expression: Any) -> bool:
    if not isinstance(default_expression, str):
        return False
    normalized = normalize_kotlin_type(kotlin_type).replace("?", "")
    return normalized.rsplit(".", 1)[-1] == "Dp" and default_expression.strip() == "Dp.Unspecified"


def callback_parameter_types(callback_type: str | None) -> list[str] | None:
    if callback_type == "() => void":
        return []
    if not isinstance(callback_type, str):
        return None
    match = re.fullmatch(r"\(\s*(.*?)\s*\)\s*=>\s*void", callback_type)
    if match is None:
        return None
    raw_parameters = match.group(1).strip()
    if not raw_parameters:
        return []
    result: list[str] = []
    for chunk in split_arguments(raw_parameters):
        match = re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\s*:\s*(.+)", chunk.strip(), re.S)
        if match is None:
            return None
        target_type = match.group(1).strip()
        if not target_type:
            return None
        result.append(target_type)
    return result


def callback_default_expression(callback_type: str) -> str | None:
    parameter_types = callback_parameter_types(callback_type)
    if parameter_types is None:
        return None
    if not parameter_types:
        return "() => {}"
    parameters = ", ".join(
        f"{'value' if len(parameter_types) == 1 else f'value{index}'}: {target_type}"
        for index, target_type in enumerate(parameter_types, start=1)
    )
    return f"({parameters}) => {{}}"


def primitive_default_expression(target_type: str) -> str | None:
    if target_type.endswith(" | null"):
        return "null"
    if target_type in {"string", "ResourceStr"}:
        return "''"
    if target_type == "boolean":
        return "false"
    if target_type == "number":
        return "0"
    if target_type == "Date":
        return "new Date()"
    if target_type == "number | undefined":
        return "undefined"
    if array_element_target_type(target_type) is not None:
        return "[]"
    return callback_default_expression(target_type)


def array_element_target_type(target_type: str) -> str | None:
    stripped = target_type.strip()
    match = re.fullmatch(r"Array<(.+)>", stripped, re.S)
    if match is not None:
        return match.group(1).strip()
    if stripped.endswith("[]"):
        return stripped[:-2].strip()
    return None


def callback_types_compatible(actual: str | None, expected: str | None) -> bool:
    actual_parameters = callback_parameter_types(actual)
    expected_parameters = callback_parameter_types(expected)
    return actual_parameters is not None and actual_parameters == expected_parameters


def state_wrapper_inner_type(kotlin_type: str) -> str | None:
    normalized = normalize_kotlin_type(kotlin_type)
    if normalized.endswith("?"):
        normalized = normalized[:-1].strip()
    match = re.fullmatch(r"(?:MutableState|State)<\s*(.+?)\s*>", normalized)
    return match.group(1).strip() if match is not None else None


def is_compose_modifier_type(kotlin_type: str) -> bool:
    normalized = normalize_kotlin_type(kotlin_type).replace("?", "")
    return normalized.rsplit(".", 1)[-1] == "Modifier"


def is_compose_slot_type(kotlin_type: str) -> bool:
    normalized = re.sub(r"\s+", " ", kotlin_type.strip()).replace("?", "")
    return "@Composable" in normalized and "-> Unit" in normalized


def is_navigation_controller_type(kotlin_type: str) -> bool:
    normalized = re.sub(r"\s+", " ", kotlin_type.strip()).replace("?", "")
    return normalized.rsplit(".", 1)[-1] in {"NavController", "NavHostController"}


def has_supported_material_style_default(kotlin_type: str, default_expression: Any) -> bool:
    if not isinstance(default_expression, str):
        return False
    base_type = material_style_base_type(kotlin_type)
    stripped = default_expression.strip()
    if base_type == "ButtonColors":
        return re.fullmatch(
            r"ButtonDefaults\.[A-Za-z_][A-Za-z0-9_]*Colors\s*\(.*\)",
            stripped,
            re.S,
        ) is not None
    if base_type == "TextStyle":
        return is_supported_text_style_expression(stripped)
    if base_type == "KeyboardActions":
        return stripped == "KeyboardActions.Default"
    if base_type == "MutableInteractionSource":
        return (
            stripped == "MutableInteractionSource()"
            or re.fullmatch(r"remember\s*\{\s*MutableInteractionSource\s*\(\s*\)\s*\}", stripped, re.S) is not None
        )
    if base_type == "TextFieldColors":
        return stripped.startswith("OutlinedTextFieldDefaults.colors(") or stripped.startswith("TextFieldDefaults.colors(")
    if base_type == "FocusRequester":
        return stripped == "FocusRequester()"
    return False


def material_style_base_type(kotlin_type: str) -> str:
    return re.sub(r"\s+", " ", kotlin_type.strip()).replace("?", "").rsplit(".", 1)[-1]


def is_supported_text_style_expression(expression: str) -> bool:
    stripped = expression.strip()
    conditional = kotlin_if_else_parts(stripped)
    if conditional is not None:
        return is_supported_text_style_expression(conditional[1]) and is_supported_text_style_expression(conditional[2])
    return (
        re.fullmatch(r"TextStyle\s*\(.*\)", stripped, re.S) is not None
        or re.fullmatch(
            r"MaterialTheme\.typography\.[A-Za-z_][A-Za-z0-9_]*(?:\.copy\s*\(.*\))?",
            stripped,
            re.S,
        )
        is not None
    )


class Renderer:
    def __init__(
        self,
        root: dict[str, str],
        closure: dict[str, Any],
        calls: list[dict[str, Any]],
        definitions: dict[tuple[str, str], dict[str, Any]],
        resource_names: set[str],
        string_values: dict[str, str],
        dimension_token_values: dict[str, str],
        number_token_values: dict[str, str],
        color_token_values: dict[str, str],
        data_classes: dict[str, dict[str, Any]],
        enum_classes: dict[str, set[str]],
        enum_string_properties: dict[str, dict[str, dict[str, str]]],
        route_symbols: dict[str, str],
        android_page_input: dict[str, Any] | None,
        verified_font_faces: list[dict[str, Any]],
        typography_font_roles: dict[str, dict[str, Any]],
    ) -> None:
        self.root = root
        self.closure = closure
        self.definitions = definitions
        self.resource_names = resource_names
        self.string_values = string_values
        self.dimension_token_values = dimension_token_values
        self.number_token_values = number_token_values
        self.color_token_values = color_token_values
        self.data_classes = data_classes
        self.enum_classes = enum_classes
        self.enum_string_properties = enum_string_properties
        self.route_symbols = route_symbols
        self.route_base_types = {
            symbol.split(".", 1)[0]
            for symbol in route_symbols
            if "." in symbol
        }
        self.android_page_input = android_page_input
        self.verified_font_faces = verified_font_faces
        self.typography_font_roles = typography_font_roles
        self.android_page_by_id: dict[str, dict[str, Any]] = {}
        self.android_page_by_call_id: dict[str, dict[str, Any]] = {}
        self.android_page_applied_paths: dict[str, set[str]] = defaultdict(set)
        self.android_page_reference_paths: dict[str, set[str]] = defaultdict(set)
        self.android_page_processed_call_ids: set[str] = set()
        self.data_class_properties_by_target: dict[str, list[dict[str, Any]]] = {}
        self.data_class_target_names_by_base: dict[str, str] = {}
        self.data_class_interface_properties: dict[str, list[dict[str, Any]]] = {}
        self._uses_fallback_list_item = False
        self.unresolved: list[dict[str, Any]] = []
        self._unresolved_keys: set[str] = set()
        self.state_fields: dict[tuple[str, str, str], dict[str, str]] = {}
        self._current_parameter_defaults: dict[str, str] = {}
        self._current_parameter_values: dict[str, str] = {}
        self._current_definition_key: tuple[str, str] | None = None
        self._current_enum_parameter_types: dict[str, str] = {}
        self._current_local_values: dict[str, str] = {}
        self._current_slot_contexts: dict[
            str,
            tuple[
                list[dict[str, Any]],
                dict[str | None, list[dict[str, Any]]],
                tuple[str, str],
                dict[str, str],
            ],
        ] = {}
        self._uses_resource_manager = False
        self._uses_resource_str_resolver = False
        self._uses_drawing_color_filter = False
        self._uses_greeting_helper = False
        self._uses_android_color_parser = False
        self._uses_rupee_formatter = False
        self._arkts_interface_names: dict[str, str] = {}
        self._arkts_interfaces: list[tuple[str, list[tuple[str, bool, str]]]] = []
        self._arkts_interface_name_counts: dict[str, int] = {}
        reached = closure.get("reached_definitions")
        if not isinstance(reached, list) or not reached:
            raise ArkUIPageError("selected closure has no reached definitions")
        self.reached_keys: list[tuple[str, str]] = []
        for item in reached:
            if not isinstance(item, dict) or not isinstance(item.get("source"), str) or not isinstance(item.get("composable"), str):
                raise ArkUIPageError("selected closure reached definition is invalid")
            key = (item["source"], item["composable"])
            if key not in definitions:
                raise ArkUIPageError(f"selected closure definition is missing: {key[0]}#{key[1]}")
            self.reached_keys.append(key)
        self.calls_by_definition: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        reached_set = set(self.reached_keys)
        self.selected_calls: list[dict[str, Any]] = []
        for call in calls:
            if not isinstance(call, dict):
                raise ArkUIPageError("semantic call inventory entry is invalid")
            key = (call.get("source"), call.get("composable"))
            if key not in reached_set:
                continue
            if not isinstance(call.get("call_id"), str) or not isinstance(call.get("component"), str):
                raise ArkUIPageError("semantic call inventory entry is incomplete")
            self.calls_by_definition[key].append(call)
            self.selected_calls.append(call)
        selected_calls_by_id = {call["call_id"]: call for call in self.selected_calls}
        self.incoming_project_calls: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for call in self.selected_calls:
            custom = call.get("custom_composable")
            definitions_for_call = custom.get("definitions") if isinstance(custom, dict) else None
            if not isinstance(definitions_for_call, list) or len(definitions_for_call) != 1:
                continue
            definition = definitions_for_call[0]
            if not isinstance(definition, dict):
                continue
            callee = (definition.get("source"), definition.get("composable"))
            if all(isinstance(item, str) for item in callee):
                self.incoming_project_calls[callee].append(call)
        if isinstance(android_page_input, dict):
            self.android_page_by_id = android_page_input["by_id"]
            for component in android_page_input["components"]:
                call_ids = component["call_ids"]
                call = selected_calls_by_id.get(call_ids[0]) if len(call_ids) == 1 else None
                if len(call_ids) != 1:
                    self.add_unresolved(
                        "android_page_mapping",
                        None,
                        "Android runtime component must map to exactly one source call before its visual facts can drive ArkUI",
                        page_component_id=component["id"],
                        semantic_key=component.get("semantic_key"),
                        call_ids=call_ids,
                    )
                elif call is None:
                    self.add_unresolved(
                        "android_page_mapping",
                        None,
                        "Android runtime component maps outside the selected Compose closure",
                        page_component_id=component["id"],
                        semantic_key=component.get("semantic_key"),
                        call_id=call_ids[0],
                    )
                elif component["type"] != call["component"]:
                    self.add_unresolved(
                        "android_page_mapping",
                        call,
                        "Android runtime component type does not match the selected source call",
                        page_component_id=component["id"],
                        page_component_type=component["type"],
                    )
                else:
                    self.android_page_by_call_id[call_ids[0]] = component
                for unresolved in component["unresolved"]:
                    self.add_unresolved(
                        "android_page_visual_fact",
                        call,
                        "Android page JSON retains an unresolved visual fact",
                        page_component_id=component["id"],
                        semantic_key=component.get("semantic_key"),
                        path=unresolved["path"],
                        expression=unresolved["expression"],
                        page_reason=unresolved["reason"],
                    )
        for values in self.calls_by_definition.values():
            values.sort(key=lambda item: (item.get("line", 0), item["call_id"]))
        self.cycle_edges = {
            (
                (item["caller"]["source"], item["caller"]["composable"]),
                (item["callee"]["source"], item["callee"]["composable"]),
            )
            for item in closure.get("cycle_edges", [])
            if isinstance(item, dict)
            and isinstance(item.get("caller"), dict)
            and isinstance(item.get("callee"), dict)
        }
        for caller, callee in sorted(self.cycle_edges):
            self.add_unresolved(
                "cycle",
                None,
                f"recursive project component edge {caller[0]}#{caller[1]} -> {callee[0]}#{callee[1]} is omitted",
            )

    def add_unresolved(
        self,
        kind: str,
        call: dict[str, Any] | None,
        reason: str,
        **extra: Any,
    ) -> None:
        item: dict[str, Any] = {"kind": kind, "reason": reason}
        if call is not None:
            item.update(
                {
                    "source": call["source"],
                    "composable": call["composable"],
                    "call_id": call["call_id"],
                    "component": call["component"],
                }
            )
        item.update(extra)
        key = canonical_sha256(item)
        if key not in self._unresolved_keys:
            self._unresolved_keys.add(key)
            self.unresolved.append(item)

    @staticmethod
    def page_number(value: int | float) -> str:
        return decimal_literal(Decimal(str(value)))

    @staticmethod
    def page_path_is_proven(component: dict[str, Any], path: str) -> bool:
        for record in component["provenance"]:
            if record["origin"] == "source_expression":
                continue
            for proven_path in record["paths"]:
                if path == proven_path or path.startswith(proven_path + "."):
                    return True
        return False

    @classmethod
    def page_value_is_proven(
        cls,
        component: dict[str, Any],
        path: str,
        value: Any,
    ) -> bool:
        if cls.page_path_is_proven(component, path):
            return True
        if not isinstance(value, dict):
            return False
        populated = [(name, child) for name, child in value.items() if child is not None]
        return bool(populated) and all(
            cls.page_value_is_proven(component, f"{path}.{name}", child)
            for name, child in populated
        )

    def record_android_page_path(self, call: dict[str, Any], path: str) -> None:
        self.android_page_applied_paths[call["call_id"]].add(path)

    def android_page_component(self, call: dict[str, Any]) -> dict[str, Any] | None:
        component = self.android_page_by_call_id.get(call["call_id"])
        return component if isinstance(component, dict) else None

    def android_page_content_alignment(self, call: dict[str, Any]) -> str:
        component = self.android_page_component(call)
        if component is None:
            return "Alignment.TopStart"
        parent_id = component.get("parent_id")
        parent = self.android_page_by_id.get(parent_id) if isinstance(parent_id, str) else None
        if parent is None:
            return "Alignment.TopStart"
        parent_bounds = parent["bounds_dp"]
        padding = parent["style"]["layout"]["padding_dp"]
        left_padding = padding["left"] if isinstance(padding, dict) else 0
        right_padding = padding["right"] if isinstance(padding, dict) else 0
        content_left = parent_bounds["x"] + left_padding
        content_right = parent_bounds["x"] + parent_bounds["width"] - right_padding
        child_left = component["bounds_dp"]["x"]
        child_right = child_left + component["bounds_dp"]["width"]
        left_gap = child_left - content_left
        right_gap = content_right - child_right
        tolerance = 1.0
        if abs(left_gap - right_gap) <= tolerance:
            return "Alignment.Center"
        if abs(right_gap) <= tolerance:
            return "Alignment.End"
        return "Alignment.TopStart"

    def android_page_child_alignment(
        self,
        children: list[dict[str, Any]],
    ) -> str | None:
        alignments = {
            self.android_page_content_alignment(child)
            for child in children
            if self.android_page_component(child) is not None
        }
        non_default = alignments - {"Alignment.TopStart"}
        return next(iter(non_default)) if len(non_default) == 1 else None

    def project_component_content_alignment(
        self,
        callee: tuple[str, str],
        seen: set[tuple[str, str]] | None = None,
    ) -> str | None:
        visited = set() if seen is None else set(seen)
        if callee in visited:
            return None
        visited.add(callee)
        root_calls = [
            candidate
            for candidate in self.calls_by_definition.get(callee, [])
            if candidate.get("parent_call_id") is None
        ]
        if len(root_calls) != 1:
            return None
        root_call = root_calls[0]
        if self.has_top_unbounded_wrap(root_call):
            return "Alignment.TopStart"
        component = root_call.get("component")
        if component in BUTTON_CONTAINER_COMPONENTS:
            return "Alignment.Center"
        if component == "Box":
            expression = str(
                root_call.get("semantic_arguments", {})
                .get("contentAlignment", {})
                .get("expression", "")
            ).strip()
            return {
                "Alignment.Center": "Alignment.Center",
                "Alignment.CenterStart": "Alignment.Start",
                "Alignment.CenterEnd": "Alignment.End",
                "Alignment.TopStart": "Alignment.TopStart",
                "Alignment.TopCenter": "Alignment.Top",
                "Alignment.TopEnd": "Alignment.TopEnd",
                "Alignment.BottomStart": "Alignment.BottomStart",
                "Alignment.BottomCenter": "Alignment.Bottom",
                "Alignment.BottomEnd": "Alignment.BottomEnd",
            }.get(expression, "Alignment.TopStart")
        custom = root_call.get("custom_composable")
        definitions = custom.get("definitions") if isinstance(custom, dict) else None
        if isinstance(definitions, list) and len(definitions) == 1:
            definition = definitions[0]
            if isinstance(definition, dict):
                nested = (definition.get("source"), definition.get("composable"))
                if all(isinstance(value, str) for value in nested):
                    return self.project_component_content_alignment(nested, visited)
        if component in {"Column", "Row", "BasicTextField"}:
            return "Alignment.TopStart"
        return None

    @staticmethod
    def flattened_modifier_chain(call: dict[str, Any]) -> list[dict[str, Any]]:
        chain = call.get("ordered_modifier_chain")
        if not isinstance(chain, list):
            return []
        flattened: list[dict[str, Any]] = []
        for modifier in chain:
            if not isinstance(modifier, dict):
                continue
            if modifier.get("name") == "then" and isinstance(modifier.get("arguments"), str):
                nested = modifier_chain_expression(modifier["arguments"])
                if nested:
                    flattened.extend(Renderer.flattened_modifier_chain({"ordered_modifier_chain": nested}))
                    continue
            flattened.append(modifier)
        return flattened

    @classmethod
    def has_top_unbounded_wrap(cls, call: dict[str, Any]) -> bool:
        for modifier in cls.flattened_modifier_chain(call):
            if modifier.get("name") != "wrapContentHeight" or not isinstance(modifier.get("arguments"), str):
                continue
            positional, named = named_arguments(modifier["arguments"])
            unbounded = named.get("unbounded") or (positional[0] if positional else None)
            alignment = named.get("align") or (positional[1] if len(positional) >= 2 else None)
            if str(unbounded or "false").strip() == "true" and str(alignment or "Alignment.CenterVertically").strip() == "Alignment.Top":
                return True
        return False

    @classmethod
    def has_vertical_visual_transform(cls, call: dict[str, Any]) -> bool:
        for modifier in cls.flattened_modifier_chain(call):
            name = modifier.get("name")
            arguments = modifier.get("arguments")
            if not isinstance(arguments, str):
                continue
            if name in {"rotate", "scale", "graphicsLayer"}:
                return True
            if name != "offset":
                continue
            positional, named = named_arguments(arguments)
            y_source = named.get("y") or (positional[1] if len(positional) >= 2 else None)
            if y_source is not None and dimension_value(y_source) not in {None, "0", "0.0"}:
                return True
        return False

    def static_bottom_padding(
        self,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> Decimal | None:
        total = Decimal(0)
        for modifier in self.flattened_modifier_chain(call):
            if modifier.get("name") != "padding" or not isinstance(modifier.get("arguments"), str):
                continue
            positional, named = named_arguments(modifier["arguments"])
            if len(positional) == 1 and not named:
                value = self.dimension_expression(positional[0], parameters)
            elif not positional and not (set(named) - {"all", "horizontal", "vertical", "start", "end", "top", "bottom"}):
                source = named.get("bottom") or named.get("vertical") or named.get("all")
                value = self.dimension_expression(source, parameters) if source is not None else "0"
            else:
                return None
            parsed = decimal_from_literal(value) if isinstance(value, str) else None
            if parsed is None:
                return None
            total += parsed
        return total

    def android_page_unbounded_content_height(
        self,
        call: dict[str, Any],
        children: list[dict[str, Any]],
        parameters: dict[str, str],
        definition_key: tuple[str, str] | None = None,
    ) -> Decimal | None:
        if not self.has_top_unbounded_wrap(call):
            return None
        vertical_alignment = call.get("semantic_arguments", {}).get("verticalAlignment")
        if not isinstance(vertical_alignment, dict) or vertical_alignment.get("expression", "").strip() != "Alignment.Bottom":
            return None
        owner_key = definition_key or self._current_definition_key
        if owner_key is None:
            return None
        incoming = [
            candidate
            for candidate in self.incoming_project_calls.get(owner_key, [])
            if self.android_page_component(candidate) is not None
        ]
        if len(incoming) != 1:
            return None
        wrapper_call = incoming[0]
        wrapper = self.android_page_component(wrapper_call)
        if wrapper is None:
            return None
        bottom_padding = self.static_bottom_padding(call, parameters)
        if bottom_padding is None:
            return None
        candidates: list[tuple[Decimal, dict[str, Any]]] = []
        for child in children:
            component = self.android_page_component(child)
            if component is None or self.has_vertical_visual_transform(child):
                continue
            bounds = component["bounds_dp"]
            wrapper_bounds = wrapper["bounds_dp"]
            content_height = (
                Decimal(str(bounds["y"]))
                - Decimal(str(wrapper_bounds["y"]))
                + Decimal(str(bounds["height"]))
                + bottom_padding
            )
            if content_height <= 0:
                continue
            candidates.append((content_height, child))
        if not candidates:
            return None
        values = [value for value, _child in candidates]
        if max(values) - min(values) > Decimal("1"):
            return None
        height = sum(values, Decimal(0)) / Decimal(len(values))
        self.record_android_page_path(wrapper_call, "bounds_dp.y")
        for _value, child in candidates:
            self.record_android_page_path(child, "bounds_dp.y")
            self.record_android_page_path(child, "bounds_dp.height")
        return height

    def android_page_has_proven_path(self, call: dict[str, Any], path: str) -> bool:
        component = self.android_page_component(call)
        return component is not None and self.page_path_is_proven(component, path)

    def android_page_overrides_modifier(
        self,
        call: dict[str, Any],
        name: str,
        positional: list[str],
        named: dict[str, str],
    ) -> bool:
        component = self.android_page_component(call)
        if component is None:
            return False
        preserve_image_geometry = self.uses_source_image_geometry(call)
        if name in {
            "width",
            "requiredWidth",
            "fillMaxWidth",
        }:
            return not preserve_image_geometry
        if name in {
            "height",
            "requiredHeight",
            "fillMaxHeight",
        }:
            return not preserve_image_geometry
        if name in {"size", "fillMaxSize", "matchParentSize", "weight"}:
            return not preserve_image_geometry
        if name == "padding":
            return self.android_page_has_proven_path(call, "style.layout.padding_dp")
        if name == "background":
            shape_present = "shape" in named or len(positional) >= 2
            return self.android_page_has_proven_path(
                call, "style.surface.background"
            ) and (
                not shape_present
                or self.android_page_has_proven_path(
                    call, "style.surface.corner_radius_dp"
                )
            )
        if name == "alpha":
            return self.android_page_has_proven_path(call, "style.surface.alpha")
        if name == "border":
            return self.android_page_has_proven_path(call, "style.surface.border")
        if name == "clip":
            return self.android_page_has_proven_path(
                call, "style.surface.corner_radius_dp"
            )
        if name == "offset":
            return any(
                self.android_page_has_proven_path(call, f"style.transform.{axis}")
                for axis in ("translation_x_dp", "translation_y_dp")
            )
        if name == "rotate":
            return self.android_page_has_proven_path(
                call, "style.transform.rotation_degrees"
            )
        return False

    @staticmethod
    def uses_source_image_geometry(call: dict[str, Any]) -> bool:
        if call.get("component") not in {"Image", "Icon"}:
            return False
        chain = call.get("ordered_modifier_chain")
        return isinstance(chain, list) and any(
            isinstance(item, dict)
            and item.get("name")
            in {
                "width",
                "requiredWidth",
                "height",
                "requiredHeight",
                "size",
                "requiredSize",
                "aspectRatio",
                "rotate",
            }
            for item in chain
        )

    def filter_android_page_semantic_overrides(
        self,
        call: dict[str, Any],
        lines: list[str],
    ) -> list[str]:
        prefix_paths = (
            (".fontSize(", "style.typography.font_size_sp"),
            (".fontWeight(", "style.typography.font_weight"),
            (".lineHeight(", "style.typography.line_height_sp"),
            (".letterSpacing(", "style.typography.letter_spacing_sp"),
            (".fontColor(", "style.typography.color"),
            (".fontFamily(", "style.typography.font_family"),
            (".maxLines(", "style.typography.max_lines"),
            (".textAlign(", "style.typography.text_align"),
            (".textOverflow(", "style.typography.overflow"),
        )
        return [
            line
            for line in lines
            if not any(
                line.startswith(prefix)
                and self.android_page_has_proven_path(call, path)
                for prefix, path in prefix_paths
            )
        ]

    def android_page_text_value(self, call: dict[str, Any]) -> str | None:
        component = self.android_page_by_call_id.get(call["call_id"])
        if not isinstance(component, dict):
            return None
        value = component["style"]["content"]["text"]
        path = "style.content.text"
        if not isinstance(value, str):
            return None
        if not self.page_path_is_proven(component, path):
            self.add_unresolved(
                "android_page_visual_fact",
                call,
                "Android page text is not bound to resolved provenance",
                page_component_id=component["id"],
                path=path,
            )
            return None
        return value

    def android_page_text_expression(self, call: dict[str, Any]) -> str | None:
        value = self.android_page_text_value(call)
        if value is None:
            return None
        self.record_android_page_path(call, "style.content.text")
        return arkts_string(value)

    def apply_page_driven_text_rasterization_adapter(
        self,
        call: dict[str, Any],
        lines: list[str],
    ) -> None:
        if self.android_page_input is None:
            return
        if any(line.startswith((".padding(", ".translate(")) for line in lines):
            return
        if self.has_vertical_visual_transform(call):
            return
        component = self.android_page_component(call)
        height = component["bounds_dp"]["height"] if component is not None else None
        font_size: Decimal | None = None
        for line in reversed(lines):
            match = re.fullmatch(r"\.fontSize\((-?[0-9]+(?:\.[0-9]+)?)\)", line)
            if match is not None:
                font_size = Decimal(match.group(1))
                break
        density = Decimal(str(self.android_page_input["viewport"]["density"]))
        if component is None and font_size is None:
            return
        use_small_baseline = (
            (font_size is not None and font_size <= Decimal("12"))
            or (isinstance(height, (int, float)) and height < 20)
        )
        offset = Decimal("2" if use_small_baseline else "3") / density
        offset = offset.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        lines.append(f".translate({{ y: -{decimal_literal(offset)} }})")

    def inherited_span_style_lines(
        self,
        parent_lines: list[str],
        span_lines: list[str],
    ) -> list[str]:
        inherited: list[str] = []
        for prefix in (".fontSize(", ".fontColor(", ".fontFamily("):
            if any(line.startswith(prefix) for line in span_lines):
                continue
            parent_line = next((line for line in parent_lines if line.startswith(prefix)), None)
            if parent_line is not None:
                inherited.append(parent_line)
        weight_line = next(
            (line for line in span_lines if line.startswith(".fontWeight(")),
            None,
        )
        family_index = next(
            (index for index, line in enumerate(inherited) if line.startswith(".fontFamily(")),
            None,
        )
        if weight_line is not None and family_index is not None:
            weight_match = re.fullmatch(r"\.fontWeight\(([0-9]+)\)", weight_line)
            alias_match = re.fullmatch(r"\.fontFamily\('([^']+)'\)", inherited[family_index])
            if weight_match is not None and alias_match is not None:
                face = next(
                    (
                        item
                        for item in self.verified_font_faces
                        if item["alias"] == alias_match.group(1)
                    ),
                    None,
                )
                if face is not None and face["match_names"]:
                    weighted_alias = self.verified_font_alias(
                        sorted(face["match_names"])[0],
                        int(weight_match.group(1)),
                    )
                    if weighted_alias is not None:
                        inherited[family_index] = f".fontFamily({arkts_string(weighted_alias)})"
        return inherited + span_lines

    def verified_font_alias(self, family: str, weight: int | float | None) -> str | None:
        requested = normalized_font_name(family)
        candidates = [
            face
            for face in self.verified_font_faces
            if requested in face["match_names"]
        ]
        if not candidates:
            return None
        requested_weight = int(weight) if isinstance(weight, (int, float)) else 400
        selected = min(
            candidates,
            key=lambda face: (abs(face["weight"] - requested_weight), face["weight"]),
        )
        return selected["alias"]

    @staticmethod
    def resolved_font_weight(expression: str | None) -> int | None:
        if not isinstance(expression, str):
            return None
        match = re.fullmatch(r"FontWeight\.([A-Za-z_][A-Za-z0-9_]*)", expression.strip())
        if match is not None:
            return FONT_WEIGHT_VALUES.get(match.group(1))
        numeric = decimal_from_literal(expression.strip())
        return int(numeric) if numeric is not None else None

    def data_class_page_text_expression(
        self,
        target_type: str,
        value: str,
    ) -> str | None:
        properties = self.data_class_properties_by_target.get(target_type)
        if not properties or sum(
            property_item["name"] == "value"
            and property_item["type"] in {"string", "ResourceStr"}
            for property_item in properties
        ) != 1:
            return None
        fields: list[str] = []
        for property_item in properties:
            if property_item["name"] == "value":
                fields.append(f"value: {arkts_string(value)}")
                continue
            if property_item.get("optional"):
                continue
            property_type = property_item["type"]
            if property_type in {"string", "ResourceStr"}:
                rendered = "''"
            elif property_type == "number":
                rendered = "0"
            elif property_type == "boolean":
                rendered = "false"
            elif array_element_target_type(property_type) is not None:
                rendered = "[]"
            elif property_type in self.data_class_properties_by_target:
                rendered = self.data_class_default_value_expression(property_type)
                if rendered is None:
                    return None
            else:
                return None
            fields.append(f"{property_item['name']}: {rendered}")
        return "{ " + ", ".join(fields) + " }"

    @classmethod
    def page_edge_value(cls, value: dict[str, Any]) -> str:
        rendered = {name: cls.page_number(value[name]) for name in ("left", "right", "top", "bottom")}
        if len(set(rendered.values())) == 1:
            return rendered["left"]
        return "{ " + ", ".join(f"{name}: {rendered[name]}" for name in ("left", "right", "top", "bottom")) + " }"

    def android_page_visual_lines(
        self,
        call: dict[str, Any],
        component_kind: str,
    ) -> list[str]:
        component = self.android_page_by_call_id.get(call["call_id"])
        if not isinstance(component, dict):
            return []
        self.android_page_processed_call_ids.add(call["call_id"])
        lines: list[str] = []
        semantic_key = component.get("semantic_key")
        if isinstance(semantic_key, str):
            lines.append(f".id({arkts_string(semantic_key)})")

        def apply(path: str, value: Any, line: str) -> None:
            if value is None:
                return
            if not self.page_value_is_proven(component, path, value):
                self.add_unresolved(
                    "android_page_visual_fact",
                    call,
                    "Android page visual value is not bound to resolved provenance",
                    page_component_id=component["id"],
                    path=path,
                )
                return
            lines.append(line)
            self.record_android_page_path(call, path)

        bounds = component["bounds_dp"]
        if not self.uses_source_image_geometry(call):
            lines.append(f".width({self.page_number(bounds['width'])})")
            self.record_android_page_path(call, "bounds_dp.width")
            lines.append(f".height({self.page_number(bounds['height'])})")
            self.record_android_page_path(call, "bounds_dp.height")
        else:
            chain = call.get("ordered_modifier_chain", [])
            modifier_names = {
                item.get("name")
                for item in chain
                if isinstance(item, dict)
            }
            layout = component["style"]["layout"]
            if layout.get("width_dp") is not None and modifier_names & {
                "width", "requiredWidth", "size", "requiredSize"
            }:
                self.record_android_page_path(call, "style.layout.width_dp")
            if layout.get("height_dp") is not None and modifier_names & {
                "height", "requiredHeight", "size", "requiredSize"
            }:
                self.record_android_page_path(call, "style.layout.height_dp")
        self.android_page_reference_paths[call["call_id"]].update(
            {"bounds_dp.x", "bounds_dp.y", "bounds_dp.width", "bounds_dp.height"}
        )

        style = component["style"]
        layout = style["layout"]
        padding = layout["padding_dp"]
        if padding is not None:
            emitted_padding = padding
            if (
                component_kind in {"Text", "BasicText", "ClickableText"}
                and padding["top"] >= 1
            ):
                emitted_padding = {
                    **padding,
                    "top": padding["top"] - 1,
                    "bottom": padding["bottom"] + 1,
                }
            apply(
                "style.layout.padding_dp",
                padding,
                f".padding({self.page_edge_value(emitted_padding)})",
            )
        margin = layout["margin_dp"]
        if margin is not None:
            apply("style.layout.margin_dp", margin, f".margin({self.page_edge_value(margin)})")

        surface = style["surface"]
        background = surface["background"]
        if isinstance(background, dict) and background.get("type") == "solid" and background.get("color"):
            apply(
                "style.surface.background",
                background,
                f".backgroundColor({arkts_string(background['color'])})",
            )
        radius = surface["corner_radius_dp"]
        if isinstance(radius, dict):
            rendered_radius = {name: self.page_number(radius[name]) for name in radius}
            if len(set(rendered_radius.values())) == 1:
                radius_value = rendered_radius["top_left"]
            else:
                radius_value = (
                    "{ topLeft: " + rendered_radius["top_left"]
                    + ", topRight: " + rendered_radius["top_right"]
                    + ", bottomRight: " + rendered_radius["bottom_right"]
                    + ", bottomLeft: " + rendered_radius["bottom_left"] + " }"
                )
            apply("style.surface.corner_radius_dp", radius, f".borderRadius({radius_value})")
        apply(
            "style.surface.alpha",
            surface["alpha"],
            f".opacity({self.page_number(surface['alpha'])})" if surface["alpha"] is not None else "",
        )

        typography = style["typography"]
        if component_kind in {"Text", "BasicText", "ClickableText", "BasicTextField", "TextField", "OutlinedTextField"}:
            apply(
                "style.typography.font_size_sp",
                typography["font_size_sp"],
                f".fontSize({self.page_number(typography['font_size_sp'])})" if typography["font_size_sp"] is not None else "",
            )
            apply(
                "style.typography.font_weight",
                typography["font_weight"],
                f".fontWeight({typography['font_weight']})" if typography["font_weight"] is not None else "",
            )
            apply(
                "style.typography.line_height_sp",
                typography["line_height_sp"],
                f".lineHeight({self.page_number(typography['line_height_sp'])})" if typography["line_height_sp"] is not None else "",
            )
            apply(
                "style.typography.letter_spacing_sp",
                typography["letter_spacing_sp"],
                f".letterSpacing({self.page_number(typography['letter_spacing_sp'])})" if typography["letter_spacing_sp"] is not None else "",
            )
            apply(
                "style.typography.color",
                typography["color"],
                f".fontColor({arkts_string(typography['color'])})" if typography["color"] is not None else "",
            )
            apply(
                "style.typography.font_family",
                typography["font_family"],
                (
                    f".fontFamily({arkts_string(self.verified_font_alias(typography['font_family'], typography['font_weight']) or typography['font_family'])})"
                    if typography["font_family"] is not None
                    else ""
                ),
            )
            apply(
                "style.typography.max_lines",
                typography["max_lines"],
                f".maxLines({typography['max_lines']})" if typography["max_lines"] is not None else "",
            )
            text_align = {
                "start": "TextAlign.Start",
                "center": "TextAlign.Center",
                "end": "TextAlign.End",
                "justify": "TextAlign.Justify",
            }.get(typography["text_align"])
            if text_align is not None:
                apply("style.typography.text_align", typography["text_align"], f".textAlign({text_align})")
            overflow = {
                "clip": "TextOverflow.Clip",
                "ellipsis": "TextOverflow.Ellipsis",
            }.get(typography["overflow"])
            if overflow is not None:
                apply(
                    "style.typography.overflow",
                    typography["overflow"],
                    f".textOverflow({{ overflow: {overflow} }})",
                )

        transform = style["transform"]
        translation_x = transform["translation_x_dp"]
        translation_y = transform["translation_y_dp"]
        if translation_x is not None or translation_y is not None:
            translation_values = {
                "translation_x_dp": translation_x,
                "translation_y_dp": translation_y,
            }
            if self.page_value_is_proven(
                component,
                "style.transform",
                translation_values,
            ):
                x = self.page_number(translation_x or 0)
                y = self.page_number(translation_y or 0)
                lines.append(f".translate({{ x: {x}, y: {y} }})")
                for axis in ("translation_x_dp", "translation_y_dp"):
                    if transform[axis] is not None:
                        self.record_android_page_path(call, f"style.transform.{axis}")
            else:
                for axis, value in translation_values.items():
                    if value is not None and not self.page_path_is_proven(
                        component, f"style.transform.{axis}"
                    ):
                        self.add_unresolved(
                            "android_page_visual_fact",
                            call,
                            "Android page visual value is not bound to resolved provenance",
                            page_component_id=component["id"],
                            path=f"style.transform.{axis}",
                        )
        scale_x = transform["scale_x"]
        scale_y = transform["scale_y"]
        if scale_x is not None or scale_y is not None:
            scale_values = {"scale_x": scale_x, "scale_y": scale_y}
            if self.page_value_is_proven(component, "style.transform", scale_values):
                x = self.page_number(scale_x if scale_x is not None else 1)
                y = self.page_number(scale_y if scale_y is not None else 1)
                lines.append(f".scale({{ x: {x}, y: {y} }})")
                for axis in ("scale_x", "scale_y"):
                    if transform[axis] is not None:
                        self.record_android_page_path(call, f"style.transform.{axis}")
            else:
                for axis, value in scale_values.items():
                    if value is not None and not self.page_path_is_proven(
                        component, f"style.transform.{axis}"
                    ):
                        self.add_unresolved(
                            "android_page_visual_fact",
                            call,
                            "Android page visual value is not bound to resolved provenance",
                            page_component_id=component["id"],
                            path=f"style.transform.{axis}",
                        )
        rotation = transform["rotation_degrees"]
        if rotation is not None:
            apply(
                "style.transform.rotation_degrees",
                rotation,
                f".rotate({{ angle: {self.page_number(rotation)} }})",
            )

        applied = self.android_page_applied_paths[call["call_id"]]
        for section_name, section in style.items():
            for field_name, value in section.items():
                path = f"style.{section_name}.{field_name}"
                if value is None or path in applied or path == "style.content.text":
                    continue
                if not self.page_value_is_proven(component, path, value):
                    continue
                self.add_unresolved(
                    "android_page_visual_fact",
                    call,
                    "proven Android page visual fact has no safe ArkUI emitter",
                    page_component_id=component["id"],
                    path=path,
                )
        return lines

    def image_tint_lines(self, color: str, prefer_template: bool = False) -> list[str]:
        literal = re.fullmatch(r"'#([0-9A-Fa-f]{8})'", color)
        if literal is not None and not prefer_template:
            self._uses_drawing_color_filter = True
            return [
                ".colorFilter(drawing.ColorFilter.createBlendModeColorFilter("
                f"0x{literal.group(1).upper()}, drawing.BlendMode.SRC_IN))"
            ]
        return [
            ".renderMode(ImageRenderMode.Template)",
            f".fillColor({color})",
        ]

    def fallback_collection_target_type(self, kotlin_type: str) -> str | None:
        compact = normalize_kotlin_type(kotlin_type)
        nullable = compact.endswith("?")
        normalized = compact[:-1].strip() if nullable else compact
        match = re.fullmatch(
            r"(?:[A-Za-z_][A-Za-z0-9_]*\.)*(?:List|MutableList|ArrayList|Set|MutableSet)<\s*(.+?)\s*>",
            normalized,
            re.S,
        )
        if match is None:
            return None
        element_source_type = normalize_kotlin_type(match.group(1).strip())
        if (
            self.data_class_target_type(element_source_type) is not None
            or target_parameter_type(f"List<{element_source_type}>") is not None
        ):
            return None
        self._uses_fallback_list_item = True
        target_type = f"Array<{FALLBACK_LIST_ITEM_TYPE}>"
        return f"{target_type} | null" if nullable else target_type

    def target_type_for_kotlin_type(
        self,
        kotlin_type: str,
        annotations: list[str] | None = None,
        unresolved_context: dict[str, Any] | None = None,
    ) -> str | None:
        target_type = (
            self.enum_target_type(kotlin_type)
            or self.callback_target_type(kotlin_type)
            or self.data_class_array_target_type(kotlin_type)
            or target_parameter_type(kotlin_type, annotations)
            or self.data_class_target_type(kotlin_type)
        )
        if target_type is not None:
            return target_type
        fallback_type = self.fallback_collection_target_type(kotlin_type)
        if fallback_type is None:
            return None
        context = dict(unresolved_context or {})
        self.add_unresolved(
            "collection_element_type",
            None,
            "collection element type is not safely translated; emitted a named opaque fallback item type",
            kotlin_type=kotlin_type,
            fallback_type=fallback_type,
            **context,
        )
        return fallback_type

    def definition_parameters(self, key: tuple[str, str]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for source_index, parameter in enumerate(self.definitions[key]["parameters"]):
            if not isinstance(parameter, dict) or not isinstance(parameter.get("name"), str) or not isinstance(parameter.get("type"), str):
                raise ArkUIPageError(f"invalid parameters for {key[0]}#{key[1]}")
            if is_compose_modifier_type(parameter["type"]) or is_compose_slot_type(parameter["type"]):
                continue
            annotations = parameter.get("annotations")
            enum_type = self.enum_base_type(parameter["type"])
            target_type = self.target_type_for_kotlin_type(
                parameter["type"],
                annotations if isinstance(annotations, list) else None,
                {
                    "source": key[0],
                    "composable": key[1],
                    "parameter": parameter["name"],
                },
            )
            if has_dp_unspecified_default(parameter["type"], parameter.get("default")):
                target_type = "number | undefined"
            if target_type is None:
                if is_navigation_controller_type(parameter["type"]):
                    continue
                if has_supported_material_style_default(parameter["type"], parameter.get("default")):
                    continue
                self.add_unresolved(
                    "parameter_type",
                    None,
                    f"unsupported Kotlin parameter type in {key[0]}#{key[1]}",
                    parameter=parameter["name"],
                    kotlin_type=parameter["type"],
                )
                continue
            item: dict[str, Any] = {
                "name": parameter["name"],
                "type": target_type,
                "source_index": source_index,
            }
            source_base_type = re.sub(r"\s+", " ", parameter["type"].strip()).removesuffix("?").strip().rsplit(".", 1)[-1]
            if source_base_type == "ColorFilter":
                item["source_base_type"] = source_base_type
            if enum_type is not None:
                item["enum_type"] = enum_type
            if isinstance(parameter.get("default"), str):
                item["default"] = parameter["default"]
                default_expression = parameter["default"].strip()
                if target_type.endswith(" | null") and default_expression == "null":
                    item["default_ts"] = "null"
                if source_base_type == "ColorFilter" and re.fullmatch(r"ColorFilter\.tint\s*\(.+\)", default_expression, re.S):
                    item["default_ts"] = "true"
            if target_type == "number | undefined":
                item["default_ts"] = "undefined"
            result.append(item)
        return result

    def root_public_parameters(self, key: tuple[str, str]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for source_index, parameter in enumerate(self.definitions[key]["parameters"]):
            if not isinstance(parameter, dict) or not isinstance(parameter.get("name"), str) or not isinstance(parameter.get("type"), str):
                raise ArkUIPageError(f"invalid parameters for {key[0]}#{key[1]}")
            if is_compose_modifier_type(parameter["type"]) or is_compose_slot_type(parameter["type"]):
                continue
            annotations = parameter.get("annotations")
            enum_type = self.enum_base_type(parameter["type"])
            target_type = self.target_type_for_kotlin_type(
                parameter["type"],
                annotations if isinstance(annotations, list) else None,
                {
                    "source": key[0],
                    "composable": key[1],
                    "parameter": parameter["name"],
                    "root_parameter": True,
                },
            )
            if has_dp_unspecified_default(parameter["type"], parameter.get("default")):
                target_type = "number | undefined"
            default_expression = primitive_default_expression(target_type) if target_type is not None else None
            source_base_type = re.sub(r"\s+", " ", parameter["type"].strip()).removesuffix("?").strip().rsplit(".", 1)[-1]
            route_like_data_class = source_base_type in self.route_base_types or source_base_type.endswith("Route")
            if (
                default_expression is None
                and target_type in self.data_class_properties_by_target
                and route_like_data_class
            ):
                default_expression = self.data_class_default_value_expression(target_type)
                if default_expression is not None:
                    self.add_unresolved(
                        "root_parameter",
                        None,
                        f"route-like data class root parameter is previewable only; real navigation argument wiring requires explicit ArkUI route integration in {key[0]}#{key[1]}",
                        parameter=parameter["name"],
                        kotlin_type=parameter["type"],
                    )
            if target_type is None or default_expression is None:
                self.add_unresolved(
                    "root_parameter",
                    None,
                    f"root runtime dependency requires explicit ArkUI state/controller wiring in {key[0]}#{key[1]}",
                    parameter=parameter["name"],
                    kotlin_type=parameter["type"],
                )
                continue
            item: dict[str, Any] = {
                "name": parameter["name"],
                "public_name": ROOT_PUBLIC_PARAMETER_ALIASES.get(parameter["name"], parameter["name"]),
                "type": target_type,
                "source_index": source_index,
                "default_ts": default_expression,
            }
            if enum_type is not None:
                item["enum_type"] = enum_type
            result.append(item)
        return result

    def data_class_array_target_type(self, kotlin_type: str, seen: set[str] | None = None) -> str | None:
        compact = normalize_kotlin_type(kotlin_type)
        nullable = compact.endswith("?")
        normalized = compact[:-1].strip() if nullable else compact
        match = re.fullmatch(
            r"(?:[A-Za-z_][A-Za-z0-9_]*\.)*(?:List|MutableList|ArrayList|Set|MutableSet)<\s*(.+?)\s*>",
            normalized,
            re.S,
        )
        if match is None:
            return None
        element_type = self.data_class_target_type(match.group(1).strip(), seen)
        if element_type is None:
            return None
        target_type = f"Array<{element_type}>"
        return f"{target_type} | null" if nullable else target_type

    def skippable_material_style_parameters(self, key: tuple[str, str]) -> dict[str, str]:
        return {
            parameter["name"]: parameter["type"]
            for parameter in self.definitions[key]["parameters"]
            if isinstance(parameter, dict)
            and isinstance(parameter.get("name"), str)
            and isinstance(parameter.get("type"), str)
            and has_supported_material_style_default(parameter["type"], parameter.get("default"))
        }

    def enum_base_type(self, kotlin_type: str) -> str | None:
        compact = normalize_kotlin_type(kotlin_type)
        normalized = compact[:-1].strip() if compact.endswith("?") else compact
        base_type = normalized.rsplit(".", 1)[-1]
        return base_type if base_type in self.enum_classes else None

    def enum_target_type(self, kotlin_type: str) -> str | None:
        base_type = self.enum_base_type(kotlin_type)
        if base_type is None:
            return None
        return "string | null" if kotlin_type.strip().endswith("?") else "string"

    def collection_element_type_for_expression(
        self,
        expression: str,
        parameters: dict[str, str],
    ) -> str | None:
        stripped = expression.strip()
        parameter_type = parameters.get(stripped)
        if isinstance(parameter_type, str):
            element_type = array_element_target_type(parameter_type)
            if element_type is not None:
                return element_type
        local_expression = self.local_value_expression(stripped, parameters)
        if local_expression is not None:
            return self.collection_element_type_for_expression(local_expression, parameters)
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+", stripped) is None:
            return None
        parts = stripped.split(".")
        current_type = parameters.get(parts[0])
        if current_type is None:
            return None
        for part in parts[1:]:
            properties = self.data_class_properties_by_target.get(current_type or "")
            if properties is None:
                return None
            match = next((item for item in properties if item["name"] == part), None)
            if match is None:
                return None
            current_type = match["type"]
        return array_element_target_type(current_type) if isinstance(current_type, str) else None

    def collection_first_value_expression(
        self,
        expression: str,
        target_type: str,
        parameters: dict[str, str],
    ) -> str | None:
        match = re.fullmatch(r"(.+?)\.(first|firstOrNull)\s*\(\s*\)", expression.strip(), re.S)
        if match is None:
            return None
        collection_expression = self.value_expression(match.group(1).strip(), "unknown[]", parameters)
        element_type = self.collection_element_type_for_expression(match.group(1).strip(), parameters)
        if collection_expression is None or element_type is None:
            return None
        nullable_target = target_type == f"{element_type} | null"
        if target_type != element_type and not nullable_target:
            return None
        if nullable_target:
            return f"({collection_expression}.length > 0 ? {collection_expression}[0] : null)"
        default_value = (
            self.data_class_default_value_expression(element_type)
            if element_type in self.data_class_properties_by_target
            else primitive_default_expression(element_type)
        )
        if default_value is None:
            return None
        return f"({collection_expression}[0] ?? {default_value})"

    def collection_first_property_expression(
        self,
        expression: str,
        property_name: str,
        target_type: str,
        parameters: dict[str, str],
    ) -> str | None:
        match = re.fullmatch(r"(.+?)\.(first|firstOrNull)\s*\(\s*\)", expression.strip(), re.S)
        if match is None:
            return None
        collection_expression = self.value_expression(match.group(1).strip(), "unknown[]", parameters)
        element_type = self.collection_element_type_for_expression(match.group(1).strip(), parameters)
        if collection_expression is None or element_type is None:
            return None
        properties = self.data_class_properties_by_target.get(element_type)
        if properties is None:
            return None
        property_item = next((item for item in properties if item["name"] == property_name), None)
        if property_item is None or not (
            property_item["type"] == target_type
            or (target_type == "ResourceStr" and property_item["type"] == "string")
        ):
            return None
        default_value = (
            self.data_class_default_value_expression(target_type)
            if target_type in self.data_class_properties_by_target
            else primitive_default_expression(target_type)
        )
        if default_value is None:
            return None
        return f"({collection_expression}[0]?.{property_name} ?? {default_value})"

    def enum_entry_string_expression(self, expression: str) -> str | None:
        match = re.fullmatch(
            r"(?:[A-Za-z_][A-Za-z0-9_]*\.)*([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)",
            expression.strip(),
        )
        if match is None:
            return None
        enum_name = match.group(1)
        entry_name = match.group(2)
        if entry_name not in self.enum_classes.get(enum_name, set()):
            return None
        return arkts_string(entry_name)

    def enum_string_property_expression(
        self,
        expression: str,
        parameters: dict[str, str],
    ) -> str | None:
        property_path = re.fullmatch(
            r"(.+\.[A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)",
            expression.strip(),
            re.S,
        )
        if property_path is not None:
            resolved = self.enum_data_class_property_path_expression(property_path.group(1).strip(), parameters)
            if resolved is not None:
                subject_expression, enum_type = resolved
                return self.render_enum_string_property_expression(
                    subject_expression,
                    enum_type,
                    property_path.group(2),
                )
        match = re.fullmatch(
            r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)",
            expression.strip(),
        )
        if match is None:
            return None
        owner = match.group(1)
        if parameters.get(owner) != "string":
            return None
        enum_type = self._current_enum_parameter_types.get(owner)
        if enum_type is None:
            return None
        return self.render_enum_string_property_expression(owner, enum_type, match.group(2))

    def render_enum_string_property_expression(
        self,
        subject_expression: str,
        enum_type: str,
        property_name: str,
    ) -> str | None:
        mapping = self.enum_string_properties.get(enum_type, {}).get(property_name)
        if not mapping:
            return None
        inline_value = self._current_parameter_values.get(subject_expression)
        if isinstance(inline_value, str):
            literal = re.fullmatch(r"'((?:\\.|[^'\\])*)'", inline_value)
            if literal is not None:
                entry = literal.group(1).replace("\\'", "'").replace("\\\\", "\\")
                value = mapping.get(entry)
                if value is not None:
                    return arkts_string(value)
        enum_values = self.enum_classes.get(enum_type, set())
        entries = [(entry, value) for entry, value in mapping.items() if entry in enum_values]
        if not entries or {entry for entry, _value in entries} != enum_values:
            return None
        result = arkts_string(entries[-1][1])
        for entry, value in reversed(entries[:-1]):
            result = f"{subject_expression} === {arkts_string(entry)} ? {arkts_string(value)} : {result}"
        return f"({result})"

    def enum_data_class_property_path_expression(
        self,
        expression: str,
        parameters: dict[str, str],
    ) -> tuple[str, str] | None:
        stripped = expression.strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+", stripped) is None:
            return None
        pieces = stripped.split(".")
        current_type = parameters.get(pieces[0])
        if current_type is None:
            return None
        rendered = pieces[0]
        enum_type: str | None = None
        for property_name in pieces[1:]:
            properties = self.data_class_properties_by_target.get(current_type or "")
            match = next((item for item in properties if item["name"] == property_name), None)
            if match is None:
                return None
            rendered += f".{property_name}"
            current_type = match["type"]
            enum_type = match.get("enum_type") if isinstance(match.get("enum_type"), str) else None
        if enum_type is None:
            return None
        return rendered, enum_type

    def callback_target_type(self, kotlin_type: str) -> str | None:
        normalized = normalize_kotlin_type(kotlin_type)
        callback_match = re.fullmatch(r"\(\s*(.*?)\s*\)\s*->\s*Unit", normalized, re.S)
        if callback_match is None:
            return None
        raw_parameters = callback_match.group(1).strip()
        if not raw_parameters:
            return "() => void"
        target_parameters: list[str] = []
        raw_chunks = split_arguments(raw_parameters)
        for index, chunk in enumerate(raw_chunks, start=1):
            match = re.fullmatch(
                r"(?:(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*)?(?P<type>.+)",
                chunk.strip(),
                re.S,
            )
            if match is None:
                return None
            source_type = match.group("type").strip()
            target_type = (
                self.enum_target_type(source_type)
                or self.data_class_array_target_type(source_type)
                or target_parameter_type(source_type)
                or self.data_class_target_type(source_type)
            )
            if target_type is None and source_type.rsplit(".", 1)[-1] in self.route_base_types:
                target_type = "string"
            if target_type is None:
                return None
            name = match.group("name") or ("value" if len(raw_chunks) == 1 else f"value{index}")
            target_parameters.append(f"{name}: {target_type}")
        return f"({', '.join(target_parameters)}) => void"

    def route_string_expression(self, expression: str) -> str | None:
        stripped = expression.strip()
        route = self.route_symbols.get(stripped)
        if route is None and not stripped.endswith(".route"):
            route = self.route_symbols.get(f"{stripped}.route")
        if route is None:
            return None
        return arkts_string(route)

    def data_class_target_type(self, kotlin_type: str, seen: set[str] | None = None) -> str | None:
        compact = normalize_kotlin_type(kotlin_type)
        nullable = compact.endswith("?")
        normalized = compact[:-1] if nullable else compact
        inner_state_type = state_wrapper_inner_type(normalized)
        if inner_state_type is not None:
            return self.data_class_target_type(inner_state_type, seen)
        base_type = normalized.rsplit(".", 1)[-1]
        known_target_type = self.data_class_target_names_by_base.get(base_type)
        if known_target_type is not None:
            if nullable:
                nullable_target_type = f"{known_target_type} | null"
                properties = self.data_class_properties_by_target.get(known_target_type)
                if properties is not None:
                    self.data_class_properties_by_target[nullable_target_type] = properties
                return nullable_target_type
            return known_target_type
        seen = set(seen or set())
        if base_type in seen:
            return None
        data_class = self.data_classes.get(base_type)
        if not isinstance(data_class, dict):
            return None
        seen.add(base_type)
        properties = data_class.get("properties")
        if not isinstance(properties, list) or not properties:
            return None
        target_properties: list[dict[str, Any]] = []
        for property_item in properties:
            if not isinstance(property_item, dict) or not isinstance(property_item.get("name"), str) or not isinstance(property_item.get("type"), str):
                return None
            annotations = property_item.get("annotations")
            enum_type = self.enum_base_type(property_item["type"])
            property_type = self.enum_target_type(property_item["type"]) or self.data_class_array_target_type(
                property_item["type"],
                seen,
            ) or target_parameter_type(
                property_item["type"],
                annotations if isinstance(annotations, list) else None,
            ) or self.data_class_target_type(
                property_item["type"],
                seen,
            )
            if property_type is None:
                property_type = self.fallback_collection_target_type(property_item["type"])
                if property_type is not None:
                    self.add_unresolved(
                        "collection_element_type",
                        None,
                        "data class collection element type is not safely translated; emitted a named opaque fallback item type",
                        data_class=base_type,
                        property=property_item["name"],
                        kotlin_type=property_item["type"],
                        fallback_type=property_type,
                    )
            optional = "?" in property_item["type"] or property_item.get("default") == "null"
            if optional and isinstance(property_type, str) and property_type.endswith(" | null"):
                property_type = property_type[: -len(" | null")]
            if property_type is None:
                continue
            target_property = {
                "name": property_item["name"],
                "type": property_type,
                "optional": optional,
                "default": property_item.get("default"),
            }
            if enum_type is not None:
                target_property["enum_type"] = enum_type
            target_properties.append(target_property)
        if not target_properties:
            return None
        target_type = data_class_interface_name(base_type)
        self.data_class_target_names_by_base[base_type] = target_type
        self.data_class_interface_properties[target_type] = target_properties
        self.data_class_properties_by_target[target_type] = target_properties
        if nullable:
            nullable_target_type = f"{target_type} | null"
            self.data_class_properties_by_target[nullable_target_type] = target_properties
            return nullable_target_type
        return target_type

    def static_color_expression(self, expression: str) -> str | None:
        stripped = expression.strip()
        literals = {
            "Color.Transparent": "'#00000000'",
            "Color.Black": "'#FF000000'",
            "Color.White": "'#FFFFFFFF'",
            "Color.Red": "'#FFF44336'",
            "Color.Gray": "'#FF9E9E9E'",
            "Color.LightGray": "'#FFD3D3D3'",
        }
        if stripped in literals:
            return literals[stripped]
        literal = re.fullmatch(r"Color\s*\(\s*0x([0-9A-Fa-f]{8})\s*\)", stripped)
        if literal is not None:
            return f"'#{literal.group(1).upper()}'"
        return None

    def static_color_argb_hex(self, expression: str) -> str | None:
        stripped = expression.strip()
        if stripped in self.color_token_values:
            return self.color_token_values[stripped]
        literal = self.static_color_expression(stripped)
        if literal is None:
            return None
        return literal.strip("'")

    def static_color_copy_alpha_expression(self, expression: str) -> str | None:
        copied = re.fullmatch(r"(.+?)\.copy\s*\((.*)\)\s*", expression.strip(), re.S)
        if copied is None:
            return None
        positional, named = named_arguments(copied.group(2))
        if positional or set(named) != {"alpha"}:
            return None
        base = self.static_color_argb_hex(copied.group(1).strip())
        if base is None or re.fullmatch(r"#[0-9A-Fa-f]{8}", base) is None:
            return None
        alpha = decimal_from_literal(number_value(named["alpha"]) or "")
        if alpha is None or alpha < 0 or alpha > 1:
            return None
        alpha_byte = int((alpha * Decimal(255)).to_integral_value(rounding=ROUND_HALF_UP))
        return f"'#{alpha_byte:02X}{base[3:].upper()}'"

    def color_copy_alpha_expression(
        self,
        expression: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> str | None:
        literal = self.static_color_copy_alpha_expression(expression)
        if literal is not None:
            return literal
        copied = re.fullmatch(r"(.+?)\.copy\s*\((.*)\)\s*", expression.strip(), re.S)
        if copied is None:
            return None
        positional, named = named_arguments(copied.group(2))
        if positional or set(named) != {"alpha"}:
            return None
        base = self.static_color_argb_hex(copied.group(1).strip())
        if base is None or re.fullmatch(r"#[0-9A-Fa-f]{8}", base) is None:
            return None
        conditional = kotlin_if_else_parts(named["alpha"])
        if conditional is None:
            return None
        condition, true_branch, false_branch = conditional
        condition_expression = self.value_expression(condition, "boolean", parameters)
        true_alpha = decimal_from_literal(number_value(true_branch) or "")
        false_alpha = decimal_from_literal(number_value(false_branch) or "")
        if (
            condition_expression is None
            or true_alpha is None
            or false_alpha is None
            or true_alpha < 0
            or true_alpha > 1
            or false_alpha < 0
            or false_alpha > 1
        ):
            return None
        true_byte = int((true_alpha * Decimal(255)).to_integral_value(rounding=ROUND_HALF_UP))
        false_byte = int((false_alpha * Decimal(255)).to_integral_value(rounding=ROUND_HALF_UP))
        return f"({condition_expression} ? '#{true_byte:02X}{base[3:].upper()}' : '#{false_byte:02X}{base[3:].upper()}')"

    def nullable_string_expression(
        self,
        expression: str,
        parameters: dict[str, str],
    ) -> str | None:
        return (
            self.value_expression(expression, "string | null", parameters)
            or self.nullable_data_class_property_path_expression(expression, "string", parameters)
            or self.data_class_property_path_expression(expression, "string", parameters)
        )

    def android_get_color_expression(
        self,
        expression: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> str | None:
        copied = re.fullmatch(r"(.+?)\.copy\s*\((.*)\)\s*", expression.strip(), re.S)
        if copied is not None:
            positional, named = named_arguments(copied.group(2))
            alpha_source = named.get("alpha") or (positional[0] if len(positional) == 1 else None)
            alpha = decimal_from_literal(number_value(alpha_source or "") or "")
            if alpha is None or alpha < 0 or alpha > 1:
                return None
            base = self.android_get_color_expression(copied.group(1).strip(), call, parameters)
            if base is None:
                return None
            self._uses_android_color_parser = True
            return f"this.withAlpha({base}, {decimal_literal(alpha)})"
        match = re.fullmatch(r"getColor\s*\((.*)\)\s*", expression.strip(), re.S)
        if match is None:
            return None
        positional, named = named_arguments(match.group(1))
        if set(named) - {"colorCode", "defaultColor"}:
            return None
        color_source = named.get("colorCode") or (positional[0] if positional else None)
        if color_source is None:
            return None
        color_value = self.nullable_string_expression(color_source, parameters)
        if color_value is None:
            return None
        default_source = named.get("defaultColor") or (positional[1] if len(positional) >= 2 else "Color.Gray")
        default_color = self.color_expression(default_source, call, parameters)
        if default_color is None:
            return None
        self._uses_android_color_parser = True
        return f"this.parseAndroidColor({color_value}, {default_color})"

    def color_expression(
        self,
        expression: str,
        call: dict[str, Any] | None,
        parameters: dict[str, str] | None = None,
    ) -> str | None:
        stripped = strip_top_level_trailing_comma(expression)
        known_parameters = parameters or {}
        local_expression = self.local_value_expression(stripped, known_parameters)
        if local_expression is not None:
            return self.color_expression(local_expression, call, known_parameters)
        subject_when = self.subject_when_color_expression(stripped, call, known_parameters)
        if subject_when is not None:
            return subject_when
        elvis = split_top_level_elvis(stripped)
        if elvis is not None and elvis[1].strip() == "Color.Unspecified":
            translated = self.color_expression(elvis[0], call, known_parameters)
            if translated is not None:
                return translated
        copied_color = self.color_copy_alpha_expression(stripped, call, known_parameters)
        if copied_color is not None:
            return copied_color
        android_color = self.android_get_color_expression(stripped, call, known_parameters)
        if android_color is not None:
            return android_color
        conditional_parts = kotlin_if_else_parts(stripped)
        if conditional_parts is not None:
            condition, true_branch, false_branch = conditional_parts
            condition_expression = self.value_expression(condition, "boolean", known_parameters)
            if condition_expression is None:
                return None
            true_color = self.color_expression(true_branch, call, known_parameters)
            false_color = self.color_expression(false_branch, call, known_parameters)
            if true_color is None or false_color is None:
                return None
            return f"({condition_expression} ? {true_color} : {false_color})"
        if parameters is not None and parameters.get(stripped) == "ResourceColor":
            return stripped
        match = re.fullmatch(r"MaterialTheme\.colorScheme\.([A-Za-z_][A-Za-z0-9_]*)", stripped)
        if match is not None:
            name = f"compose_theme_{snake_name(match.group(1))}"
            if name in self.resource_names:
                return f"$r('app.color.{name}')"
            self.add_unresolved("theme_resource", call, f"generated color resource is missing: {name}")
            return None
        extended = re.fullmatch(
            r"MaterialTheme\.[A-Za-z_][A-Za-z0-9_]*\.([A-Za-z_][A-Za-z0-9_]*)",
            stripped,
        )
        if extended is not None:
            name = f"compose_extended_color_{snake_name(extended.group(1))}"
            if name in self.resource_names:
                return f"$r('app.color.{name}')"
        if IDENTIFIER_PATTERN.fullmatch(stripped) is not None:
            name = f"compose_color_{snake_name(stripped)}"
            if name in self.resource_names:
                return f"$r('app.color.{name}')"
        return self.static_color_expression(stripped)

    def linear_gradient_line(
        self,
        expression: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> str | None:
        stripped = expression.strip()
        local_expression = self.local_value_expression(stripped, parameters)
        if local_expression is not None:
            return self.linear_gradient_line(local_expression, call, parameters)
        gradient = re.fullmatch(r"Brush\.linearGradient\s*\((.*)\)", stripped, re.S)
        if gradient is None:
            return None
        positional, named = named_arguments(gradient.group(1))
        if set(named) - {"colors", "start", "end", "tileMode"}:
            return None
        if "start" in named or "end" in named:
            return None
        if "tileMode" in named and named["tileMode"].strip() != "TileMode.Clamp":
            return None
        colors_source = named.get("colors") or (positional[0] if positional else None)
        if colors_source is None:
            return None
        colors = self.linear_gradient_colors_expression(colors_source, call, parameters)
        if colors is None:
            return None
        return f".linearGradient({{ direction: GradientDirection.RightBottom, colors: {colors} }})"

    def linear_gradient_colors_expression(
        self,
        expression: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> str | None:
        colors = re.fullmatch(r"(?:listOf|mutableListOf|arrayListOf)\s*\((.*)\)", expression.strip(), re.S)
        if colors is None:
            return None
        color_items = split_arguments(colors.group(1))
        if len(color_items) < 2:
            return None
        translated_colors = [self.color_expression(item, call, parameters) for item in color_items]
        if any(color is None for color in translated_colors):
            return None
        denominator = Decimal(len(translated_colors) - 1)
        stops = [decimal_literal(Decimal(index) / denominator) for index in range(len(translated_colors))]
        return "[" + ", ".join(
            f"[{color}, {stop}]"
            for color, stop in zip(translated_colors, stops)
            if color is not None
        ) + "]"

    def subject_when_color_expression(
        self,
        expression: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> str | None:
        parsed = kotlin_subject_when_parts(expression)
        if parsed is None:
            return None
        subject, branches, else_value = parsed
        subject_expression = self.value_expression(subject, "string", parameters)
        if subject_expression is None:
            return None
        rendered_branches: list[tuple[str, str]] = []
        enum_names: set[str] = set()
        branch_enum_values: set[str] = set()
        for cases, value in branches:
            branch_color = self.color_expression(value, call, parameters)
            if branch_color is None:
                return None
            for case in cases:
                case_value = self.enum_entry_string_expression(case) or self.value_expression(case, "string", parameters)
                if case_value is None:
                    return None
                enum_case = re.fullmatch(
                    r"(?:[A-Za-z_][A-Za-z0-9_]*\.)*([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)",
                    case.strip(),
                )
                if enum_case is not None and enum_case.group(2) in self.enum_classes.get(enum_case.group(1), set()):
                    enum_names.add(enum_case.group(1))
                    branch_enum_values.add(enum_case.group(2))
                rendered_branches.append((case_value, branch_color))
        fallback_color: str | None = None
        if else_value is not None:
            fallback_color = self.color_expression(else_value, call, parameters)
        elif len(enum_names) == 1:
            enum_values = next(iter(self.enum_classes.get(next(iter(enum_names)), set())), None)
            if enum_values is not None and branch_enum_values == self.enum_classes[next(iter(enum_names))]:
                fallback_color = rendered_branches[-1][1]
                rendered_branches = rendered_branches[:-1]
        if fallback_color is None:
            return None
        result = fallback_color
        for case_value, branch_color in reversed(rendered_branches):
            result = f"{subject_expression} === {case_value} ? {branch_color} : {result}"
        return f"({result})"

    def subject_when_boolean_expression(
        self,
        expression: str,
        parameters: dict[str, str],
    ) -> str | None:
        parsed = kotlin_subject_when_parts(expression)
        if parsed is None:
            return None
        subject, branches, else_value = parsed
        subject_expression = self.value_expression(subject, "string", parameters)
        if subject_expression is None:
            return None
        rendered_branches: list[tuple[str, str]] = []
        enum_names: set[str] = set()
        branch_enum_values: set[str] = set()
        for cases, value in branches:
            branch_boolean = self.value_expression(value, "boolean", parameters)
            if branch_boolean is None:
                return None
            for case in cases:
                case_value = self.enum_entry_string_expression(case) or self.value_expression(case, "string", parameters)
                if case_value is None:
                    return None
                enum_case = re.fullmatch(
                    r"(?:[A-Za-z_][A-Za-z0-9_]*\.)*([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)",
                    case.strip(),
                )
                if enum_case is not None and enum_case.group(2) in self.enum_classes.get(enum_case.group(1), set()):
                    enum_names.add(enum_case.group(1))
                    branch_enum_values.add(enum_case.group(2))
                rendered_branches.append((case_value, branch_boolean))
        fallback_boolean: str | None = None
        if else_value is not None:
            fallback_boolean = self.value_expression(else_value, "boolean", parameters)
        elif len(enum_names) == 1:
            enum_values = next(iter(self.enum_classes.get(next(iter(enum_names)), set())), None)
            if enum_values is not None and branch_enum_values == self.enum_classes[next(iter(enum_names))]:
                fallback_boolean = rendered_branches[-1][1]
                rendered_branches = rendered_branches[:-1]
        if fallback_boolean is None:
            return None
        result = fallback_boolean
        for case_value, branch_boolean in reversed(rendered_branches):
            result = f"{subject_expression} === {case_value} ? {branch_boolean} : {result}"
        return f"({result})"

    def equality_operand_expression(
        self,
        expression: str,
        target_type: str,
        parameters: dict[str, str],
    ) -> str | None:
        nullable_type = f"{target_type} | null"
        nullable_translated = self.value_expression(expression, nullable_type, parameters)
        if nullable_translated is not None:
            return nullable_translated
        translated = self.value_expression(expression, target_type, parameters)
        if translated is not None:
            return translated
        return None

    def equality_boolean_expression(
        self,
        expression: str,
        parameters: dict[str, str],
    ) -> str | None:
        comparison = re.fullmatch(r"(.+?)\s*([!=]=)\s*(.+)", expression.strip(), re.S)
        if comparison is None:
            return None
        left_source = comparison.group(1).strip()
        operator = "!==" if comparison.group(2) == "!=" else "==="
        right_source = comparison.group(3).strip()
        for target_type in ("number", "string", "boolean", "ResourceStr"):
            left = self.equality_operand_expression(left_source, target_type, parameters)
            right = self.equality_operand_expression(right_source, target_type, parameters)
            if left is not None and right is not None:
                return f"{left} {operator} {right}"
        return None

    def collection_contains_boolean_expression(
        self,
        expression: str,
        parameters: dict[str, str],
    ) -> str | None:
        contains = re.fullmatch(r"(.+?)\.contains\s*\((.*)\)", expression.strip(), re.S)
        if contains is None:
            return None
        collection_source = contains.group(1).strip()
        collection = self.value_expression(collection_source, "unknown[]", parameters)
        if collection is None:
            return None
        element_target_type: str | None = None
        if IDENTIFIER_PATTERN.fullmatch(collection_source) is not None:
            collection_type = parameters.get(collection_source)
            if isinstance(collection_type, str):
                element_target_type = array_element_target_type(collection_type)
        translated_element: str | None = None
        if element_target_type is not None:
            translated_element = self.value_expression(contains.group(2).strip(), element_target_type, parameters)
        if translated_element is None:
            for candidate_type in ("number", "string", "boolean", "ResourceStr"):
                translated_element = self.value_expression(contains.group(2).strip(), candidate_type, parameters)
                if translated_element is not None:
                    break
        if translated_element is None:
            return None
        return f"{collection}.includes({translated_element})"

    def data_class_validity_expression(
        self,
        expression: str,
        parameters: dict[str, str],
    ) -> str | None:
        valid_call = re.fullmatch(r"(.+?)\.isValid\s*\(\s*\)", expression.strip(), re.S)
        if valid_call is None:
            return None
        receiver = valid_call.group(1).strip()
        error_presence = self.nullable_data_class_presence_expression(f"{receiver}.error", parameters)
        if error_presence is None:
            return None
        return f"{error_presence} === undefined || {error_presence} === null"

    def font_color_lines(
        self,
        expression: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> list[str] | None:
        optional_color = self.optional_font_color_parameter(expression, parameters)
        if optional_color is not None and call.get("component") == "Text":
            return [f"{OPTIONAL_FONT_COLOR_PREFIX}{optional_color}"]
        copied = re.fullmatch(
            r"(.+?)\.copy\s*\(\s*alpha\s*=\s*([0-9]+(?:\.[0-9]+)?)[fFdD]?\s*,?\s*\)\s*",
            expression.strip(),
            re.S,
        )
        if copied is not None:
            alpha = number_value(copied.group(2))
            if alpha is None:
                return None
            alpha_number = float(alpha)
            if alpha_number < 0 or alpha_number > 1:
                return None
            color = self.color_expression(copied.group(1).strip(), call, parameters)
            if color is None:
                return None
            return [f".fontColor({color})", f".opacity({alpha})"]
        color = self.color_expression(expression, call, parameters)
        if color is None:
            return None
        return [f".fontColor({color})"]

    def optional_font_color_parameter(
        self,
        expression: str,
        parameters: dict[str, str],
    ) -> str | None:
        elvis = split_top_level_elvis(expression.strip())
        if elvis is None or elvis[1].strip() != "Color.Unspecified":
            return None
        candidate = elvis[0].strip()
        if IDENTIFIER_PATTERN.fullmatch(candidate) is None:
            return None
        return candidate if parameters.get(candidate) == "ResourceColor | null" else None

    def list_literal_expression(
        self,
        expression: str,
        element_target_type: str,
        parameters: dict[str, str],
    ) -> str | None:
        match = re.fullmatch(
            r"(?:listOf|mutableListOf|arrayListOf)\s*\((.*)\)",
            expression.strip(),
            re.S,
        )
        if match is None:
            return None
        raw_items = match.group(1).strip()
        if not raw_items:
            return "[]"
        translated_items: list[str] = []
        for item in split_arguments(raw_items):
            translated = self.value_expression(item, element_target_type, parameters)
            if translated is None:
                return None
            translated_items.append(translated)
        return "[" + ", ".join(translated_items) + "]"

    def to_string_operand_expression(
        self,
        expression: str,
        parameters: dict[str, str],
    ) -> str | None:
        for target_type in ("number", "string", "ResourceStr"):
            translated = self.value_expression(expression, target_type, parameters)
            if translated is not None:
                return translated
        return None

    def to_string_inner_expression(
        self,
        expression: str,
        parameters: dict[str, str],
    ) -> str | None:
        stripped = strip_wrapping_parentheses(expression)
        elvis = split_top_level_elvis(stripped)
        if elvis is not None:
            left = self.to_string_operand_expression(elvis[0], parameters)
            right = self.to_string_operand_expression(elvis[1], parameters)
            if left is not None and right is not None:
                return f"({left} ?? {right})"
            return None
        translated = self.to_string_operand_expression(stripped, parameters)
        if translated is None:
            return None
        if self.nullable_data_class_presence_expression(stripped, parameters) is not None:
            return f"{translated} ?? null"
        if IDENTIFIER_PATTERN.fullmatch(stripped) is not None:
            parameter_type = parameters.get(stripped)
            if isinstance(parameter_type, str) and parameter_type.endswith(" | null"):
                return f"{translated} ?? null"
        return translated

    def rupee_format_receiver_expression(
        self,
        expression: str,
        parameters: dict[str, str],
    ) -> str | None:
        match = re.fullmatch(r"(.+?)(?:\?\.|\.)\s*formatRupees\s*\(\s*\)", expression.strip(), re.S)
        if match is None:
            return None
        receiver = strip_wrapping_parentheses(match.group(1).strip())
        numeric_conversion = re.fullmatch(
            r"(.+?)\.to(?:BigDecimal|Double|Float|Int|Long)\s*\(\s*\)",
            receiver,
            re.S,
        )
        if numeric_conversion is not None:
            receiver = numeric_conversion.group(1).strip()
        return (
            self.nullable_data_class_property_path_expression(receiver, "string", parameters)
            or self.data_class_property_path_expression(receiver, "string", parameters)
            or self.value_expression(receiver, "string", parameters)
            or self.numeric_template_value_expression(receiver, parameters)
        )

    def rupee_format_expression(
        self,
        expression: str,
        parameters: dict[str, str],
    ) -> str | None:
        receiver = self.rupee_format_receiver_expression(expression, parameters)
        if receiver is None:
            return None
        self._uses_rupee_formatter = True
        return f"this.formatRupees({receiver})"

    def rupee_format_elvis_expression(
        self,
        expression: str,
        target_type: str,
        parameters: dict[str, str],
    ) -> str | None:
        elvis = split_top_level_elvis(expression.strip())
        if elvis is None:
            return None
        receiver = self.rupee_format_receiver_expression(elvis[0], parameters)
        if receiver is None:
            return None
        fallback = self.value_expression(elvis[1], target_type, parameters)
        if fallback is None:
            return None
        self._uses_rupee_formatter = True
        return f"(({receiver} === null || {receiver} === undefined) ? {fallback} : this.formatRupees({receiver}))"

    def if_empty_string_expression(
        self,
        expression: str,
        target_type: str,
        parameters: dict[str, str],
    ) -> str | None:
        match = re.fullmatch(r"(.+?)\.ifEmpty\s*\{\s*(.+?)\s*\}", expression.strip(), re.S)
        if match is None:
            return None
        source = self.value_expression(match.group(1).strip(), target_type, parameters)
        fallback = self.value_expression(match.group(2).strip(), target_type, parameters)
        if source is None or fallback is None:
            return None
        return f"({source} === '' ? {fallback} : {source})"

    def collected_state_initial_expression(
        self,
        expression: str,
        target_type: str,
        parameters: dict[str, str],
    ) -> str | None:
        match = re.fullmatch(
            r".+?\.collectAsState(?:WithLifecycle)?\s*\((.*)\)\.value",
            expression.strip(),
            re.S,
        )
        if match is None:
            return None
        positional, named = named_arguments(match.group(1))
        initial = named.get("initialValue") or named.get("initial") or (positional[0] if positional else None)
        if initial is None:
            return None
        return self.value_expression(initial, target_type, parameters)

    def value_expression(
        self,
        expression: str,
        target_type: str,
        parameters: dict[str, str],
    ) -> str | None:
        stripped = expression.strip()
        inline_parameter_value = self._current_parameter_values.get(stripped)
        if (
            inline_parameter_value is not None
            and IDENTIFIER_PATTERN.fullmatch(stripped) is not None
        ):
            return inline_parameter_value
        nullable_target = target_type.endswith(" | null")
        undefined_target = target_type.endswith(" | undefined")
        non_null_target = target_type[: -len(" | null")] if nullable_target else target_type
        non_null_target = target_type[: -len(" | undefined")] if undefined_target else non_null_target
        if non_null_target == "(() => void)":
            non_null_target = "() => void"
        if stripped == "null" and nullable_target:
            return "null"
        if stripped in {"undefined", "Dp.Unspecified"} and undefined_target:
            return "undefined"
        remembered_state = re.fullmatch(
            r"remember(?:Saveable)?\s*(?:\([^)]*\))?\s*\{\s*(mutableStateOf(?:<[^>]+>)?\s*\(.*\))\s*\}",
            stripped,
            re.S,
        )
        if remembered_state is not None:
            return self.value_expression(remembered_state.group(1).strip(), target_type, parameters)
        state_constructor = re.fullmatch(r"mutableStateOf(?:<[^>]+>)?\s*\((.*)\)", stripped, re.S)
        if state_constructor is not None:
            return self.value_expression(state_constructor.group(1).strip(), target_type, parameters)
        remembered_value = re.fullmatch(
            r"remember(?:Saveable)?\s*(?:\([^)]*\))?\s*\{\s*(.+)\s*\}",
            stripped,
            re.S,
        )
        if remembered_value is not None:
            return self.value_expression(remembered_value.group(1).strip(), target_type, parameters)
        collected_initial = self.collected_state_initial_expression(stripped, target_type, parameters)
        if collected_initial is not None:
            return collected_initial
        if stripped in parameters and (
            parameters[stripped] == target_type
            or (nullable_target and parameters[stripped] == non_null_target)
            or (undefined_target and parameters[stripped] == non_null_target)
            or callback_types_compatible(parameters[stripped], target_type)
        ):
            return stripped
        local_expression = self.local_value_expression(stripped, parameters)
        if local_expression is not None:
            return self.value_expression(local_expression, target_type, parameters)
        if nullable_target:
            return self.value_expression(stripped, non_null_target, parameters)
        if undefined_target:
            return self.value_expression(stripped, non_null_target, parameters)
        if target_type == "Date":
            if stripped in parameters and parameters[stripped] == "Date":
                return stripped
            to_date = re.fullmatch(r"(.+?)\.toDate\s*\(\s*\)", stripped, re.S)
            if to_date is not None:
                translated_inner = self.value_expression(to_date.group(1).strip(), "Date", parameters)
                if translated_inner is not None:
                    return translated_inner
            calendar_selected = re.fullmatch(
                r"([A-Za-z_][A-Za-z0-9_]*)\.calendarUiState\.value\.selected(?:Start|End)Date!!(?:\.toDate\s*\(\s*\))?",
                stripped,
                re.S,
            )
            if calendar_selected is not None:
                state_field = self.state_field_expression(self.root, calendar_selected.group(1), "Date", parameters)
                if state_field is not None:
                    return state_field
            state_property = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\.selectedDateMillis", stripped)
            if state_property is not None:
                state_field = self.state_field_expression(self.root, state_property.group(1), "Date", parameters)
                if state_field is not None:
                    return state_field
            literal_number = number_value(stripped)
            if literal_number is not None:
                return f"new Date({literal_number})"
            if stripped in {"LocalDate.now()", "LocalTime.now()", "Date()"}:
                return "new Date()"
            translated_date = self.date_from_millis_expression(stripped, parameters)
            if translated_date is not None:
                return translated_date
        if target_type == "Resource":
            property_resource = self.data_class_property_path_expression(stripped, "Resource", parameters)
            if property_resource is not None:
                return property_resource
            return self.drawable_resource_expression(stripped, parameters)
        target_array_element = array_element_target_type(target_type)
        if target_type == "unknown[]" or target_array_element is not None:
            if (
                target_type == "unknown[]"
                and stripped in parameters
                and array_element_target_type(parameters[stripped]) is not None
            ):
                return stripped
            if stripped in {"emptyList()", "listOf()", "mutableListOf()"}:
                return "[]"
            if target_array_element is not None:
                list_literal = self.list_literal_expression(stripped, target_array_element, parameters)
                if list_literal is not None:
                    return list_literal
            property_collection = self.data_class_property_path_expression(stripped, "unknown[]", parameters)
            if property_collection is not None:
                return property_collection
        first_value = self.collection_first_value_expression(stripped, target_type, parameters)
        if first_value is not None:
            return first_value
        state_value_access = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\.value", stripped)
        if state_value_access is not None:
            owner = state_value_access.group(1)
            owner_type = parameters.get(owner)
            if owner_type == target_type or (nullable_target and owner_type == non_null_target):
                return owner
            local_state = self.local_value_expression(owner, parameters)
            if local_state is not None:
                translated = self.value_expression(local_state, target_type, parameters)
                if translated is not None:
                    return translated
        property_path = self.data_class_property_path_expression(stripped, target_type, parameters)
        if property_path is not None:
            return property_path
        local_property = self.local_data_class_property_expression(stripped, target_type, parameters)
        if local_property is not None:
            return local_property
        state_value_property_path = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\.value\.([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+)", stripped)
        if state_value_property_path is not None:
            path_expression = f"{state_value_property_path.group(1)}.{state_value_property_path.group(2)}"
            translated_path = self.data_class_property_path_expression(path_expression, target_type, parameters)
            if translated_path is not None:
                return translated_path
        state_value_nullable_property_path = re.fullmatch(
            r"([A-Za-z_][A-Za-z0-9_]*)\.value((?:\?\.|\.)[A-Za-z_][A-Za-z0-9_]*(?:(?:\?\.|\.)[A-Za-z_][A-Za-z0-9_]*)*)",
            stripped,
        )
        if state_value_nullable_property_path is not None:
            translated_path = self.nullable_data_class_property_path_expression(
                f"{state_value_nullable_property_path.group(1)}{state_value_nullable_property_path.group(2)}",
                target_type,
                parameters,
            )
            if translated_path is not None:
                return translated_path
        property_access = re.fullmatch(
            r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)",
            stripped,
        )
        if property_access is not None:
            owner_type = parameters.get(property_access.group(1))
            for property_item in self.data_class_properties_by_target.get(owner_type or "", []):
                if property_item["name"] == property_access.group(2) and (
                    property_item["type"] == target_type
                    or (target_type == "ResourceStr" and property_item["type"] == "string")
                ):
                    return stripped
        state_value_property_access = re.fullmatch(
            r"([A-Za-z_][A-Za-z0-9_]*)\.value\.([A-Za-z_][A-Za-z0-9_]*)",
            stripped,
        )
        if state_value_property_access is not None:
            owner_type = parameters.get(state_value_property_access.group(1))
            for property_item in self.data_class_properties_by_target.get(owner_type or "", []):
                if property_item["name"] == state_value_property_access.group(2) and (
                    property_item["type"] == target_type
                    or (target_type == "ResourceStr" and property_item["type"] == "string")
                ):
                    return f"{state_value_property_access.group(1)}.{state_value_property_access.group(2)}"
        safe_property_access = re.fullmatch(
            r"([A-Za-z_][A-Za-z0-9_]*)\?\.\s*([A-Za-z_][A-Za-z0-9_]*)",
            stripped,
        )
        if safe_property_access is not None:
            owner_type = parameters.get(safe_property_access.group(1))
            for property_item in self.data_class_properties_by_target.get(owner_type or "", []):
                if property_item["name"] == safe_property_access.group(2) and (
                    property_item["type"] == target_type
                    or (target_type == "ResourceStr" and property_item["type"] == "string")
                ):
                    return f"{safe_property_access.group(1)}?.{safe_property_access.group(2)}"
        nested_safe_as_string = re.fullmatch(r"(.+?)\?\.\s*asString\s*\(\s*\)", stripped, re.S)
        if nested_safe_as_string is not None and target_type in {"string", "ResourceStr"}:
            source = nested_safe_as_string.group(1).strip()
            translated_string = (
                self.nullable_data_class_property_path_expression(source, "string", parameters)
                or self.data_class_property_path_expression(source, "string", parameters)
            )
            if translated_string is not None:
                return translated_string
            translated_resource = (
                self.nullable_data_class_property_path_expression(source, "ResourceStr", parameters)
                or self.data_class_property_path_expression(source, "ResourceStr", parameters)
            )
            if translated_resource is not None:
                if target_type == "ResourceStr":
                    return translated_resource
                self._uses_resource_str_resolver = True
                return f"this.resolveResourceStr({translated_resource})"
        safe_property_as_string = re.fullmatch(
            r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\?\.\s*asString\s*\(\s*\)",
            stripped,
        )
        if safe_property_as_string is not None and target_type in {"string", "ResourceStr"}:
            owner_type = parameters.get(safe_property_as_string.group(1))
            for property_item in self.data_class_properties_by_target.get(owner_type or "", []):
                if property_item["name"] == safe_property_as_string.group(2) and property_item["type"] in {"string", "ResourceStr"}:
                    return f"{safe_property_as_string.group(1)}.{safe_property_as_string.group(2)}"
        safe_state_value_property_as_string = re.fullmatch(
            r"([A-Za-z_][A-Za-z0-9_]*)\.value\.([A-Za-z_][A-Za-z0-9_]*)\?\.\s*asString\s*\(\s*\)",
            stripped,
        )
        if safe_state_value_property_as_string is not None and target_type in {"string", "ResourceStr"}:
            owner_type = parameters.get(safe_state_value_property_as_string.group(1))
            for property_item in self.data_class_properties_by_target.get(owner_type or "", []):
                if property_item["name"] == safe_state_value_property_as_string.group(2) and property_item["type"] in {"string", "ResourceStr"}:
                    return f"{safe_state_value_property_as_string.group(1)}.{safe_state_value_property_as_string.group(2)}"
        if target_type in self.data_class_properties_by_target:
            return self.data_class_value_expression(stripped, target_type, parameters)
        if (
            target_type == "ResourceStr"
            and stripped in parameters
            and parameters[stripped] in {"ResourceStr", "string"}
        ):
            return stripped
        as_string = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\.asString\s*\(\s*\)", stripped)
        if (
            as_string is not None
            and target_type == "ResourceStr"
            and parameters.get(as_string.group(1)) in {"ResourceStr", "string", "ResourceStr | null", "string | null"}
        ):
            return as_string.group(1)
        if target_type in {"string", "ResourceStr"}:
            rupee_elvis = self.rupee_format_elvis_expression(stripped, target_type, parameters)
            if rupee_elvis is not None:
                return rupee_elvis
            rupee = self.rupee_format_expression(stripped, parameters)
            if rupee is not None:
                return rupee
            if_empty = self.if_empty_string_expression(stripped, target_type, parameters)
            if if_empty is not None:
                return if_empty
            if stripped == "getGreetingMessage()":
                self._uses_greeting_helper = True
                return "this.getGreetingMessage()"
            if target_type == "string":
                route_string = self.route_string_expression(stripped)
                if route_string is not None:
                    return route_string
            to_string = re.fullmatch(r"(.+?)\.toString\s*\(\s*\)", stripped, re.S)
            if to_string is not None:
                source = self.to_string_inner_expression(to_string.group(1).strip(), parameters)
                if source is not None:
                    return f"String({source})"
            enum_property = self.enum_string_property_expression(stripped, parameters)
            if enum_property is not None:
                return enum_property
            enum_entry = self.enum_entry_string_expression(stripped)
            if enum_entry is not None:
                return enum_entry
            grouped = self.split_string_with_divider_expression(stripped, parameters)
            if grouped is not None:
                return grouped
            interpolated = self.interpolated_string_expression(stripped, parameters)
            if interpolated is not None:
                return interpolated
            annotated = self.build_annotated_string_expression(stripped, target_type, parameters)
            if annotated is not None:
                return annotated
            or_empty = re.fullmatch(r"(.+?)\.orEmpty\s*\(\s*\)", stripped, re.S)
            if or_empty is not None:
                source = or_empty.group(1).strip()
                translated = self.value_expression(source, target_type, parameters) or self.nullable_data_class_property_path_expression(
                    source,
                    target_type,
                    parameters,
                )
                if translated is not None:
                    return f"({translated} ?? '')"
            elvis = split_top_level_elvis(stripped)
            if elvis is not None:
                left = self.value_expression(elvis[0], target_type, parameters) or self.nullable_data_class_property_path_expression(
                    elvis[0],
                    target_type,
                    parameters,
                )
                right = self.value_expression(elvis[1], target_type, parameters)
                if left is not None and right is not None:
                    return f"({left} ?? {right})"
            conditional_parts = kotlin_if_else_parts(stripped)
            if conditional_parts is not None:
                condition, true_branch, false_branch = conditional_parts
                condition_expression = self.value_expression(condition, "boolean", parameters)
                if condition_expression is not None:
                    first = self.value_expression(true_branch, target_type, parameters)
                    second = self.value_expression(false_branch, target_type, parameters)
                    if first is not None and second is not None:
                        return f"({condition_expression} ? {first} : {second})"
                first = re.sub(r"\s+", " ", true_branch)
                second = re.sub(r"\s+", " ", false_branch)
                for source, alternate in ((first, second), (second, first)):
                    case_mapping = re.fullmatch(r"(.+?)\.(?:toUpperCase|uppercase)\s*\(.*\)", source, re.S)
                    if case_mapping is None:
                        continue
                    base = re.sub(r"\s+", " ", case_mapping.group(1).strip())
                    if base == alternate:
                        translated = self.value_expression(base, target_type, parameters)
                        if translated is not None:
                            return translated
            template = kotlin_string_template(stripped, parameters)
            if template is not None:
                return template
        if target_type == "string":
            replaced = self.static_string_resource_replace_expression(stripped)
            if replaced is not None:
                return replaced
            key = self.string_resource_key(stripped)
            if key is not None and key in self.string_values:
                return arkts_string(self.string_values[key])
            return kotlin_string(stripped)
        if target_type == "ResourceStr":
            replaced = self.static_string_resource_replace_expression(stripped)
            if replaced is not None:
                return replaced
            uppercase = re.fullmatch(r"(.+)\.uppercase\s*\(\s*\)", stripped)
            if uppercase is not None:
                key = self.string_resource_key(uppercase.group(1).strip())
                if key is not None and key in self.string_values:
                    return arkts_string(self.string_values[key].upper())
            resource = self.string_resource_expression(stripped, parameters)
            if resource is not None:
                return resource
            return kotlin_string(stripped)
        if target_type == "boolean":
            time_boolean = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\.is24hour", stripped)
            if time_boolean is not None:
                local_expression = self.local_value_expression(time_boolean.group(1), parameters)
                if isinstance(local_expression, str):
                    military = self.material_time_picker_use_military_expression(local_expression, parameters)
                    if military is not None:
                        return military
            if re.fullmatch(r"ColorFilter\.tint\s*\(.+\)", stripped, re.S):
                return "true"
            subject_when = self.subject_when_boolean_expression(stripped, parameters)
            if subject_when is not None:
                return subject_when
            valid_expression = self.data_class_validity_expression(stripped, parameters)
            if valid_expression is not None:
                return valid_expression
            if stripped == "isSystemInDarkTheme()":
                self._uses_resource_manager = True
                return "this.isSystemInDarkTheme()"
            contains_expression = self.collection_contains_boolean_expression(stripped, parameters)
            if contains_expression is not None:
                return contains_expression
            string_empty_call = re.fullmatch(r"(.+?)\.is(Not)?Empty\s*\(\s*\)", stripped, re.S)
            if string_empty_call is not None:
                base_expression = string_empty_call.group(1).strip()
                text_expression = self.value_expression(base_expression, "string", parameters)
                if text_expression is not None:
                    operator = "!==" if string_empty_call.group(2) == "Not" else "==="
                    return f"{text_expression} {operator} ''"
                collection_expression = self.value_expression(base_expression, "unknown[]", parameters)
                if collection_expression is not None:
                    operator = ">" if string_empty_call.group(2) == "Not" else "==="
                    right = "0" if operator == ">" else "0"
                    return f"{collection_expression}.length {operator} {right}"
            size_comparison = re.fullmatch(r"(.+?)\.size\s*(<=|>=|<|>|==|!=)\s*([0-9]+)", stripped, re.S)
            if size_comparison is not None:
                collection_expression = self.value_expression(size_comparison.group(1).strip(), "unknown[]", parameters)
                if collection_expression is not None:
                    return f"{collection_expression}.length {size_comparison.group(2)} {size_comparison.group(3)}"
            null_check = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*([!=]=)\s*null", stripped)
            if null_check is not None:
                name = null_check.group(1)
                operator = null_check.group(2)
                parameter_type = parameters.get(name)
                if parameter_type in {"string", "ResourceStr"}:
                    comparison = f"{name} === ''"
                    return comparison if operator == "==" else f"{name} !== ''"
                if isinstance(parameter_type, str) and parameter_type.endswith(" | null"):
                    comparison = f"{name} === null"
                    return comparison if operator == "==" else f"{name} !== null"
            unspecified_check = re.fullmatch(
                r"([A-Za-z_][A-Za-z0-9_]*)\s*([!=]=)\s*Dp\.Unspecified",
                stripped,
            )
            if unspecified_check is not None:
                name = unspecified_check.group(1)
                operator = unspecified_check.group(2)
                if parameters.get(name) == "number | undefined":
                    comparison = f"{name} === undefined"
                    return comparison if operator == "==" else f"{name} !== undefined"
            equality_expression = self.equality_boolean_expression(stripped, parameters)
            if equality_expression is not None:
                return equality_expression
            for operator in ("&&", "||"):
                parts = split_top_level_operator(stripped, operator)
                if parts is not None:
                    left = self.value_expression(parts[0], "boolean", parameters)
                    right = self.value_expression(parts[1], "boolean", parameters)
                    if left is not None and right is not None:
                        return f"({left} {operator} {right})"
            negated = re.fullmatch(r"!\s*(.+)", stripped, re.S)
            if negated is not None:
                inner = self.value_expression(negated.group(1).strip(), "boolean", parameters)
                if inner is not None:
                    if IDENTIFIER_PATTERN.fullmatch(inner) is not None:
                        return f"!{inner}"
                    return f"!({inner})"
            if stripped in {"true", "false"}:
                return stripped
        if target_type == "VerticalAlign":
            return {
                "Alignment.Top": "VerticalAlign.Top",
                "Alignment.CenterVertically": "VerticalAlign.Center",
                "Alignment.Bottom": "VerticalAlign.Bottom",
            }.get(stripped)
        if target_type == "HorizontalAlign":
            return {
                "Alignment.Start": "HorizontalAlign.Start",
                "Alignment.CenterHorizontally": "HorizontalAlign.Center",
                "Alignment.End": "HorizontalAlign.End",
            }.get(stripped)
        if target_type == "TextAlign":
            if parameters.get(stripped) == "TextAlign":
                return stripped
            return {
                "TextAlign.Start": "TextAlign.Start",
                "TextAlign.Center": "TextAlign.Center",
                "TextAlign.End": "TextAlign.End",
                "TextAlign.Left": "TextAlign.Left",
                "TextAlign.Right": "TextAlign.Right",
                "TextAlign.Justify": "TextAlign.Justify",
            }.get(stripped)
        if target_type == "ResourceColor":
            return self.color_expression(stripped, None, parameters)
        if target_type == "Resource":
            property_resource = self.data_class_property_path_expression(stripped, "Resource", parameters)
            if property_resource is not None:
                return property_resource
            return self.drawable_resource_expression(stripped, parameters)
        if target_type == "Padding":
            return self.padding_values_expression(stripped, parameters)
        if target_type == "InputType":
            return self.input_type_expression(stripped, parameters)
        if target_type == "number":
            date_parameter_property = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\.(hour|minute)", stripped)
            if date_parameter_property is not None and parameters.get(date_parameter_property.group(1)) == "Date":
                return {
                    "hour": f"{date_parameter_property.group(1)}.getHours()",
                    "minute": f"{date_parameter_property.group(1)}.getMinutes()",
                }[date_parameter_property.group(2)]
            time_property = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\.(hour|minute|selectedDateMillis)", stripped)
            if time_property is not None:
                state_field = self.state_field_expression(self.root, time_property.group(1), "Date", parameters)
                if state_field is not None:
                    return {
                        "hour": f"{state_field}.getHours()",
                        "minute": f"{state_field}.getMinutes()",
                        "selectedDateMillis": f"{state_field}.getTime()",
                    }[time_property.group(2)]
            rounded_radius = self.rounded_corner_radius_expression(stripped, parameters)
            if rounded_radius is not None and not (rounded_radius.startswith("'") and rounded_radius.endswith("'")):
                return rounded_radius
            font_weight = font_weight_expression(stripped)
            if font_weight is not None:
                return font_weight
            dimension = dimension_value(stripped)
            if dimension is not None:
                return dimension
        if target_type == "number" and stripped == "Int.MAX_VALUE":
            return "Number.MAX_SAFE_INTEGER"
        if target_type == "number":
            literal_number = number_value(stripped)
            if literal_number is not None:
                return literal_number
        if callback_parameter_types(target_type) is not None and stripped in {"{}", "{ }"}:
            return callback_default_expression(target_type)
        if target_type == "() => void" and stripped in {"{}", "{ }"}:
            return "() => {}"
        if (
            target_type == "() => void"
            and stripped in parameters
            and parameters[stripped] == "(() => void) | null"
        ):
            return f"() => {{ if ({stripped} !== null) {{ {stripped}() }} }}"
        if target_type == "() => void":
            direct_callback = re.fullmatch(
                r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:\.\s*invoke\s*)?\(\s*\)",
                stripped,
            )
            if direct_callback is not None and parameters.get(direct_callback.group(1)) == "() => void":
                name = direct_callback.group(1)
                return f"() => {{ {name}() }}"
            callback_with_argument = re.fullmatch(
                r"(?:\{\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*(?:\.\s*invoke\s*)?\(\s*(.+?)\s*\)(?:\s*\})?",
                stripped,
                re.S,
            )
            if callback_with_argument is not None:
                name = callback_with_argument.group(1)
                callback_type = parameters.get(name)
                argument_types = callback_parameter_types(callback_type)
                argument_chunks = split_arguments(callback_with_argument.group(2))
                if argument_types is not None and len(argument_types) == len(argument_chunks):
                    translated_arguments = [
                        self.value_expression(argument, argument_type, parameters)
                        for argument, argument_type in zip(argument_chunks, argument_types)
                    ]
                    if all(argument is not None for argument in translated_arguments):
                        return f"() => {{ {name}({', '.join(argument for argument in translated_arguments if argument is not None)}) }}"
            callback = re.fullmatch(r"\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*\)\s*\}", stripped)
            if callback is not None and parameters.get(callback.group(1)) == "() => void":
                name = callback.group(1)
                return f"() => {{ {name}() }}"
            invoke_callback = re.fullmatch(
                r"\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*invoke\s*\(\s*\)\s*\}",
                stripped,
            )
            if invoke_callback is not None and parameters.get(invoke_callback.group(1)) == "() => void":
                name = invoke_callback.group(1)
                return f"() => {{ {name}() }}"
        if target_type == "(value: string) => void" and stripped in {"{}", "{ }"}:
            return "(value: string) => {}"
        if target_type == "(value: string) => void":
            callback = re.fullmatch(r"\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*it\s*\)\s*\}", stripped)
            if callback is not None and callback_parameter_types(parameters.get(callback.group(1))) == ["string"]:
                name = callback.group(1)
                return f"(value: string) => {{ {name}(value) }}"
            invoke_callback = re.fullmatch(
                r"\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*invoke\s*\(\s*it\s*\)\s*\}",
                stripped,
            )
            if invoke_callback is not None and callback_parameter_types(parameters.get(invoke_callback.group(1))) == ["string"]:
                name = invoke_callback.group(1)
                return f"(value: string) => {{ {name}(value) }}"
        if target_type == "(value: number) => void" and stripped in {"{}", "{ }"}:
            return "(value: number) => {}"
        if target_type == "(value: number) => void":
            if stripped in parameters and callback_parameter_types(parameters[stripped]) == ["number"]:
                return stripped
            callback = re.fullmatch(r"\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*it\s*\)\s*\}", stripped)
            if callback is not None and callback_parameter_types(parameters.get(callback.group(1))) == ["number"]:
                name = callback.group(1)
                return f"(value: number) => {{ {name}(value) }}"
            invoke_callback = re.fullmatch(
                r"\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*invoke\s*\(\s*it\s*\)\s*\}",
                stripped,
            )
            if invoke_callback is not None and callback_parameter_types(parameters.get(invoke_callback.group(1))) == ["number"]:
                name = invoke_callback.group(1)
                return f"(value: number) => {{ {name}(value) }}"
        if target_type == "(value: boolean) => void" and stripped in {"{}", "{ }"}:
            return "(value: boolean) => {}"
        if target_type == "(value: boolean) => void":
            if stripped in parameters and callback_parameter_types(parameters[stripped]) == ["boolean"]:
                return stripped
            callback = re.fullmatch(r"\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*it\s*\)\s*\}", stripped)
            if callback is not None and callback_parameter_types(parameters.get(callback.group(1))) == ["boolean"]:
                name = callback.group(1)
                return f"(value: boolean) => {{ {name}(value) }}"
            invoke_callback = re.fullmatch(
                r"\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*invoke\s*\(\s*it\s*\)\s*\}",
                stripped,
            )
            if invoke_callback is not None and callback_parameter_types(parameters.get(invoke_callback.group(1))) == ["boolean"]:
                name = invoke_callback.group(1)
                return f"(value: boolean) => {{ {name}(value) }}"
        return None

    def static_string_value_expression(self, expression: str, parameters: dict[str, str]) -> str | None:
        stripped = expression.strip()
        local_expression = self.local_value_expression(stripped, parameters)
        if local_expression is not None:
            return self.static_string_value_expression(local_expression, parameters)
        return kotlin_string_value(stripped)

    def split_string_with_divider_expression(self, expression: str, parameters: dict[str, str]) -> str | None:
        match = re.fullmatch(r"(.+?)\.splitStringWithDivider\s*\((.*)\)", expression.strip(), re.S)
        if match is None:
            return None
        source_value = self.static_string_value_expression(match.group(1).strip(), parameters)
        if source_value is None:
            return None
        positional, named = named_arguments(match.group(2))
        count_source = named.get("groupCharCount") or (positional[0] if positional else "4")
        divider_source = named.get("divider") or (positional[1] if len(positional) > 1 else "' '")
        count = number_value(count_source)
        if count is None or not count.isdigit():
            return None
        group_size = int(count)
        divider = kotlin_char_value(divider_source) or kotlin_string_value(divider_source)
        if group_size <= 0 or divider is None:
            return None
        chunks = [
            source_value[index : index + group_size]
            for index in range(0, len(source_value), group_size)
        ]
        return arkts_string(divider.join(chunks))

    def numeric_template_value_expression(self, expression: str, parameters: dict[str, str]) -> str | None:
        stripped = expression.strip()
        local_expression = self.local_value_expression(stripped, parameters)
        if local_expression is not None:
            return self.numeric_template_value_expression(local_expression, parameters)
        if parameters.get(stripped) == "number":
            return stripped
        literal = number_value(stripped)
        if literal is not None:
            return literal
        rounded_floor = re.fullmatch(r"floor\s*\((.*)\)\.roundToInt\s*\(\s*\)", stripped, re.S)
        if rounded_floor is not None:
            inner = self.numeric_template_value_expression(rounded_floor.group(1).strip(), parameters)
            return f"Math.floor({inner})" if inner is not None else None
        rounded = re.fullmatch(r"(.+)\.roundToInt\s*\(\s*\)", stripped, re.S)
        if rounded is not None:
            inner = self.numeric_template_value_expression(rounded.group(1).strip(), parameters)
            return f"Math.round({inner})" if inner is not None else None
        multiplied = split_top_level_operator(stripped, "*")
        if multiplied is not None:
            left = self.numeric_template_value_expression(multiplied[0], parameters)
            right = self.numeric_template_value_expression(multiplied[1], parameters)
            if left is not None and right is not None:
                return f"{left} * {right}"
        return None

    def interpolated_string_expression(self, expression: str, parameters: dict[str, str]) -> str | None:
        stripped = expression.strip()
        if not (stripped.startswith('"') and stripped.endswith('"')):
            return None
        content = stripped[1:-1]
        parts: list[str] = []
        literal: list[str] = []
        saw_placeholder = False

        def flush_literal() -> bool:
            if not literal:
                return True
            try:
                value = json.loads('"' + "".join(literal) + '"')
            except json.JSONDecodeError:
                return False
            if not isinstance(value, str):
                return False
            if value:
                parts.append(arkts_string(value))
            literal.clear()
            return True

        index = 0
        while index < len(content):
            char = content[index]
            if char == "\\":
                literal.append(char)
                index += 1
                if index < len(content):
                    literal.append(content[index])
                    index += 1
                continue
            if char != "$":
                literal.append(char)
                index += 1
                continue
            token: str | None = None
            if index + 1 < len(content) and content[index + 1] == "{":
                closing = content.find("}", index + 2)
                if closing < 0:
                    return None
                token = content[index + 2 : closing].strip()
                index = closing + 1
            else:
                match = re.match(r"\$([A-Za-z_][A-Za-z0-9_]*)", content[index:])
                if match is None:
                    literal.append(char)
                    index += 1
                    continue
                token = match.group(1)
                index += len(match.group(0))
            if not token or not flush_literal():
                return None
            string_part = self.value_expression(token, "string", parameters)
            if string_part is not None:
                parts.append(string_part)
                saw_placeholder = True
                continue
            number_part = self.numeric_template_value_expression(token, parameters)
            if number_part is not None:
                parts.append(f"String({number_part})")
                saw_placeholder = True
                continue
            return None
        if not flush_literal() or not saw_placeholder:
            return None
        return " + ".join(parts) if parts else None

    def remembered_mutable_state_initial_value(self, name: str, target_type: str, parameters: dict[str, str]) -> str | None:
        local_expression = self._current_local_values.get(name)
        if not isinstance(local_expression, str):
            return None
        if target_type == "Date":
            date_expression = self.material_date_state_expression(local_expression, parameters)
            if date_expression is not None:
                return date_expression
        remembered = re.fullmatch(
            r"remember(?:Saveable)?\s*(?:\([^)]*\))?\s*\{\s*mutableStateOf(?:<[^>]+>)?\s*\((.*)\)\s*\}",
            local_expression.strip(),
            re.S,
        )
        if remembered is None:
            remembered = re.fullmatch(r"mutableStateOf(?:<[^>]+>)?\s*\((.*)\)", local_expression.strip(), re.S)
        if remembered is None:
            return None
        initializer = remembered.group(1).strip()
        safe_parameters = {key: value for key, value in parameters.items() if key != name}
        return self.value_expression(initializer, target_type, safe_parameters)

    def state_field_expression(
        self,
        call: dict[str, Any],
        name: str,
        target_type: str,
        parameters: dict[str, str],
    ) -> str | None:
        if target_type not in {"string", "boolean", "number", "Date"} and target_type not in self.data_class_properties_by_target:
            return None
        initial_value = self.remembered_mutable_state_initial_value(name, target_type, parameters)
        if initial_value is None:
            return None
        suffix = hashlib.sha256(f"{call['source']}#{call['composable']}#{name}".encode("utf-8")).hexdigest()[:8]
        field_name = f"state{pascal_identifier(name)}{suffix}"
        key = (call["source"], call["composable"], name)
        current = self.state_fields.get(key)
        if current is None:
            self.state_fields[key] = {
                "name": field_name,
                "type": target_type,
                "initial_value": initial_value,
            }
        elif current["type"] != target_type or current["initial_value"] != initial_value:
            return None
        return f"this.{field_name}"

    def state_field_access_expression(
        self,
        call: dict[str, Any],
        expression: str,
        target_type: str,
        parameters: dict[str, str],
    ) -> str | None:
        state_value = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)(?:\.value)?", expression.strip())
        if state_value is None:
            return None
        return self.state_field_expression(call, state_value.group(1), target_type, parameters)

    def state_field_change_line(
        self,
        expression: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> str | None:
        stripped = expression.strip()
        lambda_match = re.fullmatch(r"\{\s*(.*?)\s*\}", stripped, re.S)
        if lambda_match is None:
            return None
        body = re.sub(r"\s+", " ", lambda_match.group(1).strip())
        direct = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)(?:\.value)?\s*=\s*it", body)
        statements: list[str] = []
        target_name: str | None = None
        if direct is not None:
            target_name = direct.group(1)
        else:
            direct_then_error = re.fullmatch(
                r"([A-Za-z_][A-Za-z0-9_]*)(?:\.value)?\s*=\s*it\s*;?\s*"
                r"([A-Za-z_][A-Za-z0-9_]*)(?:\.value)?\s*=\s*false",
                body,
            )
            if direct_then_error is not None:
                target_name = direct_then_error.group(1)
                error_field = self.state_field_expression(call, direct_then_error.group(2), "boolean", parameters)
                if error_field is None:
                    return None
                statements.extend((f"__VALUE__", f"{error_field} = false"))
            else:
                error_then_value = re.fullmatch(
                    r"([A-Za-z_][A-Za-z0-9_]*)(?:\.value)?\s*=\s*false\s*;?\s*"
                    r"([A-Za-z_][A-Za-z0-9_]*)(?:\.value)?\s*=\s*it",
                    body,
                )
                if error_then_value is not None:
                    target_name = error_then_value.group(2)
                    error_field = self.state_field_expression(call, error_then_value.group(1), "boolean", parameters)
                    if error_field is None:
                        return None
                    statements.append(f"{error_field} = false")
                else:
                    guarded = re.fullmatch(
                        r"if\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)(?:\.value)?\s*\)\s*\{\s*\1(?:\.value)?\s*=\s*false\s*\}\s*"
                        r"([A-Za-z_][A-Za-z0-9_]*)(?:\.value)?\s*=\s*it",
                        body,
                    )
                    if guarded is None:
                        return None
                    target_name = guarded.group(2)
                    error_field = self.state_field_expression(call, guarded.group(1), "boolean", parameters)
                    if error_field is None:
                        return None
                    statements.append(f"{error_field} = false")
        if target_name is None:
            return None
        target_field = self.state_field_expression(call, target_name, "string", parameters)
        if target_field is None:
            return None
        if statements and statements[0] == "__VALUE__":
            statements[0] = f"{target_field} = value"
        else:
            statements.append(f"{target_field} = value")
        return f".onChange((value: string): void => {{ {'; '.join(statements)} }})"

    def state_field_toggle_click_line(
        self,
        expression: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> str | None:
        stripped = expression.strip()
        lambda_match = re.fullmatch(r"\{\s*(.*?)\s*\}", stripped, re.S)
        if lambda_match is None:
            return None
        body = re.sub(r"\s+", " ", lambda_match.group(1).strip())
        toggle = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\.value\s*=\s*!\s*\1\.value", body)
        if toggle is None:
            toggle = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*!\s*\1", body)
        if toggle is None:
            return None
        previous_local_values = self._current_local_values
        local_values = call.get("local_values")
        if isinstance(local_values, dict) and all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in local_values.items()
        ):
            self._current_local_values = {**previous_local_values, **local_values}
        try:
            target_field = self.state_field_expression(call, toggle.group(1), "boolean", parameters)
        finally:
            self._current_local_values = previous_local_values
        if target_field is None:
            return None
        return f".onClick(() => {{ {target_field} = !{target_field} }})"

    def state_field_set_callback_expression(
        self,
        expression: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> str | None:
        stripped = expression.strip()
        translated_callback = re.fullmatch(r"\(\)\s*=>\s*\{.*\}", stripped, re.S)
        if translated_callback is not None:
            return stripped
        lambda_match = re.fullmatch(r"\{\s*(.*?)\s*\}", stripped, re.S)
        if lambda_match is None:
            return None
        body = re.sub(r"\s+", " ", lambda_match.group(1).strip())
        callback_clauses: list[str] = []
        remainder = body
        while True:
            remainder = remainder.lstrip()
            if remainder.startswith(";"):
                remainder = remainder[1:].strip()
            callback_match = re.match(
                r"([A-Za-z_][A-Za-z0-9_]*)(?:\s*\.\s*invoke)?\(\s*\)\s*",
                remainder,
            )
            if callback_match is None:
                break
            callback_name = callback_match.group(1)
            translated_callback = self.callback_argument_expression(
                callback_name,
                "() => void",
                call,
                parameters,
            )
            if translated_callback is None:
                return None
            callback_clauses.append(f"{translated_callback}()")
            remainder = remainder[callback_match.end() :].strip()
        if callback_clauses:
            body = remainder
        assignment = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)(?:\.value)?\s*=\s*(true|false)", body)
        previous_local_values = self._current_local_values
        local_values = call.get("local_values")
        if isinstance(local_values, dict) and all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in local_values.items()
        ):
            self._current_local_values = {**previous_local_values, **local_values}
        try:
            if assignment is not None:
                target_field = self.state_field_expression(call, assignment.group(1), "boolean", parameters)
                if target_field is None:
                    return None
                clauses = callback_clauses + [f"{target_field} = {assignment.group(2)}"]
                return f"() => {{ {'; '.join(clauses)} }}"
            data_assignment = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)(?:\.value)?\s*=\s*(.+)", body, re.S)
            if data_assignment is None:
                return None
            target_name = data_assignment.group(1)
            value_source = data_assignment.group(2).strip()
            candidate_types: list[str] = []
            constructor_match = re.fullmatch(
                r"(?:[A-Za-z_][A-Za-z0-9_]*\.)*([A-Za-z_][A-Za-z0-9_]*)\s*\(.*\)",
                value_source,
                re.S,
            )
            if constructor_match is not None:
                constructor_type = self.data_class_target_type(constructor_match.group(1))
                if constructor_type is not None:
                    candidate_types.append(constructor_type)
            candidate_types.extend(
                target_type
                for target_type in self.data_class_properties_by_target
                if target_type not in candidate_types and not target_type.endswith(" | null")
            )
            for target_type in candidate_types:
                value = self.value_expression(value_source, target_type, parameters)
                if value is None:
                    continue
                target_field = self.state_field_expression(call, target_name, target_type, parameters)
                if target_field is not None:
                    clauses = callback_clauses + [f"{target_field} = {value}"]
                    return f"() => {{ {'; '.join(clauses)} }}"
            return None
        finally:
            self._current_local_values = previous_local_values

    def state_field_set_click_line(
        self,
        expression: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> str | None:
        callback = self.state_field_set_callback_expression(expression, call, parameters)
        return f".onClick({callback})" if callback is not None else None

    def callback_argument_expression(
        self,
        expression: str,
        target_type: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> str | None:
        state_value = self.state_field_access_expression(call, expression, target_type, parameters)
        if state_value is not None:
            return state_value
        return self.value_expression(expression, target_type, parameters)

    def date_from_millis_expression(
        self,
        expression: str,
        parameters: dict[str, str],
    ) -> str | None:
        translated_number = self.value_expression(expression, "number", parameters)
        if translated_number is not None:
            return f"new Date({translated_number})"
        translated_nullable = self.value_expression(expression, "number | null", parameters)
        if translated_nullable is not None:
            return f"new Date(({translated_nullable}) ?? Date.now())"
        return None

    def material_date_state_expression(
        self,
        expression: str,
        parameters: dict[str, str],
    ) -> str | None:
        stripped = expression.strip()
        remembered_date = re.fullmatch(r"rememberDatePickerState\s*\((.*)\)", stripped, re.S)
        if remembered_date is not None:
            positional, named = named_arguments(remembered_date.group(1))
            selected_source = (
                named.get("initialSelectedDateMillis")
                or named.get("selectedDateMillis")
                or (positional[0] if positional else None)
            )
            if isinstance(selected_source, str):
                translated_date = self.date_from_millis_expression(selected_source, parameters)
                if translated_date is not None:
                    return translated_date
            return "new Date()"
        time_state = re.fullmatch(r"TimePickerState\s*\((.*)\)", stripped, re.S)
        if time_state is not None:
            positional, named = named_arguments(time_state.group(1))
            hour_source = named.get("initialHour") or (positional[0] if positional else None)
            minute_source = named.get("initialMinute") or (positional[1] if len(positional) > 1 else None)
            if isinstance(hour_source, str) and isinstance(minute_source, str):
                hour_value = self.value_expression(hour_source, "number", parameters)
                minute_value = self.value_expression(minute_source, "number", parameters)
                if hour_value is not None and minute_value is not None:
                    return f"new Date(2000, 0, 1, {hour_value}, {minute_value}, 0)"
        remembered_time = re.fullmatch(
            r"remember(?:Saveable)?\s*\{\s*TimePickerState\s*\((.*)\)\s*\}",
            stripped,
            re.S,
        )
        if remembered_time is not None:
            return self.material_date_state_expression(
                f"TimePickerState({remembered_time.group(1)})",
                parameters,
            )
        calendar_state = re.fullmatch(
            r"(?:remember(?:Saveable)?\s*\{\s*)?CalendarState\s*\((.*)\)\s*\}?",
            stripped,
            re.S,
        )
        if calendar_state is not None:
            positional, named = named_arguments(calendar_state.group(1))
            selected_source = (
                named.get("selectDate")
                or named.get("selectedStartDate")
                or (positional[2] if len(positional) > 2 else None)
            )
            if isinstance(selected_source, str):
                translated = self.value_expression(selected_source, "Date", parameters)
                if translated is not None:
                    return translated
        return None

    def material_picker_selected_state_field(
        self,
        call: dict[str, Any],
        state_expression: str,
        parameters: dict[str, str],
    ) -> str | None:
        state_match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)", state_expression.strip())
        if state_match is None:
            return None
        return self.state_field_expression(call, state_match.group(1), "Date", parameters)

    def inferred_local_calendar_state_field(
        self,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> str | None:
        local_values = call.get("local_values")
        if not isinstance(local_values, dict):
            return None
        candidates: list[str] = []
        for name, value in local_values.items():
            if not isinstance(name, str) or not isinstance(value, str):
                continue
            if self.material_date_state_expression(value, parameters) is None:
                continue
            state_field = self.state_field_expression(call, name, "Date", parameters)
            if state_field is not None:
                candidates.append(state_field)
        if len(candidates) == 1:
            return candidates[0]
        return None

    def material_time_picker_use_military_expression(
        self,
        expression: str,
        parameters: dict[str, str],
    ) -> str | None:
        stripped = expression.strip()
        remembered_time = re.fullmatch(
            r"(?:remember(?:Saveable)?\s*\{\s*)?TimePickerState\s*\((.*)\)\s*\}?",
            stripped,
            re.S,
        )
        if remembered_time is None:
            return None
        positional, named = named_arguments(remembered_time.group(1))
        military_source = named.get("is24Hour") or (positional[2] if len(positional) > 2 else None)
        if not isinstance(military_source, str):
            return None
        return self.value_expression(military_source, "boolean", parameters)

    def call_aware_value_expression(
        self,
        expression: str,
        target_type: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> str | None:
        local_expression = self.local_value_expression(expression, parameters)
        if local_expression is not None:
            return self.call_aware_value_expression(local_expression, target_type, call, parameters)
        conditional = kotlin_if_else_parts(expression)
        if conditional is not None and target_type in {"string", "ResourceStr"}:
            condition, true_branch, false_branch = conditional
            condition_expression = self.state_condition_expression(condition, call, parameters)
            true_expression = self.call_aware_value_expression(true_branch, target_type, call, parameters)
            false_expression = self.call_aware_value_expression(false_branch, target_type, call, parameters)
            if condition_expression is not None and true_expression is not None and false_expression is not None:
                return f"({condition_expression} ? {true_expression} : {false_expression})"
        if target_type == "() => void":
            callback = self.state_field_set_callback_expression(expression, call, parameters)
            if callback is not None:
                return callback
        return self.value_expression(expression, target_type, parameters)

    def form_validation_click_line(
        self,
        expression: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> str | None:
        previous_local_values = self._current_local_values
        local_values = call.get("local_values")
        if isinstance(local_values, dict) and all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in local_values.items()
        ):
            self._current_local_values = {**previous_local_values, **local_values}
        try:
            return self._form_validation_click_line(expression, call, parameters)
        finally:
            self._current_local_values = previous_local_values

    def _form_validation_click_line(
        self,
        expression: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> str | None:
        stripped = expression.strip()
        lambda_match = re.fullmatch(r"\{\s*(.*?)\s*\}", stripped, re.S)
        if lambda_match is None:
            return None
        body = re.sub(r"\s+", " ", lambda_match.group(1).strip())
        when_match = re.search(r"\bwhen\s*\{\s*(.*?)\s*\}\s*$", body, re.S)
        if when_match is None:
            return None
        branches = when_match.group(1)
        validation_matches = list(
            re.finditer(
                r"([A-Za-z_][A-Za-z0-9_]*)\.value\.isEmpty\s*\(\s*\)\s*->\s*\{\s*"
                r"([A-Za-z_][A-Za-z0-9_]*)\.value\s*=\s*true\s*\}",
                branches,
            )
        )
        if not validation_matches:
            return None
        else_match = re.search(
            r"else\s*->\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\.\s*invoke\s*)?\(\s*(.*?)\s*\)\s*$",
            branches,
            re.S,
        )
        if else_match is None:
            return None
        callback_name = else_match.group(1)
        callback_types = callback_parameter_types(parameters.get(callback_name))
        callback_arguments = split_arguments(else_match.group(2))
        if callback_types is None or len(callback_types) != len(callback_arguments):
            return None
        translated_callback_arguments = [
            self.callback_argument_expression(argument, argument_type, call, parameters)
            for argument, argument_type in zip(callback_arguments, callback_types)
        ]
        if any(argument is None for argument in translated_callback_arguments):
            return None
        clauses: list[str] = []
        for index, match in enumerate(validation_matches):
            input_field = self.state_field_access_expression(call, f"{match.group(1)}.value", "string", parameters)
            error_field = self.state_field_expression(call, match.group(2), "boolean", parameters)
            if input_field is None or error_field is None:
                return None
            prefix = "if" if index == 0 else "else if"
            clauses.append(f"{prefix} ({input_field} === '') {{ {error_field} = true }}")
        clauses.append(
            f"else {{ {callback_name}({', '.join(argument for argument in translated_callback_arguments if argument is not None)}) }}"
        )
        return f".onClick(() => {{ {' '.join(clauses)} }})"

    def state_condition_expression(
        self,
        expression: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> str | None:
        stripped = expression.strip()
        direct_state_value = self.state_field_access_expression(call, stripped, "boolean", parameters)
        if direct_state_value is not None:
            return direct_state_value
        local_expression = self.local_value_expression(stripped, parameters)
        if local_expression is not None:
            return self.state_condition_expression(local_expression, call, parameters)
        for operator in ("&&", "||"):
            parts = split_top_level_operator(stripped, operator)
            if parts is not None:
                left = self.state_condition_expression(parts[0], call, parameters)
                right = self.state_condition_expression(parts[1], call, parameters)
                if left is not None and right is not None:
                    return f"({left} {operator} {right})"
        negated = re.fullmatch(r"!\s*(.+)", stripped, re.S)
        if negated is not None:
            inner = self.state_condition_expression(negated.group(1).strip(), call, parameters)
            if inner is not None:
                if IDENTIFIER_PATTERN.fullmatch(inner) is not None:
                    return f"!{inner}"
                return f"!({inner})"
        string_empty_call = re.fullmatch(r"(.+?)\.is(Not)?Empty\s*\(\s*\)", stripped, re.S)
        if string_empty_call is not None:
            base_expression = string_empty_call.group(1).strip()
            text_expression = self.state_field_access_expression(call, base_expression, "string", parameters)
            if text_expression is None:
                text_expression = self.value_expression(base_expression, "string", parameters)
            if text_expression is not None:
                operator = "!==" if string_empty_call.group(2) == "Not" else "==="
                return f"{text_expression} {operator} ''"
        boolean_literal_comparison = re.fullmatch(r"(.+?)\s*([!=]=)\s*(true|false)", stripped, re.S)
        if boolean_literal_comparison is not None:
            left = self.state_field_access_expression(call, boolean_literal_comparison.group(1).strip(), "boolean", parameters)
            if left is None:
                left = self.value_expression(boolean_literal_comparison.group(1).strip(), "boolean", parameters)
            if left is not None:
                operator = "!==" if boolean_literal_comparison.group(2) == "!=" else "==="
                return f"{left} {operator} {boolean_literal_comparison.group(3)}"
        null_comparison = re.fullmatch(r"(.+?)\s*([!=]=)\s*null", stripped, re.S)
        if null_comparison is not None:
            source_left = null_comparison.group(1).strip()
            local_value = self.local_value_expression(source_left, parameters)
            if local_value is not None:
                first_or_null = re.fullmatch(r"(.+?)\.firstOrNull\s*\(\s*\)", local_value, re.S)
                if first_or_null is not None:
                    collection_expression = self.value_expression(first_or_null.group(1).strip(), "unknown[]", parameters)
                    if collection_expression is not None:
                        if null_comparison.group(2) == "==":
                            return f"{collection_expression}.length === 0"
                        return f"{collection_expression}.length > 0"
            if (
                IDENTIFIER_PATTERN.fullmatch(source_left) is not None
                and isinstance(parameters.get(source_left), str)
                and parameters[source_left].endswith(" | null")
            ):
                left = source_left
                if null_comparison.group(2) == "==":
                    return f"{left} === null"
                return f"{left} !== null"
            left = self.nullable_data_class_presence_expression(source_left, parameters)
            if left is not None:
                if null_comparison.group(2) == "==":
                    return f"{left} === undefined || {left} === null"
                return f"{left} !== undefined && {left} !== null"
        string_comparison = re.fullmatch(r"(.+?)\s*([!=]=)\s*(.+)", stripped, re.S)
        if string_comparison is not None:
            left = self.state_field_access_expression(call, string_comparison.group(1).strip(), "string", parameters)
            if left is None:
                left = self.value_expression(string_comparison.group(1).strip(), "string", parameters)
            right = self.state_field_access_expression(call, string_comparison.group(3).strip(), "string", parameters)
            if right is None:
                right = self.value_expression(string_comparison.group(3).strip(), "string", parameters)
            if left is not None and right is not None:
                operator = "!==" if string_comparison.group(2) == "!=" else "==="
                return f"{left} {operator} {right}"
        state_value = self.state_field_access_expression(call, stripped, "boolean", parameters)
        if state_value is not None:
            return state_value
        return self.value_expression(stripped, "boolean", parameters)

    def visibility_condition_expression(
        self,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> str | None:
        condition = call.get("visibility_condition")
        if not isinstance(condition, dict) or not isinstance(condition.get("expression"), str):
            return None
        previous_local_values = self._current_local_values
        local_values = call.get("local_values")
        if isinstance(local_values, dict) and all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in local_values.items()
        ):
            self._current_local_values = {**previous_local_values, **local_values}
        try:
            return self.state_condition_expression(condition["expression"], call, parameters)
        finally:
            self._current_local_values = previous_local_values

    def wrap_visibility_lines(
        self,
        call: dict[str, Any],
        lines: list[str],
        indent: int,
        parameters: dict[str, str],
    ) -> list[str]:
        if not lines or "visibility_condition" not in call:
            return lines
        condition = self.visibility_condition_expression(call, parameters)
        if condition is None:
            self.add_unresolved("visibility_condition", call, "enclosing if condition is not safely translated")
            return []
        if condition == "true":
            return lines
        prefix = " " * indent
        shifted = [
            f"{prefix}  {line[len(prefix):]}" if line.startswith(prefix) else f"{prefix}  {line}"
            for line in lines
        ]
        return [f"{prefix}if ({condition}) {{", *shifted, f"{prefix}}}"]

    def data_class_property_path_expression(
        self,
        expression: str,
        target_type: str,
        parameters: dict[str, str],
    ) -> str | None:
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+", expression) is None:
            return None
        parts = expression.split(".")
        current_type = parameters.get(parts[0])
        if current_type is None:
            return None
        last_property: dict[str, Any] | None = None
        for part in parts[1:]:
            properties = self.data_class_properties_by_target.get(current_type or "")
            if properties is None:
                return None
            match = next((item for item in properties if item["name"] == part), None)
            if match is None:
                return None
            last_property = match
            current_type = match["type"]
        if (
            current_type == target_type
            or (target_type == "ResourceStr" and current_type == "string")
            or (target_type == "unknown[]" and isinstance(current_type, str) and array_element_target_type(current_type) is not None)
        ):
            if (
                last_property is not None
                and last_property.get("optional")
                and target_type in self.data_class_properties_by_target
            ):
                default_value = self.data_class_default_value_expression(target_type)
                if default_value is None:
                    return None
                return f"({expression} ?? {default_value})"
            return expression
        return None

    def nullable_data_class_presence_expression(
        self,
        expression: str,
        parameters: dict[str, str],
    ) -> str | None:
        stripped = expression.strip()
        state_value_path = re.fullmatch(
            r"([A-Za-z_][A-Za-z0-9_]*)\.value((?:\?\.|\.)[A-Za-z_][A-Za-z0-9_]*(?:(?:\?\.|\.)[A-Za-z_][A-Za-z0-9_]*)*)",
            stripped,
        )
        if state_value_path is not None:
            stripped = f"{state_value_path.group(1)}{state_value_path.group(2)}"
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:(?:\?\.|\.)[A-Za-z_][A-Za-z0-9_]*)*", stripped) is None:
            return None
        if IDENTIFIER_PATTERN.fullmatch(stripped) is not None:
            parameter_type = parameters.get(stripped)
            if isinstance(parameter_type, str) and parameter_type.endswith(" | null"):
                return stripped
            return None
        pieces = re.split(r"(\?\.|\.)", stripped)
        if len(pieces) < 3 or len(pieces) % 2 == 0:
            return None
        current_type = parameters.get(pieces[0])
        if current_type is None:
            return None
        rendered = pieces[0]
        last_property: dict[str, Any] | None = None
        for index in range(1, len(pieces), 2):
            operator = pieces[index]
            property_name = pieces[index + 1]
            properties = self.data_class_properties_by_target.get(current_type or "")
            if properties is None:
                return None
            match = next((item for item in properties if item["name"] == property_name), None)
            if match is None:
                return None
            rendered += f"{operator}{property_name}"
            current_type = match["type"]
            last_property = match
        if last_property is None:
            return None
        if last_property.get("optional") or (isinstance(current_type, str) and current_type.endswith(" | null")):
            return rendered
        return None

    def nullable_data_class_property_path_expression(
        self,
        expression: str,
        target_type: str,
        parameters: dict[str, str],
    ) -> str | None:
        stripped = expression.strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:(?:\?\.|\.)[A-Za-z_][A-Za-z0-9_]*)+", stripped) is None:
            return None
        pieces = re.split(r"(\?\.|\.)", stripped)
        if len(pieces) < 3 or len(pieces) % 2 == 0:
            return None
        current_type = parameters.get(pieces[0])
        if current_type is None:
            return None
        rendered = pieces[0]
        for index in range(1, len(pieces), 2):
            operator = pieces[index]
            property_name = pieces[index + 1]
            properties = self.data_class_properties_by_target.get(current_type or "")
            if properties is None:
                return None
            match = next((item for item in properties if item["name"] == property_name), None)
            if match is None:
                return None
            rendered += f"{operator}{property_name}"
            current_type = match["type"]
        accepted_types = {target_type}
        if target_type == "ResourceStr":
            accepted_types.add("string")
        nullable_types = {f"{item} | null" for item in accepted_types}
        if current_type in accepted_types or current_type in nullable_types:
            return rendered
        return None

    def object_literal_fields(self, expression: str) -> dict[str, str] | None:
        stripped = expression.strip()
        if not (stripped.startswith("{") and stripped.endswith("}")):
            return None
        fields: dict[str, str] = {}
        for chunk in split_arguments(stripped[1:-1]):
            match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.+)", chunk, re.S)
            if match is None:
                return None
            fields[match.group(1)] = match.group(2).strip()
        return fields

    def local_data_class_property_expression(
        self,
        expression: str,
        target_type: str,
        parameters: dict[str, str],
    ) -> str | None:
        property_access = re.fullmatch(
            r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)",
            expression.strip(),
        )
        if property_access is None:
            return None
        local_expression = self.local_value_expression(property_access.group(1), parameters)
        if local_expression is None:
            return None
        for class_name in sorted(self.data_classes):
            owner_type = self.data_class_target_type(class_name)
            if owner_type is None:
                continue
            properties = self.data_class_properties_by_target.get(owner_type, [])
            property_item = next(
                (item for item in properties if item["name"] == property_access.group(2)),
                None,
            )
            if property_item is None or not (
                property_item["type"] == target_type
                or (target_type == "ResourceStr" and property_item["type"] == "string")
            ):
                continue
            object_expression = self.data_class_value_expression(
                local_expression,
                owner_type,
                parameters,
            )
            fields = self.object_literal_fields(object_expression) if object_expression is not None else None
            if fields is not None and property_access.group(2) in fields:
                return fields[property_access.group(2)]
            collection_property = self.collection_first_property_expression(
                local_expression,
                property_access.group(2),
                target_type,
                parameters,
            )
            if collection_property is not None:
                return collection_property
        return None

    def data_class_value_expression(
        self,
        expression: str,
        target_type: str,
        parameters: dict[str, str],
    ) -> str | None:
        state_match = re.fullmatch(r"mutableStateOf\s*\((.*)\)", expression.strip(), re.S)
        if state_match is not None:
            return self.data_class_value_expression(state_match.group(1).strip(), target_type, parameters)
        for class_name, data_class in self.data_classes.items():
            if self.data_class_target_type(class_name) != target_type:
                continue
            object_match = re.fullmatch(rf"{re.escape(class_name)}\.([A-Za-z_][A-Za-z0-9_]*)", expression.strip())
            objects = data_class.get("objects")
            if object_match is not None and isinstance(objects, list):
                object_item = next(
                    (
                        item
                        for item in objects
                        if isinstance(item, dict) and item.get("name") == object_match.group(1)
                    ),
                    None,
                )
                if isinstance(object_item, dict) and isinstance(object_item.get("arguments"), list):
                    properties = self.data_class_properties_by_target[target_type]
                    fields: list[str] = []
                    for index, property_item in enumerate(properties):
                        arguments = object_item["arguments"]
                        if index >= len(arguments) or not isinstance(arguments[index], str):
                            return None
                        translated = self.value_expression(arguments[index], property_item["type"], parameters)
                        if translated is None:
                            return None
                        fields.append(f"{property_item['name']}: {translated}")
                    return "{ " + ", ".join(fields) + " }"
            factory_match = re.fullmatch(
                rf"{re.escape(class_name)}\.([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)",
                expression.strip(),
                re.S,
            )
            factories = data_class.get("factories")
            if factory_match is not None and isinstance(factories, list):
                factory = next(
                    (
                        item
                        for item in factories
                        if isinstance(item, dict) and item.get("name") == factory_match.group(1)
                    ),
                    None,
                )
                if isinstance(factory, dict) and isinstance(factory.get("return_expression"), str):
                    positional, named = named_arguments(factory_match.group(2))
                    local_values: dict[str, str] = {}
                    raw_local_values = factory.get("local_values")
                    if isinstance(raw_local_values, dict) and all(
                        isinstance(key, str) and isinstance(value, str)
                        for key, value in raw_local_values.items()
                    ):
                        local_values.update(raw_local_values)
                    factory_parameters = factory.get("parameters")
                    if isinstance(factory_parameters, list):
                        for index, parameter in enumerate(factory_parameters):
                            if not isinstance(parameter, dict) or not isinstance(parameter.get("name"), str):
                                continue
                            source = named.get(parameter["name"])
                            if source is None and index < len(positional):
                                source = positional[index]
                            if source is None and isinstance(parameter.get("default"), str):
                                source = parameter["default"]
                            if source is not None:
                                local_values[parameter["name"]] = source
                    previous_local_values = self._current_local_values
                    self._current_local_values = {**previous_local_values, **local_values}
                    try:
                        return self.data_class_value_expression(
                            factory["return_expression"],
                            target_type,
                            parameters,
                        )
                    finally:
                        self._current_local_values = previous_local_values
            match = re.fullmatch(
                rf"(?:[A-Za-z_][A-Za-z0-9_]*\.)*{re.escape(class_name)}\s*\((.*)\)",
                expression.strip(),
                re.S,
            )
            if match is None:
                continue
            positional, named = named_arguments(match.group(1))
            fields: list[str] = []
            properties = self.data_class_properties_by_target[target_type]
            for index, property_item in enumerate(properties):
                source = named.get(property_item["name"])
                if source is None and index < len(positional):
                    source = positional[index]
                if source is None and isinstance(property_item.get("default"), str):
                    source = property_item["default"]
                if source is None:
                    if property_item.get("optional"):
                        continue
                    return None
                if source.strip() == "null" and property_item.get("optional"):
                    continue
                translated = self.value_expression(source, property_item["type"], parameters)
                if translated is None:
                    return None
                fields.append(f"{property_item['name']}: {translated}")
            if not fields:
                return "{}"
            return "{ " + ", ".join(fields) + " }"
        return None

    def conditional_static_fallback_expression(
        self,
        expression: str,
        target_type: str,
        parameters: dict[str, str],
    ) -> str | None:
        elvis = split_top_level_elvis(expression)
        if elvis is not None:
            translated = self.value_expression(elvis[1], target_type, parameters)
            if translated is not None:
                return translated
        conditional = kotlin_if_else_parts(expression)
        if conditional is None:
            return None
        for branch in (conditional[2], conditional[1]):
            translated = self.value_expression(branch.strip(), target_type, parameters)
            if translated is not None:
                return translated
        return None

    def data_class_default_value_expression(self, target_type: str) -> str | None:
        properties = self.data_class_properties_by_target.get(target_type)
        if not properties:
            return None
        fields: list[str] = []
        for property_item in properties:
            if property_item.get("optional"):
                continue
            target_property_type = property_item["type"]
            if target_property_type in {"string", "ResourceStr"}:
                value = "''"
            elif target_property_type == "number":
                value = "0"
            elif target_property_type == "boolean":
                value = "false"
            elif array_element_target_type(target_property_type) is not None:
                value = "[]"
            elif target_property_type in self.data_class_properties_by_target:
                value = self.data_class_default_value_expression(target_property_type)
                if value is None:
                    return None
            else:
                return None
            fields.append(f"{property_item['name']}: {value}")
        if not fields:
            return "{}"
        return "{ " + ", ".join(fields) + " }"

    def string_resource_expression(self, expression: str, parameters: dict[str, str] | None = None) -> str | None:
        stripped = expression.strip()
        dynamic = re.fullmatch(r"UiText\.DynamicString\s*\(\s*(.+)\s*\)", stripped)
        if dynamic is not None:
            return kotlin_string(dynamic.group(1).strip())
        direct = re.fullmatch(r"R\.string\.([A-Za-z_][A-Za-z0-9_]*)", stripped)
        if direct is not None:
            name = direct.group(1)
            if f"string:{name}" not in self.resource_names:
                return None
            return f"$r('app.string.{name}')"
        resource_arg = re.fullmatch(
            r"stringResource\s*\(\s*(?:id\s*=\s*)?(.+?)\s*\)",
            stripped,
            re.S,
        )
        if resource_arg is not None and not resource_arg.group(1).strip().startswith("R.string."):
            return self.value_expression(resource_arg.group(1).strip(), "ResourceStr", parameters or {})
        name = self.string_resource_key(expression)
        if name is None:
            return None
        return f"$r('app.string.{name}')"

    def static_string_resource_replace_expression(self, expression: str) -> str | None:
        replaced = re.fullmatch(r"(.+?)\.replace\s*\((.*)\)\s*", expression.strip(), re.S)
        if replaced is None:
            return None
        key = self.string_resource_key(replaced.group(1).strip())
        if key is None or key not in self.string_values:
            return None
        positional, named = named_arguments(replaced.group(2))
        if named or len(positional) != 2:
            return None
        old = kotlin_string_value(positional[0])
        new = kotlin_string_value(positional[1])
        if old is None or new is None:
            return None
        return arkts_string(self.string_values[key].replace(old, new))

    def string_resource_key(self, expression: str) -> str | None:
        stripped = expression.strip()
        resource = re.fullmatch(
            r"(?:stringResource|UiText\.StringResource)\s*\(\s*"
            r"(?:[A-Za-z_][A-Za-z0-9_]*\s*=\s*)?"
            r"R\.string\.([A-Za-z_][A-Za-z0-9_]*)\s*\)",
            stripped,
        )
        if resource is None:
            return None
        name = resource.group(1)
        if f"string:{name}" not in self.resource_names:
            return None
        return name

    def dimension_expression(
        self,
        expression: str,
        parameters: dict[str, str],
        *,
        allow_constraint_fill: bool = False,
    ) -> str | None:
        stripped = expression.strip()
        inline_parameter_value = self._current_parameter_values.get(stripped)
        if (
            inline_parameter_value is not None
            and IDENTIFIER_PATTERN.fullmatch(stripped) is not None
        ):
            translated = self.dimension_expression(
                inline_parameter_value,
                parameters,
                allow_constraint_fill=allow_constraint_fill,
            )
            if translated is not None:
                return translated
            return inline_parameter_value.strip()
        if allow_constraint_fill and parameters.get(stripped) == "constraint_dimension":
            return "'100%'"
        if parameters.get(stripped) == "number":
            return stripped
        screen_width_minus = re.fullmatch(
            r"LocalConfiguration\.current\.screenWidthDp\.dp\s*-\s*([0-9]+(?:\.[0-9]+)?)\.dp",
            stripped,
        )
        if screen_width_minus is not None:
            return f"'calc(100% - {screen_width_minus.group(1)}vp)'"
        arithmetic = re.fullmatch(
            r"(-?)\s*([A-Za-z_][A-Za-z0-9_]*)\s*([*/])\s*([0-9]+(?:\.[0-9]+)?)(?:[fFdD])?",
            stripped,
        )
        if arithmetic is not None and arithmetic.group(2) in self.dimension_token_values:
            computed = decimal_binary(
                self.dimension_token_values[arithmetic.group(2)],
                arithmetic.group(3),
                arithmetic.group(4),
            )
            if computed is not None:
                return f"-{computed}" if arithmetic.group(1) else computed
        if arithmetic is not None and parameters.get(arithmetic.group(2)) == "number":
            sign = "-" if arithmetic.group(1) else ""
            return f"{sign}{arithmetic.group(2)} {arithmetic.group(3)} {arithmetic.group(4)}"
        token_arithmetic = re.fullmatch(
            r"(-?)\s*([A-Za-z_][A-Za-z0-9_]*)\s*([*/])\s*([A-Za-z_][A-Za-z0-9_]*)",
            stripped,
        )
        if token_arithmetic is not None:
            left = token_arithmetic.group(2)
            operator = token_arithmetic.group(3)
            right = token_arithmetic.group(4)
            computed = None
            if left in self.dimension_token_values and right in self.number_token_values:
                computed = decimal_binary(
                    self.dimension_token_values[left],
                    operator,
                    self.number_token_values[right],
                )
            elif operator == "*" and left in self.number_token_values and right in self.dimension_token_values:
                computed = decimal_binary(
                    self.number_token_values[left],
                    operator,
                    self.dimension_token_values[right],
                )
            if computed is not None:
                return f"-{computed}" if token_arithmetic.group(1) else computed
        if IDENTIFIER_PATTERN.fullmatch(stripped) is not None:
            resource = f"compose_dimension_{snake_name(stripped)}"
            if resource in self.resource_names:
                return f"$r('app.float.{resource}')"
        return dimension_value(stripped)

    def modifier_dimension_expression(
        self,
        expression: str,
        parameters: dict[str, str],
        *,
        allow_constraint_fill: bool = False,
    ) -> str | None:
        value = self.dimension_expression(
            expression,
            parameters,
            allow_constraint_fill=allow_constraint_fill,
        )
        if value is not None:
            return value
        stripped = expression.strip()
        if parameters.get(stripped) == "number | undefined":
            return stripped
        return None

    def rounded_corner_radius_expression(
        self,
        expression: str,
        parameters: dict[str, str],
    ) -> str | None:
        resolved = self.current_parameter_default_expression(expression, parameters)
        if resolved == "CircleShape":
            return "'50%'"
        custom_corner = re.fullmatch(r"(?:[A-Za-z_][A-Za-z0-9_]*\.)*CustomCornerShape\s*\((.*)\)", resolved, re.S)
        if custom_corner is not None:
            positional, named = named_arguments(custom_corner.group(1))
            allowed = ("topLeft", "topRight", "bottomLeft", "bottomRight")
            if positional or set(named) - set(allowed):
                return None
            values: list[str] = []
            for key in allowed:
                if key not in named:
                    continue
                radius = self.dimension_expression(named[key], parameters)
                if radius is None:
                    return None
                values.append(f"{key}: {radius}")
            return "{ " + ", ".join(values) + " }" if values else None
        match = re.fullmatch(r"RoundedCornerShape\s*\((.*)\)", resolved, re.S)
        if match is None and parameters.get(resolved) == "number":
            return resolved
        if match is None and parameters.get(resolved) == "number | null":
            return f"({resolved} ?? 0)"
        if match is None:
            return None
        positional, named = named_arguments(match.group(1))
        if len(positional) == 1 and not named:
            dimension = self.dimension_expression(positional[0], parameters)
            if dimension is not None:
                return dimension
            percent = re.fullmatch(r"([0-9]|[1-9][0-9]|100)", positional[0].strip())
            if percent is not None:
                return f"'{percent.group(1)}%'"
            return None
        if not positional and set(named) == {"size"}:
            return self.dimension_expression(named["size"], parameters)
        return None

    def outlined_text_field_border_line(
        self,
        semantic: dict[str, Any],
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> tuple[str | None, bool]:
        colors = semantic.get("colors")
        colors_expression = colors.get("resolved_local_expression") if isinstance(colors, dict) else None
        if not isinstance(colors_expression, str) and isinstance(colors, dict):
            colors_expression = colors.get("expression")
        if not isinstance(colors_expression, str):
            if "compose_theme_outline" not in self.resource_names:
                return None, False
            normal_color = "$r('app.color.compose_theme_outline')"
        else:
            resolved_colors = self.current_parameter_default_expression(colors_expression, parameters)
            colors_match = re.fullmatch(
                r"(?:OutlinedTextFieldDefaults|TextFieldDefaults)\.(?:colors|outlinedTextFieldColors)\s*\((.*)\)",
                resolved_colors.strip(),
                re.S,
            )
            if colors_match is None:
                return None, False
            _positional, named = named_arguments(colors_match.group(1))
            focused_source = named.get("focusedBorderColor")
            unfocused_source = named.get("unfocusedBorderColor")
            normal_source = unfocused_source or focused_source
            if normal_source is None:
                return None, False
            normal_color = self.color_expression(normal_source, call, parameters)
            if normal_color is None:
                self.add_unresolved("text_field_border_color", call, "outlined text field normal border color is not safely translated")
                return None, False
            if focused_source is not None and unfocused_source is not None and focused_source.strip() != unfocused_source.strip():
                self.add_unresolved("text_field_focus_border_color", call, "outlined text field focused/unfocused border colors require focus-state reconciliation")

        is_error = semantic.get("isError")
        is_error_expression = is_error.get("expression") if isinstance(is_error, dict) else None
        if not isinstance(is_error_expression, str) or is_error_expression.strip() == "false":
            return f".border({{ width: 1, color: {normal_color} }})", True
        error_source = named.get("errorBorderColor") if isinstance(colors_expression, str) else "MaterialTheme.colorScheme.error"
        if error_source is None:
            self.add_unresolved("text_field_error_border_color", call, "outlined text field error border color is not explicitly translated")
            return f".border({{ width: 1, color: {normal_color} }})", False
        error_condition = self.state_condition_expression(is_error_expression, call, parameters)
        error_color = self.color_expression(error_source, call, parameters)
        if error_condition is None or error_color is None:
            self.add_unresolved("text_field_error_border_color", call, "outlined text field error border color is not safely translated")
            return f".border({{ width: 1, color: {normal_color} }})", False
        return f".border({{ width: 1, color: ({error_condition} ? {error_color} : {normal_color}) }})", True

    def outlined_text_field_has_unsupported_decoration(
        self,
        semantic: dict[str, Any],
        *,
        password_trailing_icon_handled: bool = False,
        supporting_text_handled: bool = False,
    ) -> bool:
        unsupported = {"leadingIcon", "trailingIcon", "prefix", "suffix", "supportingText"}
        if password_trailing_icon_handled:
            unsupported.remove("trailingIcon")
        if supporting_text_handled:
            unsupported.remove("supportingText")
        return any(name in semantic for name in unsupported)

    def password_visibility_security_state(
        self,
        semantic: dict[str, Any],
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> tuple[str, bool] | None:
        visual = semantic.get("visualTransformation")
        visual_expression = visual.get("expression") if isinstance(visual, dict) else None
        if not isinstance(visual_expression, str):
            return None
        conditional = kotlin_if_else_parts(visual_expression)
        if conditional is None:
            return None
        condition, true_branch, false_branch = conditional
        true_type = self.input_type_expression(true_branch, parameters)
        false_type = self.input_type_expression(false_branch, parameters)
        if {true_type, false_type} != {"InputType.Password", "InputType.Normal"}:
            return None
        condition_text = condition.strip()
        negated = False
        negated_match = re.fullmatch(r"!\s*(.+)", condition_text, re.S)
        if negated_match is not None:
            negated = True
            condition_text = negated_match.group(1).strip()
        state_match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\.value", condition_text)
        if state_match is None:
            return None
        state_name = state_match.group(1)
        trailing = semantic.get("trailingIcon")
        trailing_expression = trailing.get("expression") if isinstance(trailing, dict) else None
        if not isinstance(trailing_expression, str):
            return None
        toggle_pattern = (
            r"IconButton\s*\(\s*onClick\s*=\s*\{\s*"
            + re.escape(state_name)
            + r"\.value\s*=\s*!\s*"
            + re.escape(state_name)
            + r"\.value\s*\}"
        )
        if re.search(toggle_pattern, trailing_expression, re.S) is None:
            return None
        if "Icons.Default.Visibility" not in trailing_expression:
            return None
        state_field = self.state_field_expression(call, state_name, "boolean", parameters)
        if state_field is None:
            return None
        password_when_condition_true = true_type == "InputType.Password"
        state_represents_hidden = (not password_when_condition_true) if negated else password_when_condition_true
        return state_field, state_represents_hidden

    def border_stroke_line(
        self,
        expression: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> str | None:
        match = re.fullmatch(r"BorderStroke\s*\((.*)\)", expression.strip(), re.S)
        if match is None:
            return None
        positional, named = named_arguments(match.group(1))
        width_source = named.get("width") or (positional[0] if len(positional) >= 1 else None)
        color_source = named.get("color") or (positional[1] if len(positional) >= 2 else None)
        if width_source is None or color_source is None:
            return None
        width = self.dimension_expression(width_source, parameters)
        color = self.color_expression(color_source, call, parameters)
        if width is None or color is None:
            return None
        return f".border({{ width: {width}, color: {color} }})"

    def surface_style_lines(
        self,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> tuple[list[str], bool]:
        previous_local_values = self._current_local_values
        local_values = call.get("local_values")
        if isinstance(local_values, dict) and all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in local_values.items()
        ):
            self._current_local_values = {**previous_local_values, **local_values}
        try:
            return self._surface_style_lines(call, parameters)
        finally:
            self._current_local_values = previous_local_values

    def _surface_style_lines(
        self,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> tuple[list[str], bool]:
        semantic = call.get("semantic_arguments")
        if not isinstance(semantic, dict):
            return [], False
        supported = {"color", "shape", "border", "shadowElevation"}
        fully_handled = not (set(semantic) - supported)
        lines: list[str] = []
        color = semantic.get("color")
        if isinstance(color, dict):
            expression = color.get("expression")
            translated = self.color_expression(str(expression or ""), call, parameters)
            if translated is None:
                fully_handled = False
            else:
                lines.append(f".backgroundColor({translated})")
        shape = semantic.get("shape")
        if isinstance(shape, dict):
            expression = shape.get("expression")
            radius = self.rounded_corner_radius_expression(str(expression or ""), parameters)
            if radius is None:
                fully_handled = False
            else:
                lines.append(f".borderRadius({radius})")
        border = semantic.get("border")
        if isinstance(border, dict):
            expression = border.get("expression")
            border_line = self.border_stroke_line(str(expression or ""), call, parameters)
            if border_line is None:
                fully_handled = False
            else:
                lines.append(border_line)
        shadow = semantic.get("shadowElevation")
        if isinstance(shadow, dict):
            expression = shadow.get("expression")
            elevation = self.numeric_value_expression(str(expression or ""), call, parameters)
            if elevation is None:
                fully_handled = False
            else:
                lines.append(f".shadow({{ radius: {elevation}, color: '#33000000', offsetY: {elevation} }})")
        return lines, bool(lines) and fully_handled

    def top_app_bar_style_lines(
        self,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> list[str]:
        previous_local_values = self._current_local_values
        local_values = call.get("local_values")
        if isinstance(local_values, dict) and all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in local_values.items()
        ):
            self._current_local_values = {**previous_local_values, **local_values}
        try:
            semantic = call.get("semantic_arguments")
            if not isinstance(semantic, dict):
                return []
            lines: list[str] = []
            colors = semantic.get("colors")
            colors_expression = colors.get("expression") if isinstance(colors, dict) else None
            if isinstance(colors_expression, str):
                resolved = self.current_parameter_default_expression(colors_expression, parameters)
                match = re.fullmatch(r"TopAppBarDefaults\.topAppBarColors\s*\((.*)\)", resolved.strip(), re.S)
                if match is not None:
                    positional, named = named_arguments(match.group(1))
                    color_source = named.get("containerColor") or (positional[0] if positional else None)
                    color = self.color_expression(color_source, call, parameters) if color_source is not None else None
                    if color is not None:
                        lines.append(f".backgroundColor({color})")
            expanded_height = semantic.get("expandedHeight")
            expanded_height_expression = expanded_height.get("expression") if isinstance(expanded_height, dict) else None
            if isinstance(expanded_height_expression, str):
                height = self.dimension_expression(expanded_height_expression, parameters)
                if height is not None:
                    lines.append(f".height({height})")
            return lines
        finally:
            self._current_local_values = previous_local_values

    def top_app_bar_defaults_supported(
        self,
        call: dict[str, Any],
        parameters: dict[str, str],
        style_lines: list[str],
    ) -> bool:
        semantic = call.get("semantic_arguments")
        if not isinstance(semantic, dict):
            return False
        allowed = {"title", "navigationIcon", "actions", "colors", "expandedHeight"}
        if any(name not in allowed for name in semantic):
            return False
        if "colors" in semantic and not any(line.startswith(".backgroundColor(") for line in style_lines):
            return False
        expanded_height = semantic.get("expandedHeight")
        expanded_height_expression = expanded_height.get("expression") if isinstance(expanded_height, dict) else None
        if isinstance(expanded_height_expression, str) and self.dimension_expression(expanded_height_expression, parameters) is None:
            return False
        return True

    def card_style_lines(
        self,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> tuple[list[str], bool]:
        previous_local_values = self._current_local_values
        local_values = call.get("local_values")
        if isinstance(local_values, dict) and all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in local_values.items()
        ):
            self._current_local_values = {**previous_local_values, **local_values}
        try:
            semantic = call.get("semantic_arguments")
            if not isinstance(semantic, dict):
                return [], False
            supported = {"colors", "shape"}
            fully_handled = not (set(semantic) - supported)
            lines: list[str] = []
            colors = semantic.get("colors")
            colors_expression = colors.get("expression") if isinstance(colors, dict) else None
            if isinstance(colors_expression, str):
                resolved = self.current_parameter_default_expression(colors_expression, parameters)
                match = re.fullmatch(r"CardDefaults\.cardColors\s*\((.*)\)", resolved.strip(), re.S)
                if match is None:
                    fully_handled = False
                else:
                    positional, named = named_arguments(match.group(1))
                    color_source = named.get("containerColor") or (positional[0] if positional else None)
                    color = self.color_expression(color_source, call, parameters) if color_source is not None else None
                    if color is None:
                        fully_handled = False
                    else:
                        lines.append(f".backgroundColor({color})")
            shape = semantic.get("shape")
            shape_expression = shape.get("expression") if isinstance(shape, dict) else None
            if isinstance(shape_expression, str):
                radius = self.rounded_corner_radius_expression(shape_expression, parameters)
                if radius is None:
                    fully_handled = False
                else:
                    lines.append(f".borderRadius({radius})")
            return lines, bool(lines) and fully_handled
        finally:
            self._current_local_values = previous_local_values

    def numeric_value_expression(
        self,
        expression: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> str | None:
        literal = number_value(expression) or dimension_value(expression)
        if literal is not None:
            return literal
        conditional = kotlin_if_else_parts(expression)
        if conditional is None:
            return None
        condition, true_branch, false_branch = conditional
        condition_expression = self.state_condition_expression(condition, call, parameters)
        true_value = number_value(true_branch) or dimension_value(true_branch)
        false_value = number_value(false_branch) or dimension_value(false_branch)
        if condition_expression is None or true_value is None or false_value is None:
            return None
        return f"({condition_expression} ? {true_value} : {false_value})"

    def opacity_expression(
        self,
        expression: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> str | None:
        direct = self.numeric_value_expression(expression, call, parameters)
        if direct is not None:
            return direct
        state_value = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\.value", expression.strip())
        if state_value is None:
            return None
        local_expression = self.local_value_expression(state_value.group(1), parameters)
        if local_expression is None:
            return None
        animated = re.fullmatch(r"animateFloatAsState\s*\((.*)\)\s*", local_expression.strip(), re.S)
        if animated is None:
            return None
        positional, named = named_arguments(animated.group(1))
        target_value = named.get("targetValue") or (positional[0] if positional else None)
        if target_value is None:
            return None
        return self.numeric_value_expression(target_value, call, parameters)

    def resolved_modifier_chain_expression(
        self,
        expression: str,
        call: dict[str, Any],
        parameters: dict[str, str],
        *,
        depth: int = 0,
    ) -> list[dict[str, Any]] | None:
        if depth > 8:
            return None
        stripped = expression.strip()
        if stripped == "Modifier":
            return []
        local_expression = self.local_value_expression(stripped, parameters)
        if local_expression is not None and local_expression.strip() != stripped:
            return self.resolved_modifier_chain_expression(
                local_expression,
                call,
                parameters,
                depth=depth + 1,
            )
        direct = modifier_chain_expression(stripped)
        if direct:
            return direct
        conditional = kotlin_if_else_parts(stripped)
        if conditional is None:
            return None
        condition, true_branch, false_branch = conditional
        condition_expression = self.value_expression(condition, "boolean", parameters)
        if condition_expression == "true":
            return self.resolved_modifier_chain_expression(true_branch, call, parameters, depth=depth + 1)
        if condition_expression == "false":
            return self.resolved_modifier_chain_expression(false_branch, call, parameters, depth=depth + 1)
        return None

    def conditional_scroll_variants_for_expression(
        self,
        expression: str,
        call: dict[str, Any],
        parameters: dict[str, str],
        *,
        depth: int = 0,
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]] | None:
        if depth > 8:
            return None
        stripped = expression.strip()
        local_expression = self.local_value_expression(stripped, parameters)
        if local_expression is not None and local_expression.strip() != stripped:
            return self.conditional_scroll_variants_for_expression(
                local_expression,
                call,
                parameters,
                depth=depth + 1,
            )
        direct = modifier_chain_expression(stripped)
        if direct:
            return self.conditional_scroll_variants(direct, call, parameters, depth=depth + 1)
        conditional = kotlin_if_else_parts(stripped)
        if conditional is None:
            return None
        condition, true_branch, false_branch = conditional
        condition_expression = self.value_expression(condition, "boolean", parameters)
        if condition_expression is None:
            return None
        true_chain = self.resolved_modifier_chain_expression(true_branch, call, parameters, depth=depth + 1)
        false_chain = self.resolved_modifier_chain_expression(false_branch, call, parameters, depth=depth + 1)
        if true_chain is None or false_chain is None:
            return None
        true_scroll = chain_has_supported_scroll(true_chain)
        false_scroll = chain_has_supported_scroll(false_chain)
        if true_scroll == false_scroll:
            return None
        return condition_expression, true_chain, false_chain

    def conditional_scroll_variants(
        self,
        chain: list[Any],
        call: dict[str, Any],
        parameters: dict[str, str],
        *,
        depth: int = 0,
    ) -> tuple[str, list[Any], list[Any]] | None:
        if depth > 8:
            return None
        for index, modifier in enumerate(chain):
            if not isinstance(modifier, dict) or modifier.get("name") != "then":
                continue
            arguments = modifier.get("resolved_arguments") if isinstance(modifier.get("resolved_arguments"), str) else modifier.get("arguments")
            if not isinstance(arguments, str):
                continue
            variants = self.conditional_scroll_variants_for_expression(
                arguments,
                call,
                parameters,
                depth=depth + 1,
            )
            if variants is None:
                continue
            condition, true_chain, false_chain = variants
            return (
                condition,
                [*chain[:index], *true_chain, *chain[index + 1 :]],
                [*chain[:index], *false_chain, *chain[index + 1 :]],
            )
        return None

    def modifier_lines(
        self,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> list[str]:
        previous_local_values = self._current_local_values
        local_values = call.get("local_values")
        if isinstance(local_values, dict) and all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in local_values.items()
        ):
            self._current_local_values = local_values
        chain = call.get("ordered_modifier_chain")
        if not isinstance(chain, list):
            raise ArkUIPageError("ordered modifier chain is invalid")
        lines: list[str] = []
        for index, modifier in enumerate(chain):
            if not isinstance(modifier, dict) or not isinstance(modifier.get("name"), str) or not isinstance(modifier.get("arguments"), str):
                raise ArkUIPageError("ordered modifier entry is invalid")
            name = modifier["name"]
            arguments_source = modifier.get("resolved_arguments") if isinstance(modifier.get("resolved_arguments"), str) else modifier["arguments"]
            arguments = arguments_source.strip()
            positional, named = named_arguments(arguments)
            if self.android_page_overrides_modifier(
                call, name, positional, named
            ):
                continue
            if name in {"width", "height", "requiredWidth", "requiredHeight"}:
                target_name = {
                    "requiredWidth": "width",
                    "requiredHeight": "height",
                }.get(name, name)
                value = (
                    self.modifier_dimension_expression(positional[0], parameters, allow_constraint_fill=True)
                    if len(positional) == 1
                    else None
                )
                if value is not None:
                    lines.append(f".{target_name}({value})")
                    continue
                if name == "height" and len(positional) == 1 and positional[0].strip() in {"IntrinsicSize.Max", "IntrinsicSize.Min"}:
                    continue
            elif name == "size":
                value = (
                    self.modifier_dimension_expression(positional[0], parameters, allow_constraint_fill=True)
                    if len(positional) == 1
                    else None
                )
                if value is not None:
                    lines.extend((f".width({value})", f".height({value})"))
                    continue
                width_value = (
                    self.modifier_dimension_expression(named["width"], parameters, allow_constraint_fill=True)
                    if "width" in named
                    else None
                )
                height_value = (
                    self.modifier_dimension_expression(named["height"], parameters, allow_constraint_fill=True)
                    if "height" in named
                    else None
                )
                if width_value is not None or height_value is not None:
                    if width_value is not None:
                        lines.append(f".width({width_value})")
                    if height_value is not None:
                        lines.append(f".height({height_value})")
                    continue
            elif name == "fillMaxWidth" and not arguments:
                lines.append(".width('100%')")
                continue
            elif name == "fillMaxHeight" and not arguments:
                lines.append(".height('100%')")
                continue
            elif name == "fillMaxSize" and not arguments:
                lines.extend((".width('100%')", ".height('100%')"))
                continue
            elif name in {"wrapContentWidth", "wrapContentHeight", "wrapContentSize"}:
                if not arguments:
                    continue
                if name == "wrapContentHeight" and not positional and set(named) <= {"unbounded", "align"}:
                    align = named.get("align")
                    unbounded = named.get("unbounded")
                    if (align is None or align.strip().startswith("Alignment.")) and (
                        unbounded is None or unbounded.strip() in {"true", "false"}
                    ):
                        content_height = self.android_page_unbounded_content_height(
                            call,
                            self.children_for(call),
                            parameters,
                        )
                        if content_height is not None:
                            lines.append(f".height({decimal_literal(content_height)})")
                        continue
            elif name == "matchParentSize" and not arguments:
                lines.extend((".width('100%')", ".height('100%')"))
                continue
            elif name == "focusRequester":
                continue
            elif name == "imePadding" and not arguments:
                continue
            elif name == "animateContentSize" and not arguments:
                continue
            elif name in {"widthIn", "requiredWidthIn", "heightIn", "sizeIn"}:
                constraint_values: list[str] = []
                if name in {"widthIn", "requiredWidthIn"}:
                    min_source = named.get("min") or (positional[0] if len(positional) >= 1 else None)
                    max_source = named.get("max") or (positional[1] if len(positional) >= 2 else None)
                    if min_source is not None:
                        min_value = self.dimension_expression(min_source, parameters)
                        if min_value is not None:
                            constraint_values.append(f"minWidth: {min_value}")
                    if max_source is not None:
                        max_value = self.dimension_expression(max_source, parameters)
                        if max_value is not None:
                            constraint_values.append(f"maxWidth: {max_value}")
                elif name == "heightIn":
                    min_source = named.get("min") or (positional[0] if len(positional) >= 1 else None)
                    max_source = named.get("max") or (positional[1] if len(positional) >= 2 else None)
                    if min_source is not None:
                        min_value = self.dimension_expression(min_source, parameters)
                        if min_value is not None:
                            constraint_values.append(f"minHeight: {min_value}")
                    if max_source is not None:
                        max_value = self.dimension_expression(max_source, parameters)
                        if max_value is not None:
                            constraint_values.append(f"maxHeight: {max_value}")
                else:
                    for source_name, target_name in (
                        ("minWidth", "minWidth"),
                        ("minHeight", "minHeight"),
                        ("maxWidth", "maxWidth"),
                        ("maxHeight", "maxHeight"),
                    ):
                        source = named.get(source_name)
                        if source is None:
                            continue
                        value = self.dimension_expression(source, parameters)
                        if value is not None:
                            constraint_values.append(f"{target_name}: {value}")
                if constraint_values:
                    lines.append(f".constraintSize({{ {', '.join(constraint_values)} }})")
                    continue
            elif name == "alpha":
                opacity = self.opacity_expression(positional[0], call, parameters) if len(positional) == 1 else None
                if opacity is not None:
                    lines.append(f".opacity({opacity})")
                    continue
            elif name == "hitTestBehavior":
                conditional = kotlin_if_else_parts(arguments)
                if conditional is not None:
                    condition, true_branch, false_branch = conditional
                    condition_expression = self.value_expression(condition, "boolean", parameters)
                    if (
                        condition_expression is not None
                        and true_branch.strip() in {"HitTestMode.Block", "HitTestMode.Transparent"}
                        and false_branch.strip() in {"HitTestMode.Block", "HitTestMode.Transparent"}
                    ):
                        lines.append(
                            f".hitTestBehavior(({condition_expression} ? {true_branch.strip()} : {false_branch.strip()}))"
                        )
                        continue
            elif name == "pointerInput":
                trailing_lambda = modifier.get("trailing_lambda")
                if isinstance(trailing_lambda, str) and commentless_kotlin_block_body(trailing_lambda) == "":
                    lines.append(".hitTestBehavior(HitTestMode.Block)")
                    continue
                if (
                    isinstance(trailing_lambda, str)
                    and re.fullmatch(r"\{\s*detectTapGestures\s*\{\s*\}\s*\}", trailing_lambda.strip(), re.S) is not None
                ):
                    lines.append(".hitTestBehavior(HitTestMode.Block)")
                    continue
                if (
                    isinstance(trailing_lambda, str)
                    and re.fullmatch(
                        r"\{\s*detectTapGestures\s*\(\s*onTap\s*=\s*\{\s*[A-Za-z_][A-Za-z0-9_]*\.clearFocus\s*\(\s*\)\s*\}\s*,?\s*\)\s*\}",
                        trailing_lambda.strip(),
                        re.S,
                    )
                    is not None
                ):
                    lines.append(".onClick(() => { this.getUIContext().getFocusController().clearFocus() })")
                    continue
            elif name == "aspectRatio":
                ratio_source = named.get("ratio") or (positional[0] if len(positional) >= 1 else None)
                ratio = number_or_boolean_conditional_value(ratio_source, parameters) if ratio_source else None
                if ratio is not None and set(named) <= {"ratio", "matchHeightConstraintsFirst"}:
                    match_height = named.get("matchHeightConstraintsFirst") or (
                        positional[1] if len(positional) >= 2 else None
                    )
                    if match_height is None or match_height.strip() == "false":
                        lines.append(f".aspectRatio({ratio})")
                        continue
            elif name == "offset":
                x_source = named.get("x") or (positional[0] if len(positional) >= 1 else None)
                y_source = named.get("y") or (positional[1] if len(positional) >= 2 else None)
                x_value = self.dimension_expression(x_source, parameters) if x_source is not None else None
                y_value = self.dimension_expression(y_source, parameters) if y_source is not None else None
                translate_values: list[str] = []
                if x_value is not None:
                    translate_values.append(f"x: {x_value}")
                if y_value is not None:
                    translate_values.append(f"y: {y_value}")
                if translate_values:
                    lines.append(f".translate({{ {', '.join(translate_values)} }})")
                    continue
            elif name == "rotate":
                angle = number_value(positional[0]) if len(positional) == 1 else None
                if angle is not None:
                    lines.append(f".rotate({{ angle: {angle} }})")
                    continue
            elif name == "align":
                alignment = positional[0].strip() if len(positional) == 1 else ""
                alignment_map = {
                    "Alignment.TopStart": "Alignment.TopStart",
                    "Alignment.TopCenter": "Alignment.Top",
                    "Alignment.TopEnd": "Alignment.TopEnd",
                    "Alignment.CenterStart": "Alignment.Start",
                    "Alignment.Center": "Alignment.Center",
                    "Alignment.CenterEnd": "Alignment.End",
                    "Alignment.BottomStart": "Alignment.BottomStart",
                    "Alignment.BottomCenter": "Alignment.Bottom",
                    "Alignment.BottomEnd": "Alignment.BottomEnd",
                }
                mapped_alignment = alignment_map.get(alignment)
                if mapped_alignment is not None:
                    lines.append(f".align({mapped_alignment})")
                    continue
            elif name == "clickable":
                callback_source = named.get("onClick") or (positional[0] if len(positional) == 1 else None)
                if callback_source and commentless_kotlin_block_body(callback_source) == "":
                    lines.append(".onClick(() => {})")
                    continue
                callback = (
                    self.state_field_set_callback_expression(callback_source, call, parameters)
                    if callback_source
                    else None
                )
                if callback is None and callback_source:
                    callback = self.value_expression(callback_source, "() => void", parameters)
                if callback == "() => {}":
                    lines.append(".onClick(() => {})")
                    continue
                if callback is not None and IDENTIFIER_PATTERN.fullmatch(callback) is not None:
                    lines.append(f".onClick(() => {{ {callback}() }})")
                    continue
                if callback is not None:
                    lines.append(f".onClick({callback})")
                    continue
                callback_name = self.nullable_callback_name(callback_source or "", parameters)
                if callback_name is not None:
                    lines.append(f".onClick(() => {{ if ({callback_name} !== null) {{ {callback_name}() }} }})")
                    continue
            elif name == "padding":
                padding = self.padding_expression(positional, named, parameters)
                if padding is not None:
                    lines.append(f".padding({padding})")
                    continue
            elif name == "background":
                color_source = named.get("color") or (positional[0] if positional else None)
                shape_source = named.get("shape") or (positional[1] if len(positional) >= 2 else None)
                color = self.color_expression(color_source, call, parameters) if color_source else None
                if color is not None:
                    lines.append(f".backgroundColor({color})")
                    if shape_source is not None:
                        radius = self.rounded_corner_radius_expression(shape_source, parameters)
                        if radius is not None:
                            lines.append(f".borderRadius({radius})")
                    continue
                brush_source = named.get("brush") or (positional[0] if positional else None)
                gradient_line = self.linear_gradient_line(brush_source, call, parameters) if brush_source else None
                if gradient_line is not None:
                    lines.append(gradient_line)
                    if shape_source is not None:
                        radius = self.rounded_corner_radius_expression(shape_source, parameters)
                        if radius is not None:
                            lines.append(f".borderRadius({radius})")
                    continue
            elif name == "border":
                width_source = named.get("width") or (positional[0] if len(positional) >= 1 else None)
                color_source = named.get("color") or (positional[1] if len(positional) >= 2 else None)
                shape_source = named.get("shape") or (positional[2] if len(positional) >= 3 else None)
                if shape_source is None and "width" in named and "color" in named and len(positional) == 1:
                    shape_source = positional[0]
                width = self.dimension_expression(width_source, parameters) if width_source is not None else None
                color = self.color_expression(color_source, call, parameters) if color_source is not None else None
                if width is not None and color is not None:
                    lines.append(f".border({{ width: {width}, color: {color} }})")
                    if shape_source is not None:
                        radius = self.rounded_corner_radius_expression(shape_source, parameters)
                        if radius is None:
                            self.add_unresolved(
                                "modifier",
                                call,
                                f"Modifier.{name} shape at chain index {index} is not safely translated",
                                modifier_index=index,
                                arguments=arguments,
                            )
                        else:
                            lines.append(f".borderRadius({radius})")
                    continue
            elif name == "dashedBorder":
                width_source = named.get("strokeWidth") or (positional[0] if len(positional) >= 1 else None)
                color_source = named.get("color") or (positional[1] if len(positional) >= 2 else None)
                radius_source = named.get("cornerRadiusDp") or (positional[2] if len(positional) >= 3 else None)
                width = self.dimension_expression(width_source, parameters) if width_source is not None else None
                color = self.color_expression(color_source, call, parameters) if color_source is not None else None
                radius = self.dimension_expression(radius_source, parameters) if radius_source is not None else None
                if width is not None and color is not None and radius is not None:
                    lines.append(
                        f".border({{ width: {width}, color: {color}, style: BorderStyle.Dashed, dashGap: 10, dashWidth: 10 }})"
                    )
                    lines.append(f".borderRadius({radius})")
                    continue
            elif name == "clip":
                radius = self.rounded_corner_radius_expression(arguments, parameters)
                if radius is not None:
                    lines.append(f".borderRadius({radius})")
                    continue
            elif name == "roundedBorder":
                radius_source = named.get("radius") or (positional[0] if positional else "16.dp")
                color_source = named.get("color") or (positional[1] if len(positional) >= 2 else None)
                radius = self.rounded_corner_radius_expression(radius_source, parameters) if radius_source is not None else None
                if radius is None and radius_source is not None:
                    radius = self.dimension_expression(radius_source, parameters)
                if color_source is None:
                    color = (
                        "$r('app.color.compose_extended_color_primary_border')"
                        if "compose_extended_color_primary_border" in self.resource_names
                        else None
                    )
                else:
                    color = self.color_expression(color_source, call, parameters)
                if radius is not None and color is not None:
                    lines.append(f".border({{ width: 1, color: {color} }})")
                    lines.append(f".borderRadius({radius})")
                    continue
            elif name == "then":
                nested = modifier_chain_expression(arguments)
                if nested:
                    nested_call = dict(call)
                    nested_call["ordered_modifier_chain"] = nested
                    lines.extend(self.modifier_lines(nested_call, parameters))
                    continue
                conditional_lines = self.conditional_then_modifier_lines(arguments, call, parameters)
                if conditional_lines is not None:
                    lines.extend(conditional_lines)
                    continue
                local_expression = self.local_value_expression(arguments, parameters)
                if local_expression is not None:
                    nested = modifier_chain_expression(local_expression)
                    if nested:
                        nested_call = dict(call)
                        nested_call["ordered_modifier_chain"] = nested
                        lines.extend(self.modifier_lines(nested_call, parameters))
                        continue
                    conditional_lines = self.conditional_then_modifier_lines(local_expression, call, parameters)
                    if conditional_lines is not None:
                        lines.extend(conditional_lines)
                        continue
                if IDENTIFIER_PATTERN.fullmatch(arguments) is not None and parameters.get(arguments) == "Modifier":
                    continue
            elif name == "let":
                nested = modifier_let_conditional_modifier_expression(arguments)
                if nested:
                    nested_call = dict(call)
                    nested_call["ordered_modifier_chain"] = nested
                    lines.extend(self.modifier_lines(nested_call, parameters))
                    continue
            elif name == "weight":
                value = positional[0].strip() if len(positional) == 1 else ""
                weight = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)[fF]?", value)
                if weight is not None:
                    lines.append(f".layoutWeight({weight.group(1)})")
                    continue
            self.add_unresolved(
                "modifier",
                call,
                f"Modifier.{name} at chain index {index} is not safely translated",
                modifier_index=index,
                arguments=arguments,
            )
        self._current_local_values = previous_local_values
        return lines

    def conditional_then_modifier_lines(
        self,
        expression: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> list[str] | None:
        conditional = kotlin_if_else_parts(expression)
        if conditional is None:
            return None
        condition, true_branch, false_branch = conditional
        condition_expression = self.value_expression(condition, "boolean", parameters)
        if condition_expression is None:
            return None
        true_modifier = modifier_chain_expression(true_branch)
        false_modifier = modifier_chain_expression(false_branch)
        if len(true_modifier) == 1 and not false_modifier:
            modifier = true_modifier[0]
            apply_when_true = True
        elif not true_modifier and len(false_modifier) == 1:
            modifier = false_modifier[0]
            apply_when_true = False
        else:
            return None
        if modifier.get("name") != "padding" or not isinstance(modifier.get("arguments"), str):
            if modifier.get("name") == "clickable" and isinstance(modifier.get("arguments"), str):
                line = self.conditional_nullable_clickable_line(
                    modifier["arguments"],
                    condition_expression,
                    apply_when_true,
                    parameters,
                )
                return [line] if line is not None else None
            return None
        positional, named = named_arguments(modifier["arguments"])
        padding = self.conditional_padding_expression(positional, named, condition_expression, apply_when_true, parameters)
        if padding is None:
            return None
        return [f".padding({padding})"]

    def nullable_callback_name(self, expression: str, parameters: dict[str, str]) -> str | None:
        stripped = expression.strip()
        direct_call = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*\)", stripped)
        if direct_call is not None and parameters.get(direct_call.group(1)) == "(() => void) | null":
            return direct_call.group(1)
        wrapped_call = re.fullmatch(r"\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*\)\s*\}", stripped)
        if wrapped_call is not None and parameters.get(wrapped_call.group(1)) == "(() => void) | null":
            return wrapped_call.group(1)
        invoke_call = re.fullmatch(r"\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*invoke\s*\(\s*\)\s*\}", stripped)
        if invoke_call is not None and parameters.get(invoke_call.group(1)) == "(() => void) | null":
            return invoke_call.group(1)
        if IDENTIFIER_PATTERN.fullmatch(stripped) is not None and parameters.get(stripped) == "(() => void) | null":
            return stripped
        return None

    def conditional_nullable_clickable_line(
        self,
        arguments: str,
        condition_expression: str,
        apply_when_true: bool,
        parameters: dict[str, str],
    ) -> str | None:
        positional, named = named_arguments(arguments)
        callback_source = named.get("onClick") or (positional[0] if len(positional) == 1 else arguments)
        callback_name = self.nullable_callback_name(callback_source, parameters)
        if callback_name is None:
            return None
        expected = f"{callback_name} !== null" if apply_when_true else f"{callback_name} === null"
        if condition_expression != expected:
            return None
        return f".onClick(() => {{ if ({callback_name} !== null) {{ {callback_name}() }} }})"

    def conditional_padding_expression(
        self,
        positional: list[str],
        named: dict[str, str],
        condition_expression: str,
        apply_when_true: bool,
        parameters: dict[str, str],
    ) -> str | None:
        def conditional_value(source: str) -> str | None:
            value = self.padding_dimension_expression(source, parameters)
            if value is None:
                return None
            if apply_when_true:
                return f"({condition_expression} ? {value} : 0)"
            return f"({condition_expression} ? 0 : {value})"

        if len(positional) == 1 and not named:
            return conditional_value(positional[0])
        allowed = {"all", "horizontal", "vertical", "start", "end", "top", "bottom"}
        if positional or set(named) - allowed:
            return None
        values: dict[str, str] = {}
        if "all" in named:
            value = conditional_value(named["all"])
            if value is None:
                return None
            return f"{{ left: {value}, right: {value}, top: {value}, bottom: {value} }}"
        horizontal = conditional_value(named["horizontal"]) if "horizontal" in named else None
        vertical = conditional_value(named["vertical"]) if "vertical" in named else None
        if "horizontal" in named and horizontal is None:
            return None
        if "vertical" in named and vertical is None:
            return None
        if horizontal is not None:
            values.update({"left": horizontal, "right": horizontal})
        if vertical is not None:
            values.update({"top": vertical, "bottom": vertical})
        for source, target in (("start", "left"), ("end", "right"), ("top", "top"), ("bottom", "bottom")):
            if source in named:
                value = conditional_value(named[source])
                if value is None:
                    return None
                values[target] = value
        if not values:
            return None
        order = ("left", "right", "top", "bottom")
        return "{ " + ", ".join(f"{name}: {values[name]}" for name in order if name in values) + " }"

    def callback_change_line(
        self,
        expression: str,
        parameters: dict[str, str],
    ) -> str | None:
        stripped = expression.strip()
        if stripped in {"{}", "{ }"}:
            return ".onChange((value: string): void => {})"
        if callback_parameter_types(parameters.get(stripped)) == ["string"]:
            return f".onChange((value: string): void => {{ {stripped}(value) }})"
        callback = re.fullmatch(r"\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*it\s*\)\s*\}", stripped)
        if callback is None:
            callback = re.fullmatch(
                r"\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*invoke\s*\(\s*it\s*\)\s*\}",
                stripped,
            )
        if callback is not None and callback_parameter_types(parameters.get(callback.group(1))) == ["string"]:
            name = callback.group(1)
            return f".onChange((value: string): void => {{ {name}(value) }})"
        return None

    def callback_click_line(
        self,
        expression: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> str | None:
        previous_local_values = self._current_local_values
        local_values = call.get("local_values")
        if isinstance(local_values, dict) and all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in local_values.items()
        ):
            self._current_local_values = {**previous_local_values, **local_values}
        nav_back = self.nav_controller_back_callback_expression(expression)
        try:
            if nav_back is not None:
                return f".onClick({nav_back})"
            translated = self.value_expression(expression, "() => void", parameters)
            if translated is None:
                return None
            if IDENTIFIER_PATTERN.fullmatch(translated) is not None and parameters.get(translated) == "() => void":
                return f".onClick(() => {{ {translated}() }})"
            return f".onClick({translated})"
        finally:
            self._current_local_values = previous_local_values

    def nav_controller_back_callback_expression(self, expression: str) -> str | None:
        stripped = expression.strip()
        target: str | None = None
        single_click = re.fullmatch(r"singleClick\s*\(\s*onClick\s*=\s*([A-Za-z_][A-Za-z0-9_]*)::popBackStack\s*\)", stripped)
        if single_click is not None:
            target = single_click.group(1)
        direct_ref = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)::popBackStack", stripped)
        if target is None and direct_ref is not None:
            target = direct_ref.group(1)
        lambda_call = re.fullmatch(r"\{\s*([A-Za-z_][A-Za-z0-9_]*)\.popBackStack\s*\(\s*\)\s*\}", stripped)
        if target is None and lambda_call is not None:
            target = lambda_call.group(1)
        if target is None or not target.lower().endswith("navcontroller"):
            return None
        return "() => { this.getUIContext().getRouter().back() }"

    def text_slot_value_expression(
        self,
        expression: str,
        parameters: dict[str, str],
    ) -> str | None:
        stripped = expression.strip()
        local_expression = self.local_value_expression(stripped, parameters)
        if local_expression is not None:
            return self.text_slot_value_expression(local_expression, parameters)
        invoke_match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\?\.invoke\s*\(\s*\)", stripped)
        if invoke_match is not None:
            local_slot = self.local_value_expression(invoke_match.group(1), parameters)
            if local_slot is not None:
                return self.text_slot_value_expression(local_slot, parameters)
        lambda_match = re.fullmatch(r"\{\s*(.+?)\s*\}", stripped, re.S)
        body = lambda_match.group(1).strip() if lambda_match is not None else stripped
        while body.startswith("{") and body.endswith("}"):
            candidate = body[1:-1].strip()
            if not candidate:
                break
            body = candidate
        text_match = re.fullmatch(r"Text\s*\((.*)\)\s*", body, re.S)
        if text_match is None:
            return None
        positional, named = named_arguments(text_match.group(1))
        text_expression = named.get("text")
        if text_expression is None and positional:
            text_expression = positional[0]
        if text_expression is None:
            return None
        translated = self.value_expression(text_expression, "ResourceStr", parameters)
        if translated is not None:
            return translated
        return self.value_expression(text_expression, "string", parameters)

    def supporting_text_lines(
        self,
        expression: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> list[str] | None:
        translated = self.text_slot_value_expression(expression, parameters)
        if translated is not None:
            return [
                f"Text({translated})",
                "  .margin({ top: 4 })",
            ]
        stripped = expression.strip()
        local_expression = self.local_value_expression(stripped, parameters)
        if local_expression is not None:
            return self.supporting_text_lines(local_expression, call, parameters)
        lambda_match = re.fullmatch(r"\{\s*(.+?)\s*\}", stripped, re.S)
        body = lambda_match.group(1).strip() if lambda_match is not None else stripped
        single_branch = re.fullmatch(r"if\s*\((.+)\)\s*\{\s*(.+)\s*\}", body, re.S)
        if single_branch is not None:
            condition_expression = self.state_condition_expression(single_branch.group(1).strip(), call, parameters)
            translated_branch = self.text_slot_value_expression(single_branch.group(2).strip(), parameters)
            if condition_expression is not None and translated_branch is not None:
                return [
                    f"if ({condition_expression}) {{",
                    f"  Text({translated_branch})",
                    "    .margin({ top: 4 })",
                    "}",
                ]
        conditional = kotlin_if_else_parts(body)
        if conditional is None:
            return None
        condition, true_branch, false_branch = conditional
        condition_expression = self.state_condition_expression(condition, call, parameters)
        if condition_expression is None:
            return None
        true_text = self.text_slot_value_expression(true_branch, parameters)
        false_text = self.text_slot_value_expression(false_branch, parameters)
        if true_text is not None and false_branch.strip() in {"null", "{ }", "{}"}:
            return [
                f"if ({condition_expression}) {{",
                f"  Text({true_text})",
                "    .margin({ top: 4 })",
                "}",
            ]
        if false_text is not None and true_branch.strip() in {"null", "{ }", "{}"}:
            negated = condition_expression[1:] if condition_expression.startswith("!") else f"!({condition_expression})"
            return [
                f"if ({negated}) {{",
                f"  Text({false_text})",
                "    .margin({ top: 4 })",
                "}",
            ]
        return None

    def build_annotated_string_expression(
        self,
        expression: str,
        target_type: str,
        parameters: dict[str, str],
    ) -> str | None:
        match = re.fullmatch(r"buildAnnotatedString\s*\{(.*)\}\s*", expression.strip(), re.S)
        if match is None:
            return None
        body = match.group(1)
        arguments: list[str] = []
        index = 0
        while index < len(body):
            call = re.search(r"\bappend\s*\(", body[index:])
            if call is None:
                break
            start = index + call.end()
            depth = 1
            quote: str | None = None
            escaped = False
            cursor = start
            while cursor < len(body):
                character = body[cursor]
                if quote is not None:
                    if escaped:
                        escaped = False
                    elif character == "\\":
                        escaped = True
                    elif character == quote:
                        quote = None
                    cursor += 1
                    continue
                if character in {'"', "'"}:
                    quote = character
                elif character in "([{<":
                    depth += 1
                elif character in ")]}>":
                    depth -= 1
                    if depth == 0:
                        break
                cursor += 1
            if depth != 0:
                return None
            argument = body[start:cursor].strip()
            if len(split_arguments(argument)) != 1:
                return None
            arguments.append(argument)
            index = cursor + 1
        if not arguments:
            return None
        translated_parts: list[str] = []
        for argument in arguments:
            translated = self.value_expression(argument, target_type, parameters)
            if translated is None:
                return None
            translated_parts.append(translated)
        return " + ".join(translated_parts)

    def build_annotated_string_spans(
        self,
        expression: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> list[tuple[str, list[str]]] | None:
        match = re.fullmatch(r"buildAnnotatedString\s*\{(.*)\}\s*", expression.strip(), re.S)
        if match is None:
            return None
        body = match.group(1)
        styled_regions: list[tuple[int, int, str]] = []
        search_from = 0
        while True:
            style_call = re.search(r"\bwithStyle\s*\(", body[search_from:])
            if style_call is None:
                break
            opening = search_from + style_call.end() - 1
            closing = closing_parenthesis(body, opening)
            if closing is None:
                return None
            body_opening = closing + 1
            while body_opening < len(body) and body[body_opening].isspace():
                body_opening += 1
            if body_opening >= len(body) or body[body_opening] != "{":
                return None
            body_closing = closing_brace(body, body_opening)
            if body_closing is None:
                return None
            positional, named = named_arguments(body[opening + 1 : closing])
            style_expression = named.get("style") or (positional[0] if len(positional) == 1 else None)
            if style_expression is None:
                return None
            styled_regions.append((body_opening + 1, body_closing, style_expression))
            search_from = body_closing + 1

        spans: list[tuple[str, list[str]]] = []
        search_from = 0
        while True:
            append_call = re.search(r"\bappend\s*\(", body[search_from:])
            if append_call is None:
                break
            opening = search_from + append_call.end() - 1
            closing = closing_parenthesis(body, opening)
            if closing is None:
                return None
            argument = body[opening + 1 : closing].strip()
            if len(split_arguments(argument)) != 1:
                return None
            translated = self.value_expression(argument, "string", parameters)
            if translated is None:
                return None
            containing = [
                region
                for region in styled_regions
                if region[0] <= opening and closing <= region[1]
            ]
            style_lines: list[str] = []
            if containing:
                _, _, style_expression = min(
                    containing,
                    key=lambda region: region[1] - region[0],
                )
                resolved_style = self.current_parameter_default_expression(
                    style_expression,
                    parameters,
                )
                rendered_style = self.inline_text_style_lines(
                    resolved_style,
                    call,
                    parameters,
                )
                if rendered_style is None:
                    return None
                style_lines = rendered_style
            spans.append((translated, style_lines))
            search_from = closing + 1
        return spans or None

    def enabled_line(
        self,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> str | None:
        semantic = call.get("semantic_arguments", {})
        enabled = semantic.get("enabled") if isinstance(semantic, dict) else None
        enabled_expression = enabled.get("expression") if isinstance(enabled, dict) else None
        if not isinstance(enabled_expression, str):
            return None
        translated = self.value_expression(enabled_expression, "boolean", parameters)
        if translated is None:
            self.add_unresolved("semantic_argument", call, "enabled expression is not safely translated")
            return None
        return f".enabled({translated})"

    def text_button_defaults_supported(self, children: list[dict[str, Any]]) -> bool:
        return bool(children) and all(
            isinstance(child, dict) and child.get("component") in {"Text", "BasicText"}
            for child in children
        )

    def icon_button_defaults_supported(self, children: list[dict[str, Any]]) -> bool:
        return bool(children) and all(
            isinstance(child, dict) and child.get("component") in {"Icon", "Image", "Text", "BasicText"}
            for child in children
        )

    def calls_reference_constraint_parameters(self, calls: list[dict[str, Any]]) -> bool:
        stack = list(calls)
        while stack:
            call = stack.pop()
            if re.search(r"\bmax(?:Width|Height)\b", json.dumps(call, ensure_ascii=False)):
                return True
            stack.extend(self.children_for(call))
        return False

    def constraint_parameter_references_supported(self, calls: list[dict[str, Any]]) -> bool:
        stack = list(calls)
        while stack:
            call = stack.pop()
            shallow = {
                key: value
                for key, value in call.items()
                if key not in {"children", "ordered_modifier_chain"}
            }
            if re.search(r"\bmax(?:Width|Height)\b", json.dumps(shallow, ensure_ascii=False)):
                return False
            chain = call.get("ordered_modifier_chain")
            if isinstance(chain, list):
                for modifier in chain:
                    if not isinstance(modifier, dict):
                        return False
                    arguments = modifier.get("resolved_arguments") if isinstance(modifier.get("resolved_arguments"), str) else modifier.get("arguments")
                    if not isinstance(arguments, str) or re.search(r"\bmax(?:Width|Height)\b", arguments) is None:
                        continue
                    name = modifier.get("name")
                    expected = {
                        "width": "maxWidth",
                        "requiredWidth": "maxWidth",
                        "height": "maxHeight",
                        "requiredHeight": "maxHeight",
                    }.get(name)
                    if expected is None or arguments.strip() != expected:
                        return False
            stack.extend(self.children_for(call))
        return True

    def box_with_constraints_defaults_supported(self, children: list[dict[str, Any]]) -> bool:
        return self.constraint_parameter_references_supported(children)

    def animated_visibility_defaults_supported(
        self,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> bool:
        semantic = call.get("semantic_arguments", {})
        if not isinstance(semantic, dict):
            return False
        visible = semantic.get("visible")
        visible_expression = visible.get("expression") if isinstance(visible, dict) else None
        if isinstance(visible, dict) and isinstance(visible.get("resolved_local_expression"), str):
            visible_expression = visible["resolved_local_expression"]
        if not isinstance(visible_expression, str):
            return False
        if self.state_condition_expression(visible_expression, call, parameters) is None:
            return False
        if set(semantic) - {"visible", "enter", "exit"}:
            return False
        enter = semantic.get("enter")
        enter_expression = enter.get("expression") if isinstance(enter, dict) else None
        if isinstance(enter_expression, str) and not self.fade_transition_expression_supported(enter_expression, "fadeIn"):
            return False
        exit = semantic.get("exit")
        exit_expression = exit.get("expression") if isinstance(exit, dict) else None
        if isinstance(exit_expression, str) and not self.fade_transition_expression_supported(exit_expression, "fadeOut"):
            return False
        return True

    def fade_transition_expression_supported(self, expression: str, function_name: str) -> bool:
        transition = re.fullmatch(rf"{re.escape(function_name)}\s*\((.*)\)", expression.strip(), re.S)
        if transition is None:
            return False
        arguments = transition.group(1).strip()
        if not arguments:
            return True
        positional, named = named_arguments(arguments)
        animation_spec = named.get("animationSpec") or (positional[0] if len(positional) == 1 else None)
        if animation_spec is None or set(named) - {"animationSpec"}:
            return False
        return re.fullmatch(
            r"tween\s*\(\s*(?:durationMillis\s*=\s*)?[0-9]+(?:\s*,\s*)?\)",
            animation_spec.strip(),
            re.S,
        ) is not None

    def lazy_list_defaults_supported(
        self,
        component: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> bool:
        semantic = call.get("semantic_arguments", {})
        if not isinstance(semantic, dict):
            return False
        arrangement_name = "verticalArrangement" if component == "LazyColumn" else "horizontalArrangement"
        allowed = {arrangement_name, "contentPadding", "state"}
        if any(name not in allowed for name in semantic):
            return False
        if arrangement_name in semantic and self.arrangement_space(component, call, parameters) is None:
            return False
        content_padding = semantic.get("contentPadding")
        content_padding_expression = content_padding.get("expression") if isinstance(content_padding, dict) else None
        if isinstance(content_padding_expression, str) and self.padding_values_expression(content_padding_expression, parameters) is None:
            return False
        state = semantic.get("state")
        state_expression = state.get("resolved_local_expression") if isinstance(state, dict) and isinstance(state.get("resolved_local_expression"), str) else None
        if state_expression is None:
            state_expression = state.get("expression") if isinstance(state, dict) else None
        if isinstance(state_expression, str) and re.fullmatch(r"rememberLazyListState\s*\(\s*\)", state_expression.strip()) is None:
            return False
        return True

    def lazy_list_style_lines(self, call: dict[str, Any], parameters: dict[str, str]) -> list[str]:
        semantic = call.get("semantic_arguments", {})
        if not isinstance(semantic, dict):
            return []
        content_padding = semantic.get("contentPadding")
        content_padding_expression = content_padding.get("expression") if isinstance(content_padding, dict) else None
        if not isinstance(content_padding_expression, str):
            return []
        padding = self.padding_values_expression(content_padding_expression, parameters)
        return [f".padding({padding})"] if padding is not None else []

    def scaffold_defaults_supported(self, call: dict[str, Any]) -> bool:
        semantic = call.get("semantic_arguments", {})
        if not isinstance(semantic, dict) or semantic:
            return False
        trailing_parameters = call.get("trailing_lambda_parameters")
        if not isinstance(trailing_parameters, list):
            return False
        return not trailing_parameters or (
            len(trailing_parameters) == 1
            and isinstance(trailing_parameters[0], str)
            and IDENTIFIER_PATTERN.fullmatch(trailing_parameters[0]) is not None
        )

    def button_style_lines(self, component: str, call: dict[str, Any], parameters: dict[str, str]) -> list[str]:
        semantic = call.get("semantic_arguments", {})
        if not isinstance(semantic, dict):
            return []
        lines: list[str] = []
        colors = semantic.get("colors")
        colors_expression = colors.get("expression") if isinstance(colors, dict) else None
        if isinstance(colors_expression, str):
            color_lines = self.button_color_lines(colors_expression, call, parameters)
            if color_lines is not None:
                lines.extend(color_lines)
            else:
                self.add_unresolved("semantic_argument", call, "button container color is not safely translated")
        if component == "TextButton" and not any(line.startswith(".backgroundColor(") for line in lines):
            lines.append(".backgroundColor('#00000000')")
        if (
            component == "TextButton"
            and not any(line.startswith(".fontColor(") for line in lines)
            and "compose_theme_primary" in self.resource_names
        ):
            lines.append(".fontColor($r('app.color.compose_theme_primary'))")
        if component == "IconButton" and not any(line.startswith(".backgroundColor(") for line in lines):
            lines.append(".backgroundColor('#00000000')")
        if component == "IconButton" and not any(line.startswith(".borderRadius(") for line in lines):
            lines.append(".borderRadius('50%')")
        if (
            component == "IconButton"
            and self.android_page_component(call) is None
            and not any(
                isinstance(item, dict)
                and item.get("name")
                in {"width", "requiredWidth", "height", "requiredHeight", "size", "requiredSize"}
                for item in call.get("ordered_modifier_chain", [])
            )
        ):
            lines.extend([".width(48)", ".height(48)"])
        shape = semantic.get("shape")
        shape_expression = shape.get("expression") if isinstance(shape, dict) else None
        if isinstance(shape_expression, str):
            radius = self.rounded_corner_radius_expression(shape_expression, parameters)
            if radius is not None:
                lines.append(f".borderRadius({radius})")
            else:
                self.add_unresolved("semantic_argument", call, "button shape is not a supported rounded corner shape")
        content_padding = semantic.get("contentPadding")
        content_padding_expression = content_padding.get("expression") if isinstance(content_padding, dict) else None
        if isinstance(content_padding_expression, str):
            padding = self.padding_values_expression(content_padding_expression, parameters)
            if padding is not None:
                lines.append(f".padding({padding})")
            else:
                self.add_unresolved("semantic_argument", call, "button contentPadding is not safely translated")
        elif component == "TextButton":
            lines.append(".padding({ left: 12, right: 12, top: 8, bottom: 8 })")
        return lines

    def button_fallback_label_expression(
        self,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> str | None:
        slot = call.get("slot_invocation")
        slot_name = slot.get("name") if isinstance(slot, dict) else None
        if isinstance(slot_name, str) and slot_name in self._current_slot_contexts:
            slot_children, _, _, slot_parameters = self._current_slot_contexts[slot_name]
            for slot_child in slot_children:
                label = self.button_fallback_label_expression(slot_child, slot_parameters)
                if label is not None:
                    return label
            return None
        component = call.get("component")
        semantic = call.get("semantic_arguments", {})
        expression: str | None = None
        if component in {"Text", "BasicText", "ClickableText"} and isinstance(semantic, dict):
            text = semantic.get("text")
            if isinstance(text, dict):
                resolved_expression = text.get("resolved_local_expression")
                if isinstance(resolved_expression, str):
                    expression = resolved_expression
                elif isinstance(text.get("expression"), str):
                    expression = text["expression"]
        if component in {"Image", "Icon"}:
            if isinstance(semantic, dict):
                description = semantic.get("contentDescription")
                if isinstance(description, dict):
                    resolved_expression = description.get("resolved_local_expression")
                    if isinstance(resolved_expression, str):
                        expression = resolved_expression
                    elif isinstance(description.get("expression"), str):
                        expression = description["expression"]
            if expression is None:
                positional = call.get("positional_arguments")
                if isinstance(positional, list) and len(positional) >= 2 and isinstance(positional[1], dict):
                    resolved_expression = positional[1].get("resolved_local_expression")
                    if isinstance(resolved_expression, str):
                        expression = resolved_expression
                    elif isinstance(positional[1].get("expression"), str):
                        expression = positional[1]["expression"]
        if not isinstance(expression, str) or expression.strip() == "null":
            return None
        translated = self.call_aware_value_expression(expression, "ResourceStr", call, parameters)
        if translated is not None:
            return translated
        return self.call_aware_value_expression(expression, "string", call, parameters)

    def button_fallback_content_lines(
        self,
        children: list[dict[str, Any]],
        indent: int,
        parameters: dict[str, str],
    ) -> list[str] | None:
        for child in children:
            label = self.button_fallback_label_expression(child, parameters)
            if label is not None:
                prefix = " " * indent
                return [f"{prefix}Text({label})"]
        return None

    def button_color_lines(
        self,
        expression: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> list[str] | None:
        resolved = self.current_parameter_default_expression(expression, parameters)
        match = re.fullmatch(r"ButtonDefaults\.[A-Za-z_][A-Za-z0-9_]*Colors\s*\((.*)\)", resolved, re.S)
        if match is None:
            return None
        positional, named = named_arguments(match.group(1))
        lines: list[str] = []
        color_source = named.get("containerColor") or named.get("backgroundColor")
        if color_source is None and positional:
            color_source = positional[0]
        if color_source is not None:
            color = self.color_expression(color_source, call, parameters)
            if color is None:
                self.add_unresolved("semantic_argument", call, "button container color is not safely translated")
            else:
                lines.append(f".backgroundColor({color})")
        content_source = named.get("contentColor")
        if content_source is not None:
            content_color = self.color_expression(content_source, call, parameters)
            if content_color is None:
                self.add_unresolved("semantic_argument", call, "button content color is not safely translated")
            else:
                lines.append(f".fontColor({content_color})")
        return lines

    def current_parameter_default_expression(self, expression: str, parameters: dict[str, str]) -> str:
        stripped = expression.strip()
        if IDENTIFIER_PATTERN.fullmatch(stripped) is None or stripped in parameters:
            return stripped
        local_expression = self.local_value_expression(stripped, parameters)
        if local_expression is not None:
            return local_expression.strip()
        default_expression = self._current_parameter_defaults.get(stripped)
        return default_expression.strip() if isinstance(default_expression, str) else stripped

    def unique_incoming_parameter_expression(self, parameter_name: str) -> str | None:
        if self._current_definition_key is None:
            return None
        values: set[str] = set()
        for incoming in self.incoming_project_calls.get(self._current_definition_key, []):
            custom = incoming.get("custom_composable")
            arguments = custom.get("arguments") if isinstance(custom, dict) else None
            caller_key = (incoming.get("source"), incoming.get("composable"))
            if not isinstance(arguments, list) or caller_key not in self.definitions:
                continue
            expression = next(
                (
                    argument.get("expression")
                    for argument in arguments
                    if isinstance(argument, dict) and argument.get("name") == parameter_name
                ),
                None,
            )
            if not isinstance(expression, str):
                continue
            stripped = expression.strip()
            if IDENTIFIER_PATTERN.fullmatch(stripped) is not None:
                caller_parameter = next(
                    (
                        item
                        for item in self.definitions[caller_key]["parameters"]
                        if isinstance(item, dict) and item.get("name") == stripped
                    ),
                    None,
                )
                caller_default = caller_parameter.get("default") if isinstance(caller_parameter, dict) else None
                if isinstance(caller_default, str):
                    stripped = caller_default.strip()
            values.add(stripped)
        return next(iter(values)) if len(values) == 1 else None

    def basic_text_field_decoration_lines(
        self,
        children: list[dict[str, Any]],
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> list[str]:
        decoration_boxes = [child for child in children if child.get("component") == "DecorationBox"]
        if len(decoration_boxes) != 1:
            return []
        semantic = decoration_boxes[0].get("semantic_arguments")
        content_padding = semantic.get("contentPadding") if isinstance(semantic, dict) else None
        expression = content_padding.get("expression") if isinstance(content_padding, dict) else None
        if not isinstance(expression, str):
            return []
        resolved = self.current_parameter_default_expression(expression, parameters)
        match = re.fullmatch(r"PaddingValues\s*\((.*)\)", resolved, re.S)
        if match is None:
            return []
        positional, named = named_arguments(match.group(1))
        if positional:
            return []
        horizontal = self.dimension_expression(named.get("horizontal", ""), parameters)
        vertical = self.dimension_expression(named.get("vertical", ""), parameters)
        start = self.dimension_expression(named.get("start", named.get("left", "")), parameters)
        end = self.dimension_expression(named.get("end", named.get("right", "")), parameters)
        top = self.dimension_expression(named.get("top", ""), parameters)
        bottom = self.dimension_expression(named.get("bottom", ""), parameters)
        left = start or horizontal
        right = end or horizontal
        top = top or vertical
        bottom = bottom or vertical
        if None in {left, right, top, bottom}:
            self.add_unresolved(
                "component_semantics",
                call,
                "DecorationBox contentPadding is not fully resolved",
            )
            return []
        if self.android_page_input is not None and top == bottom:
            vertical_value = decimal_from_literal(top)
            if vertical_value is not None and vertical_value >= 1:
                top = decimal_literal(vertical_value - 1)
                bottom = decimal_literal(vertical_value + 1)
        lines = [f".padding({{ left: {left}, right: {right}, top: {top}, bottom: {bottom} }})"]

        colors = semantic.get("colors") if isinstance(semantic, dict) else None
        colors_expression = colors.get("expression") if isinstance(colors, dict) else None
        if isinstance(colors_expression, str):
            resolved_colors = self.unique_incoming_parameter_expression(colors_expression.strip())
            if resolved_colors is None:
                resolved_colors = self.current_parameter_default_expression(colors_expression, parameters)
            colors_match = re.fullmatch(
                r"(?:OutlinedTextFieldDefaults|TextFieldDefaults)\.colors\s*\((.*)\)",
                resolved_colors,
                re.S,
            )
            if colors_match is not None:
                color_positional, color_named = named_arguments(colors_match.group(1))
                if not color_positional:
                    background_source = (
                        color_named.get("unfocusedContainerColor")
                        or color_named.get("containerColor")
                    )
                    indicator_source = color_named.get("unfocusedIndicatorColor")
                    if background_source is not None:
                        background = self.color_expression(background_source, call, parameters)
                        if background is not None:
                            lines.append(f".backgroundColor({background})")
                            if indicator_source is not None:
                                indicator = self.color_expression(indicator_source, call, parameters)
                                if indicator == background:
                                    lines.append(".border({ width: 0 })")
                                elif indicator is not None:
                                    lines.append(f".border({{ width: 1, color: {indicator} }})")

        shape_expression = self.unique_incoming_parameter_expression("shape")
        if shape_expression is None:
            shape_expression = self._current_parameter_defaults.get("shape")
        if isinstance(shape_expression, str):
            radius = self.rounded_corner_radius_expression(shape_expression, parameters)
            if radius is not None:
                lines.append(f".borderRadius({radius})")

        text_style = call.get("semantic_arguments", {}).get("textStyle")
        text_style_expression = text_style.get("expression") if isinstance(text_style, dict) else None
        resolved_style = (
            self.current_parameter_default_expression(text_style_expression, parameters)
            if isinstance(text_style_expression, str)
            else ""
        )
        style_match = re.fullmatch(r"TextStyle\s*\((.*)\)", resolved_style, re.S)
        style_named = named_arguments(style_match.group(1))[1] if style_match is not None else {}
        line_height = self.dimension_expression(style_named.get("lineHeight", ""), parameters)
        numeric_top = decimal_from_literal(top)
        numeric_bottom = decimal_from_literal(bottom)
        numeric_line_height = decimal_from_literal(line_height) if line_height is not None else None
        if numeric_top is not None and numeric_bottom is not None and numeric_line_height is not None:
            height = numeric_top + numeric_bottom + numeric_line_height + Decimal(4)
            lines.append(f".height({decimal_literal(height)})")
        lines.append(".showPasswordIcon(false)")
        return lines

    def local_value_expression(self, expression: str, parameters: dict[str, str]) -> str | None:
        stripped = expression.strip()
        if IDENTIFIER_PATTERN.fullmatch(stripped) is None or stripped in parameters:
            return None
        value = self._current_local_values.get(stripped)
        if not isinstance(value, str) or value.strip() == stripped:
            return None
        return value

    def input_type_expression(self, expression: str, parameters: dict[str, str]) -> str | None:
        stripped = self.current_parameter_default_expression(expression, parameters)
        if parameters.get(stripped) == "InputType":
            return stripped
        conditional = kotlin_if_else_parts(stripped)
        if conditional is not None:
            condition, true_branch, false_branch = conditional
            condition_expression = self.value_expression(condition, "boolean", parameters)
            true_type = self.input_type_expression(true_branch, parameters)
            false_type = self.input_type_expression(false_branch, parameters)
            if condition_expression is not None and true_type is not None and false_type is not None:
                return f"({condition_expression} ? {true_type} : {false_type})"
        mapping = {
            "KeyboardType.Text": "InputType.Normal",
            "KeyboardType.Number": "InputType.Number",
            "KeyboardType.Decimal": "InputType.NUMBER_DECIMAL",
            "KeyboardType.Phone": "InputType.PhoneNumber",
            "KeyboardType.Email": "InputType.Email",
            "KeyboardType.Password": "InputType.Password",
            "KeyboardType.NumberPassword": "InputType.NUMBER_PASSWORD",
        }
        if stripped in mapping:
            return mapping[stripped]
        if stripped == "KeyboardOptions.Default":
            return "InputType.Normal"
        if stripped == "VisualTransformation.None":
            return "InputType.Normal"
        if re.fullmatch(r"PasswordVisualTransformation\s*\(\s*\)", stripped):
            return "InputType.Password"
        match = re.fullmatch(r"KeyboardOptions\s*\((.*)\)", stripped, re.S)
        if match is None:
            return None
        positional, named = named_arguments(match.group(1))
        if positional:
            return None
        keyboard_type = named.get("keyboardType")
        if keyboard_type is None:
            return "InputType.Normal"
        return self.input_type_expression(keyboard_type, parameters)

    def input_type_parameter_default_is_normal(
        self,
        expression: str | None,
        parameters: dict[str, str],
    ) -> bool:
        if expression is None:
            return False
        stripped = expression.strip()
        if IDENTIFIER_PATTERN.fullmatch(stripped) is None or parameters.get(stripped) != "InputType":
            return False
        default_expression = self._current_parameter_defaults.get(stripped)
        if not isinstance(default_expression, str):
            return False
        return self.input_type_expression(default_expression, parameters) == "InputType.Normal"

    def padding_values_expression(self, expression: str, parameters: dict[str, str]) -> str | None:
        stripped = expression.strip()
        if parameters.get(stripped) == "Padding":
            return stripped
        if parameters.get(stripped) == "PaddingZero":
            return "{ left: 0, right: 0, top: 0, bottom: 0 }"
        match = re.fullmatch(r"PaddingValues\s*\((.*)\)", stripped, re.S)
        if match is None:
            return None
        arguments = match.group(1).strip()
        if not arguments:
            return "{}"
        positional, named = named_arguments(arguments)
        padding = self.padding_expression(positional, named, parameters)
        if padding is None:
            return None
        if re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", padding) is not None:
            return f"{{ left: {padding}, right: {padding}, top: {padding}, bottom: {padding} }}"
        return padding

    def padding_expression(
        self,
        positional: list[str],
        named: dict[str, str],
        parameters: dict[str, str],
    ) -> str | None:
        if len(positional) == 1 and not named:
            value = positional[0].strip()
            if parameters.get(value) == "Padding":
                return value
            if parameters.get(value) == "PaddingZero":
                return "{ left: 0, right: 0, top: 0, bottom: 0 }"
            return dimension_value(value)
        allowed = {"all", "horizontal", "vertical", "start", "end", "top", "bottom"}
        if positional or set(named) - allowed:
            return None
        if "all" in named:
            return self.padding_dimension_expression(named["all"], parameters)
        values: dict[str, str] = {}
        horizontal = self.padding_dimension_expression(named["horizontal"], parameters) if "horizontal" in named else None
        vertical = self.padding_dimension_expression(named["vertical"], parameters) if "vertical" in named else None
        if "horizontal" in named and horizontal is None:
            return None
        if "vertical" in named and vertical is None:
            return None
        if horizontal is not None:
            values.update({"left": horizontal, "right": horizontal})
        if vertical is not None:
            values.update({"top": vertical, "bottom": vertical})
        for source, target in (("start", "left"), ("end", "right"), ("top", "top"), ("bottom", "bottom")):
            if source in named:
                value = self.padding_dimension_expression(named[source], parameters)
                if value is None:
                    return None
                values[target] = value
        if not values:
            return None
        order = ("left", "right", "top", "bottom")
        return "{ " + ", ".join(f"{name}: {values[name]}" for name in order if name in values) + " }"

    def padding_dimension_expression(self, expression: str, parameters: dict[str, str]) -> str | None:
        literal = dimension_value(expression)
        if literal is not None:
            return literal
        stripped = expression.strip()
        added = split_top_level_operator(stripped, "+")
        if added is not None:
            left = self.padding_dimension_expression(added[0], parameters)
            right = self.padding_dimension_expression(added[1], parameters)
            if left is not None and right is not None:
                return f"{left} + {right}"
        if parameters.get(stripped) == "number":
            return stripped
        match = re.fullmatch(
            r"([A-Za-z_][A-Za-z0-9_]*)\.calculate(Top|Bottom|Start|End)Padding\s*\(\s*\)(?:\s*\+\s*(.+))?",
            stripped,
            re.S,
        )
        if match is None or parameters.get(match.group(1)) not in {"Padding", "PaddingZero"}:
            return None
        side = {
            "Top": "top",
            "Bottom": "bottom",
            "Start": "left",
            "End": "right",
        }[match.group(2)]
        if parameters.get(match.group(1)) == "PaddingZero":
            base = "0"
        else:
            base = f"{match.group(1)}.{side}"
        addition = match.group(3)
        if addition is None:
            return base
        amount = dimension_value(addition.strip())
        if amount is None:
            return None
        return f"{base} + {amount}"

    def semantic_lines(self, call: dict[str, Any], parameters: dict[str, str]) -> list[str]:
        arguments = call.get("semantic_arguments")
        if not isinstance(arguments, dict):
            raise ArkUIPageError("semantic argument inventory is invalid")
        lines: list[str] = []
        component = call["component"]
        color_key = "color" if component != "Divider" else "color"
        if color_key in arguments:
            expression = arguments[color_key].get("resolved_local_expression")
            if not isinstance(expression, str):
                expression = arguments[color_key].get("expression", "")
            color_lines = self.font_color_lines(str(expression), call, parameters) if component == "Text" else None
            color = self.color_expression(str(expression), call, parameters) if component != "Text" else None
            if color_lines is not None:
                lines.extend(color_lines)
            elif color is not None:
                lines.append(f".color({color})")
            else:
                self.add_unresolved("semantic_argument", call, f"{color_key} expression is not safely translated")
        style = arguments.get("style")
        if isinstance(style, dict):
            expression = style.get("resolved_local_expression")
            if not isinstance(expression, str):
                expression = style.get("expression")
            expression_text = expression.strip() if isinstance(expression, str) else ""
            expression_text = self.current_parameter_default_expression(expression_text, parameters)
            inline_lines = self.inline_text_style_lines(expression_text, call, parameters)
            if inline_lines is not None:
                if inline_lines:
                    lines.extend(inline_lines)
                else:
                    self.add_unresolved("typography", call, "TextStyle contains no safely translated text style primitives")
            else:
                role = self.direct_typography_role(expression_text)
                if role is None:
                    self.add_unresolved("typography", call, "text style expression is not a direct generated typography role")
                    return self.filter_android_page_semantic_overrides(call, lines)
                role_lines = self.theme_typography_lines(role, call, {}, parameters)
                if role_lines:
                    lines.extend(role_lines)
                else:
                    self.add_unresolved("theme_resource", call, f"generated typography resources are missing for role: {role}")
        font_size = arguments.get("fontSize")
        if isinstance(font_size, dict):
            expression = str(font_size.get("expression", ""))
            value = self.dimension_expression(expression, parameters)
            if value is None:
                value = self.value_expression(expression, "number", parameters)
            if value is None:
                self.add_unresolved("semantic_argument", call, "fontSize expression is not one literal sp value")
            else:
                lines.append(f".fontSize({value})")
        font_weight = arguments.get("fontWeight")
        if isinstance(font_weight, dict):
            weight = str(font_weight.get("expression", "")).strip()
            translated = self.value_expression(weight, "number", parameters)
            if translated is not None:
                lines.append(f".fontWeight({translated})")
            else:
                self.add_unresolved("semantic_argument", call, "fontWeight expression is not safely translated")
        max_lines = arguments.get("maxLines")
        if isinstance(max_lines, dict):
            value = str(max_lines.get("expression", "")).strip()
            if re.fullmatch(r"[1-9][0-9]*", value):
                lines.append(f".maxLines({value})")
            else:
                self.add_unresolved("semantic_argument", call, "maxLines expression is not a positive literal")
        overflow = arguments.get("overflow")
        if isinstance(overflow, dict):
            value = str(overflow.get("expression", "")).strip()
            if value == "TextOverflow.Ellipsis":
                lines.append(".textOverflow({ overflow: TextOverflow.Ellipsis })")
            else:
                self.add_unresolved("semantic_argument", call, "overflow expression is not safely translated")
        text_align = arguments.get("textAlign")
        if isinstance(text_align, dict):
            value = str(text_align.get("expression", "")).strip()
            translated = self.value_expression(value, "TextAlign", parameters)
            if translated is not None:
                lines.append(f".textAlign({translated})")
            else:
                self.add_unresolved("semantic_argument", call, "textAlign expression is not safely translated")
        if component == "Divider":
            thickness = arguments.get("thickness")
            if isinstance(thickness, dict):
                value = dimension_value(str(thickness.get("expression", "")))
                if value is not None:
                    lines.append(f".strokeWidth({value})")
                else:
                    self.add_unresolved("semantic_argument", call, "Divider thickness is not one literal dp value")
        return self.filter_android_page_semantic_overrides(call, lines)

    def direct_typography_role(self, expression: str) -> str | None:
        stripped = expression.strip()
        material = re.fullmatch(r"MaterialTheme\.typography\.([A-Za-z_][A-Za-z0-9_]*)", stripped)
        if material is not None:
            return snake_name(material.group(1))
        project_object = re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\.([A-Za-z_][A-Za-z0-9_]*)", stripped)
        if project_object is None:
            return None
        role = snake_name(project_object.group(1))
        if any(
            f"compose_typography_{role}_{property_name}" in self.resource_names
            for property_name in ("font_size", "line_height", "letter_spacing")
        ):
            return role
        return None

    def inline_text_style_lines(
        self,
        expression: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> list[str] | None:
        copied_role = re.fullmatch(
            r"(.+?)\.copy\s*\((.*)\)\s*",
            expression.strip(),
            re.S,
        )
        if copied_role is not None:
            positional, named = named_arguments(copied_role.group(2))
            if positional or set(named) - {"fontSize", "lineHeight", "letterSpacing", "color", "textAlign", "fontWeight", "fontFamily"}:
                return None
            role = self.direct_typography_role(copied_role.group(1))
            if role is None:
                return None
            supported_named = {
                key: value
                for key, value in named.items()
                if key != "fontFamily"
            }
            if "fontFamily" in named:
                self.add_unresolved(
                    "typography",
                    call,
                    "fontFamily override requires font resource reconciliation",
                    expression=named["fontFamily"],
                )
            return self.theme_typography_lines(role, call, supported_named, parameters)
        match = re.fullmatch(r"(?:TextStyle|SpanStyle)\s*\((.*)\)\s*", expression.strip(), re.S)
        if match is None:
            return None
        positional, named = named_arguments(match.group(1))
        if positional:
            return None
        lines: list[str] = []
        for source, target in (
            ("fontSize", "fontSize"),
            ("lineHeight", "lineHeight"),
            ("letterSpacing", "letterSpacing"),
        ):
            value = named.get(source)
            if value is None:
                continue
            dimension = self.dimension_expression(value, parameters)
            if dimension is not None:
                lines.append(f".{target}({dimension})")
        color = named.get("color")
        if color is not None:
            translated = self.font_color_lines(color, call, parameters)
            if translated is not None:
                lines.extend(translated)
        text_align = named.get("textAlign")
        if text_align is not None:
            alignment = text_align.strip()
            if alignment in {
                "TextAlign.Start",
                "TextAlign.Center",
                "TextAlign.End",
                "TextAlign.Left",
                "TextAlign.Right",
                "TextAlign.Justify",
            }:
                lines.append(f".textAlign({alignment})")
        font_weight = named.get("fontWeight")
        resolved_weight = self.resolved_font_weight(font_weight)
        if font_weight is not None:
            translated = self.value_expression(font_weight, "number", parameters)
            if translated is not None:
                lines.append(f".fontWeight({translated})")
                resolved_weight = self.resolved_font_weight(translated)
        font_family = named.get("fontFamily")
        if font_family is not None:
            alias = self.verified_font_alias(font_family.strip(), resolved_weight)
            if alias is not None:
                lines.append(f".fontFamily({arkts_string(alias)})")
            else:
                self.add_unresolved(
                    "typography",
                    call,
                    "fontFamily requires a manifest-verified copied font asset",
                    expression=font_family,
                )
        return lines

    def theme_typography_lines(
        self,
        role: str,
        call: dict[str, Any],
        overrides: dict[str, str],
        parameters: dict[str, str],
    ) -> list[str]:
        lines: list[str] = []
        mapped = 0
        for property_name, arkui_name, override_name in (
            ("font_size", "fontSize", "fontSize"),
            ("line_height", "lineHeight", "lineHeight"),
            ("letter_spacing", "letterSpacing", "letterSpacing"),
        ):
            override = overrides.get(override_name)
            if override is not None:
                dimension = self.dimension_expression(override, parameters)
                if dimension is None:
                    dimension = self.value_expression(override, "number", parameters)
                if dimension is None:
                    self.add_unresolved("typography", call, f"{override_name} override is not one literal sp value")
                    continue
                lines.append(f".{arkui_name}({dimension})")
                mapped += 1
                continue
            resource = f"compose_typography_{role}_{property_name}"
            if resource in self.resource_names:
                lines.append(f".{arkui_name}($r('app.float.{resource}'))")
                mapped += 1
        color = overrides.get("color")
        if color is not None:
            translated = self.font_color_lines(color, call, parameters)
            if translated is not None:
                lines.extend(translated)
            else:
                self.add_unresolved("typography", call, "color override is not safely translated")
        text_align = overrides.get("textAlign")
        if text_align is not None:
            alignment = text_align.strip()
            if alignment in {
                "TextAlign.Start",
                "TextAlign.Center",
                "TextAlign.End",
                "TextAlign.Left",
                "TextAlign.Right",
                "TextAlign.Justify",
            }:
                lines.append(f".textAlign({alignment})")
            else:
                self.add_unresolved("typography", call, "textAlign override is not safely translated")
        font_weight = overrides.get("fontWeight")
        default_font = self.typography_font_roles.get(role)
        selected_weight: int | None = None
        if font_weight is not None:
            translated = self.value_expression(font_weight, "number", parameters)
            if translated is not None:
                lines.append(f".fontWeight({translated})")
                selected_weight = self.resolved_font_weight(translated)
            else:
                self.add_unresolved("typography", call, "fontWeight override is not safely translated")
        elif isinstance(default_font, dict) and isinstance(default_font.get("weight"), int):
            selected_weight = default_font["weight"]
            lines.append(f".fontWeight({selected_weight})")
        if isinstance(default_font, dict) and isinstance(default_font.get("family"), str):
            alias = self.verified_font_alias(default_font["family"], selected_weight)
            if alias is not None:
                lines.append(f".fontFamily({arkts_string(alias)})")
        if mapped == 0 and not lines:
            return []
        return lines

    def arrangement_space(
        self,
        component: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> str | None:
        arguments = call.get("semantic_arguments", {})
        argument_name = None
        if component == "Row":
            argument_name = "horizontalArrangement"
        elif component == "LazyRow":
            argument_name = "horizontalArrangement"
        elif component == "Column":
            argument_name = "verticalArrangement"
        elif component == "LazyColumn":
            argument_name = "verticalArrangement"
        if argument_name is None or argument_name not in arguments:
            return None
        expression = str(arguments[argument_name].get("expression", "")).strip()
        match = re.fullmatch(r"Arrangement\.spacedBy\s*\((.*)\)", expression, re.S)
        if match is None:
            return None
        positional, named = named_arguments(match.group(1))
        if len(positional) > 2 or any(name not in {"space", "alignment"} for name in named):
            return None
        space = named.get("space") or (positional[0] if positional else None)
        if space is None:
            return None
        return self.dimension_expression(space.strip(), parameters)

    def alignment_lines(self, call: dict[str, Any], parameters: dict[str, str]) -> list[str]:
        arguments = call.get("semantic_arguments", {})
        component = call["component"]
        lines: list[str] = []
        if component == "Column" and "horizontalAlignment" not in arguments:
            lines.append(".alignItems(HorizontalAlign.Start)")
        if component == "Row" and "verticalAlignment" not in arguments:
            lines.append(".alignItems(VerticalAlign.Top)")
        mappings = {
            ("Column", "horizontalAlignment"): {
                "Alignment.Start": ".alignItems(HorizontalAlign.Start)",
                "Alignment.CenterHorizontally": ".alignItems(HorizontalAlign.Center)",
                "Alignment.End": ".alignItems(HorizontalAlign.End)",
            },
            ("Column", "verticalArrangement"): {
                "Arrangement.Top": ".justifyContent(FlexAlign.Start)",
                "Arrangement.Center": ".justifyContent(FlexAlign.Center)",
                "Arrangement.Bottom": ".justifyContent(FlexAlign.End)",
                "Arrangement.SpaceBetween": ".justifyContent(FlexAlign.SpaceBetween)",
                "Arrangement.SpaceAround": ".justifyContent(FlexAlign.SpaceAround)",
                "Arrangement.SpaceEvenly": ".justifyContent(FlexAlign.SpaceEvenly)",
            },
            ("Row", "verticalAlignment"): {
                "Alignment.Top": ".alignItems(VerticalAlign.Top)",
                "Alignment.CenterVertically": ".alignItems(VerticalAlign.Center)",
                "Alignment.Bottom": ".alignItems(VerticalAlign.Bottom)",
            },
            ("Row", "horizontalArrangement"): {
                "Arrangement.Start": ".justifyContent(FlexAlign.Start)",
                "Arrangement.Center": ".justifyContent(FlexAlign.Center)",
                "Arrangement.End": ".justifyContent(FlexAlign.End)",
                "Arrangement.SpaceBetween": ".justifyContent(FlexAlign.SpaceBetween)",
                "Arrangement.SpaceAround": ".justifyContent(FlexAlign.SpaceAround)",
                "Arrangement.SpaceEvenly": ".justifyContent(FlexAlign.SpaceEvenly)",
            },
            ("Box", "contentAlignment"): {
                "Alignment.Center": ".alignContent(Alignment.Center)",
                "Alignment.CenterStart": ".alignContent(Alignment.Start)",
                "Alignment.CenterEnd": ".alignContent(Alignment.End)",
                "Alignment.TopStart": ".alignContent(Alignment.TopStart)",
                "Alignment.TopCenter": ".alignContent(Alignment.Top)",
                "Alignment.TopEnd": ".alignContent(Alignment.TopEnd)",
                "Alignment.BottomStart": ".alignContent(Alignment.BottomStart)",
                "Alignment.BottomCenter": ".alignContent(Alignment.Bottom)",
                "Alignment.BottomEnd": ".alignContent(Alignment.BottomEnd)",
            },
        }
        for (mapped_component, argument_name), values in mappings.items():
            if component != mapped_component or argument_name not in arguments:
                continue
            expression = str(arguments[argument_name].get("expression", "")).strip()
            if component == "Row" and argument_name == "verticalAlignment":
                translated = self.value_expression(expression, "VerticalAlign", parameters)
                if translated is not None:
                    lines.append(f".alignItems({translated})")
                    continue
            if component == "Column" and argument_name == "horizontalAlignment":
                translated = self.value_expression(expression, "HorizontalAlign", parameters)
                if translated is not None:
                    lines.append(f".alignItems({translated})")
                    continue
            if expression in values:
                lines.append(values[expression])
            elif (
                component in {"Row", "Column"}
                and expression.startswith("Arrangement.spacedBy")
                and self.arrangement_space(component, call, parameters) is not None
            ):
                continue
            else:
                self.add_unresolved("alignment", call, f"{argument_name} expression is not safely translated")
        return lines

    def call_arguments(
        self,
        call: dict[str, Any],
        callee: tuple[str, str],
        caller: tuple[str, str],
        caller_parameters: dict[str, str],
    ) -> list[str] | None:
        custom = call.get("custom_composable")
        arguments = custom.get("arguments") if isinstance(custom, dict) else None
        if not isinstance(arguments, list):
            raise ArkUIPageError("project component invocation arguments are invalid")
        previous_local_values = self._current_local_values
        local_values = call.get("local_values")
        if isinstance(local_values, dict) and all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in local_values.items()
        ):
            self._current_local_values = {**previous_local_values, **local_values}

        def finish(value: list[str] | None) -> list[str] | None:
            self._current_local_values = previous_local_values
            return value

        parameters = self.definition_parameters(callee)
        parameter_order = [item["name"] for item in parameters]
        page_text_value = self.android_page_text_value(call)
        page_text_candidates: dict[str, str] = {}
        if page_text_value is not None:
            for parameter in parameters:
                if (
                    parameter["name"] in {"text", "value"}
                    and parameter["type"] in {"string", "ResourceStr"}
                ):
                    page_text_candidates[parameter["name"]] = arkts_string(page_text_value)
                    continue
                rendered_data_value = self.data_class_page_text_expression(
                    parameter["type"],
                    page_text_value,
                )
                if rendered_data_value is not None:
                    page_text_candidates[parameter["name"]] = rendered_data_value
        if len(page_text_candidates) != 1:
            page_text_candidates = {}
        skippable_style_parameters = self.skippable_material_style_parameters(callee)
        caller_skippable_style_parameters = self.skippable_material_style_parameters(caller)
        known_parameter_names = {
            item["name"]
            for item in self.definitions[callee]["parameters"]
            if isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and isinstance(item.get("type"), str)
            and (
                is_compose_modifier_type(item["type"])
                or is_compose_slot_type(item["type"])
                or is_navigation_controller_type(item["type"])
            )
        }
        supplied_named: dict[str, str] = {}
        supplied_positional: list[str] = []
        for argument in arguments:
            if not isinstance(argument, dict) or not isinstance(argument.get("expression"), str):
                raise ArkUIPageError("project component invocation argument is invalid")
            expression = argument["expression"]
            if isinstance(argument.get("resolved_local_expression"), str):
                expression = argument["resolved_local_expression"]
            name = argument.get("name")
            if name is None:
                if expression.strip():
                    supplied_positional.append(expression)
            elif isinstance(name, str):
                supplied_named[name] = expression
            else:
                raise ArkUIPageError("project component invocation argument name is invalid")
        result: list[str] = []
        for parameter in parameters:
            page_text_override = page_text_candidates.get(parameter["name"])
            if page_text_override is not None:
                self.record_android_page_path(call, "style.content.text")
                result.append(page_text_override)
                continue
            expression = supplied_named.get(parameter["name"])
            source_index = parameter["source_index"]
            if expression is None and source_index < len(supplied_positional):
                expression = supplied_positional[source_index]
            if expression is None:
                default_expression = parameter.get("default")
                if isinstance(default_expression, str):
                    expression = default_expression
                else:
                    self.add_unresolved(
                        "invocation_argument",
                        call,
                        f"required argument is not statically supplied: {parameter['name']}",
                    )
                    return finish(None)
            if parameter["type"] in {"string", "ResourceStr"} and expression.strip() == "null":
                self.add_unresolved(
                    "invocation_argument",
                    call,
                    f"explicit null argument is approximated as empty string: {parameter['name']}",
                    expression=expression,
                )
                translated = "''"
            elif parameter.get("source_base_type") == "ColorFilter" and expression.strip() == "null":
                translated = "false"
            else:
                translated = self.call_aware_value_expression(expression, parameter["type"], call, caller_parameters)
            if translated is None:
                self.add_unresolved(
                    "invocation_argument",
                    call,
                    f"argument is not safely translated: {parameter['name']}",
                    expression=expression,
                )
                if parameter["type"] in {"string", "ResourceStr"}:
                    translated = self.conditional_static_fallback_expression(
                        expression,
                        parameter["type"],
                        caller_parameters,
                    )
                    if translated is not None:
                        result.append(translated)
                        continue
                default_expression = parameter.get("default")
                if not isinstance(default_expression, str):
                    if parameter["type"] in {"string", "ResourceStr"}:
                        translated = "''"
                    elif parameter["type"] == "() => void":
                        translated = "() => {}"
                    elif callback_parameter_types(parameter["type"]) == ["string"]:
                        translated = "(value: string) => {}"
                    elif callback_parameter_types(parameter["type"]) == ["number"]:
                        translated = "(value: number) => {}"
                    elif callback_parameter_types(parameter["type"]) == ["boolean"]:
                        translated = "(value: boolean) => {}"
                    elif array_element_target_type(parameter["type"]) is not None:
                        translated = "[]"
                    elif parameter["type"] in self.data_class_properties_by_target:
                        translated = self.data_class_default_value_expression(parameter["type"])
                        if translated is None:
                            return finish(None)
                    else:
                        return finish(None)
                else:
                    translated = self.value_expression(default_expression, parameter["type"], caller_parameters)
                    if translated is None:
                        if parameter["type"] in {"string", "ResourceStr"} and default_expression.strip() == "null":
                            translated = "''"
                        else:
                            return finish(None)
            result.append(translated)
        supported_names = set(parameter_order) | known_parameter_names
        for name, expression in supplied_named.items():
            if name not in supported_names and name != "modifier":
                skippable_type = skippable_style_parameters.get(name)
                if skippable_type is not None and has_supported_material_style_default(skippable_type, expression):
                    continue
                caller_skippable_type = caller_skippable_style_parameters.get(name)
                if (
                    skippable_type is not None
                    and caller_skippable_type is not None
                    and expression.strip() == name
                    and material_style_base_type(caller_skippable_type) == material_style_base_type(skippable_type)
                ):
                    continue
                self.add_unresolved(
                    "invocation_argument",
                    call,
                    f"argument targets an unsupported or unknown parameter: {name}",
                    expression=expression,
                )
        modifier_expression = supplied_named.get("modifier")
        if (
            modifier_expression is not None
            and modifier_expression.strip() != "Modifier"
            and not modifier_chain_expression(modifier_expression)
            and caller_parameters.get(modifier_expression.strip()) != "Modifier"
        ):
            self.add_unresolved(
                "modifier_parameter",
                call,
                "project component Modifier forwarding requires explicit target-boundary reconciliation",
            )
        return finish(result)

    def call_argument_expressions(
        self,
        call: dict[str, Any],
        callee: tuple[str, str],
    ) -> dict[str, str] | None:
        custom = call.get("custom_composable")
        arguments = custom.get("arguments") if isinstance(custom, dict) else None
        if not isinstance(arguments, list):
            raise ArkUIPageError("project component invocation arguments are invalid")
        parameters = self.definition_parameters(callee)
        supplied_named: dict[str, str] = {}
        supplied_positional: list[str] = []
        for argument in arguments:
            if not isinstance(argument, dict) or not isinstance(argument.get("expression"), str):
                raise ArkUIPageError("project component invocation argument is invalid")
            expression = argument["expression"]
            if isinstance(argument.get("resolved_local_expression"), str):
                expression = argument["resolved_local_expression"]
            name = argument.get("name")
            if name is None:
                if expression.strip():
                    supplied_positional.append(expression)
            elif isinstance(name, str):
                supplied_named[name] = expression
            else:
                raise ArkUIPageError("project component invocation argument name is invalid")

        result: dict[str, str] = {}
        for parameter in parameters:
            expression = supplied_named.get(parameter["name"])
            source_index = parameter["source_index"]
            if expression is None and source_index < len(supplied_positional):
                expression = supplied_positional[source_index]
            if expression is None:
                default_expression = parameter.get("default")
                if not isinstance(default_expression, str):
                    return None
                expression = default_expression
            result[parameter["name"]] = expression
        return result

    def project_modifier_argument_lines(
        self,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> list[str]:
        custom = call.get("custom_composable")
        arguments = custom.get("arguments") if isinstance(custom, dict) else None
        if not isinstance(arguments, list):
            return []
        for argument in arguments:
            if (
                isinstance(argument, dict)
                and argument.get("name") == "modifier"
                and isinstance(argument.get("expression"), str)
            ):
                chain = modifier_chain_expression(argument["expression"])
                if not chain:
                    return []
                modifier_call = dict(call)
                modifier_call["ordered_modifier_chain"] = chain
                return self.modifier_lines(modifier_call, parameters)
        return []

    def optional_spacer_lines(
        self,
        call: dict[str, Any],
        parameters: dict[str, str],
        prefix: str,
    ) -> list[str] | None:
        chain = call.get("ordered_modifier_chain")
        if not isinstance(chain, list) or not chain:
            return None
        fixed_lines: list[str] = []
        optional_entries: list[tuple[str, list[str]]] = []
        expanded_chain: list[dict[str, Any]] = []
        for modifier in chain:
            if not isinstance(modifier, dict) or not isinstance(modifier.get("name"), str) or not isinstance(modifier.get("arguments"), str):
                return None
            if modifier["name"] == "let":
                nested = modifier_let_conditional_modifier_expression(modifier["arguments"])
                if nested is None:
                    return None
                expanded_chain.extend(nested)
            else:
                expanded_chain.append(modifier)
        for modifier in expanded_chain:
            name = modifier["name"]
            if name not in {"optional_width", "optional_height", "optional_size"}:
                return None
            positional, named = named_arguments(modifier["arguments"])
            if named or len(positional) != 1:
                return None
            argument = positional[0].strip()
            targets = {
                "optional_width": ["width"],
                "optional_height": ["height"],
                "optional_size": ["width", "height"],
            }[name]
            if parameters.get(argument) == "number | undefined":
                if IDENTIFIER_PATTERN.fullmatch(argument) is None:
                    return None
                optional_entries.append((argument, targets))
                continue
            value = self.dimension_expression(argument, parameters)
            if value is None:
                return None
            fixed_lines.extend(f".{target}({value})" for target in targets)
        if not optional_entries:
            return None

        def branch_lines(branch_prefix: str, active_entries: list[tuple[str, list[str]]]) -> list[str]:
            result = [f"{branch_prefix}Stack() {{", f"{branch_prefix}}}"]
            for modifier_line in fixed_lines:
                result.append(f"{branch_prefix}  {modifier_line}")
            for argument, targets in active_entries:
                for target in targets:
                    result.append(f"{branch_prefix}  .{target}({argument})")
            return result

        lines: list[str] = []
        first = True
        indexed_entries = list(enumerate(optional_entries))
        for size in range(len(indexed_entries), 0, -1):
            for combination in itertools.combinations(indexed_entries, size):
                active = [entry for _, entry in combination]
                condition = " && ".join(f"{argument} !== undefined" for argument, _ in active)
                keyword = "if" if first else "else if"
                lines.append(f"{prefix}{keyword} ({condition}) {{")
                lines.extend(branch_lines(prefix + "  ", active))
                lines.append(f"{prefix}}}")
                first = False
        lines.append(f"{prefix}else {{")
        lines.extend(branch_lines(prefix + "  ", []))
        lines.append(f"{prefix}}}")
        return lines

    def definition_slot_parameters(self, key: tuple[str, str]) -> list[dict[str, Any]]:
        return [
            parameter
            for parameter in self.definitions[key]["parameters"]
            if isinstance(parameter, dict)
            and isinstance(parameter.get("name"), str)
            and isinstance(parameter.get("type"), str)
            and is_compose_slot_type(parameter["type"])
        ]

    def child_map_for_definition(
        self,
        key: tuple[str, str],
    ) -> dict[str | None, list[dict[str, Any]]]:
        calls = self.calls_by_definition.get(key, [])
        children: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
        call_ids = {item["call_id"] for item in calls}
        for call in calls:
            parent = call.get("parent_call_id")
            if parent is not None and parent not in call_ids:
                self.add_unresolved("hierarchy", call, "parent call is outside the selected definition")
                parent = None
            children[parent].append(call)
        return children

    def render_slot_invocation(
        self,
        call: dict[str, Any],
        indent: int,
        parameters: dict[str, str],
    ) -> list[str]:
        slot = call.get("slot_invocation")
        slot_name = slot.get("name") if isinstance(slot, dict) else None
        if not isinstance(slot_name, str):
            self.add_unresolved("component_semantics", call, "slot invocation is missing a stable slot name")
            return []
        context = self._current_slot_contexts.get(slot_name)
        if context is None:
            return []
        slot_children, slot_child_map, slot_definition_key, slot_parameters = context
        previous_children = self._children
        self._children = slot_child_map
        try:
            lines: list[str] = []
            for child in slot_children:
                lines.extend(
                    self.render_call(
                        child,
                        self.children_for(child),
                        indent,
                        slot_definition_key,
                        slot_parameters,
                    )
                )
        finally:
            self._children = previous_children
        return self.wrap_visibility_lines(call, lines, indent, parameters)

    def inline_project_component_slot_lines(
        self,
        call: dict[str, Any],
        children: list[dict[str, Any]],
        indent: int,
        caller_key: tuple[str, str],
        caller_parameters: dict[str, str],
        callee: tuple[str, str],
        arguments: list[str],
    ) -> list[str] | None:
        normalized_caller_parameters = {
            name: target_parameter_type(parameter_type) or parameter_type
            for name, parameter_type in caller_parameters.items()
        }
        slot_parameters = self.definition_slot_parameters(callee)
        if not slot_parameters:
            return None
        slot_names = [parameter["name"] for parameter in slot_parameters]
        slot_invocation_names = {
            item["slot_invocation"]["name"]
            for item in self.calls_by_definition.get(callee, [])
            if isinstance(item.get("slot_invocation"), dict)
            and isinstance(item["slot_invocation"].get("name"), str)
        }
        if not slot_invocation_names.intersection(slot_names):
            return None

        callee_parameters = self.definition_parameters(callee)
        if len(arguments) != len(callee_parameters):
            return None
        parameter_types = {item["name"]: item["type"] for item in callee_parameters}
        parameter_values = {
            item["name"]: value
            for item, value in zip(callee_parameters, arguments, strict=True)
        }
        for parameter in self.definitions[callee]["parameters"]:
            if (
                isinstance(parameter, dict)
                and isinstance(parameter.get("name"), str)
                and isinstance(parameter.get("type"), str)
                and is_compose_modifier_type(parameter["type"])
            ):
                parameter_types[parameter["name"]] = "Modifier"

        wrapper_modifier_lines = self.project_modifier_argument_lines(call, caller_parameters)
        if call.get("ordered_modifier_chain"):
            wrapper_modifier_lines.extend(self.modifier_lines(call, caller_parameters))
        body_indent = indent + 2 if wrapper_modifier_lines else indent
        callee_children = self.child_map_for_definition(callee)
        caller_children = self._children

        direct_slot_children: dict[str, list[dict[str, Any]]] = {name: [] for name in slot_names}
        unassigned_children: list[dict[str, Any]] = []
        for child in children:
            slot_argument_name = child.get("slot_argument_name")
            if isinstance(slot_argument_name, str) and slot_argument_name in direct_slot_children:
                direct_slot_children[slot_argument_name].append(child)
            elif len(slot_names) == 1:
                direct_slot_children[slot_names[0]].append(child)
            else:
                unassigned_children.append(child)
        if unassigned_children:
            return None

        supplied_slot_contexts: dict[
            str,
            tuple[
                list[dict[str, Any]],
                dict[str | None, list[dict[str, Any]]],
                tuple[str, str],
                dict[str, str],
            ],
        ] = {}
        for name, slot_children in direct_slot_children.items():
            if slot_children:
                supplied_slot_contexts[name] = (slot_children, caller_children, caller_key, normalized_caller_parameters)

        custom = call.get("custom_composable")
        custom_arguments = custom.get("arguments") if isinstance(custom, dict) else None
        if isinstance(custom_arguments, list):
            for argument in custom_arguments:
                if not isinstance(argument, dict):
                    continue
                name = argument.get("name")
                expression = argument.get("expression")
                if not isinstance(name, str) or name not in slot_names or not isinstance(expression, str):
                    continue
                stripped = expression.strip()
                if stripped in self._current_slot_contexts:
                    supplied_slot_contexts[name] = self._current_slot_contexts[stripped]
                elif stripped == "{}":
                    supplied_slot_contexts[name] = ([], caller_children, caller_key, normalized_caller_parameters)
        if not supplied_slot_contexts:
            return None

        previous_children = self._children
        previous_slots = self._current_slot_contexts
        previous_values = self._current_parameter_values
        previous_defaults = self._current_parameter_defaults
        previous_enum_parameters = self._current_enum_parameter_types
        previous_definition_key = self._current_definition_key
        self._current_definition_key = callee
        enum_parameter_types = {
            item["name"]: item["enum_type"]
            for item in callee_parameters
            if isinstance(item.get("enum_type"), str)
        }
        self._children = callee_children
        self._current_slot_contexts = {**previous_slots, **supplied_slot_contexts}
        self._current_parameter_values = {**previous_values, **parameter_values}
        self._current_enum_parameter_types = {**previous_enum_parameters, **enum_parameter_types}
        self._current_parameter_defaults = {
            parameter["name"]: parameter["default"]
            for parameter in self.definitions[callee]["parameters"]
            if isinstance(parameter, dict)
            and isinstance(parameter.get("name"), str)
            and isinstance(parameter.get("default"), str)
        }
        try:
            body_lines: list[str] = []
            for root_call in callee_children[None]:
                body_lines.extend(
                    self.render_call(
                        root_call,
                        self.children_for(root_call),
                        body_indent,
                        callee,
                        parameter_types,
                    )
                )
        finally:
            self._children = previous_children
            self._current_slot_contexts = previous_slots
            self._current_parameter_values = previous_values
            self._current_parameter_defaults = previous_defaults
            self._current_enum_parameter_types = previous_enum_parameters
            self._current_definition_key = previous_definition_key

        if not wrapper_modifier_lines:
            return body_lines
        prefix = " " * indent
        lines = [f"{prefix}Stack() {{"]
        lines.extend(body_lines)
        lines.append(f"{prefix}}}")
        lines.extend(f"{prefix}  {line}" for line in wrapper_modifier_lines)
        return lines

    def inline_project_component_single_root_lines(
        self,
        call: dict[str, Any],
        indent: int,
        caller_key: tuple[str, str],
        caller_parameters: dict[str, str],
        callee: tuple[str, str],
        arguments: list[str],
        parent_component: str | None,
        *,
        allowed_components: set[str],
    ) -> list[str] | None:
        callee_children = self.child_map_for_definition(callee)
        root_calls = callee_children.get(None, [])
        if len(root_calls) != 1:
            return None
        root_call = root_calls[0]
        if root_call.get("component") not in allowed_components:
            return None

        callee_parameters = self.definition_parameters(callee)
        if len(arguments) != len(callee_parameters):
            return None
        parameter_types = {item["name"]: item["type"] for item in callee_parameters}
        parameter_values = {
            item["name"]: value
            for item, value in zip(callee_parameters, arguments, strict=True)
        }
        for parameter in self.definitions[callee]["parameters"]:
            if (
                isinstance(parameter, dict)
                and isinstance(parameter.get("name"), str)
                and isinstance(parameter.get("type"), str)
                and is_compose_modifier_type(parameter["type"])
            ):
                parameter_types[parameter["name"]] = "Modifier"

        previous_children = self._children
        previous_values = self._current_parameter_values
        previous_defaults = self._current_parameter_defaults
        previous_enum_parameters = self._current_enum_parameter_types
        enum_parameter_types = {
            item["name"]: item["enum_type"]
            for item in callee_parameters
            if isinstance(item.get("enum_type"), str)
        }
        self._children = callee_children
        self._current_parameter_values = {**previous_values, **parameter_values}
        self._current_enum_parameter_types = {**previous_enum_parameters, **enum_parameter_types}
        self._current_parameter_defaults = {
            parameter["name"]: parameter["default"]
            for parameter in self.definitions[callee]["parameters"]
            if isinstance(parameter, dict)
            and isinstance(parameter.get("name"), str)
            and isinstance(parameter.get("default"), str)
        }
        try:
            lines = self.render_call(
                root_call,
                self.children_for(root_call),
                indent,
                callee,
                parameter_types,
                parent_component,
            )
        finally:
            self._children = previous_children
            self._current_parameter_values = previous_values
            self._current_parameter_defaults = previous_defaults
            self._current_enum_parameter_types = previous_enum_parameters

        wrapper_modifier_lines = self.project_modifier_argument_lines(call, caller_parameters)
        if call.get("ordered_modifier_chain"):
            wrapper_modifier_lines.extend(self.modifier_lines(call, caller_parameters))
        if wrapper_modifier_lines:
            prefix = " " * indent
            lines.extend(f"{prefix}  {line}" for line in wrapper_modifier_lines)
        return lines

    def project_component_single_root_menu_item(
        self,
        call: dict[str, Any],
        caller_key: tuple[str, str],
        caller_parameters: dict[str, str],
    ) -> tuple[str, str] | None:
        custom = call.get("custom_composable")
        definitions = custom.get("definitions") if isinstance(custom, dict) else None
        if not isinstance(definitions, list) or len(definitions) != 1:
            return None
        definition = definitions[0]
        callee = (definition.get("source"), definition.get("composable"))
        if callee not in set(self.reached_keys) or (caller_key, callee) in self.cycle_edges:
            return None
        argument_expressions = self.call_argument_expressions(call, callee)
        if argument_expressions is None:
            return None

        callee_children = self.child_map_for_definition(callee)
        root_calls = callee_children.get(None, [])
        if len(root_calls) != 1:
            return None
        root_call = root_calls[0]
        if root_call.get("component") != "DropdownMenuItem":
            return None

        callee_parameters = self.definition_parameters(callee)
        parameter_types = {item["name"]: item["type"] for item in callee_parameters}
        parameter_values = argument_expressions.copy()
        for parameter in self.definitions[callee]["parameters"]:
            if (
                isinstance(parameter, dict)
                and isinstance(parameter.get("name"), str)
                and isinstance(parameter.get("type"), str)
                and is_compose_modifier_type(parameter["type"])
            ):
                parameter_types[parameter["name"]] = "Modifier"

        previous_children = self._children
        previous_values = self._current_parameter_values
        previous_defaults = self._current_parameter_defaults
        previous_enum_parameters = self._current_enum_parameter_types
        enum_parameter_types = {
            item["name"]: item["enum_type"]
            for item in callee_parameters
            if isinstance(item.get("enum_type"), str)
        }
        self._children = callee_children
        self._current_parameter_values = {**previous_values, **parameter_values}
        self._current_enum_parameter_types = {**previous_enum_parameters, **enum_parameter_types}
        self._current_parameter_defaults = {
            parameter["name"]: parameter["default"]
            for parameter in self.definitions[callee]["parameters"]
            if isinstance(parameter, dict)
            and isinstance(parameter.get("name"), str)
            and isinstance(parameter.get("default"), str)
        }
        try:
            on_click_expression = str(root_call.get("semantic_arguments", {}).get("onClick", {}).get("expression", ""))
            on_click_stripped = on_click_expression.strip()
            if on_click_stripped in self._current_parameter_values:
                on_click_expression = self._current_parameter_values[on_click_stripped]
            text = self.text_slot_value_expression(
                root_call.get("semantic_arguments", {}).get("text", {}).get("expression", ""),
                parameter_types,
            )
            if text is None:
                caller_text_expression = str(call.get("semantic_arguments", {}).get("text", {}).get("expression", ""))
                if caller_text_expression.strip():
                    text = self.call_aware_value_expression(
                        caller_text_expression,
                        "ResourceStr",
                        call,
                        caller_parameters,
                    )
                if text is None and caller_text_expression.strip():
                    text = self.call_aware_value_expression(
                        caller_text_expression,
                        "string",
                        call,
                        caller_parameters,
                    )
            if text is None:
                custom_arguments = custom.get("arguments") if isinstance(custom, dict) else None
                if isinstance(custom_arguments, list):
                    text_expression = next(
                        (
                            argument.get("expression")
                            for argument in custom_arguments
                            if isinstance(argument, dict)
                            and argument.get("name") == "text"
                            and isinstance(argument.get("expression"), str)
                        ),
                        None,
                    )
                    if isinstance(text_expression, str):
                        text = self.call_aware_value_expression(
                            text_expression,
                            "string",
                            call,
                            caller_parameters,
                        )
                        if text is None:
                            text = self.call_aware_value_expression(
                                text_expression,
                                "ResourceStr",
                                call,
                                caller_parameters,
                            )
            action = self.state_field_set_callback_expression(
                on_click_expression,
                call,
                caller_parameters,
            )
        finally:
            self._children = previous_children
            self._current_parameter_values = previous_values
            self._current_parameter_defaults = previous_defaults
            self._current_enum_parameter_types = previous_enum_parameters
        if text is None or action is None:
            return None
        return text, action

    def render_call(
        self,
        call: dict[str, Any],
        children: list[dict[str, Any]],
        indent: int,
        definition_key: tuple[str, str],
        parameters: dict[str, str],
        parent_component: str | None = None,
    ) -> list[str]:
        prefix = " " * indent
        if "slot_invocation" in call:
            return self.render_slot_invocation(call, indent, parameters)
        custom = call.get("custom_composable")
        if isinstance(custom, dict):
            definitions = custom.get("definitions")
            if not isinstance(definitions, list) or len(definitions) != 1:
                self.add_unresolved("project_component", call, "project component does not resolve to exactly one definition")
                return []
            definition = definitions[0]
            callee = (definition.get("source"), definition.get("composable"))
            if callee not in set(self.reached_keys):
                self.add_unresolved("project_component", call, "resolved project component is outside the selected closure")
                return []
            if (definition_key, callee) in self.cycle_edges:
                return []
            arguments = self.call_arguments(call, callee, definition_key, parameters)
            if arguments is None:
                return []
            if children:
                inlined = self.inline_project_component_slot_lines(
                    call,
                    children,
                    indent,
                    definition_key,
                    parameters,
                    callee,
                    arguments,
                )
                if inlined is not None:
                    return self.wrap_visibility_lines(call, inlined, indent, parameters)
            wrapper_modifier_lines = self.project_modifier_argument_lines(call, parameters)
            if call.get("ordered_modifier_chain"):
                wrapper_modifier_lines.extend(self.modifier_lines(call, parameters))
            if self.android_page_component(call) is not None:
                content_alignment = self.project_component_content_alignment(callee)
                wrapper_modifier_lines.append(
                    f".alignContent({content_alignment or 'Alignment.TopStart'})"
                )
            elif children:
                child_alignment = self.android_page_child_alignment(children)
                if child_alignment is not None:
                    wrapper_modifier_lines.append(f".alignContent({child_alignment})")
            wrapper_modifier_lines.extend(
                self.android_page_visual_lines(call, call["component"])
            )
            if wrapper_modifier_lines or children:
                if children:
                    self.add_unresolved(
                        "component_semantics",
                        call,
                        "project component slot children are structurally preserved at call site and need target slot reconciliation",
                    )
                lines = [f"{prefix}Stack() {{", f"{prefix}  this.{builder_name(*callee)}({', '.join(arguments)})"]
                for child in children:
                    lines.extend(
                        self.render_call(
                            child,
                            self.children_for(child),
                            indent + 2,
                            definition_key,
                            parameters,
                            "Stack",
                        )
                    )
                lines.append(f"{prefix}}}")
                lines.extend(f"{prefix}  {line}" for line in wrapper_modifier_lines)
                return self.wrap_visibility_lines(call, lines, indent, parameters)
            if call.get("ordered_modifier_chain"):
                self.add_unresolved("project_component_modifier", call, "call-site modifiers on project builders require a target wrapper")
            return self.wrap_visibility_lines(call, [f"{prefix}this.{builder_name(*callee)}({', '.join(arguments)})"], indent, parameters)

        component = call["component"]
        container_map = {
            "Column": "Column",
            "Row": "Row",
            "Box": "Stack",
            "Dialog": "Stack",
            "DecorationBox": "Column",
            "BoxWithConstraints": "Stack",
            "Scaffold": "Column",
            "Card": "Column",
            "Canvas": "Stack",
            "DatePickerDialog": "Stack",
            "AnimatedVisibility": "Stack",
            "ModalBottomSheet": "Stack",
            "PullToRefreshBox": "Stack",
            "Surface": "Stack",
            "TopAppBar": "Stack",
            "CenterAlignedTopAppBar": "Stack",
            "ConstraintLayout": "RelativeContainer",
            "LazyColumn": "List",
            "LazyRow": "List",
            "Button": "Button",
            "TextButton": "Button",
            "OutlinedButton": "Button",
            "IconButton": "Button",
        }
        if component in container_map:
            surface_lines: list[str] = []
            surface_handled = False
            if component == "Surface":
                surface_lines, surface_handled = self.surface_style_lines(call, parameters)
            top_app_bar_lines: list[str] = []
            if component in {"TopAppBar", "CenterAlignedTopAppBar"}:
                top_app_bar_lines = self.top_app_bar_style_lines(call, parameters)
            card_lines: list[str] = []
            card_handled = False
            if component == "Card":
                card_lines, card_handled = self.card_style_lines(call, parameters)
            lazy_list_lines = self.lazy_list_style_lines(call, parameters) if component in {"LazyColumn", "LazyRow"} else []
            if component in {"Dialog", "DecorationBox", "BoxWithConstraints", "Scaffold", "Card", "Canvas", "DatePickerDialog", "AnimatedVisibility", "ModalBottomSheet", "PullToRefreshBox", "Surface", "TopAppBar", "CenterAlignedTopAppBar", "ConstraintLayout", "LazyColumn", "LazyRow", "TextButton", "OutlinedButton", "IconButton"} and not (
                component == "TextButton" and self.text_button_defaults_supported(children)
            ) and not (
                component == "IconButton" and self.icon_button_defaults_supported(children)
            ) and not (
                component == "BoxWithConstraints" and self.box_with_constraints_defaults_supported(children)
            ) and not (
                component == "AnimatedVisibility" and self.animated_visibility_defaults_supported(call, parameters)
            ) and not (
                component in {"LazyColumn", "LazyRow"} and self.lazy_list_defaults_supported(component, call, parameters)
            ) and not (
                component == "Scaffold" and self.scaffold_defaults_supported(call)
            ) and not (
                component in {"TopAppBar", "CenterAlignedTopAppBar"}
                and self.top_app_bar_defaults_supported(call, parameters, top_app_bar_lines)
            ) and not (
                component == "Surface" and surface_handled
            ) and not (
                component == "Card" and card_handled
            ):
                self.add_unresolved(
                    "component_semantics",
                    call,
                    f"{component} needs platform/default/slot reconciliation beyond its emitted structural container",
                )
            space = self.arrangement_space(component, call, parameters) if component in {"Row", "Column", "LazyColumn", "LazyRow"} else None
            constructor = f"{container_map[component]}({{ space: {space} }})" if space is not None else f"{container_map[component]}()"
            chain = call.get("ordered_modifier_chain")
            previous_local_values = self._current_local_values
            local_values = call.get("local_values")
            if isinstance(local_values, dict) and all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in local_values.items()
            ):
                self._current_local_values = local_values
            try:
                conditional_scroll_variants = (
                    self.conditional_scroll_variants(chain, call, parameters)
                    if isinstance(chain, list) and component in {"Column", "Row", "Box", "BoxWithConstraints"}
                    else None
                )
            finally:
                self._current_local_values = previous_local_values
            effective_chain = expand_then_containing_supported_scroll(chain) if isinstance(chain, list) else chain
            visibility_condition: str | None = None
            if component == "AnimatedVisibility":
                semantic = call.get("semantic_arguments", {})
                visible = semantic.get("visible") if isinstance(semantic, dict) else None
                visible_expression = visible.get("expression") if isinstance(visible, dict) else None
                if isinstance(visible, dict) and isinstance(visible.get("resolved_local_expression"), str):
                    visible_expression = visible["resolved_local_expression"]
                if isinstance(visible_expression, str):
                    visibility_condition = self.state_condition_expression(visible_expression, call, parameters)
                    if visibility_condition is None:
                        self.add_unresolved("visibility_condition", call, "AnimatedVisibility visible expression is not safely translated")
            child_parameters = dict(parameters)
            if component == "BoxWithConstraints":
                child_parameters.setdefault("maxWidth", "constraint_dimension")
                child_parameters.setdefault("maxHeight", "constraint_dimension")
            if component == "Scaffold":
                trailing_parameters = call.get("trailing_lambda_parameters")
                if (
                    isinstance(trailing_parameters, list)
                    and len(trailing_parameters) == 1
                    and isinstance(trailing_parameters[0], str)
                    and IDENTIFIER_PATTERN.fullmatch(trailing_parameters[0]) is not None
                ):
                    child_parameters[trailing_parameters[0]] = "PaddingZero"
                    self.add_unresolved(
                        "scaffold_padding",
                        call,
                        "Scaffold content padding is emitted as zero Padding because ArkUI builder syntax cannot declare a local Padding value here",
                        parameter=trailing_parameters[0],
                    )

            def render_container_variant(container_prefix: str, variant_chain: list[Any] | Any) -> list[str]:
                has_vertical_scroll = (
                    isinstance(variant_chain, list)
                    and any(isinstance(item, dict) and is_supported_vertical_scroll(item) for item in variant_chain)
                )
                has_horizontal_scroll = (
                    isinstance(variant_chain, list)
                    and any(isinstance(item, dict) and is_supported_horizontal_scroll(item) for item in variant_chain)
                )
                scroll_wrapped = (
                    component in {"Column", "Row", "Box", "BoxWithConstraints"}
                    and (has_vertical_scroll or has_horizontal_scroll)
                )
                inner_prefix = container_prefix + ("  " if scroll_wrapped else "")
                variant_lines: list[str] = []
                if scroll_wrapped:
                    variant_lines.append(f"{container_prefix}Scroll() {{")
                variant_lines.append(f"{inner_prefix}{constructor} {{")
                child_indent = len(inner_prefix) + 2
                if component in {"LazyColumn", "LazyRow"}:
                    list_item_prefix = inner_prefix + "  "
                    list_child_indent = len(inner_prefix) + 4
                    for child in children:
                        list_item_context = child.get("list_item_context")
                        if isinstance(list_item_context, dict):
                            collection_source = list_item_context.get("collection")
                            item_parameter = list_item_context.get("item_parameter")
                            if isinstance(collection_source, str) and isinstance(item_parameter, str):
                                collection_expression = self.value_expression(collection_source, "unknown[]", child_parameters)
                                if collection_expression is not None:
                                    item_type = self.collection_element_type_for_expression(collection_source, child_parameters) or FALLBACK_LIST_ITEM_TYPE
                                    if item_type == FALLBACK_LIST_ITEM_TYPE:
                                        self._uses_fallback_list_item = True
                                        self.add_unresolved(
                                            "collection_element_type",
                                            child,
                                            "Lazy list item type is not statically known; emitted a named opaque fallback item type",
                                            expression=collection_source,
                                            fallback_type=FALLBACK_LIST_ITEM_TYPE,
                                        )
                                    loop_parameters = dict(child_parameters)
                                    loop_parameters[item_parameter] = item_type
                                    variant_lines.append(f"{list_item_prefix}ForEach({collection_expression}, ({item_parameter}: {item_type}) => {{")
                                    variant_lines.append(f"{list_item_prefix}  ListItem() {{")
                                    variant_lines.extend(
                                        self.render_call(
                                            child,
                                            self.children_for(child),
                                            list_child_indent + 2,
                                            definition_key,
                                            loop_parameters,
                                            "ListItem",
                                        )
                                    )
                                    variant_lines.append(f"{list_item_prefix}  }}")
                                    variant_lines.append(f"{list_item_prefix}}})")
                                    continue
                                self.add_unresolved(
                                    "list_items",
                                    child,
                                    "Lazy list items collection is not safely translated",
                                    expression=collection_source,
                                )
                        variant_lines.append(f"{list_item_prefix}ListItem() {{")
                        variant_lines.extend(
                            self.render_call(
                                child,
                                self.children_for(child),
                                list_child_indent,
                                definition_key,
                                child_parameters,
                                "ListItem",
                            )
                        )
                        variant_lines.append(f"{list_item_prefix}}}")
                else:
                    if component in BUTTON_CONTAINER_COMPONENTS and len(children) > 1:
                        button_child_prefix = " " * child_indent
                        variant_lines.append(f"{button_child_prefix}Row() {{")
                        variant_lines.extend(
                            self.render_call_sequence(
                                children,
                                child_indent + 2,
                                definition_key,
                                child_parameters,
                                "Row",
                            )
                        )
                        variant_lines.append(f"{button_child_prefix}}}")
                    else:
                        rendered_children = self.render_call_sequence(
                            children,
                            child_indent,
                            definition_key,
                            child_parameters,
                            component,
                        )
                        if component in BUTTON_CONTAINER_COMPONENTS and not rendered_children:
                            fallback_children = self.button_fallback_content_lines(
                                children,
                                child_indent,
                                child_parameters,
                            )
                            if fallback_children is not None:
                                rendered_children = fallback_children
                        variant_lines.extend(rendered_children)
                variant_lines.append(f"{inner_prefix}}}")
                modifier_call = call
                if isinstance(variant_chain, list):
                    modifier_call = dict(call)
                    modifier_call["ordered_modifier_chain"] = [
                        item
                        for item in variant_chain
                        if not scroll_wrapped or not (
                            isinstance(item, dict)
                            and (is_supported_vertical_scroll(item) or is_supported_horizontal_scroll(item))
                        )
                    ]
                post_lines = (
                    self.modifier_lines(modifier_call, parameters)
                    + surface_lines
                    + top_app_bar_lines
                    + card_lines
                    + lazy_list_lines
                    + self.alignment_lines(call, parameters)
                    + self.android_page_visual_lines(call, component)
                )
                if component in {"Button", "TextButton", "OutlinedButton", "IconButton"}:
                    post_lines.extend(self.button_style_lines(component, call, parameters))
                    enabled_line = self.enabled_line(call, parameters)
                    if enabled_line is not None:
                        post_lines.append(enabled_line)
                    semantic = call.get("semantic_arguments", {})
                    on_click = semantic.get("onClick") if isinstance(semantic, dict) else None
                    on_click_expression = on_click.get("expression") if isinstance(on_click, dict) else None
                    click_line = self.form_validation_click_line(str(on_click_expression or ""), call, parameters)
                    if click_line is None:
                        click_line = self.state_field_toggle_click_line(str(on_click_expression or ""), call, parameters)
                    if click_line is None:
                        click_line = self.state_field_set_click_line(str(on_click_expression or ""), call, parameters)
                    if click_line is None:
                        click_line = self.callback_click_line(str(on_click_expression or ""), call, parameters)
                    if click_line is None:
                        self.add_unresolved("button_callback", call, "button onClick is not a supported no-arg callback")
                    else:
                        post_lines.append(click_line)
                if (
                    component == "IconButton"
                    and self.android_page_input is not None
                    and self.android_page_component(call) is not None
                    and not any(line.startswith(".translate(") for line in post_lines)
                ):
                    post_lines.append(".translate({ y: -1 })")
                if component == "LazyRow":
                    post_lines.append(".listDirection(Axis.Horizontal)")
                for modifier in post_lines:
                    variant_lines.append(f"{inner_prefix}  {modifier}")
                if scroll_wrapped:
                    variant_lines.append(f"{container_prefix}}}")
                    if has_horizontal_scroll:
                        variant_lines.append(f"{container_prefix}  .scrollable(ScrollDirection.Horizontal)")
                return variant_lines

            container_prefix = prefix
            lines: list[str] = []
            if visibility_condition is not None and visibility_condition != "true":
                lines.append(f"{prefix}if ({visibility_condition}) {{")
                container_prefix = prefix + "  "
            if conditional_scroll_variants is not None:
                condition_expression, true_chain, false_chain = conditional_scroll_variants
                lines.append(f"{container_prefix}if ({condition_expression}) {{")
                lines.extend(render_container_variant(container_prefix + "  ", true_chain))
                lines.append(f"{container_prefix}}} else {{")
                lines.extend(render_container_variant(container_prefix + "  ", false_chain))
                lines.append(f"{container_prefix}}}")
            else:
                lines.extend(render_container_variant(container_prefix, effective_chain))
            if visibility_condition is not None and visibility_condition != "true":
                lines.append(f"{prefix}}}")
            return self.wrap_visibility_lines(call, lines, indent, parameters)
        if component == "ExposedDropdownMenuBox":
            rendered = self.render_exposed_dropdown_menu_box(call, children, indent, parameters)
            if rendered is not None:
                return rendered
            self.add_unresolved(
                "component_semantics",
                call,
                "ExposedDropdownMenuBox needs a supported anchor field and dropdown item collection to emit Select",
            )
            self.add_unresolved("component", call, f"no compile-safe ArkUI emitter is available for {component}")
            return []
        if component in {"Text", "BasicText", "ClickableText"}:
            previous_local_values = self._current_local_values
            local_values = call.get("local_values")
            if isinstance(local_values, dict) and all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in local_values.items()
            ):
                self._current_local_values = {**previous_local_values, **local_values}
            try:
                semantic = call.get("semantic_arguments", {})
                text = semantic.get("text") if isinstance(semantic, dict) else None
                expression = None
                if isinstance(text, dict):
                    expression = text.get("resolved_local_expression")
                    if not isinstance(expression, str):
                        expression = text.get("expression")
                positional = call.get("positional_arguments")
                if expression is None and isinstance(positional, list) and positional:
                    first = positional[0]
                    if isinstance(first, dict):
                        expression = first.get("resolved_local_expression")
                        if not isinstance(expression, str):
                            expression = first.get("expression")
                translated = self.android_page_text_expression(call)
                if translated is None:
                    translated = self.call_aware_value_expression(str(expression or ""), "ResourceStr", call, parameters)
                if translated is None:
                    self.add_unresolved("text_expression", call, "Text content is not a literal or supported string parameter")
                    return []
                modifiers = (
                    self.modifier_lines(call, parameters)
                    + self.semantic_lines(call, parameters)
                    + self.android_page_visual_lines(call, component)
                )
                if parent_component == "TextButton":
                    for prefix_name, default_line in (
                        (".fontSize(", ".fontSize(14)"),
                        (".lineHeight(", ".lineHeight(20)"),
                        (".fontWeight(", ".fontWeight(500)"),
                        (".maxLines(", ".maxLines(1)"),
                    ):
                        if not any(line.startswith(prefix_name) for line in modifiers):
                            modifiers.append(default_line)
                    if (
                        self.android_page_input is not None
                        and not any(line.startswith(".letterSpacing(") for line in modifiers)
                    ):
                        modifiers.append(".letterSpacing(-0.5)")
                if component == "ClickableText" and self.android_page_component(call) is not None:
                    if not any(line.startswith(".letterSpacing(") for line in modifiers):
                        modifiers.append(".letterSpacing(-0.05)")
                    if not any(line.startswith(".maxLines(") for line in modifiers):
                        modifiers.append(".maxLines(1)")
                self.apply_page_driven_text_rasterization_adapter(call, modifiers)
                annotated_spans = (
                    self.build_annotated_string_spans(
                        str(expression or ""),
                        call,
                        parameters,
                    )
                    if component == "ClickableText"
                    else None
                )
                if annotated_spans is not None:
                    lines = [f"{prefix}Text() {{"]
                    for span_expression, span_style_lines in annotated_spans:
                        lines.append(f"{prefix}  Span({span_expression})")
                        effective_span_lines = self.inherited_span_style_lines(
                            modifiers,
                            span_style_lines,
                        )
                        lines.extend(
                            f"{prefix}    {style_line}"
                            for style_line in effective_span_lines
                        )
                    lines.append(f"{prefix}}}")
                    lines.extend(f"{prefix}  {modifier}" for modifier in modifiers)
                    self.add_unresolved(
                        "component_semantics",
                        call,
                        "ClickableText span/click offsets require annotation reconciliation",
                    )
                    return self.wrap_visibility_lines(call, lines, indent, parameters)
                optional_font_colors = [
                    modifier[len(OPTIONAL_FONT_COLOR_PREFIX) :]
                    for modifier in modifiers
                    if modifier.startswith(OPTIONAL_FONT_COLOR_PREFIX)
                ]
                modifiers = [
                    modifier
                    for modifier in modifiers
                    if not modifier.startswith(OPTIONAL_FONT_COLOR_PREFIX)
                ]
                if optional_font_colors:
                    color = optional_font_colors[0]
                    lines = [f"{prefix}if ({color} !== null) {{"]
                    lines.append(f"{prefix}  Text({translated})")
                    for modifier in modifiers:
                        lines.append(f"{prefix}    {modifier}")
                    lines.append(f"{prefix}    .fontColor({color})")
                    lines.append(f"{prefix}}} else {{")
                    lines.append(f"{prefix}  Text({translated})")
                    for modifier in modifiers:
                        lines.append(f"{prefix}    {modifier}")
                    lines.append(f"{prefix}}}")
                else:
                    lines = [f"{prefix}Text({translated})"]
                    for modifier in modifiers:
                        lines.append(f"{prefix}  {modifier}")
                if component == "ClickableText":
                    self.add_unresolved("component_semantics", call, "ClickableText span/click offsets require annotation reconciliation")
                return self.wrap_visibility_lines(call, lines, indent, parameters)
            finally:
                self._current_local_values = previous_local_values
        if component == "Spacer":
            optional_lines = self.optional_spacer_lines(call, parameters, prefix)
            if optional_lines is not None:
                return self.wrap_visibility_lines(call, optional_lines, indent, parameters)
            lines = [f"{prefix}Stack() {{", f"{prefix}}}"]
            for modifier in self.modifier_lines(call, parameters) + self.android_page_visual_lines(call, component):
                lines.append(f"{prefix}  {modifier}")
            return self.wrap_visibility_lines(call, lines, indent, parameters)
        if component in {"Divider", "HorizontalDivider"}:
            lines = [f"{prefix}Divider()"]
            for modifier in self.modifier_lines(call, parameters) + self.semantic_lines(call, parameters) + self.android_page_visual_lines(call, component):
                lines.append(f"{prefix}  {modifier}")
            return self.wrap_visibility_lines(call, lines, indent, parameters)
        if component in {"BasicTextField", "TextField", "OutlinedTextField"}:
            previous_local_values = self._current_local_values
            local_values = call.get("local_values")
            if isinstance(local_values, dict) and all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in local_values.items()
            ):
                self._current_local_values = {**previous_local_values, **local_values}
            semantic = call.get("semantic_arguments", {})
            value = semantic.get("value") if isinstance(semantic, dict) else None
            value_expression = value.get("expression") if isinstance(value, dict) else None
            translated_value = self.android_page_text_expression(call)
            if translated_value is None:
                translated_value = self.state_field_access_expression(call, str(value_expression or ""), "string", parameters)
            if translated_value is None:
                translated_value = self.value_expression(str(value_expression or ""), "string", parameters)
            if translated_value is None:
                self.add_unresolved("text_field_value", call, "text field value is not a literal or supported string parameter")
                translated_value = "''"
            text_input_arguments = [f"text: {translated_value}"]
            placeholder = semantic.get("placeholder") if isinstance(semantic, dict) else None
            placeholder_expression = placeholder.get("expression") if isinstance(placeholder, dict) else None
            if isinstance(placeholder_expression, str):
                translated_placeholder = self.text_slot_value_expression(placeholder_expression, parameters)
                if translated_placeholder is None:
                    self.add_unresolved("text_field_placeholder", call, "text field placeholder is not a supported Text slot")
                else:
                    text_input_arguments.append(f"placeholder: {translated_placeholder}")
            elif isinstance(semantic, dict):
                label = semantic.get("label")
                label_expression = label.get("expression") if isinstance(label, dict) else None
                if isinstance(label_expression, str):
                    translated_label = self.text_slot_value_expression(label_expression, parameters)
                    if translated_label is not None:
                        text_input_arguments.append(f"placeholder: {translated_label}")
            lines = [f"{prefix}TextInput({{ {', '.join(text_input_arguments)} }})"]
            on_change = semantic.get("onValueChange") if isinstance(semantic, dict) else None
            on_change_expression = on_change.get("expression") if isinstance(on_change, dict) else None
            change_line = self.state_field_change_line(str(on_change_expression or ""), call, parameters)
            if change_line is None:
                change_line = self.callback_change_line(str(on_change_expression or ""), parameters)
            if change_line is None:
                self.add_unresolved("text_field_callback", call, "text field onValueChange is not a supported string callback parameter")
            else:
                lines.append(f"{prefix}  {change_line}")
            text_style = semantic.get("textStyle") if isinstance(semantic, dict) else None
            text_style_expression = text_style.get("expression") if isinstance(text_style, dict) else None
            if isinstance(text_style_expression, str):
                resolved_style = self.current_parameter_default_expression(text_style_expression, parameters)
                style_lines = self.inline_text_style_lines(resolved_style, call, parameters)
                if style_lines is None:
                    self.add_unresolved("text_field_text_style", call, "text field textStyle is not safely translated")
                else:
                    lines.extend(f"{prefix}  {line}" for line in style_lines)
            if component == "BasicTextField":
                lines.extend(
                    f"{prefix}  {line}"
                    for line in self.basic_text_field_decoration_lines(children, call, parameters)
                )
            shape = semantic.get("shape") if isinstance(semantic, dict) else None
            shape_expression = shape.get("expression") if isinstance(shape, dict) else None
            shape_rendered = False
            if isinstance(shape_expression, str):
                radius = self.rounded_corner_radius_expression(shape_expression, parameters)
                if radius is None:
                    self.add_unresolved(
                        "semantic_argument",
                        call,
                        "text field shape is not a supported rounded corner shape",
                    )
                else:
                    lines.append(f"{prefix}  .borderRadius({radius})")
                    shape_rendered = True
            if component == "OutlinedTextField" and not shape_rendered:
                lines.append(f"{prefix}  .borderRadius(4)")
                shape_rendered = True
            outlined_border_handled = False
            if component == "OutlinedTextField" and isinstance(semantic, dict):
                border_line, outlined_border_handled = self.outlined_text_field_border_line(semantic, call, parameters)
                if border_line is not None:
                    lines.append(f"{prefix}  {border_line}")
            password_security_state = (
                self.password_visibility_security_state(semantic, call, parameters)
                if component == "OutlinedTextField" and isinstance(semantic, dict)
                else None
            )
            keyboard_options = semantic.get("keyboardOptions") if isinstance(semantic, dict) else None
            keyboard_options_expression = keyboard_options.get("expression") if isinstance(keyboard_options, dict) else None
            rendered_input_type: str | None = None
            if isinstance(keyboard_options_expression, str):
                input_type = self.input_type_expression(keyboard_options_expression, parameters)
                if input_type is None:
                    self.add_unresolved(
                        "text_field_keyboard_type",
                        call,
                        "text field keyboardOptions keyboardType is not safely translated",
                    )
                else:
                    rendered_input_type = input_type
            visual_transformation = semantic.get("visualTransformation") if isinstance(semantic, dict) else None
            visual_transformation_expression = (
                visual_transformation.get("expression") if isinstance(visual_transformation, dict) else None
            )
            password_security_lines: list[str] = []
            if password_security_state is not None:
                state_field, state_represents_hidden = password_security_state
                if rendered_input_type not in {None, "InputType.Normal", "InputType.Password"}:
                    self.add_unresolved(
                        "text_field_visual_transformation",
                        call,
                        "password visualTransformation conflicts with keyboardOptions input type",
                    )
                    password_security_state = None
                else:
                    rendered_input_type = "InputType.Password"
                    visible_expression = f"!{state_field}" if state_represents_hidden else state_field
                    sync_expression = f"!visible" if state_represents_hidden else "visible"
                    password_security_lines = [
                        f".showPassword({visible_expression})",
                        ".showPasswordIcon(true)",
                        f".onSecurityStateChange((visible: boolean): void => {{ {state_field} = {sync_expression} }})",
                    ]
            if isinstance(visual_transformation_expression, str) and password_security_state is None:
                visual_input_type = self.input_type_expression(visual_transformation_expression, parameters)
                if visual_input_type is None:
                    pass
                elif rendered_input_type is None:
                    rendered_input_type = visual_input_type
                elif rendered_input_type == "InputType.Normal":
                    rendered_input_type = visual_input_type
                elif visual_input_type.startswith("(") and "InputType.Normal" in visual_input_type:
                    pass
                elif self.input_type_parameter_default_is_normal(rendered_input_type, parameters):
                    rendered_input_type = (
                        f"({visual_input_type} === InputType.Normal ? {rendered_input_type} : {visual_input_type})"
                    )
                elif visual_input_type not in {"InputType.Normal", rendered_input_type}:
                    self.add_unresolved(
                        "text_field_visual_transformation",
                        call,
                        "text field keyboardOptions and visualTransformation input types conflict",
                    )
            if rendered_input_type is not None:
                lines.append(f"{prefix}  .type({rendered_input_type})")
            lines.extend(f"{prefix}  {line}" for line in password_security_lines)
            single_line = semantic.get("singleLine") if isinstance(semantic, dict) else None
            single_line_expression = single_line.get("expression") if isinstance(single_line, dict) else None
            max_lines = semantic.get("maxLines") if isinstance(semantic, dict) else None
            max_lines_expression = max_lines.get("expression") if isinstance(max_lines, dict) else None
            if isinstance(single_line_expression, str):
                translated_single_line = self.value_expression(single_line_expression, "boolean", parameters)
                if translated_single_line is None:
                    self.add_unresolved("text_field_line_limit", call, "singleLine expression is not safely translated")
                elif translated_single_line == "true":
                    lines.append(f"{prefix}  .maxLines(1)")
                elif translated_single_line != "false":
                    lines.append(f"{prefix}  .maxLines({translated_single_line} ? 1 : Number.MAX_SAFE_INTEGER)")
            elif isinstance(max_lines_expression, str):
                translated_max_lines = self.value_expression(max_lines_expression, "number", parameters)
                if translated_max_lines is None:
                    self.add_unresolved("text_field_line_limit", call, "maxLines expression is not safely translated")
                else:
                    lines.append(f"{prefix}  .maxLines({translated_max_lines})")
            enabled_line = self.enabled_line(call, parameters)
            if enabled_line is not None:
                lines.append(f"{prefix}  {enabled_line}")
            for modifier in self.modifier_lines(call, parameters) + self.android_page_visual_lines(call, component):
                lines.append(f"{prefix}  {modifier}")
            supporting_text_handled = False
            grouped_lines = lines
            if component == "BasicTextField" and children:
                grouped_lines = [f"{prefix}Column() {{"]
                grouped_lines.extend(f"{prefix}  {line[len(prefix):]}" for line in lines)
                child_indent = len(prefix) + 2
                for child in children:
                    grouped_lines.extend(
                        self.render_call(
                            child,
                            self.children_for(child),
                            child_indent,
                            definition_key,
                            parameters,
                            "Column",
                        )
                    )
                grouped_lines.append(f"{prefix}}}")
            if component == "OutlinedTextField" and isinstance(semantic, dict):
                supporting = semantic.get("supportingText")
                supporting_expression = supporting.get("expression") if isinstance(supporting, dict) else None
                if isinstance(supporting_expression, str):
                    supporting_lines = self.supporting_text_lines(supporting_expression, call, parameters)
                    if supporting_lines is None:
                        self.add_unresolved(
                            "component_semantics",
                            call,
                            "OutlinedTextField supportingText is not safely translated",
                        )
                    else:
                        grouped_lines = [f"{prefix}Column() {{"]
                        grouped_lines.extend(f"{prefix}  {line[len(prefix):]}" for line in lines)
                        grouped_lines.extend(f"{prefix}  {line}" for line in supporting_lines)
                        grouped_lines.append(f"{prefix}}}")
                        supporting_text_handled = True
            material_defaults_handled = (
                component == "OutlinedTextField"
                and outlined_border_handled
                and isinstance(semantic, dict)
                and not self.outlined_text_field_has_unsupported_decoration(
                    semantic,
                    password_trailing_icon_handled=password_security_state is not None,
                    supporting_text_handled=supporting_text_handled,
                )
            )
            if component != "BasicTextField" and not material_defaults_handled:
                self.add_unresolved("component_semantics", call, f"{component} decoration/defaults require Material reconciliation")
            self._current_local_values = previous_local_values
            return self.wrap_visibility_lines(call, grouped_lines, indent, parameters)
        if component == "DatePicker":
            previous_local_values = self._current_local_values
            local_values = call.get("local_values")
            if isinstance(local_values, dict) and all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in local_values.items()
            ):
                self._current_local_values = {**previous_local_values, **local_values}
            semantic = call.get("semantic_arguments", {})
            state_arg = None
            if isinstance(semantic, dict):
                state_arg = semantic.get("state")
                if state_arg is None:
                    state_arg = semantic.get("calendarState")
            state_expression = state_arg.get("expression") if isinstance(state_arg, dict) else None
            if isinstance(state_arg, dict) and isinstance(state_arg.get("resolved_local_expression"), str):
                state_expression = state_arg["expression"]
            selected_state = (
                self.material_picker_selected_state_field(call, state_expression, parameters)
                if isinstance(state_expression, str)
                else None
            )
            if selected_state is None:
                selected_state = self.inferred_local_calendar_state_field(call, parameters)
            lines = [f"{prefix}DatePicker({{ selected: {selected_state or 'new Date()'} }})"]
            if selected_state is not None:
                lines.append(f"{prefix}  .onDateChange((value: Date): void => {{ {selected_state} = value }})")
            for modifier in self.modifier_lines(call, parameters) + self.android_page_visual_lines(call, component):
                lines.append(f"{prefix}  {modifier}")
            if isinstance(semantic, dict) and "selectableDates" in semantic:
                self.add_unresolved("component_semantics", call, "DatePicker selectableDates requires explicit manual reconciliation")
            self.add_unresolved("component_semantics", call, "DatePicker Material header and mode toggle defaults require reconciliation")
            self._current_local_values = previous_local_values
            return self.wrap_visibility_lines(call, lines, indent, parameters)
        if component in {"TimePicker", "TimeInput"}:
            previous_local_values = self._current_local_values
            local_values = call.get("local_values")
            if isinstance(local_values, dict) and all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in local_values.items()
            ):
                self._current_local_values = {**previous_local_values, **local_values}
            semantic = call.get("semantic_arguments", {})
            state_arg = semantic.get("state") if isinstance(semantic, dict) else None
            state_expression = state_arg.get("expression") if isinstance(state_arg, dict) else None
            resolved_state_expression = (
                state_arg.get("resolved_local_expression")
                if isinstance(state_arg, dict) and isinstance(state_arg.get("resolved_local_expression"), str)
                else None
            )
            selected_state = (
                self.material_picker_selected_state_field(call, state_expression, parameters)
                if isinstance(state_expression, str)
                else None
            )
            lines = [f"{prefix}TimePicker({{ selected: {selected_state or 'new Date()'} }})"]
            if isinstance(state_expression, str):
                local_or_expression = resolved_state_expression or self.local_value_expression(state_expression, parameters) or state_expression
                military = self.material_time_picker_use_military_expression(local_or_expression, parameters)
                if military is not None:
                    lines.append(f"{prefix}  .useMilitaryTime({military})")
            if selected_state is not None:
                lines.append(
                    f"{prefix}  .onChange((value: TimePickerResult): void => {{ {selected_state} = new Date(2000, 0, 1, value.hour, value.minute, value.second) }})"
                )
            for modifier in self.modifier_lines(call, parameters) + self.android_page_visual_lines(call, component):
                lines.append(f"{prefix}  {modifier}")
            if component == "TimeInput":
                self.add_unresolved("component_semantics", call, "TimeInput text-entry layout is approximated using TimePicker")
            self._current_local_values = previous_local_values
            return self.wrap_visibility_lines(call, lines, indent, parameters)
        if component == "CircularProgressIndicator":
            semantic = call.get("semantic_arguments", {})
            stroke_width_handled = False
            stroke_width = None
            if isinstance(semantic, dict) and isinstance(semantic.get("strokeWidth"), dict):
                stroke_width_expression = semantic["strokeWidth"].get("expression")
                if isinstance(stroke_width_expression, str):
                    stroke_width = self.dimension_expression(stroke_width_expression, parameters)
                    stroke_width_handled = stroke_width is not None
            if stroke_width_handled:
                lines = [f"{prefix}Progress({{ value: 0, total: 1, type: ProgressType.Ring }})"]
                lines.append(f"{prefix}  .style({{ strokeWidth: {stroke_width}, status: ProgressStatus.LOADING }})")
            else:
                lines = [f"{prefix}LoadingProgress()"]
            color_handled = False
            if isinstance(semantic, dict) and isinstance(semantic.get("color"), dict):
                color_expression = semantic["color"].get("expression")
                if isinstance(color_expression, str):
                    translated_color = self.color_expression(color_expression, call, parameters)
                    if translated_color is not None:
                        lines.append(f"{prefix}  .color({translated_color})")
                        color_handled = True
            if not color_handled and "compose_theme_primary" in self.resource_names:
                lines.append(f"{prefix}  .color($r('app.color.compose_theme_primary'))")
                color_handled = True
            for modifier in self.modifier_lines(call, parameters) + self.android_page_visual_lines(call, component):
                lines.append(f"{prefix}  {modifier}")
            unsupported_progress_arguments = (
                isinstance(semantic, dict)
                and (
                    any(name in semantic for name in ("progress", "trackColor", "strokeCap"))
                    or ("strokeWidth" in semantic and not stroke_width_handled)
                    or ("color" in semantic and not color_handled)
                )
            )
            if unsupported_progress_arguments or not color_handled:
                self.add_unresolved("component_semantics", call, "Material progress defaults require version reconciliation")
            return self.wrap_visibility_lines(call, lines, indent, parameters)
        if component in {"Image", "Icon"}:
            previous_local_values = self._current_local_values
            local_values = call.get("local_values")
            if isinstance(local_values, dict) and all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in local_values.items()
            ):
                self._current_local_values = {**previous_local_values, **local_values}
            semantic = call.get("semantic_arguments", {})
            painter = semantic.get("painter") if isinstance(semantic, dict) else None
            painter_expression = painter.get("expression") if isinstance(painter, dict) else None
            if isinstance(painter, dict) and isinstance(painter.get("resolved_local_expression"), str):
                painter_expression = painter["resolved_local_expression"]
            positional = call.get("positional_arguments")
            if painter_expression is None and isinstance(positional, list) and positional:
                first = positional[0]
                if isinstance(first, dict):
                    if isinstance(first.get("resolved_local_expression"), str):
                        painter_expression = first["resolved_local_expression"]
                    elif isinstance(first.get("expression"), str):
                        painter_expression = first["expression"]
            if isinstance(painter_expression, str):
                if (
                    isinstance(local_values, dict)
                    and IDENTIFIER_PATTERN.fullmatch(painter_expression.strip()) is not None
                    and isinstance(local_values.get(painter_expression.strip()), str)
                ):
                    painter_expression = local_values[painter_expression.strip()]
            media = self.painter_resource_expression(str(painter_expression or ""), parameters)
            if media is None:
                self.add_unresolved("asset", call, f"{component} requires an approved asset key/hash or verified native symbol")
                self._current_local_values = previous_local_values
                return []
            tint_expression: str | None = None
            conditional_tint: tuple[str, str] | None = None
            tint = semantic.get("tint") if isinstance(semantic, dict) else None
            if isinstance(tint, dict) and isinstance(tint.get("expression"), str):
                tint_expression = tint["expression"]
            color_filter = semantic.get("colorFilter") if isinstance(semantic, dict) else None
            if isinstance(color_filter, dict) and isinstance(color_filter.get("expression"), str):
                color_filter_expression = color_filter["expression"].strip()
                match = re.fullmatch(r"ColorFilter\.tint\s*\(\s*(.+)\s*\)", color_filter_expression)
                if match is not None:
                    tint_expression = match.group(1).strip()
                elif IDENTIFIER_PATTERN.fullmatch(color_filter_expression) is not None and parameters.get(color_filter_expression) == "boolean":
                    color = self.color_expression("color", call, parameters)
                    if color is not None:
                        conditional_tint = (color_filter_expression, color)
                else:
                    conditional = kotlin_if_else_parts(color_filter_expression)
                    if conditional is not None:
                        condition, true_branch, false_branch = conditional
                        condition_expression = self.value_expression(condition, "boolean", parameters)
                        true_tint = re.fullmatch(r"ColorFilter\.tint\s*\(\s*(.+)\s*\)", true_branch.strip())
                        false_tint = re.fullmatch(r"ColorFilter\.tint\s*\(\s*(.+)\s*\)", false_branch.strip())
                        if condition_expression is not None and true_tint is not None and false_branch.strip() == "null":
                            color = self.color_expression(true_tint.group(1).strip(), call, parameters)
                            if color is not None:
                                conditional_tint = (condition_expression, color)
                        elif condition_expression is not None and false_tint is not None and true_branch.strip() == "null":
                            color = self.color_expression(false_tint.group(1).strip(), call, parameters)
                            if color is not None:
                                conditional_tint = (f"!({condition_expression})", color)
            primitive_resolution = call.get("primitive_mapping_resolution")
            imported_symbol = (
                primitive_resolution.get("imported_symbol")
                if isinstance(primitive_resolution, dict)
                else None
            )
            if (
                component == "Icon"
                and tint_expression is None
                and conditional_tint is None
                and imported_symbol == "androidx.compose.material3.Icon"
            ):
                tint_expression = "Color(0xFF49454F)"
            modifiers = self.modifier_lines(call, parameters) + self.android_page_visual_lines(call, component)
            if conditional_tint is not None:
                condition, color = conditional_tint
                lines = [f"{prefix}if ({condition}) {{"]
                lines.append(f"{prefix}  Image({media})")
                for tint_line in self.image_tint_lines(color, component == "Icon"):
                    lines.append(f"{prefix}    {tint_line}")
                for modifier in modifiers:
                    lines.append(f"{prefix}    {modifier}")
                lines.append(f"{prefix}}} else {{")
                lines.append(f"{prefix}  Image({media})")
                for modifier in modifiers:
                    lines.append(f"{prefix}    {modifier}")
                lines.append(f"{prefix}}}")
                self._current_local_values = previous_local_values
                return self.wrap_visibility_lines(call, lines, indent, parameters)
            lines = [f"{prefix}Image({media})"]
            if tint_expression is not None:
                color = self.color_expression(tint_expression, call, parameters)
                if color is None:
                    self.add_unresolved("semantic_argument", call, "image tint expression is not safely translated")
                else:
                    for tint_line in self.image_tint_lines(color, component == "Icon"):
                        lines.append(f"{prefix}  {tint_line}")
            for modifier in modifiers:
                lines.append(f"{prefix}  {modifier}")
            self._current_local_values = previous_local_values
            return self.wrap_visibility_lines(call, lines, indent, parameters)
        if component == "AsyncImage":
            semantic = call.get("semantic_arguments", {})
            placeholder = semantic.get("placeholder") if isinstance(semantic, dict) else None
            placeholder_expression = placeholder.get("expression") if isinstance(placeholder, dict) else None
            media_key = self.placeholder_resource_key(str(placeholder_expression or ""))
            if media_key is None:
                self.add_unresolved("asset", call, "AsyncImage dynamic model/placeholder requires network image or approved local placeholder reconciliation")
                lines = [f"{prefix}Blank()"]
            else:
                self.add_unresolved("asset", call, "AsyncImage dynamic model is emitted using an approved local placeholder")
                lines = [f"{prefix}Image($r('app.media.{media_key}'))"]
            for modifier in self.modifier_lines(call, parameters) + self.android_page_visual_lines(call, component):
                lines.append(f"{prefix}  {modifier}")
            return self.wrap_visibility_lines(call, lines, indent, parameters)
        self.add_unresolved("component", call, f"no compile-safe ArkUI emitter is available for {component}")
        return []

    def drawable_resource_expression(
        self,
        expression: str,
        parameters: dict[str, str] | None = None,
        seen_locals: set[str] | None = None,
    ) -> str | None:
        stripped = expression.strip()
        if seen_locals is None:
            seen_locals = set()
        if IDENTIFIER_PATTERN.fullmatch(stripped) is not None and stripped not in seen_locals:
            local_expression = self._current_local_values.get(stripped)
            if isinstance(local_expression, str):
                return self.drawable_resource_expression(local_expression, parameters, seen_locals | {stripped})
        conditional = kotlin_if_else_parts(stripped)
        if conditional is not None:
            condition, true_branch, false_branch = conditional
            condition_expression = self.value_expression(condition, "boolean", parameters or {})
            true_resource = self.drawable_resource_expression(true_branch, parameters, seen_locals)
            false_resource = self.drawable_resource_expression(false_branch, parameters, seen_locals)
            if condition_expression is not None and true_resource is not None and false_resource is not None:
                return f"({condition_expression} ? {true_resource} : {false_resource})"
        match = re.fullmatch(
            r"R\.(?:drawable|mipmap)\.([A-Za-z_][A-Za-z0-9_]*)",
            stripped,
        )
        if match is None:
            return None
        name = match.group(1)
        if f"media:{name}" not in self.resource_names:
            return None
        return f"$r('app.media.{name}')"

    def painter_resource_expression(
        self,
        expression: str,
        parameters: dict[str, str],
    ) -> str | None:
        conditional = kotlin_if_else_parts(expression.strip())
        if conditional is not None:
            condition, true_branch, false_branch = conditional
            condition_expression = self.value_expression(condition, "boolean", parameters)
            true_resource = self.painter_resource_expression(true_branch, parameters)
            false_resource = self.painter_resource_expression(false_branch, parameters)
            if condition_expression is not None and true_resource is not None and false_resource is not None:
                return f"({condition_expression} ? {true_resource} : {false_resource})"
        remembered = re.fullmatch(
            r"rememberAsyncImagePainter\s*\(\s*(.+?)\s*\)",
            expression.strip(),
            re.S,
        )
        if remembered is not None:
            return self.value_expression(remembered.group(1).strip(), "Resource", parameters)
        resource_arg = re.fullmatch(
            r"painterResource\s*\(\s*(?:id\s*=\s*)?(.+?)\s*\)",
            expression.strip(),
            re.S,
        )
        if resource_arg is not None:
            return self.value_expression(resource_arg.group(1).strip(), "Resource", parameters)
        match = re.fullmatch(
            r"painterResource\s*\(\s*(?:id\s*=\s*)?R\.drawable\.([A-Za-z_][A-Za-z0-9_]*)\s*\)",
            expression.strip(),
        )
        if match is None:
            return None
        name = match.group(1)
        if f"media:{name}" not in self.resource_names:
            return None
        return f"$r('app.media.{name}')"

    def placeholder_resource_key(self, expression: str) -> str | None:
        match = re.fullmatch(
            r"(?:debugPlaceholder|painterResource)\s*\((.*)\)",
            expression.strip(),
            re.S,
        )
        if match is None:
            return None
        positional, named = named_arguments(match.group(1))
        source = named.get("id") or named.get("debugPreview") or (positional[0] if positional else None)
        if source is None:
            return None
        resource = re.fullmatch(r"R\.drawable\.([A-Za-z_][A-Za-z0-9_]*)", source.strip())
        if resource is None:
            return None
        name = resource.group(1)
        if f"media:{name}" not in self.resource_names:
            return None
        return name

    def children_for(self, call: dict[str, Any]) -> list[dict[str, Any]]:
        return self._children.get(call["call_id"], [])

    def render_call_sequence(
        self,
        calls: list[dict[str, Any]],
        indent: int,
        definition_key: tuple[str, str],
        parameters: dict[str, str],
        parent_component: str | None = None,
    ) -> list[str]:
        lines: list[str] = []
        index = 0
        while index < len(calls):
            call = calls[index]
            next_call = calls[index + 1] if index + 1 < len(calls) else None
            if next_call is not None:
                paired = self.render_action_menu_anchor_pair(
                    call,
                    self.children_for(call),
                    next_call,
                    self.children_for(next_call),
                    indent,
                    definition_key,
                    parameters,
                    parent_component,
                )
                if paired is not None:
                    lines.extend(paired)
                    index += 2
                    continue
            lines.extend(
                self.render_call(
                    call,
                    self.children_for(call),
                    indent,
                    definition_key,
                    parameters,
                    parent_component,
                )
            )
            index += 1
        return lines

    def remembered_enum_type(
        self,
        name: str,
        parameters: dict[str, str],
    ) -> str | None:
        local_expression = self.local_value_expression(name, parameters)
        if local_expression is None:
            return None
        remembered_state = re.fullmatch(
            r"remember(?:Saveable)?\s*(?:\([^)]*\))?\s*\{\s*(mutableStateOf(?:<[^>]+>)?\s*\(.*\))\s*\}",
            local_expression.strip(),
            re.S,
        )
        if remembered_state is not None:
            local_expression = remembered_state.group(1).strip()
        state_constructor = re.fullmatch(r"mutableStateOf(?:<[^>]+>)?\s*\((.*)\)", local_expression.strip(), re.S)
        if state_constructor is None:
            return None
        initializer = state_constructor.group(1).strip()
        literal = re.fullmatch(r"(?:[A-Za-z_][A-Za-z0-9_]*\.)*([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)", initializer)
        if literal is None:
            return None
        enum_name = literal.group(1)
        entry_name = literal.group(2)
        if entry_name not in self.enum_classes.get(enum_name, set()):
            return None
        return enum_name

    def dropdown_item_collection_context(self, item: dict[str, Any]) -> tuple[str, str] | None:
        context = item.get("list_item_context")
        if not isinstance(context, dict):
            return None
        collection = context.get("collection")
        item_parameter = context.get("item_parameter")
        if not isinstance(collection, str) or not isinstance(item_parameter, str):
            return None
        return collection, item_parameter

    def dropdown_item_selection_targets(
        self,
        expression: str,
        item_parameter: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> tuple[str | None, str | None]:
        match = re.fullmatch(
            rf"\{{\s*([A-Za-z_][A-Za-z0-9_]*)(?:\.value)?\s*=\s*{re.escape(item_parameter)}\s*;?\s*([A-Za-z_][A-Za-z0-9_]*)(?:\.value)?\s*=\s*false\s*\}}",
            re.sub(r"\s+", " ", expression.strip()),
        )
        if match is None:
            return None, None
        value_target = self.state_field_expression(call, match.group(1), "string", parameters)
        expanded_target = self.state_field_expression(call, match.group(2), "boolean", parameters)
        return value_target, expanded_target

    def dropdown_menu_state_field(
        self,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> str | None:
        semantic = call.get("semantic_arguments", {})
        expanded = semantic.get("expanded") if isinstance(semantic, dict) else None
        expression = expanded.get("expression") if isinstance(expanded, dict) else None
        if not isinstance(expression, str):
            return None
        return self.state_field_access_expression(call, expression, "boolean", parameters)

    def render_exposed_dropdown_menu_box(
        self,
        call: dict[str, Any],
        children: list[dict[str, Any]],
        indent: int,
        parameters: dict[str, str],
    ) -> list[str] | None:
        previous_local_values = self._current_local_values
        local_values = call.get("local_values")
        if isinstance(local_values, dict) and all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in local_values.items()
        ):
            self._current_local_values = {**previous_local_values, **local_values}
        anchor = next((child for child in children if child.get("component") in {"OutlinedTextField", "TextField", "BasicTextField"}), None)
        item = next((child for child in children if child.get("component") == "DropdownMenuItem"), None)
        try:
            if anchor is None or item is None:
                return None
            collection_context = self.dropdown_item_collection_context(item)
            if collection_context is None:
                return None
            collection_source, item_parameter = collection_context
            options_array = self.value_expression(collection_source, "Array<string>", parameters)
            label_expression: str | None = None
            fallback_label_used = False
            enum_entries: list[str] | None = None
            if options_array is None:
                enum_match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\.entries", collection_source.strip())
                if enum_match is None:
                    return None
                enum_name = enum_match.group(1)
                raw_text_expression = str(item.get("semantic_arguments", {}).get("text", {}).get("expression", ""))
                property_match = re.fullmatch(
                    rf"\{{\s*Text\(\s*{re.escape(item_parameter)}\.([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*\}}",
                    re.sub(r"\s+", " ", raw_text_expression),
                )
                property_name = property_match.group(1) if property_match is not None else "label"
                mapping = self.enum_string_properties.get(enum_name, {}).get(property_name)
                if not mapping:
                    return None
                enum_entries = list(mapping.keys())
                options_array = "[" + ", ".join(arkts_string(mapping[entry]) for entry in enum_entries) + "]"
                label_expression = "optionLabel"
            else:
                label_expression = self.text_slot_value_expression(
                    item.get("semantic_arguments", {}).get("text", {}).get("expression", ""),
                    {**parameters, item_parameter: "string"},
                )
                if label_expression is None:
                    label_expression = item_parameter
                    fallback_label_used = True
            on_click_expression = item.get("semantic_arguments", {}).get("onClick", {}).get("expression", "")
            value_target, expanded_target = self.dropdown_item_selection_targets(
                str(on_click_expression),
                item_parameter,
                call,
                parameters,
            )
            if value_target is None or expanded_target is None:
                return None
            anchor_value = anchor.get("semantic_arguments", {}).get("value", {}).get("expression", "")
            current_value = self.state_field_access_expression(call, str(anchor_value), "string", parameters)
            if current_value is None:
                enum_property = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)", str(anchor_value).strip())
                if enum_property is not None:
                    enum_type = self.remembered_enum_type(enum_property.group(1), parameters)
                    state_value = self.state_field_expression(call, enum_property.group(1), "string", parameters)
                    if enum_type is not None and state_value is not None:
                        current_value = self.render_enum_string_property_expression(
                            state_value,
                            enum_type,
                            enum_property.group(2),
                        )
            if current_value is None:
                current_value = self.value_expression(str(anchor_value), "string", parameters)
            if current_value is None:
                return None
            prefix = " " * indent
            if enum_entries is None:
                select_expression = f"{options_array}.map(({item_parameter}: string): SelectOption => ({{ value: {label_expression} }}))"
                on_select_line = (
                    f"{prefix}  .onSelect((index: number, value: string): void => {{ {value_target} = value; {expanded_target} = false }})"
                )
            else:
                select_expression = f"{options_array}.map((optionLabel: string): SelectOption => ({{ value: optionLabel }}))"
                branches = []
                for index, entry in enumerate(enum_entries):
                    condition = "if" if index == 0 else "else if"
                    branches.append(f"{condition} (index === {index}) {{ {value_target} = {arkts_string(entry)}; {expanded_target} = false }}")
                branches.append(f"else {{ {expanded_target} = false }}")
                on_select_line = f"{prefix}  .onSelect((index: number, value: string): void => {{ {' '.join(branches)} }})"
            lines = [
                f"{prefix}Select({select_expression})",
                f"{prefix}  .value({current_value})",
                on_select_line,
            ]
            enabled_line = self.enabled_line(anchor, parameters)
            if enabled_line is not None:
                lines.append(f"{prefix}  {enabled_line}")
            for modifier in self.modifier_lines(anchor, parameters):
                if ".menuAnchor" in modifier:
                    continue
                lines.append(f"{prefix}  {modifier}")
            if fallback_label_used:
                self.add_unresolved(
                    "component_semantics",
                    call,
                    "dropdown item label decoration was reduced to its primary item value",
                )
            return self.wrap_visibility_lines(call, lines, indent, parameters)
        finally:
            self._current_local_values = previous_local_values

    def render_action_menu_anchor_pair(
        self,
        anchor_call: dict[str, Any],
        anchor_children: list[dict[str, Any]],
        menu_call: dict[str, Any],
        menu_children: list[dict[str, Any]],
        indent: int,
        definition_key: tuple[str, str],
        parameters: dict[str, str],
        parent_component: str | None,
    ) -> list[str] | None:
        previous_local_values = self._current_local_values
        local_values = menu_call.get("local_values")
        if isinstance(local_values, dict) and all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in local_values.items()
        ):
            self._current_local_values = {**previous_local_values, **local_values}
        if menu_call.get("component") != "DropdownMenu":
            return None
        try:
            state_field = self.dropdown_menu_state_field(menu_call, parameters)
            if state_field is None:
                return None
            anchor_lines: list[str] | None = None
            if anchor_call.get("component") in BUTTON_CONTAINER_COMPONENTS:
                anchor_lines = self.render_call(
                    anchor_call,
                    anchor_children,
                    indent,
                    definition_key,
                    parameters,
                    parent_component,
                )
            else:
                custom = anchor_call.get("custom_composable")
                definitions = custom.get("definitions") if isinstance(custom, dict) else None
                if isinstance(definitions, list) and len(definitions) == 1:
                    definition = definitions[0]
                    callee = (definition.get("source"), definition.get("composable"))
                    if callee in set(self.reached_keys) and (definition_key, callee) not in self.cycle_edges:
                        arguments = self.call_arguments(anchor_call, callee, definition_key, parameters)
                        if arguments is not None:
                            anchor_lines = self.inline_project_component_single_root_lines(
                                anchor_call,
                                indent,
                                definition_key,
                                parameters,
                                callee,
                                arguments,
                                parent_component,
                                allowed_components=BUTTON_CONTAINER_COMPONENTS,
                            )
            if anchor_lines is None:
                return None
            menu_items: list[str] = []
            expanded_menu_children: list[tuple[dict[str, Any], bool, dict[str, str]]] = []
            for item in menu_children:
                slot = item.get("slot_invocation")
                slot_name = slot.get("name") if isinstance(slot, dict) else None
                if isinstance(slot_name, str) and slot_name in self._current_slot_contexts:
                    slot_children, _, _, slot_parameters = self._current_slot_contexts[slot_name]
                    expanded_menu_children.extend((slot_child, True, slot_parameters) for slot_child in slot_children)
                    continue
                expanded_menu_children.append((item, False, parameters))
            for item, from_slot, item_parameters in expanded_menu_children:
                if item.get("component") == "DropdownMenuItem":
                    text = self.text_slot_value_expression(
                        item.get("semantic_arguments", {}).get("text", {}).get("expression", ""),
                        item_parameters,
                    )
                    action = self.state_field_set_callback_expression(
                        str(item.get("semantic_arguments", {}).get("onClick", {}).get("expression", "")),
                        item,
                        item_parameters,
                    )
                    if action is None and from_slot:
                        action = self.slot_menu_item_close_callback_expression(
                            str(item.get("semantic_arguments", {}).get("onClick", {}).get("expression", "")),
                            state_field,
                            item,
                            item_parameters,
                        )
                else:
                    resolved_item = self.project_component_single_root_menu_item(
                        item,
                        definition_key,
                        item_parameters,
                    )
                    if resolved_item is None:
                        return None
                    text, action = resolved_item
                if text is None or action is None:
                    return None
                menu_items.append(f"{{ value: {text}, action: {action} }}")
            if not menu_items:
                return None
            prefix = " " * indent
            anchor_lines.append(f"{prefix}  .bindMenu({state_field}, [")
            for index, item_line in enumerate(menu_items):
                suffix = "," if index + 1 < len(menu_items) else ""
                anchor_lines.append(f"{prefix}    {item_line}{suffix}")
            anchor_lines.append(f"{prefix}  ])")
            return anchor_lines
        finally:
            self._current_local_values = previous_local_values

    def slot_menu_item_close_callback_expression(
        self,
        expression: str,
        state_field: str,
        call: dict[str, Any],
        parameters: dict[str, str],
    ) -> str | None:
        stripped = expression.strip()
        lambda_match = re.fullmatch(r"\{\s*(.*?)\s*\}", stripped, re.S)
        if lambda_match is None:
            return None
        body = re.sub(r"\s+", " ", lambda_match.group(1).strip())
        callback_clauses: list[str] = []
        remainder = body
        while True:
            remainder = remainder.lstrip()
            if remainder.startswith(";"):
                remainder = remainder[1:].strip()
            callback_match = re.match(
                r"([A-Za-z_][A-Za-z0-9_]*)(?:\s*\.\s*invoke)?\(\s*\)\s*",
                remainder,
            )
            if callback_match is None:
                break
            callback_name = callback_match.group(1)
            remainder = remainder[callback_match.end() :].strip()
            if not remainder:
                callback_clauses.append(f"{state_field} = false")
                return f"() => {{ {'; '.join(callback_clauses)} }}"
            translated_callback = self.callback_argument_expression(
                callback_name,
                "() => void",
                call,
                parameters,
            )
            if translated_callback is None:
                return None
            callback_clauses.append(f"{translated_callback}()")
        return None

    def split_top_level_items(self, value: str, delimiter: str) -> list[str]:
        items: list[str] = []
        current: list[str] = []
        depth = 0
        quote: str | None = None
        escaped = False
        for character in value:
            if quote is not None:
                current.append(character)
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    quote = None
                continue
            if character in {'"', "'"}:
                quote = character
                current.append(character)
                continue
            if character in "([{<":
                depth += 1
            elif character in ")]}>":
                depth = max(0, depth - 1)
            if character == delimiter and depth == 0:
                chunk = "".join(current).strip()
                if chunk:
                    items.append(chunk)
                current = []
                continue
            current.append(character)
        chunk = "".join(current).strip()
        if chunk:
            items.append(chunk)
        return items

    def ensure_arkts_interface(self, shape: str, hint: str) -> str:
        normalized_shape = shape.strip()
        existing = self._arkts_interface_names.get(normalized_shape)
        if existing is not None:
            return existing
        base_name = f"{pascal_identifier(hint)}Model"
        count = self._arkts_interface_name_counts.get(base_name, 0)
        self._arkts_interface_name_counts[base_name] = count + 1
        name = base_name if count == 0 else f"{base_name}{count + 1}"
        body = normalized_shape[1:-1].strip()
        properties: list[tuple[str, bool, str]] = []
        if body:
            for item in self.split_top_level_items(body, ";"):
                match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)(\?)?\s*:\s*(.+)", item)
                if match is None:
                    continue
                property_name = match.group(1)
                optional = match.group(2) == "?"
                property_type = self.rendered_arkts_type(match.group(3).strip(), f"{hint}_{property_name}")
                properties.append((property_name, optional, property_type))
        self._arkts_interface_names[normalized_shape] = name
        self._arkts_interfaces.append((name, properties))
        return name

    def rendered_arkts_type(self, type_expression: str, hint: str) -> str:
        stripped = type_expression.strip()
        union_parts = self.split_top_level_items(stripped, "|")
        if len(union_parts) > 1:
            return " | ".join(self.rendered_arkts_type(part, hint) for part in union_parts)
        if stripped == "unknown":
            return "Object"
        if stripped == "unknown[]":
            return "Array<Object>"
        if stripped.endswith("[]"):
            return f"Array<{self.rendered_arkts_type(stripped[:-2].strip(), hint)}>"
        array_match = re.fullmatch(r"Array<(.+)>", stripped, re.S)
        if array_match is not None:
            return f"Array<{self.rendered_arkts_type(array_match.group(1).strip(), hint + '_item')}>"
        if stripped.startswith("{") and stripped.endswith("}"):
            return self.ensure_arkts_interface(stripped, hint)
        return stripped

    def render_definition(self, key: tuple[str, str]) -> list[str]:
        calls = self.calls_by_definition.get(key, [])
        self._children: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
        call_ids = {item["call_id"] for item in calls}
        for call in calls:
            parent = call.get("parent_call_id")
            if parent is not None and parent not in call_ids:
                self.add_unresolved("hierarchy", call, "parent call is outside the selected definition")
                parent = None
            self._children[parent].append(call)
        root_key = (self.root["source"], self.root["composable"])
        if key == root_key:
            parameters = list(getattr(self, "_root_public_parameters", []))
        else:
            parameters = self.definition_parameters(key)
        parameter_types = {item["name"]: item["type"] for item in parameters}
        parameter_enum_types = {
            item["name"]: item["enum_type"]
            for item in parameters
            if isinstance(item.get("enum_type"), str)
        }
        for parameter in self.definitions[key]["parameters"]:
            if (
                isinstance(parameter, dict)
                and isinstance(parameter.get("name"), str)
                and isinstance(parameter.get("type"), str)
                and is_compose_modifier_type(parameter["type"])
            ):
                parameter_types[parameter["name"]] = "Modifier"
        declaration = ", ".join(
            (
                f"{item['name']}: {self.rendered_arkts_type(item['type'], item['name'])} = {item['default_ts']}"
                if isinstance(item.get("default_ts"), str)
                else f"{item['name']}: {self.rendered_arkts_type(item['type'], item['name'])}"
            )
            for item in parameters
        )
        lines = ["  @Builder", f"  private {builder_name(*key)}({declaration}) {{"]
        previous_defaults = self._current_parameter_defaults
        previous_enum_parameters = self._current_enum_parameter_types
        previous_definition_key = self._current_definition_key
        self._current_definition_key = key
        self._current_parameter_defaults = {
            parameter["name"]: parameter["default"]
            for parameter in self.definitions[key]["parameters"]
            if isinstance(parameter, dict)
            and isinstance(parameter.get("name"), str)
            and isinstance(parameter.get("default"), str)
        }
        self._current_enum_parameter_types = {**previous_enum_parameters, **parameter_enum_types}
        try:
            lines.extend(self.render_call_sequence(self._children[None], 4, key, parameter_types))
        finally:
            self._current_parameter_defaults = previous_defaults
            self._current_enum_parameter_types = previous_enum_parameters
            self._current_definition_key = previous_definition_key
        lines.append("  }")
        return lines

    def render(self) -> str:
        root_key = (self.root["source"], self.root["composable"])
        struct_name = f"Generated{pascal_identifier(self.root['composable'])}"
        root_public_parameters = self.root_public_parameters(root_key)
        self._root_public_parameters = root_public_parameters
        root_public_parameter_names = {
            parameter["name"]: parameter["public_name"]
            for parameter in root_public_parameters
        }
        ordered = [root_key] + sorted(key for key in self.reached_keys if key != root_key)
        definition_sections: list[list[str]] = []
        for key in ordered:
            definition_sections.append(self.render_definition(key))
        selected_call_ids = {call["call_id"] for call in self.selected_calls}
        for call_id, component in self.android_page_by_call_id.items():
            if call_id in selected_call_ids and call_id not in self.android_page_processed_call_ids:
                self.add_unresolved(
                    "android_page_mapping",
                    next(call for call in self.selected_calls if call["call_id"] == call_id),
                    "Android page facts mapped to a source call that emitted no visual ArkUI boundary",
                    page_component_id=component["id"],
                )
        lines = [
            (
                "// Generated from an audited Compose semantic contract and Android page facts."
                if self.android_page_input is not None
                else "// Generated from an audited Compose semantic contract."
            ),
            "// Unresolved behavior is recorded in the paired .migration manifest.",
            "",
        ]
        if self._uses_resource_manager:
            lines.extend(["import resourceManager from '@ohos.resourceManager';", ""])
        if self._uses_drawing_color_filter:
            lines.extend(["import drawing from '@ohos.graphics.drawing';", ""])
        if self._uses_fallback_list_item:
            lines.extend([
                f"interface {FALLBACK_LIST_ITEM_TYPE} {{",
                "  readonly __opaque?: string",
                "}",
                "",
            ])
        for target_type in sorted(self.data_class_interface_properties):
            lines.append(f"interface {target_type} {{")
            for property_item in self.data_class_interface_properties[target_type]:
                suffix = "?" if property_item.get("optional") else ""
                lines.append(f"  {property_item['name']}{suffix}: {property_item['type']}")
            lines.extend(("}", ""))
        for interface_name, properties in self._arkts_interfaces:
            lines.append(f"interface {interface_name} {{")
            for property_name, optional, property_type in properties:
                lines.append(f"  {property_name}{'?' if optional else ''}: {property_type}")
            lines.extend(("}", ""))
        lines.extend([
            "@Component",
            f"export struct {struct_name} {{",
        ])
        for parameter in root_public_parameters:
            lines.append(
                f"  {parameter['public_name']}: "
                f"{self.rendered_arkts_type(parameter['type'], parameter['name'])} = {parameter['default_ts']}"
            )
        if root_public_parameters and self.state_fields:
            lines.append("")
        for field in sorted(self.state_fields.values(), key=lambda item: item["name"]):
            initial_value = field["initial_value"]
            if IDENTIFIER_PATTERN.fullmatch(initial_value) is not None:
                public_name = root_public_parameter_names.get(initial_value)
                if public_name is not None:
                    initial_value = f"this.{public_name}"
            lines.append(f"  @State {field['name']}: {field['type']} = {initial_value}")
        if root_public_parameters or self.state_fields:
            lines.append("")
        if self.verified_font_faces:
            lines.extend([
                "  aboutToAppear(): void {",
                "    const fontManager = this.getUIContext().getFont()",
            ])
            for face in self.verified_font_faces:
                lines.append(
                    "    fontManager.registerFont({ familyName: "
                    f"{arkts_string(face['alias'])}, familySrc: $rawfile({arkts_string(face['rawfile'])}) }})"
                )
            lines.extend(("  }", ""))
        if self._uses_resource_manager:
            lines.extend([
                "  private isSystemInDarkTheme(): boolean {",
                "    const colorMode = this.getUIContext()",
                "      .getHostContext()",
                "      ?.resourceManager.getConfigurationSync().colorMode;",
                "    return colorMode === resourceManager.ColorMode.DARK;",
                "  }",
                "",
            ])
        if self._uses_resource_str_resolver:
            lines.extend([
                "  private resolveResourceStr(value: ResourceStr | null | undefined): string {",
                "    if (value === null || value === undefined) {",
                "      return ''",
                "    }",
                "    if (typeof value === 'string') {",
                "      return value",
                "    }",
                "    const manager = this.getUIContext().getHostContext()?.resourceManager",
                "    return manager === undefined ? '' : manager.getStringSync(value.id)",
                "  }",
                "",
            ])
        if self._uses_greeting_helper:
            lines.extend([
                "  private getGreetingMessage(): string {",
                "    const currentHour = new Date().getHours()",
                "    if (currentHour >= 5 && currentHour <= 11) {",
                "      return 'Good Morning'",
                "    }",
                "    if (currentHour >= 12 && currentHour <= 16) {",
                "      return 'Good Afternoon'",
                "    }",
                "    if (currentHour >= 17 && currentHour <= 20) {",
                "      return 'Good Evening'",
                "    }",
                "    return 'Good Night'",
                "  }",
                "",
            ])
        if self._uses_rupee_formatter:
            lines.extend([
                "  private formatRupees(value: string | number | null | undefined): string {",
                "    if (value === null || value === undefined) {",
                "      return 'null'",
                "    }",
                "    const text = String(value).trim()",
                "    const negative = text.startsWith('-')",
                "    const unsigned = negative ? text.slice(1) : text",
                "    const pieces = unsigned.split('.')",
                "    let whole = pieces[0].replace(/[^0-9]/g, '')",
                "    if (whole.length === 0) {",
                "      whole = '0'",
                "    }",
                "    let grouped = whole",
                "    if (whole.length > 3) {",
                "      const lastThree = whole.slice(-3)",
                "      const leading = whole.slice(0, -3)",
                "      const groups: string[] = []",
                "      for (let index = leading.length; index > 0; index -= 2) {",
                "        groups.unshift(leading.slice(Math.max(0, index - 2), index))",
                "      }",
                "      grouped = groups.join(',') + ',' + lastThree",
                "    }",
                "    const fractionSource = pieces.length > 1 ? pieces[1].replace(/[^0-9]/g, '') : ''",
                "    const fraction = fractionSource.length > 0 ? '.' + fractionSource : ''",
                "    return (negative ? '- ₹ ' : '₹ ') + grouped + fraction",
                "  }",
                "",
            ])
        if self._uses_android_color_parser:
            lines.extend([
                "  private parseAndroidColor(value: string | null | undefined, defaultColor: string): string {",
                "    if (value === null || value === undefined) {",
                "      return defaultColor",
                "    }",
                "    const normalized = value.trim()",
                "    if (normalized.length === 0) {",
                "      return defaultColor",
                "    }",
                "    if (/^#[0-9A-Fa-f]{6}$/.test(normalized)) {",
                "      return '#FF' + normalized.slice(1).toUpperCase()",
                "    }",
                "    if (/^#[0-9A-Fa-f]{8}$/.test(normalized)) {",
                "      return '#' + normalized.slice(1).toUpperCase()",
                "    }",
                "    const named = new Map<string, string>([",
                "      ['black', '#FF000000'],",
                "      ['blue', '#FF0000FF'],",
                "      ['cyan', '#FF00FFFF'],",
                "      ['darkgray', '#FF444444'],",
                "      ['darkgrey', '#FF444444'],",
                "      ['gray', '#FF888888'],",
                "      ['grey', '#FF888888'],",
                "      ['green', '#FF00FF00'],",
                "      ['lightgray', '#FFCCCCCC'],",
                "      ['lightgrey', '#FFCCCCCC'],",
                "      ['magenta', '#FFFF00FF'],",
                "      ['red', '#FFFF0000'],",
                "      ['transparent', '#00000000'],",
                "      ['white', '#FFFFFFFF'],",
                "      ['yellow', '#FFFFFF00']",
                "    ])",
                "    return named.get(normalized.toLowerCase()) ?? defaultColor",
                "  }",
                "",
                "  private withAlpha(color: string, alpha: number): string {",
                "    const clamped = Math.max(0, Math.min(1, alpha))",
                "    const alphaHex = Math.round(clamped * 255).toString(16).toUpperCase().padStart(2, '0')",
                "    return '#' + alphaHex + color.slice(3).toUpperCase()",
                "  }",
                "",
            ])
        lines.extend([
            "  build() {",
            f"    this.{builder_name(*root_key)}({', '.join('this.' + parameter['public_name'] for parameter in root_public_parameters)})",
            "  }",
            "",
        ])
        for index, section in enumerate(definition_sections):
            if index:
                lines.append("")
            lines.extend(section)
        lines.extend(("}", ""))
        return "\n".join(lines)


def snake_name(value: str) -> str:
    first = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", value)
    second = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", first)
    return re.sub(r"[^A-Za-z0-9]+", "_", second).strip("_").lower()


def load_theme_resources(target: Path, module: str) -> tuple[set[str], dict[str, str]]:
    resources: set[str] = set()
    string_values: dict[str, str] = {}
    manifest_path = target / ".migration" / "compose-theme-resources.json"
    if manifest_path.exists():
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise ArkUIPageError("theme resource manifest is not a regular file")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ArkUIPageError(f"theme resource manifest is invalid: {error}") from error
        if isinstance(manifest, dict) and manifest.get("module") == module:
            outputs = manifest.get("outputs")
            names = manifest.get("generated_resource_names")
            if not isinstance(outputs, dict) or not isinstance(names, dict):
                raise ArkUIPageError("theme resource manifest outputs are invalid")
            for relative, metadata in outputs.items():
                if not isinstance(relative, str) or not isinstance(metadata, dict) or not isinstance(metadata.get("sha256"), str):
                    raise ArkUIPageError("theme resource manifest output entry is invalid")
                destination = target / relative
                if not destination.is_file() or destination.is_symlink() or sha256_file(destination) != metadata["sha256"]:
                    raise ArkUIPageError(f"generated theme resource changed after generation: {relative}")
                generated = names.get(relative, [])
                if not isinstance(generated, list) or not all(isinstance(item, str) for item in generated):
                    raise ArkUIPageError("theme resource manifest generated names are invalid")
                resources.update(generated)

    string_path = target / "AppScope/resources/base/element/string.json"
    if string_path.exists():
        if string_path.is_symlink() or not string_path.is_file():
            raise ArkUIPageError("string resource file is not a regular file")
        try:
            strings = json.loads(string_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ArkUIPageError(f"string resource file is invalid: {error}") from error
        values = strings.get("string") if isinstance(strings, dict) else None
        if not isinstance(values, list):
            raise ArkUIPageError("string resource file must contain a string array")
        for item in values:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                resources.add(f"string:{item['name']}")
                if isinstance(item.get("value"), str):
                    string_values[item["name"]] = item["value"]
    media_root = target / module / "src/main/resources/base/media"
    if media_root.exists():
        if media_root.is_symlink() or not media_root.is_dir():
            raise ArkUIPageError("base media resource directory is not a regular directory")
        for media in media_root.iterdir():
            if media.is_file() and not media.is_symlink() and RESOURCE_NAME_PATTERN.fullmatch(media.stem) is not None:
                resources.add(f"media:{media.stem}")
    return resources, string_values


def normalized_font_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def font_key_family_and_weight(key: str) -> tuple[str, int]:
    lowered = key.lower()
    for suffix, weight in sorted(FONT_KEY_SUFFIXES.items(), key=lambda item: -len(item[0])):
        match = re.fullmatch(rf"(.+?)(?:[_-]?{re.escape(suffix)})", lowered)
        if match is not None and match.group(1):
            return match.group(1).rstrip("_-"), weight
    return lowered, 400


def expression_font_weight(expression: str, key: str, fallback: int) -> int:
    match = re.search(
        rf"R\.font\.{re.escape(key)}\s*,\s*FontWeight\.([A-Za-z_][A-Za-z0-9_]*)",
        expression,
        re.S,
    )
    if match is None:
        return fallback
    return FONT_WEIGHT_VALUES.get(match.group(1), fallback)


def load_verified_font_faces(
    target: Path,
    module: str,
    contract: dict[str, Any],
) -> list[dict[str, Any]]:
    ledger_path = target / ".migration" / "assets.json"
    if not ledger_path.exists():
        return []
    if ledger_path.is_symlink() or not ledger_path.is_file():
        raise ArkUIPageError("asset ledger is not a regular file")
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ArkUIPageError(f"asset ledger is invalid: {error}") from error
    assets = ledger.get("assets") if isinstance(ledger, dict) else None
    if (
        not isinstance(ledger, dict)
        or ledger.get("schema") != "android-to-harmony.asset-ledger.v1"
        or not isinstance(assets, dict)
    ):
        raise ArkUIPageError("asset ledger has an unsupported schema")

    inventory = (
        contract.get("ui", {}).get("compose_theme_token_inventory", {})
        if isinstance(contract.get("ui"), dict)
        else {}
    )
    tokens = inventory.get("tokens") if isinstance(inventory, dict) else None
    if not isinstance(tokens, list):
        return []
    faces: dict[tuple[str, int], dict[str, Any]] = {}
    for token in tokens:
        if (
            not isinstance(token, dict)
            or token.get("kind") not in {"font", "font_family"}
            or not isinstance(token.get("name"), str)
            or not isinstance(token.get("font_resource_keys"), list)
        ):
            continue
        expression = token.get("expression") if isinstance(token.get("expression"), str) else ""
        token_name = token["name"]
        token_family_name = re.sub(r"fontfamily$", "", token_name, flags=re.I)
        for key in token["font_resource_keys"]:
            if not isinstance(key, str) or RESOURCE_NAME_PATTERN.fullmatch(key) is None:
                continue
            family_key, suffix_weight = font_key_family_and_weight(key)
            weight = expression_font_weight(expression, key, suffix_weight)
            matching: list[tuple[str, dict[str, Any]]] = []
            for relative, metadata in assets.items():
                if not isinstance(relative, str) or not isinstance(metadata, dict):
                    continue
                asset_path = metadata.get("asset_path")
                if (
                    not isinstance(asset_path, str)
                    or Path(asset_path).stem != key
                    or Path(asset_path).parent.as_posix().split("/")[-2:] != ["res", "font"]
                ):
                    continue
                matching.append((relative, metadata))
            if len(matching) != 1:
                continue
            relative, metadata = matching[0]
            destination = target / relative
            rawfile_root = target / module / "src/main/resources/rawfile"
            try:
                rawfile_relative = destination.relative_to(rawfile_root).as_posix()
            except ValueError:
                continue
            expected_sha256 = metadata.get("destination_sha256")
            if (
                destination.is_symlink()
                or not destination.is_file()
                or not isinstance(expected_sha256, str)
                or SHA256_PATTERN.fullmatch(expected_sha256) is None
                or sha256_file(destination) != expected_sha256
            ):
                raise ArkUIPageError(f"verified font asset changed after copy: {relative}")
            family = pascal_identifier(family_key)
            alias = f"{family}{weight}"
            match_names = {
                normalized_font_name(family_key),
                normalized_font_name(family),
                normalized_font_name(token_name),
                normalized_font_name(token_family_name),
            }
            faces[(alias, weight)] = {
                "alias": alias,
                "weight": weight,
                "rawfile": rawfile_relative,
                "target_path": relative,
                "sha256": expected_sha256,
                "match_names": sorted(name for name in match_names if name),
            }
    return sorted(faces.values(), key=lambda item: (item["alias"], item["weight"]))


def load_typography_font_roles(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    inventory = (
        contract.get("ui", {}).get("compose_theme_token_inventory", {})
        if isinstance(contract.get("ui"), dict)
        else {}
    )
    typography_sets = inventory.get("typography_sets") if isinstance(inventory, dict) else None
    if not isinstance(typography_sets, list):
        return {}
    roles: dict[str, dict[str, Any]] = {}
    for typography_set in typography_sets:
        styles = typography_set.get("styles") if isinstance(typography_set, dict) else None
        if not isinstance(styles, dict):
            continue
        for role_name, style in styles.items():
            properties = style.get("properties") if isinstance(style, dict) else None
            if not isinstance(role_name, str) or not isinstance(properties, dict):
                continue
            family_property = properties.get("fontFamily")
            resolved = family_property.get("resolved_token") if isinstance(family_property, dict) else None
            family_name = resolved.get("name") if isinstance(resolved, dict) else None
            weight_property = properties.get("fontWeight")
            weight_expression = (
                weight_property.get("expression") if isinstance(weight_property, dict) else None
            )
            weight_match = (
                re.fullmatch(r"FontWeight\.([A-Za-z_][A-Za-z0-9_]*)", weight_expression.strip())
                if isinstance(weight_expression, str)
                else None
            )
            if isinstance(family_name, str):
                roles[snake_name(role_name)] = {
                    "family": family_name,
                    "weight": FONT_WEIGHT_VALUES.get(weight_match.group(1), 400) if weight_match else 400,
                }
    return roles


def load_static_theme_tokens(contract: dict[str, Any]) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    inventory = (
        contract.get("ui", {})
        .get("compose_theme_token_inventory", {})
        if isinstance(contract.get("ui"), dict)
        else {}
    )
    tokens = inventory.get("tokens") if isinstance(inventory, dict) else None
    if not isinstance(tokens, list):
        return {}, {}, {}
    dimension_candidates: dict[str, set[str]] = defaultdict(set)
    number_candidates: dict[str, set[str]] = defaultdict(set)
    color_candidates: dict[str, set[str]] = defaultdict(set)
    for token in tokens:
        if not isinstance(token, dict) or not isinstance(token.get("name"), str):
            continue
        name = token["name"]
        kind = token.get("kind")
        if kind == "dimension":
            dimensions = token.get("dimensions")
            if not isinstance(dimensions, list) or len(dimensions) != 1:
                continue
            dimension = dimensions[0]
            if not isinstance(dimension, dict) or not isinstance(dimension.get("value"), str):
                continue
            if decimal_from_literal(dimension["value"]) is not None:
                dimension_candidates[name].add(dimension["value"])
        elif kind == "number":
            value = token.get("value") if isinstance(token.get("value"), str) else None
            if value is None and isinstance(token.get("expression"), str):
                value = number_value(token["expression"])
            if value is not None and decimal_from_literal(value) is not None:
                number_candidates[name].add(value)
        elif kind == "color" and isinstance(token.get("argb_hex"), str):
            argb_hex = token["argb_hex"].upper()
            if re.fullmatch(r"#[0-9A-F]{8}", argb_hex) is not None:
                color_candidates[name].add(argb_hex)
    extended_sets = inventory.get("extended_color_sets") if isinstance(inventory, dict) else None
    if isinstance(extended_sets, list):
        for item in extended_sets:
            roles = item.get("roles") if isinstance(item, dict) else None
            if not isinstance(roles, dict):
                continue
            for role_name, role in roles.items():
                if not isinstance(role_name, str) or not isinstance(role, dict):
                    continue
                resolved = role.get("resolved_token")
                if not isinstance(resolved, dict) or resolved.get("status") != "resolved_unique":
                    continue
                argb_hex = resolved.get("argb_hex")
                if isinstance(argb_hex, str) and re.fullmatch(r"#[0-9A-Fa-f]{8}", argb_hex) is not None:
                    color_candidates[f"MaterialTheme.extendedColors.{role_name}"].add(argb_hex.upper())
    dimensions = {
        name: next(iter(values))
        for name, values in dimension_candidates.items()
        if len(values) == 1
    }
    numbers = {
        name: next(iter(values))
        for name, values in number_candidates.items()
        if len(values) == 1
    }
    colors = {
        name: next(iter(values))
        for name, values in color_candidates.items()
        if len(values) == 1
    }
    return dimensions, numbers, colors


def load_kotlin_data_classes(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    ui = contract.get("ui")
    inventory = ui.get("kotlin_data_class_inventory") if isinstance(ui, dict) else None
    classes = inventory.get("classes") if isinstance(inventory, dict) else None
    if not isinstance(classes, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in classes:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            result.setdefault(item["name"], item)
    return result


def load_kotlin_enums(contract: dict[str, Any]) -> dict[str, set[str]]:
    ui = contract.get("ui")
    inventory = ui.get("kotlin_enum_inventory") if isinstance(ui, dict) else None
    classes = inventory.get("classes") if isinstance(inventory, dict) else None
    if not isinstance(classes, list):
        return {}
    result: dict[str, set[str]] = {}
    for item in classes:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not isinstance(item.get("values"), list):
            continue
        values = {value for value in item["values"] if isinstance(value, str)}
        if values:
            result.setdefault(item["name"], set()).update(values)
    return result


def load_kotlin_enum_string_properties(contract: dict[str, Any]) -> dict[str, dict[str, dict[str, str]]]:
    ui = contract.get("ui")
    inventory = ui.get("kotlin_enum_inventory") if isinstance(ui, dict) else None
    classes = inventory.get("classes") if isinstance(inventory, dict) else None
    if not isinstance(classes, list):
        return {}
    result: dict[str, dict[str, dict[str, str]]] = {}
    for item in classes:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        properties = item.get("string_properties")
        if not isinstance(properties, dict):
            continue
        rendered_properties: dict[str, dict[str, str]] = {}
        for property_name, mapping in properties.items():
            if not isinstance(property_name, str) or not isinstance(mapping, dict):
                continue
            rendered = {
                entry: value
                for entry, value in mapping.items()
                if isinstance(entry, str) and isinstance(value, str)
            }
            if rendered:
                rendered_properties[property_name] = rendered
        if rendered_properties:
            result[item["name"]] = rendered_properties
    return result


def load_route_symbols(contract: dict[str, Any]) -> dict[str, str]:
    ui = contract.get("ui")
    routes = ui.get("routes") if isinstance(ui, dict) else None
    if not isinstance(routes, list):
        return {}
    result: dict[str, str] = {}
    for item in routes:
        if not isinstance(item, dict):
            continue
        symbol = item.get("symbol")
        route = item.get("route")
        if not isinstance(symbol, str) or not isinstance(route, str) or not symbol.endswith(".route"):
            continue
        result[symbol] = route
        result[symbol[: -len(".route")]] = route
    return result


def validate_previous(
    target: Path,
    output_path: Path,
    manifest_path: Path,
    root: dict[str, str],
    module: str,
    force: bool,
) -> None:
    output_exists = output_path.exists()
    manifest_exists = manifest_path.exists()
    if not output_exists and not manifest_exists:
        return
    if not force:
        raise ArkUIPageError("generated ArkUI page already exists; use --force only for unchanged generated outputs")
    if not output_exists or not manifest_exists or output_path.is_symlink() or manifest_path.is_symlink():
        raise ArkUIPageError("forced regeneration requires the complete previous generated output and manifest")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ArkUIPageError(f"previous ArkUI generation manifest is invalid: {error}") from error
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != MANIFEST_SCHEMA
        or manifest.get("module") != module
        or manifest.get("root") != root
    ):
        raise ArkUIPageError("previous ArkUI generation manifest does not own this output")
    relative = output_path.relative_to(target).as_posix()
    outputs = manifest.get("outputs")
    metadata = outputs.get(relative) if isinstance(outputs, dict) else None
    if not isinstance(metadata, dict) or metadata.get("sha256") != sha256_file(output_path):
        raise ArkUIPageError("generated ArkUI output changed after generation")


def generate(
    contract_path: Path,
    target_path: Path,
    module: str,
    root_source: str,
    root_composable: str,
    android_page_json: Path | None,
    force: bool,
) -> dict[str, Any]:
    root_source = require_safe_relative_source(root_source)
    target = normalize_target(target_path)
    require_module(target, module)
    contract, resolved_contract = load_contract(contract_path)
    if contract is None or resolved_contract is None:
        raise ArkUIPageError("migration contract is required")
    closure, all_calls, definitions = require_contract_ui(contract, root_source, root_composable)
    root = {"source": root_source, "composable": root_composable}
    resource_names, string_values = load_theme_resources(target, module)
    dimension_token_values, number_token_values, color_token_values = load_static_theme_tokens(contract)
    data_classes = load_kotlin_data_classes(contract)
    enum_classes = load_kotlin_enums(contract)
    enum_string_properties = load_kotlin_enum_string_properties(contract)
    route_symbols = load_route_symbols(contract)
    android_page_input = load_android_page_input(android_page_json)
    verified_font_faces = load_verified_font_faces(target, module, contract)
    typography_font_roles = load_typography_font_roles(contract)
    renderer = Renderer(
        root,
        closure,
        all_calls,
        definitions,
        resource_names,
        string_values,
        dimension_token_values,
        number_token_values,
        color_token_values,
        data_classes,
        enum_classes,
        enum_string_properties,
        route_symbols,
        android_page_input,
        verified_font_faces,
        typography_font_roles,
    )
    source = renderer.render()
    output_relative = (
        f"{module}/src/main/ets/generated/Generated{pascal_identifier(root_composable)}.ets"
    )
    identity = hashlib.sha256(f"{root_source}#{root_composable}".encode("utf-8")).hexdigest()[:16]
    manifest_relative = f".migration/arkui-pages/{identity}.json"
    output_path = target / output_relative
    manifest_path = target / manifest_relative
    validate_previous(target, output_path, manifest_path, root, module, force)
    output_bytes = source.encode("utf-8")
    selected_definitions = [
        definitions[key]
        for key in renderer.reached_keys
    ]
    semantic_input = {
        "root": root,
        "closure": closure,
        "definitions": selected_definitions,
        "calls": renderer.selected_calls,
        "verified_font_faces": [
            {
                "alias": face["alias"],
                "weight": face["weight"],
                "rawfile": face["rawfile"],
                "sha256": face["sha256"],
            }
            for face in verified_font_faces
        ],
        "android_page_input_sha256": (
            android_page_input["sha256"] if android_page_input is not None else None
        ),
    }
    source_git = contract.get("source", {}).get("git") if isinstance(contract.get("source"), dict) else None
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "generator": "migrate-android-compose-to-harmony",
        "status": "candidate_requires_review",
        "authoritative": False,
        "target_root": ".",
        "module": module,
        "root": root,
        "source_revision": source_git.get("revision") if isinstance(source_git, dict) else None,
        "contract_sha256": sha256_file(resolved_contract),
        "semantic_input_sha256": canonical_sha256(semantic_input),
        "expanded_definition_count": len(renderer.reached_keys),
        "selected_call_count": len(renderer.selected_calls),
        "verified_font_assets": [
            {
                "alias": face["alias"],
                "weight": face["weight"],
                "target_path": face["target_path"],
                "sha256": face["sha256"],
            }
            for face in verified_font_faces
        ],
        "generation_complete": not renderer.unresolved,
        "unresolved": renderer.unresolved,
        "outputs": {
            output_relative: {
                "sha256": hashlib.sha256(output_bytes).hexdigest(),
                "root_component": f"Generated{pascal_identifier(root_composable)}",
            }
        },
        "limitations": [
            "The semantic contract is a static candidate inventory rather than a Kotlin compiler AST.",
            "Runtime branches, DSL-generated calls, Material defaults, state, callbacks, and assets are complete only when they have no explicit unresolved record.",
            "A successful ArkTS build proves source compatibility, not visual or behavioral parity.",
        ],
    }
    if android_page_input is not None:
        manifest["android_page_input"] = {
            "file": android_page_input["file"],
            "byte_count": android_page_input["byte_count"],
            "sha256": android_page_input["sha256"],
            "page": android_page_input["page"],
            "viewport": android_page_input["viewport"],
            "screenshot": android_page_input["screenshot"],
            "component_count": len(android_page_input["components"]),
            "mapped_call_count": len(renderer.android_page_by_call_id),
            "applied_paths": {
                call_id: sorted(paths)
                for call_id, paths in sorted(renderer.android_page_applied_paths.items())
            },
            "reference_paths": {
                call_id: sorted(paths)
                for call_id, paths in sorted(renderer.android_page_reference_paths.items())
            },
        }
    manifest_bytes = json_bytes(manifest)
    commit_payloads({output_path: output_bytes, manifest_path: manifest_bytes})
    return {
        "target": str(target),
        "module": module,
        "root": root,
        "output": output_relative,
        "manifest": manifest_relative,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "generation_complete": not renderer.unresolved,
        "unresolved_count": len(renderer.unresolved),
        "expanded_definition_count": len(renderer.reached_keys),
    }


def main() -> int:
    args = parse_args()
    try:
        result = generate(
            args.contract,
            args.target,
            args.module,
            args.root_source,
            args.root_composable,
            args.android_page_json,
            args.force,
        )
    except (ArkUIPageError, OSError, TypeError, ValueError) as error:
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
