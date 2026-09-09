from __future__ import annotations
import copy
import re
from collections import defaultdict
from page_component_catalog import NATIVE_CONTAINERS, NATIVE_LEAVES
from typing import Any
from ui_migration.arkui.document import ArkUIDocument
from ui_migration.arkui.business_components import BusinessComponents
from ui_migration.arkui.fonts import FontRegistry
from ui_migration.arkui.formatting import LayoutLengths, page_number
from ui_migration.arkui.layout import LayoutContext, LayoutPolicy
from ui_migration.arkui.leaves import NativeLeafEmitter
from ui_migration.arkui.surface import SurfaceEmitter
from ui_migration.contracts.requirements import layout_scope
from ui_migration.arkui.typography import TypographyEmitter
from ui_migration.arkui.style_tokens import StyleTokenEmitter
from ui_migration.common import ArkUIPageError, BUTTON_CONTAINER_COMPONENTS, PAGE_DRIVEN_BASELINE_VP, PAGE_SNAPSHOT_COLUMN_COMPONENTS, arkts_string
from ui_migration.contracts.identity import canonical_sha256


class Renderer:
    def __init__(
        self,
        root: dict[str, str],
        resource_names: set[str],
        string_values: dict[str, str],
        android_page_input: dict[str, Any],
        tinted_vector_resources: dict[tuple[str, str], str] | None = None,
    ) -> None:
        if not isinstance(android_page_input, dict):
            raise ArkUIPageError(
                "source-generated page JSON is required; source translation fallback is disabled"
            )
        self.root = root
        self.resource_names = resource_names
        self.android_page_input = android_page_input
        self.android_page_layout_mode = "snapshot"
        self.verified_font_faces: list[dict[str, Any]] = []
        self.tinted_vector_resources = tinted_vector_resources or {}
        self.android_page_by_id: dict[str, dict[str, Any]] = {}
        self.android_page_by_call_id: dict[str, dict[str, Any]] = {}
        self.android_source_tree_by_id: dict[str, dict[str, Any]] = {}
        self.android_source_layout_by_subject: dict[str, dict[str, Any]] = {}
        self.android_page_applied_paths: dict[str, set[str]] = defaultdict(set)
        self.android_page_applied_component_paths: dict[str, set[str]] = defaultdict(set)
        self.android_page_reference_paths: dict[str, set[str]] = defaultdict(set)
        self.android_page_processed_call_ids: set[str] = set()
        self.android_page_processed_component_ids: set[str] = set()
        self.unresolved: list[dict[str, Any]] = []
        self._unresolved_keys: set[str] = set()
        self._uses_drawing_color_filter = False
        self.reached_keys: list[tuple[str, str]] = []
        self.selected_calls: list[dict[str, Any]] = []
        self.android_page_by_id = android_page_input["by_id"]
        self.component_ui_catalogs = android_page_input.get('component_ui_states', {})
        state_components = []
        for catalog in self.component_ui_catalogs.values():
            for variant in catalog['variants']:
                if variant['id'] == catalog['selected']:
                    continue
                self.android_page_by_id.update(variant['page']['by_id'])
                state_components.extend(variant['page']['components'])
        self._page_constraint_states: dict[str, dict[str, Any]] = {}
        if android_page_input["components"] and all(
            component.get("parent_mapping") == "source-semantic-ancestor"
            for component in android_page_input["components"]
        ):
            self.android_page_layout_mode = "source-tree"
        self.android_source_tree_by_id = android_page_input["by_id"]
        self.android_source_layout_by_subject = {
            relationship["subject_id"]: relationship
            for relationship in android_page_input.get("layout_relationships") or []
        }
        for component in [*android_page_input["components"], *state_components]:
            for fact in component.get("required_facts") or []:
                if fact["status"] in {"unresolved", "symbolic"}:
                    self.add_unresolved(
                        "page_json_required_fact", None,
                        "Source fact remains unresolved; supported content is still generated",
                        page_component_id=component["id"],
                        path=fact["path"], expression=fact.get("expression"),
                        page_reason=fact.get("reason"),
                    )
            for unresolved in component["unresolved"]:
                self.add_unresolved(
                    "android_page_visual_fact",
                    None,
                    "Android page JSON retains an unresolved visual fact",
                    page_component_id=component["id"],
                    semantic_key=component.get("semantic_key"),
                    path=unresolved["path"],
                    expression=unresolved["expression"],
                    page_reason=unresolved["reason"],
                )
        source_phase_gate = android_page_input.get("source_phase_consumption_gate") or {}
        for failure in source_phase_gate.get("failures") or []:
            self.add_unresolved(
                "page_json_source_phase", None, failure["reason"],
                page_component_id=failure["component_id"], phase=failure["phase"],
                relationship_id=failure.get("relationship_id"),
            )
        self._page_match_parent_sizes = {}
        self.lengths = LayoutLengths()
        self.business_components = BusinessComponents(android_page_input.get('component_definitions') or [], root['composable'],
                                                      self.add_page_json_unresolved)
        self.layout = LayoutPolicy(LayoutContext(
            self.android_page_by_id, self.android_page_layout_mode,
            self.android_source_layout_by_subject, self._page_constraint_states,
            self._page_match_parent_sizes, self.record_page_paths,
            self.record_page_layout_rule, self.add_page_json_unresolved, self.lengths,
        ))
        self.style_tokens = StyleTokenEmitter()
        self.surface = SurfaceEmitter(self.add_page_json_unresolved, self.style_tokens)
        self.leaves = NativeLeafEmitter(self.resource_names, self.tinted_vector_resources,
                                       self.layout, self.add_page_json_unresolved, self.business_components.bind,
                                       self.image_tint_lines, self.style_tokens)

    def add_unresolved(
        self,
        kind: str,
        call: dict[str, Any] | None,
        reason: str,
        **extra: Any,
    ) -> None:
        item: dict[str, Any] = {"kind": kind, "reason": reason}
        if call is not None:
            item.update(
                {
                    "source": call["source"],
                    "composable": call["composable"],
                    "call_id": call["call_id"],
                    "component": call["component"],
                }
            )
        item.update(extra)
        key = canonical_sha256(item)
        if key not in self._unresolved_keys:
            self._unresolved_keys.add(key)
            self.unresolved.append(item)


    def image_tint_lines(self, color: str, prefer_template: bool = False) -> list[str]:
        literal = re.fullmatch(r"'#([0-9A-Fa-f]{8})'", color)
        if literal is not None and not prefer_template:
            self._uses_drawing_color_filter = True
            return [
                ".colorFilter(drawing.ColorFilter.createBlendModeColorFilter("
                f"0x{literal.group(1).upper()}, drawing.BlendMode.SRC_IN))"
            ]
        return [
            ".renderMode(ImageRenderMode.Template)",
            f".fillColor({color})",
        ]

    def page_snapshot_text_value(self, component: dict[str, Any]) -> str:
        text = component['style']['content'].get('text')
        return text if isinstance(text, str) else ''

    def page_snapshot_descendant_consumes_typography_color(
        self,
        component: dict[str, Any],
        color: str,
    ) -> bool:
        pending = list(component.get("children_ids") or [])
        while pending:
            descendant_id = pending.pop()
            descendant = self.android_page_by_id.get(descendant_id)
            if not isinstance(descendant, dict):
                continue
            typography = (descendant.get("style") or {}).get("typography") or {}
            if (
                typography.get("color") == color
                and "style.typography.color"
                in self.android_page_applied_component_paths.get(descendant_id, set())
            ):
                return True
            pending.extend(descendant.get("children_ids") or [])
        return False

    def record_page_paths(self, component: dict[str, Any], paths: set[str]) -> None:
        if not hasattr(self, "android_page_applied_component_paths"):
            self.android_page_applied_component_paths = defaultdict(set)
        self.android_page_applied_component_paths[component["id"]].update(paths)

    def record_page_layout_rule(self, component: dict[str, Any], rule: dict[str, Any],
                                *, outcome='applied', axis=None, constraint=None,
                                constraint_source_id=None, reason='emitted layout rule') -> None:
        paths = set()
        if isinstance(rule.get("source_modifier_name"), str):
            paths.add(f"source.modifiers.{rule['source_modifier_name'].lower()}")
        modifiers = (component.get("source") or {}).get("modifiers") or []
        index = rule.get("source_modifier_index")
        if type(index) is int and 0 <= index < len(modifiers):
            name = modifiers[index].get("name")
            if isinstance(name, str):
                paths.add(f"source.modifiers.{name.lower()}")
        if outcome != 'unresolved':
            self.record_page_paths(component, paths)
        if not hasattr(self, 'android_page_layout_decisions'):
            self.android_page_layout_decisions = []
        parent = self.layout.layout_parent(component) or {}
        for path in sorted(paths):
            decision = dict(component_id=component['id'], component_type=component['type'],
                parent_id=parent.get('id'), parent_type=parent.get('type'),
                path=path, kind=rule.get('kind'), axis=axis, constraint=constraint,
                constraint_source_id=constraint_source_id, outcome=outcome, reason=reason)
            if decision not in self.android_page_layout_decisions:
                self.android_page_layout_decisions.append(decision)

    def page_snapshot_source_draw_order(self, component: dict[str, Any]) -> int | None:
        context = component.get("component_context")
        if not isinstance(context, dict):
            return None
        source_ids = [
            source_id
            for source_id in (
                context.get("source_component_id"),
                context.get("business_component_id"),
            )
            if isinstance(source_id, str)
        ]
        for source_id in source_ids:
            current = self.android_source_tree_by_id.get(source_id)
            while isinstance(current, dict):
                relationship = self.android_source_layout_by_subject.get(current["id"])
                if (
                    isinstance(relationship, dict)
                    and relationship.get("composition") == "overlay"
                    and not relationship.get("unresolved")
                ):
                    return int(relationship["draw_order"])
                parent_id = current.get("parent_id")
                current = (
                    self.android_source_tree_by_id.get(parent_id)
                    if isinstance(parent_id, str)
                    else None
                )
        return None

    def add_page_json_unresolved(
        self,
        component: dict[str, Any],
        path: str,
        reason: str,
    ) -> None:
        self.add_unresolved(
            "page_json_missing_fact",
            None,
            reason,
            page_component_id=component["id"],
            semantic_key=component.get("semantic_key"),
            path=path,
        )

    def page_snapshot_decorated_input_lines(self, component, decoration, parent_bounds, parent_type, indent):
        # BasicTextField owns editing; its decoration owns padding, chrome and slots.
        outer = copy.deepcopy(component)
        outer['type'] = 'Box'
        outer['style']['content']['text'] = None
        inner = copy.deepcopy(component)
        inner['id'] += '-editor'
        inner['semantic_key'] += '__editor'
        inner['parent_id'] = decoration['id']
        inner['children_ids'] = []
        inner['style']['layout'] = {key: None for key in inner['style']['layout']}
        inner['style']['surface'] = {key: None for key in inner['style']['surface']}
        inner['source'] = {'layoutRules': [{'kind': 'weight', 'value': 1.0, 'fill': True}]}
        row = copy.deepcopy(decoration)
        row['type'] = 'Row'
        row['style']['layout']['alignment'] = 'CenterVertically'
        facts = (decoration.get('source') or {}).get('input_decoration') or {}
        outlined = facts.get('kind') == 'material3-outlined'
        leading, trailing, supporting = [], [], []
        for child_id in row['children_ids']:
            child = self.android_page_by_id[child_id]
            slot = (child.get('source') or {}).get('slot_argument_name')
            if outlined and slot == 'supportingText':
                supporting.append(child_id)
                continue
            (leading if slot == 'leadingIcon' else trailing).append(child_id)
            if slot not in {'leadingIcon', 'trailingIcon'}:
                self.add_page_json_unresolved(child, 'source.slot_argument_name',
                    'input decoration slot retained; floating label/supporting layout is not resolved')
        row['children_ids'] = leading + [inner['id']] + trailing
        outer['children_ids'] = [row['id']]
        updates = {outer['id']: outer, row['id']: row, inner['id']: inner}
        if outlined:
            fill_width = {'kind': 'sizing', 'axes': ['width'], 'mode': 'fill_parent', 'fraction': 1}

            def container(suffix, kind, child_ids, padding=None, min_height=None):
                node = copy.deepcopy(decoration)
                node.update(id=decoration['id'] + '-' + suffix,
                            semantic_key=decoration['semantic_key'] + '__' + suffix,
                            type=kind, children_ids=child_ids, required_facts=[], unresolved=[])
                node['style'] = {group: dict.fromkeys(values) for group, values in node['style'].items()}
                node['style']['layout'].update(padding_dp=padding, alignment='Center' if kind == 'Box' else 'Start')
                rules = [copy.deepcopy(fill_width)]
                if min_height is not None:
                    rules.append({'kind': 'constraints', 'limits': {'minHeight': min_height}})
                node['source'] = {'layoutRules': rules}
                updates[node['id']] = node
                return node

            # Material measures the editor with content padding, but icons without it.
            padding = row['style']['layout'].get('padding_dp') or dict.fromkeys(('left', 'right', 'top', 'bottom'), 0)
            line = container('text_line', 'Box', [inner['id']], min_height=facts['text_min_height_dp'])
            padded = container('text_padding', 'Box', [line['id']],
                               dict(left=0, right=0, top=padding['top'], bottom=padding['bottom']))
            padded['source']['layoutRules'] = [{'kind': 'weight', 'value': 1.0, 'fill': True}]
            padded['parent_id'], line['parent_id'], inner['parent_id'] = row['id'], padded['id'], line['id']
            inner['source']['layoutRules'] = [copy.deepcopy(fill_width)]
            row['style']['layout']['padding_dp'] = {**padding, 'top': 0, 'bottom': 0}
            row['source'].setdefault('layoutRules', []).append(copy.deepcopy(fill_width))
            row['children_ids'] = leading + [padded['id']] + trailing
            if facts.get('supporting_text') is True or supporting:
                support = container('supporting', 'Column', supporting,
                                    facts['supporting_padding_dp'], facts['supporting_min_height_dp'])
                support['parent_id'] = outer['id']
                for child_id in supporting:
                    updates[child_id] = {**self.android_page_by_id[child_id], 'parent_id': support['id']}
                outer['type'] = 'Column'
                outer['children_ids'].append(support['id'])
            self.record_page_paths(decoration, {'source.input_decoration'})
        original = {node_id: self.android_page_by_id.get(node_id) for node_id in updates}
        self.android_page_by_id.update(updates)
        try:
            return self.page_snapshot_component_lines(outer, parent_bounds, parent_type, indent)
        finally:
            for node_id, node in original.items():
                if node is None:
                    self.android_page_by_id.pop(node_id, None)
                else:
                    self.android_page_by_id[node_id] = node

    def page_snapshot_component_lines(
        self,
        component: dict[str, Any],
        parent_bounds: dict[str, float],
        parent_type: str | None,
        indent: int,
    ) -> list[str]:
        prefix = " " * indent
        component_type = component["type"]
        selection = (component.get('source') or {}).get('state_resolution') or {}
        if selection.get('status') == 'unresolved':
            self.add_page_json_unresolved(component, 'source.state_resolution',
                'source branch/list template is preserved in JSON; state input is required before rendering it')
            return []
        children = [self.android_page_by_id[child_id] for child_id in component["children_ids"]]
        catalog = self.component_ui_catalogs.get(component['id'])
        if catalog is not None:
            def render_variant(variant):
                if variant['id'] == catalog['selected']:
                    roots = children
                else:
                    roots = [variant['page']['by_id'][node_id] for node_id in variant['root']['children_ids']]
                lines = [line for child in roots for line in self.page_snapshot_component_lines(child, parent_bounds, parent_type, 4)]
                expected, pending = set(), list(roots)
                while pending:
                    child = pending.pop()
                    expected.add(child['id'])
                    pending.extend(self.android_page_by_id[n] for n in child['children_ids'])
                missing = sorted(expected - self.android_page_processed_component_ids)
                self.business_components.ui_states.coverage.append({'name':catalog['name'],
                    'instance_id':component['id'], 'state':variant['id'],
                    'component_count':len(expected), 'missing_component_ids':missing})
                if missing:
                    self.add_page_json_unresolved(component, 'source.component_ui_states.' + variant['id'],
                        'UI variant contains unrendered components: ' + ', '.join(missing))
                return lines
            lines = self.business_components.ui_states.render(component, catalog, render_variant, indent)
            self.android_page_processed_component_ids.add(component['id'])
            self.android_page_applied_component_paths[component['id']].update({
                'structure.type', 'structure.parent_id', 'structure.children_ids', 'structure.sibling_index'})
            return lines
        if component.get('source', {}).get('component_reuse') is not None:
            lines = self.component_reuse.render(component, children, lambda child, level:
                self.page_snapshot_component_lines(child, parent_bounds, None, level), indent)
            self.android_page_processed_component_ids.add(component['id'])
            self.android_page_applied_component_paths[component['id']].update({
                'structure.type', 'structure.parent_id', 'structure.children_ids',
                'structure.sibling_index', 'source.component_reuse'})
            return lines
        native_containers = NATIVE_CONTAINERS
        native_leaves = NATIVE_LEAVES
        project_wrapper = (component.get("source") or {}).get("custom_component") is True
        slot_invocation = (component.get('source') or {}).get('slot_invocation')
        if (project_wrapper or slot_invocation) and self.android_page_layout_mode == 'source-tree':
            def body(body_indent):
                return [line for child in children for line in
                        self.page_snapshot_component_lines(child, parent_bounds, parent_type, body_indent)]
            if project_wrapper and component.get('definition_id'):
                lines = self.business_components.render(component, lambda: body(4), indent)
            elif slot_invocation and self.business_components.frames:
                lines = self.business_components.slot(component, lambda: body(4), indent)
            else:
                lines = body(indent)
            self.android_page_processed_component_ids.add(component['id'])
            applied = self.android_page_applied_component_paths[component['id']]
            applied.update({
                'structure.type', 'structure.parent_id', 'structure.children_ids', 'structure.sibling_index'})
            for child in children:
                consumed = self.android_page_applied_component_paths.get(child['id'], set())
                for section, values in component['style'].items():
                    for field, value in values.items():
                        path = f'style.{section}.{field}'
                        if value is not None and path in consumed and child['style'].get(section, {}).get(field) == value:
                            applied.add(path)
                for rule in self.layout.page_snapshot_layout_rules(component):
                    if rule in self.layout.page_snapshot_layout_rules(child):
                        self.record_page_layout_rule(component, rule)
            return lines
        if component_type == 'Canvas':
            self.add_page_json_unresolved(component, 'source.custom_draw', 'custom Canvas drawing is not translated; declared layout is retained without invented pixels')
        elif component_type not in native_containers | native_leaves | BUTTON_CONTAINER_COMPONENTS and not project_wrapper:
            self.add_page_json_unresolved(component, "structure.type", f"unsupported component {component_type}; implicit Stack fallback is disabled")
            return []
        source_layout_weight = self.layout.page_snapshot_effective_layout_weight(component)
        bounds, relative_x, relative_y = self.layout.page_snapshot_bounds(component, parent_bounds)
        is_text = component_type in {"Text", "BasicText", "ClickableText"}
        is_text_field = component_type in {"BasicTextField", "TextField", "OutlinedTextField"}
        from ui_migration.contracts.style_tokens import has_token_reference
        if (is_text or is_text_field) and not has_token_reference(component, 'content.text') and not isinstance(component["style"]["content"].get("text"), str):
            self.add_page_json_unresolved(component, "style.content.text", "dynamic content is unresolved; native control and static styles are retained without invented text")
        decoration = next((child for child in children if child['type'] == 'DecorationBox'), None)
        if is_text_field and decoration is not None:
            return self.page_snapshot_decorated_input_lines(component, decoration, parent_bounds, parent_type, indent)
        input_style = component['style'].get('input') or {}
        control = component['style'].get('control') or {}
        size_updates: list[str] = []
        multiline_input = is_text_field and input_style.get('single_line') is False
        is_button = component_type in BUTTON_CONTAINER_COMPONENTS
        intrinsic_image_lines = self.layout.page_snapshot_intrinsic_image_lines(component)
        page_tint_baked = False
        page_image_drawn = False
        emitted_phase_paths: set[str] = set()
        scroll_rule = next((r for r in self.layout.page_snapshot_layout_rules(component) if r["kind"] == "scroll"), None)
        scroll_axis = (scroll_rule or {}).get("axis") if (scroll_rule or {}).get("enabled") else None
        if component_type in {"LazyColumn", "LazyRow"}:
            scroll_axis = "vertical" if component_type == "LazyColumn" else "horizontal"

        if self.leaves.supports(component_type):
            leaf = self.leaves.emit(component, prefix, parent_type)
            if not leaf.lines:
                return []
            lines = leaf.lines
            emitted_phase_paths.update(leaf.consumed)
            page_tint_baked, page_image_drawn = leaf.tint_baked, leaf.image_drawn
        elif component_type in {'ListItem', 'FilterChip', 'ExtendedFloatingActionButton'}:
            from ui_migration.arkui.material_items import material_item_lines
            lines = material_item_lines(self, component, children, bounds, indent)
        elif is_button:
            lines = [f"{prefix}Stack() {{"]
            if len(children) > 1:
                lines.append(f"{prefix}  Row() {{")
                for child in children:
                    lines.extend(
                        self.page_snapshot_component_lines(
                            child, bounds, "Row", indent + 4
                        )
                    )
                lines.extend((f"{prefix}  }}", f"{prefix}    .alignItems(VerticalAlign.Center)"))
            else:
                for child in children:
                    lines.extend(
                        self.page_snapshot_component_lines(
                            child, bounds, component_type, indent + 2
                        )
                    )
            lines.append(f"{prefix}}}")
        elif component_type == 'BottomAppBar':
            lines = [f'{prefix}Row() {{']
            for child in children:
                lines.extend(self.page_snapshot_component_lines(child, bounds, 'Row', indent + 2))
            lines.extend([f'{prefix}}}', f"{prefix}  .width('100%')",
                          f'{prefix}  .alignItems(VerticalAlign.Center)'])
            if not self.layout.page_snapshot_has_explicit_axis_size(component, 'height'):
                lines.append(f'{prefix}  .height({self.lengths.length(80)})')
        elif component_type in {'TopAppBar', 'CenterAlignedTopAppBar', 'LargeFlexibleTopAppBar', 'Scaffold'}:
            if component_type == 'Scaffold':
                self._page_scaffold_states[component['id']] = f'scaffold{len(self._page_scaffold_states)}'
            is_appbar = component_type != 'Scaffold'
            appbar = (component.get('source') or {}).get('appbar') or {}
            large_appbar = component_type == 'LargeFlexibleTopAppBar'
            lines = [f"{prefix}{'RelativeContainer' if is_appbar else 'Stack'}() {{"]
            for child in children:
                child_lines = self.page_snapshot_component_lines(child, bounds, 'Stack', indent + 2)
                slot = (child.get('source') or {}).get('slot_argument_name')
                alignment = ({'title': 'Center' if component_type == 'CenterAlignedTopAppBar' else 'Start',
                              'navigationIcon': 'Start', 'actions': 'End'}
                             if component_type != 'Scaffold' else
                             {'topBar': 'Top', 'bottomBar': 'Bottom', 'content': 'TopStart', 'floatingActionButton': 'BottomEnd'})
                if child_lines and slot in alignment:
                    if (child.get('source') or {}).get('custom_component') or child.get('definition_id'):
                        child_lines = [f'{prefix}  Stack() {{',
                                       *['  ' + line for line in child_lines], f'{prefix}  }}']
                        if component_type == 'Scaffold':
                            child_lines.append(f"{prefix}    .width('100%')")
                            child_lines.append(f'{prefix}    .alignContent(Alignment.TopStart)')
                    if is_appbar:
                        if large_appbar and slot == 'title':
                            bottom = self.lengths.length(appbar.get('title_baseline_bottom_dp', 28))
                            text = child['style']['typography']
                            alias = self.typography.fonts.alias(str(text.get('font_family') or ''), text.get('font_weight'))
                            face = next((f for f in self.verified_font_faces if f['alias'] == alias), None)
                            if child['type'] == 'Text' and face and text.get('line_height_sp') is not None and text.get('font_size_sp') is not None:
                                self.typography.uses_font_metrics = True
                                bottom = f'this.layoutPx({appbar.get("title_baseline_bottom_dp", 28)} - this.nativeBaselineBottom($rawfile({arkts_string(face["rawfile"])}), {page_number(text["font_size_sp"])}, {page_number(text["line_height_sp"])}))'
                            else:
                                self.add_page_json_unresolved(child, 'source.appbar.title_baseline', 'expanded appbar title needs verified baseline metrics')
                            child_lines.append(f"{prefix}    .alignRules({{ left: {{ anchor: '__container__', align: HorizontalAlign.Start }}, bottom: {{ anchor: '__container__', align: VerticalAlign.Bottom }} }})")
                            child_lines.append(f"{prefix}    .margin({{ left: {self.lengths.length(12)}, bottom: {bottom} }})")
                            lines.extend(child_lines)
                            continue
                        edge = {'navigationIcon': 'left', 'actions': 'right', 'title': 'middle' if component_type == 'CenterAlignedTopAppBar' else 'left'}[slot]
                        align = {'left': 'Start', 'right': 'End', 'middle': 'Center'}[edge]
                        child_lines.append(f"{prefix}    .alignRules({{ {edge}: {{ anchor: '__container__', align: HorizontalAlign.{align} }}, center: {{ anchor: '__container__', align: VerticalAlign.Center }} }})")
                        if slot == 'title' and edge == 'left':
                            has_navigation = any(c.get('source', {}).get('slot_argument_name') == 'navigationIcon' for c in children)
                            child_lines.append(f'{prefix}    .margin({{ left: {self.lengths.length(48 if has_navigation else 12)} }})')
                    else:
                        gravity = {'topBar': 'TOP', 'bottomBar': 'BOTTOM', 'content': 'TOP_START', 'floatingActionButton': 'BOTTOM_END'}[slot]
                        child_lines.append(f'{prefix}    .layoutGravity(LocalizedAlignment.{gravity})')
                        if slot == 'floatingActionButton':
                            state_name = self._page_scaffold_states[component['id']] + 'Bottombar'
                            child_lines.append(f'{prefix}    .margin({{ right: {self.lengths.length(16)}, bottom: this.layoutPx(16 + this.{state_name}) }})')
                            child_lines.append(f'{prefix}    .zIndex(2)')
                    if component_type == 'Scaffold' and slot in {'topBar', 'bottomBar'}:
                        state_name = self._page_scaffold_states[component['id']] + slot.title()
                        child_lines.append(f'{prefix}    .onAreaChange((_old, area) => {{ this.{state_name} = Number(area.height) }})')
                        child_lines.append(f'{prefix}    .zIndex(1)')
                elif child_lines:
                    self.add_page_json_unresolved(child, 'source.slot_argument_name',
                                                  'native container child requires an explicit supported slot')
                lines.extend(child_lines)
            lines.append(f'{prefix}}}')
            if is_appbar:
                if not self.layout.page_snapshot_has_explicit_axis_size(component, 'height'):
                    lines.append(f'{prefix}  .height({self.lengths.length(appbar.get("content_height_dp", 64) + (appbar.get("top_inset_dp") or 0))})')
                lines.append(f'{prefix}  .padding({{ left: {self.lengths.length(4)}, right: {self.lengths.length(4)}, top: {self.lengths.length(appbar.get("top_inset_dp") or 0)} }})')
                if appbar:
                    emitted_phase_paths.add('source.appbar')
            else:
                lines.append(f'{prefix}  .alignContent(Alignment.TopStart)')
        elif component_type in {'HorizontalPager', 'VerticalPager'}:
            from ui_migration.arkui.pager import pager_lines
            lines, consumed = pager_lines(self, component, bounds, indent)
            emitted_phase_paths.update(consumed)
        elif component_type == 'PullToRefreshBox':
            refreshing = component['style']['state'].get('refreshing')
            if not isinstance(refreshing, bool):
                self.add_page_json_unresolved(component, 'style.state.refreshing',
                    'refresh state is unresolved; only the content layout is rendered')
            custom_indicator = any((child.get('source') or {}).get('slot_argument_name') == 'indicator'
                                   for child in children)
            # Compose overlays its indicator; ArkUI Refresh would move the content by 64vp.
            # Keep the fixed-state Box layout and do not invent an onRefresh callback.
            lines = [f'{prefix}Stack() {{']
            for child in children:
                lines.extend(self.page_snapshot_component_lines(child, bounds, 'Stack',
                    indent + 2))
            if refreshing is True and not custom_indicator:
                # Material3: 40dp container, 16dp spinner, settled threshold 80dp.
                lines.extend([f'{prefix}  Stack() {{', f'{prefix}    LoadingProgress()',
                    f'{prefix}      .width({self.lengths.length(16)})',
                    f'{prefix}      .height({self.lengths.length(16)})'])
                if control.get('active_color'):
                    lines.append(f"{prefix}      .color({arkts_string(control['active_color'])})")
                    emitted_phase_paths.add('style.control.active_color')
                lines.extend([f'{prefix}  }}', f'{prefix}    .width({self.lengths.length(40)})',
                    f'{prefix}    .height({self.lengths.length(40)})',
                    f'{prefix}    .borderRadius({self.lengths.length(20)})',
                    f'{prefix}    .layoutGravity(LocalizedAlignment.TOP)',
                    f'{prefix}    .translate({{ y: {self.lengths.length(40)} }})',
                    f'{prefix}    .hitTestBehavior(HitTestMode.Transparent)',
                    f"{prefix}    .id({arkts_string(str(component.get('semantic_key') or component['id']) + '__refresh_indicator')})"])
                if control.get('inactive_color'):
                    lines.append(f"{prefix}    .backgroundColor({arkts_string(control['inactive_color'])})")
                    emitted_phase_paths.add('style.control.inactive_color')
            elif refreshing is False:
                emitted_phase_paths.update({'style.control.active_color', 'style.control.inactive_color'})
            lines.append(f'{prefix}}}')
            if isinstance(refreshing, bool) and not custom_indicator:
                emitted_phase_paths.add('style.state.refreshing')
        elif children or component_type in native_containers:
            layout_container = self.layout.page_snapshot_layout_container(component)
            if project_wrapper and self.layout.page_snapshot_stretched_axis(component, "height"):
                layout_container = "Row"
            elif project_wrapper and self.layout.page_snapshot_stretched_axis(component, "width"):
                layout_container = "Column"
            rendered_container = layout_container or "Stack"
            space = (
                self.layout.page_snapshot_arrangement_space(component)
                if rendered_container in {"Column", "Row"}
                else None
            )
            constructor = (
                f"{rendered_container}({{ space: {self.lengths.length(float(space))} }})"
                if space is not None
                else f"{rendered_container}()"
            )
            if rendered_container == 'Row' and any((child.get('source') or {}).get('baseline_alignment') for child in children):
                constructor = 'Flex({ direction: FlexDirection.Row, alignItems: ItemAlign.Baseline })'
            container_prefix = prefix + "  " if scroll_axis else prefix
            lines = [f"{prefix}Scroll() {{"] if scroll_axis else []
            lines.append(f"{container_prefix}{constructor} {{")
            for child in children:
                if component_type in {'Box', 'BoxWithConstraints'} and any(
                    rule.get('mode') == 'match_parent' for rule in self.layout.page_snapshot_layout_rules(child)
                ):
                    name = f'pageMatchParent{len(self._page_match_parent_sizes)}'
                    self._page_match_parent_sizes[child['id']] = name
                    child_lines = self.page_snapshot_component_lines(child, bounds, 'Stack', 4)
                    self._page_match_parent_builders.append([
                        f'  @State private {name}Width: Length = 0',
                        f'  @State private {name}Height: Length = 0',
                        '  @Builder', f'  private {name}() {{', *child_lines, '  }', '',
                    ])
                    size_updates.extend([f'this.{name}Width = current.width ?? this.{name}Width',
                                         f'this.{name}Height = current.height ?? this.{name}Height'])
                    continue
                lines.extend(
                    self.page_snapshot_component_lines(
                        child, bounds, rendered_container, indent + (4 if scroll_axis else 2)
                    )
                )
            lines.append(f"{container_prefix}}}")
            for child in children:
                name = self._page_match_parent_sizes.get(child['id'])
                if name:
                    lines.append(f'{container_prefix}  .overlay(this.{name}(), {{ align: Alignment.TopStart }})')
            if scroll_axis:
                lines.extend(f"{container_prefix}  {line}" for line in self.layout.page_snapshot_container_alignment_lines(component))
                if scroll_axis == 'vertical':
                    lines.append(f"{container_prefix}  .width('100%')")
                lines.extend([f"{prefix}}}", f"{prefix}  .scrollable(ScrollDirection.{scroll_axis.title()})", f"{prefix}  .scrollBar(BarState.Off)"])
                lines.append(f'{prefix}  .align(Alignment.TopStart)')
                if scroll_rule:
                    self.record_page_layout_rule(component, scroll_rule)
        else:
            return []

        is_flow_child = (
            self.android_page_layout_mode == "source-tree"
            and parent_type in {"Column", "Row"}
        )
        parent_component = self.android_page_by_id.get(component.get("parent_id", ""))
        structural_parent = parent_component
        if self.android_page_layout_mode == 'source-tree':
            parent_component = self.layout.layout_parent(component)
        centered_button_child = (
            parent_type in BUTTON_CONTAINER_COMPONENTS
            and isinstance(parent_component, dict)
            and parent_component.get("children_ids") == [component["id"]]
        )
        requires_position = self.layout.page_snapshot_requires_position(
            component, bounds, parent_component, parent_type
        )
        if (
            is_text
            and parent_type not in BUTTON_CONTAINER_COMPONENTS
            and not is_flow_child
            and requires_position
        ):
            relative_y -= float(PAGE_DRIVEN_BASELINE_VP)
        if centered_button_child:
            lines.append(f"{prefix}  .align(Alignment.Center)")
        elif parent_type == "RelativeContainer":
            for alignment_line in self.layout.page_snapshot_constraint_alignment_lines(component):
                lines.append(f"{prefix}  {alignment_line}")
            for rule in self.layout.page_snapshot_layout_rules(component):
                if rule["kind"] == "constraint_reference":
                    self.record_page_layout_rule(component, rule)
        elif requires_position:
            lines.append(
                f"{prefix}  .position({{ x: {page_number(relative_x)}, y: {page_number(relative_y)} }})"
            )
        if self.android_page_layout_mode == "source-tree":
            resolved_translation = self.layout.page_snapshot_explicit_offset_line(
                component, parent_component
            )
            if resolved_translation is not None:
                lines.append(f"{prefix}  {resolved_translation}")
                for rule in self.layout.page_snapshot_layout_rules(component):
                    if rule["kind"] == "offset":
                        self.record_page_layout_rule(component, rule)
        source_draw_order = self.page_snapshot_source_draw_order(component)
        parent = parent_component
        parent_draw_order = (
            self.page_snapshot_source_draw_order(parent)
            if isinstance(parent, dict)
            else None
        )
        if source_draw_order is not None and source_draw_order != parent_draw_order:
            lines.append(f"{prefix}  .zIndex({source_draw_order})")
        if source_layout_weight is not None:
            lines.append(f"{prefix}  {source_layout_weight}")
        for rule in self.layout.page_snapshot_layout_rules(component):
            if rule["kind"] == "weight":
                axis = {'Row': 'width', 'Column': 'height'}.get(layout_scope(parent_component))
                if parent_type in {"Row", "Column"} and (
                    source_layout_weight is not None or self.layout.page_snapshot_weight_is_unbounded(component)
                ):
                    constraint, origin = self.layout.incoming_axis_constraint(component, axis)
                    self.record_page_layout_rule(component, rule, axis=axis, constraint=constraint,
                        constraint_source_id=origin,
                        outcome='applied' if source_layout_weight else 'source_no_op',
                        reason='finite main-axis weight allocation' if source_layout_weight else
                               'Compose weight ignores an unbounded incoming main axis')
                else:
                    self.record_page_layout_rule(component, rule, axis=axis, outcome='unresolved',
                        reason='weight requires Row/Column and supported fill semantics')
                    self.add_page_json_unresolved(component, "source.modifiers.weight", "weight requires Row/Column and fill=true; fill=false allocation is not yet equivalent")
            elif rule["kind"] == "alignment":
                value = rule["value"].removeprefix("Alignment.")
                axis_alignments = {
                    "Row": {"Top": "ItemAlign.Start", "Bottom": "ItemAlign.End", "CenterVertically": "ItemAlign.Center"},
                    "Column": {"Start": "ItemAlign.Start", "End": "ItemAlign.End", "CenterHorizontally": "ItemAlign.Center"},
                }
                mapped = axis_alignments.get(parent_type, {}).get(value)
                if mapped:
                    lines.append(f"{prefix}  .alignSelf({mapped})")
                    self.record_page_layout_rule(component, rule)
                elif parent_type == "Stack":
                    mapped = {"TopStart": "TOP_START", "TopCenter": "TOP", "TopEnd": "TOP_END", "CenterStart": "START", "Center": "CENTER", "CenterEnd": "END", "BottomStart": "BOTTOM_START", "BottomCenter": "BOTTOM", "BottomEnd": "BOTTOM_END"}.get(value)
                    if mapped:
                        lines.append(f"{prefix}  .layoutGravity(LocalizedAlignment.{mapped})")
                        self.record_page_layout_rule(component, rule)
                if not mapped:
                    self.add_page_json_unresolved(component, "source.modifiers.align", "alignment is not valid for the actual parent layout scope")
            elif rule["kind"] == "z_index":
                lines.append(f"{prefix}  .zIndex({rule['value']})")
                self.record_page_layout_rule(component, rule)
            elif rule["kind"] == "constraints":
                if not intrinsic_image_lines:
                    limits = ", ".join(f"{key}: {self.lengths.length(value)}" for key, value in rule["limits"].items())
                    lines.append(f"{prefix}  .constraintSize({{ {limits} }})")
                self.record_page_layout_rule(component, rule)
            elif rule["kind"] == "scroll" and not rule["enabled"]:
                self.record_page_layout_rule(component, rule)
        flow_shrink = self.layout.page_snapshot_flow_shrink_line(component, parent_type)
        if flow_shrink is not None:
            lines.append(f"{prefix}  {flow_shrink}")
        lines.extend(
            f"{prefix}  {line}"
            for line in self.layout.page_snapshot_dimension_lines(
                component,
                bounds,
                parent_component,
                parent_type,
                is_text,
            )
        )
        minimum_constraint = self.layout.page_snapshot_minimum_constraint_line(component, bounds)
        baseline = (component.get('source') or {}).get('baseline_alignment')
        if baseline and parent_type == 'Row':
            if baseline['kind'] == 'first_baseline':
                emitted_phase_paths.add('source.modifiers.alignby')
            elif baseline['kind'] == 'offset' and self.layout.page_snapshot_has_explicit_axis_size(component, 'height'):
                delta = component['style']['layout']['height_dp'] - baseline['offset_dp']
                lines.append(f'{prefix}  .translate({{ y: {self.lengths.length(delta)} }})')
                emitted_phase_paths.add('source.modifiers.alignby')
        lines.extend(f"{prefix}  {line}" for line in intrinsic_image_lines)
        if minimum_constraint is not None:
            lines.append(f"{prefix}  {minimum_constraint}")
            if (component.get('source') or {}).get('material_size'):
                emitted_phase_paths.add('source.material_size')
        if component_type in {"CenterAlignedTopAppBar", "TopAppBar"} and not self.layout.page_snapshot_has_explicit_axis_size(component, "height"):
            padding = component["style"]["layout"].get("padding_dp") or {}
            height = 64 + float(padding.get("top", 0)) + float(padding.get("bottom", 0))
            lines.append(f"{prefix}  .constraintSize({{ minHeight: {self.lengths.length(height)} }})")
        semantic_key = component.get("semantic_key")
        if isinstance(semantic_key, str):
            identity = self.business_components.bind(component, 'semantic_key', arkts_string(semantic_key))
            lines.append(f"{prefix}  .id({identity})")
        alignment_lines = self.layout.page_snapshot_container_alignment_lines(component)
        if not scroll_axis:
            lines.extend(f"{prefix}  {line}" for line in alignment_lines)
        if any(".alignItems(" in line or ".alignContent(" in line for line in alignment_lines):
            emitted_phase_paths.add("style.layout.alignment")
        if any(".justifyContent(" in line for line in alignment_lines):
            emitted_phase_paths.add("style.layout.vertical_arrangement" if component_type in PAGE_SNAPSHOT_COLUMN_COMPONENTS else "style.layout.horizontal_arrangement")
        if is_button:
            lines.append(f"{prefix}  .padding(0)")

        style = component["style"]
        state = style["state"]
        if isinstance(state.get("enabled"), bool):
            lines.append(f"{prefix}  .enabled({str(state['enabled']).lower()})")
            emitted_phase_paths.add("style.state.enabled")
        if state.get("visible") is False:
            lines.append(f"{prefix}  .visibility(Visibility.None)")
            emitted_phase_paths.add("style.state.visible")
        description = style["content"].get("content_description")
        if isinstance(description, str):
            description = self.business_components.bind(component, 'style.content.description', arkts_string(description))
            lines.append(f"{prefix}  .accessibilityText({description})")
            emitted_phase_paths.add("style.content.content_description")
        transform = style["transform"]
        translation = {axis: transform.get(f"translation_{axis}_dp") for axis in ("x", "y")}
        if any(value is not None for value in translation.values()):
            if any(rule['kind'] == 'offset' for rule in self.layout.page_snapshot_layout_rules(component)):
                self.add_page_json_unresolved(component, "style.transform", "offset plus explicit translation requires ordered transform composition")
            else:
                values = ', '.join(f"{axis}: {self.lengths.length(value)}" for axis, value in translation.items() if value is not None)
                lines.append(f"{prefix}  .translate({{ {values} }})")
                emitted_phase_paths.update(f"style.transform.translation_{axis}_dp" for axis, value in translation.items() if value is not None)
        if transform.get('scale_x') is not None or transform.get('scale_y') is not None:
            values = ', '.join(f"{axis}: {page_number(transform.get('scale_' + axis) if transform.get('scale_' + axis) is not None else 1)}" for axis in ('x', 'y'))
            lines.append(f"{prefix}  .scale({{ {values} }})")
            emitted_phase_paths.update(f"style.transform.scale_{axis}" for axis in ('x', 'y') if transform.get('scale_' + axis) is not None)
        if transform.get('rotation_degrees') not in (None, 0):
            lines.append(f"{prefix}  .rotate({{ angle: {page_number(transform['rotation_degrees'])} }})")
            emitted_phase_paths.add('style.transform.rotation_degrees')
        layout_style = style["layout"]
        if layout_style.get("aspect_ratio") is not None:
            lines.append(f"{prefix}  .aspectRatio({page_number(layout_style['aspect_ratio'])})")
            emitted_phase_paths.add("style.layout.aspect_ratio")
        if isinstance(layout_style.get("margin_dp"), dict):
            lines.append(f"{prefix}  .margin({self.lengths.edges(layout_style['margin_dp'])})")
            emitted_phase_paths.add("style.layout.margin_dp")
        direction = {"ltr": "Ltr", "rtl": "Rtl"}.get(layout_style.get("layout_direction"))
        if direction:
            lines.append(f"{prefix}  .direction(Direction.{direction})")
            emitted_phase_paths.add("style.layout.layout_direction")
        if layout_style.get("z_index") is not None:
            lines.append(f"{prefix}  .zIndex({page_number(layout_style['z_index'])})")
            emitted_phase_paths.add("style.layout.z_index")
        surface_lines, surface_paths, surface_updates = self.surface.emit(component, prefix)
        lines.extend(surface_lines)
        emitted_phase_paths.update(surface_paths)
        size_updates.extend(surface_updates)
        text_lines, text_paths = self.typography.emit(component, prefix, is_text, is_text_field)
        lines.extend(text_lines)
        emitted_phase_paths.update(text_paths)

        if component_type in {"Image", "Icon", "AsyncImage"} and page_image_drawn:
            content_scale = {
                "fit": "ImageFit.Contain",
                "crop": "ImageFit.Cover",
                "fill": "ImageFit.Fill",
                "inside": "ImageFit.ScaleDown",
                "none": "ImageFit.None",
            }.get(style["asset"].get("content_scale"))
            if content_scale is not None:
                lines.append(f"{prefix}  .objectFit({content_scale})")
                emitted_phase_paths.add("style.asset.content_scale")
            tint = style["asset"].get("tint")
            if isinstance(tint, str) and not page_tint_baked:
                lines.extend(
                    f"{prefix}  {line}"
                    for line in self.image_tint_lines(arkts_string(tint))
                )
                emitted_phase_paths.add("style.asset.tint")
        elif component_type == "ProgressRing":
            custom_draw = component.get("custom_draw")
            if isinstance(custom_draw, dict):
                lines.extend((
                    f"{prefix}  .color({arkts_string(custom_draw['active_color'])})",
                    f"{prefix}  .backgroundColor({arkts_string(custom_draw['track_color'])})",
                    f"{prefix}  .style({{ strokeWidth: {page_number(float(custom_draw['stroke_width_dp']))} }})",
                ))

        padding = style["layout"]["padding_dp"]
        if isinstance(padding, dict):
            lines.append(f"{prefix}  .padding({self.lengths.edges(padding)})")
            emitted_phase_paths.add("style.layout.padding_dp")
        if is_text_field and not multiline_input:
            lines.append(f"{prefix}  .showPasswordIcon(false)")
        if is_text_field:
            password = input_style.get('password')
            keyboard = input_style.get('keyboard_type')
            if multiline_input and (password or keyboard in {'password', 'number_password'}):
                self.add_page_json_unresolved(component, 'style.input.password', 'multiline password needs a dedicated transformation renderer')
            else:
                kind = ('number_password' if keyboard in {'number', 'number_password'} else 'password') if password else keyboard
                native_types = ({'text': 'NORMAL', 'number': 'NUMBER', 'phone': 'PHONE_NUMBER', 'email': 'EMAIL', 'url': 'URL', 'decimal': 'NUMBER_DECIMAL'}
                    if multiline_input else {'text': 'Normal', 'number': 'Number', 'phone': 'PhoneNumber', 'email': 'Email', 'url': 'URL', 'decimal': 'NUMBER_DECIMAL', 'password': 'Password', 'number_password': 'NUMBER_PASSWORD'})
                if kind in native_types:
                    lines.append(f"{prefix}  .type({'TextAreaType' if multiline_input else 'InputType'}.{native_types[kind]})")
                    emitted_phase_paths.add('style.input.keyboard_type')
                if password is not None:
                    if not multiline_input and kind in {'password', 'number_password'}:
                        lines.append(f"{prefix}  .showPassword({str(not password).lower()})")
                    emitted_phase_paths.add('style.input.password')
            read_only = input_style.get('read_only')
            if read_only is True:
                lines.append(f"{prefix}  .enableKeyboardOnFocus(false)")
                lines.append(f"{prefix}  .onWillChange(() => false)")
                emitted_phase_paths.add('style.input.read_only')
            elif read_only is False:
                emitted_phase_paths.add('style.input.read_only')
            action = input_style.get('ime_action')
            action_map = {'go': 'Go', 'search': 'Search', 'send': 'Send', 'next': 'Next', 'done': 'Done',
                          'default': 'NEW_LINE' if multiline_input else 'Done'}
            if multiline_input:
                action_map['none'] = 'NEW_LINE'
            if action in action_map:
                lines.append(f"{prefix}  .enterKeyType(EnterKeyType.{action_map[action]})")
                emitted_phase_paths.add('style.input.ime_action')

        measured = self._page_constraint_states.get(component['id'])
        if measured:
            padding = style['layout'].get('padding_dp') or {}
            for axis in sorted(measured['axes']):
                edges = ('left', 'right') if axis == 'width' else ('top', 'bottom')
                inset = sum(float(padding.get(edge) or 0) for edge in edges)
                size_updates.append(f"this.{measured['name']}{axis.title()} = Math.max(0, Number(current.{axis}) - {page_number(inset)})")
        if size_updates:
            lines.append(f"{prefix}  .onSizeChange((_old, current) => {{ {'; '.join(size_updates)} }})")
        scaffold_padding = (component.get('source') or {}).get('scaffold_padding')
        if isinstance(scaffold_padding, dict):
            owner = self._page_scaffold_states.get(scaffold_padding.get('owner_id'))
            edges = scaffold_padding.get('edges') or {}
            if owner and edges and set(edges.values()) <= {'topBar', 'bottomBar'}:
                padding = style['layout'].get('padding_dp') or {}
                values = []
                for edge in ('left', 'right', 'top', 'bottom'):
                    offset = page_number(padding.get(edge, 0))
                    expression = f'this.{owner}{edges[edge].title()} + {offset}' if edge in edges else offset
                    values.append(f'{edge}: {expression}')
                lines.append(f"{prefix}  .padding({{ {', '.join(values)} }})")
            else:
                self.add_page_json_unresolved(component, 'source.scaffold_padding', 'Scaffold padding owner/slot is unavailable')

        component_text = style["content"].get("text")
        if isinstance(component_text, str) and "style.content.text" not in emitted_phase_paths:
            pending_descendants = list(component.get("children_ids") or [])
            while pending_descendants:
                descendant_id = pending_descendants.pop()
                descendant = self.android_page_by_id.get(descendant_id)
                if not isinstance(descendant, dict):
                    continue
                if (
                    descendant["style"]["content"].get("text") == component_text
                    and "style.content.text"
                    in self.android_page_applied_component_paths.get(descendant_id, set())
                ):
                    emitted_phase_paths.add("style.content.text")
                    break
                pending_descendants.extend(descendant.get("children_ids") or [])

        component_color = style["typography"].get("color")
        if (
            isinstance(component_color, str)
            and "style.typography.color" not in emitted_phase_paths
            and self.page_snapshot_descendant_consumes_typography_color(
                component, component_color
            )
        ):
            emitted_phase_paths.add("style.typography.color")

        if not hasattr(self, "android_page_applied_component_paths"):
            self.android_page_applied_component_paths = defaultdict(set)
        component_applied = self.android_page_applied_component_paths[component["id"]]
        component_applied.update(
            {"bounds_dp.x", "bounds_dp.y", "bounds_dp.width", "bounds_dp.height"}
        )
        component_applied.update(emitted_phase_paths)
        component_applied.add("structure.type")
        if all(child["id"] in self.android_page_processed_component_ids for child in children):
            component_applied.add("structure.children_ids")
        if parent_component is None and component.get("parent_id") is None:
            component_applied.update({"structure.parent_id", "structure.sibling_index"})
        elif structural_parent is not None and component["id"] in structural_parent["children_ids"]:
            component_applied.add("structure.parent_id")
            if structural_parent["children_ids"].index(component["id"]) == component.get("sibling_index"):
                component_applied.add("structure.sibling_index")
        if component.get("source_layout_bounds_dp") is not None:
            component_applied.add("source_layout_bounds_dp")
        if not hasattr(self, "android_page_processed_component_ids"):
            self.android_page_processed_component_ids = set()
        self.android_page_processed_component_ids.add(component["id"])
        if component_type == 'FilterChip':
            minimum = component.get('source', {}).get('material_item', {}).get('minimum_interactive_dp')
            if type(minimum) in (int, float) and minimum > 0:
                lines = [prefix + 'Stack() {', *['  ' + line for line in lines], prefix + '}',
                    prefix + f'  .constraintSize({{ minHeight: {self.lengths.length(minimum)} }})']
            elif minimum is None:
                self.add_page_json_unresolved(component, 'source.material_item.minimum_interactive_dp', 'minimum interactive size is unresolved')
        return lines

    def render_android_page_snapshot(self) -> list[str]:
        if self.android_page_input is None:
            return []
        content_bounds = self.android_page_input["viewport"]["content_bounds_dp"]
        roots = [
            component
            for component in self.android_page_input["components"]
            if component["parent_id"] is None
        ]
        roots.sort(
            key=lambda component: (
                0 if component["style"]["content"].get("role") == "surface" else 1,
                component["sibling_index"],
                component["bounds_dp"]["y"],
                component["bounds_dp"]["x"],
            )
        )
        lines = ["  @Builder", "  private renderAndroidPageSnapshot() {", "    Stack() {"]
        for component in roots:
            lines.extend(self.page_snapshot_component_lines(component, content_bounds, None, 6))
        lines.extend([
            "    }",
            "      .width('100%')",
            "      .height('100%')",
        ])
        if "compose_theme_background" in self.resource_names:
            lines.append("      .backgroundColor($r('app.color.compose_theme_background'))")
        lines.append("  }")
        return lines

    def render(self) -> str:
        from ui_migration.arkui.component_reuse import ComponentReuseEmitter
        self.style_tokens.modules.clear()
        self.style_tokens.consumed.clear()
        self.business_components.clear()
        self.component_reuse = ComponentReuseEmitter(self.root['composable'], self.business_components)
        self.lengths.used = False
        self.surface.builders.clear()
        self._page_constraint_states.clear()
        self._page_scaffold_states: dict[str, str] = {}
        self._material_item_states: dict[str, str] = {}
        self._page_match_parent_sizes.clear()
        self._page_match_parent_builders: list[list[str]] = []
        self.typography = TypographyEmitter(FontRegistry(self.verified_font_faces), self.layout, self.add_page_json_unresolved, self.style_tokens)
        page_snapshot_section = self.render_android_page_snapshot()
        for component in self.android_page_by_id.values():
            for path in component.get('source', {}).get('style_token_references', {}):
                if (component['id'], path) not in self.style_tokens.consumed:
                    self.add_page_json_unresolved(component, 'style.' + path, 'mapped style token was not consumed by this component renderer')
        business_interfaces, business_methods = self.business_components.declarations()
        return ArkUIDocument(
            self.root, page_snapshot_section, self.verified_font_faces,
            self.surface.builders, self._page_match_parent_builders,
            self._page_scaffold_states, self._page_constraint_states,
            self._uses_drawing_color_filter, self.typography.uses_font_metrics,
            self.lengths.used,
            business_interfaces, business_methods,
            self._material_item_states,
            self.style_tokens.imports() + self.component_reuse.imports(),
        ).render()
