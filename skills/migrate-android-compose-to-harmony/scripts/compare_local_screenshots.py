#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
from collections import deque
from pathlib import Path
from typing import Any

from page_snapshot import (
    PageSnapshotError,
    normalize_provenance,
    normalize_style,
    normalize_unresolved,
)

try:
    from PIL import (
        Image,
        ImageChops,
        ImageDraw,
        ImageEnhance,
        ImageFilter,
        ImageOps,
        ImageStat,
        UnidentifiedImageError,
        __version__ as PILLOW_VERSION,
    )
except ImportError:
    Image = None
    ImageChops = None
    ImageDraw = None
    ImageEnhance = None
    ImageFilter = None
    ImageOps = None
    ImageStat = None
    UnidentifiedImageError = OSError
    PILLOW_VERSION = None


REPORT_SCHEMA = "android-to-harmony.local-image-comparison.v1"
COMMAND_SCHEMA = "android-to-harmony.command-result.v1"
COMPONENT_SCHEMA = "android-to-harmony.component-bounds.v1"
COMPONENT_SCHEMA_V2 = "android-to-harmony.component-bounds.v2"
PAGE_SNAPSHOT_SCHEMA = "android-to-harmony.page-snapshot.v1"
PAGE_SNAPSHOT_V2_SCHEMA = "android-to-harmony.page-snapshot.v2"
SOURCE_ATTRIBUTE_SCHEMA = "android-to-harmony.source-attribute-inventory.v1"
EDGE_TOLERANCE_RADIUS_PX = 1.0
RASTERIZATION_TOLERANCE_RADIUS_PX = 0.5


