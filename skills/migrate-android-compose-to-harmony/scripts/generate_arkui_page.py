#!/usr/bin/env python3
"""Generate a conservative ArkUI page from one exact Compose closure."""

from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from statistics import median
from typing import Any
from urllib.parse import urlsplit

from component_required_facts import normalize_required_facts, required_fact_gate
from page_component_catalog import NATIVE_CONTAINERS, NATIVE_LEAVES, NATIVE_BUTTONS
from generate_harmony_theme_resources import commit_payloads, json_bytes
from init_harmony_project import has_external_ownership_proof, sha256_file
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
LANHU_VERSION_KEYS = {"meta", "assets", "artboard"}
LANHU_COMPONENT_MANIFEST_SCHEMA = "android-to-harmony.lanhu-component-manifest.v1"
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
BUTTON_CONTAINER_COMPONENTS = NATIVE_BUTTONS
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
PAGE_SNAPSHOT_COLUMN_COMPONENTS = {"Column", "LazyColumn", "Card"}
PAGE_SNAPSHOT_ROW_COMPONENTS = {"Row", "LazyRow"}
PAGE_SNAPSHOT_FLOW_COMPONENTS = (
    PAGE_SNAPSHOT_COLUMN_COMPONENTS | PAGE_SNAPSHOT_ROW_COMPONENTS
)
PAGE_RUNTIME_OVERLAY_LEAF_TYPES = (
    BUTTON_CONTAINER_COMPONENTS
    | {"Text", "BasicText", "ClickableText", "BasicTextField", "TextField", "OutlinedTextField"}
    | {"Image", "Icon", "AsyncImage", "ProgressRing"}
)
BLANK_UNSAFE_PARENT_COMPONENTS = BUTTON_CONTAINER_COMPONENTS | STACK_RENDERED_COMPONENTS | {"ListItem", "Stack"}
PAGE_DRIVEN_BASELINE_PX = Decimal("3")
PAGE_DRIVEN_BASELINE_VP = Decimal("0.85")
PAGE_DRIVEN_RASTER_PIXEL_VP = Decimal("0.285")


class ArkUIPageError(RuntimeError):
    pass


def runtime_overlay_style_path_allowed(method: str, path: str) -> bool:
    if not path.startswith("style."):
        return False
    if method in {"business_component_id", "child_source_anchor"}:
        return path.startswith("style.state.")
    return True


