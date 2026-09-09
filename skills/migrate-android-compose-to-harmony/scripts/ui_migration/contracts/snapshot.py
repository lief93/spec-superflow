from __future__ import annotations
import copy
from component_required_facts import normalize_required_facts
from page_snapshot import PageSnapshotError, normalize_provenance, normalize_style, normalize_unresolved, require_token
from typing import Any
from ui_migration.common import ArkUIPageError, BUTTON_CONTAINER_COMPONENTS


def runtime_overlay_style_path_allowed(method: str, path: str) -> bool:
    if not path.startswith("style."):
        return False
    if method in {"business_component_id", "child_source_anchor"}:
        return path.startswith("style.state.")
    return True


def is_direct_native_wrapper(
    target: dict[str, Any], descendant: dict[str, Any]
) -> bool:
    source = target.get("source")
    return (
        descendant.get("parent_id") == target.get("id")
        and isinstance(source, dict)
        and source.get("custom_component") is True
        and descendant.get("type") in BUTTON_CONTAINER_COMPONENTS
    )


def normalize_source_component_tree(value: Any) -> dict[str, Any]:
    required_fields = {
        "schema", "definitions", "root_ids", "business_root_ids", "business_component_ids",
        "third_party_component_ids", "components"
    }
    optional_fields = {"layout_relationships"}
    if (
        not isinstance(value, dict)
        or not required_fields.issubset(value)
        or set(value) - required_fields - optional_fields
    ):
        raise ArkUIPageError("Android page JSON source component tree is malformed")
    if value.get("schema") != "android-to-harmony.source-component-tree.v2":
        raise ArkUIPageError("Android page JSON source component tree schema is unsupported")
    raw_roots = value.get("root_ids")
    raw_business_roots = value.get("business_root_ids")
    raw_business_components = value.get("business_component_ids")
    raw_third_party_components = value.get("third_party_component_ids")
    raw_definitions = value.get("definitions")
    raw_components = value.get("components")
    if (
        not isinstance(raw_roots, list)
        or not isinstance(raw_business_roots, list)
        or not isinstance(raw_business_components, list)
        or not isinstance(raw_third_party_components, list)
        or not isinstance(raw_definitions, list)
        or not isinstance(raw_components, list)
        or len(raw_definitions) > 10000
        or len(raw_components) > 10000
    ):
        raise ArkUIPageError("Android page JSON source component tree is malformed")
    try:
        root_ids = [require_token(item, "Android page source root id") for item in raw_roots]
        business_root_ids = [
            require_token(item, "Android page business root id")
            for item in raw_business_roots
        ]
        business_component_ids = [
            require_token(item, "Android page business component id")
            for item in raw_business_components
        ]
        third_party_component_ids = [
            require_token(item, "Android page third-party component id")
            for item in raw_third_party_components
        ]
    except PageSnapshotError as error:
        raise ArkUIPageError(str(error)) from error
    if (
        len(root_ids) != len(set(root_ids))
        or len(business_root_ids) != len(set(business_root_ids))
        or len(business_component_ids) != len(set(business_component_ids))
        or len(third_party_component_ids) != len(set(third_party_component_ids))
    ):
        raise ArkUIPageError("Android page JSON source component tree repeats an identity")
    definitions: list[dict[str, Any]] = []
    definition_ids: set[str] = set()
    allowed_component_kinds = {
        "project_component", "compose_primitive", "third_party_component",
        "platform_component", "custom_draw",
    }
    for raw in raw_definitions:
        required_definition_fields = {"id", "type", "component_kind", "identity", "dependency", "declared_from"}
        if (not isinstance(raw, dict) or not required_definition_fields.issubset(raw)
                or set(raw) - required_definition_fields - {'parameters', 'ui_template'}):
            raise ArkUIPageError("Android page JSON source component definition is malformed")
        if 'parameters' in raw or 'ui_template' in raw:
            template = raw.get('ui_template')
            if (not isinstance(raw.get('parameters'), list) or not isinstance(template, dict)
                    or template.get('stage') != 'before-state-projection'
                    or not isinstance(template.get('calls'), list)):
                raise ArkUIPageError('Android page JSON source component template is malformed')
        try:
            item_id = require_token(raw.get("id"), "Android page source definition id")
            item_type = require_token(raw.get("type"), "Android page source definition type")
        except PageSnapshotError as error:
            raise ArkUIPageError(str(error)) from error
        if item_id in definition_ids or raw.get("component_kind") not in allowed_component_kinds:
            raise ArkUIPageError("Android page JSON source component definition is inconsistent")
        identity = raw.get("identity")
        declared_from = raw.get("declared_from")
        dependency = raw.get("dependency")
        if (
            not isinstance(identity, dict)
            or set(identity) != {"status", "qualified_name", "source", "symbol"}
            or not isinstance(identity.get("status"), str)
            or not isinstance(identity.get("symbol"), str)
            or not isinstance(declared_from, dict)
            or set(declared_from) != {"source", "composable", "package"}
            or not isinstance(declared_from.get("source"), str)
            or not isinstance(declared_from.get("composable"), str)
        ):
            raise ArkUIPageError("Android page JSON source component definition identity is malformed")
        if raw["component_kind"] == "third_party_component":
            if (
                not isinstance(dependency, dict)
                or set(dependency) != {"qualified_name", "package_root", "version", "version_status"}
                or not isinstance(dependency.get("qualified_name"), str)
                or not isinstance(dependency.get("package_root"), str)
                or dependency.get("version") is not None
                or dependency.get("version_status") != "requires_resolved_dependency_graph"
            ):
                raise ArkUIPageError("Android page JSON third-party component dependency is malformed")
        elif dependency is not None:
            raise ArkUIPageError("Android page JSON non-third-party component has a dependency record")
        definition_ids.add(item_id)
        definitions.append(copy.deepcopy(raw))
    components: list[dict[str, Any]] = []
    component_ids: set[str] = set()
    for raw in raw_components:
        required_component_fields = {
            "id", "semantic_key", "type", "definition_id", "component_kind", "node_kind", "parent_id", "children_ids",
            "business_parent_id", "business_owner_id", "business_children_ids", "sibling_index",
            "capture_membership", "source", "arguments", "modifiers", "style", "provenance",
            "unresolved", "runtime_instances", "runtime_descendant_ids",
        }
        optional_component_fields = {
            "slot_argument_name", "slot_invocation", "required_facts"
        }
        if (
            not isinstance(raw, dict)
            or not required_component_fields.issubset(raw)
            or set(raw) - required_component_fields - optional_component_fields
        ):
            raise ArkUIPageError("Android page JSON source component tree contains a malformed component")
        try:
            component_id = require_token(raw.get("id"), "Android page source component id")
            semantic_key = require_token(raw.get("semantic_key"), "Android page source semantic key")
            component_type = require_token(raw.get("type"), "Android page source component type")
            component_definition_id = require_token(
                raw.get("definition_id"), "Android page source component definition id"
            )
            parent_id = raw.get("parent_id")
            if parent_id is not None:
                parent_id = require_token(parent_id, "Android page source parent id")
            children_ids = [
                require_token(item, "Android page source child id")
                for item in raw.get("children_ids", [])
            ]
            business_parent_id = raw.get("business_parent_id")
            if business_parent_id is not None:
                business_parent_id = require_token(
                    business_parent_id, "Android page business parent id"
                )
            business_owner_id = raw.get("business_owner_id")
            if business_owner_id is not None:
                business_owner_id = require_token(
                    business_owner_id, "Android page business owner id"
                )
            business_children_ids = [
                require_token(item, "Android page business child id")
                for item in raw.get("business_children_ids", [])
            ]
            runtime_descendant_ids = [
                require_token(item, "Android page source runtime descendant id")
                for item in raw.get("runtime_descendant_ids", [])
            ]
        except PageSnapshotError as error:
            raise ArkUIPageError(str(error)) from error
        if component_id in component_ids:
            raise ArkUIPageError("Android page JSON source component tree repeats a component id")
        component_ids.add(component_id)
        if (
            len(children_ids) != len(set(children_ids))
            or len(business_children_ids) != len(set(business_children_ids))
            or len(runtime_descendant_ids) != len(set(runtime_descendant_ids))
        ):
            raise ArkUIPageError("Android page JSON source component tree repeats a child id")
        node_kind = raw.get("node_kind")
        if node_kind not in {
            "screen_root", "project_component", "third_party_component", "platform_component",
            "custom_draw", "content_slot", "layout_primitive", "visual_primitive"
        }:
            raise ArkUIPageError("Android page JSON source component node kind is unsupported")
        component_kind = raw.get("component_kind")
        if component_kind not in allowed_component_kinds or component_definition_id not in definition_ids:
            raise ArkUIPageError("Android page JSON source component definition reference is inconsistent")
        sibling_index = raw.get("sibling_index")
        if type(sibling_index) is not int or sibling_index < 0:
            raise ArkUIPageError("Android page JSON source component sibling index is malformed")
        if raw.get("capture_membership") not in {"observed_instance", "candidate_active_descendant"}:
            raise ArkUIPageError("Android page JSON source component capture membership is unsupported")
        source = raw.get("source")
        if (
            not isinstance(source, dict)
            or not isinstance(source.get("source"), str)
            or not isinstance(source.get("composable"), str)
            or not isinstance(source.get("call_id"), str)
        ):
            raise ArkUIPageError("Android page JSON source component provenance is malformed")
        instances = raw.get("runtime_instances")
        if not isinstance(instances, list):
            raise ArkUIPageError("Android page JSON source runtime instances are malformed")
        for instance in instances:
            if (
                not isinstance(instance, dict)
                or set(instance) != {"runtime_component_id", "mapping_method", "mapping_status"}
                or instance.get("mapping_status") not in {"proven", "candidate"}
            ):
                raise ArkUIPageError("Android page JSON source runtime instance is malformed")
            try:
                require_token(instance.get("runtime_component_id"), "Android page runtime component id")
                require_token(instance.get("mapping_method"), "Android page runtime mapping method")
            except PageSnapshotError as error:
                raise ArkUIPageError(str(error)) from error
        try:
            normalized_style = normalize_style(raw.get("style"), f"Android page source component {component_id}.style")
            normalized_provenance = normalize_provenance(
                raw.get("provenance"), f"Android page source component {component_id}.provenance"
            )
            normalized_unresolved = normalize_unresolved(
                raw.get("unresolved"), f"Android page source component {component_id}.unresolved"
            )
        except PageSnapshotError as error:
            raise ArkUIPageError(str(error)) from error
        try:
            normalized_required_facts = normalize_required_facts(
                raw.get("required_facts") or [],
                f"Android page source component {component_id}.required_facts",
            )
        except ValueError as error:
            raise ArkUIPageError(str(error)) from error
        component = copy.deepcopy(raw)
        component["definition_id"] = component_definition_id
        component["component_kind"] = component_kind
        component["node_kind"] = node_kind
        component["business_parent_id"] = business_parent_id
        component["business_owner_id"] = business_owner_id
        component["business_children_ids"] = business_children_ids
        component["runtime_descendant_ids"] = runtime_descendant_ids
        slot_argument_name = raw.get("slot_argument_name")
        if slot_argument_name is not None:
            try:
                slot_argument_name = require_token(
                    slot_argument_name, "Android page source slot argument name"
                )
            except PageSnapshotError as error:
                raise ArkUIPageError(str(error)) from error
        slot_invocation = raw.get("slot_invocation")
        if slot_invocation is not None:
            if (not isinstance(slot_invocation, dict)
                    or not set(slot_invocation).issubset({'name', 'arguments', 'parameters', 'expression'})
                    or ('expression' in slot_invocation and not isinstance(slot_invocation['expression'], str))
                    or any(not isinstance(slot_invocation.get(key, []), list)
                           or not all(isinstance(value, str) for value in slot_invocation.get(key, []))
                           for key in ('arguments', 'parameters'))):
                raise ArkUIPageError("Android page source slot invocation is malformed")
            try:
                slot_invocation = {
                    **slot_invocation,
                    "name": require_token(
                        slot_invocation.get("name"),
                        "Android page source slot invocation name",
                    )
                }
            except PageSnapshotError as error:
                raise ArkUIPageError(str(error)) from error
        component["slot_argument_name"] = slot_argument_name
        component["slot_invocation"] = slot_invocation
        component["style"] = normalized_style
        component["provenance"] = normalized_provenance
        component["unresolved"] = normalized_unresolved
        component["required_facts"] = normalized_required_facts
        components.append(component)
    by_id = {item["id"]: item for item in components}
    if any(root_id not in by_id or by_id[root_id]["parent_id"] is not None for root_id in root_ids):
        raise ArkUIPageError("Android page JSON source component root is inconsistent")
    business_id_set = set(business_component_ids)
    third_party_id_set = set(third_party_component_ids)
    if any(
        component_id not in by_id
        or by_id[component_id]["node_kind"] not in {"screen_root", "project_component"}
        for component_id in business_component_ids
    ):
        raise ArkUIPageError("Android page JSON business component index is inconsistent")
    if any(
        component_id not in by_id
        or by_id[component_id]["component_kind"] != "third_party_component"
        or by_id[component_id]["node_kind"] != "third_party_component"
        for component_id in third_party_component_ids
    ):
        raise ArkUIPageError("Android page JSON third-party component index is inconsistent")
    if third_party_id_set != {
        item["id"] for item in components if item["component_kind"] == "third_party_component"
    }:
        raise ArkUIPageError("Android page JSON third-party component index is incomplete")
    if any(
        root_id not in business_id_set or by_id[root_id]["business_parent_id"] is not None
        for root_id in business_root_ids
    ):
        raise ArkUIPageError("Android page JSON business component root is inconsistent")
    for component in components:
        parent_id = component["parent_id"]
        if parent_id is not None and parent_id not in by_id:
            raise ArkUIPageError("Android page JSON source component parent is unknown")
        if any(child_id not in by_id for child_id in component["children_ids"]):
            raise ArkUIPageError("Android page JSON source component child is unknown")
        if parent_id is not None and component["id"] not in by_id[parent_id]["children_ids"]:
            raise ArkUIPageError("Android page JSON source component relationship is inconsistent")
        for index, child_id in enumerate(component["children_ids"]):
            child = by_id[child_id]
            if child["parent_id"] != component["id"] or child["sibling_index"] != index:
                raise ArkUIPageError("Android page JSON source component relationship is inconsistent")
        business_parent_id = component["business_parent_id"]
        if business_parent_id is not None and business_parent_id not in business_id_set:
            raise ArkUIPageError("Android page JSON source business parent is inconsistent")
        if component["node_kind"] in {"screen_root", "project_component"}:
            if component["business_owner_id"] != component["id"]:
                raise ArkUIPageError("Android page JSON business component owner is inconsistent")
        elif component["business_owner_id"] not in business_id_set:
            raise ArkUIPageError("Android page JSON source business owner is inconsistent")
        for child_id in component["business_children_ids"]:
            if child_id not in business_id_set or by_id[child_id]["business_parent_id"] != component["id"]:
                raise ArkUIPageError("Android page JSON source business relationship is inconsistent")
    raw_layout_relationships = value.get("layout_relationships", [])
    if not isinstance(raw_layout_relationships, list) or len(raw_layout_relationships) > 10000:
        raise ArkUIPageError("Android page JSON source layout relationships are malformed")
    layout_relationships: list[dict[str, Any]] = []
    relationship_ids: set[str] = set()
    for raw in raw_layout_relationships:
        if not isinstance(raw, dict) or set(raw) != {
            "id", "container_id", "container_type", "subject_id", "subject_reference",
            "composition", "draw_order", "source_expression", "branch_resolution",
            "active_constraints", "unresolved",
        }:
            raise ArkUIPageError("Android page JSON source layout relationship is malformed")
        try:
            relationship_id = require_token(raw.get("id"), "Android page layout relationship id")
            container_id = require_token(raw.get("container_id"), "Android page layout container id")
            subject_id = require_token(raw.get("subject_id"), "Android page layout subject id")
            subject_reference = require_token(
                raw.get("subject_reference"), "Android page layout subject reference"
            )
        except PageSnapshotError as error:
            raise ArkUIPageError(str(error)) from error
        if relationship_id in relationship_ids:
            raise ArkUIPageError("Android page JSON source layout relationship repeats an id")
        relationship_ids.add(relationship_id)
        if (
            raw.get("container_type") != "ConstraintLayout"
            or container_id not in by_id
            or by_id[container_id]["type"] != "ConstraintLayout"
            or subject_id not in by_id
            or by_id[subject_id]["parent_id"] != container_id
            or raw.get("composition") not in {"constraint", "overlay"}
            or type(raw.get("draw_order")) is not int
            or raw["draw_order"] != by_id[subject_id]["sibling_index"]
            or not isinstance(raw.get("source_expression"), str)
            or raw.get("branch_resolution") not in {
                "missing_constraint_body", "not_conditional", "resolved_condition",
                "unresolved_condition",
            }
            or not isinstance(raw.get("active_constraints"), list)
            or not isinstance(raw.get("unresolved"), list)
        ):
            raise ArkUIPageError("Android page JSON source layout relationship is inconsistent")
        constraints: list[dict[str, Any]] = []
        for constraint in raw["active_constraints"]:
            if not isinstance(constraint, dict) or set(constraint) != {
                "kind", "subject_anchor", "target_id", "target_reference", "target_anchor",
                "margin_expression", "margin_dp",
            }:
                raise ArkUIPageError("Android page JSON source layout constraint is malformed")
            if (
                constraint.get("kind") not in {"link_to", "center_around"}
                or constraint.get("subject_anchor") not in {
                    "start", "end", "top", "bottom", "baseline", "center"
                }
                or constraint.get("target_anchor") not in {
                    "start", "end", "top", "bottom", "baseline"
                }
                or constraint.get("target_id") not in by_id
                or not isinstance(constraint.get("target_reference"), str)
                or constraint.get("margin_expression") is not None
                and not isinstance(constraint.get("margin_expression"), str)
                or constraint.get("margin_dp") is not None
                and not isinstance(constraint.get("margin_dp"), (int, float))
            ):
                raise ArkUIPageError("Android page JSON source layout constraint is inconsistent")
            constraints.append(copy.deepcopy(constraint))
        unresolved = raw["unresolved"]
        if any(
            not isinstance(item, dict)
            or set(item) != {"expression", "reason"}
            or not isinstance(item.get("expression"), str)
            or not isinstance(item.get("reason"), str)
            for item in unresolved
        ):
            raise ArkUIPageError("Android page JSON source layout unresolved record is malformed")
        relationship = copy.deepcopy(raw)
        relationship["active_constraints"] = constraints
        layout_relationships.append(relationship)
    return {
        "schema": value["schema"],
        "definitions": definitions,
        "by_definition_id": {item["id"]: item for item in definitions},
        "root_ids": root_ids,
        "business_root_ids": business_root_ids,
        "business_component_ids": business_component_ids,
        "third_party_component_ids": third_party_component_ids,
        "layout_relationships": layout_relationships,
        "components": components,
        "by_id": by_id,
    }
