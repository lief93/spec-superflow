from __future__ import annotations
import copy
import hashlib
import re
from collections import defaultdict
from page_snapshot import empty_style
from pathlib import Path
from typing import Any
from ui_migration.frontend.bindings import modifier_dimensions, number
from ui_migration.frontend.model import PAGE_SCHEMA, RealPageError, SOURCE_COMPONENT_TREE_SCHEMA, SOURCE_LAYOUT_PRIMITIVES, canonical_sha256
from ui_migration.frontend.relationships import select_most_specific_surface_owner, surface_height_matches_source
from ui_migration.runtime.mapping import expand_runtime_source_instances, match_source_to_runtime, resolve_runtime_source_map, runtime_semantic_key, semantic_runtime_component, source_descendants, stable_runtime_fallback_key, tree_descendants
from ui_migration.runtime.pixels import screenshot_surface_regions


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
    from ui_migration.contracts.requirements import merge_requirement_facts
    return [
        str(item["path"])
        for item in merge_requirement_facts(component)
        if isinstance(item, dict) and item.get("status") in {"unresolved", "symbolic"}
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
