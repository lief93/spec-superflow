from __future__ import annotations
import copy
import re
from collections import defaultdict
from component_required_facts import normalized_layout_rules
from typing import Any
from ui_migration.frontend.page_model import IMAGE_TYPES, MANIFEST_SCHEMA, OVERLAY_NAME_MARKERS, STATE_SCHEMA, TEXT_TYPES, clean_number, finite_number, nested_modifier_arguments, resolved_alignment, semantic_expression, style_group, uniform_corner_radius
from ui_migration.frontend.reference_layout import SourceLayout
from ui_migration.frontend.source_tree import SourceTree


def rgba_fill(color: str, opacity: float = 1.0) -> dict[str, Any]:
    normalized = color.lstrip("#")
    if len(normalized) == 8:
        alpha = int(normalized[0:2], 16) / 255
        red = int(normalized[2:4], 16) / 255
        green = int(normalized[4:6], 16) / 255
        blue = int(normalized[6:8], 16) / 255
    elif len(normalized) == 6:
        alpha = 1.0
        red = int(normalized[0:2], 16) / 255
        green = int(normalized[2:4], 16) / 255
        blue = int(normalized[4:6], 16) / 255
    else:
        raise ValueError(f"unsupported color: {color}")
    alpha *= opacity
    return {
        "type": "color",
        "color": {
            "a": alpha,
            "r": red,
            "g": green,
            "b": blue,
            "value": f"rgba({round(red * 255)},{round(green * 255)},{round(blue * 255)},{alpha:g})",
            "type": "percentage",
            "boundVariables": {},
        },
        "opacity": alpha,
        "isEnabled": True,
        "blendMode": 0,
        "boundVariables": {},
    }


def lanhu_frame(frame_dp: dict[str, float], scale: float) -> dict[str, int | float]:
    return {
        "left": clean_number(frame_dp["x"] * scale),
        "top": clean_number(frame_dp["y"] * scale),
        "width": clean_number(frame_dp["width"] * scale),
        "height": clean_number(frame_dp["height"] * scale),
    }


def radius_value(value: Any, scale: float) -> dict[str, int | float]:
    if isinstance(value, dict):
        return {
            "topLeft": clean_number((finite_number(value.get("top_left")) or 0.0) * scale),
            "topRight": clean_number((finite_number(value.get("top_right")) or 0.0) * scale),
            "bottomRight": clean_number((finite_number(value.get("bottom_right")) or 0.0) * scale),
            "bottomLeft": clean_number((finite_number(value.get("bottom_left")) or 0.0) * scale),
        }
    number = finite_number(value) or 0.0
    scaled = clean_number(number * scale)
    return {"topLeft": scaled, "topRight": scaled, "bottomRight": scaled, "bottomLeft": scaled}


def layer_type(component_type: str, surface: dict[str, Any]) -> str:
    if component_type in TEXT_TYPES:
        return "text"
    if component_type in IMAGE_TYPES:
        return "image"
    if surface.get("background") or surface.get("border"):
        return "shapeLayer"
    return "group"


def required_phase_paths(node: dict[str, Any], phase: str) -> list[str]:
    from ui_migration.contracts.consumption import target_fact_phase
    paths = [
        str(item.get("path"))
        for item in node.get("required_facts") or []
        if isinstance(item, dict)
        and item.get("status") in {"resolved", "default_resolved"}
        and isinstance(item.get("path"), str)
    ]
    return sorted(path for path in paths if target_fact_phase(path) == phase)


def draw_output_paths(node: dict[str, Any], layer: dict[str, Any]) -> list[str]:
    emitted: set[str] = {"structure.type", "style.state.visible"}
    style = layer["style"]
    if style.get("fills"):
        emitted.add("style.surface.background")
    if style.get("borders"):
        emitted.add("style.surface.border")
    if layer.get("clipped"):
        emitted.add("style.surface.clip")
    if layer.get("opacity") is not None:
        emitted.add("style.surface.alpha")
    for source_name, lanhu_name in (
        ("font_size_sp", "fontSize"),
        ("font_weight", "fontWeight"),
        ("color", "color"),
    ):
        if lanhu_name in style:
            emitted.add(f"style.typography.{source_name}")
    if "text" in layer:
        emitted.add("style.content.text")
    if "exportImageUrl" in layer:
        emitted.add("style.asset.resource")
    if finite_number(style_group(node, "transform").get("rotation_degrees")) is not None:
        emitted.add("style.transform.rotation_degrees")
    return sorted(emitted)


