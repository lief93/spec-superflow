"""Native leaf creation. Shared layout and drawing stay in their own modules."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from ui_migration.arkui.formatting import page_number
from ui_migration.common import RESOURCE_NAME_PATTERN, arkts_string
from ui_migration.contracts.material_icons import material_icon_identity
from urllib.parse import urlsplit


@dataclass
class LeafResult:
    lines: list[str] = field(default_factory=list)
    consumed: set[str] = field(default_factory=set)
    image_drawn: bool = False
    tint_baked: bool = False


class NativeLeafEmitter:
    def __init__(self, resources, tinted_resources, layout, unresolved, bind=None, tint_lines=None, tokens=None):
        self.resources = resources
        self.tinted_resources = tinted_resources
        self.layout = layout
        self.unresolved = unresolved
        self.bind = bind or (lambda component, path, expression, kind='string': expression)
        self.tint_lines = tint_lines
        self.tokens = tokens
        self.handlers = {
            'Text': self.text,
            'BasicText': self.text,
            'ClickableText': self.text,
            'BasicTextField': self.input,
            'TextField': self.input,
            'OutlinedTextField': self.input,
            'Image': self.image,
            'Icon': self.image,
            'AsyncImage': self.image,
            'Checkbox': self.selection,
            'Switch': self.selection,
            'RadioButton': self.selection,
            'Slider': self.slider,
            'LinearProgressIndicator': self.progress,
            'CircularProgressIndicator': self.progress,
            'Divider': self.divider,
            'HorizontalDivider': self.divider,
            'VerticalDivider': self.divider,
            'ProgressRing': self.ring,
            'Spacer': self.spacer,
            'Canvas': self.spacer,
        }

    def supports(self, component_type: str) -> bool:
        return component_type in self.handlers

    def emit(self, component, prefix, parent_type=None) -> LeafResult:
        return self.handlers[component['type']](component, prefix, parent_type)

    def text(self, component, prefix, parent_type):
        emitted_phase_paths = set()
        reference = self.tokens.expression(component, 'content.text') if self.tokens else None
        text = self.bind(component, 'style.content.text', reference or arkts_string(component['style']['content'].get('text') or ''))
        lines = [f"{prefix}Text({text})"]
        spans = (component.get('source') or {}).get('text_spans')
        plain = component['style']['content'].get('text') or ''
        if isinstance(spans, list) and spans and not reference:
            encoded = plain.encode('utf-16-le')
            limit = len(encoded) // 2
            valid = all(isinstance(s, dict) and type(s.get('start')) is int and type(s.get('end')) is int
                        and 0 <= s['start'] <= s['end'] <= limit for s in spans)
            if valid:
                points = sorted({0, limit, *(s[k] for s in spans for k in ('start', 'end'))})
                lines = [f'{prefix}Text() {{']
                for index, (start, end) in enumerate(zip(points, points[1:])):
                    part = encoded[start*2:end*2].decode('utf-16-le')
                    value = self.bind(component, f'source.text_spans.segment{index}.text', arkts_string(part))
                    lines.append(f'{prefix}  Span({value})')
                    properties = {}
                    for span in spans:
                        if span['start'] <= start and span['end'] >= end:
                            properties.update(span.get('item', {}).get('properties', {}))
                    weight = {'FontWeight.Bold':700, 'FontWeight.Medium':500, 'FontWeight.Normal':400}.get(properties.get('fontWeight'))
                    if weight:
                        lines.append(f'{prefix}    .fontWeight({weight})')
                    if properties.get('fontStyle') == 'FontStyle.Italic':
                        lines.append(f'{prefix}    .fontStyle(FontStyle.Italic)')
                    if properties.get('textDecoration') == 'TextDecoration.Underline':
                        lines.append(f'{prefix}    .decoration({{ type: TextDecorationType.Underline }})')
                lines.append(f'{prefix}}}')
                emitted_phase_paths.add('source.text_spans')
        emitted_phase_paths.add("style.content.text")
        indent = (component.get('source') or {}).get('first_line_indent_dp')
        if type(indent) in (int, float):
            lines.append(f'{prefix}  .textIndent({self.layout.page_layout_length(indent)})')
            emitted_phase_paths.add('source.first_line_indent_dp')

        return LeafResult(lines, emitted_phase_paths)

    def input(self, component, prefix, parent_type):
        component_type = component['type']
        input_style = component['style'].get('input') or {}
        multiline_input = input_style.get('single_line') is False
        emitted_phase_paths = set()
        reference = self.tokens.expression(component, 'content.text') if self.tokens else None
        text = self.bind(component, 'style.content.text', reference or arkts_string(component['style']['content'].get('text') or ''))
        options = [f"text: {text}"]
        emitted_phase_paths.add("style.content.text")
        placeholder = component["style"]["content"].get("placeholder")
        placeholder_reference = self.tokens.expression(component, 'content.placeholder') if self.tokens else None
        if placeholder_reference is not None or isinstance(placeholder, str):
            placeholder = self.bind(component, 'style.content.placeholder', placeholder_reference or arkts_string(placeholder))
            options.append(f"placeholder: {placeholder}")
            emitted_phase_paths.add("style.content.placeholder")
        input_component = 'TextArea' if multiline_input else 'TextInput'
        lines = [f"{prefix}{input_component}({{ {', '.join(options)} }})"]
        material = (component.get('source') or {}).get('material_input')
        if material:
            length = self.layout.page_layout_length
            if not self.layout.page_snapshot_has_explicit_axis_size(component, 'width'):
                lines.append(f"{prefix}  .width({length(material['min_width_dp'])})")
            if not self.layout.page_snapshot_has_explicit_axis_size(component, 'height'):
                lines.append(f"{prefix}  .constraintSize({{ minHeight: {length(material['min_height_dp'])} }})")
            padding = material['content_padding_dp']
            lines.append(f"{prefix}  .padding({{ left: {length(padding['left'])}, right: {length(padding['right'])}, top: {length(padding['top'])}, bottom: {length(padding['bottom'])} }})")
            if material.get('label_top_inset_dp'):
                lines.append(f"{prefix}  .margin({{ top: {length(material['label_top_inset_dp'])} }})")
            if material.get('label_color'):
                lines.append(f"{prefix}  .placeholderColor({arkts_string(material['label_color'])})")
            font_size = component['style']['typography'].get('font_size_sp')
            font_weight = component['style']['typography'].get('font_weight')
            if font_size is not None and font_weight is not None:
                lines.append(f"{prefix}  .placeholderFont({{ size: {page_number(font_size)}, weight: {font_weight} }})")
            if component_type == 'TextField' and material.get('indicator_color'):
                lines.append(f"{prefix}  .border({{ width: {{ bottom: {length(material['indicator_width_dp'])} }}, color: {arkts_string(material['indicator_color'])} }})")
            emitted_phase_paths.add('source.material_input')
        if component_type == 'BasicTextField':
            lines.extend([f'{prefix}  .padding(0)', f"{prefix}  .backgroundColor('#00000000')",
                          f'{prefix}  .borderRadius(0)'])
        if input_style.get('single_line') is not None:
            emitted_phase_paths.add('style.input.single_line')

        return LeafResult(lines, emitted_phase_paths)

    def image(self, component, prefix, parent_type):
        component_type = component['type']
        emitted_phase_paths = set()
        page_tint_baked = False
        page_image_drawn = False
        page_resource = component["style"]["asset"].get("resource")
        page_tint = component["style"]["asset"].get("tint")
        media = None
        if isinstance(page_resource, str) and isinstance(page_tint, str):
            tinted_resource = self.tinted_resources.get(
                (page_resource, page_tint)
            )
            if tinted_resource is not None:
                media = f"$r('app.media.{tinted_resource}')"
                page_tint_baked = True
        material_icon = material_icon_identity(page_resource)
        if material_icon:
            page_resource = material_icon[1]
        if (
            media is None
            and isinstance(page_resource, str)
            and RESOURCE_NAME_PATTERN.fullmatch(page_resource) is not None
            and f"media:{page_resource}" in self.resources
        ):
            media = f"$r('app.media.{page_resource}')"
        if media is None:
            if component_type == "AsyncImage" and isinstance(page_resource, str):
                try:
                    uri = urlsplit(page_resource)
                    if uri.scheme in {"http", "https"} and uri.hostname and not uri.username and not uri.password:
                        media = arkts_string(page_resource)
                except ValueError:
                    pass
        if media is None:
            self.unresolved(
                component,
                "style.asset.resource",
                "page JSON image has no target-resolvable asset; source fallback is disabled",
            )
            # Unknown image content does not remove its measured/drawn surface.
            lines = [f"{prefix}Stack() {{}}"]
        else:
            media = self.bind(component, 'style.asset.resource', media, 'ResourceStr')
            lines = [f"{prefix}Image({media})"]
            page_image_drawn = True
            emitted_phase_paths.add("style.asset.resource")
            if page_tint_baked:
                emitted_phase_paths.add('style.asset.tint')
            asset = component['style']['asset']
            if asset.get('content_scale') == 'inside' and all(
                    isinstance(asset.get(axis + '_dp'), (int, float)) and asset[axis + '_dp'] > 0
                    for axis in ('width', 'height')):
                # ScaleDown uses decoded pixels; Compose Inside uses density-aware intrinsic dp.
                lines = [f'{prefix}Stack() {{', f'{prefix}  Image({media})',
                         f"{prefix}    .width({page_number(asset['width_dp'])})",
                         f"{prefix}    .height({page_number(asset['height_dp'])})",
                         f"{prefix}    .constraintSize({{ maxWidth: '100%', maxHeight: '100%' }})",
                         f'{prefix}    .objectFit(ImageFit.Contain)']
                if isinstance(page_tint, str) and not page_tint_baked and self.tint_lines:
                    lines.extend(f'{prefix}    {line}' for line in self.tint_lines(arkts_string(page_tint)))
                    emitted_phase_paths.add('style.asset.tint')
                lines.append(f'{prefix}}}')
                page_image_drawn = False
                emitted_phase_paths.update({'style.asset.content_scale', 'style.asset.width_dp', 'style.asset.height_dp'})

        return LeafResult(lines, emitted_phase_paths, page_image_drawn, page_tint_baked)

    def selection(self, component, prefix, parent_type):
        component_type = component['type']
        emitted_phase_paths = set()
        field = 'selected' if component_type == 'RadioButton' else 'checked'
        checked = component['style']['state'].get(field)
        if not isinstance(checked, bool):
            self.unresolved(component, 'style.state.' + field, 'selection state is required')
            return LeafResult()
        boolean = str(checked).lower()
        if component_type == 'Checkbox':
            lines = [f'{prefix}Checkbox()', f'{prefix}  .select({boolean})',
                     f'{prefix}  .shape(CheckBoxShape.ROUNDED_SQUARE)']
        elif component_type == 'Switch':
            lines = [f'{prefix}Toggle({{ type: ToggleType.Switch, isOn: {boolean} }})']
        else:
            key = arkts_string(component['id'])
            lines = [f'{prefix}Radio({{ value: {key}, group: {key} }})', f'{prefix}  .checked({boolean})']
        lines.extend([f'{prefix}  .margin(0)', f'{prefix}  .padding(0)'])
        emitted_phase_paths.add('style.state.' + field)
        material = (component.get('source') or {}).get('material_selection')
        if material:
            control = component['style']['control']
            active, inactive = control.get('active_color'), control.get('inactive_color')
            mark = component['style']['typography'].get('color')
            if component_type == 'Checkbox':
                for value, method in [(active, 'selectedColor'), (inactive, 'unselectedColor')]:
                    if value:
                        lines.append(f'{prefix}  .{method}({arkts_string(value)})')
                if mark:
                    lines.append(f'{prefix}  .mark({{ strokeColor: {arkts_string(mark)}, size: 16, strokeWidth: 2 }})')
            elif component_type == 'RadioButton':
                entries = [f'{name}: {arkts_string(value)}' for name, value in
                    [('checkedBackgroundColor', active), ('uncheckedBorderColor', inactive), ('indicatorColor', mark)] if value]
                lines.append(f"{prefix}  .radioStyle({{ {', '.join(entries)} }})")
            else:
                if active:
                    lines.append(f'{prefix}  .selectedColor({arkts_string(active)})')
                entries = [f'{name}: {arkts_string(value)}' for name, value in
                    [('unselectedColor', inactive), ('pointColor', mark)] if value]
                entries.append(f'pointRadius: {12 if checked else 8}')
                lines.append(f"{prefix}  .switchStyle({{ {', '.join(entries)} }})")
            length = self.layout.page_layout_length
            lines.extend([f"{prefix}  .width({length(material['width_dp'])})",
                          f"{prefix}  .height({length(material['height_dp'])})"])
            minimum = material.get('minimum_interactive_dp')
            if type(minimum) not in (int, float):
                self.unresolved(component, 'source.material_selection.minimum_interactive_dp', 'source minimum touch size is unresolved')
                minimum = 0
            lines = [f'{prefix}Stack() {{'] + ['  ' + line for line in lines] + [f'{prefix}}}',
                f"{prefix}  .width({length(max(minimum, material['width_dp']))})",
                f"{prefix}  .height({length(max(minimum, material['height_dp']))})"]
            emitted_phase_paths.update({'source.material_selection', 'style.control.active_color',
                'style.control.inactive_color', 'style.typography.color'})

        return LeafResult(lines, emitted_phase_paths)

    def slider(self, component, prefix, parent_type):
        control = component['style'].get('control') or {}
        emitted_phase_paths = set()
        value, low, high, steps = (control.get(k) for k in ('value', 'minimum', 'maximum', 'steps'))
        if any(v is None for v in (value, low, high, steps)) or high <= low or steps <= 0:
            self.unresolved(component, 'style.control.steps',
                'native Slider requires explicit discrete steps; continuous Compose slider must not become a stepped slider')
            return LeafResult()
        step = (high - low) / (steps + 1)
        if step < 0.01:
            self.unresolved(component, 'style.control.steps', 'native Slider minimum step is 0.01')
            return LeafResult()
        lines = [f'{prefix}Slider({{ value: {page_number(max(low, min(high, value)))}, min: {page_number(low)}, max: {page_number(high)}, step: {page_number(step)} }})']
        emitted_phase_paths.update('style.control.' + k for k in ('value', 'minimum', 'maximum', 'steps'))

        return LeafResult(lines, emitted_phase_paths)

    def progress(self, component, prefix, parent_type):
        component_type = component['type']
        control = component['style'].get('control') or {}
        emitted_phase_paths = set()
        value = control.get('value')
        if value is None:
            self.unresolved(component, 'style.control.value', 'indeterminate animation requires a separate renderer')
            return LeafResult()
        if control.get('minimum') != 0 or control.get('maximum') != 1:
            self.unresolved(component, 'style.control', 'Compose progress requires a normalized 0..1 range')
            return LeafResult()
        if control.get('inactive_color') and component['style']['surface'].get('background') is not None:
            self.unresolved(component, 'style.surface.background',
                'trackColor and an outer modifier background require separate draw layers')
            return LeafResult()
        shape = 'Linear' if component_type == 'LinearProgressIndicator' else 'Ring'
        lines = [f'{prefix}Progress({{ value: {page_number(max(0, min(1, value)))}, total: 1, type: ProgressType.{shape} }})']
        for field, method in [('active_color', 'color'), ('inactive_color', 'backgroundColor')]:
            reference = self.tokens.expression(component, 'control.' + field) if self.tokens else None
            if reference is not None or control.get(field):
                color = reference or arkts_string(control[field])
                lines.append(f'{prefix}  .{method}({color})')
                emitted_phase_paths.add('style.control.' + field)
        if control.get('stroke_width_dp') is not None:
            lines.append(f"{prefix}  .style({{ strokeWidth: {page_number(control['stroke_width_dp'])} }})")
            emitted_phase_paths.add('style.control.stroke_width_dp')
        material_size = (component.get('source') or {}).get('material_size')
        if material_size:
            for axis in ('width', 'height'):
                if not self.layout.page_snapshot_has_explicit_axis_size(component, axis):
                    lines.append(f"{prefix}  .{axis}({self.layout.page_layout_length(material_size[axis + '_dp'])})")
            emitted_phase_paths.add('source.material_size')
        emitted_phase_paths.update('style.control.' + k for k in ('value', 'minimum', 'maximum'))

        return LeafResult(lines, emitted_phase_paths)

    def divider(self, component, prefix, parent_type):
        component_type = component['type']
        control = component['style'].get('control') or {}
        emitted_phase_paths = set()
        lines = [f'{prefix}Divider()', f"{prefix}  .vertical({str(component_type == 'VerticalDivider').lower()})"]
        axis = 'height' if component_type == 'VerticalDivider' else 'width'
        parent = self.layout.context.components.get(component.get('parent_id'))
        if (parent and parent.get('type') == {'height': 'Row', 'width': 'Column'}[axis]
                and not self.layout.page_snapshot_has_explicit_axis_size(component, axis)):
            call_id = (parent.get('source') or {}).get('call_id')
            while parent:
                rule = self.layout.page_snapshot_axis_layout_rule(parent, axis)
                if rule and rule.get('kind') == 'intrinsic_size':
                    # A divider contributes zero to Compose's intrinsic cross-axis measure.
                    # ArkUI's default/auto length fills the constraint before stretching.
                    lines.append(f"{prefix}  .{axis}(0)")
                    lines.append(f'{prefix}  .alignSelf(ItemAlign.Stretch)')
                    break
                parent = self.layout.context.components.get(parent.get('parent_id'))
                if parent is None or not call_id or (parent.get('source') or {}).get('call_id') != call_id:
                    break
        if control.get('stroke_width_dp') is not None:
            lines.append(f"{prefix}  .strokeWidth({page_number(control['stroke_width_dp'])})")
            emitted_phase_paths.add('style.control.stroke_width_dp')
        reference = self.tokens.expression(component, 'control.active_color') if self.tokens else None
        if reference is not None or control.get('active_color'):
            color = reference or arkts_string(control['active_color'])
            lines.append(f"{prefix}  .color({color})")
            emitted_phase_paths.add('style.control.active_color')

        return LeafResult(lines, emitted_phase_paths)

    def ring(self, component, prefix, parent_type):

        custom_draw = component.get("custom_draw")
        if isinstance(custom_draw, dict):
            progress_value = page_number(float(custom_draw["value"]))
            progress_total = page_number(float(custom_draw["total"]))
        else:
            value_text = component["style"]["content"].get("text")
            match = re.fullmatch(r"(100|[0-9]{1,2})%", str(value_text or ""))
            if match is None:
                return LeafResult()
            progress_value = str(int(match.group(1)))
            progress_total = "100"
        lines = [
            f"{prefix}Progress({{ value: {progress_value}, total: {progress_total}, type: ProgressType.Ring }})"
        ]

        return LeafResult(lines, set())

    def spacer(self, component, prefix, parent_type):

        lines = [f"{prefix}Blank()"] if parent_type in {"Row", "Column", "Flex"} else [f"{prefix}Stack() {{", f"{prefix}}}"]

        return LeafResult(lines, set())
