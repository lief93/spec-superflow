from __future__ import annotations
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable
from ui_migration.arkui.formatting import LayoutLengths, page_number
from ui_migration.contracts.requirements import layout_parent, layout_scope
from ui_migration.common import ArkUIPageError, BUTTON_CONTAINER_COMPONENTS, PAGE_DRIVEN_RASTER_PIXEL_VP, PAGE_SNAPSHOT_COLUMN_COMPONENTS, PAGE_SNAPSHOT_FLOW_COMPONENTS, PAGE_SNAPSHOT_ROW_COMPONENTS, arkts_string, decimal_literal, named_arguments


@dataclass
class LayoutContext:
    components: dict
    mode: str
    relationships: dict
    constraints: dict
    match_parent_sizes: dict
    record_paths: Callable
    record_rule: Callable
    unresolved: Callable
    lengths: LayoutLengths


class LayoutPolicy:
    def __init__(self, context: LayoutContext):
        self.context = context

    page_number = staticmethod(page_number)

    def page_layout_length(self, value: float) -> str:
        return self.context.lengths.length(value)

    def layout_parent(self, component):
        return layout_parent(component, self.context.components)

    @staticmethod
    def page_snapshot_layout_rules(component: dict[str, Any]) -> list[dict[str, Any]]:
        source = component.get("source")
        rules = source.get("layoutRules") if isinstance(source, dict) else None
        return [rule for rule in rules if isinstance(rule, dict)] if isinstance(rules, list) else []

    @classmethod
    def page_snapshot_axis_layout_rule(
        cls,
        component: dict[str, Any],
        axis: str,
    ) -> dict[str, Any] | None:
        result: dict[str, Any] | None = None
        for rule in cls.page_snapshot_layout_rules(component):
            if (
                rule.get("kind") == "sizing"
                and axis in (rule.get("axes") or [])
            ) or (
                rule.get("kind") == "intrinsic_size"
                and rule.get("axis") == axis
            ):
                result = rule
        return result

    @classmethod
    def page_snapshot_source_layout_weight(cls, component: dict[str, Any]) -> str | None:
        for rule in cls.page_snapshot_layout_rules(component):
            if rule.get("kind") == "weight":
                if rule.get("fill") is not True:
                    return None
                return f".layoutWeight({decimal_literal(Decimal(str(rule['value'])))})"
        source = component.get("source")
        modifiers = source.get("modifiers") if isinstance(source, dict) else None
        if not isinstance(modifiers, list):
            return None
        for modifier in modifiers:
            if not isinstance(modifier, dict) or modifier.get("name") != "weight":
                continue
            arguments = modifier.get("arguments")
            if not isinstance(arguments, str):
                continue
            positional, named = named_arguments(arguments)
            if named.get("fill", positional[1] if len(positional) > 1 else "true").strip() != "true":
                return None
            value = (
                positional[0].strip()
                if positional
                else str(named.get("weight") or "").strip()
            )
            match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)[fF]?", value)
            if match is not None:
                return f".layoutWeight({match.group(1)})"
        return None

    @staticmethod
    def page_snapshot_has_explicit_axis_size(
        component: dict[str, Any],
        axis: str,
    ) -> bool:
        style = component.get("style")
        if not isinstance(style, dict):
            return False
        layout = style.get("layout")
        key = f"{axis}_dp"
        return isinstance(layout, dict) and layout.get(key) is not None

    def page_snapshot_fills_remaining_main_axis(self, component, parent, parent_type, axis):
        if not parent or parent.get('type') != parent_type:
            return False
        if axis != {'Row': 'width', 'Column': 'height'}.get(parent_type):
            return False
        if self.context.mode != 'source-tree':
            return False
        siblings = parent.get('children_ids', [])
        if len(siblings) < 2 or siblings[-1] != component['id'] or self.page_snapshot_source_layout_weight(component):
            return False
        parent_rule = self.page_snapshot_axis_layout_rule(parent, axis) or {}
        if not self.page_snapshot_has_explicit_axis_size(parent, axis) and not (
            parent_rule.get('mode') == 'fill_parent' and parent_rule.get('fraction') == 1
        ):
            return False
        scope = parent
        while scope:
            if any(r.get('kind') == 'scroll' and r.get('enabled') and
                   r.get('axis') == ('vertical' if axis == 'height' else 'horizontal')
                   for r in self.page_snapshot_layout_rules(scope)):
                return False
            if self.page_snapshot_has_explicit_axis_size(scope, axis):
                break
            scope = self.context.components.get(scope.get('parent_id'))
        for node_id in siblings[:-1]:
            sibling = self.context.components[node_id]
            if (sibling.get('source') or {}).get('custom_component') or self.page_snapshot_source_layout_weight(sibling):
                return False
            if (self.page_snapshot_axis_layout_rule(sibling, axis) or {}).get('mode') in {'fill_parent', 'match_parent'}:
                return False
        return True

    def incoming_axis_constraint(self, component, axis):
        parent = self.layout_parent(component)
        scroll_axis = 'vertical' if axis == 'height' else 'horizontal'
        while parent:
            rules = self.page_snapshot_layout_rules(parent)
            if parent.get('type') == {'height': 'LazyColumn', 'width': 'LazyRow'}[axis] or any(
                r.get('kind') == 'scroll' and r.get('enabled') and r.get('axis') == scroll_axis for r in rules
            ):
                return 'unbounded', parent['id']
            if self.page_snapshot_has_explicit_axis_size(parent, axis) or any(
                r.get('kind') == 'constraints' and (r.get('limits') or {}).get('max' + axis.title()) is not None
                for r in rules
            ):
                return 'bounded', parent['id']
            parent = self.layout_parent(parent)
        return 'bounded', 'page-viewport'

    def page_snapshot_unbounded_parent_axis(self, component, axis):
        return self.incoming_axis_constraint(component, axis)[0] == 'unbounded'

    def page_snapshot_weight_is_unbounded(self, component):
        parent = self.layout_parent(component)
        axis = {'Column': 'height', 'Row': 'width'}.get(layout_scope(parent))
        return bool(axis and self.page_snapshot_unbounded_parent_axis(component, axis))

    def page_snapshot_effective_layout_weight(self, component):
        parent = self.layout_parent(component)
        if layout_scope(parent) not in {'Row', 'Column'}:
            return None
        if self.page_snapshot_weight_is_unbounded(component):
            return None
        return self.page_snapshot_source_layout_weight(component)

    def page_snapshot_dimension_lines(
        self,
        component: dict[str, Any],
        bounds: dict[str, float],
        parent: dict[str, Any] | None,
        parent_type: str | None,
        is_text: bool,
    ) -> list[str]:
        component_type = component["type"]
        weight = self.page_snapshot_effective_layout_weight(component)
        result: list[str] = []
        for axis in ("width", "height"):
            rule = self.page_snapshot_axis_layout_rule(component, axis)
            if rule is None and self.page_snapshot_stretched_axis(component, axis):
                result.append(".alignSelf(ItemAlign.Stretch)")
                continue
            if isinstance(rule, dict):
                if rule.get("kind") == "intrinsic_size" or rule.get("mode") == "wrap_content":
                    self.context.record_rule(component, rule)
                    if component_type == "ConstraintLayout":
                        # RelativeContainer otherwise defaults to filling both axes.
                        fills = any(
                            (self.page_snapshot_axis_layout_rule(child, axis) or {}).get("mode") == "fill_parent"
                            for child_id in component.get("children_ids", [])
                            if (child := self.context.components.get(child_id)) is not None
                        )
                        result.append(f".{axis}({arkts_string('100%' if fills else 'auto')})")
                    continue
                if rule.get("mode") in {"fill_parent", "match_parent"}:
                    constraint, constraint_source_id = self.incoming_axis_constraint(component, axis)
                    if rule.get('mode') == 'fill_parent' and self.page_snapshot_unbounded_parent_axis(component, axis):
                        # Compose fillMax* is a no-op when that incoming axis is unbounded.
                        self.context.record_rule(component, rule, axis=axis, outcome='source_no_op',
                            constraint=constraint, constraint_source_id=constraint_source_id,
                            reason='Compose fillMax ignores an unbounded incoming axis')
                        continue
                    if rule.get('mode') == 'fill_parent' and rule.get('fraction') == 1 and self.page_snapshot_fills_remaining_main_axis(component, parent, parent_type, axis):
                        # Compose measures this trailing child with the remaining main-axis constraint.
                        result.append('.layoutWeight(1)')
                        self.context.record_rule(component, rule, axis=axis, constraint=constraint,
                            constraint_source_id=constraint_source_id, reason='trailing child receives remaining main-axis space')
                        continue
                    match_parent_name = self.context.match_parent_sizes.get(component['id'])
                    if rule.get('mode') == 'match_parent' and match_parent_name:
                        result.append(f'.{axis}(this.{match_parent_name}{axis.title()})')
                        self.context.record_rule(component, rule)
                        continue
                    parent_rule = self.page_snapshot_axis_layout_rule(parent, axis) if parent else None
                    if parent_rule and parent_rule.get("kind") == "intrinsic_size":
                        if (parent_type, axis) in {("Row", "height"), ("Column", "width")} and rule["fraction"] == 1:
                            result.append(".alignSelf(ItemAlign.Stretch)")
                        else:
                            self.context.unresolved(component, f"layout.{axis}", "intrinsic parent fill requires a full cross-axis stretch")
                            self.context.record_rule(component, rule, axis=axis, outcome='unresolved',
                                constraint=constraint, constraint_source_id=constraint_source_id,
                                reason='intrinsic parent fill requires a full cross-axis stretch')
                            continue
                    else:
                        percentage = decimal_literal(Decimal(str(float(rule["fraction"]) * 100)))
                        result.append(f".{axis}('{percentage}%')")
                    self.context.record_rule(component, rule, axis=axis, constraint=constraint,
                        constraint_source_id=constraint_source_id)
                    continue
            if self.page_snapshot_root_fills_viewport(component, parent, axis):
                result.append(f".{axis}('100%')")
                continue
            if self.page_snapshot_fills_parent_inner_axis(component, parent, axis):
                result.append(f".{axis}('100%')")
                continue
            weighted_axis = (
                weight is not None
                and (
                    (parent_type == "Row" and axis == "width")
                    or (parent_type == "Column" and axis == "height")
                )
            )
            if weighted_axis:
                continue
            layout = component["style"]["layout"]
            explicit = layout.get(f"{axis}_dp")
            explicit_path = f"style.layout.{axis}_dp"
            if explicit is not None:
                self.context.record_paths(component, {explicit_path})
                result.append(f".{axis}({self.page_layout_length(float(explicit))})")
            elif component_type in {"CenterAlignedTopAppBar", "TopAppBar"}:
                if axis == "width":
                    result.append(".width('100%')")
            elif component_type == "Spacer" and weight is None:
                result.append(f".{axis}(0)")
        return result

    def page_snapshot_intrinsic_image_lines(self, component: dict[str, Any]) -> list[str]:
        if component["type"] not in {"Image", "Icon", "AsyncImage"}:
            return []
        if any(
            fact.get("origin") == "modifier" and fact.get("path") in {"style.asset.width_dp", "style.asset.height_dp"}
            for fact in component.get("required_facts", [])
        ):
            self.context.unresolved(component, "style.layout", "legacy image JSON conflates modifier sizes with intrinsic asset sizes; regenerate the page JSON")
            return []
        asset = component["style"]["asset"]
        axes = [
            axis for axis in ("width", "height")
            if not self.page_snapshot_has_explicit_axis_size(component, axis)
            and (self.page_snapshot_axis_layout_rule(component, axis) or {}).get("mode") not in {"fill_parent", "match_parent"}
        ]
        if not axes:
            return []
        sizes = {axis: asset.get(f"{axis}_dp") for axis in ("width", "height")}
        if not all(isinstance(value, (int, float)) and value > 0 for value in sizes.values()):
            return []
        padding = component['style']['layout'].get('padding_dp') or {}
        sizes['width'] += (padding.get('left') or 0) + (padding.get('right') or 0)
        sizes['height'] += (padding.get('top') or 0) + (padding.get('bottom') or 0)
        if asset.get("content_scale") not in {None, "fit", "inside"}:
            self.context.unresolved(component, "style.asset.content_scale", "intrinsic image measurement currently supports Fit/Inside; other modes require explicit layout sizes")
            return []
        limits = {"max" + axis.title(): sizes[axis] for axis in axes}
        for rule in self.page_snapshot_layout_rules(component):
            if rule["kind"] == "constraints":
                # Explicit source constraints override an intrinsic preference.
                limits.update(rule["limits"])
                self.context.record_rule(component, rule)
        self.context.record_paths(component, {f"style.asset.{axis}_dp" for axis in ("width", "height")})
        values = ", ".join(f"{key}: {self.page_number(value)}" for key, value in limits.items())
        lines = [f".constraintSize({{ {values} }})"]
        if len(axes) == 2 and component["style"]["layout"].get("aspect_ratio") is None:
            lines.append(f".aspectRatio({self.page_number(sizes['width'] / sizes['height'])})")
        return lines

    def page_snapshot_stretched_axis(self, component: dict[str, Any], axis: str) -> bool:
        if self.page_snapshot_has_explicit_axis_size(component, axis):
            return False
        parent = self.context.components.get(component.get("parent_id"))
        if not parent:
            return False
        rule = self.page_snapshot_axis_layout_rule(component, axis)
        if rule:
            parent_rule = self.page_snapshot_axis_layout_rule(parent, axis)
            return bool(
                rule.get("mode") == "fill_parent" and rule.get("fraction") == 1
                and parent_rule and parent_rule.get("kind") == "intrinsic_size"
                and (parent.get("type"), axis) in {("Row", "height"), ("Column", "width")}
            )
        return bool(
            (parent.get("source") or {}).get("custom_component")
            and parent.get("children_ids") == [component["id"]]
            and self.page_snapshot_stretched_axis(parent, axis)
        )

    def page_snapshot_minimum_constraint_line(
        self,
        component: dict[str, Any],
        bounds: dict[str, float],
    ) -> str | None:
        if component.get("type") not in BUTTON_CONTAINER_COMPONENTS:
            return None
        constraints = []
        material = (component.get('source') or {}).get('material_size')
        if material:
            for axis, name in [('width', 'minWidth'), ('height', 'minHeight')]:
                if not self.page_snapshot_has_explicit_axis_size(component, axis):
                    minimum = material['min_' + axis + '_dp']
                    if component['type'] in {'IconButton', 'IconToggleButton'}:
                        padding = component['style']['layout'].get('padding_dp') or {}
                        minimum += sum(padding.get(edge, 0) for edge in
                            (('left', 'right') if axis == 'width' else ('top', 'bottom')))
                    constraints.append(f"{name}: {self.page_layout_length(minimum)}")
            return '.constraintSize({ ' + ', '.join(constraints) + ' })' if constraints else None
        if component.get('type') in {'Button', 'TextButton', 'OutlinedButton', 'IconButton', 'IconToggleButton'} and not self.page_snapshot_has_explicit_axis_size(component, 'width'):
            minimum = 58
            if component.get('type') in {'IconButton', 'IconToggleButton'}:
                padding = component['style']['layout'].get('padding_dp') or {}
                minimum = 48 + padding.get('left', 0) + padding.get('right', 0)
            constraints.append(f"minWidth: {self.page_layout_length(minimum)}")
        if not self.page_snapshot_has_explicit_axis_size(component, 'height'):
            minimum = 48
            if component.get('type') in {'IconButton', 'IconToggleButton'}:
                padding = component['style']['layout'].get('padding_dp') or {}
                minimum += padding.get('top', 0) + padding.get('bottom', 0)
            constraints.append(f"minHeight: {self.page_layout_length(minimum)}")
        return '.constraintSize({ ' + ', '.join(constraints) + ' })' if constraints else None

    def page_snapshot_flow_shrink_line(
        self,
        component: dict[str, Any],
        parent_type: str | None,
    ) -> str | None:
        if parent_type not in {"Column", "Row"}:
            return None
        if self.page_snapshot_effective_layout_weight(component) is not None:
            return None
        return ".flexShrink(0)"

    def page_snapshot_root_fills_viewport(
        self,
        component: dict[str, Any],
        parent: dict[str, Any] | None,
        axis: str,
    ) -> bool:
        if parent is not None or component.get("parent_id") is not None:
            return False
        return not self.page_snapshot_has_explicit_axis_size(component, axis)

    def page_snapshot_fills_parent_inner_axis(
        self,
        component: dict[str, Any],
        parent: dict[str, Any] | None,
        axis: str,
    ) -> bool:
        if axis not in {"width", "height"} or not isinstance(parent, dict):
            return False
        if self.page_snapshot_has_explicit_axis_size(component, axis):
            return False
        parent_source = parent.get("source")
        custom_parent = (
            isinstance(parent_source, dict)
            and (parent_source.get("custom_component") is True or parent.get("type") in {"content", "toolbar"})
            and parent.get("children_ids") == [component.get("id")]
        )
        if not custom_parent:
            return False
        parent_rule = self.page_snapshot_axis_layout_rule(parent, axis)
        if parent_rule:
            ancestor = self.context.components.get(parent.get("parent_id"))
            ancestor_rule = self.page_snapshot_axis_layout_rule(ancestor, axis) if ancestor else None
            if ancestor_rule and ancestor_rule.get("kind") == "intrinsic_size":
                return False
            return parent_rule.get("mode") in {"fill_parent", "match_parent"}
        if self.page_snapshot_has_explicit_axis_size(parent, axis):
            return True
        ancestor = self.context.components.get(parent.get("parent_id"))
        if self.page_snapshot_source_layout_weight(parent) and ancestor:
            if (ancestor.get("type"), axis) in {("Row", "width"), ("Column", "height")}:
                return True
        return self.page_snapshot_fills_parent_inner_axis(parent, ancestor, axis)

    def page_snapshot_bounds(
        self,
        component: dict[str, Any],
        parent_bounds: dict[str, float],
    ) -> tuple[dict[str, float], float, float]:
        if component.get("_runtime_bounds_applied") is True:
            bounds = dict(component["bounds_dp"])
        else:
            bounds = dict(
                component.get("source_layout_bounds_dp")
                or component.get("visual_bounds_dp")
                or component["bounds_dp"]
            )
        if (
            component["type"] in {"BasicTextField", "TextField", "OutlinedTextField"}
            and component.get("visual_bounds_dp") is not None
        ):
            raster_pixel = float(PAGE_DRIVEN_RASTER_PIXEL_VP)
            bounds["y"] -= raster_pixel
            bounds["width"] = max(raster_pixel, bounds["width"] - raster_pixel)
            bounds["height"] = max(raster_pixel, bounds["height"] - raster_pixel)
        return bounds, bounds["x"] - parent_bounds["x"], bounds["y"] - parent_bounds["y"]

    def page_snapshot_layout_container(self, component: dict[str, Any]) -> str | None:
        if self.context.mode != "source-tree":
            return None
        component_type = component["type"]
        if component_type in PAGE_SNAPSHOT_FLOW_COMPONENTS:
            return "Column" if component_type in PAGE_SNAPSHOT_COLUMN_COMPONENTS else "Row"
        if component_type == "ConstraintLayout":
            return "RelativeContainer"
        return None

    def page_snapshot_constraint_alignment_lines(
        self,
        component: dict[str, Any],
    ) -> list[str]:
        try:
            return self.page_snapshot_supported_constraint_lines(component)
        except ArkUIPageError as error:
            # The document graph was validated on input. A missing mapping here
            # is a local capability gap, not permission to infer coordinates.
            self.context.unresolved(component, "source.layout_relationships", str(error))
            return []

    def page_snapshot_supported_constraint_lines(
        self,
        component: dict[str, Any],
    ) -> list[str]:
        if self.context.mode != "source-tree":
            return []
        relationship = self.context.relationships.get(component["id"])
        if not isinstance(relationship, dict):
            raise ArkUIPageError(
                f"ConstraintLayout child has no source relationship: {component['id']}"
            )
        if relationship.get("unresolved"):
            raise ArkUIPageError(
                f"ConstraintLayout relationship is unresolved: {component['id']}"
            )
        rules: list[str] = []
        emitted_keys: set[str] = set()
        horizontal_target = {
            "start": "HorizontalAlign.Start",
            "end": "HorizontalAlign.End",
        }
        vertical_target = {
            "top": "VerticalAlign.Top",
            "bottom": "VerticalAlign.Bottom",
        }
        for constraint in relationship.get("active_constraints") or []:
            margin = constraint.get("margin_dp")
            if margin not in {None, 0, 0.0}:
                raise ArkUIPageError(
                    "ConstraintLayout margins are not yet representable without changing "
                    f"layout semantics: {component['id']}"
                )
            kind = constraint.get("kind")
            subject_anchor = constraint.get("subject_anchor")
            target_anchor = constraint.get("target_anchor")
            parent = self.context.components.get(component.get("parent_id"))
            axis = "height" if subject_anchor == "top" else "width"
            parent_rule = self.page_snapshot_axis_layout_rule(parent, axis) if parent else None
            other_axis_anchors = {"bottom", "center"} if axis == "height" else {"end", "middle"}
            if (
                kind == "link_to"
                and subject_anchor in {"top", "start"}
                and subject_anchor == target_anchor
                and constraint.get("target_reference") == "parent"
                and parent_rule and parent_rule.get("mode") == "wrap_content"
                and not any(c.get("subject_anchor") in other_axis_anchors for c in relationship["active_constraints"])
            ):
                # The origin is already zero. Keeping this redundant anchor disables
                # RelativeContainer's native wrap measurement in the same axis.
                continue
            if kind == "center_around":
                if target_anchor in horizontal_target:
                    rule_key = "middle"
                    alignment = horizontal_target[target_anchor]
                elif target_anchor in vertical_target:
                    rule_key = "center"
                    alignment = vertical_target[target_anchor]
                else:
                    raise ArkUIPageError(
                        f"unsupported centerAround anchor: {target_anchor}"
                    )
            elif kind == "link_to":
                if subject_anchor in {"start", "end"} and target_anchor in horizontal_target:
                    rule_key = "left" if subject_anchor == "start" else "right"
                    alignment = horizontal_target[target_anchor]
                elif subject_anchor in {"top", "bottom"} and target_anchor in vertical_target:
                    rule_key = subject_anchor
                    alignment = vertical_target[target_anchor]
                else:
                    raise ArkUIPageError(
                        "unsupported or cross-axis ConstraintLayout link: "
                        f"{component['id']}:{subject_anchor}->{target_anchor}"
                    )
            else:
                raise ArkUIPageError(
                    f"unsupported ConstraintLayout relationship kind: {kind}"
                )
            if rule_key in emitted_keys:
                raise ArkUIPageError(
                    f"duplicate ConstraintLayout rule {rule_key}: {component['id']}"
                )
            target_id = constraint.get("target_id")
            if constraint.get("target_reference") == "parent":
                anchor = "__container__"
            else:
                target = self.context.components.get(target_id)
                anchor = target.get("semantic_key") if isinstance(target, dict) else None
                if not isinstance(anchor, str) or not anchor:
                    raise ArkUIPageError(
                        f"ConstraintLayout target has no ArkUI id: {target_id}"
                    )
            rules.append(
                f"{rule_key}: {{ anchor: {arkts_string(anchor)}, align: {alignment} }}"
            )
            emitted_keys.add(rule_key)
        if not rules and not relationship.get("active_constraints"):
            raise ArkUIPageError(
                f"ConstraintLayout child has no active constraints: {component['id']}"
            )
        return [f".alignRules({{ {', '.join(rules)} }})"] if rules else []

    def page_snapshot_requires_position(
        self,
        component: dict[str, Any],
        bounds: dict[str, float],
        parent: dict[str, Any] | None,
        parent_container: str | None,
    ) -> bool:
        if self.context.mode == "source-tree":
            return False
        return parent_container is not None

    def page_snapshot_explicit_offset_line(
        self,
        component: dict[str, Any],
        parent: dict[str, Any] | None,
    ) -> str | None:
        if self.context.mode != "source-tree" or not isinstance(parent, dict):
            return None
        offset_rule = next(
            (
                rule
                for rule in reversed(self.page_snapshot_layout_rules(component))
                if rule.get("kind") == "offset"
            ),
            None,
        )
        if isinstance(offset_rule, dict):
            values: list[str] = []
            for axis in ("x", "y"):
                offset = offset_rule.get(axis)
                if not isinstance(offset, dict):
                    continue
                if offset.get("kind") == "dp":
                    value = float(offset["value"])
                    if abs(value) > 0.001:
                        values.append(f"{axis}: {self.page_number(value)}")
                else:
                    parent_axis = str(offset["axis"])
                    scope = parent
                    while scope and scope['type'] != 'BoxWithConstraints':
                        scope = self.context.components.get(scope.get('parent_id'))
                    bounded = False
                    if scope:
                        rule = self.page_snapshot_axis_layout_rule(scope, parent_axis) or {}
                        bounded = self.page_snapshot_has_explicit_axis_size(scope, parent_axis)
                        if not bounded and rule.get('mode') == 'fill_parent' and rule.get('fraction') == 1:
                            bounded = True
                            ancestor = self.context.components.get(scope.get('parent_id'))
                            while ancestor:
                                if self.page_snapshot_has_explicit_axis_size(ancestor, parent_axis):
                                    break
                                scroll_axis = 'vertical' if parent_axis == 'height' else 'horizontal'
                                if ancestor['type'] == ('LazyColumn' if parent_axis == 'height' else 'LazyRow') or any(
                                    r.get('kind') == 'scroll' and r.get('axis') == scroll_axis and r.get('enabled')
                                    for r in self.page_snapshot_layout_rules(ancestor)
                                ):
                                    bounded = False
                                    break
                                ancestor = self.context.components.get(ancestor.get('parent_id'))
                    if not bounded:
                        self.context.unresolved(component, 'source.modifiers.offset',
                            'parent max constraint needs a bounded, size-filling BoxWithConstraints scope; wrap size is not max constraint')
                        return None
                    state = self.context.constraints.setdefault(scope['id'], {
                        'name': f'pageConstraint{len(self.context.constraints)}', 'axes': set()})
                    state['axes'].add(parent_axis)
                    values.append(f"{axis}: this.{state['name']}{parent_axis.title()} * {self.page_number(float(offset['fraction']))}")
            return f".translate({{ {', '.join(values)} }})" if values else None
        source = component.get("source")
        modifiers = source.get("modifiers") if isinstance(source, dict) else None
        if not isinstance(modifiers, list) or not any(
            isinstance(modifier, dict) and modifier.get("name") == "offset"
            for modifier in modifiers
        ):
            return None
        self.context.unresolved(
            component,
            "source.modifiers.offset",
            "offset requires a normalized layout rule; deriving translation from bbox is forbidden",
        )
        return None

    @staticmethod
    def page_snapshot_arrangement_space(component: dict[str, Any]) -> str | None:
        layout = component["style"]["layout"]
        key = (
            "vertical_arrangement"
            if component["type"] in PAGE_SNAPSHOT_COLUMN_COMPONENTS
            else "horizontal_arrangement"
        )
        expression = layout.get(key)
        if not isinstance(expression, str):
            return None
        match = re.fullmatch(
            r"(?:Arrangement\.)?spacedBy\(\s*(?:space\s*=\s*)?(-?[0-9]+(?:\.[0-9]+)?)\.dp\s*(?:,\s*(?:alignment\s*=\s*)?Alignment\.[A-Za-z]+\s*)?\)",
            expression,
        )
        return match.group(1) if match is not None else None

    def page_snapshot_container_alignment_lines(
        self,
        component: dict[str, Any],
    ) -> list[str]:
        component_type = component["type"]
        layout = component["style"]["layout"]
        alignment = layout.get("alignment")
        lines: list[str] = []
        if component_type in PAGE_SNAPSHOT_ROW_COMPONENTS:
            if any((self.context.components[child].get('source') or {}).get('baseline_alignment')
                   for child in component.get('children_ids', []) if child in self.context.components):
                return []  # Baseline rows use Flex's ItemAlign in the constructor.
            mapped = {
                "Top": "VerticalAlign.Top",
                "CenterVertically": "VerticalAlign.Center",
                "Bottom": "VerticalAlign.Bottom",
            }.get(str(alignment or "Top").removeprefix("Alignment."))
            if mapped is not None:
                lines.append(f".alignItems({mapped})")
            arrangement = layout.get("horizontal_arrangement")
        elif component_type in PAGE_SNAPSHOT_COLUMN_COMPONENTS:
            mapped = {
                "Start": "HorizontalAlign.Start",
                "CenterHorizontally": "HorizontalAlign.Center",
                "End": "HorizontalAlign.End",
            }.get(str(alignment or "Start").removeprefix("Alignment."))
            if mapped is not None:
                lines.append(f".alignItems({mapped})")
            arrangement = layout.get("vertical_arrangement")
        else:
            arrangement = None
        justify = {
            "Arrangement.Start": "FlexAlign.Start",
            "Arrangement.Center": "FlexAlign.Center",
            "Arrangement.End": "FlexAlign.End",
            "Arrangement.Top": "FlexAlign.Start",
            "Arrangement.Bottom": "FlexAlign.End",
            "Arrangement.SpaceBetween": "FlexAlign.SpaceBetween",
            "Arrangement.SpaceAround": "FlexAlign.SpaceAround",
            "Arrangement.SpaceEvenly": "FlexAlign.SpaceEvenly",
        }.get(arrangement)
        if self.page_snapshot_arrangement_space(component) is not None:
            match = re.search(r"Alignment\.(\w+)", str(arrangement))
            justify = {"CenterHorizontally": "FlexAlign.Center", "CenterVertically": "FlexAlign.Center",
                       "Start": "FlexAlign.Start", "Top": "FlexAlign.Start",
                       "End": "FlexAlign.End", "Bottom": "FlexAlign.End"}.get(match.group(1) if match else "Start")
        if justify is not None:
            lines.append(f".justifyContent({justify})")
        if component_type == "CenterAlignedTopAppBar":
            return lines
        if component_type not in {"Box", "BoxWithConstraints", "PullToRefreshBox", "Surface", "AnimatedVisibility", "AnimatedContent"}:
            return lines
        mapped = {
            "Center": "Alignment.Center",
            "CenterStart": "Alignment.Start",
            "CenterEnd": "Alignment.End",
            "TopStart": "Alignment.TopStart",
            "TopCenter": "Alignment.Top",
            "TopEnd": "Alignment.TopEnd",
            "BottomStart": "Alignment.BottomStart",
            "BottomCenter": "Alignment.Bottom",
            "BottomEnd": "Alignment.BottomEnd",
        }.get(str(alignment or "TopStart").removeprefix("Alignment."))
        return [f".alignContent({mapped})", *lines] if mapped is not None else lines
