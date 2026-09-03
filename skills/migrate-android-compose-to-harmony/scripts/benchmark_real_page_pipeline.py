#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


BOUNDS_PATTERN = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


class BenchmarkError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BenchmarkError(f"cannot read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise BenchmarkError(f"JSON root must be an object: {path}")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bounds(raw: str, dimensions: tuple[int, int]) -> dict[str, int] | None:
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


def append_raw(
    rows: dict[str, dict[str, Any]],
    component_id: str,
    component_bounds: dict[str, int],
    parent_id: str | None,
) -> None:
    sibling_index = len(rows[parent_id]["children_ids"]) if parent_id is not None else 0
    rows[component_id] = {
        "bounds_px": component_bounds,
        "parent_id": parent_id,
        "children_ids": [],
        "sibling_index": sibling_index,
    }
    if parent_id is not None:
        rows[parent_id]["children_ids"].append(component_id)


def independent_android_rows(
    path: Path, dimensions: tuple[int, int], package_name: str
) -> dict[str, dict[str, Any]]:
    try:
        root = ET.fromstring(path.read_bytes())
    except (OSError, ET.ParseError) as error:
        raise BenchmarkError(f"cannot read UIAutomator XML {path}: {error}") from error
    rows: dict[str, dict[str, Any]] = {}

    def walk(element: ET.Element, item_path: tuple[int, ...], nearest_parent: str | None) -> None:
        if element.tag != "node":
            for index, child in enumerate(element):
                walk(child, item_path + (index,), nearest_parent)
            return
        component_bounds = bounds(element.attrib.get("bounds", ""), dimensions)
        resource_id = element.attrib.get("resource-id", "")
        package = element.attrib.get("package", "")
        keep = (
            component_bounds is not None
            and resource_id not in {"android:id/statusBarBackground", "android:id/navigationBarBackground"}
            and (not package_name or not package or package == package_name)
        )
        parent_id = nearest_parent
        if keep:
            component_id = "runtime-" + "-".join(str(index) for index in item_path)
            append_raw(rows, component_id, component_bounds, parent_id)
            parent_id = component_id
        for index, child in enumerate(element):
            walk(child, item_path + (index,), parent_id)

    walk(root, (), None)
    return rows


def independent_harmony_rows(
    path: Path, dimensions: tuple[int, int]
) -> dict[str, dict[str, Any]]:
    root = load_json(path)
    rows: dict[str, dict[str, Any]] = {}

    def walk(node: Any, item_path: tuple[int, ...], nearest_parent: str | None) -> None:
        if not isinstance(node, dict):
            return
        attributes = node.get("attributes")
        children = node.get("children")
        parent_id = nearest_parent
        if isinstance(attributes, dict):
            component_bounds = bounds(str(attributes.get("bounds", "")), dimensions)
            kind = str(attributes.get("type", "")).strip()
            visible = str(attributes.get("visible", "true")).lower() == "true"
            if component_bounds is not None and visible and kind:
                component_id = "runtime-h-" + "-".join(str(index) for index in item_path)
                append_raw(rows, component_id, component_bounds, parent_id)
                parent_id = component_id
        if isinstance(children, list):
            for index, child in enumerate(children):
                walk(child, item_path + (index,), parent_id)

    walk(root, (), None)
    return rows


def raw_tree_accuracy(
    runtime_tree: dict[str, Any], raw_rows: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    components = runtime_tree.get("components")
    if not isinstance(components, list):
        raise BenchmarkError("runtime-tree.json has no component list")
    emitted = {
        str(item.get("id")): item
        for item in components
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    exact_ids: list[str] = []
    field_mismatches: dict[str, list[str]] = {}
    for component_id in sorted(set(raw_rows).intersection(emitted)):
        expected = raw_rows[component_id]
        actual = emitted[component_id]
        mismatches = [
            field
            for field in ("bounds_px", "parent_id", "children_ids", "sibling_index")
            if actual.get(field) != expected[field]
        ]
        if mismatches:
            field_mismatches[component_id] = mismatches
        else:
            exact_ids.append(component_id)
    denominator = max(len(raw_rows), len(emitted))
    exact_ratio = round(len(exact_ids) / denominator, 6) if denominator else 1.0
    return {
        "raw_component_count": len(raw_rows),
        "emitted_component_count": len(emitted),
        "exact_component_count": len(exact_ids),
        "exact_ratio": exact_ratio,
        "missing_component_ids": sorted(set(raw_rows).difference(emitted)),
        "extra_component_ids": sorted(set(emitted).difference(raw_rows)),
        "field_mismatches": field_mismatches,
        "verdict": "pass" if exact_ratio == 1.0 else "fail",
    }


def semantic_key_from_runtime(component: dict[str, Any]) -> str | None:
    runtime_id = component.get("runtime_id")
    if isinstance(runtime_id, str) and runtime_id:
        return runtime_id
    resource_id = component.get("resource_id")
    if not isinstance(resource_id, str) or not resource_id or resource_id.startswith("android:id/"):
        return None
    return resource_id.rsplit("/", 1)[-1]


def semantic_mapping_evidence(
    source_page: dict[str, Any], runtime_tree: dict[str, Any], page: dict[str, Any]
) -> dict[str, Any]:
    source_by_key = {
        item["semantic_key"]: item
        for item in source_page.get("components", [])
        if isinstance(item, dict) and isinstance(item.get("semantic_key"), str)
    }
    runtime_by_id = {
        item["id"]: item
        for item in runtime_tree.get("components", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    direct_stable: list[str] = []
    explicit_binding: list[str] = []
    exact_content: list[str] = []
    review_required: list[str] = []
    invalid_source_keys: list[str] = []
    for component in page.get("components", []):
        if not isinstance(component, dict) or not isinstance(component.get("semantic_key"), str):
            continue
        semantic_key = component["semantic_key"]
        source = source_by_key.get(semantic_key)
        runtime = runtime_by_id.get(component.get("id"))
        if source is None or runtime is None:
            invalid_source_keys.append(semantic_key)
            continue
        source_mapping = component.get("source_mapping")
        mapping_method = source_mapping.get("method") if isinstance(source_mapping, dict) else None
        if mapping_method == "explicit_runtime_source_map":
            explicit_binding.append(semantic_key)
            continue
        if semantic_key_from_runtime(runtime) == semantic_key:
            direct_stable.append(semantic_key)
            continue
        source_content = source.get("style", {}).get("content", {})
        runtime_content = runtime.get("style", {}).get("content", {})
        if any(
            isinstance(source_content.get(field), str)
            and source_content.get(field)
            and source_content.get(field) == runtime_content.get(field)
            for field in ("text", "content_description", "placeholder")
        ):
            exact_content.append(semantic_key)
        else:
            review_required.append(semantic_key)
    mapped_count = (
        len(direct_stable)
        + len(explicit_binding)
        + len(exact_content)
        + len(review_required)
        + len(invalid_source_keys)
    )
    proven_count = len(direct_stable) + len(explicit_binding)
    return {
        "mapped_component_count": mapped_count,
        "direct_stable_id_count": len(direct_stable),
        "explicit_runtime_source_map_count": len(explicit_binding),
        "exact_source_runtime_content_count": len(exact_content),
        "independently_proven_count": proven_count,
        "independently_proven_ratio": round(proven_count / mapped_count, 6) if mapped_count else 1.0,
        "hierarchy_or_order_review_required_count": len(review_required),
        "hierarchy_or_order_review_required_keys": review_required,
        "invalid_source_key_count": len(invalid_source_keys),
        "invalid_source_keys": invalid_source_keys,
        "interpretation": "This is a conservative evidence ratio, not statistical model accuracy.",
    }


def required_visual_fact_coverage(page: dict[str, Any]) -> dict[str, Any]:
    paths_by_type = {
        "Text": ("content.text", "typography.font_size_sp", "typography.color"),
        "BasicText": ("content.text", "typography.font_size_sp", "typography.color"),
        "ClickableText": ("content.text", "typography.font_size_sp", "typography.color"),
        "Image": ("asset.resource", "asset.content_scale"),
        "Icon": ("asset.resource", "asset.content_scale"),
        "AsyncImage": ("asset.resource", "asset.content_scale"),
        "Button": ("state.clickable", "surface.background", "surface.corner_radius_dp"),
        "IconButton": ("state.clickable", "surface.background", "surface.corner_radius_dp"),
        "FloatingActionButton": ("state.clickable", "surface.background", "surface.corner_radius_dp"),
        "SmallFloatingActionButton": ("state.clickable", "surface.background", "surface.corner_radius_dp"),
    }
    total = 0
    resolved = 0
    for component in page.get("components", []):
        if not isinstance(component, dict) or not isinstance(component.get("semantic_key"), str):
            continue
        style = component.get("style", {})
        for path in paths_by_type.get(str(component.get("type")), ()):
            section, field = path.split(".", 1)
            total += 1
            if isinstance(style.get(section), dict) and style[section].get(field) is not None:
                resolved += 1
    return {
        "required_fact_count": total,
        "resolved_fact_count": resolved,
        "unresolved_fact_count": total - resolved,
        "resolved_ratio": round(resolved / total, 6) if total else 1.0,
    }


def side_report(directory: Path, platform: str, package_name: str) -> dict[str, Any]:
    screenshot = directory / "screenshot.png"
    page = load_json(directory / "page.json")
    runtime = load_json(directory / "runtime-tree.json")
    source_page = load_json(directory / "source-page.json")
    metrics = load_json(directory / "metrics.json")
    viewport = page.get("viewport")
    if not isinstance(viewport, dict):
        raise BenchmarkError(f"page viewport is missing: {directory}")
    dimensions = (int(viewport["width_px"]), int(viewport["height_px"]))
    actual_screenshot_sha = sha256(screenshot)
    page_screenshot = page.get("capture", {}).get("screenshot", {})
    capture_binding = {
        "screenshot_sha256": actual_screenshot_sha,
        "page_matches_screenshot": page_screenshot.get("sha256") == actual_screenshot_sha,
        "runtime_tree_matches_screenshot": runtime.get("screenshot_sha256") == actual_screenshot_sha,
    }
    capture_binding["verdict"] = (
        "pass"
        if capture_binding["page_matches_screenshot"] and capture_binding["runtime_tree_matches_screenshot"]
        else "fail"
    )
    if platform == "android":
        raw_rows = independent_android_rows(directory / "uiautomator.xml", dimensions, package_name)
    else:
        raw_rows = independent_harmony_rows(directory / "uitest-layout.json", dimensions)
    source = metrics.get("source", {})
    runtime_metrics = metrics.get("runtime", {})
    return {
        "artifact_set": directory.name,
        "page": page.get("page"),
        "capture_binding": capture_binding,
        "raw_tree_accuracy": raw_tree_accuracy(runtime, raw_rows),
        "semantic_mapping_evidence": semantic_mapping_evidence(source_page, runtime, page),
        "required_visual_fact_coverage": required_visual_fact_coverage(page),
        "generator_verdict": metrics.get("verdict"),
        "source": {
            "call_count": source.get("call_count"),
            "emitted_call_count": source.get("emitted_call_count"),
            "emitted_call_ratio": source.get("emitted_call_ratio"),
            "visible_candidate_count": source.get("primitive_visible_candidate_count"),
            "visible_mapped_count": source.get("primitive_mapped_count"),
            "visible_mapping_ratio": source.get("primitive_mapping_ratio"),
            "mapped_unresolved_fact_count": source.get("mapped_unresolved_fact_count"),
            "unresolved_required_visual_fact_count": source.get("unresolved_required_visual_fact_count"),
            "unresolved_required_visual_facts": source.get("unresolved_required_visual_facts", []),
        },
        "runtime": {
            "component_count": runtime_metrics.get("component_count"),
            "semantic_component_count": runtime_metrics.get("semantic_component_count"),
            "semantic_mapped_count": runtime_metrics.get("semantic_mapped_count"),
            "semantic_mapping_ratio": runtime_metrics.get("semantic_mapping_ratio"),
        },
        "timings_ms": metrics.get("timings_ms", {}),
    }


def fidelity_report(comparison: dict[str, Any]) -> dict[str, Any]:
    analysis = comparison.get("difference_analysis", {})
    presence = analysis.get("component_presence", {})
    geometry = analysis.get("component_geometry_deltas", [])
    hierarchy = analysis.get("component_hierarchy_deltas", [])
    styles = analysis.get("component_style_deltas", [])
    verdict = comparison.get("verdict", {})
    return {
        "verdict": verdict.get("status", "fail"),
        "failure_reasons": verdict.get("failure_reasons", []),
        "ssim": comparison.get("metrics", {}),
        "missing_in_android": presence.get("missing_in_left", []),
        "missing_in_harmony": presence.get("missing_in_right", []),
        "geometry_over_1dp_count": sum(
            isinstance(item, dict) and item.get("over_1dp") is True for item in geometry
        ),
        "hierarchy_failure_count": sum(
            isinstance(item, dict) and item.get("status") == "fail" for item in hierarchy
        ),
        "style_failure_count": sum(
            isinstance(item, dict) and item.get("status") == "fail" for item in styles
        ),
    }


def build_benchmark(
    android_dir: Path,
    harmony_dir: Path,
    comparison_path: Path,
    android_package: str,
) -> dict[str, Any]:
    android = side_report(android_dir.resolve(), "android", android_package)
    harmony = side_report(harmony_dir.resolve(), "harmony", android_package)
    identity_match = android["page"] == harmony["page"] and isinstance(android["page"], dict)
    extraction_pass = identity_match and all(
        side[check]["verdict"] == "pass"
        for side in (android, harmony)
        for check in ("capture_binding", "raw_tree_accuracy")
    )
    completeness = {
        "android": {
            "source_call_ratio": android["source"]["emitted_call_ratio"],
            "visible_mapping_ratio": android["source"]["visible_mapping_ratio"],
            "runtime_semantic_mapping_ratio": android["runtime"]["semantic_mapping_ratio"],
            "unresolved_required_visual_fact_count": android["source"]["unresolved_required_visual_fact_count"],
        },
        "harmony": {
            "source_call_ratio": harmony["source"]["emitted_call_ratio"],
            "visible_mapping_ratio": harmony["source"]["visible_mapping_ratio"],
            "runtime_semantic_mapping_ratio": harmony["runtime"]["semantic_mapping_ratio"],
            "unresolved_required_visual_fact_count": harmony["source"]["unresolved_required_visual_fact_count"],
        },
        "verdict": "pass" if android["generator_verdict"] == harmony["generator_verdict"] == "pass" else "fail",
    }
    fidelity = fidelity_report(load_json(comparison_path.resolve()))
    final_pass = extraction_pass and completeness["verdict"] == "pass" and fidelity["verdict"] == "pass"
    return {
        "schema": "android-to-harmony.real-page-benchmark.v1",
        "verdict": "pass" if final_pass else "fail",
        "extraction_verdict": "pass" if extraction_pass else "fail",
        "page_state_identity_match": identity_match,
        "android": android,
        "harmony": harmony,
        "completeness": completeness,
        "fidelity": fidelity,
        "timings_ms": {
            "android_generation": android["timings_ms"].get("total"),
            "harmony_generation": harmony["timings_ms"].get("total"),
            "combined_generation": round(
                float(android["timings_ms"].get("total") or 0)
                + float(harmony["timings_ms"].get("total") or 0),
                3,
            ),
        },
        "interpretation": {
            "extraction_verdict": "Whether each JSON exactly matches its raw runtime tree and bound screenshot.",
            "completeness_verdict": "Whether source/runtime mapping and required visual facts are fully resolved.",
            "fidelity_verdict": "Whether Android and Harmony page structure, style, geometry, and pixels pass comparison.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Independently benchmark real Android/Harmony page JSON extraction and visual fidelity."
    )
    parser.add_argument("--android-dir", required=True, type=Path)
    parser.add_argument("--harmony-dir", required=True, type=Path)
    parser.add_argument("--comparison", required=True, type=Path)
    parser.add_argument("--android-package", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = build_benchmark(
            args.android_dir, args.harmony_dir, args.comparison, args.android_package
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "verdict": result["verdict"],
                    "extraction_verdict": result["extraction_verdict"],
                    "completeness_verdict": result["completeness"]["verdict"],
                    "fidelity_verdict": result["fidelity"]["verdict"],
                    "output": str(args.output),
                    "output_sha256": sha256(args.output),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except BenchmarkError as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
