#!/usr/bin/env python3
"""Derive one compact, state-aware working closure from a full source-page contract."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

from audit_behavior_source import census as behavior_census
from audit_behavior_source import source_revision_identity
from compose_theme_facts import validate_compose_theme_facts
from ui_migration.contracts.identity import canonical_sha256
from ui_migration.contracts.source_storage import unpack_source_page
from ui_migration.frontend.api_adapters.builtins import BUILTIN_ADAPTERS
from ui_migration.frontend.api_adapters.loader import load_adapters
from ui_migration.frontend.fixed_state import project_source_page
from ui_migration.frontend.inventory import build_source_page_spec
from ui_migration.frontend.project_styles import load_style_definitions


SCHEMA = "android-to-harmony.effective-page-closure.v1"
STRING_RESOURCE = re.compile(r"\bR\.string\.([A-Za-z_][A-Za-z0-9_]*)\b")
ASSET_RESOURCE = re.compile(r"\bR\.(?:drawable|mipmap)\.([A-Za-z_][A-Za-z0-9_]*)\b")


class EffectiveClosureError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--contract", type=Path)
    inputs.add_argument("--source-page", type=Path)
    parser.add_argument("--style-definitions", type=Path)
    parser.add_argument("--root-source")
    parser.add_argument("--root-composable")
    parser.add_argument("--page-id")
    parser.add_argument("--state-id", default="default")
    parser.add_argument("--state-fixture", type=Path)
    parser.add_argument("--android-page-json", type=Path)
    parser.add_argument("--android-theme-facts", type=Path)
    parser.add_argument("--api-adapters", type=Path)
    parser.add_argument("--behavior-source-scope", type=Path)
    parser.add_argument(
        "--ui-only-preview",
        action="store_true",
        help="Explicitly allow a Preview root and exclude business transcription.",
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise EffectiveClosureError(f"cannot read {label}: {error}") from error
    if not isinstance(value, dict):
        raise EffectiveClosureError(f"{label} must be a JSON object")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compact(value: Any) -> Any:
    """Drop only absent/empty facts; retain false and numeric zero."""
    if isinstance(value, dict):
        result = {str(key): compact(item) for key, item in value.items() if item is not None}
        return {key: item for key, item in result.items() if item not in ({}, [])}
    if isinstance(value, list):
        result = [compact(item) for item in value if item is not None]
        return [item for item in result if item not in ({}, [])]
    return value


def argument_expressions(component: dict[str, Any]) -> dict[str, Any]:
    arguments = component.get("arguments") or {}
    semantic = {}
    for name, value in (arguments.get("semantic") or {}).items():
        if isinstance(value, dict) and isinstance(value.get("expression"), str):
            semantic[str(name)] = value["expression"]
    positional = [
        value["expression"]
        for value in arguments.get("positional") or []
        if isinstance(value, dict) and isinstance(value.get("expression"), str)
    ]
    invocation = []
    for index, value in enumerate(arguments.get("invocation") or []):
        if not isinstance(value, dict) or not isinstance(value.get("expression"), str):
            continue
        invocation.append({
            "name": value.get("name") if isinstance(value.get("name"), str) else f"position_{index}",
            "expression": value["expression"],
        })
    return compact({
        "semantic": semantic,
        "positional": positional,
        "invocation": invocation,
        "state_slots": arguments.get("state_slots") or [],
    })


def action_expressions(arguments: dict[str, Any]) -> dict[str, str]:
    actions: dict[str, str] = {}
    for name, expression in arguments.get("semantic", {}).items():
        if name.startswith("on") and isinstance(expression, str):
            actions[name] = expression
    for item in arguments.get("invocation", []):
        name = item.get("name")
        expression = item.get("expression")
        if isinstance(name, str) and name.startswith("on") and isinstance(expression, str):
            actions[name] = expression
    return actions


def visible_component(component: dict[str, Any]) -> dict[str, Any]:
    style = compact(component.get("style") or {})
    arguments = argument_expressions(component)
    source = component.get("source") or {}
    provenance = compact({
        "source": source.get("source"),
        "composable": source.get("composable"),
        "line": source.get("line"),
        "call_id": source.get("call_id"),
        "declaration_id": source.get("declaration_id"),
        "state_resolution": source.get("state_resolution"),
    })
    return compact({
        "id": component.get("id"),
        "type": component.get("type"),
        "component_kind": component.get("component_kind"),
        "definition_id": component.get("definition_id"),
        "parent_id": component.get("parent_id"),
        "children_ids": component.get("children_ids") or [],
        "sibling_index": component.get("sibling_index"),
        "source": provenance,
        "display": style.get("content", {}),
        "control": {
            "state": style.get("state", {}),
            "actions": action_expressions(arguments),
        },
        "style": {key: value for key, value in style.items() if key not in {"content", "state"}},
        "arguments": arguments,
        "modifiers": [
            compact({"name": item.get("name"), "arguments": item.get("arguments")})
            for item in component.get("modifiers") or []
            if isinstance(item, dict)
        ],
        "source_attributes": source.get("attributes") or [],
        "style_token_references": source.get("style_token_references") or {},
        "unresolved": component.get("unresolved") or [],
    })


def all_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from all_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from all_strings(item)


def referenced_resources(projected: dict[str, Any], components: list[dict[str, Any]]) -> dict[str, Any]:
    serialized_values = list(all_strings(components))
    referenced_string_names = {
        match.group(1)
        for value in serialized_values
        for match in STRING_RESOURCE.finditer(value)
    }
    string_inventory = projected.get("source_string_resources") or {}
    strings = {
        name: string_inventory[f"R.string.{name}"]
        for name in sorted(referenced_string_names)
        if f"R.string.{name}" in string_inventory
    }
    asset_names = {
        item.get("style", {}).get("asset", {}).get("resource")
        for item in components
        if isinstance(item, dict)
    }
    asset_names.update(
        match.group(1)
        for value in serialized_values
        for match in ASSET_RESOURCE.finditer(value)
    )
    asset_inventory = {
        item.get("resource"): compact(item)
        for item in projected.get("source_assets") or []
        if isinstance(item, dict) and isinstance(item.get("resource"), str)
    }
    assets = [
        asset_inventory.get(name, {"resource": name, "status": "referenced_metadata_unavailable"})
        for name in sorted(item for item in asset_names if isinstance(item, str) and item)
    ]
    token_references = []
    for item in components:
        references = item.get("style_token_references")
        if references:
            token_references.append({"component_id": item["id"], "references": references})
    return {"strings": strings, "assets": assets, "theme_token_references": token_references}


def selected_definitions(projected: dict[str, Any], components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = {item.get("definition_id") for item in components}
    result = []
    for definition in projected.get("component_definitions") or []:
        if not isinstance(definition, dict) or definition.get("id") not in selected:
            continue
        result.append(compact({
            "id": definition.get("id"),
            "type": definition.get("type"),
            "component_kind": definition.get("component_kind"),
            "identity": definition.get("identity"),
            "parameters": definition.get("parameters"),
            "declared_from": definition.get("declared_from"),
            "dependency": definition.get("dependency"),
        }))
    return result


def android_runtime_facts(
    path: Path | None, expected_source_page: dict[str, Any]
) -> tuple[dict[str, Any] | None, str | None]:
    if path is None:
        return None, None
    resolved = path.expanduser().resolve()
    payload = read_object(resolved, "Android page JSON")
    if payload.get("schema") != "android-to-harmony.page-snapshot.v2":
        raise EffectiveClosureError("Android page JSON must use page-snapshot.v2")
    if payload.get("platform") != "android":
        raise EffectiveClosureError("Android page JSON platform must be android")
    if payload.get("page") != expected_source_page.get("page"):
        raise EffectiveClosureError("Android page JSON page/state must match source page")
    bound_source_page_sha256 = (payload.get("input_hashes") or {}).get("source_page_spec_sha256")
    if bound_source_page_sha256 is not None:
        if (
            not isinstance(bound_source_page_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", bound_source_page_sha256) is None
        ):
            raise EffectiveClosureError("Android page JSON source page identity must be a lowercase SHA-256")
        if bound_source_page_sha256 != canonical_sha256(expected_source_page):
            raise EffectiveClosureError("Android page JSON source page identity must match selected source page")
    capture = payload.get("capture") or {}
    screenshot = capture.get("screenshot") or {}
    screenshot_sha256 = screenshot.get("sha256")
    if not isinstance(screenshot_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", screenshot_sha256) is None:
        raise EffectiveClosureError("Android page JSON must bind a lowercase SHA-256 screenshot")
    raw_components = payload.get("components")
    if not isinstance(raw_components, list):
        raise EffectiveClosureError("Android page JSON components must be a list")
    components = []
    for item in raw_components:
        if not isinstance(item, dict):
            raise EffectiveClosureError("Android page JSON component must be an object")
        mapping = item.get("source_mapping") or {}
        context = item.get("component_context") or {}
        components.append(compact({
            "id": item.get("id"),
            "type": item.get("type"),
            "parent_id": item.get("parent_id"),
            "children_ids": item.get("children_ids") or [],
            "sibling_index": item.get("sibling_index"),
            "semantic_key": item.get("semantic_key"),
            "source_component_id": context.get("source_component_id"),
            "source_call_id": mapping.get("source_call_id"),
            "source_mapping_method": mapping.get("method"),
            "bounds_dp": item.get("bounds_dp"),
            "style": item.get("style"),
            "provenance": item.get("provenance") or [],
            "unresolved": item.get("unresolved") or [],
        }))
    return compact({
        "origin": "android-page-snapshot-v2",
        "source_page_spec_sha256": bound_source_page_sha256,
        "screenshot_sha256": screenshot_sha256,
        "viewport": payload.get("viewport"),
        "components": components,
        "inactive_source_components": payload.get("inactive_source_components") or [],
        "runtime_elided_source_components": payload.get("runtime_elided_source_components") or [],
        "unmapped_source_components": payload.get("unmapped_source_components") or [],
        "limitations": payload.get("limitations") or [],
    }), sha256_file(resolved)


def require_matching_runtime_content(
    runtime_facts: dict[str, Any] | None,
    projected_components: list[dict[str, Any]],
) -> None:
    if runtime_facts is None:
        return
    projected_by_id = {
        item.get("id"): item
        for item in projected_components
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    mask_characters = frozenset({"•", "*", "●"})
    for runtime_component in runtime_facts.get("components") or []:
        source_component_id = runtime_component.get("source_component_id")
        if not isinstance(source_component_id, str):
            continue
        projected = projected_by_id.get(source_component_id)
        if projected is None:
            continue
        runtime_text = ((runtime_component.get("style") or {}).get("content") or {}).get("text")
        runtime_role = ((runtime_component.get("style") or {}).get("content") or {}).get("role")
        projected_display = projected.get("display") or (
            (projected.get("style") or {}).get("content") or {}
        )
        projected_text = projected_display.get("text")
        if not isinstance(runtime_text, str) or not isinstance(projected_text, str):
            continue
        masked_value = (
            runtime_role == "textbox"
            and projected_display.get("role") == "textbox"
            and bool(runtime_text)
            and len(runtime_text) == len(projected_text)
            and set(runtime_text).issubset(mask_characters)
        )
        visual_transformation = (projected.get("parameter_bindings") or {}).get(
            "visualTransformation"
        )
        transformed_value = (
            runtime_role == "textbox"
            and projected_display.get("role") == "textbox"
            and isinstance(visual_transformation, str)
            and visual_transformation.strip()
            not in {"", "VisualTransformation.None"}
        )
        if runtime_text != projected_text and not masked_value and not transformed_value:
            raise EffectiveClosureError(
                "state fixture visible content must match Android page capture "
                f"for source component {source_component_id}"
            )


def android_runtime_theme(path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    if path is None:
        return None, None
    resolved = path.expanduser().resolve()
    return validate_compose_theme_facts(read_object(resolved, "Android theme facts")), sha256_file(resolved)


def require_matching_android_capture_environment(
    runtime_facts: dict[str, Any] | None,
    runtime_theme: dict[str, Any] | None,
) -> None:
    if runtime_facts is None or runtime_theme is None:
        return
    viewport = runtime_facts.get("viewport") or {}
    capture = runtime_theme.get("capture") or {}
    for page_name, theme_name, label in (
        ("density", "density", "density"),
        ("font_scale", "font_scale", "font scale"),
    ):
        page_value = viewport.get(page_name)
        theme_value = capture.get(theme_name)
        if type(page_value) not in {int, float} or type(theme_value) not in {int, float}:
            continue
        if abs(float(page_value) - float(theme_value)) > 0.001:
            raise EffectiveClosureError(
                f"Android theme capture {label} does not match Android page capture"
            )


def bounded_caller_context(
    contract: dict[str, Any] | None,
    root: dict[str, Any],
    *,
    max_depth: int = 3,
    max_edges: int = 64,
) -> dict[str, Any]:
    if contract is None:
        return {
            "status": "unavailable-source-page-input",
            "truncated": False,
            "caller_edges": [],
        }
    graph = ((contract.get("ui") or {}).get("custom_composable_call_graph") or {})
    edges = graph.get("edges") or []
    semantic_calls = ((contract.get("ui") or {}).get("semantic_translation_candidates") or {}).get(
        "calls"
    ) or []
    calls_by_id = {
        item.get("call_id"): item
        for item in semantic_calls
        if isinstance(item, dict) and isinstance(item.get("call_id"), str)
    }
    frontier = {(root.get("source"), root.get("composable"))}
    visited = set(frontier)
    selected: list[dict[str, Any]] = []
    truncated = False
    for depth in range(1, max_depth + 1):
        level = []
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            caller = edge.get("caller") or {}
            callee = edge.get("callee") or {}
            if (callee.get("source"), callee.get("composable")) not in frontier:
                continue
            caller_name = caller.get("composable")
            if (
                not isinstance(caller_name, str)
                or caller_name.startswith("__content_")
                or "preview" in caller_name.lower()
            ):
                continue
            call_id = edge.get("call_id")
            call = calls_by_id.get(call_id) or {}
            custom_component = call.get("custom_composable") or {}
            arguments = [
                compact({"name": item.get("name"), "expression": item.get("expression")})
                for item in custom_component.get("arguments") or []
                if isinstance(item, dict)
                and isinstance(item.get("name"), str)
                and isinstance(item.get("expression"), str)
            ]
            level.append({
                "depth": depth,
                "caller": compact({
                    "source": caller.get("source"),
                    "composable": caller.get("composable"),
                }),
                "callee": compact({
                    "source": callee.get("source"),
                    "composable": callee.get("composable"),
                }),
                "line": edge.get("line"),
                "call_id": call_id,
                "invocation_arguments": arguments,
            })
        level.sort(key=lambda item: (
            item["caller"].get("source", ""),
            item["caller"].get("composable", ""),
            item.get("call_id", ""),
        ))
        if len(selected) + len(level) > max_edges:
            level = level[: max_edges - len(selected)]
            truncated = True
        selected.extend(level)
        next_frontier = {
            (item["caller"].get("source"), item["caller"].get("composable"))
            for item in level
        } - visited
        visited.update(next_frontier)
        frontier = next_frontier
        if not frontier or len(selected) >= max_edges:
            break
    if frontier and any(
        isinstance(edge, dict)
        and ((edge.get("callee") or {}).get("source"),
             (edge.get("callee") or {}).get("composable")) in frontier
        for edge in edges
    ):
        truncated = True
    return {
        "status": "bounded-candidate-context",
        "max_depth": max_depth,
        "max_edges": max_edges,
        "truncated": truncated,
        "caller_edges": selected,
    }


def is_preview_root(root: dict[str, Any]) -> bool:
    name = root.get("composable")
    return isinstance(name, str) and "preview" in name.lower()


def root_owns_business_state(source_page: dict[str, Any]) -> bool:
    """Return true when the selected production root already owns its state adapter.

    A leaf UI function normally receives state/callback values and needs its immediate Route
    caller in the business denominator. A Route that injects a ViewModel or collects/emits state
    already owns that boundary; its navigation host is context only and must not pull sibling
    routes into the transitive business scope.
    """
    root = source_page.get("root") or {}
    function = next((item for item in source_page.get("source_functions") or []
        if isinstance(item, dict)
        and item.get("top_level") is True
        and item.get("source") == root.get("source")
        and item.get("name") == root.get("composable")), None)
    if function is None:
        return False
    parameter_types = [
        str(item.get("type") or "")
        for item in function.get("parameters") or []
        if isinstance(item, dict)
    ]
    body_text = str((function.get("body") or {}).get("text") or "")
    return (
        any("ViewModel" in value for value in parameter_types)
        or "collectAsState" in body_text
        or ".emitIntent(" in body_text
    )


def business_transcription_context(
    contract: dict[str, Any] | None,
    source_page: dict[str, Any],
    caller_context: dict[str, Any],
    *,
    ui_only_preview: bool,
    selected_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = source_page.get("root") or {}
    preview = is_preview_root(root)
    if preview and not ui_only_preview:
        raise EffectiveClosureError(
            "Preview composable roots require explicit --ui-only-preview; "
            "use the production page root for business semantic transcription"
        )
    if ui_only_preview and not preview:
        raise EffectiveClosureError("--ui-only-preview requires a Preview composable root")
    if ui_only_preview:
        return {
            "status": "explicitly_out_of_scope",
            "required": False,
            "root_kind": "ui_only_preview",
            "files": [],
            "required_target_mappings": [],
            "limitations": [
                "This closure is explicitly UI-only and cannot prove page business behavior."
            ],
        }
    if contract is None:
        return {
            "status": "external_snapshot_required",
            "required": True,
            "root_kind": "production_page",
            "files": [],
            "required_target_mappings": [
                "state", "intent", "branch", "callback", "side_effect_order",
                "navigation", "platform_adapter",
            ],
            "limitations": [
                "A full Contract and validated safe snapshot are required to derive the business source denominator."
            ],
        }

    snapshot_value = (contract.get("source") or {}).get("safe_snapshot_root")
    if not isinstance(snapshot_value, str) or not snapshot_value:
        raise EffectiveClosureError("migration contract does not identify a safe snapshot root")
    snapshot_root = Path(snapshot_value).expanduser().resolve()
    manifest_path = snapshot_root / ".android-to-harmony-safe.json"
    manifest = read_object(manifest_path, "safe snapshot manifest")
    root_source = root.get("source")
    if not isinstance(root_source, str) or not root_source:
        raise EffectiveClosureError("page root does not identify a source file")
    entry_symbols: dict[str, set[str]] = {root_source: {str(root.get("composable"))}}
    caller_is_business_owner = not root_owns_business_state(source_page)
    for edge in caller_context.get("caller_edges") or []:
        if not isinstance(edge, dict):
            continue
        if edge.get("depth") != 1 or not caller_is_business_owner:
            continue
        caller = edge.get("caller") or {}
        source = caller.get("source")
        composable = caller.get("composable")
        if (
            isinstance(source, str)
            and source
            and isinstance(composable, str)
            and composable
            and "preview" not in composable.lower()
        ):
            entry_symbols.setdefault(source, set()).add(composable)
    scope = {
        "schema_version": "behavior-source-scope.v1",
        "id": f"page:{source_page.get('page', {}).get('id')}:{root.get('composable')}",
        "kind": "page",
        "source_revision": source_revision_identity(manifest, snapshot_root),
        "entry_paths": sorted(entry_symbols),
        "entry_symbols": {
            path: sorted(symbols) for path, symbols in sorted(entry_symbols.items())
        },
    }
    if selected_scope is not None:
        if {k: v for k, v in selected_scope.items() if k != "definition_boundaries"} != scope:
            raise EffectiveClosureError("business source scope must retain the generated page roots and identity")
        scope = selected_scope
    try:
        census = behavior_census(snapshot_root, scope)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise EffectiveClosureError(f"cannot derive page business source closure: {error}") from error
    obligations = census.get("obligations") or []
    obligation_index = [
        compact({
            "id": item.get("id"),
            "path": item.get("path"),
            "kind": item.get("kind"),
            "symbol": item.get("symbol"),
            "start_line": item.get("start_line"),
            "end_line": item.get("end_line"),
            "span_sha256": item.get("span_sha256"),
        })
        for item in obligations
    ]
    counts: dict[str, int] = {}
    for obligation in obligations:
        kind = str(obligation.get("kind") or "unknown")
        counts[kind] = counts.get(kind, 0) + 1
    unresolved = list(census.get("unresolved") or [])
    host_callback_obligations = []
    for edge in caller_context.get("caller_edges") or []:
        if not isinstance(edge, dict) or edge.get("depth") != 1:
            continue
        for argument in edge.get("invocation_arguments") or []:
            if not isinstance(argument, dict):
                continue
            name = argument.get("name")
            expression = argument.get("expression")
            if not isinstance(name, str) or not isinstance(expression, str):
                continue
            stripped = expression.strip()
            if not (name.startswith("on") or stripped.startswith("{") or "::" in stripped):
                continue
            host_callback_obligations.append(compact({
                "call_id": edge.get("call_id"),
                "caller": edge.get("caller"),
                "parameter": name,
                "expression": expression,
            }))
    result = compact({
        "schema": "android-to-harmony.page-business-transcription.v1",
        "status": "requires_source_resolution" if unresolved else "ready_for_source_transcription",
        "required": True,
        "root_kind": "production_page",
        "scope_sha256": census.get("scope_sha256"),
        "census_sha256": census.get("census_sha256"),
        "source_revision": census.get("source_revision"),
        "files": census.get("files") or [],
        "reached_definitions": census.get("reached_definitions") or [],
        "dependency_edges": census.get("dependency_edges") or [],
        "external_dependencies": census.get("external_dependencies") or [],
        "reading_context": census.get("reading_context") or [],
        "obligation_summary": {"total": len(obligations), "by_kind": counts},
        "obligation_index_sha256": canonical_sha256(obligation_index),
        "unresolved": unresolved,
        "host_callback_obligations": host_callback_obligations,
        "required_target_mappings": [
            "state", "intent", "branch", "callback", "side_effect_order",
            "navigation", "platform_adapter",
        ],
        "completion_rule": (
            "Read every bound source file and transcribe each reachable business obligation. "
            "Platform mechanisms may use Harmony adapters, but source branches, state transitions, "
            "callback inputs, host-provided callback bodies, and side-effect order must remain "
            "traceable. Host callback obligations stop at the exact selected-page invocation and "
            "must not expand unrelated sibling routes. Missing mappings are "
            "diagnostics and must never be replaced by mock values or no-op callbacks. Regenerate "
            "the hash-bound obligation index with audit_behavior_source.py when authoring the "
            "behavior contract; it is intentionally not duplicated in this compact closure."
        ),
        "limitations": census.get("limits") or [],
    })
    # Scope is a hash-bound validator input, not compact display facts. Empty
    # boundary lists carry meaning and must survive the normal CLI round trip.
    result["scope"] = census["scope"]
    return result


def scoped_source_files(
    contract: dict[str, Any] | None,
    source_page: dict[str, Any],
    caller_context: dict[str, Any],
    business_context: dict[str, Any],
) -> dict[str, Any]:
    reasons: dict[str, set[str]] = {}

    def add(path: Any, reason: str) -> None:
        if not isinstance(path, str) or not path:
            return
        normalized = Path(path)
        if normalized.is_absolute() or ".." in normalized.parts:
            raise EffectiveClosureError(f"unsafe source path in page closure: {path}")
        reasons.setdefault(normalized.as_posix(), set()).add(reason)

    root = source_page.get("root") or {}
    add(root.get("source"), "page_root")
    for component in [
        *(source_page.get("components") or []),
        *(source_page.get("source_callable_components") or []),
    ]:
        if isinstance(component, dict):
            add((component.get("source") or {}).get("source"), "page_component")
    for definition in source_page.get("component_definitions") or []:
        if not isinstance(definition, dict):
            continue
        add((definition.get("identity") or {}).get("source"), "component_definition")
        add((definition.get("declared_from") or {}).get("source"), "component_caller")
    for edge in caller_context.get("caller_edges") or []:
        if not isinstance(edge, dict):
            continue
        add((edge.get("caller") or {}).get("source"), "page_host")
        add((edge.get("callee") or {}).get("source"), "caller_chain")
    for item in business_context.get("files") or []:
        if isinstance(item, dict):
            add(item.get("path"), "business_dependency")

    relative_files = sorted(reasons)
    if contract is None:
        identity = {
            "status": "external_snapshot_required",
            "entry_files": relative_files,
        }
        return {
            "status": identity["status"],
            "reading_required": True,
            "entry_files": [
                {"path": path, "reasons": sorted(reasons[path])}
                for path in relative_files
            ],
            "sha256": canonical_sha256(identity),
            "reading_rule": (
                "Read every entry file from the validated safe snapshot and follow its "
                "project-local definitions before transcribing; this closure does not replace source."
            ),
        }

    snapshot_value = (contract.get("source") or {}).get("safe_snapshot_root")
    if not isinstance(snapshot_value, str) or not snapshot_value:
        raise EffectiveClosureError("migration contract does not identify a safe snapshot root")
    snapshot_root = Path(snapshot_value).expanduser()
    if snapshot_root.is_symlink() or not snapshot_root.is_dir():
        raise EffectiveClosureError("safe snapshot root is unavailable or symbolic")
    snapshot_root = snapshot_root.resolve()
    manifest = snapshot_root / ".android-to-harmony-safe.json"
    if manifest.is_symlink() or not manifest.is_file():
        raise EffectiveClosureError("safe snapshot manifest is unavailable or symbolic")
    entries = []
    for path in relative_files:
        source_file = snapshot_root / path
        if source_file.is_symlink() or not source_file.is_file():
            raise EffectiveClosureError(f"scoped safe source file is unavailable: {path}")
        resolved = source_file.resolve()
        try:
            resolved.relative_to(snapshot_root)
        except ValueError as error:
            raise EffectiveClosureError(f"scoped source escapes safe snapshot: {path}") from error
        entries.append({
            "path": path,
            "sha256": sha256_file(resolved),
            "reasons": sorted(reasons[path]),
        })
    identity = {
        "snapshot_manifest_sha256": sha256_file(manifest),
        "entry_files": [{"path": item["path"], "sha256": item["sha256"]} for item in entries],
    }
    return {
        "status": "ready",
        "reading_required": True,
        "safe_snapshot_root": str(snapshot_root),
        "snapshot_manifest_sha256": identity["snapshot_manifest_sha256"],
        "entry_files": entries,
        "sha256": canonical_sha256(identity),
        "reading_rule": (
            "Read every entry file from this validated safe snapshot and follow referenced "
            "project-local helpers needed by the page before transcribing. The closure limits "
            "scope and carries evidence; it is not a substitute for source semantics."
        ),
    }


def write_new(path: Path, payload: dict[str, Any]) -> tuple[Path, str]:
    output = Path(os.path.abspath(os.path.expanduser(str(path))))
    if output.exists() or output.is_symlink():
        raise EffectiveClosureError(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        with output.open("xb") as stream:
            stream.write(encoded)
    except FileExistsError as error:
        raise EffectiveClosureError(f"output already exists: {output}") from error
    return output, hashlib.sha256(encoded).hexdigest()


def generate(args: argparse.Namespace) -> dict[str, Any]:
    contract: dict[str, Any] | None = None
    if args.contract is not None:
        required = {
            "--style-definitions": args.style_definitions,
            "--root-source": args.root_source,
            "--root-composable": args.root_composable,
            "--page-id": args.page_id,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            raise EffectiveClosureError("--contract requires " + ", ".join(missing))
        contract_path = args.contract.expanduser().resolve()
        contract = read_object(contract_path, "migration contract")
        contract_sha256 = sha256_file(contract_path)
        styles = load_style_definitions(args.style_definitions.expanduser().resolve())
        snapshot_value = (contract.get("source") or {}).get("safe_snapshot_root")
        if not isinstance(snapshot_value, str) or not snapshot_value:
            raise EffectiveClosureError("migration contract does not identify a safe snapshot root")
        snapshot_root = Path(snapshot_value).expanduser().resolve()
        source_page = build_source_page_spec(
            contract,
            args.root_source,
            args.root_composable,
            args.page_id,
            args.state_id,
            contract_sha256,
            snapshot_root,
            style_definitions=styles,
        )
        source_input_sha256 = canonical_sha256(source_page)
        source_input = "full-contract-closure"
    else:
        source_page_path = args.source_page.expanduser().resolve()
        source_page = unpack_source_page(read_object(source_page_path, "source page"))
        contract_sha256 = source_page.get("contract_sha256")
        source_input_sha256 = sha256_file(source_page_path)
        source_input = "source-page"
    if args.state_fixture is None:
        fixture = {
            "schema": "android-to-harmony.page-state-fixture.v1",
            "page": source_page.get("page"),
            "values": {},
        }
        fixture_sha256 = canonical_sha256(fixture)
        fixture_source = "default-empty-fixture"
    else:
        fixture_path = args.state_fixture.expanduser().resolve()
        fixture = read_object(fixture_path, "state fixture")
        fixture_sha256 = sha256_file(fixture_path)
        fixture_source = "explicit-state-fixture"
    registry = load_adapters(args.api_adapters, BUILTIN_ADAPTERS)
    projected, selection = project_source_page(
        source_page, fixture, allow_unresolved=True, api_registry=registry
    )
    complete = bool(selection.get("selection_complete"))
    projected_components = projected.get("components") or []
    retained_components = selection.get("retained_components") or []
    if complete:
        proven_components = projected_components
        unresolved_branch_components = []
    else:
        proven_components = [
            item for item in projected_components
            if not (item.get("source") or {}).get("state_resolution")
        ]
        unresolved_branch_components = [
            *[
                item for item in projected_components
                if (item.get("source") or {}).get("state_resolution")
            ],
            *retained_components,
        ]
    components = [visible_component(item) for item in proven_components]
    branch_components = [visible_component(item) for item in unresolved_branch_components]
    evidence_components = [*components, *branch_components]
    unresolved_state_selection = bool(selection.get("preview_branch_choices")) or any(
        (item.get("source") or {}).get("state_resolution", {}).get("kind") == "condition"
        for item in unresolved_branch_components
    )
    status = (
        "candidate_complete"
        if complete
        else "candidate_requires_runtime_facts"
        if unresolved_state_selection
        else "candidate_ready_for_ai"
    )
    runtime_facts, android_page_sha256 = android_runtime_facts(
        args.android_page_json, source_page
    )
    require_matching_runtime_content(runtime_facts, proven_components)
    runtime_theme, android_theme_sha256 = android_runtime_theme(args.android_theme_facts)
    require_matching_android_capture_environment(runtime_facts, runtime_theme)
    caller_context = bounded_caller_context(contract, source_page.get("root") or {})
    business_context = business_transcription_context(
        contract, source_page, caller_context, ui_only_preview=args.ui_only_preview,
        selected_scope=(read_object(args.behavior_source_scope, "behavior source scope")
                        if args.behavior_source_scope else None),
    )
    source_scope = scoped_source_files(contract, source_page, caller_context, business_context)
    identity_input = {
        "contract_sha256": contract_sha256,
        "source_input": source_input,
        "source_input_sha256": source_input_sha256,
        "root": source_page.get("root"),
        "page": source_page.get("page"),
        "state_fixture_sha256": fixture_sha256,
        "android_page_sha256": android_page_sha256,
        "android_theme_sha256": android_theme_sha256,
        "api_adapters_sha256": sha256_file(args.api_adapters.expanduser().resolve()) if args.api_adapters else None,
        "source_scope_sha256": source_scope["sha256"],
        "business_census_sha256": business_context.get("census_sha256"),
    }
    payload = {
        "schema": SCHEMA,
        "status": status,
        "authoritative": False,
        "identity": {**identity_input, "sha256": canonical_sha256(identity_input)},
        "root": source_page.get("root"),
        "page": source_page.get("page"),
        "selection": {
            "complete": complete,
            "fixture_source": fixture_source,
            "active_root_ids": selection.get("active_root_ids") or [],
            "inactive_source_ids": selection.get("inactive_source_ids") or [],
            "deferred_component_ids": selection.get("deferred_component_ids") or [],
            "unresolved_branches": selection.get("preview_branch_choices") or [],
        },
        "source_context": caller_context,
        "source_scope": source_scope,
        "business_transcription": business_context,
        "visible_components": components,
        "unresolved_branch_components": branch_components,
        "definitions": selected_definitions(projected, evidence_components),
        "resources": referenced_resources(projected, evidence_components),
        "runtime_facts": runtime_facts,
        "runtime_theme": runtime_theme,
        "unresolved": projected.get("unresolved") or [],
        "limitations": [
            "This is a candidate working closure derived from the full migration contract, not migration-completion evidence.",
            "The closure is a bounded source-reading index plus evidence, not a replacement for the scoped Android source files.",
            "A complete visibility selection requires explicit state or matching runtime facts; unresolved branches retain both alternatives and neither is called proven visible.",
            "Runtime geometry, insets, fonts, colors, and layer order are included only when present in a bound Android page snapshot; coordinates remain relative to that snapshot's viewport.",
            "Android page facts are state-bound measurement evidence; they do not replace source hierarchy or authorize screenshot-derived hardcoding.",
            "Runtime theme facts expose resolved MaterialTheme values for this capture environment; null fields and unresolved records must still be reconciled from source.",
        ],
    }
    output, output_sha256 = write_new(args.output, payload)
    return {
        "ok": True,
        "schema": "android-to-harmony.command-result.v1",
        "output": str(output),
        "output_sha256": output_sha256,
        "status": payload["status"],
        "identity_sha256": payload["identity"]["sha256"],
        "contract_sha256": payload["identity"]["contract_sha256"],
        "android_page_sha256": android_page_sha256,
        "android_theme_sha256": android_theme_sha256,
        "visible_component_count": len(components),
        "unresolved_branch_component_count": len(branch_components),
        "selection_complete": complete,
        "business_transcription_status": business_context.get("status"),
    }


def main() -> int:
    args = parse_args()
    try:
        result = generate(args)
    except (EffectiveClosureError, KeyError, OSError, TypeError, ValueError, RuntimeError) as error:
        print(json.dumps({
            "ok": False,
            "schema": "android-to-harmony.command-result.v1",
            "error": str(error),
        }, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
