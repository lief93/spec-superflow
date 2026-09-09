from __future__ import annotations
import re
from collections import defaultdict
from component_required_facts import normalized_layout_rules
from typing import Any
from ui_migration.frontend.page_model import HORIZONTAL_TYPES, IMAGE_TYPES, OVERLAY_TYPES, TEXT_TYPES, VERTICAL_TYPES, arrangement_spacing, edge_values, finite_number, has_modifier, modifier_argument, offset_values, parse_padding_expression, resolved_alignment, semantic_expression, style_group, uses_parent_width
from ui_migration.frontend.source_tree import SourceTree


class SourceLayout:
    def __init__(self, tree: SourceTree, viewport_width: float, viewport_height: float) -> None:
        self.tree = tree
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.frames: dict[str, dict[str, float]] = {}
        self.measured_sizes: dict[str, dict[str, float]] = {}
        self.geometry_status: dict[str, str] = {}
        self.geometry_reasons: dict[str, list[str]] = defaultdict(list)
        self.consumed_relationship_ids: set[str] = set()
        self.phase_failures: list[dict[str, str]] = []
        self.drawn_component_ids: set[str] = set()
        self.draw_output_paths: dict[str, list[str]] = {}
        self.measure_complete = False
        self.layout_complete = False
        self._measure_cache: dict[tuple[str, float], tuple[float, float]] = {}
        self.dimension_tokens: dict[str, float] = {}
        for token in tree.payload.get("source_tokens") or []:
            if not isinstance(token, dict) or not isinstance(token.get("name"), str):
                continue
            for dimension in token.get("dimensions") or []:
                if not isinstance(dimension, dict) or dimension.get("unit") != "dp":
                    continue
                raw = dimension.get("value")
                try:
                    resolved = finite_number(float(raw))
                except (TypeError, ValueError):
                    resolved = None
                if resolved is not None:
                    self.dimension_tokens[token["name"]] = resolved
                    break
        self.relationships_by_container: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for relationship in tree.payload.get("layout_relationships") or []:
            if isinstance(relationship, dict) and isinstance(
                relationship.get("container_id"), str
            ):
                self.relationships_by_container[relationship["container_id"]].append(
                    relationship
                )

    def calculate(self) -> dict[str, dict[str, float]]:
        # Keep the same phase boundary as Android/Compose: measure the complete
        # source tree first, then place it. Drawing is performed by lanhu_layer.
        self._measure(self.tree.root_id, self.viewport_width)
        self.measure_complete = len(self.measured_sizes) == len(self.tree.nodes)
        self._layout(
            self.tree.root_id,
            0.0,
            0.0,
            self.viewport_width,
            self.viewport_height,
            force_size=(self.viewport_width, self.viewport_height),
        )
        self.layout_complete = len(self.frames) == len(self.tree.nodes)
        return self.frames

    def _explicit_size(self, node: dict[str, Any]) -> tuple[float | None, float | None]:
        layout = style_group(node, "layout")
        width = finite_number(layout.get("width_dp"))
        height = finite_number(layout.get("height_dp"))
        for modifier in node.get("modifiers") or []:
            if not isinstance(modifier, dict) or modifier.get("name") not in {
                "width", "requiredWidth", "height", "requiredHeight"
            }:
                continue
            argument = str(modifier.get("arguments") or "").strip()
            resolved = self.dimension_tokens.get(argument)
            if resolved is None:
                match = re.fullmatch(r"(-?\d+(?:\.\d+)?)\.dp", argument)
                resolved = float(match.group(1)) if match else None
            if modifier["name"] in {"width", "requiredWidth"} and width is None:
                width = resolved
            elif modifier["name"] in {"height", "requiredHeight"} and height is None:
                height = resolved
        return width, height

    def _intrinsic_image_size(self, node: dict[str, Any], width: float, height: float | None = None) -> tuple[float, float] | None:
        if node.get("type") not in IMAGE_TYPES:
            return None
        asset = style_group(node, "asset")
        intrinsic_width = finite_number(asset.get("width_dp"))
        intrinsic_height = finite_number(asset.get("height_dp"))
        if not intrinsic_width or not intrinsic_height:
            return None
        scale = min(1.0, width / intrinsic_width, height / intrinsic_height if height is not None else 1.0)
        if asset.get("content_scale") not in {None, "fit", "inside"}:
            return min(width, intrinsic_width), min(height, intrinsic_height) if height is not None else intrinsic_height
        return intrinsic_width * scale, intrinsic_height * scale

    def effective_padding(self, node: dict[str, Any]) -> dict[str, float]:
        raw = style_group(node, "layout").get("padding_dp")
        if isinstance(raw, dict):
            children = self.tree.children.get(node["id"], [])
            if (
                len(children) == 1
                and str(node.get("component_kind") or "").startswith("project")
                and "modifier"
                in " ".join(
                    str(modifier.get("arguments") or "")
                    for modifier in self.tree.nodes[children[0]].get("modifiers") or []
                    if isinstance(modifier, dict)
                )
            ):
                self.geometry_reasons[node["id"]].append(
                    "invocation padding is applied by the project component internal root"
                )
                return edge_values(None)
            return edge_values(raw)
        parent_id = node.get("parent_id")
        if not isinstance(parent_id, str):
            return edge_values(None)
        parent = self.tree.nodes[parent_id]
        modifier_text = " ".join(
            str(modifier.get("arguments") or "")
            for modifier in node.get("modifiers") or []
            if isinstance(modifier, dict)
        )
        for invocation in (parent.get("arguments") or {}).get("invocation") or []:
            if not isinstance(invocation, dict):
                continue
            name = invocation.get("name")
            expression = invocation.get("expression")
            if (
                isinstance(name, str)
                and isinstance(expression, str)
                and name in modifier_text
            ):
                parsed = parse_padding_expression(expression)
                if parsed is not None:
                    self.geometry_reasons[node["id"]].append(
                        f"padding propagated from parent parameter {name}"
                    )
                    return parsed
        return edge_values(None)

    def _measure(self, component_id: str, available_width: float) -> tuple[float, float]:
        cache_key = (component_id, round(max(0.0, available_width), 4))
        if cache_key in self._measure_cache:
            return self._measure_cache[cache_key]
        node = self.tree.nodes[component_id]
        component_type = str(node.get("type") or "Group")
        children = self.tree.children.get(component_id, [])
        layout = style_group(node, "layout")
        padding = self.effective_padding(node)
        explicit_width, explicit_height = self._explicit_size(node)
        fill_width = uses_parent_width(node)
        if component_type in {"TopAppBar", "CenterAlignedTopAppBar", "BottomAppBar"}:
            fill_width = True
        width = explicit_width if explicit_width is not None else (available_width if fill_width else None)
        for rule in normalized_layout_rules(node):
            if rule.get("kind") == "sizing" and "width" in rule.get("axes", []) and rule.get("mode") == "fill_parent":
                width = available_width * rule["fraction"]
        inner_width = max(
            0.0,
            (width if width is not None else available_width) - padding["left"] - padding["right"],
        )

        child_sizes = [(child_id, self._measure(child_id, inner_width)) for child_id in children]
        if component_type == "ConstraintLayout":
            content_width, content_height = self._measure_constraint(
                component_id, child_sizes, inner_width
            )
        elif component_type in VERTICAL_TYPES:
            spacing = arrangement_spacing(node, "vertical")
            content_width = max((size[0] for _, size in child_sizes), default=0.0)
            content_height = sum(size[1] for _, size in child_sizes)
            content_height += spacing * max(0, len(child_sizes) - 1)
        elif component_type in HORIZONTAL_TYPES:
            spacing = arrangement_spacing(node, "horizontal")
            if width is None and any(
                has_modifier(self.tree.nodes[child_id], "weight") for child_id in children
            ):
                width = available_width
            content_width = sum(size[0] for _, size in child_sizes)
            content_width += spacing * max(0, len(child_sizes) - 1)
            content_height = max((size[1] for _, size in child_sizes), default=0.0)
        elif children:
            content_width = max((size[0] for _, size in child_sizes), default=0.0)
            content_height = max((size[1] for _, size in child_sizes), default=0.0)
            if component_type not in OVERLAY_TYPES and len(children) > 1:
                self.geometry_reasons[component_id].append(
                    "custom multi-child component measured as overlay"
                )
        else:
            content_width, content_height = self._measure_leaf(node, inner_width)

        if component_type == "CenterAlignedTopAppBar" and explicit_height is None:
            content_height = max(content_height, 64.0)
            self.geometry_reasons[component_id].append("Material3 small top app bar content height 64dp, excluding modifier padding")
        if component_type == 'BottomAppBar' and explicit_height is None:
            content_height = max(content_height, 80.0)
        if component_type in {"IconButton", "IconToggleButton"}:
            if width is None:
                width = 48.0
            if explicit_height is None:
                content_height = max(content_height, 48.0)
            self.geometry_reasons[component_id].append("Material IconButton default 48dp touch target")
        elif component_type in {"Button", "TextButton"}:
            if width is None:
                width = content_width + 24.0
            if explicit_height is None:
                content_height = max(content_height, 48.0)
            self.geometry_reasons[component_id].append("Material button minimum touch target")
        if width is None:
            width = content_width + padding["left"] + padding["right"]
        if explicit_height is not None:
            height = explicit_height
        else:
            height = content_height + padding["top"] + padding["bottom"]
        ratio = finite_number(layout.get("aspect_ratio"))
        if ratio is not None and ratio > 0:
            if explicit_height is None:
                height = width / ratio
            elif explicit_width is None:
                width = height * ratio
        for rule in normalized_layout_rules(node):
            if rule.get("kind") == "constraints":
                limits = rule["limits"]
                width = max(limits.get("minWidth", 0), min(width, limits.get("maxWidth", float("inf"))))
                height = max(limits.get("minHeight", 0), min(height, limits.get("maxHeight", float("inf"))))
        width = max(0.0, min(width, max(0.0, available_width)))
        height = max(0.0, height)
        self._measure_cache[cache_key] = (width, height)
        self.measured_sizes[component_id] = {"width": width, "height": height}
        return width, height

    def _constraint_vertical_positions(
        self,
        container_id: str,
        child_sizes: dict[str, tuple[float, float]],
        parent_height: float | None,
    ) -> dict[str, float]:
        relationships = {
            relationship.get("subject_id"): relationship
            for relationship in self.relationships_by_container.get(container_id, [])
        }
        positions: dict[str, float] = {}
        pending = list(child_sizes)
        while pending:
            progress = False
            for child_id in list(pending):
                relationship = relationships.get(child_id)
                constraints = (relationship or {}).get("active_constraints") or []
                unsupported = [
                    constraint
                    for constraint in constraints
                    if not (
                        constraint.get("kind") == "link_to"
                        and constraint.get("subject_anchor") in {"top", "start", "end"}
                        and constraint.get("target_anchor") in {"top", "bottom", "start", "end"}
                    )
                    and not (
                        constraint.get("kind") == "center_around"
                        and constraint.get("subject_anchor") == "center"
                        and constraint.get("target_anchor") in {"top", "center", "bottom"}
                    )
                ]
                if unsupported:
                    for constraint in unsupported:
                        failure = {
                            "phase": "layout",
                            "component_id": child_id,
                            "relationship_id": str((relationship or {}).get("id") or ""),
                            "reason": (
                                "unsupported constraint "
                                f"{constraint.get('kind')}:{constraint.get('subject_anchor')}"
                                f"->{constraint.get('target_anchor')}"
                            ),
                        }
                        if failure not in self.phase_failures:
                            self.phase_failures.append(failure)
                    positions[child_id] = 0.0
                    pending.remove(child_id)
                    progress = True
                    continue
                top = next(
                    (
                        constraint
                        for constraint in constraints
                        if constraint.get("kind") == "link_to"
                        and constraint.get("subject_anchor") == "top"
                    ),
                    None,
                )
                center = next(
                    (
                        constraint
                        for constraint in constraints
                        if constraint.get("kind") == "center_around"
                        and constraint.get("subject_anchor") == "center"
                    ),
                    None,
                )
                dependency = center or top
                if (
                    isinstance(dependency, dict)
                    and dependency.get("target_reference") != "parent"
                    and str(dependency.get("target_id")) not in positions
                ):
                    continue
                if isinstance(center, dict):
                    if center.get("target_reference") == "parent":
                        if parent_height is None:
                            positions[child_id] = 0.0
                            self.geometry_reasons[container_id].append(
                                "parent-centered child extent requires the layout phase"
                            )
                        else:
                            target_position = 0.0
                            target_height = parent_height
                            target_anchor = center.get("target_anchor")
                            if target_anchor == "bottom":
                                target_position = target_height
                            elif target_anchor == "center":
                                target_position = target_height / 2
                            positions[child_id] = (
                                target_position
                                - child_sizes[child_id][1] / 2
                                + (finite_number(center.get("margin_dp")) or 0.0)
                            )
                    else:
                        target_id = str(center.get("target_id"))
                        target_position = positions[target_id]
                        target_height = child_sizes.get(target_id, (0.0, 0.0))[1]
                        target_anchor = center.get("target_anchor")
                        if target_anchor == "bottom":
                            target_position += target_height
                        elif target_anchor == "center":
                            target_position += target_height / 2
                        positions[child_id] = (
                            target_position
                            - child_sizes[child_id][1] / 2
                            + (finite_number(center.get("margin_dp")) or 0.0)
                        )
                elif isinstance(top, dict) and top.get("target_reference") != "parent":
                    target_id = str(top.get("target_id"))
                    target_position = positions[target_id]
                    if top.get("target_anchor") == "bottom":
                        target_position += child_sizes.get(target_id, (0.0, 0.0))[1]
                    positions[child_id] = target_position + (
                        finite_number(top.get("margin_dp")) or 0.0
                    )
                else:
                    positions[child_id] = (
                        finite_number(top.get("margin_dp")) or 0.0
                        if isinstance(top, dict)
                        else 0.0
                    )
                if isinstance(relationship, dict) and isinstance(relationship.get("id"), str):
                    self.consumed_relationship_ids.add(relationship["id"])
                pending.remove(child_id)
                progress = True
            if not progress:
                for child_id in pending:
                    positions[child_id] = 0.0
                    relationship = relationships.get(child_id) or {}
                    failure = {
                        "phase": "layout",
                        "component_id": child_id,
                        "relationship_id": str(relationship.get("id") or ""),
                        "reason": "constraint dependency could not be resolved",
                    }
                    if failure not in self.phase_failures:
                        self.phase_failures.append(failure)
                self.geometry_reasons[container_id].append(
                    "constraint extent contains unresolved dependency"
                )
                break
        return positions

    def _measure_constraint(
        self,
        container_id: str,
        child_sizes: list[tuple[str, tuple[float, float]]],
        available_width: float,
    ) -> tuple[float, float]:
        sizes = dict(child_sizes)
        relationships = {
            relationship.get("subject_id"): relationship
            for relationship in self.relationships_by_container.get(container_id, [])
        }
        positions = self._constraint_vertical_positions(container_id, sizes, None)
        content_height = max(
            (positions[child_id] + sizes[child_id][1] for child_id in sizes),
            default=0.0,
        )
        content_width = max((size[0] for size in sizes.values()), default=0.0)
        if any(
            {constraint.get("subject_anchor") for constraint in relationship.get("active_constraints") or []}
            >= {"start", "end"}
            for relationship in relationships.values()
        ):
            content_width = available_width
        return content_width, content_height

    def _measure_leaf(self, node: dict[str, Any], available_width: float) -> tuple[float, float]:
        component_type = str(node.get("type") or "")
        if component_type in TEXT_TYPES:
            typography = style_group(node, "typography")
            content = style_group(node, "content")
            font_size = finite_number(typography.get("font_size_sp")) or 14.0
            line_height = finite_number(typography.get("line_height_sp")) or font_size * 1.25
            text = content.get("text")
            text_length = len(text) if isinstance(text, str) and text else 1
            estimated_width = min(available_width, max(font_size * 0.55 * text_length, font_size))
            self.geometry_reasons[node["id"]].append("text width estimated from source typography")
            return estimated_width, line_height
        if component_type in IMAGE_TYPES:
            intrinsic = self._intrinsic_image_size(node, available_width)
            if intrinsic is not None:
                self.geometry_reasons[node["id"]].append("image intrinsic size constrained by available layout space")
                return intrinsic
            self.geometry_reasons[node["id"]].append("image has no resolved source dimensions")
            return 24.0, 24.0
        if component_type in {"HorizontalDivider", "Divider"}:
            return available_width, 1.0
        self.geometry_reasons[node["id"]].append("leaf has no source-resolved dimensions")
        return 0.0, 0.0

    def _layout(
        self,
        component_id: str,
        x: float,
        y: float,
        available_width: float,
        available_height: float | None,
        *,
        force_size: tuple[float, float] | None = None,
    ) -> tuple[float, float]:
        node = self.tree.nodes[component_id]
        component_type = str(node.get("type") or "Group")
        width, height = force_size or self._measure(component_id, available_width)
        offset_x, offset_y = offset_values(node, available_width, available_height)
        x += offset_x
        y += offset_y
        self.frames[component_id] = {"x": x, "y": y, "width": width, "height": height}
        explicit_width, explicit_height = self._explicit_size(node)
        reasons = self.geometry_reasons.get(component_id, [])
        if component_id == self.tree.root_id or (explicit_width is not None and explicit_height is not None):
            status = "source_resolved"
        elif any("no source-resolved" in reason for reason in reasons):
            status = "unresolved"
        else:
            status = "source_inferred"
        self.geometry_status[component_id] = status

        children = self.tree.children.get(component_id, [])
        if not children:
            return width, height
        padding = self.effective_padding(node)
        content_x = x + padding["left"]
        content_y = y + padding["top"]
        content_width = max(0.0, width - padding["left"] - padding["right"])
        content_height = max(0.0, height - padding["top"] - padding["bottom"])
        if component_type in VERTICAL_TYPES:
            self._layout_vertical(node, children, content_x, content_y, content_width, content_height)
        elif component_type in HORIZONTAL_TYPES:
            self._layout_horizontal(node, children, content_x, content_y, content_width, content_height)
        elif component_type == "TopAppBar":
            self._layout_top_app_bar(children, content_x, content_y, content_width, content_height)
        elif component_type in {"IconButton", "Button", "TextButton"}:
            self._layout_center(children, content_x, content_y, content_width, content_height)
        elif component_type == "ConstraintLayout":
            self._layout_constraint(component_id, children, content_x, content_y, content_width, content_height)
        else:
            self._layout_overlay(
                children,
                content_x,
                content_y,
                content_width,
                content_height,
                container_node=node,
            )
        return width, height

    def _layout_vertical(
        self,
        node: dict[str, Any],
        children: list[str],
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        spacing = arrangement_spacing(node, "vertical")
        cursor = y
        weighted = [child for child in children if has_modifier(self.tree.nodes[child], "weight")]
        measured = {child: self._measure(child, width) for child in children}
        occupied = sum(size[1] for child, size in measured.items() if child not in weighted)
        occupied += spacing * max(0, len(children) - 1)
        weights = {child: next(rule for rule in normalized_layout_rules(self.tree.nodes[child]) if rule["kind"] == "weight") for child in weighted}
        total_weight = sum(rule["value"] for rule in weights.values())
        weight_height = max(0.0, height - occupied) / total_weight if total_weight else None
        container_alignment = (
            semantic_expression(node, "horizontalAlignment")
            or resolved_alignment(node)
        )
        for child in children:
            child_node = self.tree.nodes[child]
            child_width, child_height = measured[child]
            if has_modifier(child_node, "fillMaxWidth") or has_modifier(child_node, "fillMaxSize"):
                rule = next((rule for rule in normalized_layout_rules(child_node) if rule["kind"] == "sizing" and "width" in rule.get("axes", [])), {})
                child_width = width * rule.get("fraction", 1)
            if child in weighted and weight_height is not None:
                allocated = weight_height * weights[child]["value"]
                child_height = allocated if weights[child]["fill"] else min(child_height, allocated)
            alignment = self._alignment(child_node) or container_alignment
            child_x = self._aligned_x(
                child_node, x, width, child_width, alignment
            )
            self._layout(
                child,
                child_x,
                cursor,
                width,
                child_height,
                force_size=(child_width, child_height),
            )
            cursor += child_height + spacing

    def _layout_horizontal(
        self,
        node: dict[str, Any],
        children: list[str],
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        spacing = arrangement_spacing(node, "horizontal")
        measured = {child: self._measure(child, width) for child in children}
        weighted = [child for child in children if has_modifier(self.tree.nodes[child], "weight")]
        occupied = sum(size[0] for child, size in measured.items() if child not in weighted)
        occupied += spacing * max(0, len(children) - 1)
        weights = {child: next(rule for rule in normalized_layout_rules(self.tree.nodes[child]) if rule["kind"] == "weight") for child in weighted}
        total_weight = sum(rule["value"] for rule in weights.values())
        weight_width = max(0.0, width - occupied) / total_weight if total_weight else None
        arrangement = semantic_expression(node, "horizontalArrangement").lower()
        if not weighted and len(children) > 1 and "spacebetween" in arrangement:
            spacing = max(0.0, width - sum(size[0] for size in measured.values())) / (len(children) - 1)
        cursor = x
        vertical_alignment = (
            semantic_expression(node, "verticalAlignment")
            or resolved_alignment(node)
        ).lower()
        for child in children:
            child_node = self.tree.nodes[child]
            child_width, child_height = measured[child]
            if child in weighted and weight_width is not None:
                allocated = weight_width * weights[child]["value"]
                child_width = allocated if weights[child]["fill"] else min(child_width, allocated)
            if has_modifier(child_node, "fillMaxHeight") or has_modifier(child_node, "fillMaxSize"):
                rule = next((rule for rule in normalized_layout_rules(child_node) if rule["kind"] == "sizing" and "height" in rule.get("axes", [])), {})
                child_height = height * rule.get("fraction", 1)
            if "center" in vertical_alignment:
                child_y = y + max(0.0, (height - child_height) / 2)
            elif "bottom" in vertical_alignment:
                child_y = y + max(0.0, height - child_height)
            else:
                child_y = self._aligned_y(child_node, y, height, child_height)
            self._layout(
                child,
                cursor,
                child_y,
                child_width,
                height,
                force_size=(child_width, child_height),
            )
            cursor += child_width + spacing

    def _layout_top_app_bar(
        self,
        children: list[str],
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        if not children:
            return
        action_ids = [
            child_id
            for child_id in children
            if self.tree.nodes[child_id].get("type") in {"IconButton", "Button", "TextButton"}
        ]
        title_ids = [child_id for child_id in children if child_id not in action_ids]
        cursor = x + width - 4.0
        for child_id in reversed(action_ids):
            child_width, child_height = self._measure(child_id, width)
            cursor -= child_width
            child_y = y + max(0.0, (height - child_height) / 2)
            self._layout(
                child_id,
                cursor,
                child_y,
                child_width,
                height,
                force_size=(child_width, child_height),
            )
        for child_id in title_ids:
            child_width, child_height = self._measure(child_id, max(0.0, cursor - x - 16.0))
            child_y = y + max(0.0, (height - child_height) / 2)
            self._layout(
                child_id,
                x + 16.0,
                child_y,
                max(0.0, cursor - x - 16.0),
                height,
                force_size=(child_width, child_height),
            )

    def _layout_center(
        self,
        children: list[str],
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        for child_id in children:
            child_width, child_height = self._measure(child_id, width)
            self._layout(
                child_id,
                x + max(0.0, (width - child_width) / 2),
                y + max(0.0, (height - child_height) / 2),
                width,
                height,
                force_size=(child_width, child_height),
            )

    def _layout_overlay(
        self,
        children: list[str],
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        container_node: dict[str, Any] | None = None,
    ) -> None:
        explicit_width, explicit_height = (
            self._explicit_size(container_node) if container_node else (None, None)
        )
        forwards_modifier_width = bool(
            container_node
            and len(children) == 1
            and str(container_node.get("component_kind") or "").startswith("project")
            and (uses_parent_width(container_node) or explicit_width is not None)
        )
        container_alignment = resolved_alignment(container_node) if container_node else ""
        for child in children:
            child_node = self.tree.nodes[child]
            child_width, child_height = self._measure(child, width)
            if self._explicit_size(child_node) == (None, None):
                intrinsic = self._intrinsic_image_size(child_node, width, height)
                if intrinsic is not None:
                    child_width, child_height = intrinsic
            if (
                forwards_modifier_width
                or self._forwarded_modifier_fills_axis(container_node, child_node, "width")
                or has_modifier(child_node, "fillMaxWidth")
                or has_modifier(child_node, "fillMaxSize")
            ):
                rule = next((rule for rule in normalized_layout_rules(child_node) if rule["kind"] == "sizing" and "width" in rule.get("axes", [])), {})
                child_width = width * rule.get("fraction", 1)
            if (
                self._forwarded_modifier_fills_axis(container_node, child_node, "height")
                or has_modifier(child_node, "fillMaxHeight")
                or has_modifier(child_node, "fillMaxSize")
            ):
                rule = next((rule for rule in normalized_layout_rules(child_node) if rule["kind"] == "sizing" and "height" in rule.get("axes", [])), {})
                child_height = height * rule.get("fraction", 1)
            elif (
                container_node
                and len(children) == 1
                and str(container_node.get("component_kind") or "").startswith("project")
                and explicit_height is not None
            ):
                child_height = height
            alignment = self._alignment(child_node) or container_alignment
            child_x = self._aligned_x(child_node, x, width, child_width, alignment)
            child_y = self._aligned_y(child_node, y, height, child_height, alignment)
            self._layout(
                child,
                child_x,
                child_y,
                width,
                height,
                force_size=(child_width, child_height),
            )

    def _forwarded_modifier_fills_axis(
        self,
        container_node: dict[str, Any] | None,
        child_node: dict[str, Any],
        axis: str,
    ) -> bool:
        if (
            not isinstance(container_node, dict)
            or len(self.tree.children.get(container_node["id"], [])) != 1
            or not str(container_node.get("component_kind") or "").startswith("project")
        ):
            return False
        bindings = child_node.get("parameter_bindings")
        expression = bindings.get("modifier") if isinstance(bindings, dict) else None
        if not isinstance(expression, str):
            return False
        compact = re.sub(r"\s+", "", expression)
        if ".fillMaxSize(" in compact:
            return True
        if axis == "width" and ".fillMaxWidth(" in compact:
            return True
        if axis == "height" and ".fillMaxHeight(" in compact:
            return True
        if ".weight(" not in compact:
            return False
        ancestor_id = container_node.get("parent_id")
        while isinstance(ancestor_id, str):
            ancestor = self.tree.nodes[ancestor_id]
            ancestor_type = str(ancestor.get("type") or "")
            if ancestor_type in HORIZONTAL_TYPES:
                return axis == "width"
            if ancestor_type in VERTICAL_TYPES:
                return axis == "height"
            ancestor_id = ancestor.get("parent_id")
        return False

    def _layout_constraint(
        self,
        container_id: str,
        children: list[str],
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        relationships = {
            relationship.get("subject_id"): relationship
            for relationship in self.relationships_by_container.get(container_id, [])
        }
        measured = {child: self._measure(child, width) for child in children}
        anchors_by_child = {
            child: {
                constraint.get("subject_anchor"): constraint
                for constraint in (relationships.get(child) or {}).get("active_constraints") or []
                if constraint.get("kind") == "link_to"
            }
            for child in children
        }
        for child, anchors in anchors_by_child.items():
            start = anchors.get("start")
            end = anchors.get("end")
            child_width, child_height = measured[child]
            if (
                isinstance(start, dict)
                and isinstance(end, dict)
            ):
                start_margin = finite_number(start.get("margin_dp")) or 0.0
                end_margin = finite_number(end.get("margin_dp")) or 0.0
                measured[child] = (
                    max(0.0, width - start_margin - end_margin),
                    child_height,
                )
        positions = self._constraint_vertical_positions(container_id, measured, height)
        for child in children:
            child_width, child_height = measured[child]
            anchors = anchors_by_child[child]
            start = anchors.get("start")
            end = anchors.get("end")
            child_x = x
            if isinstance(start, dict) and start.get("target_reference") == "parent":
                child_x += finite_number(start.get("margin_dp")) or 0.0
            elif isinstance(start, dict) and isinstance(end, dict):
                child_x += finite_number(start.get("margin_dp")) or 0.0
            elif isinstance(end, dict) and end.get("target_reference") == "parent":
                child_x += width - child_width - (finite_number(end.get("margin_dp")) or 0.0)
            self._layout(
                child,
                child_x,
                y + positions[child],
                width,
                height,
                force_size=(child_width, child_height),
            )

    def _alignment(self, node: dict[str, Any]) -> str:
        modifier = modifier_argument(node, "align")
        return modifier or ""

    def _aligned_x(
        self,
        node: dict[str, Any],
        x: float,
        width: float,
        child_width: float,
        alignment: str | None = None,
    ) -> float:
        alignment = (alignment if alignment is not None else self._alignment(node)).lower()
        if "end" in alignment or "right" in alignment:
            return x + max(0.0, width - child_width)
        if "center" in alignment:
            return x + max(0.0, (width - child_width) / 2)
        return x

    def _aligned_y(
        self,
        node: dict[str, Any],
        y: float,
        height: float,
        child_height: float,
        alignment: str | None = None,
    ) -> float:
        alignment = (alignment if alignment is not None else self._alignment(node)).lower()
        if "top" in alignment:
            return y
        if "bottom" in alignment:
            return y + max(0.0, height - child_height)
        if "center" in alignment:
            return y + max(0.0, (height - child_height) / 2)
        return y
