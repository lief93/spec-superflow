#!/usr/bin/env python3
"""Generate ArkUI from one source-generated Lanhu page document."""
from __future__ import annotations
from generate_harmony_theme_resources import commit_payloads
from generate_harmony_theme_resources import json_bytes
from pathlib import Path
from typing import Any
import argparse
import hashlib
import json
from ui_migration.progress import Progress, step, checkpoint, phase
from ui_migration.naming import source_identifier
from ui_migration.contracts.identity import canonical_sha256, require_contract_ui, require_safe_relative_source
from ui_migration.arkui.project import normalize_target, require_module
from ui_migration.target_access import add_target_arguments, metadata_directory, check_manifest_outputs, checked_path
from ui_migration.arkui.renderer import (
    Renderer,
)
from ui_migration.arkui.resources import (
    derive_page_tinted_vectors,
    load_page_font_faces,
    load_theme_resources,
)
from ui_migration.common import (
    ArkUIPageError,
    MANIFEST_SCHEMA,
    named_arguments,
    pascal_identifier,
)
from ui_migration.contracts.consumption import (
    build_target_phase_consumption_gate,
    target_fact_phase,
)
from ui_migration.contracts.lanhu import (
    derive_page_root,
    load_lanhu_page_input,
)
from ui_migration.contracts.snapshot import (
    is_direct_native_wrapper,
    normalize_source_component_tree,
    runtime_overlay_style_path_allowed,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate one candidate ArkUI page from one source-generated version_json."
    )
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--module", default="entry")
    parser.add_argument('--page-output-dir', type=Path, help='Page directory, absolute or relative to --target, inside the module ETS tree; created automatically.')
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
    add_target_arguments(parser)
    return parser.parse_args()


def generate(
    target_path: Path,
    module: str,
    page_json: Path,
    force: bool,
    page_output_dir: Path | None = None,
    *, existing_target=False, target_metadata_dir=None,
) -> dict[str, Any]:
    metadata = metadata_directory(target_path, module, existing_target, target_metadata_dir)
    target = target_path.expanduser().resolve() if existing_target else normalize_target(target_path)
    require_module(target, module)
    from ui_migration.target_paths import page_directory, relocate_import
    output_directory = page_directory(target, module, page_output_dir)
    android_page_input = step('load-page-json', load_lanhu_page_input, page_json)
    if not android_page_input.get("source_generated"):
        raise ArkUIPageError(
            "--page-json must be a source-generated Lanhu version_json"
        )
    root = derive_page_root(android_page_input)
    identity = hashlib.sha256(
        f"{root['source']}#{root['composable']}".encode("utf-8")
    ).hexdigest()[:16]
    from ui_migration.arkui.source_modules import page_file, render_modules, validate_outputs
    manifest_relative = str(metadata / 'arkui-pages' / f'{identity}.json') if existing_target else f".migration/arkui-pages/{identity}.json"
    manifest_path = target / manifest_relative
    checked_path(metadata, manifest_path)
    check_manifest_outputs(target, module, manifest_path)
    output_path = page_file(root, output_directory, target, manifest_path)
    checked_path(target / module / 'src/main/ets', output_path)
    resource_names, string_values = step('load-target-resources', load_theme_resources, target, module, metadata)
    required_gate = android_page_input.get("required_fact_gate")
    tinted_vector_resources, tinted_vector_payloads, tinted_vector_records = (
        step('derive-tinted-vectors', derive_page_tinted_vectors, target, module, identity, android_page_input)
    )
    renderer = step('initialize-renderer', Renderer,
        root,
        resource_names,
        string_values,
        android_page_input,
        tinted_vector_resources,
        import_module=lambda value: relocate_import(value, target/module/'src/main/ets/generated', output_path.parent),
    )
    renderer.verified_font_faces = step('verify-font-assets', load_page_font_faces, target, module, android_page_input, metadata)
    with phase('render-arkts', components=len(android_page_input['components'])):
        source = renderer.render()
    module_payloads, source_organization = step('organize-source-modules', render_modules,
        source, root, renderer.business_components, output_directory, output_path, identity)
    source_organization['output_root'] = output_directory.relative_to(target).as_posix()
    target_phase_gate = step('validate-target-consumption', build_target_phase_consumption_gate,
        android_page_input,
        renderer.android_page_processed_component_ids,
        renderer.android_page_processed_call_ids,
        renderer.android_page_applied_paths,
        renderer.android_page_applied_component_paths,
        getattr(renderer, 'android_page_layout_decisions', []),
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
    output_relative = output_path.relative_to(target).as_posix()
    payloads = {**module_payloads, **tinted_vector_payloads}
    deletions = validate_outputs(target, module, output_path, manifest_path, root, force, payloads)
    output_bytes = module_payloads[output_path]
    semantic_input = {
        "input_mode": "page-json-only",
        "page_json_sha256": android_page_input["sha256"],
    }
    business_report = renderer.business_components.report()
    business_report['representation'] = source_organization['representation']
    business_report['module_sharing'] = source_organization['shared_cross_page_modules']
    renamed = source_organization['renamed_methods']
    for definition in business_report['definitions']:
        definition['builders'] = [renamed.get(name, name) for name in definition['builders']]
    for instance in business_report['instances']:
        instance['builder'] = renamed.get(instance['builder'], instance['builder'])
        instance['slots'] = [renamed.get(name, name) for name in instance['slots']]
    for entry in business_report['declared_interfaces'] + business_report['component_ui_states']:
        entry['name'] = renamed.get(entry['name'], entry['name'])
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
        "business_components": business_report,
        "source_organization": source_organization,
        "reused_business_components": renderer.component_reuse.instances,
        "generation_complete": generation_complete,
        "verdict": "pass" if generation_complete else "fail",
        "required_fact_gate": required_gate,
        "source_phase_consumption_gate": android_page_input.get("source_phase_consumption_gate"),
        "target_phase_consumption_gate": target_phase_gate,
        "unresolved": renderer.unresolved,
        "warnings": android_page_input.get('generation_warnings', []),
        "outputs": {
            **{path.relative_to(target).as_posix(): {
                'sha256': hashlib.sha256(data).hexdigest(), 'kind':'source_ui_module',
            } for path, data in module_payloads.items()},
            output_relative: {
                "sha256": hashlib.sha256(output_bytes).hexdigest(),
                "root_component": source_identifier(root['composable']),
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
            "Known visual properties can use reported migration defaults before validation; no Android source or contract is read.",
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
    manifest_bytes = step('serialize-arkui-manifest', json_bytes, manifest)
    step('write-arkui-output', commit_payloads, {
        **payloads,
        manifest_path: manifest_bytes,
    }, deletions)
    checkpoint('arkui-output', output=str(output_path), unresolved=len(renderer.unresolved),
               completed=len(renderer.android_page_processed_component_ids), total=len(renderer.android_page_by_id))
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
        "warnings": manifest['warnings'],
        "expanded_definition_count": len(renderer.reached_keys),
    }


def main() -> int:
    args = parse_args()
    try:
        with Progress('arkui'):
            result = generate(args.target, args.module, args.page_json, args.force, args.page_output_dir,
                              existing_target=args.existing_target, target_metadata_dir=args.target_metadata_dir)
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
    raise SystemExit(main())