def is_direct_native_wrapper(
    target: dict[str, Any], descendant: dict[str, Any]
) -> bool:
    source = target.get("source")
    return (
        descendant.get("parent_id") == target.get("id")
        and isinstance(source, dict)
        and source.get("custom_component") is True
        and descendant.get("type") in BUTTON_CONTAINER_COMPONENTS
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate one candidate ArkUI page from one source-generated version_json."
    )
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--module", default="entry")
    parser.add_argument(
        "--page-json",
        required=True,
        type=Path,
        help=(
            "the single source-generated Lanhu version_json containing the complete component "
            "tree, layout relationships, styles, and provenance"
        ),
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


def normalize_source_component_tree(value: Any) -> dict[str, Any]:
    required_fields = {
        "schema", "definitions", "root_ids", "business_root_ids", "business_component_ids",
        "third_party_component_ids", "components"
    }
    optional_fields = {"layout_relationships"}
    if (
        not isinstance(value, dict)
        or not required_fields.issubset(value)
        or set(value) - required_fields - optional_fields
    ):
        raise ArkUIPageError("Android page JSON source component tree is malformed")
    if value.get("schema") != "android-to-harmony.source-component-tree.v2":
        raise ArkUIPageError("Android page JSON source component tree schema is unsupported")
    raw_roots = value.get("root_ids")
    raw_business_roots = value.get("business_root_ids")
    raw_business_components = value.get("business_component_ids")
    raw_third_party_components = value.get("third_party_component_ids")
    raw_definitions = value.get("definitions")
    raw_components = value.get("components")
    if (
        not isinstance(raw_roots, list)
        or not isinstance(raw_business_roots, list)
        or not isinstance(raw_business_components, list)
        or not isinstance(raw_third_party_components, list)
        or not isinstance(raw_definitions, list)
        or not isinstance(raw_components, list)
        or len(raw_definitions) > 10000
        or len(raw_components) > 10000
    ):
        raise ArkUIPageError("Android page JSON source component tree is malformed")
    try:
        root_ids = [require_token(item, "Android page source root id") for item in raw_roots]
        business_root_ids = [
            require_token(item, "Android page business root id")
            for item in raw_business_roots
        ]
        business_component_ids = [
            require_token(item, "Android page business component id")
            for item in raw_business_components
        ]
        third_party_component_ids = [
            require_token(item, "Android page third-party component id")
            for item in raw_third_party_components
        ]
    except PageSnapshotError as error:
        raise ArkUIPageError(str(error)) from error
    if (
        len(root_ids) != len(set(root_ids))
        or len(business_root_ids) != len(set(business_root_ids))
        or len(business_component_ids) != len(set(business_component_ids))
        or len(third_party_component_ids) != len(set(third_party_component_ids))
    ):
        raise ArkUIPageError("Android page JSON source component tree repeats an identity")
    definitions: list[dict[str, Any]] = []
    definition_ids: set[str] = set()
    allowed_component_kinds = {
        "project_component", "compose_primitive", "third_party_component",
        "platform_component", "custom_draw",
    }
    for raw in raw_definitions:
        if not isinstance(raw, dict) or set(raw) != {
            "id", "type", "component_kind", "identity", "dependency", "declared_from"
        }:
            raise ArkUIPageError("Android page JSON source component definition is malformed")
        try:
            item_id = require_token(raw.get("id"), "Android page source definition id")
            item_type = require_token(raw.get("type"), "Android page source definition type")
        except PageSnapshotError as error:
            raise ArkUIPageError(str(error)) from error
        if item_id in definition_ids or raw.get("component_kind") not in allowed_component_kinds:
            raise ArkUIPageError("Android page JSON source component definition is inconsistent")
        identity = raw.get("identity")
        declared_from = raw.get("declared_from")
        dependency = raw.get("dependency")
        if (
            not isinstance(identity, dict)
            or set(identity) != {"status", "qualified_name", "source", "symbol"}
            or not isinstance(identity.get("status"), str)
            or not isinstance(identity.get("symbol"), str)
            or not isinstance(declared_from, dict)
            or set(declared_from) != {"source", "composable", "package"}
            or not isinstance(declared_from.get("source"), str)
            or not isinstance(declared_from.get("composable"), str)
        ):
            raise ArkUIPageError("Android page JSON source component definition identity is malformed")
        if raw["component_kind"] == "third_party_component":
            if (
                not isinstance(dependency, dict)
                or set(dependency) != {"qualified_name", "package_root", "version", "version_status"}
                or not isinstance(dependency.get("qualified_name"), str)
                or not isinstance(dependency.get("package_root"), str)
                or dependency.get("version") is not None
                or dependency.get("version_status") != "requires_resolved_dependency_graph"
            ):
                raise ArkUIPageError("Android page JSON third-party component dependency is malformed")
        elif dependency is not None:
            raise ArkUIPageError("Android page JSON non-third-party component has a dependency record")
        definition_ids.add(item_id)
        definitions.append(copy.deepcopy(raw))
    components: list[dict[str, Any]] = []
    component_ids: set[str] = set()
    for raw in raw_components:
        required_component_fields = {
            "id", "semantic_key", "type", "definition_id", "component_kind", "node_kind", "parent_id", "children_ids",
            "business_parent_id", "business_owner_id", "business_children_ids", "sibling_index",
            "capture_membership", "source", "arguments", "modifiers", "style", "provenance",
            "unresolved", "runtime_instances", "runtime_descendant_ids",
        }
        optional_component_fields = {
            "slot_argument_name", "slot_invocation", "required_facts"
        }
        if (
            not isinstance(raw, dict)
            or not required_component_fields.issubset(raw)
            or set(raw) - required_component_fields - optional_component_fields
        ):
            raise ArkUIPageError("Android page JSON source component tree contains a malformed component")
        try:
            component_id = require_token(raw.get("id"), "Android page source component id")
            semantic_key = require_token(raw.get("semantic_key"), "Android page source semantic key")
            component_type = require_token(raw.get("type"), "Android page source component type")
            component_definition_id = require_token(
                raw.get("definition_id"), "Android page source component definition id"
            )
            parent_id = raw.get("parent_id")
            if parent_id is not None:
                parent_id = require_token(parent_id, "Android page source parent id")
            children_ids = [
                require_token(item, "Android page source child id")
                for item in raw.get("children_ids", [])
            ]
            business_parent_id = raw.get("business_parent_id")
            if business_parent_id is not None:
                business_parent_id = require_token(
                    business_parent_id, "Android page business parent id"
                )
            business_owner_id = raw.get("business_owner_id")
            if business_owner_id is not None:
                business_owner_id = require_token(
                    business_owner_id, "Android page business owner id"
                )
            business_children_ids = [
                require_token(item, "Android page business child id")
                for item in raw.get("business_children_ids", [])
            ]
            runtime_descendant_ids = [
                require_token(item, "Android page source runtime descendant id")
                for item in raw.get("runtime_descendant_ids", [])
            ]
        except PageSnapshotError as error:
            raise ArkUIPageError(str(error)) from error
        if component_id in component_ids:
            raise ArkUIPageError("Android page JSON source component tree repeats a component id")
        component_ids.add(component_id)
        if (
            len(children_ids) != len(set(children_ids))
            or len(business_children_ids) != len(set(business_children_ids))
            or len(runtime_descendant_ids) != len(set(runtime_descendant_ids))
        ):
            raise ArkUIPageError("Android page JSON source component tree repeats a child id")
        node_kind = raw.get("node_kind")
        if node_kind not in {
            "screen_root", "project_component", "third_party_component", "platform_component",
            "custom_draw", "content_slot", "layout_primitive", "visual_primitive"
        }:
            raise ArkUIPageError("Android page JSON source component node kind is unsupported")
        component_kind = raw.get("component_kind")
        if component_kind not in allowed_component_kinds or component_definition_id not in definition_ids:
            raise ArkUIPageError("Android page JSON source component definition reference is inconsistent")
        sibling_index = raw.get("sibling_index")
        if type(sibling_index) is not int or sibling_index < 0:
            raise ArkUIPageError("Android page JSON source component sibling index is malformed")
        if raw.get("capture_membership") not in {"observed_instance", "candidate_active_descendant"}:
            raise ArkUIPageError("Android page JSON source component capture membership is unsupported")
        source = raw.get("source")
        if (
            not isinstance(source, dict)
            or not isinstance(source.get("source"), str)
            or not isinstance(source.get("composable"), str)
            or not isinstance(source.get("call_id"), str)
        ):
            raise ArkUIPageError("Android page JSON source component provenance is malformed")
        instances = raw.get("runtime_instances")
        if not isinstance(instances, list):
            raise ArkUIPageError("Android page JSON source runtime instances are malformed")
        for instance in instances:
            if (
                not isinstance(instance, dict)
                or set(instance) != {"runtime_component_id", "mapping_method", "mapping_status"}
                or instance.get("mapping_status") not in {"proven", "candidate"}
            ):
                raise ArkUIPageError("Android page JSON source runtime instance is malformed")
            try:
                require_token(instance.get("runtime_component_id"), "Android page runtime component id")
                require_token(instance.get("mapping_method"), "Android page runtime mapping method")
            except PageSnapshotError as error:
                raise ArkUIPageError(str(error)) from error
        try:
            normalized_style = normalize_style(raw.get("style"), f"Android page source component {component_id}.style")
            normalized_provenance = normalize_provenance(
                raw.get("provenance"), f"Android page source component {component_id}.provenance"
            )
            normalized_unresolved = normalize_unresolved(
                raw.get("unresolved"), f"Android page source component {component_id}.unresolved"
            )
        except PageSnapshotError as error:
            raise ArkUIPageError(str(error)) from error
        try:
            normalized_required_facts = normalize_required_facts(
                raw.get("required_facts") or [],
                f"Android page source component {component_id}.required_facts",
            )
        except ValueError as error:
            raise ArkUIPageError(str(error)) from error
        component = copy.deepcopy(raw)
        component["definition_id"] = component_definition_id
        component["component_kind"] = component_kind
        component["node_kind"] = node_kind
        component["business_parent_id"] = business_parent_id
        component["business_owner_id"] = business_owner_id
        component["business_children_ids"] = business_children_ids
        component["runtime_descendant_ids"] = runtime_descendant_ids
        slot_argument_name = raw.get("slot_argument_name")
        if slot_argument_name is not None:
            try:
                slot_argument_name = require_token(
                    slot_argument_name, "Android page source slot argument name"
                )
            except PageSnapshotError as error:
                raise ArkUIPageError(str(error)) from error
        slot_invocation = raw.get("slot_invocation")
        if slot_invocation is not None:
            if not isinstance(slot_invocation, dict) or set(slot_invocation) != {"name"}:
                raise ArkUIPageError("Android page source slot invocation is malformed")
            try:
                slot_invocation = {
                    "name": require_token(
                        slot_invocation.get("name"),
                        "Android page source slot invocation name",
                    )
                }
            except PageSnapshotError as error:
                raise ArkUIPageError(str(error)) from error
        component["slot_argument_name"] = slot_argument_name
        component["slot_invocation"] = slot_invocation
        component["style"] = normalized_style
        component["provenance"] = normalized_provenance
        component["unresolved"] = normalized_unresolved
        component["required_facts"] = normalized_required_facts
        components.append(component)
    by_id = {item["id"]: item for item in components}
    if any(root_id not in by_id or by_id[root_id]["parent_id"] is not None for root_id in root_ids):
        raise ArkUIPageError("Android page JSON source component root is inconsistent")
    business_id_set = set(business_component_ids)
    third_party_id_set = set(third_party_component_ids)
    if any(
        component_id not in by_id
        or by_id[component_id]["node_kind"] not in {"screen_root", "project_component"}
        for component_id in business_component_ids
    ):
        raise ArkUIPageError("Android page JSON business component index is inconsistent")
    if any(
        component_id not in by_id
        or by_id[component_id]["component_kind"] != "third_party_component"
        or by_id[component_id]["node_kind"] != "third_party_component"
        for component_id in third_party_component_ids
    ):
        raise ArkUIPageError("Android page JSON third-party component index is inconsistent")
    if third_party_id_set != {
        item["id"] for item in components if item["component_kind"] == "third_party_component"
    }:
        raise ArkUIPageError("Android page JSON third-party component index is incomplete")
    if any(
        root_id not in business_id_set or by_id[root_id]["business_parent_id"] is not None
        for root_id in business_root_ids
    ):
        raise ArkUIPageError("Android page JSON business component root is inconsistent")
    for component in components:
        parent_id = component["parent_id"]
        if parent_id is not None and parent_id not in by_id:
            raise ArkUIPageError("Android page JSON source component parent is unknown")
        if any(child_id not in by_id for child_id in component["children_ids"]):
            raise ArkUIPageError("Android page JSON source component child is unknown")
        if parent_id is not None and component["id"] not in by_id[parent_id]["children_ids"]:
            raise ArkUIPageError("Android page JSON source component relationship is inconsistent")
        for index, child_id in enumerate(component["children_ids"]):
            child = by_id[child_id]
            if child["parent_id"] != component["id"] or child["sibling_index"] != index:
                raise ArkUIPageError("Android page JSON source component relationship is inconsistent")
        business_parent_id = component["business_parent_id"]
        if business_parent_id is not None and business_parent_id not in business_id_set:
            raise ArkUIPageError("Android page JSON source business parent is inconsistent")
        if component["node_kind"] in {"screen_root", "project_component"}:
            if component["business_owner_id"] != component["id"]:
                raise ArkUIPageError("Android page JSON business component owner is inconsistent")
        elif component["business_owner_id"] not in business_id_set:
            raise ArkUIPageError("Android page JSON source business owner is inconsistent")
        for child_id in component["business_children_ids"]:
            if child_id not in business_id_set or by_id[child_id]["business_parent_id"] != component["id"]:
                raise ArkUIPageError("Android page JSON source business relationship is inconsistent")
    raw_layout_relationships = value.get("layout_relationships", [])
    if not isinstance(raw_layout_relationships, list) or len(raw_layout_relationships) > 10000:
        raise ArkUIPageError("Android page JSON source layout relationships are malformed")
    layout_relationships: list[dict[str, Any]] = []
    relationship_ids: set[str] = set()
    for raw in raw_layout_relationships:
        if not isinstance(raw, dict) or set(raw) != {
            "id", "container_id", "container_type", "subject_id", "subject_reference",
            "composition", "draw_order", "source_expression", "branch_resolution",
            "active_constraints", "unresolved",
        }:
            raise ArkUIPageError("Android page JSON source layout relationship is malformed")
        try:
            relationship_id = require_token(raw.get("id"), "Android page layout relationship id")
            container_id = require_token(raw.get("container_id"), "Android page layout container id")
            subject_id = require_token(raw.get("subject_id"), "Android page layout subject id")
            subject_reference = require_token(
                raw.get("subject_reference"), "Android page layout subject reference"
            )
        except PageSnapshotError as error:
            raise ArkUIPageError(str(error)) from error
        if relationship_id in relationship_ids:
            raise ArkUIPageError("Android page JSON source layout relationship repeats an id")
        relationship_ids.add(relationship_id)
        if (
            raw.get("container_type") != "ConstraintLayout"
            or container_id not in by_id
            or by_id[container_id]["type"] != "ConstraintLayout"
            or subject_id not in by_id
            or by_id[subject_id]["parent_id"] != container_id
            or raw.get("composition") not in {"constraint", "overlay"}
            or type(raw.get("draw_order")) is not int
            or raw["draw_order"] != by_id[subject_id]["sibling_index"]
            or not isinstance(raw.get("source_expression"), str)
            or raw.get("branch_resolution") not in {
                "missing_constraint_body", "not_conditional", "resolved_condition",
                "unresolved_condition",
            }
            or not isinstance(raw.get("active_constraints"), list)
            or not isinstance(raw.get("unresolved"), list)
        ):
            raise ArkUIPageError("Android page JSON source layout relationship is inconsistent")
        constraints: list[dict[str, Any]] = []
        for constraint in raw["active_constraints"]:
            if not isinstance(constraint, dict) or set(constraint) != {
                "kind", "subject_anchor", "target_id", "target_reference", "target_anchor",
                "margin_expression", "margin_dp",
            }:
                raise ArkUIPageError("Android page JSON source layout constraint is malformed")
            if (
                constraint.get("kind") not in {"link_to", "center_around"}
                or constraint.get("subject_anchor") not in {
                    "start", "end", "top", "bottom", "baseline", "center"
                }
                or constraint.get("target_anchor") not in {
                    "start", "end", "top", "bottom", "baseline"
                }
                or constraint.get("target_id") not in by_id
                or not isinstance(constraint.get("target_reference"), str)
                or constraint.get("margin_expression") is not None
                and not isinstance(constraint.get("margin_expression"), str)
                or constraint.get("margin_dp") is not None
                and not isinstance(constraint.get("margin_dp"), (int, float))
            ):
                raise ArkUIPageError("Android page JSON source layout constraint is inconsistent")
            constraints.append(copy.deepcopy(constraint))
        unresolved = raw["unresolved"]
        if any(
            not isinstance(item, dict)
            or set(item) != {"expression", "reason"}
            or not isinstance(item.get("expression"), str)
            or not isinstance(item.get("reason"), str)
            for item in unresolved
        ):
            raise ArkUIPageError("Android page JSON source layout unresolved record is malformed")
        relationship = copy.deepcopy(raw)
        relationship["active_constraints"] = constraints
        layout_relationships.append(relationship)
    return {
        "schema": value["schema"],
        "definitions": definitions,
        "by_definition_id": {item["id"]: item for item in definitions},
        "root_ids": root_ids,
        "business_root_ids": business_root_ids,
        "business_component_ids": business_component_ids,
        "third_party_component_ids": third_party_component_ids,
        "layout_relationships": layout_relationships,
        "components": components,
        "by_id": by_id,
    }


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
    optional_fields = {
        "inactive_source_components",
        "runtime_elided_source_components",
        "source_component_tree",
    }
    if (
        not isinstance(payload, dict)
        or not required_fields.issubset(payload)
        or not set(payload).issubset(required_fields | optional_fields)
    ):
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
    content_bounds_dp = viewport.get("content_bounds_dp")
    if (
        not isinstance(content_bounds_dp, dict)
        or set(content_bounds_dp) != {"x", "y", "width", "height"}
        or any(type(content_bounds_dp[field]) not in {int, float} for field in content_bounds_dp)
        or any(not math.isfinite(float(content_bounds_dp[field])) for field in content_bounds_dp)
        or content_bounds_dp["x"] < 0
        or content_bounds_dp["y"] < 0
        or content_bounds_dp["width"] <= 0
        or content_bounds_dp["height"] <= 0
    ):
        raise ArkUIPageError("Android page JSON content bounds are malformed")
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
    call_id_owners: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
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
        visual_bounds_dp = raw.get("visual_bounds_dp")
        if visual_bounds_dp is not None and (
            not isinstance(visual_bounds_dp, dict)
            or set(visual_bounds_dp) != {"x", "y", "width", "height"}
            or any(type(visual_bounds_dp[field]) not in {int, float} for field in visual_bounds_dp)
            or any(not math.isfinite(float(visual_bounds_dp[field])) for field in visual_bounds_dp)
            or visual_bounds_dp["x"] < 0
            or visual_bounds_dp["y"] < 0
            or visual_bounds_dp["width"] <= 0
            or visual_bounds_dp["height"] <= 0
        ):
            raise ArkUIPageError(
                f"Android page component {component_id} has malformed visual bounds"
            )
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
        raw_custom_draw = raw.get("custom_draw")
        custom_draw = None
        if raw_custom_draw is not None:
            expected_custom_draw_fields = {
                "kind", "value", "total", "start_angle_degrees", "stroke_width_dp",
                "track_color", "active_color",
            }
            if (
                not isinstance(raw_custom_draw, dict)
                or set(raw_custom_draw) != expected_custom_draw_fields
                or raw_custom_draw.get("kind") != "ring_progress"
                or type(raw_custom_draw.get("value")) not in {int, float}
                or type(raw_custom_draw.get("total")) not in {int, float}
                or type(raw_custom_draw.get("start_angle_degrees")) not in {int, float}
                or type(raw_custom_draw.get("stroke_width_dp")) not in {int, float}
                or not 0 <= float(raw_custom_draw["value"]) <= float(raw_custom_draw["total"])
                or float(raw_custom_draw["total"]) <= 0
                or float(raw_custom_draw["stroke_width_dp"]) <= 0
                or not isinstance(raw_custom_draw.get("track_color"), str)
                or re.fullmatch(r"#[0-9A-Fa-f]{8}", raw_custom_draw["track_color"]) is None
                or not isinstance(raw_custom_draw.get("active_color"), str)
                or re.fullmatch(r"#[0-9A-Fa-f]{8}", raw_custom_draw["active_color"]) is None
            ):
                raise ArkUIPageError(
                    f"Android page component {component_id} custom draw is malformed"
                )
            custom_draw = copy.deepcopy(raw_custom_draw)
        source = raw.get("source")
        raw_component_context = raw.get("component_context")
        component_context: dict[str, Any] | None = None
        if raw_component_context is not None:
            if not isinstance(raw_component_context, dict) or set(raw_component_context) != {
                "status", "method", "source_component_id", "business_component_id",
                "business_component_path", "evidence_runtime_ids",
            }:
                raise ArkUIPageError(
                    f"Android page component {component_id} component context is malformed"
                )
            if raw_component_context.get("status") not in {"proven", "candidate", "unbound"}:
                raise ArkUIPageError(
                    f"Android page component {component_id} component context status is unsupported"
                )
            try:
                context_source_id = raw_component_context.get("source_component_id")
                if context_source_id is not None:
                    context_source_id = require_token(
                        context_source_id, "Android page component context source id"
                    )
                context_business_id = raw_component_context.get("business_component_id")
                if context_business_id is not None:
                    context_business_id = require_token(
                        context_business_id, "Android page component context business id"
                    )
                context_business_path = [
                    require_token(item, "Android page component context business path id")
                    for item in raw_component_context.get("business_component_path", [])
                ]
                context_evidence_ids = [
                    require_token(item, "Android page component context evidence runtime id")
                    for item in raw_component_context.get("evidence_runtime_ids", [])
                ]
                context_method = require_token(
                    raw_component_context.get("method"),
                    "Android page component context method",
                )
            except PageSnapshotError as error:
                raise ArkUIPageError(str(error)) from error
            if (
                len(context_business_path) != len(set(context_business_path))
                or len(context_evidence_ids) != len(set(context_evidence_ids))
                or context_business_id != (context_business_path[-1] if context_business_path else None)
                or (raw_component_context["status"] == "unbound") != (context_business_id is None)
            ):
                raise ArkUIPageError(
                    f"Android page component {component_id} component context is inconsistent"
                )
            component_context = {
                "status": raw_component_context["status"],
                "method": context_method,
                "source_component_id": context_source_id,
                "business_component_id": context_business_id,
                "business_component_path": context_business_path,
                "evidence_runtime_ids": context_evidence_ids,
            }
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
            "smallest-containing-runtime-component", "source-semantic-ancestor",
            "runtime-semantic-ancestor",
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
            source_mapping = raw.get("source_mapping")
            mapped_call_id = (
                source_mapping.get("source_call_id")
                if isinstance(source_mapping, dict)
                and source_mapping.get("status") in {"proven", "candidate"}
                else None
            )
            if isinstance(mapped_call_id, str):
                call_ids.append(mapped_call_id)
        component = {
            "id": component_id,
            "type": component_type,
            "semantic_key": raw.get("semantic_key"),
            "bounds_dp": {name: float(bounds_dp[name]) for name in ("x", "y", "width", "height")},
            "visual_bounds_dp": (
                {
                    name: float(visual_bounds_dp[name])
                    for name in ("x", "y", "width", "height")
                }
                if isinstance(visual_bounds_dp, dict)
                else None
            ),
            "parent_id": parent_id,
            "children_ids": normalized_children,
            "sibling_index": sibling_index,
            "parent_mapping": parent_mapping,
            "style": style,
            "provenance": provenance,
            "unresolved": unresolved,
            "custom_draw": custom_draw,
            "call_ids": sorted(set(call_ids)),
            "component_context": component_context,
            "source": copy.deepcopy(source),
        }
        raw_source_layout_bounds = raw.get("source_layout_bounds_dp")
        if raw_source_layout_bounds is not None:
            if (
                component_context is None
                or component_context["status"] != "candidate"
                or component_context["method"] != "source_layout_projection"
                or not isinstance(raw_source_layout_bounds, dict)
                or set(raw_source_layout_bounds) != {"x", "y", "width", "height"}
                or any(
                    type(raw_source_layout_bounds[field]) not in {int, float}
                    for field in raw_source_layout_bounds
                )
                or any(
                    not math.isfinite(float(raw_source_layout_bounds[field]))
                    for field in raw_source_layout_bounds
                )
                or raw_source_layout_bounds["width"] <= 0
                or raw_source_layout_bounds["height"] <= 0
            ):
                raise ArkUIPageError(
                    f"Android page component {component_id} source layout bounds are malformed"
                )
            expected_visible_bounds = {
                "x": max(
                    float(raw_source_layout_bounds["x"]),
                    float(content_bounds_dp["x"]),
                ),
                "y": max(
                    float(raw_source_layout_bounds["y"]),
                    float(content_bounds_dp["y"]),
                ),
                "width": min(
                    float(raw_source_layout_bounds["x"])
                    + float(raw_source_layout_bounds["width"]),
                    float(content_bounds_dp["x"])
                    + float(content_bounds_dp["width"]),
                )
                - max(
                    float(raw_source_layout_bounds["x"]),
                    float(content_bounds_dp["x"]),
                ),
                "height": min(
                    float(raw_source_layout_bounds["y"])
                    + float(raw_source_layout_bounds["height"]),
                    float(content_bounds_dp["y"])
                    + float(content_bounds_dp["height"]),
                )
                - max(
                    float(raw_source_layout_bounds["y"]),
                    float(content_bounds_dp["y"]),
                ),
            }
            if (
                expected_visible_bounds["width"] <= 0
                or expected_visible_bounds["height"] <= 0
                or any(
                    abs(float(bounds_dp[field]) - expected_visible_bounds[field]) > 0.002
                    for field in ("x", "y", "width", "height")
                )
            ):
                raise ArkUIPageError(
                    f"Android page component {component_id} source layout bounds do not match its clipped visible bounds"
                )
            component["source_layout_bounds_dp"] = {
                field: float(raw_source_layout_bounds[field])
                for field in ("x", "y", "width", "height")
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
            owners = call_id_owners[call_id]
            semantic_key = component["semantic_key"]
            if owners:
                semantic_keys = [owner_key for _owner_id, owner_key in owners] + [semantic_key]
                bases = {
                    re.sub(r"(?:__[0-9]+|__instance_[A-Za-z0-9._:@#-]+)$", "", key)
                    for key in semantic_keys
                    if isinstance(key, str)
                }
                if (
                    any(not isinstance(key, str) for key in semantic_keys)
                    or len(set(semantic_keys)) != len(semantic_keys)
                    or len(bases) != 1
                    or any(key in bases for key in semantic_keys[1:])
                ):
                    raise ArkUIPageError(
                        "Android page JSON maps multiple runtime components to one source call "
                        "without distinct source instances: " + call_id
                    )
            owners.append((component_id, semantic_key))
            by_call_id.setdefault(call_id, component)
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
    raw_elided = payload.get("runtime_elided_source_components", [])
    if not isinstance(raw_elided, list) or len(raw_elided) > 10000:
        raise ArkUIPageError("Android page JSON runtime-elided source components are malformed")
    runtime_elided_source_components: list[dict[str, str]] = []
    elided_semantic_keys: set[str] = set()
    for entry in raw_elided:
        if not isinstance(entry, dict) or set(entry) != {
            "source_semantic_key",
            "source_call_id",
            "reason",
        }:
            raise ArkUIPageError("Android page JSON runtime-elided source component is malformed")
        try:
            semantic_key = require_token(
                entry.get("source_semantic_key"),
                "Android page runtime-elided source semantic key",
            )
            reason = require_token(
                entry.get("reason"),
                "Android page runtime-elided source reason",
            )
        except PageSnapshotError as error:
            raise ArkUIPageError(str(error)) from error
        call_id = entry.get("source_call_id")
        if (
            not isinstance(call_id, str)
            or not call_id
            or len(call_id) > 4096
            or any(character in call_id for character in "\r\n\0")
        ):
            raise ArkUIPageError("Android page runtime-elided source call ID is malformed")
        if semantic_key in elided_semantic_keys:
            raise ArkUIPageError("Android page JSON repeats a runtime-elided source semantic key")
        elided_semantic_keys.add(semantic_key)
        runtime_elided_source_components.append({
            "source_semantic_key": semantic_key,
            "source_call_id": call_id,
            "reason": reason,
        })
    source_component_tree = (
        normalize_source_component_tree(payload["source_component_tree"])
        if "source_component_tree" in payload
        else None
    )
    if source_component_tree is not None:
        source_tree_by_id = source_component_tree["by_id"]
        business_ids = set(source_component_tree["business_component_ids"])
        runtime_ids = set(by_id)
        for component in components:
            context = component["component_context"]
            if context is None:
                raise ArkUIPageError(
                    "Android page JSON with a source component tree requires component context"
                )
            if (
                context["source_component_id"] is not None
                and context["source_component_id"] not in source_tree_by_id
            ):
                raise ArkUIPageError("Android page component context source id is unknown")
            if any(item not in business_ids for item in context["business_component_path"]):
                raise ArkUIPageError("Android page component context business path is unknown")
            if any(item not in runtime_ids for item in context["evidence_runtime_ids"]):
                raise ArkUIPageError("Android page component context evidence runtime id is unknown")
    return {
        "file": requested.name,
        "byte_count": byte_count,
        "sha256": sha256_file(requested),
        "page": normalized_page,
        "viewport": {
            "density": float(density),
            "font_scale": float(font_scale),
            "orientation": orientation,
            "content_bounds_dp": {
                name: float(content_bounds_dp[name])
                for name in ("x", "y", "width", "height")
            },
        },
        "screenshot": {
            "file": screenshot["file"],
            "byte_count": screenshot["byte_count"],
            "sha256": screenshot["sha256"],
        },
        "components": components,
        "by_id": by_id,
        "by_call_id": by_call_id,
        "instances_by_call_id": {
            call_id: [by_id[component_id] for component_id, _semantic_key in owners]
            for call_id, owners in call_id_owners.items()
        },
        "runtime_elided_source_components": runtime_elided_source_components,
        "source_component_tree": source_component_tree,
    }


def load_bounded_json_object(path: Path, label: str) -> tuple[dict[str, Any], Path, int]:
    requested = Path(os.path.abspath(os.path.expanduser(str(path))))
    if requested.is_symlink() or not requested.is_file():
        raise ArkUIPageError(f"{label} must be an existing non-symbolic-link file")
    byte_count = requested.stat().st_size
    if byte_count <= 0 or byte_count > PAGE_INPUT_MAX_BYTES:
        raise ArkUIPageError(f"{label} must contain 1 byte to 10 MiB")
    try:
        payload = json.loads(requested.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ArkUIPageError(f"{label} is invalid: {error}") from error
    if not isinstance(payload, dict):
        raise ArkUIPageError(f"{label} must contain a JSON object")
    return payload, requested, byte_count


def require_lanhu_number(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ArkUIPageError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or (positive and number <= 0):
        qualifier = "positive" if positive else "finite"
        raise ArkUIPageError(f"{label} must be {qualifier}")
    return number


def require_lanhu_frame(
    value: Any,
    label: str,
    *,
    positive_dimensions: bool = False,
) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ArkUIPageError(f"{label} has no frame")
    frame = {
        field: require_lanhu_number(value.get(field), f"{label}.{field}")
        for field in ("left", "top", "width", "height")
    }
    if frame["width"] < 0 or frame["height"] < 0:
        raise ArkUIPageError(f"{label} frame dimensions must not be negative")
    if positive_dimensions and (frame["width"] <= 0 or frame["height"] <= 0):
        raise ArkUIPageError(f"{label} frame dimensions must be positive")
    return frame


def lanhu_color(value: Any) -> str | None:
    if isinstance(value, str) and re.fullmatch(r"#[0-9A-Fa-f]{8}", value):
        return value.upper()
    if not isinstance(value, dict):
        return None
    channels = [value.get(name) for name in ("a", "r", "g", "b")]
    if any(isinstance(channel, bool) or not isinstance(channel, (int, float)) for channel in channels):
        return None
    normalized = [float(channel) for channel in channels]
    if any(not math.isfinite(channel) or channel < 0 or channel > 1 for channel in normalized):
        return None
    return "#" + "".join(f"{round(channel * 255):02X}" for channel in normalized)


def validate_lanhu_style(value: Any, label: str) -> None:
    required = {
        "isEnabled", "opacity", "blendMode", "fills", "borders", "shadows", "blurs"
    }
    if not isinstance(value, dict) or not required.issubset(value):
        missing = sorted(required - set(value) if isinstance(value, dict) else required)
        raise ArkUIPageError(f"{label} is missing required fields: {missing}")
    if type(value["isEnabled"]) is not bool:
        raise ArkUIPageError(f"{label}.isEnabled must be a boolean")
    opacity = require_lanhu_number(value["opacity"], f"{label}.opacity")
    if not 0 <= opacity <= 1:
        raise ArkUIPageError(f"{label}.opacity must be between 0 and 1")
    if type(value["blendMode"]) is not int:
        raise ArkUIPageError(f"{label}.blendMode must be an integer")
    for field in ("fills", "borders", "shadows", "blurs"):
        if not isinstance(value[field], list):
            raise ArkUIPageError(f"{label}.{field} must be a list")


def validate_lanhu_layout_rules(value: Any, label: str) -> None:
    if not isinstance(value, list) or len(value) > 1000:
        raise ArkUIPageError(f"{label} must be a bounded list")
    for index, rule in enumerate(value):
        rule_label = f"{label}[{index}]"
        if not isinstance(rule, dict):
            raise ArkUIPageError(f"{rule_label} must be an object")
        modifier_index = rule.get("source_modifier_index")
        if type(modifier_index) is not int or modifier_index < 0:
            raise ArkUIPageError(
                f"{rule_label}.source_modifier_index must be a non-negative integer"
            )
        kind = rule.get("kind")
        if kind == "sizing":
            axes = rule.get("axes")
            mode = rule.get("mode")
            if (
                not isinstance(axes, list)
                or not axes
                or len(axes) != len(set(axes))
                or any(axis not in {"width", "height"} for axis in axes)
                or mode not in {"fill_parent", "match_parent", "wrap_content"}
            ):
                raise ArkUIPageError(f"{rule_label} sizing rule is malformed")
            if mode in {"fill_parent", "match_parent"}:
                fraction = require_lanhu_number(
                    rule.get("fraction"), f"{rule_label}.fraction"
                )
                if not 0 <= fraction <= 1:
                    raise ArkUIPageError(
                        f"{rule_label}.fraction must be greater than zero and at most one"
                    )
        elif kind == "intrinsic_size":
            if rule.get("axis") not in {"width", "height"} or rule.get("mode") not in {
                "min", "max"
            }:
                raise ArkUIPageError(f"{rule_label} intrinsic-size rule is malformed")
        elif kind == "constraints":
            limits = rule.get("limits")
            if not isinstance(limits, dict) or not limits or set(limits) - {"minWidth", "maxWidth", "minHeight", "maxHeight"}:
                raise ArkUIPageError(f"{rule_label} constraints are malformed")
            for key, value in limits.items():
                if require_lanhu_number(value, f"{rule_label}.{key}") < 0:
                    raise ArkUIPageError(f"{rule_label}.{key} must be non-negative")
            for axis in ("Width", "Height"):
                if limits.get("min" + axis, 0) > limits.get("max" + axis, float("inf")):
                    raise ArkUIPageError(f"{rule_label} minimum exceeds maximum")
        elif kind == "scroll":
            if rule.get("axis") not in {"vertical", "horizontal"} or type(rule.get("enabled")) is not bool:
                raise ArkUIPageError(f"{rule_label} scroll rule is malformed")
        elif kind == "weight":
            value_number = require_lanhu_number(
                rule.get("value"), f"{rule_label}.value"
            )
            if value_number <= 0 or type(rule.get("fill")) is not bool:
                raise ArkUIPageError(f"{rule_label} weight rule is malformed")
        elif kind == "offset":
            if "x" not in rule and "y" not in rule:
                raise ArkUIPageError(f"{rule_label} offset rule has no axis")
            for axis in ("x", "y"):
                if axis not in rule:
                    continue
                offset = rule[axis]
                if not isinstance(offset, dict):
                    raise ArkUIPageError(f"{rule_label}.{axis} is malformed")
                offset_kind = offset.get("kind")
                if offset_kind == "dp":
                    require_lanhu_number(offset.get("value"), f"{rule_label}.{axis}.value")
                elif offset_kind == "parent_fraction":
                    if offset.get("axis") not in {"width", "height"}:
                        raise ArkUIPageError(f"{rule_label}.{axis}.axis is malformed")
                    require_lanhu_number(
                        offset.get("fraction"), f"{rule_label}.{axis}.fraction"
                    )
                else:
                    raise ArkUIPageError(f"{rule_label}.{axis}.kind is unsupported")
        elif kind == "constraint_reference":
            try:
                require_token(rule.get("reference"), f"{rule_label}.reference")
            except PageSnapshotError as error:
                raise ArkUIPageError(str(error)) from error
        elif kind == "alignment":
            if not isinstance(rule.get("value"), str) or re.fullmatch(
                r"Alignment\.[A-Za-z]+", rule["value"]
            ) is None:
                raise ArkUIPageError(f"{rule_label} alignment rule is malformed")
        elif kind == "z_index":
            require_lanhu_number(rule.get("value"), f"{rule_label}.value")
        else:
            raise ArkUIPageError(f"{rule_label}.kind is unsupported")


def validate_lanhu_version_document(version: dict[str, Any]) -> None:
    if set(version) != LANHU_VERSION_KEYS:
        raise ArkUIPageError("Lanhu version_json must contain exactly meta/assets/artboard")
    meta = version.get("meta")
    if not isinstance(meta, dict):
        raise ArkUIPageError("Lanhu version_json meta is malformed")
    require_lanhu_number(
        meta.get("sliceScale"), "Lanhu version_json sliceScale", positive=True
    )
    if not isinstance(version.get("assets"), list):
        raise ArkUIPageError("Lanhu version_json assets must be a list")
    if not all(isinstance(asset, str) and asset for asset in version["assets"]):
        raise ArkUIPageError("Lanhu version_json assets must contain non-empty strings")
    artboard = version.get("artboard")
    artboard_required = {
        "id", "name", "type", "visible", "clipped", "opacity", "frame",
        "realFrame", "combinedFrame", "style", "layers",
    }
    if not isinstance(artboard, dict) or not artboard_required.issubset(artboard):
        missing = sorted(
            artboard_required - set(artboard) if isinstance(artboard, dict) else artboard_required
        )
        raise ArkUIPageError(f"Lanhu artboard is missing required fields: {missing}")
    for field in ("id", "name", "type"):
        try:
            require_token(artboard[field], f"Lanhu artboard {field}")
        except PageSnapshotError as error:
            raise ArkUIPageError(str(error)) from error
    if type(artboard["visible"]) is not bool or type(artboard["clipped"]) is not bool:
        raise ArkUIPageError("Lanhu artboard visible/clipped fields must be booleans")
    artboard_opacity = require_lanhu_number(artboard["opacity"], "Lanhu artboard opacity")
    if not 0 <= artboard_opacity <= 1:
        raise ArkUIPageError("Lanhu artboard opacity must be between 0 and 1")
    for field in ("frame", "realFrame", "combinedFrame"):
        require_lanhu_frame(
            artboard[field], f"Lanhu artboard {field}", positive_dimensions=True
        )
    validate_lanhu_style(artboard["style"], "Lanhu artboard style")
    if not isinstance(artboard["layers"], list) or not artboard["layers"]:
        raise ArkUIPageError("Lanhu artboard layers must be a non-empty list")

    layer_required = {
        "id", "name", "type", "visible", "clipped", "isMask", "opacity", "rotation",
        "frame", "realFrame", "combinedFrame", "radius", "paths", "style",
        "hasExportImage", "hasExportDDSImage", "layers",
    }

    def visit(layer: Any) -> None:
        if not isinstance(layer, dict) or not layer_required.issubset(layer):
            missing = sorted(
                layer_required - set(layer) if isinstance(layer, dict) else layer_required
            )
            raise ArkUIPageError(f"Lanhu layer is missing required fields: {missing}")
        layer_id = layer.get("id")
        for field in ("id", "name", "type"):
            try:
                require_token(layer[field], f"Lanhu layer {layer_id} {field}")
            except PageSnapshotError as error:
                raise ArkUIPageError(str(error)) from error
        for field in ("visible", "clipped", "isMask", "hasExportImage", "hasExportDDSImage"):
            if type(layer[field]) is not bool:
                raise ArkUIPageError(f"Lanhu layer {layer_id}.{field} must be a boolean")
        opacity = require_lanhu_number(layer["opacity"], f"Lanhu layer {layer_id}.opacity")
        if not 0 <= opacity <= 1:
            raise ArkUIPageError(f"Lanhu layer {layer_id}.opacity must be between 0 and 1")
        require_lanhu_number(layer["rotation"], f"Lanhu layer {layer_id}.rotation")
        for field in ("frame", "realFrame", "combinedFrame"):
            require_lanhu_frame(layer[field], f"Lanhu layer {layer_id}.{field}")
        radius = layer["radius"]
        radius_fields = {"topLeft", "topRight", "bottomRight", "bottomLeft"}
        if not isinstance(radius, dict) or set(radius) != radius_fields:
            raise ArkUIPageError(f"Lanhu layer {layer_id}.radius is malformed")
        for field in radius_fields:
            number = require_lanhu_number(radius[field], f"Lanhu layer {layer_id}.radius.{field}")
            if number < 0:
                raise ArkUIPageError(f"Lanhu layer {layer_id}.radius.{field} must not be negative")
        if not isinstance(layer["paths"], list) or not isinstance(layer["layers"], list):
            raise ArkUIPageError(f"Lanhu layer {layer_id} paths/layers must be lists")
        validate_lanhu_style(layer["style"], f"Lanhu layer {layer_id}.style")
        migration = layer.get("migration")
        if layer["type"] == "text" and not isinstance(layer.get("text"), str):
            unresolved_text = (
                isinstance(meta.get("sourceGeneration"), dict)
                and "text" in layer and layer["text"] is None
                and isinstance(migration, dict)
                and isinstance(migration.get("unresolved"), list)
                and any(isinstance(item, dict) and item.get("path") == "style.content.text"
                        for item in migration["unresolved"])
            )
            if not unresolved_text:
                raise ArkUIPageError(f"Lanhu text layer {layer_id} must contain text or an explicit unresolved fact")
        if layer["hasExportImage"] and (
            not isinstance(layer.get("exportImageUrl"), str)
            or not layer["exportImageUrl"]
        ):
            raise ArkUIPageError(
                f"Lanhu export-image layer {layer_id} must contain exportImageUrl"
            )
        migration = layer.get("migration")
        if migration is not None:
            migration_required = {
                "schema", "componentType", "semanticKey", "source", "style",
                "customDraw", "provenance", "unresolved", "geometryStatus",
                "geometryEvidence",
            }
            migration_allowed = migration_required | {"requiredFacts", "phaseTrace"}
            source_generated = isinstance(meta.get("sourceGeneration"), dict)
            if (
                not isinstance(migration, dict)
                or not migration_required.issubset(migration)
                or not set(migration).issubset(migration_allowed)
                or source_generated and "requiredFacts" not in migration
            ):
                raise ArkUIPageError(f"Lanhu layer {layer_id}.migration is malformed")
            if migration.get("schema") != "android-to-harmony.lanhu-node.v1":
                raise ArkUIPageError(f"Lanhu layer {layer_id}.migration schema is unsupported")
            try:
                require_token(
                    migration.get("componentType"),
                    f"Lanhu layer {layer_id}.migration componentType",
                )
                require_token(
                    migration.get("semanticKey"),
                    f"Lanhu layer {layer_id}.migration semanticKey",
                )
                normalize_style(
                    migration.get("style"),
                    f"Lanhu layer {layer_id}.migration.style",
                )
                normalize_provenance(
                    migration.get("provenance"),
                    f"Lanhu layer {layer_id}.migration.provenance",
                )
                normalize_unresolved(
                    migration.get("unresolved"),
                    f"Lanhu layer {layer_id}.migration.unresolved",
                )
                if "requiredFacts" in migration:
                    normalize_required_facts(
                        migration.get("requiredFacts"),
                        f"Lanhu layer {layer_id}.migration.requiredFacts",
                    )
            except PageSnapshotError as error:
                raise ArkUIPageError(str(error)) from error
            except ValueError as error:
                raise ArkUIPageError(str(error)) from error
            source = migration.get("source")
            if not isinstance(source, dict) or not isinstance(source.get("attributes"), list):
                raise ArkUIPageError(f"Lanhu layer {layer_id}.migration.source is malformed")
            if "layoutRules" in source:
                validate_lanhu_layout_rules(
                    source["layoutRules"],
                    f"Lanhu layer {layer_id}.migration.source.layoutRules",
                )
            if migration.get("geometryStatus") not in {
                "source_resolved", "source_inferred", "unresolved"
            }:
                raise ArkUIPageError(
                    f"Lanhu layer {layer_id}.migration.geometryStatus is unsupported"
                )
            geometry_evidence = migration.get("geometryEvidence")
            if not isinstance(geometry_evidence, list) or not all(
                isinstance(item, str) for item in geometry_evidence
            ):
                raise ArkUIPageError(
                    f"Lanhu layer {layer_id}.migration.geometryEvidence is malformed"
                )
            phase_trace = migration.get("phaseTrace")
            if phase_trace is not None:
                phase_names = ("measure", "layout", "draw")
                if (
                    not isinstance(phase_trace, dict)
                    or set(phase_trace) != {"schema", "phaseOrder", *phase_names}
                    or phase_trace.get("schema")
                    != "android-to-harmony.render-phase-trace.v1"
                    or phase_trace.get("phaseOrder") != list(phase_names)
                ):
                    raise ArkUIPageError(
                        f"Lanhu layer {layer_id}.migration.phaseTrace is malformed"
                    )
                for phase_name in phase_names:
                    phase = phase_trace.get(phase_name)
                    if not isinstance(phase, dict) or phase.get("status") not in {
                        "consumed", "missing"
                    }:
                        raise ArkUIPageError(
                            f"Lanhu layer {layer_id}.migration.phaseTrace.{phase_name} is malformed"
                        )
        for child in layer["layers"]:
            visit(child)

    for root_layer in artboard["layers"]:
        visit(root_layer)
    source_generation = meta.get("sourceGeneration")
    if isinstance(source_generation, dict) and not isinstance(
        source_generation.get("layoutRelationships"), list
    ):
        raise ArkUIPageError(
            "source-generated Lanhu version_json requires meta.sourceGeneration.layoutRelationships"
        )


def normalize_lanhu_layout_relationships(
    value: Any,
    by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 10000:
        raise ArkUIPageError("Lanhu source layout relationships are malformed")
    relationships: list[dict[str, Any]] = []
    relationship_ids: set[str] = set()
    expected_fields = {
        "id", "container_id", "container_type", "subject_id", "subject_reference",
        "composition", "draw_order", "source_expression", "branch_resolution",
        "active_constraints", "unresolved",
    }
    constraint_fields = {
        "kind", "subject_anchor", "target_id", "target_reference", "target_anchor",
        "margin_expression", "margin_dp",
    }
    for raw in value:
        if not isinstance(raw, dict) or set(raw) != expected_fields:
            raise ArkUIPageError("Lanhu source layout relationship is malformed")
        relationship_id = str(raw.get("id") or "")
        container_id = str(raw.get("container_id") or "")
        subject_id = str(raw.get("subject_id") or "")
        if not relationship_id or relationship_id in relationship_ids:
            raise ArkUIPageError("Lanhu source layout relationship id is invalid")
        relationship_ids.add(relationship_id)
        if (
            raw.get("container_type") != "ConstraintLayout"
            or container_id not in by_id
            or by_id[container_id]["type"] != "ConstraintLayout"
            or subject_id not in by_id
            or by_id[subject_id]["parent_id"] != container_id
            or raw.get("composition") not in {"constraint", "overlay"}
            or type(raw.get("draw_order")) is not int
            or raw["draw_order"] != by_id[subject_id]["sibling_index"]
            or not isinstance(raw.get("subject_reference"), str)
            or not raw["subject_reference"]
            or not isinstance(raw.get("source_expression"), str)
            or raw.get("branch_resolution") not in {
                "missing_constraint_body", "not_conditional", "resolved_condition",
                "unresolved_condition",
            }
            or not isinstance(raw.get("active_constraints"), list)
            or not isinstance(raw.get("unresolved"), list)
        ):
            raise ArkUIPageError("Lanhu source layout relationship is inconsistent")
        constraints: list[dict[str, Any]] = []
        for raw_constraint in raw["active_constraints"]:
            if not isinstance(raw_constraint, dict) or set(raw_constraint) != constraint_fields:
                raise ArkUIPageError("Lanhu source layout constraint is malformed")
            target_id = raw_constraint.get("target_id")
            if (
                raw_constraint.get("kind") not in {"link_to", "center_around"}
                or raw_constraint.get("subject_anchor") not in {
                    "start", "end", "top", "bottom", "baseline", "center"
                }
                or raw_constraint.get("target_anchor") not in {
                    "start", "end", "top", "bottom", "baseline"
                }
                or target_id not in by_id
                or not isinstance(raw_constraint.get("target_reference"), str)
                or raw_constraint.get("margin_expression") is not None
                and not isinstance(raw_constraint.get("margin_expression"), str)
                or raw_constraint.get("margin_dp") is not None
                and not isinstance(raw_constraint.get("margin_dp"), (int, float))
            ):
                raise ArkUIPageError("Lanhu source layout constraint is inconsistent")
            constraints.append(copy.deepcopy(raw_constraint))
        if any(
            not isinstance(item, dict)
            or set(item) != {"expression", "reason"}
            or not isinstance(item.get("expression"), str)
            or not isinstance(item.get("reason"), str)
            for item in raw["unresolved"]
        ):
            raise ArkUIPageError("Lanhu source layout unresolved record is malformed")
        relationship = copy.deepcopy(raw)
        relationship["active_constraints"] = constraints
        relationships.append(relationship)
    return relationships


def apply_lanhu_visual_style(
    style: dict[str, dict[str, Any]],
    layer: dict[str, Any],
    scale: float,
) -> list[str]:
    applied: list[str] = []

    def assign(section: str, field: str, value: Any) -> None:
        style[section][field] = value
        applied.append(f"style.{section}.{field}")

    if type(layer.get("visible")) is bool:
        assign("state", "visible", layer["visible"])
    layer_style = layer.get("style")
    if not isinstance(layer_style, dict):
        layer_style = {}
    # Lanhu isEnabled enables a paint style, not Android interaction state.
    opacity = layer.get("opacity", layer_style.get("opacity"))
    if isinstance(opacity, (int, float)) and not isinstance(opacity, bool):
        number = float(opacity)
        if math.isfinite(number) and 0 <= number <= 1:
            assign("surface", "alpha", number)
    if type(layer.get("clipped")) is bool:
        assign("surface", "clip", layer["clipped"])
    rotation = layer.get("rotation")
    if isinstance(rotation, (int, float)) and not isinstance(rotation, bool):
        number = float(rotation)
        if math.isfinite(number):
            assign("transform", "rotation_degrees", number)
    if isinstance(layer.get("text"), str):
        assign("content", "text", layer["text"])
    font_size = layer_style.get("fontSize")
    if isinstance(font_size, (int, float)) and not isinstance(font_size, bool):
        number = float(font_size) / scale
        if math.isfinite(number) and number >= 0:
            assign("typography", "font_size_sp", number)
    font_weight = layer_style.get("fontWeight")
    if type(font_weight) is int and 1 <= font_weight <= 1000:
        assign("typography", "font_weight", font_weight)
    font_color = layer_style.get("color")
    if isinstance(font_color, str) and re.fullmatch(r"#[0-9A-Fa-f]{8}", font_color):
        assign("typography", "color", font_color.upper())
    radius = layer.get("radius")
    radius_fields = {
        "top_left": "topLeft",
        "top_right": "topRight",
        "bottom_right": "bottomRight",
        "bottom_left": "bottomLeft",
    }
    if isinstance(radius, dict) and all(
        isinstance(radius.get(source), (int, float)) and not isinstance(radius.get(source), bool)
        for source in radius_fields.values()
    ):
        assign(
            "surface",
            "corner_radius_dp",
            {
                target: float(radius[source]) / scale
                for target, source in radius_fields.items()
            },
        )
    fills = layer_style.get("fills")
    if isinstance(fills, list):
        fill = next(
            (
                item
                for item in fills
                if isinstance(item, dict)
                and item.get("type") == "color"
                and item.get("isEnabled", True) is not False
            ),
            None,
        )
        color = lanhu_color(fill.get("color")) if isinstance(fill, dict) else None
        if color is not None:
            assign("surface", "background", {"type": "solid", "color": color})
    resource = layer.get("exportImageUrl")
    if isinstance(resource, str) and RESOURCE_NAME_PATTERN.fullmatch(resource):
        assign("asset", "resource", resource)
    return applied


def load_lanhu_page_input(
    version_json_path: Path,
    component_manifest_path: Path | None = None,
) -> dict[str, Any]:
    version, version_path, version_bytes = load_bounded_json_object(
        version_json_path, "Lanhu version_json"
    )
    validate_lanhu_version_document(version)
    manifest: dict[str, Any] | None = None
    manifest_path: Path | None = None
    manifest_bytes = 0
    if component_manifest_path is not None:
        manifest, manifest_path, manifest_bytes = load_bounded_json_object(
            component_manifest_path, "Lanhu component manifest"
        )
    meta = version.get("meta")
    source_generated = isinstance(
        meta.get("sourceGeneration") if isinstance(meta, dict) else None, dict
    )
    scale = require_lanhu_number(
        meta.get("sliceScale") if isinstance(meta, dict) else None,
        "Lanhu version_json sliceScale",
        positive=True,
    )
    artboard = version.get("artboard")
    if not isinstance(artboard, dict):
        raise ArkUIPageError("Lanhu version_json artboard is malformed")
    artboard_frame = require_lanhu_frame(
        artboard.get("frame"), "Lanhu artboard", positive_dimensions=True
    )
    viewport_width = round(artboard_frame["width"] / scale, 6)
    viewport_height = round(artboard_frame["height"] / scale, 6)

    layers_by_id: dict[str, dict[str, Any]] = {}
    layer_parent: dict[str, str | None] = {}
    layer_children: dict[str, list[str]] = {}
    layer_order: list[str] = []

    def visit(layer: Any, parent_id: str | None) -> None:
        if not isinstance(layer, dict) or not isinstance(layer.get("id"), str):
            raise ArkUIPageError("every Lanhu version_json layer must have a string id")
        layer_id = layer["id"]
        if layer_id in layers_by_id:
            raise ArkUIPageError(f"duplicate Lanhu version_json layer id: {layer_id}")
        require_lanhu_frame(layer.get("frame"), f"Lanhu layer {layer_id}")
        children = layer.get("layers") or []
        if not isinstance(children, list):
            raise ArkUIPageError(f"Lanhu layer {layer_id} layers must be a list")
        layers_by_id[layer_id] = layer
        layer_parent[layer_id] = parent_id
        layer_children[layer_id] = []
        layer_order.append(layer_id)
        for child in children:
            visit(child, layer_id)
            layer_children[layer_id].append(child["id"])

    artboard_layers = artboard.get("layers")
    if not isinstance(artboard_layers, list) or not artboard_layers:
        raise ArkUIPageError("Lanhu version_json artboard must contain layers")
    for root_layer in artboard_layers:
        visit(root_layer, None)

    instances: dict[str, dict[str, Any]] = {}
    if manifest is not None:
        if manifest.get("schema") != LANHU_COMPONENT_MANIFEST_SCHEMA:
            raise ArkUIPageError("Lanhu component manifest schema is unsupported")
        raw_instances = manifest.get("instances")
        if not isinstance(raw_instances, list) or len(raw_instances) > 10000:
            raise ArkUIPageError("Lanhu component manifest instances are malformed")
        for instance in raw_instances:
            if not isinstance(instance, dict) or not isinstance(instance.get("id"), str):
                raise ArkUIPageError(
                    "every Lanhu component manifest instance must have a string id"
                )
            if instance["id"] in instances:
                raise ArkUIPageError(
                    f"duplicate Lanhu component manifest instance id: {instance['id']}"
                )
            instances[instance["id"]] = instance
        if set(instances) != set(layers_by_id):
            raise ArkUIPageError("Lanhu version_json and component manifest instance sets differ")
        for component_id in layer_order:
            instance = instances[component_id]
            if (
                instance.get("parent_id") != layer_parent[component_id]
                or instance.get("children_ids") != layer_children[component_id]
            ):
                raise ArkUIPageError(
                    f"Lanhu version_json/component manifest hierarchy mismatch at {component_id}"
                )
    else:
        type_mapping = {
            "group": "Box",
            "shapeLayer": "Box",
            "text": "Text",
            "image": "Image",
        }
        for component_id in layer_order:
            layer = layers_by_id[component_id]
            migration = layer.get("migration")
            if migration is None and source_generated:
                raise ArkUIPageError(
                    "source-generated Lanhu version_json requires embedded migration metadata; "
                    "regenerate it or provide --lanhu-component-manifest for legacy output"
                )
            if isinstance(migration, dict):
                instance = {
                    "id": component_id,
                    "type": migration["componentType"],
                    "semantic_key": migration["semanticKey"],
                    "parent_id": layer_parent[component_id],
                    "children_ids": layer_children[component_id],
                    "sibling_index": (
                        layer_children[layer_parent[component_id]].index(component_id)
                        if layer_parent[component_id] is not None
                        else [
                            item for item in layer_order if layer_parent[item] is None
                        ].index(component_id)
                    ),
                    "style": migration["style"],
                    "custom_draw": migration["customDraw"],
                    "source": migration["source"],
                    "provenance": migration["provenance"],
                    "unresolved": migration["unresolved"],
                    "required_facts": migration.get("requiredFacts") or [],
                    "phase_trace": migration.get("phaseTrace"),
                }
            else:
                instance = {
                    "id": component_id,
                    "type": type_mapping.get(str(layer.get("type")), "Box"),
                    "semantic_key": layer.get("name") or component_id,
                    "parent_id": layer_parent[component_id],
                    "children_ids": layer_children[component_id],
                    "sibling_index": 0,
                    "style": {},
                    "custom_draw": None,
                    "source": {"attributes": []},
                    "provenance": [],
                    "unresolved": [],
                    "required_facts": [],
                }
            instances[component_id] = instance

    for component_id, instance in instances.items():
        raw_facts = instance.get("required_facts")
        if raw_facts is None:
            raw_facts = instance.get("requiredFacts")
        if source_generated and raw_facts is None:
            raise ArkUIPageError(
                f"source-generated Lanhu component {component_id} has no required fact contract"
            )
        try:
            instance["required_facts"] = normalize_required_facts(
                raw_facts or [], f"Lanhu component {component_id}.required_facts"
            )
        except ValueError as error:
            raise ArkUIPageError(str(error)) from error

    full_frames: dict[str, dict[str, float]] = {}
    visible_frames: dict[str, dict[str, float]] = {}
    for component_id in layer_order:
        raw_frame = require_lanhu_frame(
            layers_by_id[component_id].get("frame"), f"Lanhu layer {component_id}"
        )
        full = {
            "x": round((raw_frame["left"] - artboard_frame["left"]) / scale, 6),
            "y": round((raw_frame["top"] - artboard_frame["top"]) / scale, 6),
            "width": round(raw_frame["width"] / scale, 6),
            "height": round(raw_frame["height"] / scale, 6),
        }
        full_frames[component_id] = full
        left = max(0.0, full["x"])
        top = max(0.0, full["y"])
        right = min(viewport_width, full["x"] + full["width"])
        bottom = min(viewport_height, full["y"] + full["height"])
        ancestor = layer_parent[component_id]
        inside_scroll = False
        while ancestor is not None:
            ancestor_instance = instances[ancestor]
            rules = (ancestor_instance.get("source") or {}).get("layoutRules") or []
            if ancestor_instance.get("type") in {"LazyColumn", "LazyRow"} or any(r.get("kind") == "scroll" and r.get("enabled") is True for r in rules):
                inside_scroll = True
                break
            ancestor = layer_parent[ancestor]
        if source_generated and full["width"] >= 0 and full["height"] >= 0:
            # Source frames are diagnostic estimates, not visibility decisions.
            # Native measurement must keep even zero-size/estimated-offscreen nodes.
            visible_frames[component_id] = full
        elif right > left and bottom > top:
            visible_frames[component_id] = {
                "x": round(left, 6),
                "y": round(top, 6),
                "width": round(right - left, 6),
                "height": round(bottom - top, 6),
            }
        elif (
            str(instances[component_id].get("type")) == "Spacer"
            and isinstance(layer_parent[component_id], str)
            and (
                (
                    str(instances[layer_parent[component_id]].get("type"))
                    in PAGE_SNAPSHOT_ROW_COMPONENTS
                    and full["width"] > 0
                    and full["height"] == 0
                )
                or (
                    str(instances[layer_parent[component_id]].get("type"))
                    in PAGE_SNAPSHOT_COLUMN_COMPONENTS
                    and full["width"] == 0
                    and full["height"] > 0
                )
            )
            and 0 <= full["x"] <= viewport_width
            and 0 <= full["y"] <= viewport_height
        ):
            # A flow spacer can have a zero cross-axis size while still
            # participating in main-axis measurement and weight distribution.
            visible_frames[component_id] = full

    def visible_parent(component_id: str) -> str | None:
        parent_id = layer_parent[component_id]
        while parent_id is not None and parent_id not in visible_frames:
            parent_id = layer_parent[parent_id]
        return parent_id

    parent_by_id = {
        component_id: visible_parent(component_id)
        for component_id in visible_frames
    }
    children_by_id: dict[str, list[str]] = {
        component_id: [] for component_id in visible_frames
    }
    roots: list[str] = []
    for component_id in layer_order:
        if component_id not in visible_frames:
            continue
        parent_id = parent_by_id[component_id]
        if parent_id is None:
            roots.append(component_id)
        else:
            children_by_id[parent_id].append(component_id)

    components: list[dict[str, Any]] = []
    call_id_owners: dict[str, list[dict[str, Any]]] = defaultdict(list)
    elided: list[dict[str, str]] = []
    for component_id in layer_order:
        instance = instances[component_id]
        source = instance.get("source")
        attributes = source.get("attributes") if isinstance(source, dict) else None
        call_ids = sorted({
            attribute["call_id"]
            for attribute in (attributes or [])
            if isinstance(attribute, dict) and isinstance(attribute.get("call_id"), str)
        })
        if component_id not in visible_frames:
            elided.append({
                "source_semantic_key": str(instance.get("semantic_key") or component_id),
                "source_call_id": call_ids[0] if call_ids else f"unavailable:{component_id}",
                "reason": "outside_artboard",
            })
            continue
        try:
            style = normalize_style(
                instance.get("style") or {},
                f"Lanhu component manifest instance {component_id}.style",
            )
            provenance = normalize_provenance(
                instance.get("provenance") or [],
                f"Lanhu component manifest instance {component_id}.provenance",
            )
            unresolved = normalize_unresolved(
                instance.get("unresolved") or [],
                f"Lanhu component manifest instance {component_id}.unresolved",
            )
        except PageSnapshotError as error:
            raise ArkUIPageError(str(error)) from error
        visual_paths = apply_lanhu_visual_style(
            style, layers_by_id[component_id], scale
        )
        if visual_paths:
            provenance.append({
                "paths": sorted(set(visual_paths)),
                "origin": "source_resolved",
                "source": f"{version_path.name}#{component_id}",
            })
        parent_id = parent_by_id[component_id]
        siblings = children_by_id[parent_id] if parent_id is not None else roots
        component = {
            "id": component_id,
            "type": str(instance.get("type") or layers_by_id[component_id].get("type") or "Group"),
            "semantic_key": instance.get("semantic_key"),
            "bounds_dp": visible_frames[component_id],
            "source_layout_bounds_dp": full_frames[component_id],
            "visual_bounds_dp": None,
            "parent_id": parent_id,
            "children_ids": children_by_id[component_id],
            "sibling_index": siblings.index(component_id),
            "parent_mapping": "source-semantic-ancestor",
            "style": style,
            "provenance": provenance,
            "unresolved": unresolved,
            "required_facts": copy.deepcopy(instance.get("required_facts") or []),
            "phase_trace": copy.deepcopy(instance.get("phase_trace")),
            "custom_draw": copy.deepcopy(instance.get("custom_draw")),
            "call_ids": call_ids,
            "component_context": {
                "status": "candidate",
                "method": "source_layout_projection",
                "source_component_id": component_id,
                "business_component_id": None,
                "business_component_path": [],
                "evidence_runtime_ids": [],
            },
            "source": copy.deepcopy(source) if isinstance(source, dict) else {"attributes": []},
        }
        components.append(component)
        for call_id in call_ids:
            call_id_owners[call_id].append(component)
    by_id = {component["id"]: component for component in components}
    source_generation = meta.get("sourceGeneration") if isinstance(meta, dict) else None
    layout_relationships = normalize_lanhu_layout_relationships(
        source_generation.get("layoutRelationships") if isinstance(source_generation, dict) else [],
        by_id,
    )
    migration_meta = meta.get("migration")
    page = manifest.get("page") if manifest is not None else (
        migration_meta.get("page") if isinstance(migration_meta, dict) else None
    )
    if not isinstance(page, dict):
        artboard_id = str(artboard.get("id") or "")
        page_id, separator, page_state = artboard_id.rpartition("--")
        page = {
            "id": page_id if separator else artboard.get("name"),
            "state": page_state if separator else "default",
        }
    if not isinstance(page, dict):
        raise ArkUIPageError("Lanhu component manifest page identity is malformed")
    try:
        normalized_page = {
            "id": require_token(page.get("id"), "Lanhu page id"),
            "state": require_token(page.get("state"), "Lanhu page state"),
        }
    except PageSnapshotError as error:
        raise ArkUIPageError(str(error)) from error
    input_hashes = {"version_json_sha256": sha256_file(version_path)}
    if manifest_path is not None:
        input_hashes["component_manifest_sha256"] = sha256_file(manifest_path)
    result = {
        "file": version_path.name,
        "byte_count": version_bytes + manifest_bytes,
        "sha256": canonical_sha256(input_hashes),
        "input_format": "lanhu-version-json",
        "version_json": {
            "file": version_path.name,
            "sha256": sha256_file(version_path),
        },
        "page": normalized_page,
        "viewport": {
            "density": 1.0,
            "font_scale": 1.0,
            "orientation": "portrait" if viewport_height >= viewport_width else "landscape",
            "content_bounds_dp": {
                "x": 0.0,
                "y": 0.0,
                "width": viewport_width,
                "height": viewport_height,
            },
        },
        "screenshot": None,
        "components": components,
        "by_id": by_id,
        "by_call_id": {
            call_id: owners[0]
            for call_id, owners in call_id_owners.items()
        },
        "instances_by_call_id": dict(call_id_owners),
        "runtime_elided_source_components": elided,
        "source_component_tree": None,
        "layout_relationships": layout_relationships,
        "source_generated": source_generated,
        "font_faces": migration_meta.get("fontFaces", []) if isinstance(migration_meta, dict) else [],
        "required_fact_gate": required_fact_gate(list(instances.values())),
        "source_phase_consumption_gate": source_generation.get("phaseConsumptionGate")
        if isinstance(source_generation, dict) else None,
    }
    if manifest_path is not None:
        result["component_manifest"] = {
            "file": manifest_path.name,
            "sha256": sha256_file(manifest_path),
        }
    return result


def target_fact_phase(path: str) -> str:
    if path == 'style.input.single_line':
        return 'measure'
    if path in {
        'style.content.text', 'style.content.placeholder',
        'style.typography.font_size_sp', 'style.typography.font_weight',
        'style.typography.font_style', 'style.typography.font_family',
        'style.typography.letter_spacing_sp', 'style.typography.line_height_sp',
        'style.typography.max_lines', 'style.typography.overflow',
        'style.typography.min_lines', 'style.typography.soft_wrap',
    }:
        return 'measure'
    if path == 'style.typography.text_align':
        return 'layout'
    if path.startswith("source.modifiers.") and path.rsplit(".", 1)[-1] in {"fillmaxwidth", "fillmaxheight", "fillmaxsize", "matchparentsize", "wrapcontentwidth", "wrapcontentheight", "wrapcontentsize", "width", "height", "widthin", "heightin", "sizein", "weight", "verticalscroll", "horizontalscroll"}:
        return "measure"
    if path in {"source.modifiers.zindex", "style.layout.z_index"}:
        return "draw"
    if path in {"style.layout.alignment", "style.layout.horizontal_arrangement", "style.layout.vertical_arrangement", "style.layout.layout_direction", "style.layout.margin_dp"}:
        return "layout"
    if path.startswith("style.layout.") or path in {
        "style.asset.width_dp", "style.asset.height_dp"
    }:
        return "measure"
    if path.startswith("structure.") or path.startswith("source.modifiers."):
        return "layout"
    return "draw"


def build_target_phase_consumption_gate(
    page_input: dict[str, Any] | None,
    processed_component_ids: set[str],
    processed_call_ids: set[str],
    applied_paths: dict[str, set[str]],
    applied_component_paths: dict[str, set[str]] | None = None,
) -> dict[str, Any] | None:
    if page_input is None:
        return None
    checks: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for component in page_input.get("components") or []:
        source = component.get("source")
        call_id = source.get("call_id") if isinstance(source, dict) else None
        rendered = component.get("id") in processed_component_ids
        # A shared source call may have several differently configured instances.
        # Another instance's emitted field is not evidence for this component.
        call_paths: set[str] = set()
        if applied_component_paths is not None:
            call_paths.update(applied_component_paths.get(str(component.get("id")), set()))
        candidate_facts: dict[str, dict[str, Any]] = {}
        for fact in component.get("required_facts") or []:
            if not isinstance(fact, dict) or fact.get("status") == "not_applicable":
                continue
            path = fact.get("path")
            if not isinstance(path, str):
                continue
            candidate_facts[path] = {
                "path": path,
                "expression": fact.get("expression"),
                "origin": "required_fact",
                "resolved": fact.get("status") in {"resolved", "default_resolved"},
            }
        style = component.get("style")
        if isinstance(style, dict):
            for section_name, section in style.items():
                if not isinstance(section, dict):
                    continue
                for field_name, value in section.items():
                    if value is None or value == [] or value == {}:
                        continue
                    path = f"style.{section_name}.{field_name}"
                    candidate_facts.setdefault(path, {
                        "path": path,
                        "expression": None,
                        "origin": "resolved_style",
                    })
        for fact in candidate_facts.values():
            path = fact["path"]
            phase = target_fact_phase(path)
            not_applicable = (
                path == "style.content.content_description"
                and fact.get("expression") == "null"
            ) or (
                path in {"style.state.selected", "style.state.checked"}
                and nested_value(component, path) is False
                and rendered
            ) or (
                path == "style.state.clickable"
                and rendered
                # The page renderer owns visuals, not the behavior contract.
                # Keep this boundary in the report instead of dropping the field.
            ) or (
                path == "style.asset.sha256"
                and "style.asset.resource" in call_paths
            ) or (
                path in {"style.asset.width_dp", "style.asset.height_dp"}
                and fact["origin"] == "resolved_style"
                and "style.asset.resource" in call_paths
                and all(
                    f"style.layout.{axis}_dp" in call_paths
                    or any(
                        f"source.modifiers.{name}" in call_paths
                        for name in (f"fillmax{axis}", "fillmaxsize", "matchparentsize")
                    )
                    for axis in ("width", "height")
                )
            ) or (
                path == "style.surface.clip"
                and nested_value(component, path) is False
                and rendered
            ) or (
                path == "style.surface.alpha"
                and nested_value(component, path) == 1
                and rendered
            ) or (
                path == "style.state.visible"
                and nested_value(component, path) is True
                and rendered
            ) or (
                path == "style.transform.rotation_degrees"
                and nested_value(component, path) == 0
                and rendered
            ) or (
                path == "style.content.role"
                and rendered
            )
            consumed = ((rendered and path in call_paths) or not_applicable) and fact.get("resolved", True)
            check = {
                "component_id": component.get("id"),
                "call_id": call_id,
                "phase": phase,
                "path": path,
                "origin": fact["origin"],
                "status": "not_applicable" if not_applicable else (
                    "consumed" if consumed else "unconsumed"
                ),
            }
            if path == "style.state.clickable":
                check["reason"] = "interaction metadata only; click handlers require the separate behavior contract"
            checks.append(check)
            if not consumed:
                failures.append(check)
    return {
        "schema": "android-to-harmony.target-phase-gate.v1",
        "verdict": "pass" if not failures else "fail",
        "phase_order": ["measure", "layout", "draw"],
        "check_count": len(checks),
        "failure_count": len(failures),
        "status_counts": {
            status: sum(item["status"] == status for item in checks)
            for status in ("consumed", "not_applicable", "unconsumed")
        },
        "failures": failures,
        "checks": checks,
    }


def nested_value(value: dict[str, Any], path: str) -> Any:
    current: Any = value
    for segment in path.split("."):
        if not isinstance(current, dict) or segment not in current:
            return None
        current = current[segment]
    return current


def set_nested_value(value: dict[str, Any], path: str, child: Any) -> None:
    segments = path.split(".")
    current: dict[str, Any] = value
    for segment in segments[:-1]:
        nested = current.get(segment)
        if not isinstance(nested, dict):
            nested = {}
            current[segment] = nested
        current = nested
    current[segments[-1]] = copy.deepcopy(child)


def normalized_runtime_bounds(
    bounds: dict[str, float],
    source_content: dict[str, float],
    runtime_content: dict[str, float],
) -> dict[str, float]:
    return {
        "x": source_content["x"] + bounds["x"] - runtime_content["x"],
        "y": source_content["y"] + bounds["y"] - runtime_content["y"],
        "width": bounds["width"],
        "height": bounds["height"],
    }


def same_bounds(left: dict[str, float], right: dict[str, float], tolerance: float = 0.002) -> bool:
    return all(abs(left[name] - right[name]) <= tolerance for name in ("x", "y", "width", "height"))


def fuse_android_page_inputs(
    source_page: dict[str, Any] | None,
    runtime_page: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if runtime_page is None:
        return source_page
    if source_page is None:
        raise ArkUIPageError("Android runtime page JSON requires --android-page-json source-tree input")
    if source_page["page"] != runtime_page["page"]:
        raise ArkUIPageError("Android source-tree and runtime page identity/state must match")
    source_viewport = source_page["viewport"]
    runtime_viewport = runtime_page["viewport"]
    if (
        source_viewport["orientation"] != runtime_viewport["orientation"]
        or abs(source_viewport["font_scale"] - runtime_viewport["font_scale"]) > 0.001
    ):
        raise ArkUIPageError("Android source-tree and runtime orientation/font scale must match")
    if not source_page["components"] or not all(
        component["parent_mapping"] == "source-semantic-ancestor"
        for component in source_page["components"]
    ):
        raise ArkUIPageError("Android runtime fusion requires a source-tree page input")

    fused = copy.deepcopy(source_page)
    source_by_id = fused["by_id"] = {
        component["id"]: component for component in fused["components"]
    }
    source_by_semantic: dict[str, list[dict[str, Any]]] = defaultdict(list)
    source_by_text: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for component in fused["components"]:
        semantic_key = component.get("semantic_key")
        if isinstance(semantic_key, str):
            source_by_semantic[semantic_key].append(component)
        text = component["style"]["content"]["text"]
        if isinstance(text, str) and text:
            source_by_text[(component["type"], text)].append(component)

    source_content = source_viewport["content_bounds_dp"]
    runtime_content = runtime_viewport["content_bounds_dp"]
    matched_source_ids: set[str] = set()
    matched_runtime_ids: set[str] = set()
    matched_leaf_count = 0
    matched_business_container_count = 0
    rejected_container_count = 0
    mappings: list[dict[str, str]] = []
    planned: list[tuple[dict[str, Any], dict[str, Any], str, dict[str, float]]] = []

    def directly_matched_source_target(
        runtime_component: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str | None]:
        semantic_key = runtime_component.get("semantic_key")
        semantic_matches = (
            source_by_semantic.get(semantic_key, []) if isinstance(semantic_key, str) else []
        )
        if len(semantic_matches) == 1:
            candidate = semantic_matches[0]
            if candidate["type"] == runtime_component["type"]:
                return candidate, "semantic_key"
        context = runtime_component.get("component_context")
        if isinstance(context, dict):
            source_id = context.get("source_component_id")
            candidate = source_by_id.get(source_id) if isinstance(source_id, str) else None
            if isinstance(candidate, dict) and candidate["type"] == runtime_component["type"]:
                return candidate, "source_component_id"
        text = runtime_component["style"]["content"]["text"]
        if isinstance(text, str) and text:
            text_matches = source_by_text.get((runtime_component["type"], text), [])
            if len(text_matches) == 1:
                return text_matches[0], "unique_text"
        if isinstance(context, dict) and runtime_component["type"] in BUTTON_CONTAINER_COMPONENTS:
            business_id = context.get("business_component_id")
            candidate = source_by_id.get(business_id) if isinstance(business_id, str) else None
            if (
                isinstance(candidate, dict)
                and candidate["parent_id"] is not None
                and candidate["type"] not in PAGE_SNAPSHOT_FLOW_COMPONENTS
            ):
                return candidate, "business_component_id"
        return None, None

    def source_target(runtime_component: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
        direct_target, direct_method = directly_matched_source_target(runtime_component)
        if direct_target is not None:
            return direct_target, direct_method
        state = runtime_component["style"]["state"]
        content = runtime_component["style"]["content"]
        if state.get("clickable") is not True and content.get("role") != "button":
            return None, None
        anchored_containers: dict[str, dict[str, Any]] = {}
        for child_id in runtime_component["children_ids"]:
            child = runtime_page["by_id"].get(child_id)
            if not isinstance(child, dict):
                continue
            child_target, _child_method = directly_matched_source_target(child)
            if child_target is None:
                continue
            parent_id = child_target.get("parent_id")
            while isinstance(parent_id, str):
                candidate = source_by_id[parent_id]
                source = candidate.get("source")
                is_project_container = (
                    isinstance(source, dict)
                    and source.get("custom_component") is True
                    and candidate["type"] not in PAGE_SNAPSHOT_FLOW_COMPONENTS
                )
                if candidate["type"] in BUTTON_CONTAINER_COMPONENTS or is_project_container:
                    anchored_containers[candidate["id"]] = candidate
                    break
                parent_id = candidate.get("parent_id")
        if len(anchored_containers) == 1:
            return next(iter(anchored_containers.values())), "child_source_anchor"
        return None, None

    def apply_runtime_component(
        target: dict[str, Any],
        runtime_component: dict[str, Any],
        method: str,
    ) -> None:
        nonlocal matched_leaf_count, matched_business_container_count
        old_bounds = copy.deepcopy(target["bounds_dp"])
        new_bounds = normalized_runtime_bounds(
            runtime_component["bounds_dp"], source_content, runtime_content
        )
        target["bounds_dp"] = new_bounds
        target["_runtime_bounds_applied"] = True
        runtime_visual_bounds = runtime_component.get("visual_bounds_dp")
        if isinstance(runtime_visual_bounds, dict):
            target["visual_bounds_dp"] = normalized_runtime_bounds(
                runtime_visual_bounds, source_content, runtime_content
            )
        for record in runtime_component["provenance"]:
            if record["origin"] not in {"runtime", "pixel_sampled"}:
                continue
            copied_paths: list[str] = []
            for path in record["paths"]:
                if not runtime_overlay_style_path_allowed(method, path):
                    continue
                value = nested_value(runtime_component, path)
                if value is None:
                    continue
                set_nested_value(target, path, value)
                copied_paths.append(path)
            if copied_paths:
                target["provenance"].append({
                    "origin": record["origin"],
                    "paths": copied_paths,
                    "source": "Android runtime overlay: " + runtime_page["file"],
                })
        target["unresolved"].extend(
            unresolved
            for unresolved in runtime_component["unresolved"]
            if unresolved not in target["unresolved"]
        )
        if method in {"business_component_id", "child_source_anchor"}:
            matched_business_container_count += 1
            for descendant in fused["components"]:
                if descendant["id"] == target["id"]:
                    continue
                if same_bounds(descendant["bounds_dp"], old_bounds) or is_direct_native_wrapper(
                    target, descendant
                ):
                    current = descendant
                    ancestors: set[str] = set()
                    while isinstance(current.get("parent_id"), str):
                        parent_id = current["parent_id"]
                        if parent_id == target["id"]:
                            descendant["bounds_dp"] = copy.deepcopy(new_bounds)
                            descendant["_runtime_bounds_applied"] = True
                            break
                        if parent_id in ancestors:
                            break
                        ancestors.add(parent_id)
                        current = source_by_id.get(parent_id, {})
            parent_id = target.get("parent_id")
            while isinstance(parent_id, str):
                parent = source_by_id[parent_id]
                parent_bounds = parent["bounds_dp"]
                if (
                    abs(parent_bounds["y"] - old_bounds["y"]) > 0.002
                    or abs(parent_bounds["height"] - old_bounds["height"]) > 0.002
                ):
                    break
                parent["bounds_dp"] = {
                    **parent_bounds,
                    "y": new_bounds["y"],
                    "height": new_bounds["height"],
                }
                parent["_runtime_bounds_applied"] = True
                parent_id = parent.get("parent_id")
        else:
            matched_leaf_count += 1
        matched_source_ids.add(target["id"])
        matched_runtime_ids.add(runtime_component["id"])
        mappings.append({
            "runtime_component_id": runtime_component["id"],
            "source_component_id": target["id"],
            "method": method,
        })

    planned_source_ids: set[str] = set()
    for runtime_component in runtime_page["components"]:
        target, method = source_target(runtime_component)
        if target is None or method is None or target["id"] in planned_source_ids:
            continue
        if method not in {"business_component_id", "child_source_anchor"}:
            if target["children_ids"]:
                rejected_container_count += 1
                continue
            if target["type"] not in PAGE_RUNTIME_OVERLAY_LEAF_TYPES:
                continue
        planned_source_ids.add(target["id"])
        planned.append((
            target,
            runtime_component,
            method,
            normalized_runtime_bounds(
                runtime_component["bounds_dp"], source_content, runtime_content
            ),
        ))

    def is_descendant_or_self(component_id: str, ancestor_id: str) -> bool:
        current = source_by_id.get(component_id)
        visited: set[str] = set()
        while isinstance(current, dict):
            if current["id"] == ancestor_id:
                return True
            parent_id = current.get("parent_id")
            if not isinstance(parent_id, str) or parent_id in visited:
                return False
            visited.add(parent_id)
            current = source_by_id.get(parent_id)
        return False

    def component_depth(component: dict[str, Any]) -> int:
        depth = 0
        current = component
        visited: set[str] = set()
        while isinstance(current.get("parent_id"), str):
            parent_id = current["parent_id"]
            if parent_id in visited:
                break
            visited.add(parent_id)
            depth += 1
            current = source_by_id[parent_id]
        return depth

    coherent_custom_groups: dict[str, tuple[float, float]] = {}
    if source_page.get("input_format") != "lanhu-version-json":
        for component in fused["components"]:
            source = component.get("source")
            if not isinstance(source, dict) or source.get("custom_component") is not True:
                continue
            descendant_matches = [
                entry
                for entry in planned
                if is_descendant_or_self(entry[0]["id"], component["id"])
            ]
            if not descendant_matches:
                continue
            x_deltas = [
                entry[3]["x"] - entry[0]["bounds_dp"]["x"]
                for entry in descendant_matches
            ]
            y_deltas = [
                entry[3]["y"] - entry[0]["bounds_dp"]["y"]
                for entry in descendant_matches
            ]
            x_shift = float(median(x_deltas))
            y_shift = float(median(y_deltas))
            if all(
                abs(delta - x_shift) <= 6.0 for delta in x_deltas
            ) and all(abs(delta - y_shift) <= 6.0 for delta in y_deltas):
                coherent_custom_groups[component["id"]] = (x_shift, y_shift)

    selected_groups: dict[str, tuple[float, float]] = {}
    for target, _runtime_component, _method, _runtime_bounds in planned:
        candidates = [
            source_by_id[component_id]
            for component_id in coherent_custom_groups
            if is_descendant_or_self(target["id"], component_id)
        ]
        if not candidates:
            continue
        selected = min(candidates, key=component_depth)
        selected_groups[selected["id"]] = coherent_custom_groups[selected["id"]]

    expanded_groups: dict[str, tuple[float, float]] = {}
    for component_id, shift in selected_groups.items():
        selected = source_by_id[component_id]
        root = selected
        parent_id = root.get("parent_id")
        while isinstance(parent_id, str):
            parent = source_by_id[parent_id]
            if parent["parent_id"] is None or parent["children_ids"] != [root["id"]]:
                break
            root = parent
            parent_id = root.get("parent_id")
        expanded_groups[root["id"]] = (
            0.0
            if root["id"] != selected["id"]
            and root["bounds_dp"]["width"] > selected["bounds_dp"]["width"] + 1.0
            else shift[0],
            shift[1],
        )

    shifted_source_group_count = 0
    for component_id, (x_shift, y_shift) in expanded_groups.items():
        shifted_source_group_count += 1
        for component in fused["components"]:
            if not is_descendant_or_self(component["id"], component_id):
                continue
            component["bounds_dp"] = {
                **component["bounds_dp"],
                "x": component["bounds_dp"]["x"] + x_shift,
                "y": component["bounds_dp"]["y"] + y_shift,
            }
            component["_runtime_bounds_applied"] = True
            visual_bounds = component.get("visual_bounds_dp")
            if isinstance(visual_bounds, dict):
                component["visual_bounds_dp"] = {
                    **visual_bounds,
                    "x": visual_bounds["x"] + x_shift,
                    "y": visual_bounds["y"] + y_shift,
                }

    for target, runtime_component, method, _runtime_bounds in planned:
        apply_runtime_component(target, runtime_component, method)

    fused["by_call_id"] = {
        call_id: component
        for component in fused["components"]
        for call_id in component["call_ids"]
        if len(component["call_ids"]) == 1
    }
    owners: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for component in fused["components"]:
        if len(component["call_ids"]) == 1:
            owners[component["call_ids"][0]].append(component)
    fused["instances_by_call_id"] = dict(owners)
    fused["runtime_overlay"] = {
        "file": runtime_page["file"],
        "byte_count": runtime_page["byte_count"],
        "sha256": runtime_page["sha256"],
        "screenshot": runtime_page["screenshot"],
        "viewport": runtime_page["viewport"],
        "matched_leaf_count": matched_leaf_count,
        "matched_business_container_count": matched_business_container_count,
        "rejected_container_count": rejected_container_count,
        "shifted_source_group_count": shifted_source_group_count,
        "unmatched_runtime_count": len(runtime_page["components"]) - len(matched_runtime_ids),
        "mappings": mappings,
    }
    return fused


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
    escapes = {'\\': '\\\\', "'": "\\'", '\n': '\\n', '\r': '\\r', '\t': '\\t'}
    return "'" + ''.join(escapes.get(char, f'\\u{ord(char):04x}' if ord(char) < 32 or char in '\u2028\u2029' else char)
                         for char in value) + "'"


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
        resource_names: set[str],
        string_values: dict[str, str],
        android_page_input: dict[str, Any],
        tinted_vector_resources: dict[tuple[str, str], str] | None = None,
    ) -> None:
        if not isinstance(android_page_input, dict):
            raise ArkUIPageError(
                "source-generated page JSON is required; source translation fallback is disabled"
            )
        self.root = root
        self.closure: dict[str, Any] = {}
        self.definitions: dict[tuple[str, str], dict[str, Any]] = {}
        self.resource_names = resource_names
        self.string_values = string_values
        self.dimension_token_values: dict[str, str] = {}
        self.number_token_values: dict[str, str] = {}
        self.color_token_values: dict[str, str] = {}
        self.data_classes: dict[str, dict[str, Any]] = {}
        self.enum_classes: dict[str, set[str]] = {}
        self.enum_string_properties: dict[str, dict[str, dict[str, str]]] = {}
        self.route_symbols: dict[str, str] = {}
        self.route_base_types: set[str] = set()
        self.android_page_input = android_page_input
        self.android_page_layout_mode = "snapshot"
        self.verified_font_faces: list[dict[str, Any]] = []
        self.typography_font_roles: dict[str, dict[str, Any]] = {}
        self.tinted_vector_resources = tinted_vector_resources or {}
        self.android_page_by_id: dict[str, dict[str, Any]] = {}
        self.android_page_by_call_id: dict[str, dict[str, Any]] = {}
        self.android_page_instances_by_call_id: dict[str, list[dict[str, Any]]] = {}
        self.android_page_runtime_elided: list[dict[str, str]] = []
        self.android_page_runtime_elided_by_call_id: dict[str, list[dict[str, str]]] = defaultdict(list)
        self.android_source_tree_by_id: dict[str, dict[str, Any]] = {}
        self.android_source_layout_by_subject: dict[str, dict[str, Any]] = {}
        self.android_page_applied_paths: dict[str, set[str]] = defaultdict(set)
        self.android_page_applied_component_paths: dict[str, set[str]] = defaultdict(set)
        self.android_page_reference_paths: dict[str, set[str]] = defaultdict(set)
        self.android_page_processed_call_ids: set[str] = set()
        self.android_page_processed_component_ids: set[str] = set()
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
        self.reached_keys: list[tuple[str, str]] = []
        self.calls_by_definition: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        self.selected_calls: list[dict[str, Any]] = []
        self.selected_calls_by_id: dict[str, dict[str, Any]] = {}
        self.incoming_project_calls: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        self.android_page_by_id = android_page_input["by_id"]
        self._page_constraint_states: dict[str, dict[str, Any]] = {}
        if android_page_input["components"] and all(
            component.get("parent_mapping") == "source-semantic-ancestor"
            for component in android_page_input["components"]
        ):
            self.android_page_layout_mode = "source-tree"
        self.android_source_tree_by_id = android_page_input["by_id"]
        self.android_source_layout_by_subject = {
            relationship["subject_id"]: relationship
            for relationship in android_page_input.get("layout_relationships") or []
        }
        self.android_page_instances_by_call_id = android_page_input["instances_by_call_id"]
        self.android_page_runtime_elided = android_page_input["runtime_elided_source_components"]
        for component in android_page_input["components"]:
            for fact in component.get("required_facts") or []:
                if fact["status"] in {"unresolved", "symbolic"}:
                    self.add_unresolved(
                        "page_json_required_fact", None,
                        "Source fact remains unresolved; supported content is still generated",
                        page_component_id=component["id"],
                        path=fact["path"], expression=fact.get("expression"),
                        page_reason=fact.get("reason"),
                    )
            for unresolved in component["unresolved"]:
                self.add_unresolved(
                    "android_page_visual_fact",
                    None,
                    "Android page JSON retains an unresolved visual fact",
                    page_component_id=component["id"],
                    semantic_key=component.get("semantic_key"),
                    path=unresolved["path"],
                    expression=unresolved["expression"],
                    page_reason=unresolved["reason"],
                )
        source_phase_gate = android_page_input.get("source_phase_consumption_gate") or {}
        for failure in source_phase_gate.get("failures") or []:
            self.add_unresolved(
                "page_json_source_phase", None, failure["reason"],
                page_component_id=failure["component_id"], phase=failure["phase"],
                relationship_id=failure.get("relationship_id"),
            )
        self.cycle_edges: set[tuple[tuple[str, str], tuple[str, str]]] = set()

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
        rounded = Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        return decimal_literal(rounded)

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

    def android_page_instances(self, call: dict[str, Any]) -> list[dict[str, Any]]:
        return self.android_page_instances_by_call_id.get(call["call_id"], [])

    @staticmethod
    def android_page_path_value(component: dict[str, Any], path: str) -> Any:
        value: Any = component
        for segment in path.split("."):
            if not isinstance(value, dict) or segment not in value:
                return None
            value = value[segment]
        return value

    def android_page_invariant_value(self, call: dict[str, Any], path: str) -> Any:
        instances = self.android_page_instances(call)
        if not instances:
            return None
        values = [self.android_page_path_value(component, path) for component in instances]
        if any(value != values[0] for value in values[1:]):
            return None
        return values[0]

    def android_page_value_is_proven_for_call(
        self,
        call: dict[str, Any],
        path: str,
        value: Any,
    ) -> bool:
        instances = self.android_page_instances(call)
        return bool(instances) and all(
            self.android_page_path_value(component, path) == value
            and self.page_value_is_proven(component, path, value)
            for component in instances
        )

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
        instances = self.android_page_instances(call)
        if not instances:
            return False
        value = self.android_page_invariant_value(call, path)
        return value is not None and all(
            self.page_path_is_proven(component, path) for component in instances
        )

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
        if len(self.android_page_instances(call)) > 1:
            return None
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

    def page_layout_length(self, value: float) -> str:
        self._uses_page_layout_pixels = True
        return f"this.layoutPx({self.page_number(value)})"

    def page_layout_edges(self, value: dict[str, Any]) -> str:
        rendered = {name: self.page_layout_length(value[name]) for name in ("left", "right", "top", "bottom")}
        if len(set(rendered.values())) == 1:
            return rendered["left"]
        return "{ " + ", ".join(f"{name}: {rendered[name]}" for name in rendered) + " }"

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
        if isinstance(semantic_key, str) and len(self.android_page_instances(call)) == 1:
            lines.append(f".id({arkts_string(semantic_key)})")

        def apply(path: str, value: Any, line: str) -> None:
            if value is None:
                return
            if not self.android_page_value_is_proven_for_call(call, path, value):
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
        width = self.android_page_invariant_value(call, "bounds_dp.width")
        height = self.android_page_invariant_value(call, "bounds_dp.height")
        if not self.uses_source_image_geometry(call):
            if width is not None:
                lines.append(f".width({self.page_number(width)})")
                self.record_android_page_path(call, "bounds_dp.width")
            if height is not None:
                lines.append(f".height({self.page_number(height)})")
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

        if component_kind in {"Image", "Icon", "AsyncImage"}:
            tint = style["asset"]["tint"]
            if tint is not None:
                if self.android_page_value_is_proven_for_call(
                    call, "style.asset.tint", tint
                ):
                    lines.extend(
                        self.image_tint_lines(arkts_string(tint), prefer_template=True)
                    )
                    self.record_android_page_path(call, "style.asset.tint")
                else:
                    self.add_unresolved(
                        "android_page_visual_fact",
                        call,
                        "Android page visual value is not bound to resolved provenance",
                        page_component_id=component["id"],
                        path="style.asset.tint",
                    )

        transform = style["transform"]
        translation_x = transform["translation_x_dp"]
        translation_y = transform["translation_y_dp"]
        if translation_x is not None or translation_y is not None:
            translation_values = {
                "translation_x_dp": translation_x,
                "translation_y_dp": translation_y,
            }
            if self.android_page_value_is_proven_for_call(
                call,
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
            if self.android_page_value_is_proven_for_call(call, "style.transform", scale_values):
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
        implicit_state_defaults = {
            "style.state.visible": True,
            "style.state.enabled": True,
            "style.state.selected": False,
            "style.state.checked": False,
            "style.state.clickable": False,
        }
        implicit_roles = {
            "Text": "text",
            "BasicText": "text",
            "ClickableText": "text",
            "BasicTextField": "textbox",
            "TextField": "textbox",
            "OutlinedTextField": "textbox",
            "Button": "button",
            "TextButton": "button",
            "OutlinedButton": "button",
            "IconButton": "button",
            "Image": "image",
            "Icon": "image",
            "AsyncImage": "image",
            "Checkbox": "checkbox",
            "CheckBox": "checkbox",
            "Switch": "switch",
            "RadioButton": "radio",
        }
        implicitly_clickable_components = {
            "BasicTextField",
            "TextField",
            "OutlinedTextField",
            "Button",
            "TextButton",
            "OutlinedButton",
            "IconButton",
        }
        implicitly_clipping_components = {
            "Button",
            "TextButton",
            "OutlinedButton",
            "IconButton",
        }
        for section_name, section in style.items():
            for field_name, value in section.items():
                path = f"style.{section_name}.{field_name}"
                if value is None or path in applied or path == "style.content.text":
                    continue
                if not self.android_page_value_is_proven_for_call(call, path, value):
                    continue
                if (
                    implicit_state_defaults.get(path) == value
                    or (
                        path == "style.state.clickable"
                        and value is True
                        and component_kind in implicitly_clickable_components
                    )
                    or (
                        path == "style.surface.clip"
                        and value is True
                        and component_kind in implicitly_clipping_components
                    )
                    or (
                        path == "style.content.role"
                        and implicit_roles.get(component_kind) == value
                    )
                ):
                    self.record_android_page_path(call, path)
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

    def page_snapshot_source_lines(self, call: dict[str, Any]) -> list[str]:
        key = (call["source"], call["composable"])
        definition = self.definitions.get(key, {})
        previous_defaults = self._current_parameter_defaults
        previous_definition_key = self._current_definition_key
        previous_local_values = self._current_local_values
        self._current_definition_key = key
        self._current_parameter_defaults = {
            parameter["name"]: parameter["default"]
            for parameter in definition.get("parameters", [])
            if isinstance(parameter, dict)
            and isinstance(parameter.get("name"), str)
            and isinstance(parameter.get("default"), str)
        }
        local_values = call.get("local_values")
        if isinstance(local_values, dict):
            self._current_local_values = {
                **previous_local_values,
                **{
                    name: value
                    for name, value in local_values.items()
                    if isinstance(name, str) and isinstance(value, str)
                },
            }
        try:
            if call["component"] in {"Text", "BasicText", "ClickableText"}:
                return self.semantic_lines(call, {})
            if call["component"] in {"Card", "ElevatedCard", "OutlinedCard", "Surface"}:
                lines, _fully_handled = self.card_style_lines(call, {})
                return lines
            if call["component"] in {"Image", "Icon"}:
                semantic = call.get("semantic_arguments", {})
                painter = semantic.get("painter") if isinstance(semantic, dict) else None
                expression = painter.get("expression") if isinstance(painter, dict) else None
                media = (
                    self.painter_resource_expression(expression, {})
                    if isinstance(expression, str)
                    else None
                )
                if media is None:
                    return []
                lines = [f"Image({media})"]
                modifiers = self.modifier_lines(call, {})
                parent = self.selected_calls_by_id.get(call.get("parent_call_id"))
                if (
                    isinstance(parent, dict)
                    and parent.get("component") == "IconButton"
                    and not any(line.startswith(".width(") for line in modifiers)
                    and not any(line.startswith(".height(") for line in modifiers)
                ):
                    modifiers.extend([".width(24)", ".height(24)"])
                tint_expression: str | None = None
                tint = semantic.get("tint") if isinstance(semantic, dict) else None
                if isinstance(tint, dict) and isinstance(tint.get("expression"), str):
                    tint_expression = tint["expression"]
                color_filter = semantic.get("colorFilter") if isinstance(semantic, dict) else None
                color_filter_expression = (
                    color_filter.get("expression") if isinstance(color_filter, dict) else None
                )
                if isinstance(color_filter_expression, str):
                    match = re.fullmatch(
                        r"ColorFilter\.tint\s*\(\s*(.+)\s*\)",
                        color_filter_expression.strip(),
                    )
                    if match is not None:
                        tint_expression = match.group(1).strip()
                if tint_expression is not None:
                    resolved_tint = self.current_parameter_default_expression(tint_expression, {})
                    color = self.color_expression(resolved_tint, call, {})
                    if color is not None:
                        lines.extend(self.image_tint_lines(color, call["component"] == "Icon"))
                lines.extend(modifiers)
                return lines
            if call["component"] == "Spacer":
                return ["Blank()", *self.modifier_lines(call, {})]
            if call["component"] not in {"BasicTextField", "TextField", "OutlinedTextField"}:
                return []
            semantic = call.get("semantic_arguments", {})
            lines: list[str] = []
            text_style = semantic.get("textStyle") if isinstance(semantic, dict) else None
            text_style_expression = text_style.get("expression") if isinstance(text_style, dict) else None
            if isinstance(text_style_expression, str):
                resolved = self.current_parameter_default_expression(text_style_expression, {})
                resolved_lines = self.inline_text_style_lines(resolved, call, {})
                if resolved_lines is not None:
                    lines.extend(resolved_lines)
            children = [
                candidate
                for candidate in self.calls_by_definition.get(key, [])
                if candidate.get("parent_call_id") == call["call_id"]
            ]
            if call["component"] == "BasicTextField":
                lines.extend(self.basic_text_field_decoration_lines(children, call, {}))
            return lines
        finally:
            self._current_parameter_defaults = previous_defaults
            self._current_definition_key = previous_definition_key
            self._current_local_values = previous_local_values

    @staticmethod
    def page_snapshot_line(lines: list[str], prefix: str) -> str | None:
        return next((line for line in reversed(lines) if line.startswith(prefix)), None)

    def page_snapshot_text_value(self, component: dict[str, Any]) -> str:
        text = component['style']['content'].get('text')
        return text if isinstance(text, str) else ''

    def page_snapshot_descendant_consumes_typography_color(
        self,
        component: dict[str, Any],
        color: str,
    ) -> bool:
        pending = list(component.get("children_ids") or [])
        while pending:
            descendant_id = pending.pop()
            descendant = self.android_page_by_id.get(descendant_id)
            if not isinstance(descendant, dict):
                continue
            typography = (descendant.get("style") or {}).get("typography") or {}
            if (
                typography.get("color") == color
                and "style.typography.color"
                in self.android_page_applied_component_paths.get(descendant_id, set())
            ):
                return True
            pending.extend(descendant.get("children_ids") or [])
        return False

    @staticmethod
    def page_snapshot_layout_rules(component: dict[str, Any]) -> list[dict[str, Any]]:
        source = component.get("source")
        rules = source.get("layoutRules") if isinstance(source, dict) else None
        return [rule for rule in rules if isinstance(rule, dict)] if isinstance(rules, list) else []

    @classmethod
    def page_snapshot_axis_layout_rule(
        cls,
        component: dict[str, Any],
        axis: str,
    ) -> dict[str, Any] | None:
        result: dict[str, Any] | None = None
        for rule in cls.page_snapshot_layout_rules(component):
            if (
                rule.get("kind") == "sizing"
                and axis in (rule.get("axes") or [])
            ) or (
                rule.get("kind") == "intrinsic_size"
                and rule.get("axis") == axis
            ):
                result = rule
        return result

    @classmethod
    def page_snapshot_source_layout_weight(cls, component: dict[str, Any]) -> str | None:
        for rule in cls.page_snapshot_layout_rules(component):
            if rule.get("kind") == "weight":
                if rule.get("fill") is not True:
                    return None
                return f".layoutWeight({decimal_literal(Decimal(str(rule['value'])))})"
        source = component.get("source")
        modifiers = source.get("modifiers") if isinstance(source, dict) else None
        if not isinstance(modifiers, list):
            return None
        for modifier in modifiers:
            if not isinstance(modifier, dict) or modifier.get("name") != "weight":
                continue
            arguments = modifier.get("arguments")
            if not isinstance(arguments, str):
                continue
            positional, named = named_arguments(arguments)
            if named.get("fill", positional[1] if len(positional) > 1 else "true").strip() != "true":
                return None
            value = (
                positional[0].strip()
                if positional
                else str(named.get("weight") or "").strip()
            )
            match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)[fF]?", value)
            if match is not None:
                return f".layoutWeight({match.group(1)})"
        return None

    @staticmethod
    def page_snapshot_has_explicit_axis_size(
        component: dict[str, Any],
        axis: str,
    ) -> bool:
        style = component.get("style")
        if not isinstance(style, dict):
            return False
        layout = style.get("layout")
        key = f"{axis}_dp"
        return isinstance(layout, dict) and layout.get(key) is not None

    def page_snapshot_dimension_lines(
        self,
        component: dict[str, Any],
        bounds: dict[str, float],
        parent: dict[str, Any] | None,
        parent_type: str | None,
        is_text: bool,
    ) -> list[str]:
        component_type = component["type"]
        weight = self.page_snapshot_source_layout_weight(component)
        result: list[str] = []
        for axis in ("width", "height"):
            rule = self.page_snapshot_axis_layout_rule(component, axis)
            if rule is None and self.page_snapshot_stretched_axis(component, axis):
                result.append(".alignSelf(ItemAlign.Stretch)")
                continue
            if isinstance(rule, dict):
                if rule.get("kind") == "intrinsic_size" or rule.get("mode") == "wrap_content":
                    self.record_page_layout_rule(component, rule)
                    if component_type == "ConstraintLayout":
                        # RelativeContainer otherwise defaults to filling both axes.
                        fills = any(
                            (self.page_snapshot_axis_layout_rule(child, axis) or {}).get("mode") == "fill_parent"
                            for child_id in component.get("children_ids", [])
                            if (child := self.android_page_by_id.get(child_id)) is not None
                        )
                        result.append(f".{axis}({arkts_string('100%' if fills else 'auto')})")
                    continue
                if rule.get("mode") in {"fill_parent", "match_parent"}:
                    match_parent_name = getattr(self, '_page_match_parent_sizes', {}).get(component['id'])
                    if rule.get('mode') == 'match_parent' and match_parent_name:
                        result.append(f'.{axis}(this.{match_parent_name}{axis.title()})')
                        self.record_page_layout_rule(component, rule)
                        continue
                    parent_rule = self.page_snapshot_axis_layout_rule(parent, axis) if parent else None
                    if parent_rule and parent_rule.get("kind") == "intrinsic_size":
                        if (parent_type, axis) in {("Row", "height"), ("Column", "width")} and rule["fraction"] == 1:
                            result.append(".alignSelf(ItemAlign.Stretch)")
                        else:
                            self.add_page_json_unresolved(component, f"layout.{axis}", "intrinsic parent fill requires a full cross-axis stretch")
                    else:
                        percentage = decimal_literal(Decimal(str(float(rule["fraction"]) * 100)))
                        result.append(f".{axis}('{percentage}%')")
                    self.record_page_layout_rule(component, rule)
                    continue
            if self.page_snapshot_root_fills_viewport(component, parent, axis):
                result.append(f".{axis}('100%')")
                continue
            if self.page_snapshot_fills_parent_inner_axis(component, parent, axis):
                result.append(f".{axis}('100%')")
                continue
            weighted_axis = (
                weight is not None
                and (
                    (parent_type == "Row" and axis == "width")
                    or (parent_type == "Column" and axis == "height")
                )
            )
            if weighted_axis:
                continue
            layout = component["style"]["layout"]
            explicit = layout.get(f"{axis}_dp")
            explicit_path = f"style.layout.{axis}_dp"
            if explicit is not None:
                self.record_page_paths(component, {explicit_path})
                result.append(f".{axis}({self.page_layout_length(float(explicit))})")
            elif component_type in {"CenterAlignedTopAppBar", "TopAppBar"}:
                if axis == "width":
                    result.append(".width('100%')")
            elif component_type == "Spacer" and weight is None:
                result.append(f".{axis}(0)")
        return result

    def page_snapshot_intrinsic_image_lines(self, component: dict[str, Any]) -> list[str]:
        if component["type"] not in {"Image", "Icon", "AsyncImage"}:
            return []
        if any(
            fact.get("origin") == "modifier" and fact.get("path") in {"style.asset.width_dp", "style.asset.height_dp"}
            for fact in component.get("required_facts", [])
        ):
            self.add_page_json_unresolved(component, "style.layout", "legacy image JSON conflates modifier sizes with intrinsic asset sizes; regenerate the page JSON")
            return []
        asset = component["style"]["asset"]
        axes = [
            axis for axis in ("width", "height")
            if not self.page_snapshot_has_explicit_axis_size(component, axis)
            and (self.page_snapshot_axis_layout_rule(component, axis) or {}).get("mode") not in {"fill_parent", "match_parent"}
        ]
        if not axes:
            return []
        sizes = {axis: asset.get(f"{axis}_dp") for axis in ("width", "height")}
        if not all(isinstance(value, (int, float)) and value > 0 for value in sizes.values()):
            return []
        if asset.get("content_scale") not in {None, "fit", "inside"}:
            self.add_page_json_unresolved(component, "style.asset.content_scale", "intrinsic image measurement currently supports Fit/Inside; other modes require explicit layout sizes")
            return []
        limits = {"max" + axis.title(): sizes[axis] for axis in axes}
        for rule in self.page_snapshot_layout_rules(component):
            if rule["kind"] == "constraints":
                # Explicit source constraints override an intrinsic preference.
                limits.update(rule["limits"])
                self.record_page_layout_rule(component, rule)
        self.record_page_paths(component, {f"style.asset.{axis}_dp" for axis in ("width", "height")})
        values = ", ".join(f"{key}: {self.page_number(value)}" for key, value in limits.items())
        lines = [f".constraintSize({{ {values} }})"]
        if len(axes) == 2 and component["style"]["layout"].get("aspect_ratio") is None:
            lines.append(f".aspectRatio({self.page_number(sizes['width'] / sizes['height'])})")
        return lines

    def page_snapshot_stretched_axis(self, component: dict[str, Any], axis: str) -> bool:
        if self.page_snapshot_has_explicit_axis_size(component, axis):
            return False
        parent = self.android_page_by_id.get(component.get("parent_id"))
        if not parent:
            return False
        rule = self.page_snapshot_axis_layout_rule(component, axis)
        if rule:
            parent_rule = self.page_snapshot_axis_layout_rule(parent, axis)
            return bool(
                rule.get("mode") == "fill_parent" and rule.get("fraction") == 1
                and parent_rule and parent_rule.get("kind") == "intrinsic_size"
                and (parent.get("type"), axis) in {("Row", "height"), ("Column", "width")}
            )
        return bool(
            (parent.get("source") or {}).get("custom_component")
            and parent.get("children_ids") == [component["id"]]
            and self.page_snapshot_stretched_axis(parent, axis)
        )

    def record_page_paths(self, component: dict[str, Any], paths: set[str]) -> None:
        if not hasattr(self, "android_page_applied_component_paths"):
            self.android_page_applied_component_paths = defaultdict(set)
        self.android_page_applied_component_paths[component["id"]].update(paths)

    def record_page_layout_rule(self, component: dict[str, Any], rule: dict[str, Any]) -> None:
        if isinstance(rule.get("source_modifier_name"), str):
            self.record_page_paths(component, {f"source.modifiers.{rule['source_modifier_name'].lower()}"})
        modifiers = (component.get("source") or {}).get("modifiers") or []
        index = rule.get("source_modifier_index")
        if type(index) is int and 0 <= index < len(modifiers):
            name = modifiers[index].get("name")
            if isinstance(name, str):
                self.record_page_paths(component, {f"source.modifiers.{name.lower()}"})

    def page_snapshot_minimum_constraint_line(
        self,
        component: dict[str, Any],
        bounds: dict[str, float],
    ) -> str | None:
        if component.get("type") not in BUTTON_CONTAINER_COMPONENTS:
            return None
        if self.page_snapshot_has_explicit_axis_size(component, "height"):
            return None
        if component.get('type') == 'IconButton' and not self.page_snapshot_has_explicit_axis_size(component, 'width'):
            padding = component['style']['layout'].get('padding_dp') or {}
            return f".constraintSize({{ minWidth: {self.page_layout_length(48 + padding.get('left', 0) + padding.get('right', 0))}, minHeight: {self.page_layout_length(48)} }})"
        return f".constraintSize({{ minHeight: {self.page_layout_length(48)} }})"

    def page_snapshot_flow_shrink_line(
        self,
        component: dict[str, Any],
        parent_type: str | None,
    ) -> str | None:
        if parent_type not in {"Column", "Row"}:
            return None
        if self.page_snapshot_source_layout_weight(component) is not None:
            return None
        return ".flexShrink(0)"

    def page_snapshot_root_fills_viewport(
        self,
        component: dict[str, Any],
        parent: dict[str, Any] | None,
        axis: str,
    ) -> bool:
        if parent is not None or component.get("parent_id") is not None:
            return False
        return not self.page_snapshot_has_explicit_axis_size(component, axis)

    def page_snapshot_fills_parent_inner_axis(
        self,
        component: dict[str, Any],
        parent: dict[str, Any] | None,
        axis: str,
    ) -> bool:
        if axis not in {"width", "height"} or not isinstance(parent, dict):
            return False
        if self.page_snapshot_has_explicit_axis_size(component, axis):
            return False
        parent_source = parent.get("source")
        custom_parent = (
            isinstance(parent_source, dict)
            and (parent_source.get("custom_component") is True or parent.get("type") in {"content", "toolbar"})
            and parent.get("children_ids") == [component.get("id")]
        )
        if not custom_parent:
            return False
        parent_rule = self.page_snapshot_axis_layout_rule(parent, axis)
        if parent_rule:
            ancestor = self.android_page_by_id.get(parent.get("parent_id"))
            ancestor_rule = self.page_snapshot_axis_layout_rule(ancestor, axis) if ancestor else None
            if ancestor_rule and ancestor_rule.get("kind") == "intrinsic_size":
                return False
            return parent_rule.get("mode") in {"fill_parent", "match_parent"}
        if self.page_snapshot_has_explicit_axis_size(parent, axis):
            return True
        ancestor = self.android_page_by_id.get(parent.get("parent_id"))
        if self.page_snapshot_source_layout_weight(parent) and ancestor:
            if (ancestor.get("type"), axis) in {("Row", "width"), ("Column", "height")}:
                return True
        return self.page_snapshot_fills_parent_inner_axis(parent, ancestor, axis)

    def page_snapshot_bounds(
        self,
        component: dict[str, Any],
        parent_bounds: dict[str, float],
    ) -> tuple[dict[str, float], float, float]:
        if component.get("_runtime_bounds_applied") is True:
            bounds = dict(component["bounds_dp"])
        else:
            bounds = dict(
                component.get("source_layout_bounds_dp")
                or component.get("visual_bounds_dp")
                or component["bounds_dp"]
            )
        if (
            component["type"] in {"BasicTextField", "TextField", "OutlinedTextField"}
            and component.get("visual_bounds_dp") is not None
        ):
            raster_pixel = float(PAGE_DRIVEN_RASTER_PIXEL_VP)
            bounds["y"] -= raster_pixel
            bounds["width"] = max(raster_pixel, bounds["width"] - raster_pixel)
            bounds["height"] = max(raster_pixel, bounds["height"] - raster_pixel)
        return bounds, bounds["x"] - parent_bounds["x"], bounds["y"] - parent_bounds["y"]

    @staticmethod
    def page_snapshot_instance_suffix(semantic_key: str | None) -> str:
        if not isinstance(semantic_key, str):
            return ""
        match = re.search(r"(__[0-9]+|__instance_[A-Za-z0-9._:@#-]+)$", semantic_key)
        return match.group(1) if match is not None else ""

    def source_call_is_descendant(self, call_id: str, ancestor_call_id: str) -> bool:
        current = self.selected_calls_by_id.get(call_id)
        visited: set[str] = set()
        while isinstance(current, dict):
            parent_id = current.get("parent_call_id")
            if parent_id == ancestor_call_id:
                return True
            if not isinstance(parent_id, str) or parent_id in visited:
                return False
            visited.add(parent_id)
            current = self.selected_calls_by_id.get(parent_id)
        return False

    def page_snapshot_elided_image_calls(
        self,
        component: dict[str, Any],
        parent_call: dict[str, Any],
    ) -> list[dict[str, Any]]:
        suffix = self.page_snapshot_instance_suffix(component.get("semantic_key"))
        result: list[dict[str, Any]] = []
        for entry in self.android_page_runtime_elided:
            if self.page_snapshot_instance_suffix(entry["source_semantic_key"]) != suffix:
                continue
            call = self.selected_calls_by_id.get(entry["source_call_id"])
            if (
                isinstance(call, dict)
                and call.get("component") in {"Image", "Icon"}
                and self.source_call_is_descendant(call["call_id"], parent_call["call_id"])
            ):
                result.append(call)
        return sorted(result, key=lambda item: (item.get("line", 0), item["call_id"]))

    @staticmethod
    def literal_padding_edges(call: dict[str, Any]) -> dict[str, float]:
        result = {"left": 0.0, "top": 0.0, "right": 0.0, "bottom": 0.0}

        def literal_dimension(expression: str) -> float | None:
            value = dimension_value(expression.strip())
            if value is None or re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", value) is None:
                return None
            return float(value)

        for modifier in call.get("ordered_modifier_chain", []):
            if not isinstance(modifier, dict) or modifier.get("name") != "padding":
                continue
            positional, named = named_arguments(str(modifier.get("arguments", "")))
            if len(positional) == 1 and not named:
                value = literal_dimension(positional[0])
                if value is not None:
                    for edge in result:
                        result[edge] += value
                continue
            if positional or set(named) - {"all", "horizontal", "vertical", "start", "end", "top", "bottom"}:
                continue
            values: dict[str, float] = {}
            for name, expression in named.items():
                value = literal_dimension(expression)
                if value is not None:
                    values[name] = value
            if "all" in values:
                for edge in result:
                    result[edge] += values["all"]
                continue
            if "horizontal" in values:
                result["left"] += values["horizontal"]
                result["right"] += values["horizontal"]
            if "vertical" in values:
                result["top"] += values["vertical"]
                result["bottom"] += values["vertical"]
            for source, target in (("start", "left"), ("end", "right"), ("top", "top"), ("bottom", "bottom")):
                if source in values:
                    result[target] += values[source]
        return result

    def page_snapshot_elided_surface_descendants(
        self,
        surface_call: dict[str, Any],
        semantic_key: str,
    ) -> list[dict[str, Any]]:
        suffix = self.page_snapshot_instance_suffix(semantic_key)
        descendants: list[dict[str, Any]] = []
        for component in self.android_page_input["components"]:
            if self.page_snapshot_instance_suffix(component.get("semantic_key")) != suffix:
                continue
            if len(component["call_ids"]) != 1:
                continue
            if self.source_call_is_descendant(component["call_ids"][0], surface_call["call_id"]):
                descendants.append(component)
        return descendants

    def page_snapshot_common_padding(
        self,
        surface_call: dict[str, Any],
        descendants: list[dict[str, Any]],
    ) -> dict[str, float]:
        common: set[str] | None = None
        for component in descendants:
            call_id = component["call_ids"][0]
            ancestors: set[str] = set()
            current = self.selected_calls_by_id.get(call_id)
            while isinstance(current, dict):
                current_id = current["call_id"]
                if current_id == surface_call["call_id"]:
                    break
                ancestors.add(current_id)
                parent_id = current.get("parent_call_id")
                current = self.selected_calls_by_id.get(parent_id) if isinstance(parent_id, str) else None
            common = ancestors if common is None else common & ancestors
        result = {"left": 0.0, "top": 0.0, "right": 0.0, "bottom": 0.0}
        for call_id in common or set():
            call = self.selected_calls_by_id.get(call_id)
            if not isinstance(call, dict):
                continue
            padding = self.literal_padding_edges(call)
            for edge in result:
                result[edge] += padding[edge]
        return result

    def page_snapshot_effective_bounds(self, component: dict[str, Any]) -> dict[str, float]:
        bounds = dict(component.get("visual_bounds_dp") or component["bounds_dp"])
        if component["type"] in {"Text", "BasicText", "ClickableText"}:
            bounds["y"] -= float(PAGE_DRIVEN_BASELINE_VP)
        return bounds

    def page_snapshot_source_draw_order(self, component: dict[str, Any]) -> int | None:
        context = component.get("component_context")
        if not isinstance(context, dict):
            return None
        source_ids = [
            source_id
            for source_id in (
                context.get("source_component_id"),
                context.get("business_component_id"),
            )
            if isinstance(source_id, str)
        ]
        for source_id in source_ids:
            current = self.android_source_tree_by_id.get(source_id)
            while isinstance(current, dict):
                relationship = self.android_source_layout_by_subject.get(current["id"])
                if (
                    isinstance(relationship, dict)
                    and relationship.get("composition") == "overlay"
                    and not relationship.get("unresolved")
                ):
                    return int(relationship["draw_order"])
                parent_id = current.get("parent_id")
                current = (
                    self.android_source_tree_by_id.get(parent_id)
                    if isinstance(parent_id, str)
                    else None
                )
        return None

    def page_snapshot_source_radius(
        self,
        call: dict[str, Any] | None,
        bounds: dict[str, float],
    ) -> float | None:
        if call is None:
            return None
        expression: str | None = None
        semantic = call.get("semantic_arguments")
        if isinstance(semantic, dict):
            surface_argument = next(
                (
                    semantic.get(name)
                    for name in ("shape", "corners", "cornerRadius")
                    if isinstance(semantic.get(name), dict)
                    and isinstance(semantic[name].get("expression"), str)
                ),
                None,
            )
            if isinstance(surface_argument, dict):
                expression = surface_argument["expression"]
        if expression is None:
            definition_key = (call["source"], call["composable"])
            custom = call.get("custom_composable")
            custom_definitions = custom.get("definitions") if isinstance(custom, dict) else None
            if (
                isinstance(custom_definitions, list)
                and len(custom_definitions) == 1
                and isinstance(custom_definitions[0], dict)
            ):
                definition_key = (
                    custom_definitions[0].get("source"),
                    custom_definitions[0].get("composable"),
                )
            definition = self.definitions.get(definition_key, {})
            expression = next(
                (
                    parameter.get("default")
                    for parameter in definition.get("parameters", [])
                    if isinstance(parameter, dict)
                    and parameter.get("name") in {"shape", "corners", "cornerRadius"}
                    and isinstance(parameter.get("default"), str)
                ),
                None,
            )
        if expression is None:
            return None
        radius = self.dimension_expression(expression, {})
        if radius is None:
            radius = self.rounded_corner_radius_expression(expression, {})
        if radius is None or re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", radius) is None:
            return None
        value = min(float(radius), bounds["width"] / 2, bounds["height"] / 2)
        nearest_integer = round(value)
        return float(nearest_integer) if abs(value - nearest_integer) <= 0.25 else value

    def page_snapshot_elided_surfaces(
        self,
        content_bounds: dict[str, float],
    ) -> list[tuple[str, list[str]]]:
        surfaces: list[tuple[str, list[str]]] = []
        surface_components = {"Card", "ElevatedCard", "OutlinedCard", "Surface"}
        for entry in self.android_page_runtime_elided:
            call = self.selected_calls_by_id.get(entry["source_call_id"])
            if not isinstance(call, dict) or call.get("component") not in surface_components:
                continue
            descendants = self.page_snapshot_elided_surface_descendants(
                call, entry["source_semantic_key"]
            )
            if not descendants:
                continue
            bounds = [self.page_snapshot_effective_bounds(component) for component in descendants]
            padding = self.page_snapshot_common_padding(call, descendants)
            left = min(bound["x"] for bound in bounds) - padding["left"]
            top = min(bound["y"] for bound in bounds) - padding["top"]
            right = max(bound["x"] + bound["width"] for bound in bounds) + padding["right"]
            bottom = max(bound["y"] + bound["height"] for bound in bounds) + padding["bottom"]
            style_lines = self.page_snapshot_source_lines(call)
            if not style_lines:
                continue
            surface_lines = [
                "      Stack()",
                f"        .position({{ x: {self.page_number(left - content_bounds['x'])}, y: {self.page_number(top - content_bounds['y'])} }})",
                f"        .width({self.page_number(right - left)})",
                f"        .height({self.page_number(bottom - top)})",
                f"        .id({arkts_string(entry['source_semantic_key'])})",
            ]
            surface_lines.extend(f"        {line}" for line in style_lines)
            descendant_roots: list[dict[str, Any]] = []
            for descendant in descendants:
                root = descendant
                while isinstance(root.get("parent_id"), str):
                    root = self.android_page_by_id[root["parent_id"]]
                descendant_roots.append(root)
            anchor = min(
                descendant_roots,
                key=lambda component: (
                    component["sibling_index"],
                    component["bounds_dp"]["y"],
                    component["bounds_dp"]["x"],
                ),
            )
            surfaces.append((anchor["id"], surface_lines))
        return surfaces

    def page_snapshot_flow_container(self, component: dict[str, Any]) -> str | None:
        container = self.page_snapshot_layout_container(component)
        return container if container in {"Column", "Row"} else None

    def page_snapshot_layout_container(self, component: dict[str, Any]) -> str | None:
        if self.android_page_layout_mode != "source-tree":
            return None
        component_type = component["type"]
        if component_type in PAGE_SNAPSHOT_FLOW_COMPONENTS:
            return "Column" if component_type in PAGE_SNAPSHOT_COLUMN_COMPONENTS else "Row"
        if component_type == "ConstraintLayout":
            return "RelativeContainer"
        return None

    def page_snapshot_constraint_alignment_lines(
        self,
        component: dict[str, Any],
    ) -> list[str]:
        try:
            return self.page_snapshot_supported_constraint_lines(component)
        except ArkUIPageError as error:
            # The document graph was validated on input. A missing mapping here
            # is a local capability gap, not permission to infer coordinates.
            self.add_page_json_unresolved(component, "source.layout_relationships", str(error))
            return []

    def page_snapshot_supported_constraint_lines(
        self,
        component: dict[str, Any],
    ) -> list[str]:
        if self.android_page_layout_mode != "source-tree":
            return []
        relationship = self.android_source_layout_by_subject.get(component["id"])
        if not isinstance(relationship, dict):
            raise ArkUIPageError(
                f"ConstraintLayout child has no source relationship: {component['id']}"
            )
        if relationship.get("unresolved"):
            raise ArkUIPageError(
                f"ConstraintLayout relationship is unresolved: {component['id']}"
            )
        rules: list[str] = []
        emitted_keys: set[str] = set()
        horizontal_target = {
            "start": "HorizontalAlign.Start",
            "end": "HorizontalAlign.End",
        }
        vertical_target = {
            "top": "VerticalAlign.Top",
            "bottom": "VerticalAlign.Bottom",
        }
        for constraint in relationship.get("active_constraints") or []:
            margin = constraint.get("margin_dp")
            if margin not in {None, 0, 0.0}:
                raise ArkUIPageError(
                    "ConstraintLayout margins are not yet representable without changing "
                    f"layout semantics: {component['id']}"
                )
            kind = constraint.get("kind")
            subject_anchor = constraint.get("subject_anchor")
            target_anchor = constraint.get("target_anchor")
            parent = self.android_page_by_id.get(component.get("parent_id"))
            axis = "height" if subject_anchor == "top" else "width"
            parent_rule = self.page_snapshot_axis_layout_rule(parent, axis) if parent else None
            other_axis_anchors = {"bottom", "center"} if axis == "height" else {"end", "middle"}
            if (
                kind == "link_to"
                and subject_anchor in {"top", "start"}
                and subject_anchor == target_anchor
                and constraint.get("target_reference") == "parent"
                and parent_rule and parent_rule.get("mode") == "wrap_content"
                and not any(c.get("subject_anchor") in other_axis_anchors for c in relationship["active_constraints"])
            ):
                # The origin is already zero. Keeping this redundant anchor disables
                # RelativeContainer's native wrap measurement in the same axis.
                continue
            if kind == "center_around":
                if target_anchor in horizontal_target:
                    rule_key = "middle"
                    alignment = horizontal_target[target_anchor]
                elif target_anchor in vertical_target:
                    rule_key = "center"
                    alignment = vertical_target[target_anchor]
                else:
                    raise ArkUIPageError(
                        f"unsupported centerAround anchor: {target_anchor}"
                    )
            elif kind == "link_to":
                if subject_anchor in {"start", "end"} and target_anchor in horizontal_target:
                    rule_key = "left" if subject_anchor == "start" else "right"
                    alignment = horizontal_target[target_anchor]
                elif subject_anchor in {"top", "bottom"} and target_anchor in vertical_target:
                    rule_key = subject_anchor
                    alignment = vertical_target[target_anchor]
                else:
                    raise ArkUIPageError(
                        "unsupported or cross-axis ConstraintLayout link: "
                        f"{component['id']}:{subject_anchor}->{target_anchor}"
                    )
            else:
                raise ArkUIPageError(
                    f"unsupported ConstraintLayout relationship kind: {kind}"
                )
            if rule_key in emitted_keys:
                raise ArkUIPageError(
                    f"duplicate ConstraintLayout rule {rule_key}: {component['id']}"
                )
            target_id = constraint.get("target_id")
            if constraint.get("target_reference") == "parent":
                anchor = "__container__"
            else:
                target = self.android_page_by_id.get(target_id)
                anchor = target.get("semantic_key") if isinstance(target, dict) else None
                if not isinstance(anchor, str) or not anchor:
                    raise ArkUIPageError(
                        f"ConstraintLayout target has no ArkUI id: {target_id}"
                    )
            rules.append(
                f"{rule_key}: {{ anchor: {arkts_string(anchor)}, align: {alignment} }}"
            )
            emitted_keys.add(rule_key)
        if not rules and not relationship.get("active_constraints"):
            raise ArkUIPageError(
                f"ConstraintLayout child has no active constraints: {component['id']}"
            )
        return [f".alignRules({{ {', '.join(rules)} }})"] if rules else []

    def page_snapshot_requires_position(
        self,
        component: dict[str, Any],
        bounds: dict[str, float],
        parent: dict[str, Any] | None,
        parent_container: str | None,
    ) -> bool:
        if self.android_page_layout_mode == "source-tree":
            return False
        return parent_container is not None

    def page_snapshot_explicit_offset_line(
        self,
        component: dict[str, Any],
        parent: dict[str, Any] | None,
    ) -> str | None:
        if self.android_page_layout_mode != "source-tree" or not isinstance(parent, dict):
            return None
        offset_rule = next(
            (
                rule
                for rule in reversed(self.page_snapshot_layout_rules(component))
                if rule.get("kind") == "offset"
            ),
            None,
        )
        if isinstance(offset_rule, dict):
            values: list[str] = []
            for axis in ("x", "y"):
                offset = offset_rule.get(axis)
                if not isinstance(offset, dict):
                    continue
                if offset.get("kind") == "dp":
                    value = float(offset["value"])
                    if abs(value) > 0.001:
                        values.append(f"{axis}: {self.page_number(value)}")
                else:
                    parent_axis = str(offset["axis"])
                    scope = parent
                    while scope and scope['type'] != 'BoxWithConstraints':
                        scope = self.android_page_by_id.get(scope.get('parent_id'))
                    bounded = False
                    if scope:
                        rule = self.page_snapshot_axis_layout_rule(scope, parent_axis) or {}
                        bounded = self.page_snapshot_has_explicit_axis_size(scope, parent_axis)
                        if not bounded and rule.get('mode') == 'fill_parent' and rule.get('fraction') == 1:
                            bounded = True
                            ancestor = self.android_page_by_id.get(scope.get('parent_id'))
                            while ancestor:
                                if self.page_snapshot_has_explicit_axis_size(ancestor, parent_axis):
                                    break
                                scroll_axis = 'vertical' if parent_axis == 'height' else 'horizontal'
                                if ancestor['type'] == ('LazyColumn' if parent_axis == 'height' else 'LazyRow') or any(
                                    r.get('kind') == 'scroll' and r.get('axis') == scroll_axis and r.get('enabled')
                                    for r in self.page_snapshot_layout_rules(ancestor)
                                ):
                                    bounded = False
                                    break
                                ancestor = self.android_page_by_id.get(ancestor.get('parent_id'))
                    if not bounded:
                        self.add_page_json_unresolved(component, 'source.modifiers.offset',
                            'parent max constraint needs a bounded, size-filling BoxWithConstraints scope; wrap size is not max constraint')
                        return None
                    state = self._page_constraint_states.setdefault(scope['id'], {
                        'name': f'pageConstraint{len(self._page_constraint_states)}', 'axes': set()})
                    state['axes'].add(parent_axis)
                    values.append(f"{axis}: this.{state['name']}{parent_axis.title()} * {self.page_number(float(offset['fraction']))}")
            return f".translate({{ {', '.join(values)} }})" if values else None
        source = component.get("source")
        modifiers = source.get("modifiers") if isinstance(source, dict) else None
        if not isinstance(modifiers, list) or not any(
            isinstance(modifier, dict) and modifier.get("name") == "offset"
            for modifier in modifiers
        ):
            return None
        self.add_page_json_unresolved(
            component,
            "source.modifiers.offset",
            "offset requires a normalized layout rule; deriving translation from bbox is forbidden",
        )
        return None

    def add_page_json_unresolved(
        self,
        component: dict[str, Any],
        path: str,
        reason: str,
    ) -> None:
        self.add_unresolved(
            "page_json_missing_fact",
            None,
            reason,
            page_component_id=component["id"],
            semantic_key=component.get("semantic_key"),
            path=path,
        )

    @staticmethod
    def page_snapshot_arrangement_space(component: dict[str, Any]) -> str | None:
        layout = component["style"]["layout"]
        key = (
            "vertical_arrangement"
            if component["type"] in PAGE_SNAPSHOT_COLUMN_COMPONENTS
            else "horizontal_arrangement"
        )
        expression = layout.get(key)
        if not isinstance(expression, str):
            return None
        match = re.fullmatch(
            r"(?:Arrangement\.)?spacedBy\(\s*(?:space\s*=\s*)?(-?[0-9]+(?:\.[0-9]+)?)\.dp\s*(?:,\s*(?:alignment\s*=\s*)?Alignment\.[A-Za-z]+\s*)?\)",
            expression,
        )
        return match.group(1) if match is not None else None

    def page_snapshot_container_alignment_lines(
        self,
        component: dict[str, Any],
    ) -> list[str]:
        component_type = component["type"]
        layout = component["style"]["layout"]
        alignment = layout.get("alignment")
        lines: list[str] = []
        if component_type in PAGE_SNAPSHOT_ROW_COMPONENTS:
            mapped = {
                "Top": "VerticalAlign.Top",
                "CenterVertically": "VerticalAlign.Center",
                "Bottom": "VerticalAlign.Bottom",
            }.get(str(alignment or "Top").removeprefix("Alignment."))
            if mapped is not None:
                lines.append(f".alignItems({mapped})")
            arrangement = layout.get("horizontal_arrangement")
        elif component_type in PAGE_SNAPSHOT_COLUMN_COMPONENTS:
            mapped = {
                "Start": "HorizontalAlign.Start",
                "CenterHorizontally": "HorizontalAlign.Center",
                "End": "HorizontalAlign.End",
            }.get(str(alignment or "Start").removeprefix("Alignment."))
            if mapped is not None:
                lines.append(f".alignItems({mapped})")
            arrangement = layout.get("vertical_arrangement")
        else:
            arrangement = None
        justify = {
            "Arrangement.Start": "FlexAlign.Start",
            "Arrangement.Center": "FlexAlign.Center",
            "Arrangement.End": "FlexAlign.End",
            "Arrangement.Top": "FlexAlign.Start",
            "Arrangement.Bottom": "FlexAlign.End",
            "Arrangement.SpaceBetween": "FlexAlign.SpaceBetween",
            "Arrangement.SpaceAround": "FlexAlign.SpaceAround",
            "Arrangement.SpaceEvenly": "FlexAlign.SpaceEvenly",
        }.get(arrangement)
        if self.page_snapshot_arrangement_space(component) is not None:
            match = re.search(r"Alignment\.(\w+)", str(arrangement))
            justify = {"CenterHorizontally": "FlexAlign.Center", "CenterVertically": "FlexAlign.Center",
                       "Start": "FlexAlign.Start", "Top": "FlexAlign.Start",
                       "End": "FlexAlign.End", "Bottom": "FlexAlign.End"}.get(match.group(1) if match else "Start")
        if justify is not None:
            lines.append(f".justifyContent({justify})")
        if component_type == "CenterAlignedTopAppBar":
            return lines
        if component_type not in {"Box", "BoxWithConstraints"}:
            return lines
        mapped = {
            "Center": "Alignment.Center",
            "CenterStart": "Alignment.Start",
            "CenterEnd": "Alignment.End",
            "TopStart": "Alignment.TopStart",
            "TopCenter": "Alignment.Top",
            "TopEnd": "Alignment.TopEnd",
            "BottomStart": "Alignment.BottomStart",
            "BottomCenter": "Alignment.Bottom",
            "BottomEnd": "Alignment.BottomEnd",
        }.get(str(alignment or "TopStart").removeprefix("Alignment."))
        return [f".alignContent({mapped})", *lines] if mapped is not None else lines

    def page_snapshot_decorated_input_lines(self, component, decoration, parent_bounds, parent_type, indent):
        # BasicTextField owns editing; its decoration owns padding, chrome and slots.
        outer = copy.deepcopy(component)
        outer['type'] = 'Box'
        outer['style']['content']['text'] = None
        inner = copy.deepcopy(component)
        inner['id'] += '-editor'
        inner['semantic_key'] += '__editor'
        inner['parent_id'] = decoration['id']
        inner['children_ids'] = []
        inner['style']['layout'] = {key: None for key in inner['style']['layout']}
        inner['style']['surface'] = {key: None for key in inner['style']['surface']}
        inner['source'] = {'layoutRules': [{'kind': 'weight', 'value': 1.0, 'fill': True}]}
        row = copy.deepcopy(decoration)
        row['type'] = 'Row'
        row['style']['layout']['alignment'] = 'CenterVertically'
        facts = (decoration.get('source') or {}).get('input_decoration') or {}
        outlined = facts.get('kind') == 'material3-outlined'
        leading, trailing, supporting = [], [], []
        for child_id in row['children_ids']:
            child = self.android_page_by_id[child_id]
            slot = (child.get('source') or {}).get('slot_argument_name')
            if outlined and slot == 'supportingText':
                supporting.append(child_id)
                continue
            (leading if slot == 'leadingIcon' else trailing).append(child_id)
            if slot not in {'leadingIcon', 'trailingIcon'}:
                self.add_page_json_unresolved(child, 'source.slot_argument_name',
                    'input decoration slot retained; floating label/supporting layout is not resolved')
        row['children_ids'] = leading + [inner['id']] + trailing
        outer['children_ids'] = [row['id']]
        updates = {outer['id']: outer, row['id']: row, inner['id']: inner}
        if outlined:
            fill_width = {'kind': 'sizing', 'axes': ['width'], 'mode': 'fill_parent', 'fraction': 1}

            def container(suffix, kind, child_ids, padding=None, min_height=None):
                node = copy.deepcopy(decoration)
                node.update(id=decoration['id'] + '-' + suffix,
                            semantic_key=decoration['semantic_key'] + '__' + suffix,
                            type=kind, children_ids=child_ids, required_facts=[], unresolved=[])
                node['style'] = {group: dict.fromkeys(values) for group, values in node['style'].items()}
                node['style']['layout'].update(padding_dp=padding, alignment='Center' if kind == 'Box' else 'Start')
                rules = [copy.deepcopy(fill_width)]
                if min_height is not None:
                    rules.append({'kind': 'constraints', 'limits': {'minHeight': min_height}})
                node['source'] = {'layoutRules': rules}
                updates[node['id']] = node
                return node

            # Material measures the editor with content padding, but icons without it.
            padding = row['style']['layout'].get('padding_dp') or dict.fromkeys(('left', 'right', 'top', 'bottom'), 0)
            line = container('text_line', 'Box', [inner['id']], min_height=facts['text_min_height_dp'])
            padded = container('text_padding', 'Box', [line['id']],
                               dict(left=0, right=0, top=padding['top'], bottom=padding['bottom']))
            padded['source']['layoutRules'] = [{'kind': 'weight', 'value': 1.0, 'fill': True}]
            padded['parent_id'], line['parent_id'], inner['parent_id'] = row['id'], padded['id'], line['id']
            inner['source']['layoutRules'] = [copy.deepcopy(fill_width)]
            row['style']['layout']['padding_dp'] = {**padding, 'top': 0, 'bottom': 0}
            row['source'].setdefault('layoutRules', []).append(copy.deepcopy(fill_width))
            row['children_ids'] = leading + [padded['id']] + trailing
            if facts.get('supporting_text') is True or supporting:
                support = container('supporting', 'Column', supporting,
                                    facts['supporting_padding_dp'], facts['supporting_min_height_dp'])
                support['parent_id'] = outer['id']
                for child_id in supporting:
                    updates[child_id] = {**self.android_page_by_id[child_id], 'parent_id': support['id']}
                outer['type'] = 'Column'
                outer['children_ids'].append(support['id'])
            self.record_page_paths(decoration, {'source.input_decoration'})
        original = {node_id: self.android_page_by_id.get(node_id) for node_id in updates}
        self.android_page_by_id.update(updates)
        try:
            return self.page_snapshot_component_lines(outer, parent_bounds, parent_type, indent)
        finally:
            for node_id, node in original.items():
                if node is None:
                    self.android_page_by_id.pop(node_id, None)
                else:
                    self.android_page_by_id[node_id] = node

    def page_snapshot_component_lines(
        self,
        component: dict[str, Any],
        parent_bounds: dict[str, float],
        parent_type: str | None,
        indent: int,
    ) -> list[str]:
        prefix = " " * indent
        component_type = component["type"]
        children = [self.android_page_by_id[child_id] for child_id in component["children_ids"]]
        native_containers = NATIVE_CONTAINERS
        native_leaves = NATIVE_LEAVES
        project_wrapper = (component.get("source") or {}).get("custom_component") is True
        if project_wrapper and self.android_page_layout_mode == 'source-tree':
            lines = []
            for child in children:
                lines.extend(self.page_snapshot_component_lines(child, parent_bounds, parent_type, indent))
            self.android_page_processed_component_ids.add(component['id'])
            applied = self.android_page_applied_component_paths[component['id']]
            applied.update({
                'structure.type', 'structure.parent_id', 'structure.children_ids', 'structure.sibling_index'})
            for child in children:
                consumed = self.android_page_applied_component_paths.get(child['id'], set())
                for section, values in component['style'].items():
                    for field, value in values.items():
                        path = f'style.{section}.{field}'
                        if value is not None and path in consumed and child['style'].get(section, {}).get(field) == value:
                            applied.add(path)
                for rule in self.page_snapshot_layout_rules(component):
                    if rule in self.page_snapshot_layout_rules(child):
                        self.record_page_layout_rule(component, rule)
            return lines
        if component_type not in native_containers | native_leaves | BUTTON_CONTAINER_COMPONENTS and not project_wrapper:
            self.add_page_json_unresolved(component, "structure.type", f"unsupported component {component_type}; implicit Stack fallback is disabled")
            return []
        source_layout_weight = self.page_snapshot_source_layout_weight(component)
        bounds, relative_x, relative_y = self.page_snapshot_bounds(component, parent_bounds)
        is_text = component_type in {"Text", "BasicText", "ClickableText"}
        is_text_field = component_type in {"BasicTextField", "TextField", "OutlinedTextField"}
        if (is_text or is_text_field) and not isinstance(component["style"]["content"].get("text"), str):
            self.add_page_json_unresolved(component, "style.content.text", "dynamic content is unresolved; native control and static styles are retained without invented text")
        decoration = next((child for child in children if child['type'] == 'DecorationBox'), None)
        if is_text_field and decoration is not None:
            return self.page_snapshot_decorated_input_lines(component, decoration, parent_bounds, parent_type, indent)
        input_style = component['style'].get('input') or {}
        control = component['style'].get('control') or {}
        size_updates: list[str] = []
        multiline_input = is_text_field and input_style.get('single_line') is False
        is_button = component_type in BUTTON_CONTAINER_COMPONENTS
        intrinsic_image_lines = self.page_snapshot_intrinsic_image_lines(component)
        page_tint_baked = False
        emitted_phase_paths: set[str] = set()
        scroll_rule = next((r for r in self.page_snapshot_layout_rules(component) if r["kind"] == "scroll"), None)
        scroll_axis = (scroll_rule or {}).get("axis") if (scroll_rule or {}).get("enabled") else None
        if component_type in {"LazyColumn", "LazyRow"}:
            scroll_axis = "vertical" if component_type == "LazyColumn" else "horizontal"

        if is_text:
            lines = [f"{prefix}Text({arkts_string(self.page_snapshot_text_value(component))})"]
            emitted_phase_paths.add("style.content.text")
        elif is_text_field:
            options = [f"text: {arkts_string(self.page_snapshot_text_value(component))}"]
            emitted_phase_paths.add("style.content.text")
            placeholder = component["style"]["content"].get("placeholder")
            if isinstance(placeholder, str):
                options.append(f"placeholder: {arkts_string(placeholder)}")
                emitted_phase_paths.add("style.content.placeholder")
            input_component = 'TextArea' if multiline_input else 'TextInput'
            lines = [f"{prefix}{input_component}({{ {', '.join(options)} }})"]
            if component_type == 'BasicTextField':
                lines.extend([f'{prefix}  .padding(0)', f"{prefix}  .backgroundColor('#00000000')",
                              f'{prefix}  .borderRadius(0)'])
            if input_style.get('single_line') is not None:
                emitted_phase_paths.add('style.input.single_line')
        elif is_button:
            # A runtime accessibility "button" proves click semantics and bounds,
            # not Material/ArkUI button chrome.  The page snapshot already owns
            # the captured surface, border, radius, and shadow, so render a neutral
            # visual container and apply those facts without ArkUI's blue default.
            lines = [f"{prefix}Stack() {{"]
            if len(children) > 1:
                lines.append(f"{prefix}  Row() {{")
                for child in children:
                    lines.extend(
                        self.page_snapshot_component_lines(
                            child, bounds, "Row", indent + 4
                        )
                    )
                lines.extend((f"{prefix}  }}", f"{prefix}    .alignItems(VerticalAlign.Center)"))
            else:
                for child in children:
                    lines.extend(
                        self.page_snapshot_component_lines(
                            child, bounds, component_type, indent + 2
                        )
                    )
            lines.append(f"{prefix}}}")
        elif component_type in {"Image", "Icon", "AsyncImage"}:
            page_resource = component["style"]["asset"].get("resource")
            page_tint = component["style"]["asset"].get("tint")
            media = None
            if isinstance(page_resource, str) and isinstance(page_tint, str):
                tinted_resource = self.tinted_vector_resources.get(
                    (page_resource, page_tint)
                )
                if tinted_resource is not None:
                    media = f"$r('app.media.{tinted_resource}')"
                    page_tint_baked = True
            if (
                media is None
                and isinstance(page_resource, str)
                and RESOURCE_NAME_PATTERN.fullmatch(page_resource) is not None
                and f"media:{page_resource}" in self.resource_names
            ):
                media = f"$r('app.media.{page_resource}')"
            if media is None:
                if component_type == "AsyncImage" and isinstance(page_resource, str):
                    try:
                        uri = urlsplit(page_resource)
                        if uri.scheme in {"http", "https"} and uri.hostname and not uri.username and not uri.password:
                            media = arkts_string(page_resource)
                    except ValueError:
                        pass
            if media is None:
                self.add_page_json_unresolved(
                    component,
                    "style.asset.resource",
                    "page JSON image has no target-resolvable asset; source fallback is disabled",
                )
                return []
            lines = [f"{prefix}Image({media})"]
            emitted_phase_paths.add("style.asset.resource")
        elif component_type in {'Checkbox', 'Switch', 'RadioButton'}:
            field = 'selected' if component_type == 'RadioButton' else 'checked'
            checked = component['style']['state'].get(field)
            if not isinstance(checked, bool):
                self.add_page_json_unresolved(component, 'style.state.' + field, 'selection state is required')
                return []
            boolean = str(checked).lower()
            if component_type == 'Checkbox':
                lines = [f'{prefix}Checkbox()', f'{prefix}  .select({boolean})',
                         f'{prefix}  .shape(CheckBoxShape.ROUNDED_SQUARE)']
            elif component_type == 'Switch':
                lines = [f'{prefix}Toggle({{ type: ToggleType.Switch, isOn: {boolean} }})']
            else:
                key = arkts_string(component['id'])
                lines = [f'{prefix}Radio({{ value: {key}, group: {key} }})', f'{prefix}  .checked({boolean})']
            lines.extend([f'{prefix}  .margin(0)', f'{prefix}  .padding(0)'])
            emitted_phase_paths.add('style.state.' + field)
        elif component_type == 'Slider':
            value, low, high, steps = (control.get(k) for k in ('value', 'minimum', 'maximum', 'steps'))
            if any(v is None for v in (value, low, high, steps)) or high <= low or steps <= 0:
                self.add_page_json_unresolved(component, 'style.control.steps',
                    'native Slider requires explicit discrete steps; continuous Compose slider must not become a stepped slider')
                return []
            step = (high - low) / (steps + 1)
            if step < 0.01:
                self.add_page_json_unresolved(component, 'style.control.steps', 'native Slider minimum step is 0.01')
                return []
            lines = [f'{prefix}Slider({{ value: {self.page_number(max(low, min(high, value)))}, min: {self.page_number(low)}, max: {self.page_number(high)}, step: {self.page_number(step)} }})']
            emitted_phase_paths.update('style.control.' + k for k in ('value', 'minimum', 'maximum', 'steps'))
        elif component_type in {'LinearProgressIndicator', 'CircularProgressIndicator'}:
            value = control.get('value')
            if value is None:
                self.add_page_json_unresolved(component, 'style.control.value', 'indeterminate animation requires a separate renderer')
                return []
            if control.get('minimum') != 0 or control.get('maximum') != 1:
                self.add_page_json_unresolved(component, 'style.control', 'Compose progress requires a normalized 0..1 range')
                return []
            if control.get('inactive_color') and component['style']['surface'].get('background') is not None:
                self.add_page_json_unresolved(component, 'style.surface.background',
                    'trackColor and an outer modifier background require separate draw layers')
                return []
            shape = 'Linear' if component_type == 'LinearProgressIndicator' else 'Ring'
            lines = [f'{prefix}Progress({{ value: {self.page_number(max(0, min(1, value)))}, total: 1, type: ProgressType.{shape} }})']
            for field, method in [('active_color', 'color'), ('inactive_color', 'backgroundColor')]:
                if control.get(field):
                    lines.append(f'{prefix}  .{method}({arkts_string(control[field])})')
                    emitted_phase_paths.add('style.control.' + field)
            if control.get('stroke_width_dp') is not None:
                lines.append(f"{prefix}  .style({{ strokeWidth: {self.page_number(control['stroke_width_dp'])} }})")
                emitted_phase_paths.add('style.control.stroke_width_dp')
            emitted_phase_paths.update('style.control.' + k for k in ('value', 'minimum', 'maximum'))
        elif component_type in {'Divider', 'HorizontalDivider', 'VerticalDivider'}:
            lines = [f'{prefix}Divider()', f"{prefix}  .vertical({str(component_type == 'VerticalDivider').lower()})"]
            if control.get('stroke_width_dp') is not None:
                lines.append(f"{prefix}  .strokeWidth({self.page_number(control['stroke_width_dp'])})")
                emitted_phase_paths.add('style.control.stroke_width_dp')
            if control.get('active_color'):
                lines.append(f"{prefix}  .color({arkts_string(control['active_color'])})")
                emitted_phase_paths.add('style.control.active_color')
        elif component_type == "ProgressRing":
            custom_draw = component.get("custom_draw")
            if isinstance(custom_draw, dict):
                progress_value = self.page_number(float(custom_draw["value"]))
                progress_total = self.page_number(float(custom_draw["total"]))
            else:
                value_text = component["style"]["content"].get("text")
                match = re.fullmatch(r"(100|[0-9]{1,2})%", str(value_text or ""))
                if match is None:
                    return []
                progress_value = str(int(match.group(1)))
                progress_total = "100"
            lines = [
                f"{prefix}Progress({{ value: {progress_value}, total: {progress_total}, type: ProgressType.Ring }})"
            ]
        elif component_type == "Spacer":
            lines = [f"{prefix}Blank()"] if parent_type in {"Row", "Column", "Flex"} else [f"{prefix}Stack() {{", f"{prefix}}}"]
        elif component_type in {'TopAppBar', 'CenterAlignedTopAppBar', 'Scaffold'}:
            if component_type == 'Scaffold':
                self._page_scaffold_states[component['id']] = f'scaffold{len(self._page_scaffold_states)}'
            is_appbar = component_type != 'Scaffold'
            lines = [f"{prefix}{'RelativeContainer' if is_appbar else 'Stack'}() {{"]
            for child in children:
                child_lines = self.page_snapshot_component_lines(child, bounds, 'Stack', indent + 2)
                slot = (child.get('source') or {}).get('slot_argument_name')
                alignment = ({'title': 'Center' if component_type == 'CenterAlignedTopAppBar' else 'Start',
                              'navigationIcon': 'Start', 'actions': 'End'}
                             if component_type != 'Scaffold' else
                             {'topBar': 'Top', 'bottomBar': 'Bottom', 'content': 'TopStart'})
                if child_lines and slot in alignment:
                    if is_appbar:
                        edge = {'navigationIcon': 'left', 'actions': 'right', 'title': 'middle'}[slot]
                        align = {'left': 'Start', 'right': 'End', 'middle': 'Center'}[edge]
                        child_lines.append(f"{prefix}    .alignRules({{ {edge}: {{ anchor: '__container__', align: HorizontalAlign.{align} }}, center: {{ anchor: '__container__', align: VerticalAlign.Center }} }})")
                    else:
                        child_lines.append(f'{prefix}    .align(Alignment.{alignment[slot]})')
                    if component_type == 'Scaffold' and slot in {'topBar', 'bottomBar'}:
                        state_name = self._page_scaffold_states[component['id']] + slot.title()
                        child_lines.append(f'{prefix}    .onAreaChange((_old, area) => {{ this.{state_name} = Number(area.height) }})')
                        child_lines.append(f'{prefix}    .zIndex(1)')
                elif child_lines:
                    self.add_page_json_unresolved(child, 'source.slot_argument_name',
                                                  'native container child requires an explicit supported slot')
                lines.extend(child_lines)
            lines.append(f'{prefix}}}')
            if is_appbar:
                if not self.page_snapshot_has_explicit_axis_size(component, 'height'):
                    lines.append(f'{prefix}  .height({self.page_layout_length(64)})')
                lines.append(f'{prefix}  .padding({{ left: {self.page_layout_length(4)}, right: {self.page_layout_length(4)} }})')
            else:
                lines.append(f'{prefix}  .alignContent(Alignment.TopStart)')
        elif children or component_type in native_containers:
            layout_container = self.page_snapshot_layout_container(component)
            if project_wrapper and self.page_snapshot_stretched_axis(component, "height"):
                layout_container = "Row"
            elif project_wrapper and self.page_snapshot_stretched_axis(component, "width"):
                layout_container = "Column"
            rendered_container = layout_container or "Stack"
            space = (
                self.page_snapshot_arrangement_space(component)
                if rendered_container in {"Column", "Row"}
                else None
            )
            constructor = (
                f"{rendered_container}({{ space: {self.page_layout_length(float(space))} }})"
                if space is not None
                else f"{rendered_container}()"
            )
            container_prefix = prefix + "  " if scroll_axis else prefix
            lines = [f"{prefix}Scroll() {{"] if scroll_axis else []
            lines.append(f"{container_prefix}{constructor} {{")
            for child in children:
                if component_type in {'Box', 'BoxWithConstraints'} and any(
                    rule.get('mode') == 'match_parent' for rule in self.page_snapshot_layout_rules(child)
                ):
                    name = f'pageMatchParent{len(self._page_match_parent_sizes)}'
                    self._page_match_parent_sizes[child['id']] = name
                    child_lines = self.page_snapshot_component_lines(child, bounds, 'Stack', 4)
                    self._page_match_parent_builders.append([
                        f'  @State private {name}Width: Length = 0',
                        f'  @State private {name}Height: Length = 0',
                        '  @Builder', f'  private {name}() {{', *child_lines, '  }', '',
                    ])
                    size_updates.extend([f'this.{name}Width = current.width ?? this.{name}Width',
                                         f'this.{name}Height = current.height ?? this.{name}Height'])
                    continue
                lines.extend(
                    self.page_snapshot_component_lines(
                        child, bounds, rendered_container, indent + (4 if scroll_axis else 2)
                    )
                )
            lines.append(f"{container_prefix}}}")
            for child in children:
                name = self._page_match_parent_sizes.get(child['id'])
                if name:
                    lines.append(f'{container_prefix}  .overlay(this.{name}(), {{ align: Alignment.TopStart }})')
            if scroll_axis:
                lines.extend(f"{container_prefix}  {line}" for line in self.page_snapshot_container_alignment_lines(component))
                lines.append(f"{container_prefix}  .{'width' if scroll_axis == 'vertical' else 'height'}('100%')")
                lines.extend([f"{prefix}}}", f"{prefix}  .scrollable(ScrollDirection.{scroll_axis.title()})", f"{prefix}  .scrollBar(BarState.Off)"])
                lines.append(f'{prefix}  .align(Alignment.TopStart)')
                if scroll_rule:
                    self.record_page_layout_rule(component, scroll_rule)
        else:
            return []

        is_flow_child = (
            self.android_page_layout_mode == "source-tree"
            and parent_type in {"Column", "Row"}
        )
        parent_component = self.android_page_by_id.get(component.get("parent_id", ""))
        structural_parent = parent_component
        if self.android_page_layout_mode == 'source-tree':
            while parent_component and (parent_component.get('source') or {}).get('custom_component'):
                parent_component = self.android_page_by_id.get(parent_component.get('parent_id'))
        centered_button_child = (
            parent_type in BUTTON_CONTAINER_COMPONENTS
            and isinstance(parent_component, dict)
            and parent_component.get("children_ids") == [component["id"]]
        )
        requires_position = self.page_snapshot_requires_position(
            component, bounds, parent_component, parent_type
        )
        if (
            is_text
            and parent_type not in BUTTON_CONTAINER_COMPONENTS
            and not is_flow_child
            and requires_position
        ):
            relative_y -= float(PAGE_DRIVEN_BASELINE_VP)
        if centered_button_child:
            lines.append(f"{prefix}  .align(Alignment.Center)")
        elif parent_type == "RelativeContainer":
            for alignment_line in self.page_snapshot_constraint_alignment_lines(component):
                lines.append(f"{prefix}  {alignment_line}")
            for rule in self.page_snapshot_layout_rules(component):
                if rule["kind"] == "constraint_reference":
                    self.record_page_layout_rule(component, rule)
        elif requires_position:
            lines.append(
                f"{prefix}  .position({{ x: {self.page_number(relative_x)}, y: {self.page_number(relative_y)} }})"
            )
        if self.android_page_layout_mode == "source-tree":
            resolved_translation = self.page_snapshot_explicit_offset_line(
                component, parent_component
            )
            if resolved_translation is not None:
                lines.append(f"{prefix}  {resolved_translation}")
                for rule in self.page_snapshot_layout_rules(component):
                    if rule["kind"] == "offset":
                        self.record_page_layout_rule(component, rule)
        source_draw_order = self.page_snapshot_source_draw_order(component)
        parent = parent_component
        parent_draw_order = (
            self.page_snapshot_source_draw_order(parent)
            if isinstance(parent, dict)
            else None
        )
        if source_draw_order is not None and source_draw_order != parent_draw_order:
            lines.append(f"{prefix}  .zIndex({source_draw_order})")
        if source_layout_weight is not None:
            lines.append(f"{prefix}  {source_layout_weight}")
        for rule in self.page_snapshot_layout_rules(component):
            if rule["kind"] == "weight":
                if source_layout_weight is not None and parent_type in {"Row", "Column"}:
                    self.record_page_layout_rule(component, rule)
                else:
                    self.add_page_json_unresolved(component, "source.modifiers.weight", "weight requires Row/Column and fill=true; fill=false allocation is not yet equivalent")
            elif rule["kind"] == "alignment":
                value = rule["value"].removeprefix("Alignment.")
                mapped = {"Start": "ItemAlign.Start", "End": "ItemAlign.End", "Top": "ItemAlign.Start", "Bottom": "ItemAlign.End", "CenterHorizontally": "ItemAlign.Center", "CenterVertically": "ItemAlign.Center"}.get(value)
                if parent_type in {"Row", "Column"} and mapped:
                    lines.append(f"{prefix}  .alignSelf({mapped})")
                    self.record_page_layout_rule(component, rule)
                elif parent_type == "Stack":
                    mapped = {"TopStart": "TopStart", "TopCenter": "Top", "TopEnd": "TopEnd", "CenterStart": "Start", "Center": "Center", "CenterEnd": "End", "BottomStart": "BottomStart", "BottomCenter": "Bottom", "BottomEnd": "BottomEnd"}.get(value)
                    if mapped:
                        lines.append(f"{prefix}  .align(Alignment.{mapped})")
                        self.record_page_layout_rule(component, rule)
            elif rule["kind"] == "z_index":
                lines.append(f"{prefix}  .zIndex({rule['value']})")
                self.record_page_layout_rule(component, rule)
            elif rule["kind"] == "constraints":
                if not intrinsic_image_lines:
                    limits = ", ".join(f"{key}: {self.page_layout_length(value)}" for key, value in rule["limits"].items())
                    lines.append(f"{prefix}  .constraintSize({{ {limits} }})")
                self.record_page_layout_rule(component, rule)
            elif rule["kind"] == "scroll" and not rule["enabled"]:
                self.record_page_layout_rule(component, rule)
        flow_shrink = self.page_snapshot_flow_shrink_line(component, parent_type)
        if flow_shrink is not None:
            lines.append(f"{prefix}  {flow_shrink}")
        lines.extend(
            f"{prefix}  {line}"
            for line in self.page_snapshot_dimension_lines(
                component,
                bounds,
                parent_component,
                parent_type,
                is_text,
            )
        )
        minimum_constraint = self.page_snapshot_minimum_constraint_line(component, bounds)
        lines.extend(f"{prefix}  {line}" for line in intrinsic_image_lines)
        if minimum_constraint is not None:
            lines.append(f"{prefix}  {minimum_constraint}")
        if component_type in {"CenterAlignedTopAppBar", "TopAppBar"} and not self.page_snapshot_has_explicit_axis_size(component, "height"):
            padding = component["style"]["layout"].get("padding_dp") or {}
            height = 64 + float(padding.get("top", 0)) + float(padding.get("bottom", 0))
            lines.append(f"{prefix}  .constraintSize({{ minHeight: {self.page_layout_length(height)} }})")
        semantic_key = component.get("semantic_key")
        if isinstance(semantic_key, str):
            lines.append(f"{prefix}  .id({arkts_string(semantic_key)})")
        alignment_lines = self.page_snapshot_container_alignment_lines(component)
        if not scroll_axis:
            lines.extend(f"{prefix}  {line}" for line in alignment_lines)
        if any(".alignItems(" in line or ".alignContent(" in line for line in alignment_lines):
            emitted_phase_paths.add("style.layout.alignment")
        if any(".justifyContent(" in line for line in alignment_lines):
            emitted_phase_paths.add("style.layout.vertical_arrangement" if component_type in PAGE_SNAPSHOT_COLUMN_COMPONENTS else "style.layout.horizontal_arrangement")
        if is_button:
            lines.append(f"{prefix}  .padding(0)")

        style = component["style"]
        state = style["state"]
        if isinstance(state.get("enabled"), bool):
            lines.append(f"{prefix}  .enabled({str(state['enabled']).lower()})")
            emitted_phase_paths.add("style.state.enabled")
        if state.get("visible") is False:
            lines.append(f"{prefix}  .visibility(Visibility.None)")
            emitted_phase_paths.add("style.state.visible")
        description = style["content"].get("content_description")
        if isinstance(description, str):
            lines.append(f"{prefix}  .accessibilityText({arkts_string(description)})")
            emitted_phase_paths.add("style.content.content_description")
        transform = style["transform"]
        translation = {axis: transform.get(f"translation_{axis}_dp") for axis in ("x", "y")}
        if any(value is not None for value in translation.values()):
            if any(rule['kind'] == 'offset' for rule in self.page_snapshot_layout_rules(component)):
                self.add_page_json_unresolved(component, "style.transform", "offset plus explicit translation requires ordered transform composition")
            else:
                values = ', '.join(f"{axis}: {self.page_layout_length(value)}" for axis, value in translation.items() if value is not None)
                lines.append(f"{prefix}  .translate({{ {values} }})")
                emitted_phase_paths.update(f"style.transform.translation_{axis}_dp" for axis, value in translation.items() if value is not None)
        if transform.get('scale_x') is not None or transform.get('scale_y') is not None:
            values = ', '.join(f"{axis}: {self.page_number(transform.get('scale_' + axis) if transform.get('scale_' + axis) is not None else 1)}" for axis in ('x', 'y'))
            lines.append(f"{prefix}  .scale({{ {values} }})")
            emitted_phase_paths.update(f"style.transform.scale_{axis}" for axis in ('x', 'y') if transform.get('scale_' + axis) is not None)
        if transform.get('rotation_degrees') not in (None, 0):
            lines.append(f"{prefix}  .rotate({{ angle: {self.page_number(transform['rotation_degrees'])} }})")
            emitted_phase_paths.add('style.transform.rotation_degrees')
        layout_style = style["layout"]
        if layout_style.get("aspect_ratio") is not None:
            lines.append(f"{prefix}  .aspectRatio({self.page_number(layout_style['aspect_ratio'])})")
            emitted_phase_paths.add("style.layout.aspect_ratio")
        if isinstance(layout_style.get("margin_dp"), dict):
            lines.append(f"{prefix}  .margin({self.page_layout_edges(layout_style['margin_dp'])})")
            emitted_phase_paths.add("style.layout.margin_dp")
        direction = {"ltr": "Ltr", "rtl": "Rtl"}.get(layout_style.get("layout_direction"))
        if direction:
            lines.append(f"{prefix}  .direction(Direction.{direction})")
            emitted_phase_paths.add("style.layout.layout_direction")
        if layout_style.get("z_index") is not None:
            lines.append(f"{prefix}  .zIndex({self.page_number(layout_style['z_index'])})")
            emitted_phase_paths.add("style.layout.z_index")
        surface = style["surface"]
        background = surface["background"]
        if isinstance(background, dict) and background.get("type") == "solid":
            lines.append(f"{prefix}  .backgroundColor({arkts_string(background['color'])})")
            emitted_phase_paths.add("style.surface.background")
        elif isinstance(background, dict) and background.get('type') == 'linear_gradient':
            direction = {0: 'Top', 90: 'Right', 180: 'Bottom', 270: 'Left'}.get(background.get('angle_degrees'))
            if direction and background.get('tile_mode', 'clamp') == 'clamp' and not any(
                key in background for key in ('center', 'radius_dp', 'resource')
            ):
                colors = background['colors']
                stops = background.get('stops') or [i / (len(colors) - 1) for i in range(len(colors))]
                pairs = ', '.join(f"[{arkts_string(color)}, {self.page_number(stop)}]" for color, stop in zip(colors, stops))
                lines.append(f"{prefix}  .linearGradient({{ direction: GradientDirection.{direction}, colors: [{pairs}], repeating: false }})")
                emitted_phase_paths.add('style.surface.background')
            else:
                self.add_page_json_unresolved(component, 'style.surface.background', 'gradient needs axis-aligned bounds and clamp tile mode')
        if surface.get("alpha") is not None:
            lines.append(f"{prefix}  .opacity({self.page_number(surface['alpha'])})")
            emitted_phase_paths.add("style.surface.alpha")
        border = surface["border"]
        if isinstance(border, dict) and (
            border.get('edges') or border.get('dash_dp')
            or border.get('width_dp') is None or border.get('color') is None
        ):
            self.add_page_json_unresolved(component, 'style.surface.border', 'per-edge/custom-dash or incomplete border needs a dedicated draw renderer')
            border = None
        if isinstance(border, dict):
            border_parts = [
                f"width: Math.max(1, Math.ceil(this.getUIContext().vp2px({self.page_number(border['width_dp'])}))) + 'px'",
                f"color: {arkts_string(border['color'])}",
            ]
            if border.get("style") == "dashed":
                border_parts.append("style: BorderStyle.Dashed")
            elif border.get("style") == "dotted":
                border_parts.append("style: BorderStyle.Dotted")
            elif border.get("style") == "none":
                border_parts = ["width: 0"]
            emitted_phase_paths.add("style.surface.border")
        radius = surface["corner_radius_dp"]
        if isinstance(radius, dict):
            values = {name: self.page_number(radius[name]) for name in radius}
            if len(set(values.values())) == 1:
                radius_expression = values["top_left"]
            else:
                radius_expression = (
                    "{ topLeft: " + values["top_left"]
                    + ", topRight: " + values["top_right"]
                    + ", bottomRight: " + values["bottom_right"]
                    + ", bottomLeft: " + values["bottom_left"] + " }"
                )
            lines.append(f"{prefix}  .borderRadius({radius_expression})")
            emitted_phase_paths.add("style.surface.corner_radius_dp")
        if isinstance(border, dict):
            builder = f"pageBorder{len(self._page_border_builders)}"
            self._page_border_builders.append([
                f"  @State private {builder}Width: Length = 0",
                f"  @State private {builder}Height: Length = 0", "",
                "  @Builder", f"  private {builder}() {{", "    Stack() {}",
                f"      .width(this.{builder}Width)", f"      .height(this.{builder}Height)",
                f"      .border({{ {', '.join(border_parts)} }})",
                f"      .borderRadius({radius_expression if isinstance(radius, dict) else '0'})",
                "      .hitTestBehavior(HitTestMode.Transparent)", "  }", "",
            ])
            size_updates.extend([f'this.{builder}Width = current.width ?? 0', f'this.{builder}Height = current.height ?? 0'])
            lines.append(f"{prefix}  .overlay(this.{builder}(), {{ align: Alignment.Center }})")
        if surface.get("clip") is True:
            lines.append(f"{prefix}  .clip(true)")
            emitted_phase_paths.add("style.surface.clip")
        shadows = surface["shadows"]
        if isinstance(shadows, list) and (len(shadows) > 1 or any(shadow.get('spread_radius_dp') != 0 for shadow in shadows)):
            self.add_page_json_unresolved(component, 'style.surface.shadows', 'multiple shadows or spread cannot be represented by one ArkUI shadow')
            shadows = None
        if isinstance(shadows, list) and shadows:
            shadow = shadows[0]
            # ShadowOptions uses physical pixels, unlike most ArkUI dimensions.
            lines.append(
                f"{prefix}  .shadow({{ radius: this.getUIContext().vp2px({self.page_number(shadow['blur_radius_dp'])}), "
                f"color: {arkts_string(shadow['color'])}, "
                f"offsetX: this.getUIContext().vp2px({self.page_number(shadow['offset_x_dp'])}), "
                f"offsetY: this.getUIContext().vp2px({self.page_number(shadow['offset_y_dp'])}) }})"
            )
            emitted_phase_paths.add("style.surface.shadows")

        if is_text or is_text_field:
            typography = style["typography"]
            font_style = {'normal': 'Normal', 'italic': 'Italic'}.get(typography.get('font_style'))
            if font_style:
                lines.append(f"{prefix}  .fontStyle(FontStyle.{font_style})")
                emitted_phase_paths.add('style.typography.font_style')
            page_font_family = typography["font_family"]
            font_size = typography["font_size_sp"]
            if font_size is not None:
                rendered_font_size = Decimal(str(font_size))
                if is_text_field:
                    rendered_font_size = rendered_font_size.quantize(
                        Decimal("1"), rounding=ROUND_HALF_UP
                    )
                if is_text and self.verified_font_alias(str(page_font_family or ''), typography.get('font_weight')):
                    lines.append(f"{prefix}  .fontSize(this.nativeFontSize({self.page_number(font_size)}))")
                else:
                    lines.append(f"{prefix}  .fontSize({decimal_literal(rendered_font_size)})")
                emitted_phase_paths.add("style.typography.font_size_sp")
            font_weight = typography["font_weight"]
            if font_weight is not None:
                lines.append(f"{prefix}  .fontWeight({font_weight})")
                emitted_phase_paths.add("style.typography.font_weight")
            if isinstance(page_font_family, str):
                alias = self.verified_font_alias(page_font_family, typography.get("font_weight"))
                if alias is not None or page_font_family in {"sans-serif", "serif", "monospace", "HarmonyOS Sans"}:
                    lines.append(f"{prefix}  .fontFamily({arkts_string(alias or page_font_family)})")
                    emitted_phase_paths.add("style.typography.font_family")
                else:
                    self.add_page_json_unresolved(component, "style.typography.font_family", f"font family {page_font_family} has no verified registered asset")
            color = typography["color"]
            if color is not None:
                lines.append(f"{prefix}  .fontColor({arkts_string(color)})")
                emitted_phase_paths.add("style.typography.color")
            line_height = typography["line_height_sp"]
            font_alias = self.verified_font_alias(str(page_font_family or ''), typography.get("font_weight"))
            font_face = next((face for face in self.verified_font_faces if face['alias'] == font_alias), None)
            if is_text and font_face is not None and font_size is not None:
                self._uses_page_font_metrics = True
                args = f"$rawfile({arkts_string(font_face['rawfile'])}), {self.page_number(font_size)}"
                if not self.page_snapshot_has_explicit_axis_size(component, 'height') and not any(
                    rule['kind'] == 'constraints' for rule in self.page_snapshot_layout_rules(component)
                ) and (typography.get('min_lines') or 1) == 1:
                    lines.append(f"{prefix}  .constraintSize({{ minHeight: this.nativeLineHeight({args}) }})")
                lines.append(f"{prefix}  .lineHeight(this.nativeLineHeight({args}))")
                lines.append(f"{prefix}  .halfLeading(true)")
                if line_height is not None:
                    lines.append(f"{prefix}  .lineSpacing(this.nativeLineSpacing({args}, {self.page_number(line_height)}), {{ onlyBetweenLines: true }})")
                    emitted_phase_paths.add("style.typography.line_height_sp")
            elif line_height is not None:
                lines.append(
                    f"{prefix}  .lineHeight({self.page_number(line_height)})"
                )
                emitted_phase_paths.add("style.typography.line_height_sp")
            letter_spacing = typography["letter_spacing_sp"]
            if letter_spacing is not None:
                lines.append(
                    f"{prefix}  .letterSpacing({self.page_number(letter_spacing)})"
                )
                emitted_phase_paths.add("style.typography.letter_spacing_sp")
            text_align = {
                "start": "TextAlign.Start",
                "center": "TextAlign.Center",
                "end": "TextAlign.End",
                "justify": "TextAlign.Justify",
            }.get(typography["text_align"])
            if text_align is not None:
                lines.append(f"{prefix}  .textAlign({text_align})")
                emitted_phase_paths.add("style.typography.text_align")
            max_lines = typography["max_lines"]
            soft_wrap = typography.get('soft_wrap')
            if soft_wrap is False:
                if is_text and re.search(r'[\n\r\u2028\u2029]', self.page_snapshot_text_value(component)) is None:
                    lines.append(f'{prefix}  .maxLines(1)')
                    emitted_phase_paths.add('style.typography.soft_wrap')
                    if max_lines is not None:
                        emitted_phase_paths.add('style.typography.max_lines')
                else:
                    self.add_page_json_unresolved(component, 'style.typography.soft_wrap', 'unwrapped hard line breaks require paragraph-specific rendering')
            elif soft_wrap is True:
                emitted_phase_paths.add('style.typography.soft_wrap')
            if max_lines is not None and soft_wrap is not False:
                lines.append(f"{prefix}  .maxLines({max_lines})")
                emitted_phase_paths.add("style.typography.max_lines")
            min_lines = typography.get('min_lines')
            if min_lines == 1:
                emitted_phase_paths.add('style.typography.min_lines')
            elif min_lines is not None:
                if is_text and font_face is not None and font_size is not None and not any(
                    rule['kind'] == 'constraints' for rule in self.page_snapshot_layout_rules(component)
                ):
                    if not self.page_snapshot_has_explicit_axis_size(component, 'height'):
                        padding = style['layout'].get('padding_dp') or {}
                        vertical_padding = float(padding.get('top', 0)) + float(padding.get('bottom', 0))
                        args = f"$rawfile({arkts_string(font_face['rawfile'])}), {self.page_number(font_size)}, {self.page_number(line_height or 0)}, {min_lines}, {self.page_number(vertical_padding)}"
                        lines.append(f'{prefix}  .constraintSize({{ minHeight: this.nativeMinLinesHeight({args}) }})')
                    emitted_phase_paths.add('style.typography.min_lines')
                else:
                    self.add_page_json_unresolved(component, 'style.typography.min_lines',
                        'minLines > 1 requires verified text font metrics without conflicting constraints; not a reference bbox height')
            overflow = {
                "clip": "TextOverflow.Clip",
                "ellipsis": "TextOverflow.Ellipsis",
            }.get(typography["overflow"])
            if overflow is not None:
                argument = overflow if is_text_field else f"{{ overflow: {overflow} }}"
                lines.append(f"{prefix}  .textOverflow({argument})")
                emitted_phase_paths.add("style.typography.overflow")
            decoration = {
                "none": "TextDecorationType.None",
                "underline": "TextDecorationType.Underline",
                "line_through": "TextDecorationType.LineThrough",
            }.get(typography["decoration"])
            if decoration is not None:
                lines.append(
                    f"{prefix}  .decoration({{ type: {decoration} }})"
                )
                emitted_phase_paths.add("style.typography.decoration")

        if component_type in {"Image", "Icon", "AsyncImage"}:
            content_scale = {
                "fit": "ImageFit.Contain",
                "crop": "ImageFit.Cover",
                "fill": "ImageFit.Fill",
                "inside": "ImageFit.ScaleDown",
                "none": "ImageFit.None",
            }.get(style["asset"].get("content_scale"))
            if content_scale is not None:
                lines.append(f"{prefix}  .objectFit({content_scale})")
                emitted_phase_paths.add("style.asset.content_scale")
            tint = style["asset"].get("tint")
            if isinstance(tint, str) and not page_tint_baked:
                lines.extend(
                    f"{prefix}  {line}"
                    for line in self.image_tint_lines(arkts_string(tint))
                )
                emitted_phase_paths.add("style.asset.tint")
        elif component_type == "ProgressRing":
            custom_draw = component.get("custom_draw")
            if isinstance(custom_draw, dict):
                lines.extend((
                    f"{prefix}  .color({arkts_string(custom_draw['active_color'])})",
                    f"{prefix}  .backgroundColor({arkts_string(custom_draw['track_color'])})",
                    f"{prefix}  .style({{ strokeWidth: {self.page_number(float(custom_draw['stroke_width_dp']))} }})",
                ))

        padding = style["layout"]["padding_dp"]
        if isinstance(padding, dict):
            lines.append(f"{prefix}  .padding({self.page_layout_edges(padding)})")
            emitted_phase_paths.add("style.layout.padding_dp")
        if is_text_field and not multiline_input:
            lines.append(f"{prefix}  .showPasswordIcon(false)")
        if is_text_field:
            password = input_style.get('password')
            keyboard = input_style.get('keyboard_type')
            if multiline_input and (password or keyboard in {'password', 'number_password'}):
                self.add_page_json_unresolved(component, 'style.input.password', 'multiline password needs a dedicated transformation renderer')
            else:
                kind = ('number_password' if keyboard in {'number', 'number_password'} else 'password') if password else keyboard
                native_types = ({'text': 'NORMAL', 'number': 'NUMBER', 'phone': 'PHONE_NUMBER', 'email': 'EMAIL', 'url': 'URL', 'decimal': 'NUMBER_DECIMAL'}
                    if multiline_input else {'text': 'Normal', 'number': 'Number', 'phone': 'PhoneNumber', 'email': 'Email', 'url': 'URL', 'decimal': 'NUMBER_DECIMAL', 'password': 'Password', 'number_password': 'NUMBER_PASSWORD'})
                if kind in native_types:
                    lines.append(f"{prefix}  .type({'TextAreaType' if multiline_input else 'InputType'}.{native_types[kind]})")
                    emitted_phase_paths.add('style.input.keyboard_type')
                if password is not None:
                    if not multiline_input and kind in {'password', 'number_password'}:
                        lines.append(f"{prefix}  .showPassword({str(not password).lower()})")
                    emitted_phase_paths.add('style.input.password')
            read_only = input_style.get('read_only')
            if read_only is True:
                lines.append(f"{prefix}  .enableKeyboardOnFocus(false)")
                lines.append(f"{prefix}  .onWillChange(() => false)")
                emitted_phase_paths.add('style.input.read_only')
            elif read_only is False:
                emitted_phase_paths.add('style.input.read_only')
            action = input_style.get('ime_action')
            action_map = {'go': 'Go', 'search': 'Search', 'send': 'Send', 'next': 'Next', 'done': 'Done',
                          'default': 'NEW_LINE' if multiline_input else 'Done'}
            if multiline_input:
                action_map['none'] = 'NEW_LINE'
            if action in action_map:
                lines.append(f"{prefix}  .enterKeyType(EnterKeyType.{action_map[action]})")
                emitted_phase_paths.add('style.input.ime_action')

        measured = self._page_constraint_states.get(component['id'])
        if measured:
            padding = style['layout'].get('padding_dp') or {}
            for axis in sorted(measured['axes']):
                edges = ('left', 'right') if axis == 'width' else ('top', 'bottom')
                inset = sum(float(padding.get(edge) or 0) for edge in edges)
                size_updates.append(f"this.{measured['name']}{axis.title()} = Math.max(0, Number(current.{axis}) - {self.page_number(inset)})")
        if size_updates:
            lines.append(f"{prefix}  .onSizeChange((_old, current) => {{ {'; '.join(size_updates)} }})")
        scaffold_padding = (component.get('source') or {}).get('scaffold_padding')
        if isinstance(scaffold_padding, dict):
            owner = self._page_scaffold_states.get(scaffold_padding.get('owner_id'))
            edges = scaffold_padding.get('edges') or {}
            if owner and edges and set(edges.values()) <= {'topBar', 'bottomBar'}:
                padding = style['layout'].get('padding_dp') or {}
                values = []
                for edge in ('left', 'right', 'top', 'bottom'):
                    offset = self.page_number(padding.get(edge, 0))
                    expression = f'this.{owner}{edges[edge].title()} + {offset}' if edge in edges else offset
                    values.append(f'{edge}: {expression}')
                lines.append(f"{prefix}  .padding({{ {', '.join(values)} }})")
            else:
                self.add_page_json_unresolved(component, 'source.scaffold_padding', 'Scaffold padding owner/slot is unavailable')

        component_text = style["content"].get("text")
        if isinstance(component_text, str) and "style.content.text" not in emitted_phase_paths:
            pending_descendants = list(component.get("children_ids") or [])
            while pending_descendants:
                descendant_id = pending_descendants.pop()
                descendant = self.android_page_by_id.get(descendant_id)
                if not isinstance(descendant, dict):
                    continue
                if (
                    descendant["style"]["content"].get("text") == component_text
                    and "style.content.text"
                    in self.android_page_applied_component_paths.get(descendant_id, set())
                ):
                    emitted_phase_paths.add("style.content.text")
                    break
                pending_descendants.extend(descendant.get("children_ids") or [])

        component_color = style["typography"].get("color")
        if (
            isinstance(component_color, str)
            and "style.typography.color" not in emitted_phase_paths
            and self.page_snapshot_descendant_consumes_typography_color(
                component, component_color
            )
        ):
            emitted_phase_paths.add("style.typography.color")

        if not hasattr(self, "android_page_applied_component_paths"):
            self.android_page_applied_component_paths = defaultdict(set)
        component_applied = self.android_page_applied_component_paths[component["id"]]
        component_applied.update(
            {"bounds_dp.x", "bounds_dp.y", "bounds_dp.width", "bounds_dp.height"}
        )
        component_applied.update(emitted_phase_paths)
        component_applied.add("structure.type")
        if all(child["id"] in self.android_page_processed_component_ids for child in children):
            component_applied.add("structure.children_ids")
        if parent_component is None and component.get("parent_id") is None:
            component_applied.update({"structure.parent_id", "structure.sibling_index"})
        elif structural_parent is not None and component["id"] in structural_parent["children_ids"]:
            component_applied.add("structure.parent_id")
            if structural_parent["children_ids"].index(component["id"]) == component.get("sibling_index"):
                component_applied.add("structure.sibling_index")
        if component.get("source_layout_bounds_dp") is not None:
            component_applied.add("source_layout_bounds_dp")
        if not hasattr(self, "android_page_processed_component_ids"):
            self.android_page_processed_component_ids = set()
        self.android_page_processed_component_ids.add(component["id"])
        return lines

    def render_android_page_snapshot(self) -> list[str]:
        if self.android_page_input is None:
            return []
        content_bounds = self.android_page_input["viewport"]["content_bounds_dp"]
        roots = [
            component
            for component in self.android_page_input["components"]
            if component["parent_id"] is None
        ]
        roots.sort(
            key=lambda component: (
                0 if component["style"]["content"].get("role") == "surface" else 1,
                component["sibling_index"],
                component["bounds_dp"]["y"],
                component["bounds_dp"]["x"],
            )
        )
        lines = ["  @Builder", "  private renderAndroidPageSnapshot() {", "    Stack() {"]
        for component in roots:
            lines.extend(self.page_snapshot_component_lines(component, content_bounds, None, 6))
        lines.extend([
            "    }",
            "      .width('100%')",
            "      .height('100%')",
        ])
        if "compose_theme_background" in self.resource_names:
            lines.append("      .backgroundColor($r('app.color.compose_theme_background'))")
        lines.append("  }")
        return lines

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
        struct_name = f"Generated{pascal_identifier(self.root['composable'])}"
        root_public_parameters: list[dict[str, Any]] = []
        self._root_public_parameters = root_public_parameters
        self._page_border_builders: list[list[str]] = []
        self._page_constraint_states: dict[str, dict[str, Any]] = {}
        self._page_scaffold_states: dict[str, str] = {}
        self._page_match_parent_sizes: dict[str, str] = {}
        self._page_match_parent_builders: list[list[str]] = []
        page_snapshot_section = self.render_android_page_snapshot()
        lines = [
            "// Generated only from the audited source-generated version_json.",
            "// Unresolved behavior is recorded in the paired .migration manifest.",
            "",
        ]
        if self._uses_resource_manager:
            lines.extend(["import resourceManager from '@ohos.resourceManager';", ""])
        if self._uses_drawing_color_filter or getattr(self, "_uses_page_font_metrics", False):
            lines.extend(["import drawing from '@ohos.graphics.drawing';", ""])
        if getattr(self, "_uses_page_font_metrics", False):
            lines.extend(["import { LengthMetrics } from '@ohos.arkui.node';", ""])
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
        for border_builder in self._page_border_builders:
            lines.extend(border_builder)
        for overlay_builder in self._page_match_parent_builders:
            lines.extend(overlay_builder)
        for name in self._page_scaffold_states.values():
            lines.extend([f'  @State private {name}{slot.title()}: number = 0' for slot in ('topBar', 'bottomBar')])
        for state in self._page_constraint_states.values():
            for axis in sorted(state['axes']):
                lines.append(f"  @State private {state['name']}{axis.title()}: number = 0")
        if getattr(self, "_uses_page_layout_pixels", False):
            lines.extend([
                "  private layoutPx(value: number): string {",
                "    return Math.round(this.getUIContext().vp2px(value)) + 'px'",
                "  }",
                "",
            ])
        if getattr(self, "_uses_page_font_metrics", False):
            lines.extend([
                "  private nativeFontSize(size: number): string {",
                "    return Math.floor(this.getUIContext().fp2px(size)) + 'px'",
                "  }",
                "",
                "  private nativeLinePixels(file: Resource, size: number): number {",
                "    const font = new drawing.Font()",
                "    font.setTypeface(drawing.Typeface.makeFromRawFile(file))",
                "    font.setSize(this.getUIContext().fp2px(size))",
                "    const metrics = font.getMetrics()",
                "    return Math.round(metrics.descent) - Math.round(metrics.ascent)",
                "  }",
                "",
                "  private nativeLineHeight(file: Resource, size: number): string {",
                "    return this.nativeLinePixels(file, size) + 'px'",
                "  }",
                "",
                "  private nativeMinLinesHeight(file: Resource, size: number, requested: number, count: number, padding: number): string {",
                "    const natural = this.nativeLinePixels(file, size)",
                "    const extra = Math.max(0, Math.round(this.getUIContext().fp2px(requested)) - natural)",
                "    return (natural * count + extra * (count - 1) + Math.round(this.getUIContext().vp2px(padding))) + 'px'",
                "  }",
                "",
                "  private nativeLineSpacing(file: Resource, size: number, requested: number): LengthMetrics {",
                "    return LengthMetrics.px(Math.max(0, Math.round(this.getUIContext().fp2px(requested)) - this.nativeLinePixels(file, size)))",
                "  }",
                "",
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
        lines.append("  build() {")
        lines.extend([
            "    Stack() {",
            "      this.renderAndroidPageSnapshot()",
            "    }",
            "      .alignContent(Alignment.TopStart)",
            "      .width('100%')",
            "      .height('100%')",
        ])
        lines.extend(("  }", ""))
        if page_snapshot_section:
            lines.extend(page_snapshot_section)
            lines.append("")
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


def load_page_font_faces(target: Path, module: str, page: dict[str, Any]) -> list[dict[str, Any]]:
    faces = page.get("font_faces", [])
    if not isinstance(faces, list):
        raise ArkUIPageError("page fontFaces must be a list")
    if not faces:
        return []
    ledger_path = target / ".migration/assets.json"
    if ledger_path.is_symlink() or not ledger_path.is_file():
        raise ArkUIPageError("page fonts require a verified target asset ledger")
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if ledger.get("schema") != "android-to-harmony.asset-ledger.v1":
        raise ArkUIPageError("unsupported font asset ledger")
    result = []
    for face in faces:
        if not isinstance(face, dict) or set(face) != {"family", "resource", "weight"}:
            raise ArkUIPageError("page font face must have family/resource/weight")
        family, resource, weight = face["family"], face["resource"], face["weight"]
        if not isinstance(family, str) or not isinstance(resource, str) or RESOURCE_NAME_PATTERN.fullmatch(resource) is None or type(weight) is not int or not 1 <= weight <= 1000:
            raise ArkUIPageError("invalid page font face")
        matches = [(path, meta) for path, meta in ledger.get("assets", {}).items()
                   if isinstance(meta, dict) and Path(meta.get("asset_path", "")).stem == resource
                   and Path(meta.get("asset_path", "")).parent.name == "font"]
        if len(matches) != 1:
            raise ArkUIPageError(f"missing or ambiguous font asset {resource}")
        relative, metadata = matches[0]
        destination = target / relative
        raw_root = (target / module / "src/main/resources/rawfile").resolve()
        if destination.is_symlink() or not destination.resolve().is_relative_to(raw_root) or not destination.is_file() or sha256_file(destination) != metadata.get("destination_sha256"):
            raise ArkUIPageError(f"font asset hash/path mismatch: {relative}")
        result.append({"alias": pascal_identifier(resource) + str(weight), "weight": weight,
                       "rawfile": destination.resolve().relative_to(raw_root).as_posix(),
                       "target_path": relative, "sha256": metadata["destination_sha256"],
                       "match_names": [normalized_font_name(family)]})
    return result


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
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict):
        raise ArkUIPageError("previous ArkUI generation manifest outputs are invalid")
    relative = output_path.relative_to(target).as_posix()
    if relative not in outputs:
        raise ArkUIPageError("previous ArkUI generation manifest does not own the page output")
    for owned_relative, metadata in outputs.items():
        if (
            not isinstance(owned_relative, str)
            or not isinstance(metadata, dict)
            or not isinstance(metadata.get("sha256"), str)
        ):
            raise ArkUIPageError("previous ArkUI generation manifest output entry is invalid")
        owned_path = target / owned_relative
        if (
            not owned_path.is_file()
            or owned_path.is_symlink()
            or metadata["sha256"] != sha256_file(owned_path)
        ):
            raise ArkUIPageError(
                f"generated ArkUI output changed after generation: {owned_relative}"
            )


def derive_page_tinted_vectors(
    target: Path,
    module: str,
    page_identity: str,
    android_page_input: dict[str, Any] | None,
) -> tuple[dict[tuple[str, str], str], dict[Path, bytes], list[dict[str, str]]]:
    if android_page_input is None:
        return {}, {}, []
    media_root = target / module / "src/main/resources/base/media"
    mappings: dict[tuple[str, str], str] = {}
    payloads: dict[Path, bytes] = {}
    records: list[dict[str, str]] = []
    for component in android_page_input["components"]:
        asset = component["style"]["asset"]
        resource = asset.get("resource")
        tint = asset.get("tint")
        if (
            not isinstance(resource, str)
            or RESOURCE_NAME_PATTERN.fullmatch(resource) is None
            or not isinstance(tint, str)
            or re.fullmatch(r"#[0-9A-Fa-f]{8}", tint) is None
            or (resource, tint) in mappings
        ):
            continue
        source = media_root / f"{resource}.svg"
        if not source.is_file() or source.is_symlink():
            continue
        source_bytes = source.read_bytes()
        try:
            root = ET.fromstring(source_bytes)
        except ET.ParseError as error:
            raise ArkUIPageError(f"target vector resource is malformed: {resource}") from error
        alpha = int(tint[1:3], 16) / 255
        rgb = f"#{tint[3:].upper()}"
        shape_names = {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}
        for element in root.iter():
            local_name = element.tag.rsplit("}", 1)[-1]
            if local_name not in shape_names:
                continue
            fill = element.get("fill")
            if fill is None or fill.lower() != "none":
                element.set("fill", rgb)
                if alpha < 1:
                    existing_alpha = float(element.get("fill-opacity", "1"))
                    element.set(
                        "fill-opacity",
                        f"{existing_alpha * alpha:.6f}".rstrip("0").rstrip("."),
                    )
            stroke = element.get("stroke")
            if stroke is not None and stroke.lower() != "none":
                element.set("stroke", rgb)
                if alpha < 1:
                    existing_alpha = float(element.get("stroke-opacity", "1"))
                    element.set(
                        "stroke-opacity",
                        f"{existing_alpha * alpha:.6f}".rstrip("0").rstrip("."),
                    )
        if root.tag.startswith("{http://www.w3.org/2000/svg}"):
            ET.register_namespace("", "http://www.w3.org/2000/svg")
        output_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        output_name = f"a2h_{page_identity[:8]}_{resource}_{tint[1:].lower()}"
        if RESOURCE_NAME_PATTERN.fullmatch(output_name) is None:
            raise ArkUIPageError(f"derived page vector name is invalid: {output_name}")
        destination = media_root / f"{output_name}.svg"
        mappings[(resource, tint)] = output_name
        payloads[destination] = output_bytes
        records.append({
            "source_resource": resource,
            "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "tint": tint.upper(),
            "output": destination.relative_to(target).as_posix(),
            "sha256": hashlib.sha256(output_bytes).hexdigest(),
        })
    return mappings, payloads, sorted(records, key=lambda item: item["output"])


def derive_page_root(android_page_input: dict[str, Any]) -> dict[str, str]:
    roots = [
        component
        for component in android_page_input["components"]
        if component["parent_id"] is None
    ]
    identities = {
        (source.get("source"), source.get("composable"))
        for component in roots
        for source in [component.get("source")]
        if isinstance(source, dict)
        and isinstance(source.get("source"), str)
        and source["source"]
        and isinstance(source.get("composable"), str)
        and source["composable"]
    }
    if len(identities) != 1:
        raise ArkUIPageError(
            "page JSON must identify exactly one source root; source fallback is disabled"
        )
    source, composable = next(iter(identities))
    return {
        "source": require_safe_relative_source(source),
        "composable": composable,
    }


def generate(
    target_path: Path,
    module: str,
    page_json: Path,
    force: bool,
) -> dict[str, Any]:
    target = normalize_target(target_path)
    require_module(target, module)
    android_page_input = load_lanhu_page_input(page_json)
    if not android_page_input.get("source_generated"):
        raise ArkUIPageError(
            "--page-json must be a source-generated Lanhu version_json"
        )
    root = derive_page_root(android_page_input)
    identity = hashlib.sha256(
        f"{root['source']}#{root['composable']}".encode("utf-8")
    ).hexdigest()[:16]
    resource_names, string_values = load_theme_resources(target, module)
    required_gate = android_page_input.get("required_fact_gate")
    tinted_vector_resources, tinted_vector_payloads, tinted_vector_records = (
        derive_page_tinted_vectors(target, module, identity, android_page_input)
    )
    renderer = Renderer(
        root,
        resource_names,
        string_values,
        android_page_input,
        tinted_vector_resources,
    )
    renderer.verified_font_faces = load_page_font_faces(target, module, android_page_input)
    source = renderer.render()
    target_phase_gate = build_target_phase_consumption_gate(
        android_page_input,
        renderer.android_page_processed_component_ids,
        renderer.android_page_processed_call_ids,
        renderer.android_page_applied_paths,
        renderer.android_page_applied_component_paths,
    )
    phase_gate_enforced = android_page_input.get("input_format") == "lanhu-version-json"
    if phase_gate_enforced and target_phase_gate["verdict"] != "pass":
        for failure in target_phase_gate["failures"]:
            renderer.add_unresolved(
                "page_json_unconsumed_fact",
                None,
                "page JSON fact was not consumed by the ArkUI emitter",
                page_component_id=failure["component_id"],
                path=failure["path"],
                phase=failure["phase"],
            )
    generation_complete = not renderer.unresolved and target_phase_gate["verdict"] == "pass"
    output_relative = (
        f"{module}/src/main/ets/generated/Generated{pascal_identifier(root['composable'])}.ets"
    )
    manifest_relative = f".migration/arkui-pages/{identity}.json"
    output_path = target / output_relative
    manifest_path = target / manifest_relative
    validate_previous(target, output_path, manifest_path, root, module, force)
    output_bytes = source.encode("utf-8")
    semantic_input = {
        "input_mode": "page-json-only",
        "page_json_sha256": android_page_input["sha256"],
    }
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "generator": "migrate-android-compose-to-harmony",
        "status": "candidate_requires_review",
        "authoritative": False,
        "target_root": ".",
        "module": module,
        "root": root,
        "input_mode": "page-json-only",
        "source_fallback_count": 0,
        "source_fallbacks": [],
        "semantic_input_sha256": canonical_sha256(semantic_input),
        "expanded_definition_count": len(renderer.reached_keys),
        "selected_call_count": len(renderer.selected_calls),
        "verified_font_assets": renderer.verified_font_faces,
        "generation_complete": generation_complete,
        "verdict": "pass" if generation_complete else "fail",
        "required_fact_gate": required_gate,
        "source_phase_consumption_gate": android_page_input.get("source_phase_consumption_gate"),
        "target_phase_consumption_gate": target_phase_gate,
        "unresolved": renderer.unresolved,
        "outputs": {
            output_relative: {
                "sha256": hashlib.sha256(output_bytes).hexdigest(),
                "root_component": f"Generated{pascal_identifier(root['composable'])}",
            },
            **{
                record["output"]: {
                    "sha256": record["sha256"],
                    "kind": "page_state_tinted_vector",
                }
                for record in tinted_vector_records
            },
        },
        "derived_page_assets": tinted_vector_records,
        "limitations": [
            "The generator consumes only the source-generated version_json and target-owned resources.",
            "Missing or symbolic page facts are recorded as unresolved and are never filled from Android source or a migration contract.",
            "A successful ArkTS build proves source compatibility, not visual or behavioral parity.",
        ],
    }
    if android_page_input is not None:
        manifest["android_page_input"] = {
            "file": android_page_input["file"],
            "byte_count": android_page_input["byte_count"],
            "sha256": android_page_input["sha256"],
            "input_format": android_page_input["input_format"],
            "layout_mode": renderer.android_page_layout_mode,
            "page": android_page_input["page"],
            "viewport": android_page_input["viewport"],
            "screenshot": android_page_input["screenshot"],
            "component_count": len(android_page_input["components"]),
            "source_component_count": len(android_page_input["components"]),
            "business_component_count": sum(
                bool((component.get("source") or {}).get("custom_component"))
                for component in android_page_input["components"]
            ),
            "layout_relationship_count": len(android_page_input["layout_relationships"]),
            "overlay_relationship_count": sum(
                relationship["composition"] == "overlay"
                for relationship in android_page_input["layout_relationships"]
            ),
            "mapped_call_count": len(renderer.android_page_by_call_id),
            "applied_paths": {
                call_id: sorted(paths)
                for call_id, paths in sorted(renderer.android_page_applied_paths.items())
            },
            "component_applied_paths": {
                component_id: sorted(paths)
                for component_id, paths in sorted(
                    renderer.android_page_applied_component_paths.items()
                )
            },
            "reference_paths": {
                call_id: sorted(paths)
                for call_id, paths in sorted(renderer.android_page_reference_paths.items())
            },
        }
        manifest["android_page_input"]["version_json"] = android_page_input["version_json"]
    manifest_bytes = json_bytes(manifest)
    commit_payloads({
        output_path: output_bytes,
        manifest_path: manifest_bytes,
        **tinted_vector_payloads,
    })
    return {
        "target": str(target),
        "module": module,
        "root": root,
        "output": output_relative,
        "manifest": manifest_relative,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "generation_complete": generation_complete,
        "verdict": "pass" if generation_complete else "fail",
        "required_fact_gate": required_gate,
        "target_phase_consumption_gate": (
            {
                key: value
                for key, value in target_phase_gate.items()
                if key != "checks"
            }
            if isinstance(target_phase_gate, dict)
            else None
        ),
        "unresolved_count": len(renderer.unresolved),
        "expanded_definition_count": len(renderer.reached_keys),
    }


def main() -> int:
    args = parse_args()
    try:
        result = generate(
            args.target,
            args.module,
            args.page_json,
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