def component_phase_trace(
    tree: SourceTree,
    layout: SourceLayout,
    component_id: str,
    layer: dict[str, Any],
) -> dict[str, Any]:
    node = tree.nodes[component_id]
    relationship_ids = sorted(
        relationship["id"]
        for relationships in layout.relationships_by_container.values()
        for relationship in relationships
        if relationship.get("subject_id") == component_id
        and isinstance(relationship.get("id"), str)
    )
    consumed_relationship_ids = sorted(
        set(relationship_ids) & layout.consumed_relationship_ids
    )
    emitted = draw_output_paths(node, layer)
    layout.drawn_component_ids.add(component_id)
    layout.draw_output_paths[component_id] = emitted
    return {
        "schema": "android-to-harmony.render-phase-trace.v1",
        "phaseOrder": ["measure", "layout", "draw"],
        "measure": {
            "status": "consumed" if component_id in layout.measured_sizes else "missing",
            "inputPaths": required_phase_paths(node, "measure"),
            "outputSizeDp": {
                key: clean_number(value)
                for key, value in layout.measured_sizes.get(component_id, {}).items()
            },
        },
        "layout": {
            "status": "consumed" if component_id in layout.frames else "missing",
            "inputPaths": required_phase_paths(node, "layout"),
            "relationshipIds": relationship_ids,
            "consumedRelationshipIds": consumed_relationship_ids,
            "outputFrameDp": {
                key: clean_number(value)
                for key, value in layout.frames.get(component_id, {}).items()
            },
        },
        "draw": {
            "status": "consumed",
            "inputPaths": required_phase_paths(node, "draw"),
            "emittedPaths": emitted,
        },
    }


def build_phase_consumption_gate(layout: SourceLayout) -> dict[str, Any]:
    failures = list(layout.phase_failures)
    component_count = len(layout.tree.nodes)
    if not layout.measure_complete or len(layout.measured_sizes) != component_count:
        failures.append({
            "phase": "measure",
            "component_id": layout.tree.root_id,
            "relationship_id": "",
            "reason": "not every source component produced a measured size",
        })
    if not layout.layout_complete or len(layout.frames) != component_count:
        failures.append({
            "phase": "layout",
            "component_id": layout.tree.root_id,
            "relationship_id": "",
            "reason": "not every measured component produced a layout frame",
        })
    if len(layout.drawn_component_ids) != component_count:
        failures.append({
            "phase": "draw",
            "component_id": layout.tree.root_id,
            "relationship_id": "",
            "reason": "not every laid-out component produced a draw node",
        })
    expected_relationship_ids = {
        relationship["id"]
        for relationships in layout.relationships_by_container.values()
        for relationship in relationships
        if relationship.get("active_constraints")
        and isinstance(relationship.get("id"), str)
    }
    missing_relationship_ids = sorted(
        expected_relationship_ids - layout.consumed_relationship_ids
    )
    for relationship_id in missing_relationship_ids:
        failures.append({
            "phase": "layout",
            "component_id": layout.tree.root_id,
            "relationship_id": relationship_id,
            "reason": "active layout relationship was parsed but not consumed",
        })
    return {
        "schema": "android-to-harmony.render-phase-gate.v1",
        "verdict": "pass" if not failures else "fail",
        "phase_order": ["measure", "layout", "draw"],
        "component_count": component_count,
        "measured_component_count": len(layout.measured_sizes),
        "laid_out_component_count": len(layout.frames),
        "drawn_component_count": len(layout.drawn_component_ids),
        "consumed_relationship_ids": sorted(layout.consumed_relationship_ids),
        "failure_count": len(failures),
        "failures": failures,
    }


