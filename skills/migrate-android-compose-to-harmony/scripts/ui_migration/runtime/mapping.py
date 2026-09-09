from __future__ import annotations
import copy
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from ui_migration.frontend.definitions import source_component_id, source_semantic_key
from ui_migration.frontend.model import RUNTIME_SOURCE_MAP_SCHEMA, RealPageError


def load_runtime_source_map_file(path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    if path is None:
        return None, None
    resolved = path.expanduser().resolve()
    if path.is_symlink() or not resolved.is_file():
        raise RealPageError("runtime source map must be a regular non-symbolic-link JSON file")
    raw = resolved.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RealPageError(f"runtime source map is invalid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise RealPageError("runtime source map root must be an object")
    return payload, hashlib.sha256(raw).hexdigest()


def source_runtime_type_compatible(source_type: str, runtime: dict[str, Any]) -> bool:
    runtime_kind = runtime["type"]
    if source_type in {"Text", "BasicText", "ClickableText"}:
        return runtime_kind == "Text"
    if source_type in {"Image", "Icon", "AsyncImage"}:
        return runtime_kind == "Image" or runtime.get("runtime_class") == "android.view.View"
    if source_type in {"Button", "IconButton", "FloatingActionButton", "SmallFloatingActionButton"}:
        return runtime_kind == "Button" or bool(runtime["style"]["state"]["clickable"])
    if source_type in {"TextField", "OutlinedTextField", "BasicTextField"}:
        return runtime_kind == "TextField"
    return runtime_kind not in {"Text", "Image", "TextField"}


def ancestors(component_id: str, runtime_by_id: dict[str, dict[str, Any]]) -> list[str]:
    result: list[str] = []
    current = runtime_by_id[component_id].get("parent_id")
    while isinstance(current, str) and current in runtime_by_id:
        result.append(current)
        current = runtime_by_id[current].get("parent_id")
    return result


def lowest_common_runtime_ancestor(
    component_ids: list[str], runtime_by_id: dict[str, dict[str, Any]]
) -> str | None:
    if not component_ids:
        return None
    chains = [[component_id] + ancestors(component_id, runtime_by_id) for component_id in component_ids]
    common = set(chains[0])
    for chain in chains[1:]:
        common.intersection_update(chain)
    return next((item for item in chains[0] if item in common), None)


def source_descendants(component_id: str, source_by_id: dict[str, dict[str, Any]]) -> list[str]:
    result: list[str] = []
    queue = list(source_by_id[component_id]["children_ids"])
    while queue:
        current = queue.pop(0)
        result.append(current)
        queue[0:0] = source_by_id[current]["children_ids"]
    return result


def tree_descendants(component_id: str, by_id: dict[str, dict[str, Any]]) -> list[str]:
    result: list[str] = []

    def visit(current: str) -> None:
        for child in by_id[current]["children_ids"]:
            result.append(child)
            visit(child)

    visit(component_id)
    return result


def semantic_source_component(component: dict[str, Any]) -> bool:
    return component["type"] in {
        "Text", "BasicText", "ClickableText", "Image", "Icon", "AsyncImage",
        "Button", "IconButton", "FloatingActionButton", "SmallFloatingActionButton", "TextField", "OutlinedTextField",
        "BasicTextField", "CheckBox", "Switch", "RadioButton",
    }


def runtime_semantic_key(component: dict[str, Any]) -> str | None:
    runtime_id = component.get("runtime_id")
    if isinstance(runtime_id, str) and runtime_id:
        return runtime_id
    resource_id = component.get("resource_id")
    if not isinstance(resource_id, str) or not resource_id or resource_id.startswith("android:id/"):
        return None
    return resource_id.rsplit("/", 1)[-1]


def stable_runtime_fallback_key(component: dict[str, Any]) -> str | None:
    runtime_key = runtime_semantic_key(component)
    if not isinstance(runtime_key, str):
        return None
    generated_key_patterns = (
        r"runtime\.[0-9a-f]{20}",
        r"runtime\.(?:asset|progress)\.[0-9a-f]{20}",
        r"[A-Za-z0-9_.:@#-]+__instance_[A-Za-z0-9_.:@#-]+",
        r"[A-Za-z0-9_.:@#-]+__surface_[0-9a-f]{20}",
    )
    return runtime_key if any(
        re.fullmatch(pattern, runtime_key)
        for pattern in generated_key_patterns
    ) else None


def expand_runtime_source_instances(
    source_components: list[dict[str, Any]],
    payload: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Expand one statically declared component definition into proven runtime instances."""
    if payload is None or not isinstance(payload, dict):
        return source_components, payload
    mappings = payload.get("mappings")
    if not isinstance(mappings, list):
        return source_components, payload

    source_by_semantic_key = {
        item["semantic_key"]: item
        for item in source_components
        if isinstance(item.get("semantic_key"), str)
        and isinstance(item.get("source"), dict)
    }
    definition_instances: dict[tuple[str, str], list[str]] = defaultdict(list)
    mapping_definitions: list[tuple[dict[str, Any], tuple[str, str] | None, str | None]] = []
    for mapping in mappings:
        if not isinstance(mapping, dict):
            mapping_definitions.append((mapping, None, None))
            continue
        instance_key = mapping.get("source_instance_key")
        if instance_key is not None and (
            not isinstance(instance_key, str)
            or re.fullmatch(r"[A-Za-z0-9._:@#-]{1,80}", instance_key) is None
        ):
            raise RealPageError("runtime source map source_instance_key is malformed")
        semantic_key = mapping.get("source_semantic_key")
        source = source_by_semantic_key.get(semantic_key) if isinstance(semantic_key, str) else None
        definition = None
        if source is not None:
            definition = (
                str(source["source"].get("source", "")),
                str(source["source"].get("composable", "")),
            )
            if instance_key is not None and instance_key not in definition_instances[definition]:
                definition_instances[definition].append(instance_key)
        mapping_definitions.append((mapping, definition, instance_key))
    if not definition_instances:
        return source_components, payload

    for _mapping, definition, instance_key in mapping_definitions:
        if definition in definition_instances and instance_key is None:
            raise RealPageError(
                "runtime source map must provide source_instance_key for every mapping from an instanced definition"
            )

    components_by_definition: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for component in source_components:
        source = component.get("source")
        if not isinstance(source, dict):
            continue
        definition = (str(source.get("source", "")), str(source.get("composable", "")))
        components_by_definition[definition].append(component)

    clone_keys: dict[tuple[str, str, str], dict[str, tuple[str, str]]] = {}
    expanded_components: list[dict[str, Any]] = []
    emitted_definitions: set[tuple[str, str]] = set()
    for component in source_components:
        source = component.get("source")
        definition = (
            str(source.get("source", "")), str(source.get("composable", ""))
        ) if isinstance(source, dict) else ("", "")
        instances = definition_instances.get(definition)
        if not instances:
            expanded_components.append(component)
            continue
        if definition in emitted_definitions:
            continue
        emitted_definitions.add(definition)
        definition_components = components_by_definition[definition]
        for instance_key in instances:
            ids = {
                item["id"]: source_component_id(
                    f"runtime-instance:{instance_key}", str(item["source"]["call_id"])
                )
                for item in definition_components
            }
            semantic_keys = {
                item["semantic_key"]: f"{item['semantic_key']}__instance_{instance_key}"
                for item in definition_components
            }
            if any(len(value) > 120 for value in semantic_keys.values()):
                raise RealPageError("runtime source map expanded semantic key exceeds 120 characters")
            clone_keys[(definition[0], definition[1], instance_key)] = {
                base: (ids[item["id"]], semantic_keys[base])
                for base, item in (
                    (candidate["semantic_key"], candidate) for candidate in definition_components
                )
            }
            for item in definition_components:
                clone = copy.deepcopy(item)
                clone["id"] = ids[item["id"]]
                clone["semantic_key"] = semantic_keys[item["semantic_key"]]
                parent_id = item.get("parent_id")
                clone["parent_id"] = ids.get(parent_id, parent_id)
                clone["children_ids"] = [ids.get(child_id, child_id) for child_id in item["children_ids"]]
                expanded_components.append(clone)

    replacement_children: dict[str, list[str]] = defaultdict(list)
    for definition, instances in definition_instances.items():
        for item in components_by_definition[definition]:
            replacement_children[item["id"]] = [
                clone_keys[(definition[0], definition[1], instance_key)][item["semantic_key"]][0]
                for instance_key in instances
            ]
    for component in expanded_components:
        children: list[str] = []
        for child_id in component["children_ids"]:
            children.extend(replacement_children.get(child_id, [child_id]))
        component["children_ids"] = children

    normalized_payload = copy.deepcopy(payload)
    normalized_mappings: list[Any] = []
    for mapping, definition, instance_key in mapping_definitions:
        normalized = copy.deepcopy(mapping)
        if isinstance(normalized, dict) and instance_key is not None and definition is not None:
            base_semantic_key = normalized["source_semantic_key"]
            clone = clone_keys[(definition[0], definition[1], instance_key)].get(base_semantic_key)
            if clone is None:
                raise RealPageError(
                    f"runtime source map cannot expand source_semantic_key: {base_semantic_key}"
                )
            normalized["source_semantic_key"] = clone[1]
            normalized.pop("source_instance_key", None)
        normalized_mappings.append(normalized)
    normalized_payload["mappings"] = normalized_mappings

    for field in (
        "inactive_source_components",
        "runtime_elided_source_components",
        "resolved_source_facts",
    ):
        entries = normalized_payload.get(field)
        if not isinstance(entries, list):
            continue
        expanded_entries: list[Any] = []
        for entry in entries:
            semantic_key = entry.get("source_semantic_key") if isinstance(entry, dict) else None
            source = source_by_semantic_key.get(semantic_key) if isinstance(semantic_key, str) else None
            if source is None:
                expanded_entries.append(entry)
                continue
            definition = (
                str(source["source"].get("source", "")),
                str(source["source"].get("composable", "")),
            )
            instances = definition_instances.get(definition)
            if not instances:
                expanded_entries.append(entry)
                continue
            for instance_key in instances:
                clone = copy.deepcopy(entry)
                clone["source_semantic_key"] = clone_keys[
                    (definition[0], definition[1], instance_key)
                ][semantic_key][1]
                expanded_entries.append(clone)
        normalized_payload[field] = expanded_entries
    return expanded_components, normalized_payload


def resolve_runtime_source_map(
    payload: dict[str, Any] | None,
    platform: str,
    page: dict[str, Any],
    source_components: list[dict[str, Any]],
    runtime_components: list[dict[str, Any]],
    runtime_tree_sha256: str | None,
) -> tuple[
    dict[str, str],
    set[str],
    list[dict[str, str]],
    set[str],
    list[dict[str, str]],
    dict[str, list[dict[str, Any]]],
]:
    if payload is None:
        return {}, set(), [], set(), [], {}
    if not {"schema", "platform", "page", "mappings"}.issubset(payload) or not set(payload).issubset(
        {
            "schema", "platform", "page", "runtime_tree_sha256", "mappings",
            "inactive_source_components", "runtime_elided_source_components", "resolved_source_facts",
        }
    ):
        raise RealPageError("runtime source map contains unsupported or missing fields")
    if payload.get("schema") != RUNTIME_SOURCE_MAP_SCHEMA:
        raise RealPageError("runtime source map schema is unsupported")
    if payload.get("platform") != platform:
        raise RealPageError("runtime source map platform does not match the capture")
    if payload.get("page") != page:
        raise RealPageError("runtime source map page/state does not match the capture")
    mappings = payload.get("mappings")
    if not isinstance(mappings, list) or len(mappings) > 10000:
        raise RealPageError("runtime source map mappings must be a bounded list")
    bound_tree_sha256 = payload.get("runtime_tree_sha256")
    if bound_tree_sha256 is not None:
        if not isinstance(bound_tree_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", bound_tree_sha256):
            raise RealPageError("runtime source map runtime_tree_sha256 is malformed")
        if bound_tree_sha256 != runtime_tree_sha256:
            raise RealPageError("runtime source map runtime tree SHA-256 does not match the capture")
    source_by_semantic_key = {
        item["semantic_key"]: item
        for item in source_components
        if isinstance(item.get("source"), dict)
        and isinstance(item["source"].get("call_id"), str)
        and isinstance(item.get("semantic_key"), str)
    }
    inactive_entries = payload.get("inactive_source_components", [])
    if not isinstance(inactive_entries, list) or len(inactive_entries) > 10000:
        raise RealPageError("runtime source map inactive_source_components must be a bounded list")
    inactive_source_ids: set[str] = set()
    normalized_inactive_entries: list[dict[str, str]] = []
    used_inactive_keys: set[str] = set()
    for entry in inactive_entries:
        if not isinstance(entry, dict) or set(entry) != {
            "source_semantic_key", "source_call_id", "reason"
        }:
            raise RealPageError("inactive source entry fields are invalid")
        semantic_key = entry.get("source_semantic_key")
        call_id = entry.get("source_call_id")
        reason = entry.get("reason")
        if (
            not isinstance(semantic_key, str)
            or not semantic_key
            or not isinstance(call_id, str)
            or not call_id
            or reason != "inactive_source_branch"
        ):
            raise RealPageError("inactive source entry values are invalid")
        if semantic_key in used_inactive_keys:
            raise RealPageError(f"runtime source map repeats inactive source_semantic_key: {semantic_key}")
        source = source_by_semantic_key.get(semantic_key)
        if source is None:
            raise RealPageError(f"runtime source map references unknown inactive source_semantic_key: {semantic_key}")
        if source["source"]["call_id"] != call_id:
            raise RealPageError(
                f"runtime source map inactive source_call_id does not match source_semantic_key: {semantic_key}"
            )
        inactive_source_ids.add(source["id"])
        used_inactive_keys.add(semantic_key)
        normalized_inactive_entries.append({
            "source_semantic_key": semantic_key,
            "source_call_id": call_id,
            "reason": reason,
        })
    elided_entries = payload.get("runtime_elided_source_components", [])
    if not isinstance(elided_entries, list) or len(elided_entries) > 10000:
        raise RealPageError("runtime source map runtime_elided_source_components must be a bounded list")
    elided_source_ids: set[str] = set()
    normalized_elided_entries: list[dict[str, str]] = []
    used_elided_keys: set[str] = set()
    for entry in elided_entries:
        if not isinstance(entry, dict) or set(entry) != {
            "source_semantic_key", "source_call_id", "reason"
        }:
            raise RealPageError("runtime-elided source entry fields are invalid")
        semantic_key = entry.get("source_semantic_key")
        call_id = entry.get("source_call_id")
        reason = entry.get("reason")
        if (
            not isinstance(semantic_key, str)
            or not semantic_key
            or not isinstance(call_id, str)
            or not call_id
            or reason not in {
                "runtime_nonsemantic_layout_elision",
                "runtime_flattened_semantic_descendant",
            }
        ):
            raise RealPageError("runtime-elided source entry values are invalid")
        if semantic_key in used_elided_keys:
            raise RealPageError(f"runtime source map repeats runtime-elided source_semantic_key: {semantic_key}")
        source = source_by_semantic_key.get(semantic_key)
        if source is None:
            raise RealPageError(f"runtime source map references unknown runtime-elided source_semantic_key: {semantic_key}")
        if source["source"]["call_id"] != call_id:
            raise RealPageError(
                f"runtime source map runtime-elided source_call_id does not match source_semantic_key: {semantic_key}"
            )
        is_semantic = semantic_source_component(source)
        is_clickable = source["style"]["state"].get("clickable") is True
        if reason == "runtime_nonsemantic_layout_elision" and (is_semantic or is_clickable):
            raise RealPageError(
                f"runtime source map cannot nonsemantically elide a semantic or clickable source component: {semantic_key}"
            )
        if reason == "runtime_flattened_semantic_descendant":
            if not is_semantic or is_clickable:
                raise RealPageError(
                    f"runtime source map can flatten only a non-clickable semantic descendant: {semantic_key}"
                )
            mapped_semantic_keys = {
                mapping.get("source_semantic_key")
                for mapping in payload["mappings"]
                if isinstance(mapping, dict)
            }
            source_by_id = {item["id"]: item for item in source_components}
            parent_id = source.get("parent_id")
            has_mapped_ancestor = False
            while isinstance(parent_id, str) and parent_id in source_by_id:
                parent = source_by_id[parent_id]
                if parent.get("semantic_key") in mapped_semantic_keys:
                    has_mapped_ancestor = True
                    break
                parent_id = parent.get("parent_id")
            if not has_mapped_ancestor:
                raise RealPageError(
                    f"runtime source map flattened semantic component has no explicitly mapped ancestor: {semantic_key}"
                )
        if source["id"] in inactive_source_ids:
            raise RealPageError(
                f"runtime source map cannot mark a source component both inactive and runtime-elided: {semantic_key}"
            )
        elided_source_ids.add(source["id"])
        used_elided_keys.add(semantic_key)
        normalized_elided_entries.append({
            "source_semantic_key": semantic_key,
            "source_call_id": call_id,
            "reason": reason,
        })
    fact_entries = payload.get("resolved_source_facts", [])
    if not isinstance(fact_entries, list) or len(fact_entries) > 10000:
        raise RealPageError("runtime source map resolved_source_facts must be a bounded list")
    resolved_source_facts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    used_fact_paths: set[tuple[str, str]] = set()
    for fact in fact_entries:
        if not isinstance(fact, dict) or set(fact) != {
            "source_semantic_key", "source_call_id", "path", "value", "origin", "source"
        }:
            raise RealPageError("resolved source fact fields are invalid")
        semantic_key = fact.get("source_semantic_key")
        call_id = fact.get("source_call_id")
        path = fact.get("path")
        value = fact.get("value")
        origin = fact.get("origin")
        evidence_source = fact.get("source")
        if (
            not isinstance(semantic_key, str)
            or not semantic_key
            or not isinstance(call_id, str)
            or not call_id
            or path not in {"style.asset.resource", "style.asset.sha256"}
            or origin != "source_resolved"
            or not isinstance(evidence_source, str)
            or not evidence_source
            or evidence_source.startswith("/")
            or ".." in Path(evidence_source).parts
        ):
            raise RealPageError("resolved source fact values are invalid")
        if path == "style.asset.resource" and (
            not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]+", value)
        ):
            raise RealPageError("resolved asset resource fact is malformed")
        if path == "style.asset.sha256" and (
            not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
        ):
            raise RealPageError("resolved asset SHA-256 fact is malformed")
        source = source_by_semantic_key.get(semantic_key)
        if source is None:
            raise RealPageError(f"runtime source map references unknown resolved source_semantic_key: {semantic_key}")
        if source["source"]["call_id"] != call_id:
            raise RealPageError(
                f"runtime source map resolved source_call_id does not match source_semantic_key: {semantic_key}"
            )
        fact_key = (semantic_key, str(path))
        if fact_key in used_fact_paths:
            raise RealPageError(f"runtime source map repeats resolved source fact: {semantic_key} {path}")
        used_fact_paths.add(fact_key)
        resolved_source_facts[source["id"]].append({
            "path": path,
            "value": value,
            "origin": origin,
            "source": evidence_source,
        })
    runtime_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    runtime_by_component_id = {component["id"]: component for component in runtime_components}
    for component in runtime_components:
        runtime_id = runtime_semantic_key(component)
        if isinstance(runtime_id, str):
            runtime_by_key[runtime_id].append(component)
    source_to_runtime: dict[str, str] = {}
    used_runtime_selectors: set[tuple[str, str]] = set()
    used_runtime_component_ids: set[str] = set()
    used_source_semantic_keys: set[str] = set()
    for mapping in mappings:
        if not isinstance(mapping, dict):
            raise RealPageError(
                "runtime source map entry must be an object"
            )
        selector_fields = {field for field in ("runtime_id", "runtime_component_id") if field in mapping}
        if (
            len(selector_fields) != 1
            or set(mapping) != selector_fields | {"source_semantic_key", "source_call_id"}
        ):
            raise RealPageError(
                "runtime source map entry must contain one runtime selector plus source_semantic_key and source_call_id"
            )
        selector_field = next(iter(selector_fields))
        runtime_selector = mapping.get(selector_field)
        source_semantic_key = mapping.get("source_semantic_key")
        source_call_id = mapping.get("source_call_id")
        if (
            not isinstance(runtime_selector, str) or not runtime_selector
            or not isinstance(source_semantic_key, str) or not source_semantic_key
            or not isinstance(source_call_id, str) or not source_call_id
        ):
            raise RealPageError("runtime source map entry IDs must be non-empty strings")
        selector = (selector_field, runtime_selector)
        if selector in used_runtime_selectors:
            raise RealPageError(f"runtime source map repeats {selector_field}: {runtime_selector}")
        if source_semantic_key in used_source_semantic_keys:
            raise RealPageError(f"runtime source map repeats source_semantic_key: {source_semantic_key}")
        if selector_field == "runtime_component_id":
            if bound_tree_sha256 is None:
                raise RealPageError("runtime_component_id mappings require runtime_tree_sha256")
            runtime = runtime_by_component_id.get(runtime_selector)
            if runtime is None:
                raise RealPageError(
                    f"runtime source map references unknown runtime_component_id: {runtime_selector}"
                )
        else:
            runtime_matches = runtime_by_key.get(runtime_selector, [])
            if not runtime_matches:
                raise RealPageError(f"runtime source map references unknown runtime_id: {runtime_selector}")
            if len(runtime_matches) != 1:
                raise RealPageError(f"runtime source map references ambiguous runtime_id: {runtime_selector}")
            runtime = runtime_matches[0]
        if runtime["id"] in used_runtime_component_ids:
            raise RealPageError(f"runtime source map repeats runtime component: {runtime['id']}")
        source = source_by_semantic_key.get(source_semantic_key)
        if source is None:
            raise RealPageError(
                f"runtime source map references unknown source_semantic_key: {source_semantic_key}"
            )
        if source["source"]["call_id"] != source_call_id:
            raise RealPageError(
                f"runtime source map source_call_id does not match source_semantic_key: {source_semantic_key}"
            )
        if source["id"] in inactive_source_ids:
            raise RealPageError(
                f"runtime source map maps an inactive source component: {source_semantic_key}"
            )
        if source["id"] in elided_source_ids:
            raise RealPageError(
                f"runtime source map maps a runtime-elided source component: {source_semantic_key}"
            )
        if not source_runtime_type_compatible(source["type"], runtime):
            raise RealPageError(
                f"runtime source map type mismatch for {selector_field} {runtime_selector} and source_call_id {source_call_id}"
            )
        source_to_runtime[source["id"]] = runtime["id"]
        used_runtime_selectors.add(selector)
        used_runtime_component_ids.add(runtime["id"])
        used_source_semantic_keys.add(source_semantic_key)
    return (
        source_to_runtime,
        inactive_source_ids,
        normalized_inactive_entries,
        elided_source_ids,
        normalized_elided_entries,
        dict(resolved_source_facts),
    )


def semantic_runtime_component(component: dict[str, Any]) -> bool:
    content = component["style"]["content"]
    state = component["style"]["state"]
    has_semantic_content = any(
        content.get(field) for field in ("text", "placeholder", "content_description")
    )
    if component["type"] in {"Button", "ImageButton"}:
        return bool(runtime_semantic_key(component) or has_semantic_content or state.get("clickable"))
    return bool(
        runtime_semantic_key(component)
        or has_semantic_content
        or component["type"] in {"TextField", "Image", "CheckBox", "Switch", "RadioButton"}
    )


def match_source_to_runtime(
    source_components: list[dict[str, Any]],
    runtime_components: list[dict[str, Any]],
    explicit_source_to_runtime: dict[str, str] | None = None,
    excluded_source_ids: set[str] | None = None,
) -> tuple[dict[str, str], dict[str, int], set[str], dict[str, str]]:
    excluded_source_ids = excluded_source_ids or set()
    source_by_id = {item["id"]: item for item in source_components}
    runtime_by_id = {item["id"]: item for item in runtime_components}
    identified_runtime_ids = {
        runtime["id"]
        for runtime in runtime_components
        if isinstance(runtime_semantic_key(runtime), str)
    }
    source_to_runtime = dict(explicit_source_to_runtime or {})
    used_runtime = set(source_to_runtime.values())
    mapping_methods = {source_id: "explicit_runtime_source_map" for source_id in source_to_runtime}
    checks = {
        "explicit_runtime_source_map_matches": len(source_to_runtime),
        "stable_runtime_id_matches": 0,
        "exact_text_matches": 0,
        "exact_content_description_matches": 0,
        "scoped_hierarchy_order_matches": 0,
        "same_row_dynamic_text_matches": 0,
        "ordered_text_field_matches": 0,
        "hierarchy_matches": 0,
    }

    source_by_semantic_key = {
        item["semantic_key"]: item
        for item in source_components
        if isinstance(item.get("semantic_key"), str)
    }
    for runtime in runtime_components:
        runtime_key = runtime_semantic_key(runtime)
        source = source_by_semantic_key.get(runtime_key) if isinstance(runtime_key, str) else None
        if source is None or source["id"] in source_to_runtime or source["id"] in excluded_source_ids:
            continue
        source_to_runtime[source["id"]] = runtime["id"]
        used_runtime.add(runtime["id"])
        mapping_methods[source["id"]] = "stable_runtime_id"
        checks["stable_runtime_id_matches"] += 1

    def choose_unique(source: dict[str, Any], field: str) -> str | None:
        value = source["style"]["content"].get(field)
        if not isinstance(value, str):
            return None
        candidates = [
            runtime
            for runtime in runtime_components
            if runtime["id"] not in used_runtime
            and runtime["id"] not in identified_runtime_ids
            and runtime["style"]["content"].get(field) == value
            and source_runtime_type_compatible(source["type"], runtime)
        ]
        return candidates[0]["id"] if len(candidates) == 1 else None

    for field, counter in (("text", "exact_text_matches"), ("content_description", "exact_content_description_matches")):
        for source in source_components:
            if (
                source["id"] in source_to_runtime
                or source["id"] in excluded_source_ids
                or source["source"]["custom_component"]
            ):
                continue
            runtime_id = choose_unique(source, field)
            if runtime_id is not None:
                source_to_runtime[source["id"]] = runtime_id
                used_runtime.add(runtime_id)
                mapping_methods[source["id"]] = f"exact_{field}"
                checks[counter] += 1

    def nearest_mapped_ancestor(
        component_id: str,
        by_id: dict[str, dict[str, Any]],
        mapped_ids: set[str],
    ) -> str | None:
        current = by_id[component_id].get("parent_id")
        while isinstance(current, str) and current in by_id:
            if current in mapped_ids:
                return current
            current = by_id[current].get("parent_id")
        return None

    # Dynamic labels and fields often have no stable runtime ID. Resolve them only inside a
    # mapped source/runtime boundary, preserving compatible preorder and never crossing a nested
    # mapped boundary. Run this again after common-ancestor discovery because flattened runtime
    # trees may not expose a usable container until their static leaves have been joined.
    def match_scoped_hierarchy_order() -> None:
        mapped_source_ids = set(source_to_runtime)
        mapped_runtime_ids = set(source_to_runtime.values())
        source_preorder = {
            parent_id: tree_descendants(parent_id, source_by_id)
            for parent_id in mapped_source_ids
        }
        runtime_preorder = {
            parent_id: tree_descendants(parent_id, runtime_by_id)
            for parent_id in mapped_runtime_ids
        }
        source_depths = {
            component_id: len(ancestors(component_id, source_by_id))
            for component_id in mapped_source_ids
        }
        for source_parent_id in sorted(mapped_source_ids, key=source_depths.get, reverse=True):
            runtime_parent_id = source_to_runtime[source_parent_id]
            source_candidates = [
                source_by_id[item]
                for item in source_preorder[source_parent_id]
                if item not in source_to_runtime
                and item not in excluded_source_ids
                and nearest_mapped_ancestor(item, source_by_id, mapped_source_ids) == source_parent_id
                and not source_by_id[item]["source"]["custom_component"]
                and semantic_source_component(source_by_id[item])
            ]
            runtime_candidates = [
                runtime_by_id[item]
                for item in runtime_preorder[runtime_parent_id]
                if item not in used_runtime
                and item not in identified_runtime_ids
                and nearest_mapped_ancestor(item, runtime_by_id, mapped_runtime_ids) == runtime_parent_id
                and semantic_runtime_component(runtime_by_id[item])
            ]
            cursor = 0
            for runtime in runtime_candidates:
                matched_index: int | None = None
                for index in range(cursor, len(source_candidates)):
                    source = source_candidates[index]
                    if not source_runtime_type_compatible(source["type"], runtime):
                        continue
                    source_text = source["style"]["content"].get("text")
                    runtime_text = runtime["style"]["content"].get("text")
                    if (
                        isinstance(source_text, str)
                        and isinstance(runtime_text, str)
                        and source_text != runtime_text
                    ):
                        continue
                    matched_index = index
                    break
                if matched_index is None:
                    continue
                source = source_candidates[matched_index]
                source_to_runtime[source["id"]] = runtime["id"]
                used_runtime.add(runtime["id"])
                mapping_methods[source["id"]] = "scoped_hierarchy_order"
                checks["scoped_hierarchy_order_matches"] += 1
                cursor = matched_index + 1

    def source_business_owner(component_id: str) -> str:
        current = component_id
        root_id = component_id
        while current in source_by_id:
            source = source_by_id[current]
            root_id = current
            if source["source"]["custom_component"]:
                return current
            parent_id = source.get("parent_id")
            if not isinstance(parent_id, str):
                break
            current = parent_id
        return root_id

    def match_business_anchor_order() -> None:
        source_order = {component["id"]: index for index, component in enumerate(source_components)}
        runtime_order = {component["id"]: index for index, component in enumerate(runtime_components)}
        changed = True
        while changed:
            changed = False
            mapped_source_ids = set(source_to_runtime)
            for source in source_components:
                source_id = source["id"]
                if (
                    source_id in source_to_runtime
                    or source_id in excluded_source_ids
                    or source["source"]["custom_component"]
                    or not semantic_source_component(source)
                ):
                    continue
                owner_id = source_business_owner(source_id)
                preceding_anchors = [
                    anchor_id
                    for anchor_id in mapped_source_ids
                    if source_business_owner(anchor_id) == owner_id
                    and source_order[anchor_id] < source_order[source_id]
                    and semantic_source_component(source_by_id[anchor_id])
                ]
                if not preceding_anchors:
                    continue
                previous_source_id = max(preceding_anchors, key=source_order.get)
                previous_runtime_index = runtime_order[source_to_runtime[previous_source_id]]
                following_anchors = [
                    anchor_id
                    for anchor_id in mapped_source_ids
                    if source_order[anchor_id] > source_order[source_id]
                    and runtime_order[source_to_runtime[anchor_id]] > previous_runtime_index
                ]
                next_runtime_index = (
                    runtime_order[source_to_runtime[min(following_anchors, key=source_order.get)]]
                    if following_anchors
                    else len(runtime_components)
                )
                candidates = [
                    runtime
                    for runtime in runtime_components
                    if runtime["id"] not in used_runtime
                    and runtime["id"] not in identified_runtime_ids
                    and previous_runtime_index < runtime_order[runtime["id"]] < next_runtime_index
                    and semantic_runtime_component(runtime)
                    and source_runtime_type_compatible(source["type"], runtime)
                ]
                source_text = source["style"]["content"].get("text")
                if isinstance(source_text, str):
                    candidates = [
                        runtime
                        for runtime in candidates
                        if runtime["style"]["content"].get("text") == source_text
                    ]
                if len(candidates) != 1:
                    continue
                runtime = candidates[0]
                source_to_runtime[source_id] = runtime["id"]
                used_runtime.add(runtime["id"])
                mapping_methods[source_id] = "scoped_hierarchy_order"
                checks["scoped_hierarchy_order_matches"] += 1
                changed = True
                break

    def match_same_row_dynamic_text() -> None:
        for source in source_components:
            source_id = source["id"]
            parent_id = source.get("parent_id")
            parent = source_by_id.get(parent_id or "")
            if (
                source_id in source_to_runtime
                or source_id in excluded_source_ids
                or source["source"]["custom_component"]
                or source["type"] not in {"Text", "BasicText", "ClickableText"}
                or source["style"]["content"].get("text") is not None
                or not any(
                    item.get("path") == "style.content.text"
                    for item in source.get("unresolved", [])
                )
                or parent is None
                or parent["type"] != "Row"
            ):
                continue

            sibling_ids = parent["children_ids"]
            source_index = sibling_ids.index(source_id)
            anchors = [
                (sibling_ids.index(sibling_id), runtime_by_id[source_to_runtime[sibling_id]])
                for sibling_id in sibling_ids
                if sibling_id in source_to_runtime
                and source_by_id[sibling_id]["type"] in {"Text", "BasicText", "ClickableText"}
            ]
            if not anchors:
                continue
            runtime_parent_ids = {anchor.get("parent_id") for _index, anchor in anchors}
            if len(runtime_parent_ids) != 1 or None in runtime_parent_ids:
                continue
            runtime_parent_id = next(iter(runtime_parent_ids))

            def vertically_aligned(candidate: dict[str, Any]) -> bool:
                candidate_bounds = candidate.get("bounds_px")
                if not isinstance(candidate_bounds, dict):
                    return False
                candidate_top = candidate_bounds.get("y")
                candidate_height = candidate_bounds.get("height")
                if not isinstance(candidate_top, (int, float)) or not isinstance(
                    candidate_height, (int, float)
                ) or candidate_height <= 0:
                    return False
                candidate_bottom = candidate_top + candidate_height
                for _index, anchor in anchors:
                    anchor_bounds = anchor.get("bounds_px")
                    if not isinstance(anchor_bounds, dict):
                        return False
                    anchor_top = anchor_bounds.get("y")
                    anchor_height = anchor_bounds.get("height")
                    if not isinstance(anchor_top, (int, float)) or not isinstance(
                        anchor_height, (int, float)
                    ) or anchor_height <= 0:
                        return False
                    overlap = min(candidate_bottom, anchor_top + anchor_height) - max(
                        candidate_top, anchor_top
                    )
                    if overlap < min(candidate_height, anchor_height) * 0.5:
                        return False
                return True

            def horizontally_ordered(candidate: dict[str, Any]) -> bool:
                candidate_bounds = candidate.get("bounds_px")
                if not isinstance(candidate_bounds, dict):
                    return False
                candidate_x = candidate_bounds.get("x")
                if not isinstance(candidate_x, (int, float)):
                    return False
                for anchor_index, anchor in anchors:
                    anchor_bounds = anchor.get("bounds_px")
                    anchor_x = anchor_bounds.get("x") if isinstance(anchor_bounds, dict) else None
                    if not isinstance(anchor_x, (int, float)):
                        return False
                    if anchor_index < source_index and candidate_x < anchor_x:
                        return False
                    if anchor_index > source_index and candidate_x > anchor_x:
                        return False
                return True

            candidates = [
                runtime
                for runtime in runtime_components
                if runtime["id"] not in used_runtime
                and runtime["id"] not in identified_runtime_ids
                and runtime.get("parent_id") == runtime_parent_id
                and source_runtime_type_compatible(source["type"], runtime)
                and semantic_runtime_component(runtime)
                and vertically_aligned(runtime)
                and horizontally_ordered(runtime)
            ]
            if len(candidates) != 1:
                continue
            runtime = candidates[0]
            source_to_runtime[source_id] = runtime["id"]
            used_runtime.add(runtime["id"])
            mapping_methods[source_id] = "same_row_dynamic_text"
            checks["same_row_dynamic_text_matches"] += 1

    match_scoped_hierarchy_order()
    match_same_row_dynamic_text()

    remaining_text_fields = [
        source
        for source in source_components
        if source["id"] not in source_to_runtime
        and source["id"] not in excluded_source_ids
        and not source["source"]["custom_component"]
        and source["type"] in {"TextField", "OutlinedTextField", "BasicTextField"}
    ]
    remaining_runtime_text_fields = [
        runtime
        for runtime in runtime_components
        if runtime["id"] not in used_runtime
        and runtime["id"] not in identified_runtime_ids
        and runtime["type"] == "TextField"
    ]
    if len(remaining_text_fields) == len(remaining_runtime_text_fields):
        for source, runtime in zip(remaining_text_fields, remaining_runtime_text_fields, strict=True):
            source_to_runtime[source["id"]] = runtime["id"]
            used_runtime.add(runtime["id"])
            mapping_methods[source["id"]] = "ordered_text_field"
            checks["ordered_text_field_matches"] += 1

    active_definitions = {
        (source_by_id[source_id]["source"]["source"], source_by_id[source_id]["source"]["composable"])
        for source_id in source_to_runtime
    }
    for source in source_components:
        source_id = source["id"]
        definition = (source["source"]["source"], source["source"]["composable"])
        if (
            source_id in source_to_runtime
            or source_id in excluded_source_ids
            or source["source"]["custom_component"]
            or definition not in active_definitions
        ):
            continue
        candidates = [
            runtime
            for runtime in runtime_components
            if runtime["id"] not in used_runtime
            and runtime["id"] not in identified_runtime_ids
            and source_runtime_type_compatible(source["type"], runtime)
        ]
        remaining_same_type = [
            item
            for item in source_components
            if (item["source"]["source"], item["source"]["composable"]) == definition
            and not item["source"]["custom_component"]
            and item["type"] == source["type"]
            and item["id"] not in source_to_runtime
            and item["id"] not in excluded_source_ids
        ]
        if len(candidates) == len(remaining_same_type) == 1:
            source_to_runtime[source_id] = candidates[0]["id"]
            used_runtime.add(candidates[0]["id"])
            mapping_methods[source_id] = "single_remaining_type"

    depth_cache: dict[str, int] = {}

    def source_depth(component_id: str) -> int:
        if component_id in depth_cache:
            return depth_cache[component_id]
        parent = source_by_id[component_id]["parent_id"]
        depth_cache[component_id] = 0 if parent is None else source_depth(parent) + 1
        return depth_cache[component_id]

    changed = True
    while changed:
        changed = False
        for source in sorted(source_components, key=lambda item: source_depth(item["id"]), reverse=True):
            source_id = source["id"]
            if (
                source_id in source_to_runtime
                or source_id in excluded_source_ids
                or source["source"]["custom_component"]
            ):
                continue
            mapped_descendants = [
                source_to_runtime[item]
                for item in source_descendants(source_id, source_by_id)
                if item in source_to_runtime
            ]
            # One mapped leaf is not enough evidence to identify a platform container as
            # the corresponding source container.  That guess can turn a full-screen
            # Android View into a business component and hide unrelated siblings in the
            # generated Stack.  Require a real common ancestor relationship instead.
            if len(set(mapped_descendants)) < 2:
                continue
            candidate_id = lowest_common_runtime_ancestor(mapped_descendants, runtime_by_id)
            if candidate_id in mapped_descendants:
                candidate_id = runtime_by_id[candidate_id].get("parent_id")
            if (
                candidate_id is not None
                and candidate_id not in used_runtime
                and candidate_id not in identified_runtime_ids
                and source_runtime_type_compatible(source["type"], runtime_by_id[candidate_id])
            ):
                source_to_runtime[source_id] = candidate_id
                used_runtime.add(candidate_id)
                mapping_methods[source_id] = "hierarchy_common_ancestor"
                checks["hierarchy_matches"] += 1
                changed = True

    match_business_anchor_order()

    active_definitions = {
        (source_by_id[source_id]["source"]["source"], source_by_id[source_id]["source"]["composable"])
        for source_id in source_to_runtime
    }
    roots = [item for item in source_components if item["parent_id"] is None]
    active_definitions.update(
        (item["source"]["source"], item["source"]["composable"]) for item in roots
    )
    active_definitions.update(
        (source_by_id[source_id]["source"]["source"], source_by_id[source_id]["source"]["composable"])
        for source_id in source_to_runtime
    )
    return source_to_runtime, checks, active_definitions, mapping_methods