class ComparisonError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare two authorized screenshots entirely through local Pillow processing. "
            "Image pixels remain in local artifacts and are never printed."
        )
    )
    parser.add_argument("--left", required=True, type=Path)
    parser.add_argument("--right", required=True, type=Path)
    parser.add_argument("--left-label", default="android")
    parser.add_argument("--right-label", default="harmony")
    parser.add_argument(
        "--left-components",
        type=Path,
        help="optional sanitized component-bounds JSON for the left screenshot",
    )
    parser.add_argument(
        "--right-components",
        type=Path,
        help="optional sanitized component-bounds JSON for the right screenshot",
    )
    parser.add_argument(
        "--source-attributes",
        type=Path,
        help="optional sanitized source-attribute inventory for component impact mapping",
    )
    parser.add_argument(
        "--left-crop",
        help="x,y,width,height; overrides v2 content bounds, otherwise defaults to the full image",
    )
    parser.add_argument(
        "--right-crop",
        help="x,y,width,height; overrides v2 content bounds, otherwise defaults to the full image",
    )
    parser.add_argument(
        "--target-size",
        help="widthxheight; defaults to the left crop dimensions",
    )
    parser.add_argument(
        "--min-ssim",
        type=float,
        default=0.95,
        help="minimum color, luma, and edge SSIM required for a pass (default: 0.95)",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_input(path: Path, label: str) -> Path:
    requested = Path(os.path.abspath(os.path.expanduser(str(path))))
    if requested.is_symlink():
        raise ComparisonError(f"{label} screenshot must not be a symbolic link")
    if not requested.is_file():
        raise ComparisonError(f"{label} screenshot is not a regular file")
    if requested.stat().st_size <= 0:
        raise ComparisonError(f"{label} screenshot is empty")
    return requested


def resolve_component_input(path: Path, label: str) -> Path:
    requested = Path(os.path.abspath(os.path.expanduser(str(path))))
    if requested.is_symlink():
        raise ComparisonError(f"{label} component inventory must not be a symbolic link")
    if not requested.is_file():
        raise ComparisonError(f"{label} component inventory is not a regular file")
    byte_count = requested.stat().st_size
    if byte_count <= 0:
        raise ComparisonError(f"{label} component inventory is empty")
    if byte_count > 5 * 1024 * 1024:
        raise ComparisonError(f"{label} component inventory exceeds 5 MiB")
    return requested


def resolve_source_attribute_input(path: Path) -> Path:
    requested = Path(os.path.abspath(os.path.expanduser(str(path))))
    if requested.is_symlink():
        raise ComparisonError("source attribute inventory must not be a symbolic link")
    if not requested.is_file():
        raise ComparisonError("source attribute inventory is not a regular file")
    byte_count = requested.stat().st_size
    if byte_count <= 0:
        raise ComparisonError("source attribute inventory is empty")
    if byte_count > 10 * 1024 * 1024:
        raise ComparisonError("source attribute inventory exceeds 10 MiB")
    return requested


def validate_component_token(value: Any, field: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9._:/#@-]{1,120}", value) is None:
        raise ComparisonError(
            f"component {field} must use 1 to 120 non-sensitive identifier characters"
        )
    return value


def load_component_inventory(
    requested_path: Path | None,
    side: str,
    expected_dimensions: tuple[int, int],
    expected_screenshot: Path,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    if requested_path is None:
        return None, [], []
    path = resolve_component_input(requested_path, side)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ComparisonError(f"{side} component inventory is not valid UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise ComparisonError(f"{side} component inventory root must be an object")
    schema = payload.get("schema")
    if schema in {COMPONENT_SCHEMA, COMPONENT_SCHEMA_V2}:
        expected_fields = {"schema", "screenshot_dimensions", "components"}
        if schema == COMPONENT_SCHEMA_V2:
            expected_fields.add("content_insets_px")
        if set(payload) != expected_fields:
            raise ComparisonError(f"{side} component inventory has unsupported root fields")
        dimensions = payload["screenshot_dimensions"]
        raw_components = payload["components"]
        bounds_field = "bounds"
    elif schema in {PAGE_SNAPSHOT_SCHEMA, PAGE_SNAPSHOT_V2_SCHEMA}:
        required_page_fields = {
            "schema", "status", "authoritative", "platform", "page", "viewport",
            "capture", "input_hashes", "components", "unmapped_source_components", "limitations",
        }
        allowed_page_fields = set(required_page_fields)
        if schema == PAGE_SNAPSHOT_V2_SCHEMA:
            required_page_fields.add("unmapped_visual_fact_components")
            allowed_page_fields.update({
                "unmapped_visual_fact_components",
                "inactive_source_components",
                "runtime_elided_source_components",
                "source_component_tree",
            })
        if not required_page_fields.issubset(payload) or not set(payload).issubset(allowed_page_fields):
            raise ComparisonError(f"{side} page snapshot has unsupported root fields")
        inactive_source_components = payload.get("inactive_source_components", [])
        if not isinstance(inactive_source_components, list) or len(inactive_source_components) > 10000:
            raise ComparisonError(f"{side} page snapshot inactive source components are malformed")
        for inactive in inactive_source_components:
            if (
                not isinstance(inactive, dict)
                or set(inactive) != {"source_semantic_key", "source_call_id", "reason"}
                or not isinstance(inactive.get("source_semantic_key"), str)
                or not inactive["source_semantic_key"]
                or not isinstance(inactive.get("source_call_id"), str)
                or not inactive["source_call_id"]
                or inactive.get("reason") != "inactive_source_branch"
            ):
                raise ComparisonError(f"{side} page snapshot inactive source component is malformed")
        runtime_elided_source_components = payload.get("runtime_elided_source_components", [])
        if not isinstance(runtime_elided_source_components, list) or len(runtime_elided_source_components) > 10000:
            raise ComparisonError(f"{side} page snapshot runtime-elided source components are malformed")
        for elided in runtime_elided_source_components:
            if (
                not isinstance(elided, dict)
                or set(elided) != {"source_semantic_key", "source_call_id", "reason"}
                or not isinstance(elided.get("source_semantic_key"), str)
                or not elided["source_semantic_key"]
                or not isinstance(elided.get("source_call_id"), str)
                or not elided["source_call_id"]
                or elided.get("reason") != "runtime_nonsemantic_layout_elision"
            ):
                raise ComparisonError(f"{side} page snapshot runtime-elided source component is malformed")
        viewport = payload["viewport"]
        if not isinstance(viewport, dict):
            raise ComparisonError(f"{side} page snapshot viewport is malformed")
        dimensions = {
            "width": viewport.get("width_px"),
            "height": viewport.get("height_px"),
        }
        capture = payload["capture"]
        screenshot_record = capture.get("screenshot") if isinstance(capture, dict) else None
        if not isinstance(screenshot_record, dict):
            raise ComparisonError(f"{side} page snapshot screenshot record is malformed")
        if screenshot_record.get("byte_count") != expected_screenshot.stat().st_size:
            raise ComparisonError(f"{side} page snapshot screenshot byte count does not match")
        expected_sha256 = sha256_file(expected_screenshot)
        if screenshot_record.get("sha256") != expected_sha256:
            raise ComparisonError(f"{side} page snapshot screenshot SHA-256 does not match")
        raw_components = payload["components"]
        bounds_field = "bounds_px"
    else:
        raise ComparisonError(f"{side} component inventory schema is unsupported")
    if not isinstance(dimensions, dict) or set(dimensions) != {"width", "height"}:
        raise ComparisonError(f"{side} component inventory dimensions are malformed")
    if (
        type(dimensions["width"]) is not int
        or type(dimensions["height"]) is not int
        or (dimensions["width"], dimensions["height"]) != expected_dimensions
    ):
        raise ComparisonError(f"{side} component inventory dimensions do not match the screenshot")
    if not isinstance(raw_components, list) or len(raw_components) > 10000:
        raise ComparisonError(f"{side} component inventory must contain at most 10000 components")

    snapshot_density: float | None = None
    if schema == PAGE_SNAPSHOT_V2_SCHEMA:
        density = viewport.get("density")
        if type(density) not in {int, float} or not math.isfinite(float(density)) or density <= 0:
            raise ComparisonError(f"{side} page snapshot density is malformed")
        snapshot_density = float(density)

    components: list[dict[str, Any]] = []
    component_ids: set[str] = set()
    for raw_component in raw_components:
        if not isinstance(raw_component, dict):
            raise ComparisonError(f"{side} component inventory contains a non-object component")
        if schema in {COMPONENT_SCHEMA, COMPONENT_SCHEMA_V2}:
            if not {"id", "type", bounds_field}.issubset(raw_component) or not set(raw_component).issubset(
                {"id", "type", "semantic_key", bounds_field}
            ):
                raise ComparisonError(f"{side} component inventory contains unsupported component fields")
        elif not {"id", "type", bounds_field}.issubset(raw_component):
            raise ComparisonError(f"{side} page snapshot contains a malformed component")
        component_id = validate_component_token(raw_component["id"], "id")
        component_type = validate_component_token(raw_component["type"], "type")
        if component_id in component_ids:
            raise ComparisonError(f"{side} component inventory contains a duplicate component id")
        component_ids.add(component_id)
        bounds = raw_component[bounds_field]
        if not isinstance(bounds, dict) or set(bounds) != {"x", "y", "width", "height"}:
            raise ComparisonError(f"{side} component bounds are malformed")
        if any(type(bounds[field]) is not int for field in ("x", "y", "width", "height")):
            raise ComparisonError(f"{side} component bounds must be integers")
        if bounds["x"] < 0 or bounds["y"] < 0 or bounds["width"] <= 0 or bounds["height"] <= 0:
            raise ComparisonError(f"{side} component bounds must be positive and non-negative")
        if (
            bounds["x"] + bounds["width"] > expected_dimensions[0]
            or bounds["y"] + bounds["height"] > expected_dimensions[1]
        ):
            raise ComparisonError(f"{side} component bounds exceed screenshot dimensions")
        component = {
            "component_id": component_id,
            "component_type": component_type,
            "bounds": bounds,
        }
        if schema in {PAGE_SNAPSHOT_SCHEMA, PAGE_SNAPSHOT_V2_SCHEMA}:
            bounds_dp = raw_component.get("bounds_dp")
            if not isinstance(bounds_dp, dict) or set(bounds_dp) != {"x", "y", "width", "height"}:
                raise ComparisonError(f"{side} page snapshot component dp bounds are malformed")
            if any(
                type(bounds_dp[field]) not in {int, float}
                or not math.isfinite(float(bounds_dp[field]))
                for field in ("x", "y", "width", "height")
            ):
                raise ComparisonError(f"{side} page snapshot component dp bounds must be finite numbers")
            if bounds_dp["x"] < 0 or bounds_dp["y"] < 0 or bounds_dp["width"] <= 0 or bounds_dp["height"] <= 0:
                raise ComparisonError(f"{side} page snapshot component dp bounds must be positive")
            component["bounds_dp"] = {
                field: round(float(bounds_dp[field]), 3)
                for field in ("x", "y", "width", "height")
            }
        if schema == PAGE_SNAPSHOT_V2_SCHEMA:
            try:
                component["style"] = normalize_style(
                    raw_component.get("style"),
                    f"{side} page snapshot component style",
                )
            except PageSnapshotError as error:
                raise ComparisonError(str(error)) from error
            parent_id = raw_component.get("parent_id")
            if parent_id is not None:
                parent_id = validate_component_token(parent_id, "parent_id")
            children_ids = raw_component.get("children_ids", [])
            if not isinstance(children_ids, list) or len(children_ids) > 10000:
                raise ComparisonError(f"{side} page snapshot component children_ids are malformed")
            normalized_children = [
                validate_component_token(child_id, "children_ids")
                for child_id in children_ids
            ]
            if len(normalized_children) != len(set(normalized_children)):
                raise ComparisonError(f"{side} page snapshot component contains duplicate children_ids")
            sibling_index = raw_component.get("sibling_index", 0)
            if type(sibling_index) is not int or sibling_index < 0:
                raise ComparisonError(f"{side} page snapshot component sibling_index is malformed")
            component.update(
                {
                    "parent_id": parent_id,
                    "children_ids": normalized_children,
                    "sibling_index": sibling_index,
                }
            )
            asset = component["style"]["asset"]
            for axis in ("width", "height"):
                pixel_field = f"{axis}_px"
                logical_field = f"{axis}_dp"
                if asset[logical_field] is None and asset[pixel_field] is not None:
                    asset[logical_field] = round(asset[pixel_field] / snapshot_density, 3)
            try:
                component["provenance"] = normalize_provenance(
                    raw_component.get("provenance"),
                    f"{side} page snapshot component provenance",
                )
                component["unresolved"] = normalize_unresolved(
                    raw_component.get("unresolved"),
                    f"{side} page snapshot component unresolved facts",
                )
            except PageSnapshotError as error:
                raise ComparisonError(str(error)) from error
        if "semantic_key" in raw_component:
            component["semantic_key"] = validate_component_token(
                raw_component["semantic_key"],
                "semantic_key",
            )
        components.append(component)
    if schema == PAGE_SNAPSHOT_V2_SCHEMA:
        by_id = {component["component_id"]: component for component in components}
        for component in components:
            parent_id = component["parent_id"]
            if parent_id is not None and parent_id not in by_id:
                raise ComparisonError(f"{side} page snapshot parent_id references an unknown component")
            if any(child_id not in by_id for child_id in component["children_ids"]):
                raise ComparisonError(f"{side} page snapshot children_ids reference an unknown component")
            component["parent_semantic_key"] = (
                by_id[parent_id].get("semantic_key") if parent_id is not None else None
            )
            component["children_semantic_keys"] = [
                by_id[child_id].get("semantic_key") for child_id in component["children_ids"]
            ]
    record = {
        "side": side,
        "schema": schema,
        "byte_count": path.stat().st_size,
        "sha256": sha256_file(path),
        "component_count": len(components),
    }
    if schema == COMPONENT_SCHEMA_V2:
        raw_insets = payload["content_insets_px"]
        inset_fields = {"left", "top", "right", "bottom"}
        if (
            not isinstance(raw_insets, dict)
            or set(raw_insets) != inset_fields
            or any(
                type(raw_insets[field]) is not int or raw_insets[field] < 0
                for field in inset_fields
            )
            or raw_insets["left"] + raw_insets["right"] >= expected_dimensions[0]
            or raw_insets["top"] + raw_insets["bottom"] >= expected_dimensions[1]
        ):
            raise ComparisonError(f"{side} component inventory content insets are malformed")
        record["content_bounds_px"] = {
            "x": raw_insets["left"],
            "y": raw_insets["top"],
            "width": expected_dimensions[0] - raw_insets["left"] - raw_insets["right"],
            "height": expected_dimensions[1] - raw_insets["top"] - raw_insets["bottom"],
        }
    if schema in {PAGE_SNAPSHOT_SCHEMA, PAGE_SNAPSHOT_V2_SCHEMA}:
        page = payload.get("page")
        if not isinstance(page, dict) or set(page) != {"id", "state"}:
            raise ComparisonError(f"{side} page snapshot page identity is malformed")
        record["page"] = {
            "id": validate_component_token(page["id"], "page.id"),
            "state": validate_component_token(page["state"], "page.state"),
        }
    if schema == PAGE_SNAPSHOT_V2_SCHEMA:
        content_bounds_dp = viewport.get("content_bounds_dp")
        if (
            not isinstance(content_bounds_dp, dict)
            or set(content_bounds_dp) != {"x", "y", "width", "height"}
            or any(
                type(content_bounds_dp[field]) not in {int, float}
                or not math.isfinite(float(content_bounds_dp[field]))
                for field in content_bounds_dp
            )
            or content_bounds_dp["x"] < 0
            or content_bounds_dp["y"] < 0
            or content_bounds_dp["width"] <= 0
            or content_bounds_dp["height"] <= 0
        ):
            raise ComparisonError(f"{side} page snapshot content bounds are malformed")
        content_bounds_px = viewport.get("content_bounds_px")
        if (
            not isinstance(content_bounds_px, dict)
            or set(content_bounds_px) != {"x", "y", "width", "height"}
            or any(type(content_bounds_px[field]) is not int for field in content_bounds_px)
            or content_bounds_px["x"] < 0
            or content_bounds_px["y"] < 0
            or content_bounds_px["width"] <= 0
            or content_bounds_px["height"] <= 0
            or content_bounds_px["x"] + content_bounds_px["width"] > expected_dimensions[0]
            or content_bounds_px["y"] + content_bounds_px["height"] > expected_dimensions[1]
        ):
            raise ComparisonError(f"{side} page snapshot pixel content bounds are malformed")
        orientation = viewport.get("orientation")
        if orientation not in {"portrait", "landscape"}:
            raise ComparisonError(f"{side} page snapshot orientation is malformed")
        font_scale = viewport.get("font_scale")
        if type(font_scale) not in {int, float} or not math.isfinite(float(font_scale)) or font_scale <= 0:
            raise ComparisonError(f"{side} page snapshot font scale is malformed")
        record["viewport"] = {
            "width_dp": viewport.get("width_dp"),
            "height_dp": viewport.get("height_dp"),
            "density": snapshot_density,
            "font_scale": round(float(font_scale), 3),
            "orientation": orientation,
            "content_bounds_dp": {
                field: round(float(content_bounds_dp[field]), 3)
                for field in ("x", "y", "width", "height")
            },
            "content_bounds_px": {
                field: content_bounds_px[field]
                for field in ("x", "y", "width", "height")
            },
        }
        record["runtime_elided_source_components"] = sorted(
            payload.get("runtime_elided_source_components", []),
            key=lambda item: (item["source_semantic_key"], item["source_call_id"]),
        )
        for component in components:
            bounds_dp = component["bounds_dp"]
            component["comparison_bounds_dp"] = {
                "x": round(bounds_dp["x"] - float(content_bounds_dp["x"]), 3),
                "y": round(bounds_dp["y"] - float(content_bounds_dp["y"]), 3),
                "width": bounds_dp["width"],
                "height": bounds_dp["height"],
            }
    business_components = (
        load_business_component_inventory(
            payload.get("source_component_tree"),
            components,
            side,
        )
        if schema == PAGE_SNAPSHOT_V2_SCHEMA
        else []
    )
    record["business_component_count"] = len(business_components)
    return record, components, business_components


def load_business_component_inventory(
    raw_tree: Any,
    runtime_components: list[dict[str, Any]],
    side: str,
) -> list[dict[str, Any]]:
    if raw_tree is None:
        return []
    required_tree_fields = {
        "business_root_ids",
        "business_component_ids",
        "components",
    }
    allowed_tree_fields = required_tree_fields | {
        "schema",
        "root_ids",
        "definitions",
        "layout_relationships",
        "third_party_component_ids",
    }
    if (
        not isinstance(raw_tree, dict)
        or not required_tree_fields.issubset(raw_tree)
        or not set(raw_tree).issubset(allowed_tree_fields)
    ):
        raise ComparisonError(f"{side} source component tree is malformed")
    raw_components = raw_tree["components"]
    business_ids = raw_tree["business_component_ids"]
    business_root_ids = raw_tree["business_root_ids"]
    if (
        not isinstance(raw_components, list)
        or len(raw_components) > 10000
        or not isinstance(business_ids, list)
        or len(business_ids) > 10000
        or not isinstance(business_root_ids, list)
        or len(business_root_ids) > 10000
    ):
        raise ComparisonError(f"{side} source component tree lists are malformed")
    normalized_business_ids = [
        validate_component_token(value, "business_component_ids")
        for value in business_ids
    ]
    normalized_root_ids = [
        validate_component_token(value, "business_root_ids")
        for value in business_root_ids
    ]
    if (
        len(normalized_business_ids) != len(set(normalized_business_ids))
        or len(normalized_root_ids) != len(set(normalized_root_ids))
    ):
        raise ComparisonError(f"{side} source component tree contains duplicate ids")

    source_by_id: dict[str, dict[str, Any]] = {}
    for raw_component in raw_components:
        required_component_fields = {
            "id",
            "semantic_key",
            "type",
            "component_kind",
            "node_kind",
            "business_parent_id",
            "business_children_ids",
            "runtime_instances",
            "runtime_descendant_ids",
            "source",
        }
        if (
            not isinstance(raw_component, dict)
            or not required_component_fields.issubset(raw_component)
        ):
            raise ComparisonError(f"{side} source component tree contains a malformed component")
        source_id = validate_component_token(raw_component["id"], "source component id")
        if source_id in source_by_id:
            raise ComparisonError(f"{side} source component tree contains duplicate components")
        source_by_id[source_id] = raw_component
    if any(source_id not in source_by_id for source_id in normalized_business_ids):
        raise ComparisonError(f"{side} business component id is missing from the source tree")
    if any(source_id not in source_by_id for source_id in normalized_root_ids):
        raise ComparisonError(f"{side} business root id is missing from the source tree")

    runtime_by_id = {
        component["component_id"]: component for component in runtime_components
    }

    def source_subtree_ids(root_id: str) -> list[str]:
        pending = [root_id]
        visited: set[str] = set()
        ordered: list[str] = []
        while pending:
            current = pending.pop()
            if current in visited or current not in source_by_id:
                continue
            visited.add(current)
            ordered.append(current)
            children = source_by_id[current].get("children_ids", [])
            if isinstance(children, list):
                pending.extend(
                    child_id for child_id in reversed(children) if isinstance(child_id, str)
                )
        return ordered

    def reliable_runtime_anchors(root_id: str) -> list[str]:
        anchors: list[str] = []
        reliable_methods = {
            "exact_text",
            "exact_content_description",
            "explicit_runtime_source_map",
            "stable_runtime_id",
        }
        for source_descendant_id in source_subtree_ids(root_id):
            source_descendant = source_by_id[source_descendant_id]
            instances = source_descendant.get("runtime_instances", [])
            if not isinstance(instances, list):
                continue
            for instance in instances:
                if not isinstance(instance, dict):
                    continue
                runtime_id = instance.get("runtime_component_id")
                method = instance.get("mapping_method")
                if runtime_id in runtime_by_id and method in reliable_methods:
                    anchors.append(runtime_id)
        return list(dict.fromkeys(anchors))

    def runtime_control_boundary(runtime_id: str) -> str:
        current = runtime_by_id[runtime_id]
        parent_id = current.get("parent_id")
        if parent_id is None or parent_id not in runtime_by_id:
            return runtime_id
        parent = runtime_by_id[parent_id]
        current_area = current["bounds"]["width"] * current["bounds"]["height"]
        parent_area = parent["bounds"]["width"] * parent["bounds"]["height"]
        if parent_area / current_area <= 20:
            return parent_id
        return runtime_id

    def union_bounds(components: list[dict[str, Any]]) -> dict[str, int]:
        left = min(component["bounds"]["x"] for component in components)
        top = min(component["bounds"]["y"] for component in components)
        right = max(
            component["bounds"]["x"] + component["bounds"]["width"]
            for component in components
        )
        bottom = max(
            component["bounds"]["y"] + component["bounds"]["height"]
            for component in components
        )
        return {
            "x": left,
            "y": top,
            "width": right - left,
            "height": bottom - top,
        }

    def union_bounds_dp(components: list[dict[str, Any]]) -> dict[str, float]:
        bounds = [
            component.get("comparison_bounds_dp", component.get("bounds_dp"))
            for component in components
        ]
        bounds = [item for item in bounds if isinstance(item, dict)]
        left = min(float(item["x"]) for item in bounds)
        top = min(float(item["y"]) for item in bounds)
        right = max(float(item["x"]) + float(item["width"]) for item in bounds)
        bottom = max(float(item["y"]) + float(item["height"]) for item in bounds)
        return {
            "x": round(left, 3),
            "y": round(top, 3),
            "width": round(right - left, 3),
            "height": round(bottom - top, 3),
        }

    def source_record(raw_source: Any) -> dict[str, Any] | None:
        if not isinstance(raw_source, dict):
            return None
        source_path = raw_source.get("source")
        composable = raw_source.get("composable")
        line = raw_source.get("line")
        if (
            not isinstance(source_path, str)
            or not isinstance(composable, str)
            or type(line) is not int
            or line <= 0
        ):
            return None
        return {
            "path": validate_source_path(source_path),
            "line": line,
            "composable": validate_component_token(composable, "source composable"),
        }

    def owned_visual_controls(owner_id: str) -> list[dict[str, Any]]:
        controls: list[dict[str, Any]] = []
        for source_component in raw_components:
            if (
                source_component.get("id") == owner_id
                or source_component.get("business_owner_id") != owner_id
                or source_component.get("component_kind")
                in {"project_component", "third_party_component"}
                or source_component.get("node_kind")
                in {"layout_primitive", "content_slot"}
            ):
                continue
            semantic_key = source_component.get("semantic_key")
            component_type = source_component.get("type")
            if not isinstance(semantic_key, str) or not isinstance(component_type, str):
                continue
            controls.append(
                {
                    "semantic_key": validate_component_token(
                        semantic_key, "control semantic_key"
                    ),
                    "component_type": validate_component_token(
                        component_type, "control component type"
                    ),
                    "source": source_record(source_component.get("source")),
                }
            )
        return sorted(controls, key=lambda item: item["semantic_key"])

    result: list[dict[str, Any]] = []
    for source_id in normalized_business_ids:
        raw_component = source_by_id[source_id]
        component_kind = raw_component["component_kind"]
        if component_kind not in {"project_component", "third_party_component"}:
            continue
        semantic_key = validate_component_token(
            raw_component["semantic_key"], "business semantic_key"
        )
        component_type = validate_component_token(
            raw_component["type"], "business component type"
        )
        parent_id = raw_component["business_parent_id"]
        if parent_id is not None:
            parent_id = validate_component_token(parent_id, "business_parent_id")
            if parent_id not in source_by_id:
                raise ComparisonError(f"{side} business parent id is unknown")
        raw_children = raw_component["business_children_ids"]
        if not isinstance(raw_children, list) or len(raw_children) > 10000:
            raise ComparisonError(f"{side} business children ids are malformed")
        child_ids = [
            validate_component_token(value, "business_children_ids")
            for value in raw_children
        ]
        if any(child_id not in source_by_id for child_id in child_ids):
            raise ComparisonError(f"{side} business child id is unknown")

        raw_instances = raw_component["runtime_instances"]
        if not isinstance(raw_instances, list) or len(raw_instances) > 10000:
            raise ComparisonError(f"{side} business runtime instances are malformed")
        direct_ids: list[str] = []
        for instance in raw_instances:
            if (
                not isinstance(instance, dict)
                or not isinstance(instance.get("runtime_component_id"), str)
                or instance.get("mapping_status") not in {"proven", "candidate"}
            ):
                raise ComparisonError(f"{side} business runtime instance is malformed")
            runtime_id = validate_component_token(
                instance["runtime_component_id"], "runtime_component_id"
            )
            if runtime_id in runtime_by_id:
                direct_ids.append(runtime_id)
        raw_descendant_ids = raw_component["runtime_descendant_ids"]
        if not isinstance(raw_descendant_ids, list) or len(raw_descendant_ids) > 10000:
            raise ComparisonError(f"{side} business runtime descendants are malformed")
        descendant_ids = [
            validate_component_token(value, "runtime_descendant_ids")
            for value in raw_descendant_ids
            if isinstance(value, str)
        ]
        anchor_roots = child_ids or [source_id]
        anchor_groups = [reliable_runtime_anchors(root_id) for root_id in anchor_roots]
        reliable_anchors = (
            list(dict.fromkeys(runtime_id for group in anchor_groups for runtime_id in group))
            if all(anchor_groups)
            else []
        )
        boundary_ids = list(dict.fromkeys(
            runtime_control_boundary(runtime_id) for runtime_id in reliable_anchors
        ))
        descendant_matches = [
            runtime_id for runtime_id in descendant_ids if runtime_id in runtime_by_id
        ]
        if direct_ids:
            mapped_ids = direct_ids
            runtime_mapping = "direct_runtime_instance"
        elif boundary_ids:
            mapped_ids = boundary_ids
            runtime_mapping = "semantic_anchor_parent"
        elif descendant_matches:
            mapped_ids = descendant_matches
            runtime_mapping = "runtime_descendant_union"
        else:
            mapped_ids = []
            runtime_mapping = "unavailable"
        mapped_components = [runtime_by_id[runtime_id] for runtime_id in mapped_ids]
        result.append(
            {
                "source_component_id": source_id,
                "semantic_key": semantic_key,
                "component_type": component_type,
                "component_kind": component_kind,
                "business_parent_semantic_key": (
                    source_by_id[parent_id]["semantic_key"] if parent_id is not None else None
                ),
                "business_children_semantic_keys": [
                    source_by_id[child_id]["semantic_key"] for child_id in child_ids
                ],
                "bounds": union_bounds(mapped_components) if mapped_components else None,
                "bounds_dp": (
                    union_bounds_dp(mapped_components) if mapped_components else None
                ),
                "runtime_component_ids": mapped_ids,
                "runtime_mapping": runtime_mapping,
                "source": source_record(raw_component["source"]),
                "controls": owned_visual_controls(source_id),
            }
        )
    return result


def validate_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ComparisonError(f"source attribute {field} must be a lowercase SHA-256")
    return value


def validate_source_path(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 400
        or re.fullmatch(r"[A-Za-z0-9._/@#:+-]+", value) is None
        or value.startswith("/")
        or ".." in Path(value).parts
    ):
        raise ComparisonError("source attribute source must be a safe relative identifier path")
    return value


def load_source_attribute_inventory(
    requested_path: Path | None,
) -> tuple[dict[str, Any] | None, dict[str, dict[str, Any]]]:
    if requested_path is None:
        return None, {}
    path = resolve_source_attribute_input(requested_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ComparisonError("source attribute inventory is not valid UTF-8 JSON") from error
    expected_root_fields = {
        "schema",
        "status",
        "authoritative",
        "root",
        "contract_sha256",
        "semantic_input_sha256",
        "components",
        "limitations",
    }
    if not isinstance(payload, dict) or set(payload) != expected_root_fields:
        raise ComparisonError("source attribute inventory has unsupported root fields")
    if payload["schema"] != SOURCE_ATTRIBUTE_SCHEMA:
        raise ComparisonError("source attribute inventory schema is unsupported")
    if payload["status"] != "candidate_requires_review" or payload["authoritative"] is not False:
        raise ComparisonError("source attribute inventory must remain a non-authoritative candidate")
    root = payload["root"]
    if not isinstance(root, dict) or set(root) != {"source", "composable"}:
        raise ComparisonError("source attribute inventory root is malformed")
    validate_source_path(root["source"])
    validate_component_token(root["composable"], "composable")
    validate_sha256(payload["contract_sha256"], "contract_sha256")
    validate_sha256(payload["semantic_input_sha256"], "semantic_input_sha256")
    limitations = payload["limitations"]
    if not isinstance(limitations, list) or not all(
        isinstance(item, str) and 1 <= len(item) <= 400 for item in limitations
    ):
        raise ComparisonError("source attribute inventory limitations are malformed")
    raw_components = payload["components"]
    if not isinstance(raw_components, list) or len(raw_components) > 10000:
        raise ComparisonError("source attribute inventory must contain at most 10000 components")
    components: dict[str, dict[str, Any]] = {}
    attribute_count = 0
    allowed_groups = {
        "asset",
        "behavior",
        "color",
        "component_semantics",
        "content",
        "geometry",
        "state",
        "surface",
        "transform",
        "typography",
    }
    allowed_origins = {
        "call_site",
        "invocation_argument",
        "modifier",
        "positional_argument",
        "semantic_argument",
        "state_slot",
    }
    required_attribute_fields = {
        "call_id",
        "line",
        "component",
        "origin",
        "name",
        "groups",
        "dimensions",
        "dimension_resources",
    }
    for raw_component in raw_components:
        required_component_fields = {
            "semantic_key",
            "source",
            "composable",
            "attributes",
        }
        optional_component_fields = {"source_hierarchy", "resolved_visual_geometry"}
        if (
            not isinstance(raw_component, dict)
            or not required_component_fields.issubset(raw_component)
            or not set(raw_component).issubset(required_component_fields | optional_component_fields)
        ):
            raise ComparisonError("source attribute inventory contains unsupported component fields")
        semantic_key = validate_component_token(raw_component["semantic_key"], "semantic_key")
        if semantic_key in components:
            raise ComparisonError("source attribute inventory contains a duplicate semantic key")
        source = validate_source_path(raw_component["source"])
        composable = validate_component_token(raw_component["composable"], "composable")
        raw_attributes = raw_component["attributes"]
        if not isinstance(raw_attributes, list) or len(raw_attributes) > 50000:
            raise ComparisonError("source component must contain at most 50000 attributes")
        attributes: list[dict[str, Any]] = []
        for raw_attribute in raw_attributes:
            if (
                not isinstance(raw_attribute, dict)
                or not required_attribute_fields.issubset(raw_attribute)
                or not set(raw_attribute).issubset(required_attribute_fields | {"modifier_index"})
            ):
                raise ComparisonError("source attribute inventory contains unsupported attribute fields")
            call_id = raw_attribute["call_id"]
            if not isinstance(call_id, str) or re.fullmatch(r"[A-Za-z0-9._/@#:+-]{1,600}", call_id) is None:
                raise ComparisonError("source attribute call_id is malformed")
            line = raw_attribute["line"]
            if type(line) is not int or line <= 0:
                raise ComparisonError("source attribute line must be a positive integer")
            component = validate_component_token(raw_attribute["component"], "component")
            origin = raw_attribute["origin"]
            if origin not in allowed_origins:
                raise ComparisonError("source attribute origin is unsupported")
            name = raw_attribute["name"]
            if not isinstance(name, str) or re.fullmatch(r"(?:[A-Za-z_][A-Za-z0-9_]*|position_[0-9]+)", name) is None:
                raise ComparisonError("source attribute name is malformed")
            groups = raw_attribute["groups"]
            if (
                not isinstance(groups, list)
                or not groups
                or groups != sorted(set(groups))
                or any(group not in allowed_groups for group in groups)
            ):
                raise ComparisonError("source attribute groups are malformed")
            dimensions = raw_attribute["dimensions"]
            if not isinstance(dimensions, list):
                raise ComparisonError("source attribute dimensions are malformed")
            sanitized_dimensions: list[dict[str, str]] = []
            for dimension in dimensions:
                if (
                    not isinstance(dimension, dict)
                    or set(dimension) != {"value", "unit"}
                    or not isinstance(dimension.get("value"), str)
                    or re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", dimension["value"]) is None
                    or dimension.get("unit") not in {"dp", "sp"}
                ):
                    raise ComparisonError("source attribute dimension is malformed")
                sanitized_dimensions.append(dimension)
            resources = raw_attribute["dimension_resources"]
            if not isinstance(resources, list) or any(
                not isinstance(item, str)
                or re.fullmatch(r"[A-Za-z0-9._:/#@-]{1,240}", item) is None
                for item in resources
            ):
                raise ComparisonError("source attribute dimension resources are malformed")
            attribute = {
                "call_id": call_id,
                "line": line,
                "component": component,
                "origin": origin,
                "name": name,
                "groups": groups,
                "dimensions": sanitized_dimensions,
                "dimension_resources": resources,
            }
            if "modifier_index" in raw_attribute:
                modifier_index = raw_attribute["modifier_index"]
                if type(modifier_index) is not int or modifier_index < 0 or origin != "modifier":
                    raise ComparisonError("source attribute modifier_index is malformed")
                attribute["modifier_index"] = modifier_index
            attributes.append(attribute)
        attribute_count += len(attributes)
        component_record: dict[str, Any] = {
            "semantic_key": semantic_key,
            "source": source,
            "composable": composable,
            "attributes": attributes,
        }
        hierarchy = raw_component.get("source_hierarchy")
        if hierarchy is not None:
            if not isinstance(hierarchy, dict) or set(hierarchy) != {
                "parent_semantic_key", "preorder_index", "mapping"
            }:
                raise ComparisonError("source attribute hierarchy is malformed")
            parent = hierarchy["parent_semantic_key"]
            if parent is not None:
                parent = validate_component_token(parent, "parent_semantic_key")
            preorder = hierarchy["preorder_index"]
            if type(preorder) is not int or preorder < 0:
                raise ComparisonError("source attribute hierarchy preorder is malformed")
            mapping = hierarchy["mapping"]
            if mapping not in {"resolved_static_call_graph", "ambiguous_runtime_fallback"}:
                raise ComparisonError("source attribute hierarchy mapping is unsupported")
            component_record["source_hierarchy"] = {
                "parent_semantic_key": parent,
                "preorder_index": preorder,
                "mapping": mapping,
            }
        geometry = raw_component.get("resolved_visual_geometry")
        if geometry is not None:
            if not isinstance(geometry, dict) or set(geometry) != {"layout", "transform"}:
                raise ComparisonError("source resolved visual geometry is malformed")
            layout = geometry["layout"]
            transform = geometry["transform"]
            if (
                not isinstance(layout, dict)
                or not set(layout).issubset({"width_dp", "height_dp"})
                or not isinstance(transform, dict)
                or not set(transform).issubset({
                    "translation_x_dp", "translation_y_dp", "scale_x", "scale_y", "rotation_degrees"
                })
                or any(type(value) not in {int, float} or not math.isfinite(float(value)) for value in [*layout.values(), *transform.values()])
            ):
                raise ComparisonError("source resolved visual geometry is malformed")
            component_record["resolved_visual_geometry"] = geometry
        components[semantic_key] = component_record
    record = {
        "schema": SOURCE_ATTRIBUTE_SCHEMA,
        "byte_count": path.stat().st_size,
        "sha256": sha256_file(path),
        "component_count": len(components),
        "attribute_count": attribute_count,
        "contract_sha256": payload["contract_sha256"],
        "semantic_input_sha256": payload["semantic_input_sha256"],
    }
    return record, components


def require_pillow() -> None:
    if Image is None:
        raise ComparisonError(
            "Pillow is required; install it with 'python3 -m pip install Pillow'"
        )


def load_image(path: Path, label: str) -> Any:
    try:
        with Image.open(path) as opened:
            opened.load()
            oriented = ImageOps.exif_transpose(opened)
            if oriented.width <= 0 or oriented.height <= 0:
                raise ComparisonError(f"{label} screenshot dimensions are invalid")
            return oriented.convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ComparisonError(f"{label} screenshot is not a decodable image") from error


def parse_crop(value: str | None, width: int, height: int, label: str) -> tuple[int, int, int, int]:
    if value is None:
        return 0, 0, width, height
    match = re.fullmatch(r"([0-9]+),([0-9]+),([0-9]+),([0-9]+)", value)
    if match is None:
        raise ComparisonError(f"{label} crop must use x,y,width,height")
    x, y, crop_width, crop_height = (int(item) for item in match.groups())
    if crop_width <= 0 or crop_height <= 0:
        raise ComparisonError(f"{label} crop width and height must be positive")
    if x + crop_width > width or y + crop_height > height:
        raise ComparisonError(f"{label} crop exceeds screenshot bounds")
    return x, y, crop_width, crop_height


def select_crop(
    value: str | None,
    width: int,
    height: int,
    label: str,
    component_record: dict[str, Any] | None,
) -> tuple[tuple[int, int, int, int], str]:
    if value is not None:
        return parse_crop(value, width, height, label), "explicit"
    viewport = component_record.get("viewport") if component_record else None
    if isinstance(viewport, dict) and isinstance(viewport.get("content_bounds_px"), dict):
        content = viewport["content_bounds_px"]
        return (
            content["x"], content["y"], content["width"], content["height"]
        ), "page_snapshot_content_bounds"
    if component_record and isinstance(component_record.get("content_bounds_px"), dict):
        content = component_record["content_bounds_px"]
        return (
            content["x"], content["y"], content["width"], content["height"]
        ), "component_inventory_content_bounds"
    return (0, 0, width, height), "full_image"


def parse_target_size(value: str | None, default: tuple[int, int]) -> tuple[int, int]:
    if value is None:
        return default
    match = re.fullmatch(r"([1-9][0-9]*)x([1-9][0-9]*)", value)
    if match is None:
        raise ComparisonError("target size must use widthxheight")
    return int(match.group(1)), int(match.group(2))


def normalize(
    source: Any,
    crop: tuple[int, int, int, int],
    target: tuple[int, int],
) -> Any:
    x, y, width, height = crop
    cropped = source.crop((x, y, x + width, y + height))
    if cropped.size == target:
        return cropped
    resized = cropped.resize(target, Image.Resampling.LANCZOS)
    cropped.close()
    return resized


def flattened_pixels(image: Any) -> Any:
    modern_getter = getattr(image, "get_flattened_data", None)
    return modern_getter() if modern_getter is not None else image.getdata()


def channel_ssim(left: Any, right: Any, tile_size: int = 64) -> float:
    if ImageChops.difference(left, right).getbbox() is None:
        return 1.0
    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2
    weighted_score = 0.0
    total_pixels = left.width * left.height
    for y in range(0, left.height, tile_size):
        for x in range(0, left.width, tile_size):
            bounds = (x, y, min(x + tile_size, left.width), min(y + tile_size, left.height))
            left_tile = left.crop(bounds)
            right_tile = right.crop(bounds)
            left_stats = ImageStat.Stat(left_tile)
            right_stats = ImageStat.Stat(right_tile)
            left_pixels = flattened_pixels(left_tile)
            right_pixels = flattened_pixels(right_tile)
            area = (bounds[2] - bounds[0]) * (bounds[3] - bounds[1])
            left_mean = left_stats.mean[0]
            right_mean = right_stats.mean[0]
            product_mean = sum(
                left_value * right_value
                for left_value, right_value in zip(left_pixels, right_pixels, strict=True)
            ) / area
            covariance = product_mean - left_mean * right_mean
            numerator = (2 * left_mean * right_mean + c1) * (2 * covariance + c2)
            denominator = (
                (left_mean * left_mean + right_mean * right_mean + c1)
                * (left_stats.var[0] + right_stats.var[0] + c2)
            )
            score = numerator / denominator if denominator else 1.0
            weighted_score += max(-1.0, min(1.0, score)) * area
    return round(weighted_score / total_pixels, 6)


def image_ssim(left: Any, right: Any) -> float:
    scores = [
        channel_ssim(left_channel, right_channel)
        for left_channel, right_channel in zip(left.split(), right.split(), strict=True)
    ]
    return round(sum(scores) / len(scores), 6)


def normalized_component_bounds(
    bounds: dict[str, int],
    crop: tuple[int, int, int, int],
    target: tuple[int, int],
) -> dict[str, int] | None:
    crop_x, crop_y, crop_width, crop_height = crop
    left = max(bounds["x"], crop_x)
    top = max(bounds["y"], crop_y)
    right = min(bounds["x"] + bounds["width"], crop_x + crop_width)
    bottom = min(bounds["y"] + bounds["height"], crop_y + crop_height)
    if left >= right or top >= bottom:
        return None
    normalized_left = max(0, math.floor((left - crop_x) * target[0] / crop_width))
    normalized_top = max(0, math.floor((top - crop_y) * target[1] / crop_height))
    normalized_right = min(
        target[0], math.ceil((right - crop_x) * target[0] / crop_width)
    )
    normalized_bottom = min(
        target[1], math.ceil((bottom - crop_y) * target[1] / crop_height)
    )
    if normalized_left >= normalized_right or normalized_top >= normalized_bottom:
        return None
    return {
        "x": normalized_left,
        "y": normalized_top,
        "width": normalized_right - normalized_left,
        "height": normalized_bottom - normalized_top,
    }


def bounds_iou(left: dict[str, int], right: dict[str, int]) -> float:
    intersection_width = max(
        0,
        min(left["x"] + left["width"], right["x"] + right["width"])
        - max(left["x"], right["x"]),
    )
    intersection_height = max(
        0,
        min(left["y"] + left["height"], right["y"] + right["height"])
        - max(left["y"], right["y"]),
    )
    intersection = intersection_width * intersection_height
    union = (
        left["width"] * left["height"]
        + right["width"] * right["height"]
        - intersection
    )
    return intersection / union if union else 0.0


def detect_visual_surface_candidates(image: Any) -> list[dict[str, Any]]:
    """Locate large visible surfaces without assigning semantic ownership."""
    analysis_scale = min(1.0, 480 / image.width)
    analysis_size = (
        max(1, round(image.width * analysis_scale)),
        max(1, round(image.height * analysis_scale)),
    )
    analysis = image.resize(analysis_size, Image.Resampling.BILINEAR)
    quantized = analysis.quantize(
        colors=32,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )
    width, height = quantized.size
    pixels = quantized.tobytes()
    palette = quantized.getpalette()
    parents: list[int] = []
    stats: list[list[int]] = []
    previous_runs: dict[int, list[tuple[int, int, int]]] = {}

    def create_label(color: int, left: int, right: int, top: int) -> int:
        label = len(parents)
        parents.append(label)
        stats.append([color, left, top, right, top, right - left])
        return label

    def find(label: int) -> int:
        while parents[label] != label:
            parents[label] = parents[parents[label]]
            label = parents[label]
        return label

    def union(left_label: int, right_label: int) -> int:
        left_root = find(left_label)
        right_root = find(right_label)
        if left_root == right_root:
            return left_root
        parents[right_root] = left_root
        left_stats = stats[left_root]
        right_stats = stats[right_root]
        left_stats[1] = min(left_stats[1], right_stats[1])
        left_stats[2] = min(left_stats[2], right_stats[2])
        left_stats[3] = max(left_stats[3], right_stats[3])
        left_stats[4] = max(left_stats[4], right_stats[4])
        left_stats[5] += right_stats[5]
        return left_root

    for y in range(height):
        row = pixels[y * width:(y + 1) * width]
        current_runs: dict[int, list[tuple[int, int, int]]] = {}
        x = 0
        while x < width:
            color = row[x]
            start = x
            x += 1
            while x < width and row[x] == color:
                x += 1
            label = create_label(color, start, x, y)
            for previous_left, previous_right, previous_label in previous_runs.get(
                color, []
            ):
                if previous_left <= x and previous_right >= start:
                    label = union(label, previous_label)
            current_runs.setdefault(color, []).append((start, x, label))
        previous_runs = current_runs

    candidates: list[dict[str, Any]] = []
    for root in {find(label) for label in range(len(parents))}:
        color_index, left, top, right, bottom, pixel_count = stats[root]
        candidate_width = right - left
        candidate_height = bottom - top + 1
        area = candidate_width * candidate_height
        fill_ratio = pixel_count / area
        if (
            candidate_width < width * 0.15
            or candidate_height < max(6, height * 0.008)
            or fill_ratio < 0.25
            or (candidate_width > width * 0.95 and candidate_height > height * 0.85)
        ):
            continue
        bounds = {
            "x": max(0, round(left / analysis_scale)),
            "y": max(0, round(top / analysis_scale)),
            "width": min(image.width, round(candidate_width / analysis_scale)),
            "height": min(image.height, round(candidate_height / analysis_scale)),
        }
        bounds["width"] = min(bounds["width"], image.width - bounds["x"])
        bounds["height"] = min(bounds["height"], image.height - bounds["y"])
        candidates.append(
            {
                "bounds": bounds,
                "fill_ratio": round(fill_ratio, 6),
                "color_rgb": palette[color_index * 3:color_index * 3 + 3],
                "method": "pillow_quantized_connected_surface_v1",
            }
        )

    # Decorative images can interrupt a full-width surface. Merge only fragments
    # that jointly touch both screen edges; separate cards remain separate.
    merged_indexes: set[int] = set()
    merged_candidates: list[dict[str, Any]] = []
    for left_index, left_candidate in enumerate(candidates):
        if left_index in merged_indexes:
            continue
        left_bounds = left_candidate["bounds"]
        if left_bounds["x"] > image.width * 0.02:
            continue
        best: tuple[float, int, dict[str, Any]] | None = None
        for right_index, right_candidate in enumerate(candidates):
            if right_index == left_index or right_index in merged_indexes:
                continue
            right_bounds = right_candidate["bounds"]
            if right_bounds["x"] + right_bounds["width"] < image.width * 0.98:
                continue
            overlap = max(
                0,
                min(
                    left_bounds["y"] + left_bounds["height"],
                    right_bounds["y"] + right_bounds["height"],
                ) - max(left_bounds["y"], right_bounds["y"]),
            )
            overlap_ratio = overlap / min(
                left_bounds["height"], right_bounds["height"]
            )
            gap = right_bounds["x"] - (left_bounds["x"] + left_bounds["width"])
            color_delta = max(
                abs(int(left_candidate["color_rgb"][index]) - int(right_candidate["color_rgb"][index]))
                for index in range(3)
            )
            if overlap_ratio < 0.6 or gap < 0 or gap > image.width * 0.1 or color_delta > 8:
                continue
            score = overlap_ratio - gap / image.width
            if best is None or score > best[0]:
                best = (score, right_index, right_candidate)
        if best is None:
            continue
        _, right_index, right_candidate = best
        right_bounds = right_candidate["bounds"]
        top = min(left_bounds["y"], right_bounds["y"])
        bottom = max(
            left_bounds["y"] + left_bounds["height"],
            right_bounds["y"] + right_bounds["height"],
        )
        merged_candidates.append(
            {
                "bounds": {
                    "x": 0,
                    "y": top,
                    "width": image.width,
                    "height": bottom - top,
                },
                "fill_ratio": round(
                    (
                        left_candidate["fill_ratio"]
                        * left_bounds["width"]
                        * left_bounds["height"]
                        + right_candidate["fill_ratio"]
                        * right_bounds["width"]
                        * right_bounds["height"]
                    )
                    / (image.width * (bottom - top)),
                    6,
                ),
                "color_rgb": left_candidate["color_rgb"],
                "method": "pillow_quantized_connected_surface_v1_edge_merge",
            }
        )
        merged_indexes.update({left_index, right_index})
    candidates.extend(merged_candidates)
    return sorted(
        candidates,
        key=lambda item: item["bounds"]["width"] * item["bounds"]["height"],
        reverse=True,
    )


def visual_surface_for_runtime_bounds(
    candidates: list[dict[str, Any]],
    runtime_bounds: dict[str, int],
) -> tuple[dict[str, Any], float] | None:
    scored = [
        (bounds_iou(candidate["bounds"], runtime_bounds), candidate)
        for candidate in candidates
    ]
    score, candidate = max(scored, default=(0.0, None), key=lambda item: item[0])
    if candidate is None or score < 0.6:
        return None
    return candidate, round(score, 6)


def matching_visual_surface(
    reference: dict[str, Any],
    candidates: list[dict[str, Any]],
    image_size: tuple[int, int],
) -> tuple[dict[str, Any], float] | None:
    reference_bounds = reference["bounds"]
    reference_center = (
        reference_bounds["x"] + reference_bounds["width"] / 2,
        reference_bounds["y"] + reference_bounds["height"] / 2,
    )
    matches: list[tuple[float, dict[str, Any]]] = []
    for candidate in candidates:
        bounds = candidate["bounds"]
        width_ratio = bounds["width"] / reference_bounds["width"]
        height_ratio = bounds["height"] / reference_bounds["height"]
        if not 0.72 <= width_ratio <= 1.28 or not 0.65 <= height_ratio <= 1.35:
            continue
        size_error = abs(math.log(width_ratio)) + abs(math.log(height_ratio))
        center = (bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2)
        position_error = math.hypot(
            (center[0] - reference_center[0]) / image_size[0],
            (center[1] - reference_center[1]) / image_size[1],
        )
        aspect_error = abs(
            math.log(
                (bounds["width"] / bounds["height"])
                / (reference_bounds["width"] / reference_bounds["height"])
            )
        )
        error = size_error + aspect_error + position_error * 0.35
        confidence = max(0.0, 1.0 - error / 1.2)
        if confidence >= 0.7:
            matches.append((confidence, candidate))
    if not matches:
        return None
    confidence, candidate = max(matches, key=lambda item: item[0])
    return candidate, round(confidence, 6)


def local_similarity(
    left_rgb: Any,
    right_rgb: Any,
    max_side: int = 320,
) -> dict[str, Any]:
    analysis_width = max(left_rgb.width, right_rgb.width)
    analysis_height = max(left_rgb.height, right_rgb.height)
    scale = min(1.0, max_side / max(analysis_width, analysis_height))
    analysis_size = (
        max(1, round(analysis_width * scale)),
        max(1, round(analysis_height * scale)),
    )
    if left_rgb.size != analysis_size:
        left_rgb = left_rgb.resize(analysis_size, Image.Resampling.LANCZOS)
    if right_rgb.size != analysis_size:
        right_rgb = right_rgb.resize(analysis_size, Image.Resampling.LANCZOS)
    left_tolerant = left_rgb.filter(
        ImageFilter.GaussianBlur(RASTERIZATION_TOLERANCE_RADIUS_PX)
    )
    right_tolerant = right_rgb.filter(
        ImageFilter.GaussianBlur(RASTERIZATION_TOLERANCE_RADIUS_PX)
    )
    metrics = {
        "ssim_color": image_ssim(left_tolerant, right_tolerant),
        "ssim_luma": channel_ssim(
            left_tolerant.convert("L"), right_tolerant.convert("L")
        ),
        "ssim_edges": channel_ssim(
            left_rgb.convert("L")
            .filter(ImageFilter.FIND_EDGES)
            .filter(ImageFilter.GaussianBlur(EDGE_TOLERANCE_RADIUS_PX)),
            right_rgb.convert("L")
            .filter(ImageFilter.FIND_EDGES)
            .filter(ImageFilter.GaussianBlur(EDGE_TOLERANCE_RADIUS_PX)),
        ),
    }
    magnitude = max_channel_difference(ImageChops.difference(left_rgb, right_rgb))
    changed_mask = magnitude.point(
        lambda value: 255 if value >= 16 else 0,
        mode="L",
    )
    return {
        "analysis_size_px": {
            "width": analysis_size[0],
            "height": analysis_size[1],
        },
        "metrics": metrics,
        "ssim_score": round(min(metrics.values()), 6),
        "changed_pixel_ratio": round(
            changed_pixel_count(changed_mask) / (analysis_size[0] * analysis_size[1]),
            6,
        ),
    }


def business_component_ssim_rankings(
    left_rgb: Any,
    right_rgb: Any,
    left_business_components: list[dict[str, Any]],
    right_business_components: list[dict[str, Any]],
    left_crop: tuple[int, int, int, int],
    right_crop: tuple[int, int, int, int],
    target: tuple[int, int],
) -> list[dict[str, Any]]:
    def unique_by_semantic_key(
        components: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for component in components:
            grouped.setdefault(component["semantic_key"], []).append(component)
        return {
            semantic_key: matches[0]
            for semantic_key, matches in grouped.items()
            if len(matches) == 1
        }

    left_by_key = unique_by_semantic_key(left_business_components)
    right_by_key = unique_by_semantic_key(right_business_components)
    shared_semantic_keys = sorted(set(left_by_key) & set(right_by_key))
    if not shared_semantic_keys:
        return []
    left_surface_candidates = detect_visual_surface_candidates(left_rgb)
    right_surface_candidates = detect_visual_surface_candidates(right_rgb)
    left_density_samples = [
        float(component["bounds"]["width"]) / float(component["bounds_dp"]["width"])
        for component in left_business_components
        if component["bounds"] is not None
        and component["bounds_dp"] is not None
        and float(component["bounds_dp"]["width"]) > 0
    ]
    target_pixels_per_dp_global = (
        sorted(left_density_samples)[len(left_density_samples) // 2]
        * target[0]
        / left_crop[2]
        if left_density_samples
        else None
    )
    full_area = target[0] * target[1]
    rankings: list[dict[str, Any]] = []
    for semantic_key in shared_semantic_keys:
        left_component = left_by_key[semantic_key]
        right_component = right_by_key[semantic_key]
        left_input_bounds = left_component["bounds"]
        right_input_bounds = right_component["bounds"]
        left_input_bounds_dp = left_component["bounds_dp"]
        right_input_bounds_dp = right_component["bounds_dp"]
        left_bounds = (
            normalized_component_bounds(left_input_bounds, left_crop, target)
            if left_input_bounds is not None
            else None
        )
        right_bounds = (
            normalized_component_bounds(right_input_bounds, right_crop, target)
            if right_input_bounds is not None
            else None
        )
        mapping_pair = {
            left_component["runtime_mapping"], right_component["runtime_mapping"]
        }
        if left_bounds is None or right_bounds is None:
            bounds_comparability = "one_sided_projection"
        elif mapping_pair == {"direct_runtime_instance"}:
            bounds_comparability = "proven_direct_runtime_bounds"
        elif mapping_pair.issubset(
            {"direct_runtime_instance", "semantic_anchor_parent"}
        ) or len(mapping_pair) == 1:
            bounds_comparability = "candidate_equivalent_runtime_bounds"
        else:
            bounds_comparability = "incompatible_runtime_scopes"
        left_boundary_source = "runtime_component_bounds" if left_bounds is not None else None
        right_boundary_source = "runtime_component_bounds" if right_bounds is not None else None
        pillow_boundary_confidence = None
        if bounds_comparability in {
            "one_sided_projection",
            "incompatible_runtime_scopes",
        }:
            left_surface = (
                visual_surface_for_runtime_bounds(left_surface_candidates, left_bounds)
                if left_bounds is not None
                else None
            )
            right_surface = (
                visual_surface_for_runtime_bounds(right_surface_candidates, right_bounds)
                if right_bounds is not None
                else None
            )
            if left_surface is not None and right_surface is None:
                matched = matching_visual_surface(
                    left_surface[0], right_surface_candidates, target
                )
                if matched is not None:
                    right_surface = matched
            elif right_surface is not None and left_surface is None:
                matched = matching_visual_surface(
                    right_surface[0], left_surface_candidates, target
                )
                if matched is not None:
                    left_surface = matched
            if left_surface is not None and right_surface is not None:
                left_bounds = left_surface[0]["bounds"]
                right_bounds = right_surface[0]["bounds"]
                left_boundary_source = left_surface[0]["method"]
                right_boundary_source = right_surface[0]["method"]
                pillow_boundary_confidence = round(
                    min(left_surface[1], right_surface[1]), 6
                )
                bounds_comparability = "pillow_visual_surface_pair"
        if left_bounds is None and right_bounds is None:
            continue
        available_bounds = [
            bounds for bounds in (left_bounds, right_bounds) if bounds is not None
        ]
        union_left = min(bounds["x"] for bounds in available_bounds)
        union_top = min(bounds["y"] for bounds in available_bounds)
        union_right = max(
            bounds["x"] + bounds["width"] for bounds in available_bounds
        )
        union_bottom = max(
            bounds["y"] + bounds["height"] for bounds in available_bounds
        )
        union = (union_left, union_top, union_right, union_bottom)
        screen_position = local_similarity(left_rgb.crop(union), right_rgb.crop(union))
        ssim_score = screen_position["ssim_score"]
        geometry_delta_px = None
        geometry_delta_dp = None
        max_abs_geometry_delta_dp = None
        target_pixels_per_dp = target_pixels_per_dp_global
        if (
            left_bounds is not None
            and right_bounds is not None
            and bounds_comparability != "incompatible_runtime_scopes"
            and target_pixels_per_dp is not None
        ):
            geometry_delta_px = {
                field: right_bounds[field] - left_bounds[field]
                for field in ("x", "y", "width", "height")
            }
            geometry_delta_dp = {
                field: round(value / target_pixels_per_dp, 3)
                for field, value in geometry_delta_px.items()
            }
            max_abs_geometry_delta_dp = round(
                max(abs(value) for value in geometry_delta_dp.values()), 3
            )
        aligned_appearance = None
        aspect_ratio_delta = None
        if (
            left_bounds is not None
            and right_bounds is not None
            and bounds_comparability != "incompatible_runtime_scopes"
        ):
            left_aspect = left_bounds["width"] / left_bounds["height"]
            right_aspect = right_bounds["width"] / right_bounds["height"]
            aspect_ratio_delta = round(right_aspect - left_aspect, 6)
            aligned_appearance = local_similarity(
                left_rgb.crop(
                    (
                        left_bounds["x"],
                        left_bounds["y"],
                        left_bounds["x"] + left_bounds["width"],
                        left_bounds["y"] + left_bounds["height"],
                    )
                ),
                right_rgb.crop(
                    (
                        right_bounds["x"],
                        right_bounds["y"],
                        right_bounds["x"] + right_bounds["width"],
                        right_bounds["y"] + right_bounds["height"],
                    )
                ),
            )
        component_area = (union_right - union_left) * (union_bottom - union_top)
        area_ratio = component_area / full_area
        impact_score = max(0.0, 1.0 - ssim_score) * area_ratio
        rankings.append(
            {
                "semantic_key": semantic_key,
                "component_type": left_component["component_type"],
                "component_kind": left_component["component_kind"],
                "source": left_component["source"] or right_component["source"],
                "business_parent_semantic_key": left_component[
                    "business_parent_semantic_key"
                ],
                "business_children_semantic_keys": left_component[
                    "business_children_semantic_keys"
                ],
                "left_runtime_mapping": left_component["runtime_mapping"],
                "right_runtime_mapping": right_component["runtime_mapping"],
                "bounds_comparability": bounds_comparability,
                "left_boundary_source": left_boundary_source,
                "right_boundary_source": right_boundary_source,
                "pillow_boundary_confidence": pillow_boundary_confidence,
                "left_input_bounds": left_input_bounds,
                "right_input_bounds": right_input_bounds,
                "left_input_bounds_dp": left_input_bounds_dp,
                "right_input_bounds_dp": right_input_bounds_dp,
                "geometry_coordinate_space": "normalized_target_content",
                "geometry_delta_px": geometry_delta_px,
                "geometry_delta_dp": geometry_delta_dp,
                "max_abs_geometry_delta_dp": max_abs_geometry_delta_dp,
                "target_pixels_per_dp": (
                    round(target_pixels_per_dp, 6)
                    if target_pixels_per_dp is not None
                    else None
                ),
                "geometry_over_1dp": (
                    max_abs_geometry_delta_dp > 1.0
                    if max_abs_geometry_delta_dp is not None
                    else None
                ),
                "left_normalized_bounds": left_bounds,
                "right_normalized_bounds": right_bounds,
                "comparison_bounds": {
                    "x": union_left,
                    "y": union_top,
                    "width": union_right - union_left,
                    "height": union_bottom - union_top,
                },
                "comparison_region_basis": (
                    "paired_pillow_visual_surfaces"
                    if bounds_comparability == "pillow_visual_surface_pair"
                    else "paired_runtime_union"
                    if left_bounds is not None and right_bounds is not None
                    else (
                        "left_runtime_projection"
                        if left_bounds is not None
                        else "right_runtime_projection"
                    )
                ),
                "analysis_size_px": screen_position["analysis_size_px"],
                "metrics": screen_position["metrics"],
                "ssim_score": round(ssim_score, 6),
                "screen_position_metrics": screen_position["metrics"],
                "screen_position_ssim_score": round(ssim_score, 6),
                "aligned_appearance_metrics": (
                    aligned_appearance["metrics"]
                    if aligned_appearance is not None
                    else None
                ),
                "aligned_appearance_ssim_score": (
                    aligned_appearance["ssim_score"]
                    if aligned_appearance is not None
                    else None
                ),
                "aligned_appearance_analysis_size_px": (
                    aligned_appearance["analysis_size_px"]
                    if aligned_appearance is not None
                    else None
                ),
                "component_aspect_ratio_delta": aspect_ratio_delta,
                "changed_pixel_ratio": screen_position["changed_pixel_ratio"],
                "normalized_area_ratio": round(area_ratio, 6),
                "impact_score": round(impact_score, 8),
            }
        )
    rankings.sort(
        key=lambda item: (
            item["impact_score"],
            1.0 - item["ssim_score"],
            item["changed_pixel_ratio"],
        ),
        reverse=True,
    )
    for index, item in enumerate(rankings, 1):
        item["rank"] = index
    return rankings


def attach_business_component_control_diagnostics(
    rankings: list[dict[str, Any]],
    left_business_components: list[dict[str, Any]],
    right_business_components: list[dict[str, Any]],
    component_geometry: list[dict[str, Any]],
    component_styles: list[dict[str, Any]],
) -> None:
    left_business = {
        component["semantic_key"]: component for component in left_business_components
    }
    right_business = {
        component["semantic_key"]: component for component in right_business_components
    }
    geometry_by_key = {item["semantic_key"]: item for item in component_geometry}
    style_by_key = {item["semantic_key"]: item for item in component_styles}

    for ranking in rankings:
        semantic_key = ranking["semantic_key"]
        left_controls = {
            control["semantic_key"]: control
            for control in left_business.get(semantic_key, {}).get("controls", [])
        }
        right_controls = {
            control["semantic_key"]: control
            for control in right_business.get(semantic_key, {}).get("controls", [])
        }
        diagnostics: list[dict[str, Any]] = []
        for control_key in sorted(set(left_controls) | set(right_controls)):
            left_control = left_controls.get(control_key)
            right_control = right_controls.get(control_key)
            geometry = geometry_by_key.get(control_key)
            style = style_by_key.get(control_key)
            presence_status = (
                "pass" if left_control is not None and right_control is not None else "fail"
            )
            geometry_status = (
                "fail"
                if geometry is not None and geometry["over_1dp"]
                else ("pass" if geometry is not None else "unavailable")
            )
            style_status = style["status"] if style is not None else "unavailable"
            status = (
                "fail"
                if "fail" in {presence_status, geometry_status, style_status}
                else (
                    "pass"
                    if "pass" in {geometry_status, style_status}
                    else "unavailable"
                )
            )
            control = left_control or right_control
            diagnostics.append(
                {
                    "semantic_key": control_key,
                    "component_type": control["component_type"],
                    "source": control["source"],
                    "presence_status": presence_status,
                    "geometry_status": geometry_status,
                    "geometry": geometry,
                    "style_status": style_status,
                    "style": style,
                    "status": status,
                }
            )
        diagnostics.sort(
            key=lambda item: (
                item["status"] == "fail",
                (
                    item["geometry"]["max_abs_delta_dp"]
                    if item["geometry"] is not None
                    else -1
                ),
                item["semantic_key"],
            ),
            reverse=True,
        )
        ranking["control_diagnostics"] = diagnostics
        ranking["control_summary"] = {
            "total": len(diagnostics),
            "failed": sum(item["status"] == "fail" for item in diagnostics),
            "passed": sum(item["status"] == "pass" for item in diagnostics),
            "unavailable": sum(
                item["status"] == "unavailable" for item in diagnostics
            ),
        }


def summarize_business_components(
    rankings: list[dict[str, Any]],
    minimum_ssim: float,
) -> dict[str, Any]:
    ranked_keys = {item["semantic_key"] for item in rankings}
    leaf_components = [
        item
        for item in rankings
        if not ranked_keys.intersection(item["business_children_semantic_keys"])
    ]
    aligned_leaf_components = [
        item
        for item in leaf_components
        if item["aligned_appearance_ssim_score"] is not None
    ]
    total_weight = sum(
        item["normalized_area_ratio"] for item in aligned_leaf_components
    )
    aligned_score = (
        sum(
            item["aligned_appearance_ssim_score"]
            * item["normalized_area_ratio"]
            for item in aligned_leaf_components
        )
        / total_weight
        if total_weight > 0
        else None
    )
    return {
        "minimum_ssim": minimum_ssim,
        "business_component_count": len(rankings),
        "leaf_business_component_count": len(leaf_components),
        "aligned_leaf_component_count": len(aligned_leaf_components),
        "aligned_leaf_area_weighted_ssim_score": (
            round(aligned_score, 6) if aligned_score is not None else None
        ),
        "position_over_1dp_count": sum(
            item["geometry_over_1dp"] is True for item in rankings
        ),
        "aligned_appearance_below_threshold_count": sum(
            item["aligned_appearance_ssim_score"] is not None
            and item["aligned_appearance_ssim_score"] < minimum_ssim
            for item in rankings
        ),
        "one_sided_projection_count": sum(
            item["bounds_comparability"] == "one_sided_projection"
            for item in rankings
        ),
        "incompatible_runtime_scope_count": sum(
            item["bounds_comparability"] == "incompatible_runtime_scopes"
            for item in rankings
        ),
        "pillow_visual_surface_pair_count": sum(
            item["bounds_comparability"] == "pillow_visual_surface_pair"
            for item in rankings
        ),
        "failed_control_count": sum(
            item["control_summary"]["failed"] for item in rankings
        ),
        "unavailable_control_count": sum(
            item["control_summary"]["unavailable"] for item in rankings
        ),
        "aggregation_rule": (
            "area_weighted_leaf_business_components_with_comparable_two_sided_bounds"
        ),
    }


def render_human_report(report: dict[str, Any]) -> str:
    verdict = report["verdict"]
    analysis = report["difference_analysis"]
    rankings = analysis["business_component_ssim_rankings"]
    summary = analysis["business_component_summary"]

    def score(value: Any) -> str:
        return "不可用" if value is None else f"{float(value):.3f}"

    def delta(value: dict[str, Any] | None) -> str:
        if value is None:
            return "不可用"
        labels = {"x": "dx", "y": "dy", "width": "dw", "height": "dh"}
        return ", ".join(
            f"{labels[field]}={float(value[field]):+.3f}dp"
            for field in ("x", "y", "width", "height")
        )

    def comparability(value: str) -> str:
        return {
            "proven_direct_runtime_bounds": "双侧直接运行边界",
            "candidate_equivalent_runtime_bounds": "候选等价运行边界",
            "one_sided_projection": "仅单侧边界，投影诊断",
            "incompatible_runtime_scopes": "双侧采集范围不同，不可直接比较",
            "pillow_visual_surface_pair": "Pillow 配对的可见表面边界",
        }.get(value, value)

    lines = [
        "# 截图对比报告",
        "",
        "## 总体结论",
        "",
        f"- **最终结果：{'通过' if verdict['status'] == 'pass' else '失败'}**",
        f"- 全屏严格 SSIM：`{report['ssim_score']:.6f}`",
        f"- 验收阈值：`{verdict['minimum_ssim']:.3f}`",
        "- 说明：全屏 SSIM 包含位置、尺寸和内部外观差异。",
    ]
    if verdict["failure_reasons"]:
        lines.extend(["- 失败原因：", ""])
        lines.extend(f"  - {reason}" for reason in verdict["failure_reasons"])
    lines.extend(
        [
            "",
            "## 组件汇总",
            "",
            f"- 业务组件：`{summary['business_component_count']}` 个",
            f"- 可用于对齐后汇总的叶子组件：`{summary['aligned_leaf_component_count']}` 个",
            "- 忽略组件位置后的面积加权 SSIM："
            f"`{score(summary['aligned_leaf_area_weighted_ssim_score'])}`",
            f"- 位置或尺寸偏差超过 1dp：`{summary['position_over_1dp_count']}` 个",
            "- 对齐后内部外观低于阈值："
            f"`{summary['aligned_appearance_below_threshold_count']}` 个",
            f"- 明确失败的子控件：`{summary['failed_control_count']}` 个",
            f"- 子控件信息不足：`{summary['unavailable_control_count']}` 个",
            f"- 仅单侧边界：`{summary['one_sided_projection_count']}` 个",
            f"- 双侧采集范围不一致：`{summary['incompatible_runtime_scope_count']}` 个",
            f"- Pillow 补全双侧可见边界：`{summary['pillow_visual_surface_pair_count']}` 个",
            "",
            "## 业务组件排名",
            "",
            "| 排名 | 业务组件 | 位置/尺寸偏差 | 屏幕位置 SSIM | 对齐后外观 SSIM | 失败控件 | 边界可信度 |",
            "| ---: | --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for item in rankings:
        lines.append(
            "| "
            f"{item['rank']} | `{item['component_type']}` | "
            f"{delta(item['geometry_delta_dp'])} | "
            f"{score(item['screen_position_ssim_score'])} | "
            f"{score(item['aligned_appearance_ssim_score'])} | "
            f"{item['control_summary']['failed']} | "
            f"{comparability(item['bounds_comparability'])} |"
        )

    lines.extend(["", "## 组件与控件明细", ""])
    for item in rankings:
        source = item.get("source")
        source_text = (
            f"`{source['path']}:{source['line']}`"
            if isinstance(source, dict)
            else "不可用"
        )
        lines.extend(
            [
                f"### {item['rank']}. {item['component_type']}",
                "",
                f"- 语义 ID：`{item['semantic_key']}`",
                f"- 源码：{source_text}",
                f"- 边界：{comparability(item['bounds_comparability'])}",
                f"- 位置/尺寸：{delta(item['geometry_delta_dp'])}",
                f"- 屏幕位置 SSIM：`{score(item['screen_position_ssim_score'])}`",
                f"- 对齐后外观 SSIM：`{score(item['aligned_appearance_ssim_score'])}`",
            ]
        )
        if item["pillow_boundary_confidence"] is not None:
            lines.append(
                "- Pillow 边界置信度："
                f"`{float(item['pillow_boundary_confidence']):.3f}`；"
                "该边界表示可见表面，不包含透明点击区。"
            )
        failed_controls = [
            control for control in item["control_diagnostics"]
            if control["status"] == "fail"
        ]
        if failed_controls:
            lines.extend(["- 失败控件：", ""])
            for control in failed_controls:
                geometry = control.get("geometry")
                style = control.get("style")
                style_issue_count = (
                    style.get("blocking_issue_count", 0)
                    if isinstance(style, dict)
                    else 0
                )
                lines.append(
                    "  - "
                    f"`{control['component_type']}` `{control['semantic_key']}`："
                    f"{delta(geometry.get('delta_dp') if geometry else None)}；"
                    f"样式问题 `{style_issue_count}` 项"
                )
        elif item["control_summary"]["total"] == 0:
            lines.append("- 控件结论：当前组件未采集到可独立比较的语义控件。")
        elif item["control_summary"]["unavailable"]:
            lines.append(
                "- 控件结论："
                f"`{item['control_summary']['unavailable']}` 个控件缺少双侧可靠事实，未判通过。"
            )
        else:
            lines.append("- 控件结论：没有检测到控件级失败。")
        lines.append("")

    lines.extend(
        [
            "## 阅读规则",
            "",
            "- `dx < 0` 表示右侧实现更靠左，`dy < 0` 表示更靠上。",
            "- 屏幕位置 SSIM 低、对齐后外观 SSIM 高：主要是位置或尺寸问题。",
            "- 两个 SSIM 都低：位置和组件内部外观都需要检查。",
            "- 显示“不可用”不是通过，而是当前运行树没有提供可比较的双侧边界。",
            "- Pillow 边界只补全卡片、按钮、背景等可见表面，不推测透明 padding 或点击区域。",
            "- 组件汇总只对不重复覆盖的叶子业务组件按面积加权。",
            "",
        ]
    )
    return "\n".join(lines)


def save_png(image: Any, destination: Path) -> None:
    image.save(destination, format="PNG", compress_level=6)


def max_channel_difference(difference: Any) -> Any:
    red, green, blue = difference.split()
    return ImageChops.lighter(ImageChops.lighter(red, green), blue)


def changed_pixel_count(mask: Any) -> int:
    histogram = mask.histogram()
    return histogram[255]


def map_bounds_to_input(
    bounds: tuple[int, int, int, int],
    crop: tuple[int, int, int, int],
    target: tuple[int, int],
) -> dict[str, int]:
    x, y, width, height = bounds
    crop_x, crop_y, crop_width, crop_height = crop
    left = crop_x + math.floor(x * crop_width / target[0])
    top = crop_y + math.floor(y * crop_height / target[1])
    right = crop_x + math.ceil((x + width) * crop_width / target[0])
    bottom = crop_y + math.ceil((y + height) * crop_height / target[1])
    return {
        "x": left,
        "y": top,
        "width": right - left,
        "height": bottom - top,
    }


def component_candidates(
    hotspot_bounds: dict[str, int],
    components: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    hotspot_left = hotspot_bounds["x"]
    hotspot_top = hotspot_bounds["y"]
    hotspot_right = hotspot_left + hotspot_bounds["width"]
    hotspot_bottom = hotspot_top + hotspot_bounds["height"]
    hotspot_area = hotspot_bounds["width"] * hotspot_bounds["height"]
    candidates: list[dict[str, Any]] = []
    for component in components:
        bounds = component["bounds"]
        component_left = bounds["x"]
        component_top = bounds["y"]
        component_right = component_left + bounds["width"]
        component_bottom = component_top + bounds["height"]
        intersection_width = max(
            0,
            min(hotspot_right, component_right) - max(hotspot_left, component_left),
        )
        intersection_height = max(
            0,
            min(hotspot_bottom, component_bottom) - max(hotspot_top, component_top),
        )
        intersection_area = intersection_width * intersection_height
        if intersection_area == 0:
            continue
        component_area = bounds["width"] * bounds["height"]
        hotspot_overlap = intersection_area / hotspot_area
        component_overlap = intersection_area / component_area
        candidate = {
            "component_id": component["component_id"],
            "component_type": component["component_type"],
            "bounds": bounds,
            "intersection_pixel_count": intersection_area,
            "hotspot_overlap_ratio": round(hotspot_overlap, 6),
            "component_overlap_ratio": round(component_overlap, 6),
            "match_score": round((hotspot_overlap + component_overlap) / 2, 6),
        }
        if "semantic_key" in component:
            candidate["semantic_key"] = component["semantic_key"]
        candidates.append(candidate)
    candidates.sort(
        key=lambda candidate: (
            candidate["match_score"],
            candidate["component_overlap_ratio"],
            -candidate["bounds"]["width"] * candidate["bounds"]["height"],
        ),
        reverse=True,
    )
    return candidates[:5]


def attach_component_candidates(
    analysis: dict[str, Any],
    left_components: list[dict[str, Any]],
    right_components: list[dict[str, Any]],
) -> None:
    for hotspot in analysis["hotspots"]:
        left_candidates = component_candidates(
            hotspot["left_input_bounds"],
            left_components,
        )
        right_candidates = component_candidates(
            hotspot["right_input_bounds"],
            right_components,
        )
        hotspot["left_component_candidates"] = left_candidates
        hotspot["right_component_candidates"] = right_candidates
        pair_candidates = [
            {
                "semantic_key": left_candidate["semantic_key"],
                "left_component_id": left_candidate["component_id"],
                "left_component_type": left_candidate["component_type"],
                "right_component_id": right_candidate["component_id"],
                "right_component_type": right_candidate["component_type"],
                "match_score": round(
                    (left_candidate["match_score"] + right_candidate["match_score"]) / 2,
                    6,
                ),
            }
            for left_candidate in left_candidates
            for right_candidate in right_candidates
            if left_candidate.get("semantic_key") is not None
            and left_candidate.get("semantic_key") == right_candidate.get("semantic_key")
        ]
        pair_candidates.sort(key=lambda candidate: candidate["match_score"], reverse=True)
        hotspot["semantic_pair_candidates"] = pair_candidates[:5]


def summarize_component_impacts(analysis: dict[str, Any]) -> None:
    summary: dict[str, Any] = {
        "quality": "diagnostic_candidate",
        "authoritative": False,
        "left": [],
        "right": [],
    }
    for side in ("left", "right"):
        impacts: dict[str, dict[str, Any]] = {}
        candidate_field = f"{side}_component_candidates"
        for hotspot in analysis["hotspots"]:
            for candidate in hotspot[candidate_field]:
                component_id = candidate["component_id"]
                if component_id not in impacts:
                    impact = {
                        "component_id": component_id,
                        "component_type": candidate["component_type"],
                        "hotspot_ids": [],
                        "hotspot_count": 0,
                        "max_hotspot_severity": 0.0,
                        "max_match_score": 0.0,
                    }
                    if "semantic_key" in candidate:
                        impact["source_component"] = candidate["semantic_key"]
                    impacts[component_id] = impact
                impact = impacts[component_id]
                impact["hotspot_ids"].append(hotspot["id"])
                impact["hotspot_count"] += 1
                impact["max_hotspot_severity"] = max(
                    impact["max_hotspot_severity"],
                    hotspot["severity"],
                )
                impact["max_match_score"] = max(
                    impact["max_match_score"],
                    candidate["match_score"],
                )
        summary[side] = sorted(
            impacts.values(),
            key=lambda impact: (
                impact["max_match_score"],
                impact["hotspot_count"],
                impact["max_hotspot_severity"],
            ),
            reverse=True,
        )
    analysis["component_impact_summary"] = summary


def compare_component_geometry(
    left_components: list[dict[str, Any]],
    right_components: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    def unique_by_semantic_key(components: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for component in components:
            semantic_key = component.get("semantic_key")
            if semantic_key is not None and "bounds_dp" in component:
                grouped.setdefault(semantic_key, []).append(component)
        return {
            semantic_key: matches[0]
            for semantic_key, matches in grouped.items()
            if len(matches) == 1
        }

    left_by_key = unique_by_semantic_key(left_components)
    right_by_key = unique_by_semantic_key(right_components)

    def proven_paths(component: dict[str, Any]) -> set[str]:
        result: set[str] = set()
        for item in component.get("provenance", []):
            paths = item.get("paths") if isinstance(item, dict) else None
            if isinstance(paths, list):
                result.update(path for path in paths if isinstance(path, str))
        return result

    def transformed_layout_contract(component: dict[str, Any]) -> dict[str, float] | None:
        style = component.get("style")
        if not isinstance(style, dict):
            return None
        layout = style.get("layout")
        transform = style.get("transform")
        if not isinstance(layout, dict) or not isinstance(transform, dict):
            return None
        transform_fields = (
            "translation_x_dp", "translation_y_dp", "scale_x", "scale_y", "rotation_degrees"
        )
        if any(type(transform.get(field)) not in {int, float} for field in transform_fields):
            return None
        if (
            abs(float(transform["rotation_degrees"])) <= 0.001
            and abs(float(transform["scale_x"]) - 1.0) <= 0.001
            and abs(float(transform["scale_y"]) - 1.0) <= 0.001
        ):
            return None
        layout_fields = {
            field: float(layout[field])
            for field in ("width_dp", "height_dp")
            if type(layout.get(field)) in {int, float}
        }
        if not layout_fields:
            return None
        values = {
            **{f"layout.{field}": value for field, value in layout_fields.items()},
            **{f"transform.{field}": float(transform[field]) for field in transform_fields},
        }
        required_provenance = {f"style.{path}" for path in values}
        if not required_provenance.issubset(proven_paths(component)):
            return None
        return values

    comparisons: list[dict[str, Any]] = []
    for semantic_key in sorted(set(left_by_key) & set(right_by_key)):
        left = left_by_key[semantic_key]
        right = right_by_key[semantic_key]
        left_contract = transformed_layout_contract(left)
        right_contract = transformed_layout_contract(right)
        if left_contract is not None and right_contract is not None:
            contract_paths = sorted(set(left_contract) | set(right_contract))
            contract_comparisons = [
                compare_style_property(
                    f"style.{path}",
                    left_contract.get(path),
                    right_contract.get(path),
                )
                for path in contract_paths
            ]
            contract_failed = (
                set(left_contract) != set(right_contract)
                or any(item["over_tolerance"] for item in contract_comparisons)
            )
            raw_left = left.get("comparison_bounds_dp", left["bounds_dp"])
            raw_right = right.get("comparison_bounds_dp", right["bounds_dp"])
            raw_delta = {
                field: round(raw_right[field] - raw_left[field], 3)
                for field in ("x", "y", "width", "height")
            }
            numeric_contract_deltas = [
                abs(float(item.get("delta", 0.0)))
                for item in contract_comparisons
                if item.get("metric") != "exact"
            ]
            comparisons.append(
                {
                    "semantic_key": semantic_key,
                    "left_component_id": left["component_id"],
                    "right_component_id": right["component_id"],
                    "coordinate_space": "source_resolved_pre_transform_layout_and_transform",
                    "left_geometry_contract": left_contract,
                    "right_geometry_contract": right_contract,
                    "contract_comparisons": contract_comparisons,
                    "runtime_bounds_diagnostic": {
                        "left_bounds_dp": raw_left,
                        "right_bounds_dp": raw_right,
                        "delta_dp": raw_delta,
                    },
                    "max_abs_delta_dp": round(max(numeric_contract_deltas, default=0.0), 3),
                    "over_1dp": contract_failed,
                }
            )
            continue
        left_bounds = left.get("comparison_bounds_dp", left["bounds_dp"])
        right_bounds = right.get("comparison_bounds_dp", right["bounds_dp"])
        delta = {
            field: round(right_bounds[field] - left_bounds[field], 3)
            for field in ("x", "y", "width", "height")
        }
        max_delta = round(max(abs(value) for value in delta.values()), 3)
        comparisons.append(
            {
                "semantic_key": semantic_key,
                "left_component_id": left["component_id"],
                "right_component_id": right["component_id"],
                "coordinate_space": (
                    left.get("comparison_coordinate_space")
                    if left.get("comparison_coordinate_space") is not None
                    and left.get("comparison_coordinate_space")
                    == right.get("comparison_coordinate_space")
                    else (
                        "content_relative_logical_units"
                        if "comparison_bounds_dp" in left and "comparison_bounds_dp" in right
                        else "screen_logical_units"
                    )
                ),
                "left_bounds_dp": left_bounds,
                "right_bounds_dp": right_bounds,
                "delta_dp": delta,
                "max_abs_delta_dp": max_delta,
                "over_1dp": max_delta > 1.0,
            }
        )
    return comparisons


def normalize_component_geometry_to_explicit_crops(
    left_components: list[dict[str, Any]],
    right_components: list[dict[str, Any]],
    left_crop: tuple[int, int, int, int],
    right_crop: tuple[int, int, int, int],
    left_record: dict[str, Any] | None,
    right_record: dict[str, Any] | None,
    left_crop_source: str,
    right_crop_source: str,
) -> dict[str, Any] | None:
    if (
        left_crop_source != "explicit"
        or right_crop_source != "explicit"
        or left_record is None
        or right_record is None
        or left_record.get("schema") != PAGE_SNAPSHOT_V2_SCHEMA
        or right_record.get("schema") != PAGE_SNAPSHOT_V2_SCHEMA
    ):
        return None
    left_viewport = left_record.get("viewport")
    right_viewport = right_record.get("viewport")
    if not isinstance(left_viewport, dict) or not isinstance(right_viewport, dict):
        return None
    if left_viewport.get("orientation") != right_viewport.get("orientation"):
        return None
    if abs(float(left_viewport["font_scale"]) - float(right_viewport["font_scale"])) > 0.001:
        return None
    aspect_delta = abs(left_crop[2] / left_crop[3] - right_crop[2] / right_crop[3])
    if aspect_delta > 0.001:
        return None

    left_density = float(left_viewport["density"])
    right_density = float(right_viewport["density"])
    reference_width_dp = left_crop[2] / left_density
    reference_height_dp = left_crop[3] / left_density
    coordinate_space = "explicit_crop_normalized_reference_logical_units"

    for components, crop in (
        (left_components, left_crop),
        (right_components, right_crop),
    ):
        crop_x, crop_y, crop_width, crop_height = crop
        for component in components:
            bounds = component["bounds"]
            component["comparison_bounds_dp"] = {
                "x": round((bounds["x"] - crop_x) * reference_width_dp / crop_width, 3),
                "y": round((bounds["y"] - crop_y) * reference_height_dp / crop_height, 3),
                "width": round(bounds["width"] * reference_width_dp / crop_width, 3),
                "height": round(bounds["height"] * reference_height_dp / crop_height, 3),
            }
            component["comparison_coordinate_space"] = coordinate_space

    return {
        "reference_side": "left",
        "reference_logical_size_dp": {
            "width": round(reference_width_dp, 3),
            "height": round(reference_height_dp, 3),
        },
        "left_crop_logical_size_dp": {
            "width": round(left_crop[2] / left_density, 3),
            "height": round(left_crop[3] / left_density, 3),
        },
        "right_crop_logical_size_dp": {
            "width": round(right_crop[2] / right_density, 3),
            "height": round(right_crop[3] / right_density, 3),
        },
    }


def unique_components_by_semantic_key(
    components: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for component in components:
        semantic_key = component.get("semantic_key")
        if semantic_key is not None:
            grouped.setdefault(semantic_key, []).append(component)
    return {
        semantic_key: matches[0]
        for semantic_key, matches in grouped.items()
        if len(matches) == 1
    }


def compare_component_presence(
    left_components: list[dict[str, Any]],
    right_components: list[dict[str, Any]],
) -> dict[str, Any]:
    def inventory(components: list[dict[str, Any]]) -> tuple[set[str], list[str], list[str]]:
        grouped: dict[str, int] = {}
        untagged: list[str] = []
        for component in components:
            semantic_key = component.get("semantic_key")
            if semantic_key is None:
                untagged.append(component["component_id"])
            else:
                grouped[semantic_key] = grouped.get(semantic_key, 0) + 1
        return set(grouped), sorted(key for key, count in grouped.items() if count > 1), sorted(untagged)

    left_keys, ambiguous_left, untagged_left = inventory(left_components)
    right_keys, ambiguous_right, untagged_right = inventory(right_components)
    result = {
        "missing_in_left": sorted(right_keys - left_keys),
        "missing_in_right": sorted(left_keys - right_keys),
        "ambiguous_in_left": ambiguous_left,
        "ambiguous_in_right": ambiguous_right,
        "untagged_left_component_ids": untagged_left,
        "untagged_right_component_ids": untagged_right,
    }
    result["status"] = "fail" if any(result.values()) else "pass"
    return result


def compare_component_hierarchy(
    left_components: list[dict[str, Any]],
    right_components: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    left_by_key = unique_components_by_semantic_key(left_components)
    right_by_key = unique_components_by_semantic_key(right_components)
    comparisons: list[dict[str, Any]] = []
    for semantic_key in sorted(set(left_by_key) & set(right_by_key)):
        left = left_by_key[semantic_key]
        right = right_by_key[semantic_key]
        if "parent_id" not in left or "parent_id" not in right:
            continue
        parent_changed = left["parent_semantic_key"] != right["parent_semantic_key"]
        sibling_index_changed = left["sibling_index"] != right["sibling_index"]
        children_order_changed = left["children_semantic_keys"] != right["children_semantic_keys"]
        comparisons.append(
            {
                "semantic_key": semantic_key,
                "left_component_id": left["component_id"],
                "right_component_id": right["component_id"],
                "left_parent_semantic_key": left["parent_semantic_key"],
                "right_parent_semantic_key": right["parent_semantic_key"],
                "left_sibling_index": left["sibling_index"],
                "right_sibling_index": right["sibling_index"],
                "left_children_semantic_keys": left["children_semantic_keys"],
                "right_children_semantic_keys": right["children_semantic_keys"],
                "parent_changed": parent_changed,
                "sibling_index_changed": sibling_index_changed,
                "children_order_changed": children_order_changed,
                "status": "fail" if parent_changed or sibling_index_changed or children_order_changed else "pass",
            }
        )
    return comparisons


def flatten_proven_style(value: Any, prefix: str, output: dict[str, Any]) -> None:
    if value is None:
        return
    if isinstance(value, dict):
        for key in sorted(value):
            flatten_proven_style(value[key], f"{prefix}.{key}", output)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            flatten_proven_style(item, f"{prefix}[{index}]", output)
        return
    output[prefix] = value


def color_channels(value: str) -> tuple[int, ...] | None:
    if re.fullmatch(r"#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?", value) is None:
        return None
    return tuple(int(value[index:index + 2], 16) for index in range(1, len(value), 2))


def compare_style_property(path: str, left: Any, right: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"path": path, "left": left, "right": right}
    left_color = color_channels(left) if isinstance(left, str) else None
    right_color = color_channels(right) if isinstance(right, str) else None
    if left_color is not None and right_color is not None and len(left_color) == len(right_color):
        delta = max(abs(right_channel - left_channel) for left_channel, right_channel in zip(left_color, right_color))
        result.update(
            {
                "metric": "max_color_channel_delta",
                "max_channel_delta": delta,
                "tolerance": 8,
                "over_tolerance": delta > 8,
            }
        )
        return result
    if type(left) in {int, float} and type(right) in {int, float}:
        delta = round(float(right) - float(left), 3)
        if "_dp" in path:
            tolerance = 1.0
            metric = "delta_dp"
        elif "_sp" in path:
            tolerance = 1.0
            metric = "delta_sp"
        elif path.endswith("rotation_degrees") or path.endswith("angle_degrees"):
            tolerance = 1.0
            metric = "delta_degrees"
        elif path.endswith("alpha") or ".scale_" in path:
            tolerance = 0.01
            metric = "numeric_delta"
        else:
            tolerance = 0.0
            metric = "numeric_delta"
        result.update(
            {
                "metric": metric,
                "delta": delta,
                "tolerance": tolerance,
                "over_tolerance": abs(delta) > tolerance,
            }
        )
        return result
    equal = left == right
    result.update(
        {
            "metric": "exact",
            "equal": equal,
            "over_tolerance": not equal,
        }
    )
    return result


def compare_component_styles(
    left_components: list[dict[str, Any]],
    right_components: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    left_by_key = unique_components_by_semantic_key(left_components)
    right_by_key = unique_components_by_semantic_key(right_components)
    comparisons: list[dict[str, Any]] = []
    for semantic_key in sorted(set(left_by_key) & set(right_by_key)):
        left_component = left_by_key[semantic_key]
        right_component = right_by_key[semantic_key]
        if "style" not in left_component or "style" not in right_component:
            continue
        left_style: dict[str, Any] = {}
        right_style: dict[str, Any] = {}
        flatten_proven_style(left_component["style"], "style", left_style)
        flatten_proven_style(right_component["style"], "style", right_style)
        for raw_pixel_path in (
            "style.asset.width_px", "style.asset.height_px",
        ):
            left_style.pop(raw_pixel_path, None)
            right_style.pop(raw_pixel_path, None)
        common_paths = sorted(set(left_style) & set(right_style))
        property_comparisons = [
            compare_style_property(path, left_style[path], right_style[path])
            for path in common_paths
        ]
        over_tolerance_count = sum(
            1 for item in property_comparisons if item["over_tolerance"]
        )
        left_only_paths = sorted(set(left_style) - set(right_style))
        right_only_paths = sorted(set(right_style) - set(left_style))
        unresolved_count = len(left_component["unresolved"]) + len(right_component["unresolved"])
        one_side_proven_count = len(left_only_paths) + len(right_only_paths)
        blocking_issue_count = over_tolerance_count + unresolved_count + one_side_proven_count
        comparisons.append(
            {
                "semantic_key": semantic_key,
                "left_component_id": left_component["component_id"],
                "right_component_id": right_component["component_id"],
                "compared_property_count": len(property_comparisons),
                "over_tolerance_count": over_tolerance_count,
                "unresolved_count": unresolved_count,
                "one_side_proven_count": one_side_proven_count,
                "blocking_issue_count": blocking_issue_count,
                "status": "fail" if blocking_issue_count else "pass",
                "left_only_proven_paths": left_only_paths,
                "right_only_proven_paths": right_only_paths,
                "left_unresolved": left_component["unresolved"],
                "right_unresolved": right_component["unresolved"],
                "comparisons": property_comparisons,
            }
        )
    return comparisons


def viewport_compatibility(
    left_dimensions: tuple[int, int],
    right_dimensions: tuple[int, int],
    left_crop: tuple[int, int, int, int],
    right_crop: tuple[int, int, int, int],
    left_record: dict[str, Any] | None,
    right_record: dict[str, Any] | None,
    explicit_crop_transform: dict[str, Any] | None,
) -> dict[str, Any]:
    aspect_delta = abs(left_crop[2] / left_crop[3] - right_crop[2] / right_crop[3])
    left_viewport = left_record.get("viewport") if left_record else None
    right_viewport = right_record.get("viewport") if right_record else None
    same_logical_size: bool | None = None
    same_orientation: bool | None = None
    same_font_scale: bool | None = None
    logical_content_delta_dp: dict[str, float] | None = None
    if isinstance(left_viewport, dict) and isinstance(right_viewport, dict):
        left_content = left_viewport["content_bounds_dp"]
        right_content = right_viewport["content_bounds_dp"]
        logical_content_delta_dp = {
            field: round(right_content[field] - left_content[field], 3)
            for field in ("x", "y", "width", "height")
        }
        same_logical_size = all(
            abs(logical_content_delta_dp[field]) <= 0.001
            for field in ("width", "height")
        )
        same_orientation = left_viewport["orientation"] == right_viewport["orientation"]
        same_font_scale = abs(left_viewport["font_scale"] - right_viewport["font_scale"]) <= 0.001
    pixel_compatible = (
        aspect_delta <= 0.001
        and (same_logical_size is True or explicit_crop_transform is not None)
        and same_orientation is True
        and same_font_scale is True
    )
    return {
        "same_pixel_size": left_dimensions == right_dimensions,
        "same_logical_content_size": same_logical_size,
        "same_orientation": same_orientation,
        "same_font_scale": same_font_scale,
        "logical_content_delta_dp": logical_content_delta_dp,
        "cropped_aspect_ratio_delta": round(aspect_delta, 8),
        "uniform_explicit_crop_transform": explicit_crop_transform is not None,
        "explicit_crop_transform": explicit_crop_transform,
        "pixel_comparison_compatible": pixel_compatible,
        "geometry_comparison_mode": (
            "explicit_crop_normalized_reference_logical_units"
            if explicit_crop_transform is not None
            else "content_relative_platform_logical_units"
        ),
        "requirement": (
            "Physical pixel dimensions may differ. Pixel metrics require aligned content aspect ratio, "
            "orientation, system-bar crop, font scale, locale, theme, and deterministic state."
        ),
    }


def build_verdict(
    left_record: dict[str, Any] | None,
    right_record: dict[str, Any] | None,
    presence: dict[str, Any],
    hierarchy: list[dict[str, Any]],
    geometry: list[dict[str, Any]],
    styles: list[dict[str, Any]],
    viewport: dict[str, Any],
    metrics: dict[str, float],
    minimum_ssim: float,
) -> dict[str, Any]:
    complete_v2 = (
        left_record is not None
        and right_record is not None
        and left_record.get("schema") == PAGE_SNAPSHOT_V2_SCHEMA
        and right_record.get("schema") == PAGE_SNAPSHOT_V2_SCHEMA
    )
    hierarchy_passed = all(item["status"] == "pass" for item in hierarchy)
    geometry_passed = all(not item["over_1dp"] for item in geometry)
    styles_passed = all(item["status"] == "pass" for item in styles)
    pixels_passed = (
        viewport["pixel_comparison_compatible"]
        and all(value >= minimum_ssim for value in metrics.values())
    )
    checks = {
        "complete_v2_page_snapshots": complete_v2,
        "component_presence": presence["status"] == "pass",
        "component_hierarchy": hierarchy_passed,
        "component_geometry": geometry_passed,
        "component_styles": styles_passed,
        "viewport_compatible": viewport["pixel_comparison_compatible"],
        "pixel_similarity": pixels_passed,
    }
    labels = {
        "complete_v2_page_snapshots": "complete v2 page snapshots are required",
        "component_presence": "component presence is not equivalent",
        "component_hierarchy": "component hierarchy or sibling order differs",
        "component_geometry": "component geometry exceeds 1dp tolerance",
        "component_styles": "component styles differ or contain unresolved facts",
        "viewport_compatible": "logical viewport, orientation, or font scale is incompatible",
        "pixel_similarity": f"one or more SSIM metrics are below {minimum_ssim}",
    }
    failure_reasons = [labels[name] for name, passed in checks.items() if not passed]
    return {
        "status": "fail" if failure_reasons else "pass",
        "minimum_ssim": minimum_ssim,
        "checks": checks,
        "failure_reasons": failure_reasons,
    }


def attribute_group_signal_scores(metrics: dict[str, float]) -> dict[str, float]:
    color_loss = min(2.0, max(0.0, 1.0 - metrics["ssim_color"])) / 2.0
    luma_loss = min(2.0, max(0.0, 1.0 - metrics["ssim_luma"])) / 2.0
    edge_loss = min(2.0, max(0.0, 1.0 - metrics["ssim_edges"])) / 2.0
    broad_loss = max(color_loss, luma_loss, edge_loss)
    return {
        "asset": round(broad_loss, 6),
        "behavior": 0.0,
        "color": round(max(color_loss, luma_loss), 6),
        "component_semantics": round(broad_loss, 6),
        "content": round(max(luma_loss, edge_loss), 6),
        "geometry": round(edge_loss, 6),
        "state": round(broad_loss, 6),
        "surface": round(max(color_loss, edge_loss), 6),
        "transform": round(edge_loss, 6),
        "typography": round(max(luma_loss, edge_loss), 6),
    }


def attach_source_attribute_candidates(
    analysis: dict[str, Any],
    source_components: dict[str, dict[str, Any]],
    metrics: dict[str, float],
) -> None:
    scores = attribute_group_signal_scores(metrics)
    summary = analysis["component_impact_summary"]
    for side in ("left", "right"):
        for impact in summary[side]:
            semantic_key = impact.get("source_component")
            source_component = source_components.get(semantic_key)
            if source_component is None:
                impact["source_attribute_candidates"] = []
                continue
            groups = sorted(
                {
                    group
                    for attribute in source_component["attributes"]
                    for group in attribute["groups"]
                },
                key=lambda group: (scores[group], group),
                reverse=True,
            )
            group_rank = {group: index for index, group in enumerate(groups)}
            attributes = sorted(
                source_component["attributes"],
                key=lambda attribute: (
                    min(group_rank[group] for group in attribute["groups"]),
                    attribute["line"],
                    attribute["call_id"],
                    attribute.get("modifier_index", -1),
                    attribute["name"],
                ),
            )
            impact["source_attribute_candidates"] = [
                {
                    "semantic_key": semantic_key,
                    "source": source_component["source"],
                    "composable": source_component["composable"],
                    "candidate_attribute_groups": groups,
                    "group_signal_scores": {
                        group: scores[group] for group in groups
                    },
                    "attributes": attributes,
                }
            ]


def analyze_difference(
    difference: Any,
    left_crop: tuple[int, int, int, int],
    right_crop: tuple[int, int, int, int],
    target: tuple[int, int],
    threshold: int = 16,
) -> tuple[dict[str, Any], Any]:
    magnitude = max_channel_difference(difference)
    mask = magnitude.point(lambda value: 255 if value >= threshold else 0, mode="L")
    total_pixels = target[0] * target[1]
    total_changed = changed_pixel_count(mask)
    mean_delta = sum(ImageStat.Stat(difference).mean) / (3 * 255)
    tile_size = min(64, max(8, math.ceil((min(target) / 12) / 8) * 8))
    hot_tiles: dict[tuple[int, int], tuple[int, int, int, int]] = {}
    hotspot_candidates: list[dict[str, Any]] = []
    for row, y in enumerate(range(0, target[1], tile_size)):
        for column, x in enumerate(range(0, target[0], tile_size)):
            right = min(x + tile_size, target[0])
            bottom = min(y + tile_size, target[1])
            tile_mask = mask.crop((x, y, right, bottom))
            area = (right - x) * (bottom - y)
            affected_pixels = changed_pixel_count(tile_mask)
            affected_ratio = affected_pixels / area
            if affected_ratio >= 0.02:
                bounds = (x, y, right - x, bottom - y)
                hot_tiles[(column, row)] = (x, y, right, bottom)
                tile_difference = difference.crop((x, y, right, bottom))
                tile_mean_delta = sum(ImageStat.Stat(tile_difference).mean) / (3 * 255)
                hotspot_candidates.append(
                    {
                        "normalized_bounds": {
                            "x": bounds[0],
                            "y": bounds[1],
                            "width": bounds[2],
                            "height": bounds[3],
                        },
                        "left_input_bounds": map_bounds_to_input(bounds, left_crop, target),
                        "right_input_bounds": map_bounds_to_input(bounds, right_crop, target),
                        "affected_pixel_count": affected_pixels,
                        "changed_pixel_ratio": round(affected_ratio, 6),
                        "mean_absolute_channel_delta": round(tile_mean_delta, 6),
                        "severity": round(
                            min(1.0, affected_ratio * 0.45 + tile_mean_delta * 0.55),
                            6,
                        ),
                    }
                )

    components: list[list[tuple[int, int, int, int]]] = []
    remaining = set(hot_tiles)
    while remaining:
        start = remaining.pop()
        pending = deque([start])
        component = [hot_tiles[start]]
        while pending:
            column, row = pending.popleft()
            for column_delta in (-1, 0, 1):
                for row_delta in (-1, 0, 1):
                    neighbor = (column + column_delta, row + row_delta)
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        pending.append(neighbor)
                        component.append(hot_tiles[neighbor])
        components.append(component)

    region_candidates: list[dict[str, Any]] = []
    for component in components:
        left = min(tile[0] for tile in component)
        top = min(tile[1] for tile in component)
        right = max(tile[2] for tile in component)
        bottom = max(tile[3] for tile in component)
        bounds = (left, top, right - left, bottom - top)
        region_mask = mask.crop((left, top, right, bottom))
        region_difference = difference.crop((left, top, right, bottom))
        area = bounds[2] * bounds[3]
        affected_pixels = changed_pixel_count(region_mask)
        affected_ratio = affected_pixels / area
        region_mean_delta = sum(ImageStat.Stat(region_difference).mean) / (3 * 255)
        region_candidates.append(
            {
                "normalized_bounds": {
                    "x": bounds[0],
                    "y": bounds[1],
                    "width": bounds[2],
                    "height": bounds[3],
                },
                "left_input_bounds": map_bounds_to_input(bounds, left_crop, target),
                "right_input_bounds": map_bounds_to_input(bounds, right_crop, target),
                "affected_pixel_count": affected_pixels,
                "changed_pixel_ratio": round(affected_ratio, 6),
                "mean_absolute_channel_delta": round(region_mean_delta, 6),
                "severity": round(
                    min(1.0, affected_ratio * 0.45 + region_mean_delta * 0.55),
                    6,
                ),
                "rank_weight": affected_pixels * region_mean_delta,
            }
        )
    region_candidates.sort(key=lambda region: region["rank_weight"], reverse=True)
    for region in region_candidates:
        region.pop("rank_weight")
    regions = region_candidates[:50]
    for index, region in enumerate(regions, start=1):
        region["id"] = index
    hotspot_candidates.sort(
        key=lambda hotspot: (
            hotspot["severity"],
            hotspot["affected_pixel_count"],
        ),
        reverse=True,
    )
    hotspots = hotspot_candidates[:20]
    for index, hotspot in enumerate(hotspots, start=1):
        hotspot["id"] = index

    annotated = ImageEnhance.Brightness(difference).enhance(4.0)
    draw = ImageDraw.Draw(annotated)
    line_width = max(2, target[0] // 360)
    for region in regions:
        bounds = region["normalized_bounds"]
        draw.rectangle(
            (
                bounds["x"],
                bounds["y"],
                bounds["x"] + bounds["width"] - 1,
                bounds["y"] + bounds["height"] - 1,
            ),
            outline=(255, 0, 0),
            width=line_width,
        )
        draw.text((bounds["x"] + line_width, bounds["y"] + line_width), f"R{region['id']}", fill=(255, 0, 0))
    for hotspot in hotspots:
        bounds = hotspot["normalized_bounds"]
        draw.rectangle(
            (
                bounds["x"],
                bounds["y"],
                bounds["x"] + bounds["width"] - 1,
                bounds["y"] + bounds["height"] - 1,
            ),
            outline=(255, 255, 0),
            width=line_width,
        )
        draw.text(
            (bounds["x"] + line_width, bounds["y"] + line_width),
            f"H{hotspot['id']}",
            fill=(255, 255, 0),
        )

    analysis = {
        "coordinate_space": "normalized_target_pixels",
        "pixel_difference_threshold": threshold,
        "tile_size": tile_size,
        "changed_pixel_ratio": round(total_changed / total_pixels, 6),
        "mean_absolute_channel_delta": round(mean_delta, 6),
        "region_count": len(regions),
        "regions_truncated": len(region_candidates) > len(regions),
        "regions": regions,
        "hotspot_count": len(hotspots),
        "hotspots_truncated": len(hotspot_candidates) > len(hotspots),
        "hotspots": hotspots,
        "quality": "diagnostic_candidate",
        "authoritative": False,
    }
    return analysis, annotated


def artifact_record(path: Path, kind: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "file": path.name,
        "byte_count": path.stat().st_size,
        "sha256": sha256_file(path),
        "contains_image_data": True,
    }


def validate_label(value: str, name: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 80:
        raise ComparisonError(f"{name} label must contain 1 to 80 characters")
    return normalized


def compare(args: argparse.Namespace) -> dict[str, Any]:
    require_pillow()
    if not math.isfinite(args.min_ssim) or not 0.0 <= args.min_ssim <= 1.0:
        raise ComparisonError("min-ssim must be between 0 and 1")
    left = resolve_input(args.left, "left")
    right = resolve_input(args.right, "right")
    left_label = validate_label(args.left_label, "left")
    right_label = validate_label(args.right_label, "right")
    output = Path(os.path.abspath(os.path.expanduser(str(args.output_dir))))
    if output.exists():
        raise ComparisonError("output directory already exists")

    left_image = load_image(left, "left")
    right_image = load_image(right, "right")
    left_dimensions = left_image.size
    right_dimensions = right_image.size
    left_component_record, left_components, left_business_components = load_component_inventory(
        args.left_components,
        "left",
        left_dimensions,
        left,
    )
    right_component_record, right_components, right_business_components = load_component_inventory(
        args.right_components,
        "right",
        right_dimensions,
        right,
    )
    if (
        left_component_record is not None
        and right_component_record is not None
        and "page" in left_component_record
        and "page" in right_component_record
        and left_component_record["page"] != right_component_record["page"]
    ):
        left_image.close()
        right_image.close()
        raise ComparisonError(
            "page/state mismatch: "
            f"{left_component_record['page']['id']}/{left_component_record['page']['state']} != "
            f"{right_component_record['page']['id']}/{right_component_record['page']['state']}"
        )
    component_inventory_records = [
        record
        for record in (left_component_record, right_component_record)
        if record is not None
    ]
    source_attribute_record, source_attribute_components = (
        load_source_attribute_inventory(args.source_attributes)
    )
    left_crop, left_crop_source = select_crop(
        args.left_crop, *left_dimensions, "left", left_component_record
    )
    right_crop, right_crop_source = select_crop(
        args.right_crop, *right_dimensions, "right", right_component_record
    )
    target = parse_target_size(args.target_size, left_crop[2:])
    output.mkdir(parents=True, mode=0o700)
    normalized_left_image = None
    normalized_right_image = None
    try:
        normalized_left = output / "normalized-left.png"
        normalized_right = output / "normalized-right.png"
        difference = output / "difference.png"
        annotated_difference = output / "annotated-difference.png"
        side_by_side = output / "side-by-side.png"
        report_path = output / "comparison.json"
        human_report_path = output / "comparison-summary.md"
        normalized_left_image = normalize(left_image, left_crop, target)
        normalized_right_image = normalize(right_image, right_crop, target)
        save_png(normalized_left_image, normalized_left)
        save_png(normalized_right_image, normalized_right)
        left_rgb = normalized_left_image.convert("RGB")
        right_rgb = normalized_right_image.convert("RGB")
        left_luma = normalized_left_image.convert("L")
        right_luma = normalized_right_image.convert("L")
        left_edges = left_luma.filter(ImageFilter.FIND_EDGES).filter(
            ImageFilter.GaussianBlur(EDGE_TOLERANCE_RADIUS_PX)
        )
        right_edges = right_luma.filter(ImageFilter.FIND_EDGES).filter(
            ImageFilter.GaussianBlur(EDGE_TOLERANCE_RADIUS_PX)
        )
        raw_difference = ImageChops.difference(left_rgb, right_rgb)
        raw_metrics = {
            "ssim_color": image_ssim(left_rgb, right_rgb),
            "ssim_luma": channel_ssim(left_luma, right_luma),
        }
        left_tolerant_rgb = left_rgb.filter(
            ImageFilter.GaussianBlur(RASTERIZATION_TOLERANCE_RADIUS_PX)
        )
        right_tolerant_rgb = right_rgb.filter(
            ImageFilter.GaussianBlur(RASTERIZATION_TOLERANCE_RADIUS_PX)
        )
        metrics = {
            "ssim_color": image_ssim(left_tolerant_rgb, right_tolerant_rgb),
            "ssim_luma": channel_ssim(
                left_tolerant_rgb.convert("L"), right_tolerant_rgb.convert("L")
            ),
            "ssim_edges": channel_ssim(left_edges, right_edges),
        }
        ssim_score = min(metrics.values())
        difference_image = ImageEnhance.Brightness(
            raw_difference
        ).enhance(4.0)
        save_png(difference_image, difference)
        difference_analysis, annotated_difference_image = analyze_difference(
            raw_difference,
            left_crop,
            right_crop,
            target,
        )
        business_component_rankings = business_component_ssim_rankings(
            left_rgb,
            right_rgb,
            left_business_components,
            right_business_components,
            left_crop,
            right_crop,
            target,
        )
        attach_component_candidates(
            difference_analysis,
            left_components,
            right_components,
        )
        summarize_component_impacts(difference_analysis)
        component_presence = compare_component_presence(left_components, right_components)
        left_elisions = (
            left_component_record.get("runtime_elided_source_components", [])
            if left_component_record is not None else []
        )
        right_elisions = (
            right_component_record.get("runtime_elided_source_components", [])
            if right_component_record is not None else []
        )
        if left_elisions != right_elisions:
            component_presence["runtime_elisions_match"] = False
            component_presence["status"] = "fail"
        component_hierarchy = compare_component_hierarchy(left_components, right_components)
        explicit_crop_transform = normalize_component_geometry_to_explicit_crops(
            left_components,
            right_components,
            left_crop,
            right_crop,
            left_component_record,
            right_component_record,
            left_crop_source,
            right_crop_source,
        )
        component_geometry = compare_component_geometry(
            left_components,
            right_components,
        )
        component_styles = compare_component_styles(
            left_components,
            right_components,
        )
        attach_business_component_control_diagnostics(
            business_component_rankings,
            left_business_components,
            right_business_components,
            component_geometry,
            component_styles,
        )
        difference_analysis["business_component_ssim_rankings"] = (
            business_component_rankings
        )
        difference_analysis["business_component_summary"] = (
            summarize_business_components(
                business_component_rankings,
                args.min_ssim,
            )
        )
        difference_analysis["component_presence"] = component_presence
        difference_analysis["component_hierarchy_deltas"] = component_hierarchy
        difference_analysis["component_geometry_deltas"] = component_geometry
        difference_analysis["component_style_deltas"] = component_styles
        attach_source_attribute_candidates(
            difference_analysis,
            source_attribute_components,
            metrics,
        )
        save_png(annotated_difference_image, annotated_difference)
        side_by_side_image = Image.new("RGB", (target[0] * 2, target[1]))
        side_by_side_image.paste(left_rgb, (0, 0))
        side_by_side_image.paste(right_rgb, (target[0], 0))
        save_png(side_by_side_image, side_by_side)
        viewport = viewport_compatibility(
            left_dimensions,
            right_dimensions,
            left_crop,
            right_crop,
            left_component_record,
            right_component_record,
            explicit_crop_transform,
        )
        verdict = build_verdict(
            left_component_record,
            right_component_record,
            component_presence,
            component_hierarchy,
            component_geometry,
            component_styles,
            viewport,
            metrics,
            args.min_ssim,
        )
        report = {
            "schema": REPORT_SCHEMA,
            "quality": "diagnostic_candidate",
            "authoritative": False,
            "inputs": [
                {
                    "label": left_label,
                    "byte_count": left.stat().st_size,
                    "sha256": sha256_file(left),
                    "dimensions": {"width": left_dimensions[0], "height": left_dimensions[1]},
                    "crop": {
                        "x": left_crop[0], "y": left_crop[1],
                        "width": left_crop[2], "height": left_crop[3],
                    },
                    "crop_source": left_crop_source,
                },
                {
                    "label": right_label,
                    "byte_count": right.stat().st_size,
                    "sha256": sha256_file(right),
                    "dimensions": {"width": right_dimensions[0], "height": right_dimensions[1]},
                    "crop": {
                        "x": right_crop[0], "y": right_crop[1],
                        "width": right_crop[2], "height": right_crop[3],
                    },
                    "crop_source": right_crop_source,
                },
            ],
            "normalization": {
                "width": target[0],
                "height": target[1],
                "mode": "explicit_crop_then_lanczos_scale",
                "aspect_ratio_delta": round(
                    abs(left_crop[2] / left_crop[3] - right_crop[2] / right_crop[3]),
                    8,
                ),
            },
            "viewport_compatibility": viewport,
            "comparator": {
                "name": Path(__file__).name,
                "sha256": sha256_file(Path(__file__).resolve()),
            },
            "component_inventories": component_inventory_records,
            "source_attribute_inventory": source_attribute_record,
            "metrics": metrics,
            "ssim_score": ssim_score,
            "raw_metrics": raw_metrics,
            "rasterization_comparison": {
                "tolerance": "gaussian",
                "radius_px": RASTERIZATION_TOLERANCE_RADIUS_PX,
                "scope": ["ssim_color", "ssim_luma"],
            },
            "edge_comparison": {
                "detector": "Pillow FIND_EDGES",
                "tolerance": "gaussian",
                "radius_px": EDGE_TOLERANCE_RADIUS_PX,
            },
            "verdict": verdict,
            "difference_analysis": difference_analysis,
            "artifacts": [
                artifact_record(normalized_left, "normalized_left"),
                artifact_record(normalized_right, "normalized_right"),
                artifact_record(difference, "absolute_difference"),
                artifact_record(annotated_difference, "annotated_difference"),
                artifact_record(side_by_side, "side_by_side"),
            ],
            "tools": [{"name": "Pillow", "version": PILLOW_VERSION}],
            "limitations": [
                "A pass is a strict automated gate over complete v2 snapshots; it is not a product acceptance decision.",
                "Metrics are meaningful only when route, state, viewport, crop, and font scale are aligned.",
                "Different physical screenshot sizes are supported, but pixel metrics are not comparable when normalized content aspect ratios or orientation differ.",
                "Dynamic themes and platform rendering can lower pixel similarity without a semantic defect.",
                "Color and luma SSIM use a half-pixel Gaussian tolerance while raw_metrics preserves untolerated values; this prevents cross-platform font and stroke rasterizers from masquerading as layout differences.",
                "Edge SSIM uses a one-pixel Gaussian tolerance so subpixel font rasterization is not treated as a layout edge displacement.",
                "Source attribute ordering is a metric-weighted inspection candidate, not a proven property-level diagnosis or suggested fix.",
                "Image artifacts contain protected pixels and must remain local unless explicitly authorized.",
            ],
        }
        human_report_path.write_text(
            render_human_report(report),
            encoding="utf-8",
        )
        report["human_report"] = {
            "file": human_report_path.name,
            "byte_count": human_report_path.stat().st_size,
            "sha256": sha256_file(human_report_path),
        }
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except Exception:
        shutil.rmtree(output)
        raise
    finally:
        left_image.close()
        right_image.close()
        if normalized_left_image is not None:
            normalized_left_image.close()
        if normalized_right_image is not None:
            normalized_right_image.close()
    return {
        "ok": True,
        "schema": COMMAND_SCHEMA,
        "report": "comparison.json",
        "report_sha256": sha256_file(report_path),
        "human_report": "comparison-summary.md",
        "human_report_sha256": sha256_file(human_report_path),
        "artifact_count": len(report["artifacts"]),
        "metrics": metrics,
        "ssim_score": ssim_score,
        "verdict": report["verdict"]["status"],
    }


def main() -> int:
    try:
        result = compare(parse_args())
    except ComparisonError as error:
        print(
            json.dumps(
                {"ok": False, "schema": COMMAND_SCHEMA, "error": str(error)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
