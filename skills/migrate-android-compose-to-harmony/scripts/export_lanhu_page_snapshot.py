#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


VERSION_KEYS = {"meta", "assets", "artboard"}
MANIFEST_SCHEMA = "android-to-harmony.lanhu-component-manifest.v1"
PAGE_SCHEMA = "android-to-harmony.page-snapshot.v2"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export a generator-compatible Android page snapshot whose geometry comes "
            "from Lanhu-compatible version_json and whose semantics come from the source manifest."
        )
    )
    parser.add_argument("--version-json", required=True, type=Path)
    parser.add_argument("--component-manifest", required=True, type=Path)
    parser.add_argument("--screenshot", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--density", required=True, type=float)
    parser.add_argument("--font-scale", type=float, default=1.0)
    return parser.parse_args()


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def require_positive(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{label} must be positive")
    return number


def require_frame(value: Any, label: str) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} has no frame")
    keys = ("left", "top", "width", "height")
    if any(isinstance(value.get(key), bool) or not isinstance(value.get(key), (int, float)) for key in keys):
        raise ValueError(f"{label} frame must contain numeric left/top/width/height")
    frame = {key: float(value[key]) for key in keys}
    if any(not math.isfinite(number) for number in frame.values()):
        raise ValueError(f"{label} frame contains a non-finite number")
    return frame


def flatten_layers(artboard: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    def visit(layer: Any) -> None:
        if not isinstance(layer, dict) or not isinstance(layer.get("id"), str):
            raise ValueError("every version_json layer must have a string id")
        layer_id = layer["id"]
        if layer_id in by_id:
            raise ValueError(f"duplicate version_json layer id: {layer_id}")
        require_frame(layer.get("frame"), f"layer {layer_id}")
        by_id[layer_id] = layer
        order.append(layer_id)
        children = layer.get("layers") or []
        if not isinstance(children, list):
            raise ValueError(f"layer {layer_id} layers must be a list")
        for child in children:
            visit(child)

    layers = artboard.get("layers")
    if not isinstance(layers, list) or not layers:
        raise ValueError("version_json artboard must contain layers")
    for layer in layers:
        visit(layer)
    return by_id, order


def frame_dp(layer: dict[str, Any], scale: float) -> dict[str, float]:
    frame = require_frame(layer.get("frame"), f"layer {layer.get('id')}")
    return {
        "x": frame["left"] / scale,
        "y": frame["top"] / scale,
        "width": frame["width"] / scale,
        "height": frame["height"] / scale,
    }


def clipped_frame(
    frame: dict[str, float], viewport_width: float, viewport_height: float
) -> dict[str, float] | None:
    left = max(0.0, frame["x"])
    top = max(0.0, frame["y"])
    right = min(viewport_width, frame["x"] + frame["width"])
    bottom = min(viewport_height, frame["y"] + frame["height"])
    if right <= left or bottom <= top:
        return None
    return {"x": left, "y": top, "width": right - left, "height": bottom - top}


def first_call_id(instance: dict[str, Any]) -> str:
    source = instance.get("source")
    attributes = source.get("attributes") if isinstance(source, dict) else None
    if isinstance(attributes, list):
        for attribute in attributes:
            if isinstance(attribute, dict) and isinstance(attribute.get("call_id"), str):
                return attribute["call_id"]
    return f"unavailable:{instance['id']}"


def export(args: argparse.Namespace) -> dict[str, Any]:
    density = require_positive(args.density, "density")
    font_scale = require_positive(args.font_scale, "font scale")
    version = read_object(args.version_json)
    if set(version) != VERSION_KEYS:
        raise ValueError("version_json must contain exactly meta/assets/artboard")
    meta = version.get("meta")
    scale = require_positive(meta.get("sliceScale") if isinstance(meta, dict) else None, "sliceScale")
    artboard = version.get("artboard")
    if not isinstance(artboard, dict):
        raise ValueError("version_json artboard is malformed")
    artboard_frame = require_frame(artboard.get("frame"), "artboard")
    viewport_width = require_positive(artboard_frame["width"] / scale, "viewport width")
    viewport_height = require_positive(artboard_frame["height"] / scale, "viewport height")
    layers_by_id, layer_order = flatten_layers(artboard)

    manifest = read_object(args.component_manifest)
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError("component manifest schema is unsupported")
    raw_instances = manifest.get("instances")
    if not isinstance(raw_instances, list):
        raise ValueError("component manifest instances must be a list")
    instances: dict[str, dict[str, Any]] = {}
    for instance in raw_instances:
        if not isinstance(instance, dict) or not isinstance(instance.get("id"), str):
            raise ValueError("every component manifest instance must have a string id")
        if instance["id"] in instances:
            raise ValueError(f"duplicate component manifest instance id: {instance['id']}")
        instances[instance["id"]] = instance
    if set(instances) != set(layers_by_id):
        missing_layers = sorted(set(instances) - set(layers_by_id))
        missing_instances = sorted(set(layers_by_id) - set(instances))
        raise ValueError(
            "version_json/component manifest instance mismatch: "
            f"missing_layers={missing_layers}, missing_instances={missing_instances}"
        )

    visible_frames: dict[str, dict[str, float]] = {}
    elided: list[dict[str, str]] = []
    for component_id in layer_order:
        frame = frame_dp(layers_by_id[component_id], scale)
        clipped = clipped_frame(frame, viewport_width, viewport_height)
        if clipped is None:
            instance = instances[component_id]
            elided.append(
                {
                    "source_semantic_key": str(instance.get("semantic_key") or component_id),
                    "source_call_id": first_call_id(instance),
                    "reason": "outside_artboard",
                }
            )
        else:
            visible_frames[component_id] = clipped

    def visible_parent(component_id: str) -> str | None:
        parent_id = instances[component_id].get("parent_id")
        visited: set[str] = set()
        while isinstance(parent_id, str):
            if parent_id in visited:
                raise ValueError(f"component manifest parent cycle at {component_id}")
            visited.add(parent_id)
            if parent_id not in instances:
                raise ValueError(f"component manifest has unknown parent: {parent_id}")
            if parent_id in visible_frames:
                return parent_id
            parent_id = instances[parent_id].get("parent_id")
        return None

    parent_by_id = {component_id: visible_parent(component_id) for component_id in visible_frames}
    children_by_id: dict[str, list[str]] = {component_id: [] for component_id in visible_frames}
    for component_id in layer_order:
        if component_id not in visible_frames:
            continue
        parent_id = parent_by_id[component_id]
        if parent_id is not None:
            children_by_id[parent_id].append(component_id)

    components: list[dict[str, Any]] = []
    for component_id in layer_order:
        if component_id not in visible_frames:
            continue
        instance = instances[component_id]
        parent_id = parent_by_id[component_id]
        siblings = children_by_id[parent_id] if parent_id is not None else [
            item for item in layer_order if item in visible_frames and parent_by_id[item] is None
        ]
        components.append(
            {
                "id": component_id,
                "type": str(instance.get("type") or layers_by_id[component_id].get("type") or "Group"),
                "semantic_key": instance.get("semantic_key"),
                "bounds_dp": visible_frames[component_id],
                "parent_id": parent_id,
                "children_ids": children_by_id[component_id],
                "sibling_index": siblings.index(component_id),
                "parent_mapping": "source-semantic-ancestor",
                "style": instance.get("style") or {},
                "custom_draw": instance.get("custom_draw"),
                "provenance": instance.get("provenance") or [],
                "unresolved": instance.get("unresolved") or [],
                "source": instance.get("source") or {"attributes": []},
            }
        )

    screenshot = args.screenshot.resolve()
    if not screenshot.is_file() or screenshot.is_symlink():
        raise ValueError("screenshot must be an existing regular file")
    page = manifest.get("page") or {}
    payload = {
        "schema": PAGE_SCHEMA,
        "status": "candidate_requires_review",
        "authoritative": False,
        "platform": "android",
        "page": {"id": page.get("id"), "state": page.get("state")},
        "viewport": {
            "width_px": round(viewport_width * density),
            "height_px": round(viewport_height * density),
            "width_dp": viewport_width,
            "height_dp": viewport_height,
            "density": density,
            "font_scale": font_scale,
            "orientation": "portrait" if viewport_height >= viewport_width else "landscape",
            "safe_area_px": {"left": 0, "top": 0, "right": 0, "bottom": 0},
            "safe_area_dp": {"left": 0, "top": 0, "right": 0, "bottom": 0},
            "content_bounds_px": {
                "x": 0,
                "y": 0,
                "width": round(viewport_width * density),
                "height": round(viewport_height * density),
            },
            "content_bounds_dp": {
                "x": 0,
                "y": 0,
                "width": viewport_width,
                "height": viewport_height,
            },
            "insets_source": "version_json_content_artboard",
        },
        "capture": {
            "screenshot": {
                "file": screenshot.name,
                "byte_count": screenshot.stat().st_size,
                "sha256": sha256_file(screenshot),
            }
        },
        "input_hashes": {
            "version_json_sha256": sha256_file(args.version_json),
            "component_manifest_sha256": sha256_file(args.component_manifest),
            "screenshot_sha256": sha256_file(screenshot),
            "geometry_role": "version_json",
            "semantics_and_style_role": "component_manifest",
            "screenshot_role": "evidence_binding_only",
        },
        "components": components,
        "unmapped_source_components": [],
        "unmapped_visual_fact_components": [],
        "runtime_elided_source_components": elided,
        "limitations": [
            *(manifest.get("limitations") or []),
            "Screenshot pixels are not used to generate component geometry or style.",
            "Components outside the current artboard are retained only in the source manifest.",
        ],
    }
    write_json(args.output, payload)
    return {
        "status": "exported",
        "output": str(args.output.resolve()),
        "component_count": len(components),
        "elided_count": len(elided),
    }


def main() -> int:
    try:
        result = export(parse_args())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
