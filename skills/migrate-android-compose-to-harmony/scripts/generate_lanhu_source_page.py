#!/usr/bin/env python3
from __future__ import annotations
from component_required_facts import build_required_facts
from component_required_facts import required_fact_gate
from pathlib import Path
from typing import Any
from ui_migration.progress import Progress, step, checkpoint, phase, tracked
from ui_migration.contracts.component_ui_states import variant_source_generation
from ui_migration.contracts.lanhu_storage import pack_lanhu_document
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
    parser.add_argument('--harmony-target', type=Path, help='Discover compatible existing components in this Harmony project.')
    parser.add_argument('--no-auto-component-reuse', action='store_true', help='Inspect target signatures but use only explicit component adapters.')
    parser.add_argument('--harmony-module', default='entry')
    parser.add_argument('--component-dir', type=Path, help='Component scan directory, absolute or relative to --harmony-target, inside the module ETS tree.')
    parser.add_argument('--page-output-dir', type=Path, help='Page output directory to exclude from discovery, relative to --harmony-target or absolute.')
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
    if (getattr(args, 'component_dir', None) is not None or getattr(args, 'page_output_dir', None) is not None) and not getattr(args, 'harmony_target', None):
        raise ValueError('--component-dir and --page-output-dir require --harmony-target')
    from ui_migration.contracts.source_storage import unpack_source_page
    from layout_expressions import needs_layout_projection
    from ui_migration.frontend.material_defaults import DEFAULT_CONTROL_TYPES
    from ui_migration.controls.registry import CONTROLS
    if args.viewport_width_dp <= 0 or args.viewport_height_dp <= 0:
        raise ValueError("viewport dimensions must be positive")
    if args.slice_scale <= 0:
        raise ValueError("slice scale must be positive")
    source_payload = copy.deepcopy(projected_payload) if projected_payload is not None else step('read-source-json', read_json, args.source_page)
    source_payload = step('decode-source-storage', unpack_source_page, source_payload)
    preserve_states = projected_payload is None and getattr(args, 'preserve_component_ui_states', False)
    raw_payload = copy.deepcopy(source_payload) if preserve_states else None
    from ui_migration.frontend.api_adapters.loader import load_adapters
    from ui_migration.frontend.api_adapters.builtins import BUILTIN_ADAPTERS
    registry = step('load-adapters', load_adapters, getattr(args, 'api_adapters', None), BUILTIN_ADAPTERS)
    discovery = None
    if projected_payload is None and getattr(args, 'harmony_target', None):
        from ui_migration.frontend.component_discovery import target_inventory, discover_adapters
        discovery = step('discover-harmony-components', target_inventory,
                         args.harmony_target, getattr(args, 'harmony_module', 'entry'),
                         getattr(args, 'component_dir', None), getattr(args, 'page_output_dir', None))
        registry.component_inventory = discovery['components']
        automatic, decisions = ([], []) if getattr(args, 'no_auto_component_reuse', False) else discover_adapters(
            source_payload.get('component_definitions', []), registry.component_adapters, discovery)
        registry.component_adapters = (*registry.component_adapters, *automatic)
        discovery['decisions'] = decisions
        write_json(args.output_dir.resolve() / 'component-discovery.json', discovery)
    state_projection = None
    if projected_payload is not None:
        pass
    elif args.state_fixture is not None:
        source_payload, state_projection = step('project-state', project_source_page,
            source_payload, read_json(args.state_fixture), allow_unresolved=True, api_registry=registry
        )
    elif discovery is not None or source_payload.get('page_host') or (source_payload.get('style_definitions') or {}).get('tokenMappings') or (source_payload.get('style_definitions') or {}).get('componentDefaults') or getattr(args, 'api_adapters', None) is not None or any(
        isinstance(node, dict) and (node.get("visibility_condition") or node.get("list_item_context")
                                   or node.get('slot_invocation')
                                   or node.get('component_kind') == 'project_component'
                                   or node.get('type') in CONTROLS.names
                                   or (node.get('type') in DEFAULT_CONTROL_TYPES - {'Card', 'Surface'}
                                       and not node.get('source', {}).get('material_defaults_profile'))
                                   or needs_layout_projection(node)
                                   or any(m.get('name') == 'then' for m in node.get('modifiers', [])))
        for node in source_payload.get("components") or []
    ):
        source_payload, state_projection = step('project-state', project_source_page, source_payload, {
            "schema": "android-to-harmony.page-state-fixture.v1",
            "page": source_payload.get("page"),
            "values": {},
        }, allow_unresolved=True, api_registry=registry)
    catalogs = []
    if preserve_states:
        from ui_migration.frontend.component_ui_states import preserve_component_states
        fixture = read_json(args.state_fixture) if args.state_fixture else {
            'schema':'android-to-harmony.page-state-fixture.v1', 'page':raw_payload['page'], 'values':{}}
        source_payload, catalogs = step('preserve-component-states', preserve_component_states,
                                        raw_payload, source_payload, fixture, registry)
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
    for component in tracked(source_payload.get("components") or [], 'prepare-component-facts',
                             lambda n: n.get('id') if isinstance(n, dict) else type(n).__name__):
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
    tree = step('build-source-tree', SourceTree, source_payload)
    if state_projection is not None or tree.root_layout_context == 'caller_owned':
        state_projection = {**(state_projection or {}), 'active_root_ids': tree.root_ids,
                            'active_root_id': tree.root_id if len(tree.root_ids) == 1 else None,
                            'root_layout_context': tree.root_layout_context}
        tree.payload['state_projection'] = state_projection
    layout = SourceLayout(tree, args.viewport_width_dp, args.viewport_height_dp)
    with phase('calculate-layout', components=len(tree.nodes)):
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
    fact_gate = step('validate-required-facts', required_fact_gate, list(tree.nodes.values()))
    with phase('build-lanhu-layers', components=len(tree.nodes)):
        root_layers = [lanhu_layer(tree, layout, root_id, args.slice_scale) for root_id in tree.root_ids]
    phase_gate = step('validate-source-consumption', build_phase_consumption_gate, layout)
    manifest = step('build-component-manifest', component_manifest, tree, layout)
    unresolved = [{'component_id': tree.root_id, **item}
                  for item in [*source_payload.get('source_diagnostics', []), *source_payload.get('unresolved', [])]]
    warnings = []
    if tree.root_layout_context == 'caller_owned':
        warnings.append({'component_id': tree.root_id, 'path': 'layout.root_host',
            'reason': 'caller-owned root placement; outputs are preserved, but preview origin is not a source layout fact'})
    from ui_migration.frontend.unresolved_worklist import collect_unresolved
    unresolved = collect_unresolved(tree.nodes.values(), unresolved)
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
                "warnings": warnings,
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
            "layers": root_layers,
            "origin": "android-source",
        },
    }
    if projected_payload is not None:
        return {'version':version_json, 'unresolved':unresolved, 'warnings':warnings}
    if catalogs:
        for catalog in tracked(catalogs, 'component-state-catalogs', lambda c: c['name']):
            for variant in tracked(catalog['variants'], 'component-state-variants', lambda v: catalog['name'] + '/' + v['id']):
                result = generate(args, projected_payload=variant.pop('payload'))
                document = result['version']
                variant['layer'] = document['artboard']['layers'][0]
                variant['source_generation'] = variant_source_generation(document['meta']['sourceGeneration'])
                variant.pop('projection', None)
                unresolved.extend({**u, 'component_ui_state':catalog['name'] + '/' + variant['id']} for u in result['unresolved'])
                warnings.extend({**w, 'component_ui_state':catalog['name'] + '/' + variant['id']} for w in result['warnings'])
        version_json['meta']['migration']['componentUiStates'] = catalogs
        generation_complete = not unresolved
        version_json['meta']['sourceGeneration'].update(generationComplete=generation_complete,
            verdict='pass' if generation_complete else 'fail', unresolved=unresolved)
    output_dir = args.output_dir.resolve()
    stored_version = step('pack-lanhu-json', pack_lanhu_document, version_json)
    step('write-version-json', write_json, output_dir / "version_json.json", stored_version)
    step('write-component-manifest', write_json, output_dir / "component-manifest.json", manifest)
    step('write-page-state-manifest', write_json, output_dir / "page-state-manifest.json", state_manifest(tree))
    from ui_migration.frontend.unresolved_worklist import build_worklist
    worklist = step('build-unresolved-worklist', build_worklist, version_json, tree, unresolved)
    from init_harmony_project import sha256_file
    worklist['version_json_sha256'] = sha256_file(output_dir / 'version_json.json')
    step('write-unresolved-worklist', write_json, output_dir / 'unresolved-worklist.json', worklist)
    checkpoint('lanhu-output', completed=len(tree.nodes), total=len(tree.nodes),
               unresolved=len(unresolved), output=str(output_dir))
    return {
        "status": "generated_requires_screenshot_validation" if generation_complete else "partial_generation",
        "generation_complete": generation_complete,
        "verdict": "pass" if generation_complete else "fail",
        "unresolved_count": len(unresolved),
        "unresolved": unresolved,
        "warnings": warnings,
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
        with Progress('lanhu'):
            result = generate(parse_args())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
