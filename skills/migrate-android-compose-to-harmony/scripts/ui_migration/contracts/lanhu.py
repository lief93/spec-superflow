from __future__ import annotations
import copy
from collections import defaultdict
from component_required_facts import normalize_required_facts, required_fact_gate
from init_harmony_project import sha256_file
from page_snapshot import PageSnapshotError, normalize_provenance, normalize_style, normalize_unresolved, require_token
from pathlib import Path
from typing import Any
from ui_migration.common import ArkUIPageError, LANHU_COMPONENT_MANIFEST_SCHEMA, PAGE_SNAPSHOT_COLUMN_COMPONENTS, PAGE_SNAPSHOT_ROW_COMPONENTS
from ui_migration.contracts.identity import canonical_sha256, require_safe_relative_source
from ui_migration.contracts.lanhu_storage import unpack_lanhu_document
from ui_migration.contracts.validation import apply_lanhu_visual_style, load_bounded_json_object, normalize_lanhu_layout_relationships, require_lanhu_frame, require_lanhu_number, validate_lanhu_version_document


def load_lanhu_page_input(
    version_json_path: Path,
    component_manifest_path: Path | None = None,
    *, _version: dict | None = None,
) -> dict[str, Any]:
    if _version is None:
        version, version_path, version_bytes = load_bounded_json_object(version_json_path, "Lanhu version_json")
    else:
        version, version_path, version_bytes = _version, version_json_path, 0
    try:
        version = unpack_lanhu_document(version)
    except ValueError as error:
        raise ArkUIPageError(str(error)) from error
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
                    "definition_id": migration.get('definitionId'),
                    "component_kind": migration.get('componentKind'),
                    "invocation_bindings": copy.deepcopy(migration.get('invocationBindings') or {}),
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
        if isinstance(source, dict) and source.get('custom_component') is True:
            # A business call is not a visual container. Preserve its explicit
            # source facts, but do not invent surface/state overrides from
            # artboard export defaults. This also applies to external reuse.
            visual_paths = []
        else:
            visual_paths = apply_lanhu_visual_style(style, layers_by_id[component_id], scale)
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
            "definition_id": instance.get('definition_id'),
            "component_kind": instance.get('component_kind'),
            "invocation_bindings": copy.deepcopy(instance.get('invocation_bindings') or {}),
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
    for component in components:
        path = []
        owner = component
        while owner is not None:
            if owner.get('component_kind') == 'project_component':
                path.append(owner['id'])
            owner = by_id.get(owner.get('parent_id'))
        if path:
            component['component_context'].update({
                'status': 'source-resolved', 'method': 'embedded-definition-identity',
                'business_component_id': path[0], 'business_component_path': list(reversed(path)),
            })
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
        "root_layout_context": (source_generation.get("stateProjection") or {}).get("root_layout_context")
        if isinstance(source_generation, dict) else None,
        "generation_warnings": source_generation.get('warnings', []) if isinstance(source_generation, dict) else [],
        "font_faces": migration_meta.get("fontFaces", []) if isinstance(migration_meta, dict) else [],
        "component_definitions": migration_meta.get('componentDefinitions', []) if isinstance(migration_meta, dict) else [],
        "required_fact_gate": required_fact_gate(list(instances.values())),
        "source_phase_consumption_gate": source_generation.get("phaseConsumptionGate")
        if isinstance(source_generation, dict) else None,
    }
    if manifest_path is not None:
        result["component_manifest"] = {
            "file": manifest_path.name,
            "sha256": sha256_file(manifest_path),
        }
    from ui_migration.contracts.component_ui_states import decode_catalogs
    result['component_ui_states'] = decode_catalogs(version,
        lambda document: load_lanhu_page_input(version_json_path, _version=document))
    return result


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
