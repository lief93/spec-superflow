from __future__ import annotations
import copy
import json
import math
import os
import re
from component_required_facts import normalize_required_facts
from page_snapshot import PageSnapshotError, normalize_provenance, normalize_style, normalize_unresolved, require_token
from pathlib import Path
from typing import Any
from ui_migration.common import ArkUIPageError, LANHU_VERSION_KEYS, PAGE_INPUT_MAX_BYTES, RESOURCE_NAME_PATTERN


def load_bounded_json_object(path: Path, label: str) -> tuple[dict[str, Any], Path, int]:
    requested = Path(os.path.abspath(os.path.expanduser(str(path))))
    if requested.is_symlink() or not requested.is_file():
        raise ArkUIPageError(f"{label} must be an existing non-symbolic-link file")
    byte_count = requested.stat().st_size
    if byte_count <= 0 or byte_count > PAGE_INPUT_MAX_BYTES:
        raise ArkUIPageError(f"{label} must contain 1 byte to 10 MiB")
    try:
        payload = json.loads(requested.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ArkUIPageError(f"{label} is invalid: {error}") from error
    if not isinstance(payload, dict):
        raise ArkUIPageError(f"{label} must contain a JSON object")
    return payload, requested, byte_count


def require_lanhu_number(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ArkUIPageError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or (positive and number <= 0):
        qualifier = "positive" if positive else "finite"
        raise ArkUIPageError(f"{label} must be {qualifier}")
    return number


def require_lanhu_frame(
    value: Any,
    label: str,
    *,
    positive_dimensions: bool = False,
) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ArkUIPageError(f"{label} has no frame")
    frame = {
        field: require_lanhu_number(value.get(field), f"{label}.{field}")
        for field in ("left", "top", "width", "height")
    }
    if frame["width"] < 0 or frame["height"] < 0:
        raise ArkUIPageError(f"{label} frame dimensions must not be negative")
    if positive_dimensions and (frame["width"] <= 0 or frame["height"] <= 0):
        raise ArkUIPageError(f"{label} frame dimensions must be positive")
    return frame


def lanhu_color(value: Any) -> str | None:
    if isinstance(value, str) and re.fullmatch(r"#[0-9A-Fa-f]{8}", value):
        return value.upper()
    if not isinstance(value, dict):
        return None
    channels = [value.get(name) for name in ("a", "r", "g", "b")]
    if any(isinstance(channel, bool) or not isinstance(channel, (int, float)) for channel in channels):
        return None
    normalized = [float(channel) for channel in channels]
    if any(not math.isfinite(channel) or channel < 0 or channel > 1 for channel in normalized):
        return None
    return "#" + "".join(f"{round(channel * 255):02X}" for channel in normalized)


def validate_lanhu_style(value: Any, label: str) -> None:
    required = {
        "isEnabled", "opacity", "blendMode", "fills", "borders", "shadows", "blurs"
    }
    if not isinstance(value, dict) or not required.issubset(value):
        missing = sorted(required - set(value) if isinstance(value, dict) else required)
        raise ArkUIPageError(f"{label} is missing required fields: {missing}")
    if type(value["isEnabled"]) is not bool:
        raise ArkUIPageError(f"{label}.isEnabled must be a boolean")
    opacity = require_lanhu_number(value["opacity"], f"{label}.opacity")
    if not 0 <= opacity <= 1:
        raise ArkUIPageError(f"{label}.opacity must be between 0 and 1")
    if type(value["blendMode"]) is not int:
        raise ArkUIPageError(f"{label}.blendMode must be an integer")
    for field in ("fills", "borders", "shadows", "blurs"):
        if not isinstance(value[field], list):
            raise ArkUIPageError(f"{label}.{field} must be a list")


def validate_lanhu_layout_rules(value: Any, label: str) -> None:
    if not isinstance(value, list) or len(value) > 1000:
        raise ArkUIPageError(f"{label} must be a bounded list")
    for index, rule in enumerate(value):
        rule_label = f"{label}[{index}]"
        if not isinstance(rule, dict):
            raise ArkUIPageError(f"{rule_label} must be an object")
        modifier_index = rule.get("source_modifier_index")
        if type(modifier_index) is not int or modifier_index < 0:
            raise ArkUIPageError(
                f"{rule_label}.source_modifier_index must be a non-negative integer"
            )
        kind = rule.get("kind")
        if kind == "sizing":
            axes = rule.get("axes")
            mode = rule.get("mode")
            if (
                not isinstance(axes, list)
                or not axes
                or len(axes) != len(set(axes))
                or any(axis not in {"width", "height"} for axis in axes)
                or mode not in {"fill_parent", "match_parent", "wrap_content"}
            ):
                raise ArkUIPageError(f"{rule_label} sizing rule is malformed")
            if mode in {"fill_parent", "match_parent"}:
                fraction = require_lanhu_number(
                    rule.get("fraction"), f"{rule_label}.fraction"
                )
                if not 0 <= fraction <= 1:
                    raise ArkUIPageError(
                        f"{rule_label}.fraction must be greater than zero and at most one"
                    )
        elif kind == "intrinsic_size":
            if rule.get("axis") not in {"width", "height"} or rule.get("mode") not in {
                "min", "max"
            }:
                raise ArkUIPageError(f"{rule_label} intrinsic-size rule is malformed")
        elif kind == "constraints":
            limits = rule.get("limits")
            if not isinstance(limits, dict) or not limits or set(limits) - {"minWidth", "maxWidth", "minHeight", "maxHeight"}:
                raise ArkUIPageError(f"{rule_label} constraints are malformed")
            for key, value in limits.items():
                if require_lanhu_number(value, f"{rule_label}.{key}") < 0:
                    raise ArkUIPageError(f"{rule_label}.{key} must be non-negative")
            for axis in ("Width", "Height"):
                if limits.get("min" + axis, 0) > limits.get("max" + axis, float("inf")):
                    raise ArkUIPageError(f"{rule_label} minimum exceeds maximum")
        elif kind == "scroll":
            if rule.get("axis") not in {"vertical", "horizontal"} or type(rule.get("enabled")) is not bool:
                raise ArkUIPageError(f"{rule_label} scroll rule is malformed")
        elif kind == "weight":
            value_number = require_lanhu_number(
                rule.get("value"), f"{rule_label}.value"
            )
            if value_number <= 0 or type(rule.get("fill")) is not bool:
                raise ArkUIPageError(f"{rule_label} weight rule is malformed")
        elif kind == "offset":
            if "x" not in rule and "y" not in rule:
                raise ArkUIPageError(f"{rule_label} offset rule has no axis")
            for axis in ("x", "y"):
                if axis not in rule:
                    continue
                offset = rule[axis]
                if not isinstance(offset, dict):
                    raise ArkUIPageError(f"{rule_label}.{axis} is malformed")
                offset_kind = offset.get("kind")
                if offset_kind == "dp":
                    require_lanhu_number(offset.get("value"), f"{rule_label}.{axis}.value")
                elif offset_kind == "parent_fraction":
                    if offset.get("axis") not in {"width", "height"}:
                        raise ArkUIPageError(f"{rule_label}.{axis}.axis is malformed")
                    require_lanhu_number(
                        offset.get("fraction"), f"{rule_label}.{axis}.fraction"
                    )
                else:
                    raise ArkUIPageError(f"{rule_label}.{axis}.kind is unsupported")
        elif kind == "constraint_reference":
            try:
                require_token(rule.get("reference"), f"{rule_label}.reference")
            except PageSnapshotError as error:
                raise ArkUIPageError(str(error)) from error
        elif kind == "alignment":
            if not isinstance(rule.get("value"), str) or re.fullmatch(
                r"Alignment\.[A-Za-z]+", rule["value"]
            ) is None:
                raise ArkUIPageError(f"{rule_label} alignment rule is malformed")
        elif kind == "z_index":
            require_lanhu_number(rule.get("value"), f"{rule_label}.value")
        else:
            raise ArkUIPageError(f"{rule_label}.kind is unsupported")


def validate_lanhu_version_document(version: dict[str, Any]) -> None:
    if set(version) != LANHU_VERSION_KEYS:
        raise ArkUIPageError("Lanhu version_json must contain exactly meta/assets/artboard")
    meta = version.get("meta")
    if not isinstance(meta, dict):
        raise ArkUIPageError("Lanhu version_json meta is malformed")
    require_lanhu_number(
        meta.get("sliceScale"), "Lanhu version_json sliceScale", positive=True
    )
    if not isinstance(version.get("assets"), list):
        raise ArkUIPageError("Lanhu version_json assets must be a list")
    if not all(isinstance(asset, str) and asset for asset in version["assets"]):
        raise ArkUIPageError("Lanhu version_json assets must contain non-empty strings")
    artboard = version.get("artboard")
    artboard_required = {
        "id", "name", "type", "visible", "clipped", "opacity", "frame",
        "realFrame", "combinedFrame", "style", "layers",
    }
    if not isinstance(artboard, dict) or not artboard_required.issubset(artboard):
        missing = sorted(
            artboard_required - set(artboard) if isinstance(artboard, dict) else artboard_required
        )
        raise ArkUIPageError(f"Lanhu artboard is missing required fields: {missing}")
    for field in ("id", "name", "type"):
        try:
            require_token(artboard[field], f"Lanhu artboard {field}")
        except PageSnapshotError as error:
            raise ArkUIPageError(str(error)) from error
    if type(artboard["visible"]) is not bool or type(artboard["clipped"]) is not bool:
        raise ArkUIPageError("Lanhu artboard visible/clipped fields must be booleans")
    artboard_opacity = require_lanhu_number(artboard["opacity"], "Lanhu artboard opacity")
    if not 0 <= artboard_opacity <= 1:
        raise ArkUIPageError("Lanhu artboard opacity must be between 0 and 1")
    for field in ("frame", "realFrame", "combinedFrame"):
        require_lanhu_frame(
            artboard[field], f"Lanhu artboard {field}", positive_dimensions=True
        )
    validate_lanhu_style(artboard["style"], "Lanhu artboard style")
    if not isinstance(artboard["layers"], list) or not artboard["layers"]:
        raise ArkUIPageError("Lanhu artboard layers must be a non-empty list")

    layer_required = {
        "id", "name", "type", "visible", "clipped", "isMask", "opacity", "rotation",
        "frame", "realFrame", "combinedFrame", "radius", "paths", "style",
        "hasExportImage", "hasExportDDSImage", "layers",
    }

    def visit(layer: Any) -> None:
        if not isinstance(layer, dict) or not layer_required.issubset(layer):
            missing = sorted(
                layer_required - set(layer) if isinstance(layer, dict) else layer_required
            )
            raise ArkUIPageError(f"Lanhu layer is missing required fields: {missing}")
        layer_id = layer.get("id")
        for field in ("id", "name", "type"):
            try:
                require_token(layer[field], f"Lanhu layer {layer_id} {field}")
            except PageSnapshotError as error:
                raise ArkUIPageError(str(error)) from error
        for field in ("visible", "clipped", "isMask", "hasExportImage", "hasExportDDSImage"):
            if type(layer[field]) is not bool:
                raise ArkUIPageError(f"Lanhu layer {layer_id}.{field} must be a boolean")
        opacity = require_lanhu_number(layer["opacity"], f"Lanhu layer {layer_id}.opacity")
        if not 0 <= opacity <= 1:
            raise ArkUIPageError(f"Lanhu layer {layer_id}.opacity must be between 0 and 1")
        require_lanhu_number(layer["rotation"], f"Lanhu layer {layer_id}.rotation")
        for field in ("frame", "realFrame", "combinedFrame"):
            require_lanhu_frame(layer[field], f"Lanhu layer {layer_id}.{field}")
        radius = layer["radius"]
        radius_fields = {"topLeft", "topRight", "bottomRight", "bottomLeft"}
        if not isinstance(radius, dict) or set(radius) != radius_fields:
            raise ArkUIPageError(f"Lanhu layer {layer_id}.radius is malformed")
        for field in radius_fields:
            number = require_lanhu_number(radius[field], f"Lanhu layer {layer_id}.radius.{field}")
            if number < 0:
                raise ArkUIPageError(f"Lanhu layer {layer_id}.radius.{field} must not be negative")
        if not isinstance(layer["paths"], list) or not isinstance(layer["layers"], list):
            raise ArkUIPageError(f"Lanhu layer {layer_id} paths/layers must be lists")
        validate_lanhu_style(layer["style"], f"Lanhu layer {layer_id}.style")
        migration = layer.get("migration")
        from ui_migration.contracts.style_tokens import has_token_reference, validate_token_reference
        if layer["type"] == "text" and not isinstance(layer.get("text"), str):
            unresolved_text = (
                isinstance(meta.get("sourceGeneration"), dict)
                and "text" in layer and layer["text"] is None
                and isinstance(migration, dict)
                and isinstance(migration.get("unresolved"), list)
                and any(isinstance(item, dict) and item.get("path") == "style.content.text"
                        for item in migration["unresolved"])
            )
            reference_text = isinstance(migration, dict) and has_token_reference(migration, 'content.text')
            if not unresolved_text and not reference_text:
                raise ArkUIPageError(f"Lanhu text layer {layer_id} must contain text or an explicit unresolved fact")
        if layer["hasExportImage"] and (
            not isinstance(layer.get("exportImageUrl"), str)
            or not layer["exportImageUrl"]
        ):
            raise ArkUIPageError(
                f"Lanhu export-image layer {layer_id} must contain exportImageUrl"
            )
        migration = layer.get("migration")
        if migration is not None:
            migration_required = {
                "schema", "componentType", "semanticKey", "source", "style",
                "customDraw", "provenance", "unresolved", "geometryStatus",
                "geometryEvidence",
            }
            migration_allowed = migration_required | {"requiredFacts", "phaseTrace", "definitionId", "componentKind", "invocationBindings"}
            if isinstance(migration, dict) and 'invocationBindings' in migration:
                bindings = migration['invocationBindings']
                if not isinstance(bindings, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in bindings.items()):
                    raise ArkUIPageError(f'Lanhu layer {layer_id} invocationBindings is malformed')
            source_generated = isinstance(meta.get("sourceGeneration"), dict)
            if (
                not isinstance(migration, dict)
                or not migration_required.issubset(migration)
                or not set(migration).issubset(migration_allowed)
                or source_generated and "requiredFacts" not in migration
            ):
                raise ArkUIPageError(f"Lanhu layer {layer_id}.migration is malformed")
            if migration.get("schema") != "android-to-harmony.lanhu-node.v1":
                raise ArkUIPageError(f"Lanhu layer {layer_id}.migration schema is unsupported")
            try:
                reuse = (migration.get('source') or {}).get('component_reuse')
                if reuse is not None:
                    from ui_migration.contracts.component_reuse import validate_reuse
                    validate_reuse(reuse)
                    if reuse['definition_id'] != migration.get('definitionId'):
                        raise ValueError('component reuse definition identity mismatch')
                references = (migration.get('source') or {}).get('style_token_references', {})
                if not isinstance(references, dict):
                    raise ValueError('style_token_references must be an object')
                for path, reference in references.items():
                    validate_token_reference(reference, path)
                require_token(
                    migration.get("componentType"),
                    f"Lanhu layer {layer_id}.migration componentType",
                )
                require_token(
                    migration.get("semanticKey"),
                    f"Lanhu layer {layer_id}.migration semanticKey",
                )
                normalize_style(
                    migration.get("style"),
                    f"Lanhu layer {layer_id}.migration.style",
                )
                normalize_provenance(
                    migration.get("provenance"),
                    f"Lanhu layer {layer_id}.migration.provenance",
                )
                normalize_unresolved(
                    migration.get("unresolved"),
                    f"Lanhu layer {layer_id}.migration.unresolved",
                )
                if "requiredFacts" in migration:
                    normalize_required_facts(
                        migration.get("requiredFacts"),
                        f"Lanhu layer {layer_id}.migration.requiredFacts",
                    )
            except PageSnapshotError as error:
                raise ArkUIPageError(str(error)) from error
            except ValueError as error:
                raise ArkUIPageError(str(error)) from error
            source = migration.get("source")
            if not isinstance(source, dict) or not isinstance(source.get("attributes"), list):
                raise ArkUIPageError(f"Lanhu layer {layer_id}.migration.source is malformed")
            if 'slot_invocation' in source:
                slot = source['slot_invocation']
                if (not isinstance(slot, dict) or not set(slot).issubset({'name', 'arguments', 'parameters', 'expression'})
                        or ('expression' in slot and not isinstance(slot['expression'], str))
                        or slot.get('name') != migration['componentType']
                        or any(not isinstance(slot.get(key, []), list)
                               or not all(isinstance(value, str) for value in slot.get(key, []))
                               for key in ('arguments', 'parameters'))):
                    raise ArkUIPageError(f"Lanhu layer {layer_id}.migration.source.slot_invocation is malformed")
            if "layoutRules" in source:
                validate_lanhu_layout_rules(
                    source["layoutRules"],
                    f"Lanhu layer {layer_id}.migration.source.layoutRules",
                )
            if migration.get("geometryStatus") not in {
                "source_resolved", "source_inferred", "unresolved"
            }:
                raise ArkUIPageError(
                    f"Lanhu layer {layer_id}.migration.geometryStatus is unsupported"
                )
            geometry_evidence = migration.get("geometryEvidence")
            if not isinstance(geometry_evidence, list) or not all(
                isinstance(item, str) for item in geometry_evidence
            ):
                raise ArkUIPageError(
                    f"Lanhu layer {layer_id}.migration.geometryEvidence is malformed"
                )
            phase_trace = migration.get("phaseTrace")
            if phase_trace is not None:
                phase_names = ("measure", "layout", "draw")
                if (
                    not isinstance(phase_trace, dict)
                    or set(phase_trace) != {"schema", "phaseOrder", *phase_names}
                    or phase_trace.get("schema")
                    != "android-to-harmony.render-phase-trace.v1"
                    or phase_trace.get("phaseOrder") != list(phase_names)
                ):
                    raise ArkUIPageError(
                        f"Lanhu layer {layer_id}.migration.phaseTrace is malformed"
                    )
                for phase_name in phase_names:
                    phase = phase_trace.get(phase_name)
                    if not isinstance(phase, dict) or phase.get("status") not in {
                        "consumed", "missing"
                    }:
                        raise ArkUIPageError(
                            f"Lanhu layer {layer_id}.migration.phaseTrace.{phase_name} is malformed"
                        )
        for child in layer["layers"]:
            visit(child)

    for root_layer in artboard["layers"]:
        visit(root_layer)
    source_generation = meta.get("sourceGeneration")
    if isinstance(source_generation, dict) and not isinstance(
        source_generation.get("layoutRelationships"), list
    ):
        raise ArkUIPageError(
            "source-generated Lanhu version_json requires meta.sourceGeneration.layoutRelationships"
        )


def normalize_lanhu_layout_relationships(
    value: Any,
    by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 10000:
        raise ArkUIPageError("Lanhu source layout relationships are malformed")
    relationships: list[dict[str, Any]] = []
    relationship_ids: set[str] = set()
    expected_fields = {
        "id", "container_id", "container_type", "subject_id", "subject_reference",
        "composition", "draw_order", "source_expression", "branch_resolution",
        "active_constraints", "unresolved",
    }
    constraint_fields = {
        "kind", "subject_anchor", "target_id", "target_reference", "target_anchor",
        "margin_expression", "margin_dp",
    }
    for raw in value:
        if not isinstance(raw, dict) or set(raw) != expected_fields:
            raise ArkUIPageError("Lanhu source layout relationship is malformed")
        relationship_id = str(raw.get("id") or "")
        container_id = str(raw.get("container_id") or "")
        subject_id = str(raw.get("subject_id") or "")
        if not relationship_id or relationship_id in relationship_ids:
            raise ArkUIPageError("Lanhu source layout relationship id is invalid")
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
            or not isinstance(raw.get("subject_reference"), str)
            or not raw["subject_reference"]
            or not isinstance(raw.get("source_expression"), str)
            or raw.get("branch_resolution") not in {
                "missing_constraint_body", "not_conditional", "resolved_condition",
                "unresolved_condition",
            }
            or not isinstance(raw.get("active_constraints"), list)
            or not isinstance(raw.get("unresolved"), list)
        ):
            raise ArkUIPageError("Lanhu source layout relationship is inconsistent")
        constraints: list[dict[str, Any]] = []
        for raw_constraint in raw["active_constraints"]:
            if not isinstance(raw_constraint, dict) or set(raw_constraint) != constraint_fields:
                raise ArkUIPageError("Lanhu source layout constraint is malformed")
            target_id = raw_constraint.get("target_id")
            if (
                raw_constraint.get("kind") not in {"link_to", "center_around"}
                or raw_constraint.get("subject_anchor") not in {
                    "start", "end", "top", "bottom", "baseline", "center"
                }
                or raw_constraint.get("target_anchor") not in {
                    "start", "end", "top", "bottom", "baseline"
                }
                or target_id not in by_id
                or not isinstance(raw_constraint.get("target_reference"), str)
                or raw_constraint.get("margin_expression") is not None
                and not isinstance(raw_constraint.get("margin_expression"), str)
                or raw_constraint.get("margin_dp") is not None
                and not isinstance(raw_constraint.get("margin_dp"), (int, float))
            ):
                raise ArkUIPageError("Lanhu source layout constraint is inconsistent")
            constraints.append(copy.deepcopy(raw_constraint))
        if any(
            not isinstance(item, dict)
            or set(item) != {"expression", "reason"}
            or not isinstance(item.get("expression"), str)
            or not isinstance(item.get("reason"), str)
            for item in raw["unresolved"]
        ):
            raise ArkUIPageError("Lanhu source layout unresolved record is malformed")
        relationship = copy.deepcopy(raw)
        relationship["active_constraints"] = constraints
        relationships.append(relationship)
    return relationships


def apply_lanhu_visual_style(
    style: dict[str, dict[str, Any]],
    layer: dict[str, Any],
    scale: float,
) -> list[str]:
    applied: list[str] = []

    def assign(section: str, field: str, value: Any) -> None:
        style[section][field] = value
        applied.append(f"style.{section}.{field}")

    if type(layer.get("visible")) is bool:
        assign("state", "visible", layer["visible"])
    layer_style = layer.get("style")
    if not isinstance(layer_style, dict):
        layer_style = {}
    # Lanhu isEnabled enables a paint style, not Android interaction state.
    opacity = layer.get("opacity", layer_style.get("opacity"))
    if isinstance(opacity, (int, float)) and not isinstance(opacity, bool):
        number = float(opacity)
        if math.isfinite(number) and 0 <= number <= 1:
            assign("surface", "alpha", number)
    if type(layer.get("clipped")) is bool:
        assign("surface", "clip", layer["clipped"])
    rotation = layer.get("rotation")
    if isinstance(rotation, (int, float)) and not isinstance(rotation, bool):
        number = float(rotation)
        if math.isfinite(number):
            assign("transform", "rotation_degrees", number)
    if isinstance(layer.get("text"), str):
        assign("content", "text", layer["text"])
    font_size = layer_style.get("fontSize")
    if isinstance(font_size, (int, float)) and not isinstance(font_size, bool):
        number = float(font_size) / scale
        if math.isfinite(number) and number >= 0:
            assign("typography", "font_size_sp", number)
    font_weight = layer_style.get("fontWeight")
    if type(font_weight) is int and 1 <= font_weight <= 1000:
        assign("typography", "font_weight", font_weight)
    font_color = layer_style.get("color")
    if isinstance(font_color, str) and re.fullmatch(r"#[0-9A-Fa-f]{8}", font_color):
        assign("typography", "color", font_color.upper())
    radius = layer.get("radius")
    radius_fields = {
        "top_left": "topLeft",
        "top_right": "topRight",
        "bottom_right": "bottomRight",
        "bottom_left": "bottomLeft",
    }
    if isinstance(radius, dict) and all(
        isinstance(radius.get(source), (int, float)) and not isinstance(radius.get(source), bool)
        for source in radius_fields.values()
    ):
        assign(
            "surface",
            "corner_radius_dp",
            {
                target: float(radius[source]) / scale
                for target, source in radius_fields.items()
            },
        )
    fills = layer_style.get("fills")
    if isinstance(fills, list):
        fill = next(
            (
                item
                for item in fills
                if isinstance(item, dict)
                and item.get("type") == "color"
                and item.get("isEnabled", True) is not False
            ),
            None,
        )
        color = lanhu_color(fill.get("color")) if isinstance(fill, dict) else None
        if color is not None:
            assign("surface", "background", {"type": "solid", "color": color})
    resource = layer.get("exportImageUrl")
    if isinstance(resource, str) and RESOURCE_NAME_PATTERN.fullmatch(resource):
        assign("asset", "resource", resource)
    return applied