def lanhu_layer(
    tree: SourceTree,
    layout: SourceLayout,
    component_id: str,
    scale: float,
) -> dict[str, Any]:
    node = tree.nodes[component_id]
    component_type = str(node.get("type") or "Group")
    surface = style_group(node, "surface")
    typography = style_group(node, "typography")
    content = style_group(node, "content")
    asset = style_group(node, "asset")
    frame = lanhu_frame(layout.frames[component_id], scale)
    opacity = finite_number(surface.get("alpha"))
    if opacity is None:
        opacity = 1.0
    background = surface.get("background")
    fills: list[dict[str, Any]] = []
    if isinstance(background, dict) and isinstance(background.get("color"), str):
        try:
            fills.append(rgba_fill(background["color"], opacity))
        except ValueError:
            pass
    borders: list[dict[str, Any]] = []
    border = surface.get("border")
    if isinstance(border, dict):
        width = finite_number(border.get("width_dp"))
        color = border.get("color")
        if width is not None and width >= 0 and isinstance(color, str):
            try:
                scaled_width = clean_number(width * scale)
                borders.append(
                    {
                        "blendMode": 0,
                        "isEnabled": True,
                        "opacity": 1,
                        "lineAlignment": "inside",
                        "style": str(border.get("style") or "solid"),
                        "width": scaled_width,
                        "lineCap": "none",
                        "lineJoin": "miter",
                        "miterLimit": 4,
                        "widths": {
                            "left": scaled_width,
                            "right": scaled_width,
                            "top": scaled_width,
                            "bottom": scaled_width,
                        },
                        "color": rgba_fill(color, 1)["color"],
                    }
                )
            except ValueError:
                pass
    source_radius = surface.get("corner_radius_dp")
    if source_radius is None and surface.get("clip") is True:
        if any(
            arguments.strip() == "CircleShape"
            for arguments in nested_modifier_arguments(node, "clip")
        ):
            component_frame = layout.frames[component_id]
            source_radius = uniform_corner_radius(
                min(component_frame["width"], component_frame["height"]) / 2
            )
    radius = radius_value(source_radius, scale)
    style: dict[str, Any] = {
        "isEnabled": True,
        "opacity": opacity,
        "blendMode": 0,
        "fills": fills,
        "borders": borders,
        "shadows": surface.get("shadows") or [],
        "blurs": [],
    }
    font_size = finite_number(typography.get("font_size_sp"))
    if font_size is not None:
        style["fontSize"] = clean_number(font_size * scale)
    if typography.get("font_weight") is not None:
        style["fontWeight"] = typography["font_weight"]
    if isinstance(typography.get("color"), str):
        style["color"] = typography["color"]
    text = content.get("text")
    has_asset = isinstance(asset.get("resource"), str) and bool(asset["resource"])
    migration_source = copy.deepcopy(node.get("source") or {})
    migration_source["modifiers"] = copy.deepcopy(node.get("modifiers") or [])
    if node.get('slot_argument_name'):
        migration_source['slot_argument_name'] = node['slot_argument_name']
    if node.get('slot_invocation'):
        migration_source['slot_invocation'] = copy.deepcopy(node['slot_invocation'])
    migration_source["layoutRules"] = copy.deepcopy(
        node.get("layout_rules") or normalized_layout_rules(node)
    )
    migration_style = copy.deepcopy(node.get("style") or {})
    source_alignment = resolved_alignment(node)
    if source_alignment:
        migration_style.setdefault("layout", {})["alignment"] = source_alignment
    resolved_padding = layout.effective_padding(node)
    migration_layout = migration_style.setdefault("layout", {})
    if migration_layout.get("padding_dp") is None and any(
        abs(value) > 0.001 for value in resolved_padding.values()
    ):
        migration_layout["padding_dp"] = {
            edge: clean_number(value) for edge, value in resolved_padding.items()
        }
    result: dict[str, Any] = {
        "id": component_id,
        "name": str(node.get("semantic_key") or component_type),
        "type": layer_type(component_type, surface),
        "visible": style_group(node, "state").get("visible") is not False,
        "clipped": bool(surface.get("clip")),
        "isMask": False,
        "opacity": opacity,
        "rotation": finite_number(style_group(node, "transform").get("rotation_degrees")) or 0,
        "frame": frame,
        "realFrame": dict(frame),
        "combinedFrame": dict(frame),
        "radius": radius,
        "paths": [],
        "style": style,
        "hasExportImage": has_asset,
        "hasExportDDSImage": False,
        "layers": [
            lanhu_layer(tree, layout, child_id, scale)
            for child_id in tree.children.get(component_id, [])
        ],
        "origin": "android-source",
        "migration": {
            "schema": "android-to-harmony.lanhu-node.v1",
            "componentType": component_type,
            "definitionId": node.get('definition_id'),
            "componentKind": node.get('component_kind'),
            "invocationBindings": copy.deepcopy(node.get('invocation_bindings') or {}),
            "semanticKey": node.get("semantic_key"),
            "source": migration_source,
            "style": migration_style,
            "customDraw": copy.deepcopy(node.get("custom_draw")),
            "provenance": copy.deepcopy(node.get("provenance") or []),
            "unresolved": copy.deepcopy(node.get("unresolved") or []),
            "requiredFacts": copy.deepcopy(node.get("required_facts") or []),
            "geometryStatus": layout.geometry_status[component_id],
            "geometryEvidence": copy.deepcopy(
                layout.geometry_reasons.get(component_id, [])
            ),
        },
    }
    if isinstance(text, str) or result["type"] == "text":
        result["text"] = text
    if has_asset:
        result["exportImageUrl"] = asset["resource"]
    if result["type"] == "shapeLayer":
        result["paths"] = [{"type": "rect", "frame": dict(frame), "radius": radius}]
    result["migration"]["phaseTrace"] = component_phase_trace(
        tree, layout, component_id, result
    )
    return result


