#!/usr/bin/env python3
from __future__ import annotations
from component_required_facts import build_required_facts
from component_required_facts import required_fact_gate
from pathlib import Path
from typing import Any
from ui_migration.frontend.fixed_state import evaluate_expression
from ui_migration.frontend.fixed_state import evaluate_static_call
from ui_migration.frontend.fixed_state import evaluate_value_leaf
from ui_migration.frontend.fixed_state import project_progress_ring
from ui_migration.frontend.fixed_state import project_source_page
from ui_migration.frontend.fixed_state import resolve_input_decoration
from ui_migration.frontend.fixed_state import set_path
from ui_migration.frontend.fixed_state import stroke_width
from ui_migration.frontend.lanhu_export import build_phase_consumption_gate
from ui_migration.frontend.lanhu_export import component_manifest
from ui_migration.frontend.lanhu_export import component_phase_trace
from ui_migration.frontend.lanhu_export import draw_output_paths
from ui_migration.frontend.lanhu_export import lanhu_frame
from ui_migration.frontend.lanhu_export import lanhu_layer
from ui_migration.frontend.lanhu_export import layer_type
from ui_migration.frontend.lanhu_export import non_rendering_argument_calls
from ui_migration.frontend.lanhu_export import page_font_faces
from ui_migration.frontend.lanhu_export import radius_value
from ui_migration.frontend.lanhu_export import required_phase_paths
from ui_migration.frontend.lanhu_export import rgba_fill
from ui_migration.frontend.lanhu_export import source_assets
from ui_migration.frontend.lanhu_export import state_manifest
from ui_migration.frontend.normalization import expand_ordered_layout_modifiers
from ui_migration.frontend.normalization import expand_surface_padding
from ui_migration.frontend.normalization import expand_material_touch_targets
from ui_migration.frontend.normalization import resolve_native_content_colors
from ui_migration.frontend.normalization import resolve_scaffold_padding
from ui_migration.frontend.page_model import HORIZONTAL_TYPES
from ui_migration.frontend.page_model import IMAGE_TYPES
from ui_migration.frontend.page_model import MANIFEST_SCHEMA
from ui_migration.frontend.page_model import OVERLAY_NAME_MARKERS
from ui_migration.frontend.page_model import OVERLAY_TYPES
from ui_migration.frontend.page_model import SOURCE_SCHEMA
from ui_migration.frontend.page_model import STATE_SCHEMA
from ui_migration.frontend.page_model import TEXT_TYPES
from ui_migration.frontend.page_model import UNRESOLVED
from ui_migration.frontend.page_model import VERTICAL_TYPES
from ui_migration.frontend.page_model import arrangement_spacing
from ui_migration.frontend.page_model import call_arguments
from ui_migration.frontend.page_model import clean_number
from ui_migration.frontend.page_model import component_dimensions
from ui_migration.frontend.page_model import edge_values
from ui_migration.frontend.page_model import finite_number
from ui_migration.frontend.page_model import has_modifier
from ui_migration.frontend.page_model import lookup_path
from ui_migration.frontend.page_model import modifier_argument
from ui_migration.frontend.page_model import nested_modifier_arguments
from ui_migration.frontend.page_model import offset_values
from ui_migration.frontend.page_model import parse_padding_expression
from ui_migration.frontend.page_model import relative_dimension
from ui_migration.frontend.page_model import resolved_alignment
from ui_migration.frontend.page_model import semantic_expression
from ui_migration.frontend.page_model import split_top_level
from ui_migration.frontend.page_model import style_group
from ui_migration.frontend.page_model import uniform_corner_radius
from ui_migration.frontend.page_model import uses_parent_width
from ui_migration.frontend.reference_layout import SourceLayout
from ui_migration.frontend.source_tree import SourceTree
import argparse
import json
import copy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a Lanhu-compatible version_json and source sidecars from an "
            "Android source-page specification. Runtime captures are not inputs."
        )
    )
    parser.add_argument("--source-page", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--viewport-width-dp", required=True, type=float)
    parser.add_argument("--viewport-height-dp", required=True, type=float)
    parser.add_argument("--slice-scale", type=float, default=2.0)
    parser.add_argument("--device", default="Android source layout")
    parser.add_argument('--api-adapters', type=Path,
                        help='Explicit trusted Python adapter manifest with pinned module SHA-256 values.')
    parser.add_argument('--preserve-component-ui-states', action='store_true',
                        help='Keep supported business-component UI branches; page state remains fixed.')
    parser.add_argument(
        "--state-fixture",
        type=Path,
        help="Optional explicit page-state values used to select source branches and expand lists.",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def generate(args: argparse.Namespace, *, projected_payload=None) -> dict[str, Any]:
    from layout_expressions import needs_layout_projection
    from ui_migration.frontend.material_defaults import DEFAULT_CONTROL_TYPES
    if args.viewport_width_dp <= 0 or args.viewport_height_dp <= 0:
        raise ValueError("viewport dimensions must be positive")
    if args.slice_scale <= 0:
        raise ValueError("slice scale must be positive")
    source_payload = copy.deepcopy(projected_payload) if projected_payload is not None else read_json(args.source_page)
    raw_payload = copy.deepcopy(source_payload)
    from ui_migration.frontend.api_adapters.loader import load_adapters
    from ui_migration.frontend.api_adapters.builtins import BUILTIN_ADAPTERS
    registry = load_adapters(getattr(args, 'api_adapters', None), BUILTIN_ADAPTERS)
    state_projection = None
    if projected_payload is not None:
        pass
    elif args.state_fixture is not None:
        source_payload, state_projection = project_source_page(
            source_payload, read_json(args.state_fixture), allow_unresolved=True, api_registry=registry
        )
    elif (source_payload.get('style_definitions') or {}).get('tokenMappings') or (source_payload.get('style_definitions') or {}).get('componentDefaults') or getattr(args, 'api_adapters', None) is not None or any(
        isinstance(node, dict) and (node.get("visibility_condition") or node.get("list_item_context")
                                   or node.get('component_kind') == 'project_component'
                                   or (node.get('type') in DEFAULT_CONTROL_TYPES - {'Card', 'Surface'}
                                       and not node.get('source', {}).get('material_defaults_profile'))
                                   or needs_layout_projection(node)
                                   or any(m.get('name') == 'then' for m in node.get('modifiers', [])))
        for node in source_payload.get("components") or []
    ):
        source_payload, state_projection = project_source_page(source_payload, {
            "schema": "android-to-harmony.page-state-fixture.v1",
            "page": source_payload.get("page"),
            "values": {},
        }, allow_unresolved=True, api_registry=registry)
    catalogs = []
    if projected_payload is None and getattr(args, 'preserve_component_ui_states', False):
        from ui_migration.frontend.component_ui_states import preserve_component_states
        fixture = read_json(args.state_fixture) if args.state_fixture else {
            'schema':'android-to-harmony.page-state-fixture.v1', 'page':raw_payload['page'], 'values':{}}
        source_payload, catalogs = preserve_component_states(raw_payload, source_payload, fixture, registry)
    resolve_native_content_colors(source_payload)
    for node in source_payload.get('components', []):
        if 'input_decoration' not in (node.get('source') or {}):
            resolve_input_decoration(node, {})
    property_calls = non_rendering_argument_calls(source_payload)
    resolve_scaffold_padding(source_payload)
    source_payload["components"] = [node for node in source_payload.get("components", []) if node["id"] not in property_calls]
    for node in source_payload["components"]:
        node["children_ids"] = [child for child in node.get("children_ids", []) if child not in property_calls]
    expand_surface_padding(source_payload)
    expand_material_touch_targets(source_payload)
    expand_ordered_layout_modifiers(source_payload)
    for component in source_payload.get("components") or []:
        if isinstance(component, dict):
            content = style_group(component, "content")
            text = content.get("text")
            from ui_migration.contracts.style_tokens import has_token_reference
            if not has_token_reference(component, 'content.text') and not isinstance(text, str) and (
                text is not None or component.get("type") in TEXT_TYPES | {"ClickableText", "BasicTextField", "TextField", "OutlinedTextField"}
            ):
                content["text"] = None
                expression = (semantic_expression(component, "text")
                              or semantic_expression(component, "value")
                              or f"{component.get('type')}.text")
                for item in component.get("unresolved") or []:
                    if item.get("path") == "style.content.text" and not item.get("expression"):
                        item["expression"] = expression
                if not any(item.get("path") == "style.content.text" for item in component.get("unresolved") or []):
                    component.setdefault("unresolved", []).append({
                        "path": "style.content.text", "expression": expression,
                        "reason": "text did not resolve to a string; no placeholder or object stringification",
                    })
            component["required_facts"] = build_required_facts(component)
    tree = SourceTree(source_payload)
    layout = SourceLayout(tree, args.viewport_width_dp, args.viewport_height_dp)
    layout.calculate()
    # Parameter-forwarded padding is resolved during measurement; retain that
    # same value in the final facts rather than leaving the original symbol.
    for component in tree.nodes.values():
        if nested_modifier_arguments(component, "padding"):
            resolved_padding = layout.effective_padding(component)
            if any(resolved_padding.values()) or style_group(component, "layout").get("padding_dp") is not None:
                style_group(component, "layout")["padding_dp"] = resolved_padding
                component["required_facts"] = build_required_facts(component)
    artboard_frame = {
        "left": 0,
        "top": 0,
        "width": clean_number(args.viewport_width_dp * args.slice_scale),
        "height": clean_number(args.viewport_height_dp * args.slice_scale),
    }
    page = tree.payload.get("page") or {}
    fact_gate = required_fact_gate(list(tree.nodes.values()))
    root_layer = lanhu_layer(tree, layout, tree.root_id, args.slice_scale)
    phase_gate = build_phase_consumption_gate(layout)
    manifest = component_manifest(tree, layout)
    unresolved = [{'component_id': tree.root_id, **item}
                  for item in [*source_payload.get('source_diagnostics', []), *source_payload.get('unresolved', [])]]
    for component in tree.nodes.values():
        for item in component.get("unresolved") or []:
            unresolved.append({"component_id": component["id"], **item})
        for item in component.get("required_facts") or []:
            if item["status"] in {"symbolic", "unresolved"} and not any(
                existing["component_id"] == component["id"]
                and existing.get("path") == item.get("path")
                and existing.get("expression") == item.get("expression")
                for existing in unresolved
            ):
                unresolved.append({"component_id": component["id"], **item})
    unresolved.extend({"kind": "source_phase_unconsumed", **item}
                      for item in phase_gate["failures"])
    generation_complete = not unresolved
    version_json = {
        "meta": {
            "device": args.device,
            "sliceScale": clean_number(args.slice_scale),
            "host": {"name": "android-source", "version": "1"},
            "plugin": {"name": "android-to-harmony", "version": "1"},
            "migration": {
                "schema": "android-to-harmony.lanhu-document.v1",
                "fontFaces": page_font_faces(source_payload),
                **({'styleDefinitions': source_payload['style_definitions']}
                   if source_payload.get('style_definitions') is not None else {}),
                "componentDefinitions": source_payload.get('component_definitions') or [],
                "page": {
                    "id": page.get("id"),
                    "state": page.get("state"),
                },
            },
            "sourceGeneration": {
                "generationComplete": generation_complete,
                "verdict": "pass" if generation_complete else "fail",
                "unresolved": unresolved,
                "sourceInstanceCount": len(tree.nodes),
                "geometrySummary": manifest["geometry_summary"],
                "layoutRelationships": tree.payload.get("layout_relationships") or [],
                "requiredFactGate": fact_gate,
                "phaseConsumptionGate": phase_gate,
                "stateProjection": state_projection,
            },
        },
        "assets": source_assets(tree),
        "artboard": {
            "id": f"{page.get('id') or 'page'}--{page.get('state') or 'default'}",
            "name": str(page.get("id") or "page"),
            "type": "artboard",
            "visible": True,
            "clipped": True,
            "opacity": 1,
            "frame": artboard_frame,
            "realFrame": dict(artboard_frame),
            "combinedFrame": dict(artboard_frame),
            "style": {
                "isEnabled": True,
                "opacity": 1,
                "blendMode": 0,
                "fills": [],
                "borders": [],
                "shadows": [],
                "blurs": [],
            },
            "layers": [root_layer],
            "origin": "android-source",
        },
    }
    if projected_payload is not None:
        return {'version':version_json, 'unresolved':unresolved}
    if catalogs:
        for catalog in catalogs:
            for variant in catalog['variants']:
                result = generate(args, projected_payload=variant.pop('payload'))
                document = result['version']
                variant['layer'] = document['artboard']['layers'][0]
                variant['source_generation'] = document['meta']['sourceGeneration']
                unresolved.extend({**u, 'component_ui_state':catalog['name'] + '/' + variant['id']} for u in result['unresolved'])
        version_json['meta']['migration']['componentUiStates'] = catalogs
        generation_complete = not unresolved
        version_json['meta']['sourceGeneration'].update(generationComplete=generation_complete,
            verdict='pass' if generation_complete else 'fail', unresolved=unresolved)
    output_dir = args.output_dir.resolve()
    write_json(output_dir / "version_json.json", version_json)
    write_json(output_dir / "component-manifest.json", manifest)
    write_json(output_dir / "page-state-manifest.json", state_manifest(tree))
    from ui_migration.frontend.unresolved_worklist import build_worklist
    worklist = build_worklist(version_json, tree, unresolved)
    write_json(output_dir / 'unresolved-worklist.json', worklist)
    return {
        "status": "generated_requires_screenshot_validation" if generation_complete else "partial_generation",
        "generation_complete": generation_complete,
        "verdict": "pass" if generation_complete else "fail",
        "unresolved_count": len(unresolved),
        "unresolved": unresolved,
        "unresolved_task_count": len(worklist['tasks']),
        "unresolved_worklist": str(output_dir / 'unresolved-worklist.json'),
        "source_page": str(args.source_page.resolve()),
        "output_dir": str(output_dir),
        "source_instances": len(tree.nodes),
        "required_fact_gate": fact_gate,
        "phase_consumption_gate": phase_gate,
        "definitions": len(tree.payload.get("component_definitions") or []),
        "geometry": manifest["geometry_summary"],
        "state_projection": state_projection,
        "non_rendering_argument_call_ids": property_calls,
    }


def main() -> int:
    try:
        result = generate(parse_args())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