def source_assets(tree: SourceTree) -> list[str]:
    return sorted(
        {
            resource
            for node in tree.nodes.values()
            if isinstance((resource := style_group(node, "asset").get("resource")), str)
            and resource
        }
    )


def component_manifest(tree: SourceTree, layout: SourceLayout) -> dict[str, Any]:
    definitions_by_id = {
        definition.get("id"): definition
        for definition in tree.payload.get("component_definitions") or []
        if isinstance(definition, dict) and isinstance(definition.get("id"), str)
    }
    instances_by_definition: dict[str, list[str]] = defaultdict(list)
    for component_id in tree.order:
        definition_id = tree.nodes[component_id].get("definition_id")
        if isinstance(definition_id, str):
            instances_by_definition[definition_id].append(component_id)
    definitions = []
    for definition_id, definition in definitions_by_id.items():
        item = dict(definition)
        item["instance_ids"] = instances_by_definition.get(definition_id, [])
        definitions.append(item)
    for definition_id in sorted(set(instances_by_definition) - set(definitions_by_id)):
        definitions.append(
            {
                "id": definition_id,
                "type": None,
                "identity": None,
                "component_kind": "unresolved",
                "declared_from": None,
                "dependency": None,
                "instance_ids": instances_by_definition[definition_id],
            }
        )
    instances = []
    for component_id in tree.order:
        node = tree.nodes[component_id]
        instances.append(
            {
                "id": component_id,
                "type": node.get("type"),
                "semantic_key": node.get("semantic_key"),
                "definition_id": node.get("definition_id"),
                "component_kind": node.get('component_kind'),
                "invocation_bindings": copy.deepcopy(node.get('invocation_bindings') or {}),
                "parent_id": node.get("parent_id"),
                "children_ids": tree.children.get(component_id, []),
                "sibling_index": node.get("sibling_index"),
                "frame_dp": {
                    key: clean_number(value) for key, value in layout.frames[component_id].items()
                },
                "resolved_layout": {
                    "padding_dp": {
                        key: clean_number(value)
                        for key, value in layout.effective_padding(node).items()
                    }
                },
                "layout_rules": copy.deepcopy(
                    node.get("layout_rules") or normalized_layout_rules(node)
                ),
                "geometry_status": layout.geometry_status[component_id],
                "geometry_evidence": layout.geometry_reasons.get(component_id, []),
                "style": node.get("style") or {},
                "custom_draw": node.get("custom_draw"),
                "source": node.get("source") or {},
                "provenance": node.get("provenance") or [],
                "unresolved": node.get("unresolved") or [],
                "required_facts": node.get("required_facts") or [],
            }
        )
    return {
        "schema": MANIFEST_SCHEMA,
        "page": tree.payload.get("page") or {},
        "source_schema": tree.payload.get("schema"),
        "source_status": tree.payload.get("status"),
        "root_instance_id": tree.root_id,
        "source_instance_count": len(tree.nodes),
        "definitions": definitions,
        "instances": instances,
        "layout_relationships": tree.payload.get("layout_relationships") or [],
        "limitations": tree.payload.get("limitations") or [],
        "state_projection": tree.payload.get("state_projection"),
        "geometry_summary": {
            status: sum(1 for value in layout.geometry_status.values() if value == status)
            for status in ("source_resolved", "source_inferred", "unresolved")
        },
    }


def state_manifest(tree: SourceTree) -> dict[str, Any]:
    page = tree.payload.get("page") or {}
    overlay_ids = [
        component_id
        for component_id in tree.order
        if any(marker in str(tree.nodes[component_id].get("type") or "") for marker in OVERLAY_NAME_MARKERS)
    ]
    return {
        "schema": STATE_SCHEMA,
        "page_id": page.get("id"),
        "source_root": tree.payload.get("root") or {},
        "states": [
            {
                "id": page.get("state"),
                "version_json": "version_json.json",
                "base_state_id": None,
                "overlay_layer_ids": overlay_ids,
                "classification": "overlay" if overlay_ids else "full_page",
            }
        ],
    }


def page_font_faces(source: dict[str, Any]) -> list[dict[str, Any]]:
    from kotlin_psi import parse_expression
    from ui_migration.semantics.syntax import call_from

    used = {style_group(c, "typography").get("font_family") for c in source.get("components", [])}
    result = [dict(face) for face in source.get('runtime_font_faces', []) if face.get('family') in used]
    weights = {"Normal": 400, "Medium": 500, "SemiBold": 600, "Bold": 700, "Light": 300, "Thin": 100, "ExtraLight": 200, "ExtraBold": 800, "Black": 900}
    weights.update({f'W{weight}': weight for weight in range(100, 1000, 100)})
    for token in source.get("source_tokens", []):
        if token.get("kind") not in {"font", "font_family"} or token.get("name") not in used:
            continue
        family = call_from(parse_expression(token.get('expression', '')))
        if family is None:
            continue
        for item in family.arguments:
            font = call_from(item['value'])
            if font is None or font.qualified_name.rsplit('.', 1)[-1] != 'Font':
                continue
            resource_node = font.argument('resId', 0)
            weight_node = font.argument('weight', 1)
            resource = (resource_node or {}).get('text', '').strip()
            weight_name = (weight_node or {}).get('text', 'FontWeight.Normal').rsplit('.', 1)[-1]
            if re.fullmatch(r'R\.font\.\w+', resource) and weight_name in weights:
                result.append({'family': token['name'], 'resource': resource.rsplit('.', 1)[-1],
                               'weight': weights[weight_name]})
    return result


def non_rendering_argument_calls(source: dict[str, Any]) -> list[str]:
    nodes = {node["id"]: node for node in source.get("components", [])}
    result = []
    for node in nodes.values():
        parent = nodes.get(node.get("parent_id"))
        if node.get("children_ids") or not parent or parent.get("type") not in {"Image", "Icon", "AsyncImage"}:
            continue
        for name in ("painter", "imageVector", "model", "placeholder", "error", "fallback"):
            expression = semantic_expression(parent, name)
            if re.match(rf"^{re.escape(node['type'])}\s*\(", expression.strip()):
                result.append(node["id"])
                break
    return result
