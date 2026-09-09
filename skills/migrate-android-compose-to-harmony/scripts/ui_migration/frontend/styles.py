from __future__ import annotations
import hashlib
import re
from component_required_facts import INPUT_ARGUMENTS, INPUT_TYPES, constant_linear_gradient, font_weight_expression, input_argument_values, is_preview_only_placeholder_expression, number_expression, numeric_literal, parsed_arguments, simple_appbar_background, size_arguments
from ui_migration.frontend.shapes import CORNERS, shape_surface
from ui_migration.frontend.values import evaluate_expression
from page_snapshot import empty_style
from pathlib import Path
from typing import Any
from ui_migration.frontend.bindings import bind_source_expression, bound_modifier_call, direct_padding, first_positional_expression, modifier_dimensions, number, positional_expression, resolve_text, resolved_dp_expression, resolved_shadow_elevation, semantic_expression
from ui_migration.frontend.model import DRAWABLE_RESOURCE_PATTERN, HEX_COLOR_PATTERN, MATERIAL3_TYPOGRAPHY, RealPageError
from ui_migration.frontend.resources import android_vector_dimensions, find_resource_file


def static_style_for_call(
    call: dict[str, Any],
    values: dict[tuple[str, str], str],
    source_root: Path | None,
    parameter_bindings: dict[str, str] | None = None,
    font_family_tokens: set[str] | None = None,
    theme_colors: dict[str, str] | None = None,
    asset_index: dict[str, dict[str, Any]] | None = None,
    theme_text_styles: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, str]]]:
    call = bound_modifier_call(call, parameter_bindings)
    style = empty_style()
    provenance_paths: list[str] = []
    asset_provenance: list[dict[str, Any]] = []
    unresolved: list[dict[str, str]] = []
    component = str(call.get("component", "View"))
    if component in INPUT_TYPES:
        style['input'].update(single_line=False, read_only=False, password=False,
                              keyboard_type='text', ime_action='default')
        for name in sorted(INPUT_ARGUMENTS):
            expression = semantic_expression(call, name)
            if expression is None:
                continue
            expression = bind_source_expression(expression, parameter_bindings)
            parsed = input_argument_values(name, expression)
            if parsed is None:
                fields = {'singleLine': ['single_line'], 'readOnly': ['read_only'],
                          'visualTransformation': ['password'], 'keyboardOptions': ['keyboard_type', 'ime_action']}[name]
                for field in fields:
                    style['input'][field] = None
                    unresolved.append({'path': 'style.input.' + field, 'expression': expression,
                                       'reason': 'input argument requires an explicit supported value'})
            else:
                style['input'].update(parsed)
                provenance_paths.extend('style.input.' + field for field in parsed)
    content = style["content"]
    state = style["state"]
    role = {
        "Text": "text",
        "BasicText": "text",
        "Button": "button",
        "IconButton": "button",
        "IconToggleButton": "button",
        "FloatingActionButton": "button",
        "SmallFloatingActionButton": "button",
        "Image": "image",
        "Icon": "image",
        "TextField": "textbox",
        "OutlinedTextField": "textbox",
        "BasicTextField": "textbox",
        "Checkbox": "checkbox",
        "Switch": "switch",
    }.get(component)
    if role is not None:
        content["role"] = role
        provenance_paths.append("style.content.role")
    if component in {'TopAppBar', 'CenterAlignedTopAppBar'}:
        expression = semantic_expression(call, 'colors')
        if expression is not None:
            background = simple_appbar_background(bind_source_expression(expression, parameter_bindings))
            if background is not None:
                style['surface']['background'] = background
                provenance_paths.append('style.surface.background')
        else:
            color = (theme_colors or {}).get('surface')
            if color:
                style['surface']['background'] = {'type': 'solid', 'color': color}
                provenance_paths.append('style.surface.background')
    if component == 'BottomAppBar':
        style['layout']['alignment'] = 'CenterVertically'
        if not semantic_expression(call, 'contentPadding'):
            style['layout']['padding_dp'] = dict(left=4, right=4, top=4, bottom=0)
        expression = bind_source_expression(semantic_expression(call, 'containerColor') or
            'MaterialTheme.colorScheme.surfaceContainer', parameter_bindings)
        color = evaluate_expression(expression, {
            'MaterialTheme.colorScheme.' + key: value for key, value in (theme_colors or {}).items()})
        if isinstance(color, str):
            style['surface']['background'] = {'type': 'solid', 'color': color}
            provenance_paths.append('style.surface.background')
        else:
            unresolved.append({'path': 'style.surface.background', 'expression': expression,
                               'reason': 'bottom bar requires selected theme color'})
    if component == "Canvas" and not call.get("custom_draw_commands"):
        unresolved.append(
            {
                "path": "style.custom_draw",
                "expression": f"Canvas trailing lambda at {call['source']}:{call['line']}",
                "reason": "custom draw commands require structural extraction or a target renderer",
            }
        )
    text_expression = semantic_expression(call, "text") or (
        first_positional_expression(call) if component in {"Text", "BasicText", "ClickableText"} else None
    )
    if text_expression is not None:
        text_expression = bind_source_expression(text_expression, parameter_bindings)
        text = resolve_text(text_expression, values)
        if text is not None:
            content["text"] = text
            provenance_paths.append("style.content.text")
        else:
            unresolved.append(
                {"path": "style.content.text", "expression": text_expression, "reason": "dynamic source expression"}
            )
    description_expression = semantic_expression(call, "contentDescription") or (
        positional_expression(call, 1) if component == "Icon" else None
    )
    if description_expression is not None:
        description_expression = bind_source_expression(
            description_expression, parameter_bindings
        )
        if description_expression.strip() == "null":
            provenance_paths.append("style.content.content_description")
        else:
            description = resolve_text(description_expression, values)
            if description is not None:
                content["content_description"] = description
                provenance_paths.append("style.content.content_description")
            else:
                unresolved.append(
                    {
                        "path": "style.content.content_description",
                        "expression": description_expression,
                        "reason": "dynamic source expression",
                    }
                )
    component_color_expression = semantic_expression(call, "color")
    if isinstance(component_color_expression, str):
        component_color_expression = bind_source_expression(
            component_color_expression, parameter_bindings
        )
        component_color = HEX_COLOR_PATTERN.search(component_color_expression)
        if component_color is not None:
            style["typography"]["color"] = component_color.group(1).replace(
                "0x", "#"
            ).upper()
            provenance_paths.append("style.typography.color")
        elif component_color_expression.strip() in {"Color.Black", "Color.White"}:
            style["typography"]["color"] = (
                "#FF000000"
                if component_color_expression.strip() == "Color.Black"
                else "#FFFFFFFF"
            )
            provenance_paths.append("style.typography.color")
    resolved_text_style = ''
    if component in {"Text", "BasicText", "ClickableText", "BasicTextField", "TextField", "OutlinedTextField"}:
        font_size_expression = semantic_expression(call, "fontSize")
        if font_size_expression is not None:
            match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\.sp\s*", font_size_expression)
            if match is not None:
                style["typography"]["font_size_sp"] = number(match.group(1))
                provenance_paths.append("style.typography.font_size_sp")
        color_expression = semantic_expression(call, "color")
        if color_expression is not None:
            color_expression = bind_source_expression(
                color_expression, parameter_bindings
            )
            match = HEX_COLOR_PATTERN.search(color_expression)
            if match is not None:
                style["typography"]["color"] = match.group(1).replace("0x", "#").upper()
                provenance_paths.append("style.typography.color")
        style_expression = semantic_expression(call, "style") or semantic_expression(call, "textStyle")
        if style_expression is not None:
            style_expression = bind_source_expression(style_expression, parameter_bindings)
            if style_expression.startswith('TextStyle(') and style_expression.endswith(')'):
                positional_style, named_style = parsed_arguments(style_expression[len('TextStyle('):-1])
                style_expression = 'TextStyle(' + ', '.join([
                    *positional_style,
                    *(f'{name} = {bind_source_expression(value, parameter_bindings)}'
                      for name, value in named_style.items()),
                ]) + ')'
        if style_expression and '.copy(' in style_expression:
            from kotlin_psi import KotlinPsiSyntaxError, parse_expression
            try:
                tree = parse_expression(style_expression)
            except KotlinPsiSyntaxError as error:
                unresolved.append({'path': 'source.arguments.style', 'expression': style_expression,
                    'reason': f'local style expression cannot be parsed: {error}'})
                tree = {'kind': 'unknown'}
            if tree['kind'] == 'qualified' and tree['selector']['kind'] == 'call' and tree['selector']['callee'].get('name') == 'copy':
                base = tree['receiver']['text']
                role = base.removeprefix('MaterialTheme.typography.')
                selected = (theme_text_styles or {}).get(role, {})
                base_expression = selected.get('expression') or ''
                if not base_expression and role in MATERIAL3_TYPOGRAPHY and not selected.get('unresolved_reason'):
                    from ui_migration.frontend.model import material3_text_metrics
                    style['typography'].update(material3_text_metrics(role))
                    size, height, weight = MATERIAL3_TYPOGRAPHY[role]
                    base_expression = f'TextStyle(fontSize = {size}.sp, lineHeight = {height}.sp, fontWeight = FontWeight({weight}))'
                if base_expression.startswith('TextStyle(') and base_expression.endswith(')'):
                    _, merged = parsed_arguments(base_expression[10:-1])
                    merged.update({a['name']: bind_source_expression(a['value']['text'], parameter_bindings)
                                   for a in tree['selector']['arguments'] if a.get('name')})
                    style_expression = 'TextStyle(' + ', '.join(f'{k} = {v}' for k, v in merged.items()) + ')'
        theme_role = re.fullmatch(r"MaterialTheme\.typography\.(\w+)", style_expression or "")
        if theme_role and theme_role.group(1) in (theme_text_styles or {}):
            selected_style = theme_text_styles[theme_role.group(1)]
            expression = selected_style.get("expression") if isinstance(selected_style, dict) else None
            if not isinstance(expression, str) or not expression.startswith("TextStyle("):
                unresolved.append({'path': 'source.arguments.style', 'expression': style_expression,
                    'reason': f"project typography {theme_role.group(1)} needs a resolved TextStyle"})
            else:
                style_expression = expression
        resolved_text_style = style_expression or ''
        if style_expression is not None:
            typography_patterns = {
                "font_size_sp": r"\bfontSize\s*=\s*([0-9]+(?:\.[0-9]+)?)\.sp\b",
                "line_height_sp": r"\blineHeight\s*=\s*([0-9]+(?:\.[0-9]+)?)\.sp\b",
            }
            for field, pattern in typography_patterns.items():
                match = re.search(pattern, style_expression)
                if match is not None:
                    style["typography"][field] = number(match.group(1))
                    provenance_paths.append(f"style.typography.{field}")
            weight_match = re.search(
                r"\bfontWeight\s*=\s*FontWeight(?:\(\s*([1-9][0-9]{2})\s*\)|\.(Normal|Medium|SemiBold|Bold))",
                style_expression,
            )
            if weight_match is not None:
                named_weights = {"Normal": 400, "Medium": 500, "SemiBold": 600, "Bold": 700}
                style["typography"]["font_weight"] = (
                    int(weight_match.group(1))
                    if weight_match.group(1) is not None
                    else named_weights[weight_match.group(2)]
                )
                provenance_paths.append("style.typography.font_weight")
            color_match = HEX_COLOR_PATTERN.search(style_expression)
            if color_match is not None:
                style["typography"]["color"] = color_match.group(1).replace("0x", "#").upper()
                provenance_paths.append("style.typography.color")
            elif re.search(r'\bcolor\s*=\s*Color\.(White|Black)\b', style_expression):
                color_name = re.search(r'\bcolor\s*=\s*Color\.(White|Black)\b', style_expression).group(1)
                style['typography']['color'] = '#FFFFFFFF' if color_name == 'White' else '#FF000000'
                provenance_paths.append('style.typography.color')
            family_match = re.search(
                r"\bfontFamily\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\b",
                style_expression,
            )
            if (
                family_match is not None
                and family_match.group(1) in (font_family_tokens or set())
            ):
                style["typography"]["font_family"] = family_match.group(1)
                provenance_paths.append("style.typography.font_family")
        font_family_expression = semantic_expression(call, "fontFamily")
        if (
            isinstance(font_family_expression, str)
            and font_family_expression.strip() in (font_family_tokens or set())
        ):
            style["typography"]["font_family"] = font_family_expression.strip()
            provenance_paths.append("style.typography.font_family")
        style_name = style_expression.rsplit(".", 1)[-1] if style_expression else None
        if style_name in MATERIAL3_TYPOGRAPHY and not (theme_text_styles or {}).get(style_name, {}).get('unresolved_reason'):
            from ui_migration.frontend.model import material3_text_metrics
            style['typography'].update(material3_text_metrics(style_name))
            font_size, line_height, font_weight = MATERIAL3_TYPOGRAPHY[style_name]
            style["typography"].update(
                {
                    "font_size_sp": font_size,
                    "line_height_sp": line_height,
                    "font_weight": font_weight,
                }
            )
            provenance_paths.extend(
                (
                    "style.typography.font_size_sp",
                    "style.typography.line_height_sp",
                    "style.typography.font_weight",
                )
            )
        # Explicit Text parameters override values inherited from TextStyle.
        # Parse them after the style so the canonical facts retain Compose's
        # actual precedence instead of silently keeping a theme default.
        direct_font_size = semantic_expression(call, "fontSize")
        if isinstance(direct_font_size, str):
            match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\.sp\s*", direct_font_size)
            if match is not None:
                style["typography"]["font_size_sp"] = number(match.group(1))
                provenance_paths.append("style.typography.font_size_sp")
        direct_line_height = semantic_expression(call, "lineHeight")
        if isinstance(direct_line_height, str):
            match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\.sp\s*", direct_line_height)
            if match is not None:
                style["typography"]["line_height_sp"] = number(match.group(1))
                provenance_paths.append("style.typography.line_height_sp")
        direct_font_weight = semantic_expression(call, "fontWeight")
        if isinstance(direct_font_weight, str):
            weight = font_weight_expression(direct_font_weight)
            if weight is not None:
                style["typography"]["font_weight"] = weight
                provenance_paths.append("style.typography.font_weight")
        direct_color = semantic_expression(call, "color")
        if isinstance(direct_color, str):
            direct_color = bind_source_expression(direct_color, parameter_bindings)
            match = HEX_COLOR_PATTERN.search(direct_color)
            if match is not None:
                style["typography"]["color"] = match.group(1).replace("0x", "#").upper()
                provenance_paths.append("style.typography.color")
            elif direct_color.strip() in {"Color.Black", "Color.White"}:
                style["typography"]["color"] = (
                    "#FF000000" if direct_color.strip() == "Color.Black" else "#FFFFFFFF"
                )
                provenance_paths.append("style.typography.color")
        direct_text_align = semantic_expression(call, "textAlign")
        if isinstance(direct_text_align, str):
            text_align = {
                "TextAlign.Start": "start",
                "TextAlign.Center": "center",
                "TextAlign.End": "end",
                "TextAlign.Justify": "justify",
            }.get(direct_text_align.strip())
            if text_align is not None:
                style["typography"]["text_align"] = text_align
                provenance_paths.append("style.typography.text_align")
        max_lines_expression = semantic_expression(call, "maxLines")
        if isinstance(max_lines_expression, str):
            match = re.fullmatch(r"\s*([1-9][0-9]*)\s*", max_lines_expression)
            if match is not None:
                style["typography"]["max_lines"] = int(match.group(1))
                provenance_paths.append("style.typography.max_lines")
        overflow_expression = semantic_expression(call, "overflow")
        if isinstance(overflow_expression, str):
            overflow = {
                "TextOverflow.Clip": "clip",
                "TextOverflow.Ellipsis": "ellipsis",
                "TextOverflow.Visible": "visible",
            }.get(overflow_expression.strip())
            if overflow is not None:
                style["typography"]["overflow"] = overflow
                provenance_paths.append("style.typography.overflow")
        decoration_expression = semantic_expression(call, "textDecoration")
        if isinstance(decoration_expression, str):
            decoration = {
                "TextDecoration.None": "none",
                "TextDecoration.Underline": "underline",
                "TextDecoration.LineThrough": "line_through",
            }.get(decoration_expression.strip())
            if decoration is not None:
                style["typography"]["decoration"] = decoration
                provenance_paths.append("style.typography.decoration")
    _, style_arguments = parsed_arguments(resolved_text_style[10:-1]) if (
        resolved_text_style.startswith('TextStyle(') and resolved_text_style.endswith(')')
    ) else ([], {})
    for argument, field, parser in (
        ("fontStyle", "font_style", lambda value: {"FontStyle.Italic": "italic", "FontStyle.Normal": "normal"}.get(value)),
        ("letterSpacing", "letter_spacing_sp", lambda value: number_expression(value, 'sp')),
        ("fontSize", "font_size_sp", lambda value: number_expression(value, 'sp')),
        ("lineHeight", "line_height_sp", lambda value: number_expression(value, 'sp')),
        ("fontWeight", "font_weight", font_weight_expression),
        ("textAlign", "text_align", lambda value: {'TextAlign.Start': 'start', 'TextAlign.Center': 'center', 'TextAlign.End': 'end', 'TextAlign.Justify': 'justify'}.get(value)),
        ("textDecoration", "decoration", lambda value: {'TextDecoration.None': 'none', 'TextDecoration.Underline': 'underline', 'TextDecoration.LineThrough': 'line_through'}.get(value)),
    ):
        expression = semantic_expression(call, argument) or style_arguments.get(argument)
        if expression is not None:
            expression = bind_source_expression(expression, parameter_bindings).strip()
            parsed = parser(expression)
            path = f"style.typography.{field}"
            style["typography"][field] = parsed
            if parsed is not None:
                provenance_paths.append(path)
            else:
                unresolved.append({"path": path, "expression": expression, "reason": "unresolved explicit text attribute"})
    if component in {"BasicTextField", "TextField", "OutlinedTextField"} and content.get("text") is None:
        expression = semantic_expression(call, "value")
        if expression is not None:
            expression = bind_source_expression(expression, parameter_bindings)
            content["text"] = resolve_text(expression, values)
            if content["text"] is not None:
                provenance_paths.append("style.content.text")
            else:
                unresolved.append({"path": "style.content.text", "expression": expression, "reason": "unresolved input value"})
    placeholder_expression = semantic_expression(call, "placeholder")
    if (
        placeholder_expression is not None
        and not is_preview_only_placeholder_expression(placeholder_expression)
    ):
        placeholder_expression = bind_source_expression(
            placeholder_expression, parameter_bindings
        )
        placeholder = resolve_text(placeholder_expression, values)
        if placeholder is not None:
            content["placeholder"] = placeholder
            provenance_paths.append("style.content.placeholder")
        else:
            unresolved.append(
                {
                    "path": "style.content.placeholder",
                    "expression": placeholder_expression,
                    "reason": "slot or dynamic source expression",
                }
            )
    from page_native_controls import CONTROL_TYPES, arguments_for, defaults_for, parse_argument
    if component in CONTROL_TYPES:
        style['control'].update(defaults_for(component))
        provenance_paths.extend('style.control.' + field for field in defaults_for(component))
        for argument in arguments_for(component):
            expression = semantic_expression(call, argument)
            if expression is None:
                continue
            expression = bind_source_expression(expression, parameter_bindings)
            parsed = parse_argument(argument, expression)
            if parsed is None:
                for field in {'valueRange': ('minimum', 'maximum'), 'steps': ('steps',)}.get(argument, ()):
                    style['control'][field] = None
                unresolved.append({'path': 'source.arguments.' + argument.lower(), 'expression': expression,
                                   'reason': 'control argument requires a resolved constant'})
            else:
                style['control'].update(parsed)
                provenance_paths.extend('style.control.' + field for field in parsed)
        # Color on these primitives paints their track/stroke, not text.
        style['typography']['color'] = None
        provenance_paths = [p for p in provenance_paths if p != 'style.typography.color']
    if component in {'Text', 'BasicText', 'ClickableText', 'TextField', 'BasicTextField', 'OutlinedTextField'}:
        for argument, field, parser in (
            ('softWrap', 'soft_wrap', lambda v: {'true': True, 'false': False}.get(v)),
            ('minLines', 'min_lines', lambda v: int(v) if re.fullmatch(r'[1-9][0-9]*', v) else None),
        ):
            expression = semantic_expression(call, argument)
            if expression is not None:
                parsed = parser(bind_source_expression(expression, parameter_bindings).strip())
                style['typography'][field] = parsed
                if parsed is not None:
                    provenance_paths.append('style.typography.' + field)
                else:
                    unresolved.append({'path': 'style.typography.' + field, 'expression': expression,
                                       'reason': 'text layout argument requires a resolved constant'})
    clickable = component in {
        "Button", "IconButton", "IconToggleButton", "FloatingActionButton", "SmallFloatingActionButton"
    } or semantic_expression(call, "onClick") is not None
    state["clickable"] = clickable
    state["enabled"] = True
    state["visible"] = True
    provenance_paths.extend(("style.state.clickable", "style.state.enabled", "style.state.visible"))
    state_arguments = {field: field for field in ("enabled", "visible", "selected", "checked")}
    if component == 'PullToRefreshBox':
        state_arguments['refreshing'] = 'isRefreshing'
        for field, role in (('active_color', 'onSurfaceVariant'), ('inactive_color', 'surfaceContainerHigh')):
            color = (theme_colors or {}).get(role)
            if color:
                style['control'][field] = color
                provenance_paths.append('style.control.' + field)
    for field, argument in state_arguments.items():
        expression = semantic_expression(call, argument)
        if expression is None:
            continue
        expression = bind_source_expression(expression, parameter_bindings).strip()
        state[field] = {"true": True, "false": False}.get(expression)
        path = f"style.state.{field}"
        if state[field] is not None:
            provenance_paths.append(path)
        else:
            provenance_paths = [item for item in provenance_paths if item != path]
            unresolved.append({"path": path, "expression": expression, "reason": "unresolved explicit state"})
    if component in {"Button", "IconButton", "FloatingActionButton", "SmallFloatingActionButton", "Card"}:
        style["surface"]["clip"] = True
        provenance_paths.append("style.surface.clip")

    if component in {'Button', 'TextButton', 'OutlinedButton', 'DecorationBox', 'Card', 'Surface', 'Scaffold'}:
        border_expression = semantic_expression(call, 'border')
        if border_expression:
            border_expression = bind_source_expression(border_expression, parameter_bindings)
            border = evaluate_expression(border_expression, {})
            if isinstance(border, dict) and border.get('kind') == 'border_stroke':
                style['surface']['border'] = {k: v for k, v in border.items() if k != 'kind'}
                provenance_paths.append('style.surface.border')
            elif border is not None:
                unresolved.append({'path': 'style.surface.border', 'expression': border_expression,
                                   'reason': 'border requires the selected width and color'})
        def surface_color(expression: str | None) -> str | None:
            expression = bind_source_expression(expression or '', parameter_bindings).strip()
            constant = {'Color.White': '#FFFFFFFF', 'Color.Black': '#FF000000',
                        'Color.Transparent': '#00000000'}.get(expression)
            if constant:
                return constant
            role = re.fullmatch(r'MaterialTheme\.colorScheme\.(\w+)', expression)
            if role:
                return (theme_colors or {}).get(role.group(1))
            match = re.fullmatch(r'Color\(\s*0x([0-9A-Fa-f]{8})\s*\)|#([0-9A-Fa-f]{8})', expression)
            return '#' + (match.group(1) or match.group(2)).upper() if match else None

        if component in ('Surface', 'Scaffold'):
            for argument, group, field, default in (
                ('color' if component == 'Surface' else 'containerColor', 'surface', 'background',
                 'MaterialTheme.colorScheme.surface' if component == 'Surface' else 'MaterialTheme.colorScheme.background'),
                ('contentColor', 'typography', 'color',
                 'LocalContentColor.current' if component == 'Surface' else 'MaterialTheme.colorScheme.onBackground'),
            ):
                expression = bind_source_expression(semantic_expression(call, argument) or default, parameter_bindings)
                color = surface_color(expression)
                if color:
                    style[group][field] = {'type': 'solid', 'color': color} if field == 'background' else color
                    provenance_paths.append(f'style.{group}.{field}')
                else:
                    unresolved.append({'path': f'style.{group}.{field}', 'expression': expression,
                                       'reason': 'surface paint requires a resolved color'})
        colors_expression = bind_source_expression(semantic_expression(call, 'colors') or
            {'Card': 'CardDefaults.cardColors()', 'Button': 'ButtonDefaults.buttonColors()',
             'TextButton': 'ButtonDefaults.textButtonColors()',
             'OutlinedButton': 'ButtonDefaults.outlinedButtonColors()'}.get(component, ''), parameter_bindings)
        color_factory = re.fullmatch(r'(?:ButtonDefaults|OutlinedTextFieldDefaults|TextFieldDefaults|CardDefaults)\.(\w+)\((.*)\)',
                                     colors_expression, re.DOTALL)
        if color_factory:
            _, colors = parsed_arguments(color_factory.group(2))
            enabled_expression = bind_source_expression(semantic_expression(call, 'enabled') or 'true', parameter_bindings)
            enabled = style['state'].get('enabled')
            roles = {'Button': ('primary', 'onPrimary'), 'TextButton': (None, 'primary'),
                     'OutlinedButton': (None, 'primary')}
            for path, property_name in [('style.surface.background', 'ContainerColor'),
                                        ('style.typography.color', 'ContentColor')]:
                normal_key = property_name[0].lower() + property_name[1:]
                if component == 'DecorationBox':
                    normal_key = 'unfocusedContainerColor' if property_name == 'ContainerColor' else 'unfocusedTextColor'
                active = surface_color(colors.get(normal_key))
                inactive = surface_color(colors.get('disabled' + property_name))
                if component == 'Card' and property_name == 'ContainerColor' and normal_key not in colors:
                    active = (theme_colors or {}).get('surfaceContainerHighest')
                if component in roles:
                    role = roles[component][0 if property_name == 'ContainerColor' else 1]
                    if active is None and normal_key not in colors:
                        active = (theme_colors or {}).get(role) if role else '#00000000'
                    on_surface = (theme_colors or {}).get('onSurface')
                    if inactive is None and 'disabled' + property_name not in colors and on_surface:
                        # Material 3 ButtonDefaults: disabled container/content alpha.
                        alpha = '1F' if property_name == 'ContainerColor' else '61'
                        inactive = (f'#{alpha}{on_surface[-6:]}' if role or property_name == 'ContentColor'
                                    else '#00000000')
                if component == 'Card' and property_name == 'ContentColor' and normal_key not in colors:
                    container = surface_color(colors.get('containerColor')) if 'containerColor' in colors else (theme_colors or {}).get('surfaceContainerHighest')
                    content_role = next((on_role for role, on_role in (
                        ('primary', 'onPrimary'), ('secondary', 'onSecondary'), ('tertiary', 'onTertiary'),
                        ('background', 'onBackground'), ('surface', 'onSurface'),
                        ('surfaceContainerHighest', 'onSurface'))
                        if container is not None and (theme_colors or {}).get(role) == container), None)
                    active = (theme_colors or {}).get(content_role)
                color = active if enabled is True else inactive if enabled is False else None
                if color is not None:
                    section, field = path.split('.')[1:]
                    style[section][field] = {'type': 'solid', 'color': color} if field == 'background' else color
                    provenance_paths.append(path)
                elif active and inactive:
                    unresolved.append({'path': path, 'expression': f'if ({enabled_expression}) {{ "{active}" }} else {{ "{inactive}" }}',
                                       'reason': 'surface depends on the selected static enabled state'})
                elif enabled is True and normal_key in colors:
                    unresolved.append({'path': path, 'expression': colors[normal_key],
                                       'reason': 'surface color depends on the selected source input'})
        shape_expression = semantic_expression(call, 'shape')
        if component == 'Card':
            elevation = bind_source_expression(semantic_expression(call, 'elevation') or 'CardDefaults.cardElevation()', parameter_bindings)
            if elevation not in {'CardDefaults.cardElevation()', 'CardDefaults.cardElevation(defaultElevation = 0.dp)'}:
                unresolved.append({'path': 'source.arguments.elevation', 'expression': elevation,
                                   'reason': 'non-default Material elevation needs a verified shadow mapping; content is retained'})
            shape_expression = shape_expression or 'RoundedCornerShape(12.dp)'
        if component == 'DecorationBox' and not shape_expression:
            container = semantic_expression(call, 'container') or ''
            match = re.fullmatch(r'\s*\{\s*OutlinedTextFieldDefaults\.ContainerBox\((.*)\)\s*\}\s*', container, re.DOTALL)
            if match:
                positional, named = parsed_arguments(match.group(1))
                shape_expression = named.get('shape') or (positional[4] if len(positional) > 4 else None)
                if color_factory:
                    # Material 3 OutlinedTextFieldDefaults.ContainerBox, initial unfocused state.
                    thickness = named.get('unfocusedBorderThickness') or (positional[6] if len(positional) > 6 else '1.dp')
                    width = re.fullmatch(r'([0-9]+(?:\.[0-9]+)?)\.dp', bind_source_expression(thickness, parameter_bindings))
                    normal = surface_color(colors.get('unfocusedIndicatorColor'))
                    error = surface_color(colors.get('errorIndicatorColor')) or (theme_colors or {}).get('error')
                    disabled = surface_color(colors.get('disabledIndicatorColor'))
                    error_expression = bind_source_expression(semantic_expression(call, 'isError') or 'false', parameter_bindings)
                    selected = (disabled if enabled is False else
                                error if enabled is True and error_expression == 'true' else
                                normal if enabled is True and error_expression == 'false' else None)
                    if width:
                        style['surface']['border'] = dict(width_dp=number(width.group(1)), color=selected, style='solid')
                        provenance_paths.extend(('style.surface.border.width_dp', 'style.surface.border.style'))
                        if selected:
                            provenance_paths.append('style.surface.border.color')
                        else:
                            expression = (f'if ({error_expression}) {{ "{error}" }} else {{ "{normal}" }}'
                                          if enabled is True and normal and error else 'unresolved outlined border state')
                            unresolved.append({'path': 'style.surface.border.color', 'expression': expression,
                                               'reason': 'outlined border color requires the selected enabled/error state'})
        if shape_expression:
            bound_shape = bind_source_expression(shape_expression, parameter_bindings)
            shape = shape_surface(evaluate_expression(bound_shape, {}), style['layout'].get('layout_direction'),
                                  [style['layout'].get(axis + '_dp') for axis in ('width', 'height')])
            if shape is not None:
                style['surface'].update(shape)
                provenance_paths.extend('style.surface.' + key for key, value in shape.items() if value is not None)
            else:
                unresolved.append({'path': 'style.surface.corner_radius_dp', 'expression': bound_shape,
                                   'reason': 'native shape requires resolved corner values'})

    semantic_arguments = call.get("semantic_arguments")
    content_padding_argument = (
        semantic_arguments.get("contentPadding")
        if isinstance(semantic_arguments, dict)
        else None
    )
    if isinstance(content_padding_argument, dict):
        padding_expression = content_padding_argument.get("expression")
        dimensions = modifier_dimensions(content_padding_argument)
        if isinstance(padding_expression, str):
            padding = direct_padding(padding_expression, dimensions)
            resolved = evaluate_expression(bind_source_expression(padding_expression, parameter_bindings), {})
            if isinstance(resolved, dict) and resolved.get('kind') == 'padding_values':
                edges = resolved['edges']
                padding = {'left': edges['start'], 'top': edges['top'], 'right': edges['end'], 'bottom': edges['bottom']}
            if padding is not None:
                style["layout"]["padding_dp"] = padding
                provenance_paths.append("style.layout.padding_dp")

    alignment_expression = (
        semantic_expression(call, "contentAlignment")
        or semantic_expression(call, "alignment")
        or semantic_expression(call, "horizontalAlignment")
        or semantic_expression(call, "verticalAlignment")
    )
    if alignment_expression is not None:
        alignment = alignment_expression.strip().rsplit(".", 1)[-1]
        if alignment in {
            "TopStart", "TopCenter", "TopEnd",
            "CenterStart", "Center", "CenterEnd",
            "BottomStart", "BottomCenter", "BottomEnd",
        }:
            style["layout"]["alignment"] = alignment
            provenance_paths.append("style.layout.alignment")
        elif alignment in {"Start", "CenterHorizontally", "End", "Top", "CenterVertically", "Bottom"}:
            style["layout"]["alignment"] = alignment
            provenance_paths.append("style.layout.alignment")

    for semantic_name, style_field in (
        ("horizontalArrangement", "horizontal_arrangement"),
        ("verticalArrangement", "vertical_arrangement"),
    ):
        arrangement_expression = semantic_expression(call, semantic_name)
        if isinstance(arrangement_expression, str):
            style["layout"][style_field] = arrangement_expression.strip()
            provenance_paths.append(f"style.layout.{style_field}")

    painter_expression = (
        semantic_expression(call, "painter")
        or semantic_expression(call, "imageVector")
        or semantic_expression(call, "model")
        or (first_positional_expression(call) if component in {"Icon", "Image"} else None)
    )
    tint_expression = semantic_expression(call, 'tint')
    if tint_expression is not None:
        tint_expression = bind_source_expression(tint_expression, parameter_bindings).strip()
        color = HEX_COLOR_PATTERN.fullmatch(tint_expression.removeprefix('Color(').removesuffix(')'))
        tint = color.group(1).replace('0x', '#').upper() if color else {
            'Color.Black': '#FF000000', 'Color.White': '#FFFFFFFF',
            'Color.Transparent': '#00000000',
        }.get(tint_expression)
        style['asset']['tint'] = tint
        if tint is not None or tint_expression == 'Color.Unspecified':
            provenance_paths.append('style.asset.tint')
        else:
            unresolved.append({'path': 'style.asset.tint', 'expression': tint_expression, 'reason': 'unresolved tint color'})
    if painter_expression is not None:
        painter_expression = bind_source_expression(
            painter_expression, parameter_bindings
        )
        match = DRAWABLE_RESOURCE_PATTERN.search(painter_expression)
        if match is not None:
            resource = match.group(1)
            style["asset"]["resource"] = resource
            provenance_paths.append("style.asset.resource")
            file = find_resource_file(source_root, resource)
            if file is not None:
                style["asset"]["sha256"] = hashlib.sha256(file.read_bytes()).hexdigest()
                provenance_paths.append("style.asset.sha256")
                intrinsic_size = android_vector_dimensions(file)
                if intrinsic_size is not None:
                    style["asset"]["width_dp"], style["asset"]["height_dp"] = intrinsic_size
                    provenance_paths.extend(
                        ("style.asset.width_dp", "style.asset.height_dp")
                    )
            elif resource in (asset_index or {}):
                evidence = asset_index[resource]
                style["asset"]["sha256"] = evidence["sha256"]
                provenance_paths.append("style.asset.sha256")
                if isinstance(evidence.get("width_dp"), (int, float)):
                    style["asset"]["width_dp"] = evidence["width_dp"]
                    provenance_paths.append("style.asset.width_dp")
                if isinstance(evidence.get("height_dp"), (int, float)):
                    style["asset"]["height_dp"] = evidence["height_dp"]
                    provenance_paths.append("style.asset.height_dp")
                asset_provenance.append(
                    {
                        "paths": ["style.asset.sha256"],
                        "origin": "source_resolved",
                        "source": evidence["path"],
                    }
                )
        elif "Icons." in painter_expression:
            style["asset"]["resource"] = painter_expression.strip()
            provenance_paths.append("style.asset.resource")
            from ui_migration.contracts.material_icons import material_icon_identity
            if material_icon_identity(painter_expression.strip()):
                style['asset']['width_dp'] = 24
                style['asset']['height_dp'] = 24
                provenance_paths.extend(('style.asset.width_dp', 'style.asset.height_dp'))
        else:
            unresolved.append(
                {"path": "style.asset.resource", "expression": painter_expression, "reason": "dynamic source expression"}
            )
        content_scale = semantic_expression(call, "contentScale")
        content_scale_name = content_scale.rsplit(".", 1)[-1].lower() if content_scale else "fit"
        style["asset"]["content_scale"] = {
            "fit": "fit",
            "crop": "crop",
            "fillbounds": "fill",
            "inside": "inside",
            "none": "none",
        }.get(content_scale_name)
        if style["asset"]["content_scale"] is not None:
            provenance_paths.append("style.asset.content_scale")

    style_modifiers = []
    for modifier in call.get('ordered_modifier_chain', []):
        style_modifiers.append(modifier)
        if isinstance(modifier, dict) and modifier.get('name') == 'then':
            from analyze_compose_project import ordered_modifier_chain
            style_modifiers.extend(ordered_modifier_chain(bind_source_expression(
                str(modifier.get('arguments') or ''), parameter_bindings)))
    for modifier in style_modifiers:
        if not isinstance(modifier, dict) or not isinstance(modifier.get("name"), str):
            continue
        name = modifier["name"]
        arguments = str(modifier.get("arguments", ""))
        dimensions = modifier_dimensions(modifier)
        dp_values = [value for value, unit in dimensions if unit == "dp"]
        shadow_elevation = resolved_shadow_elevation(arguments, parameter_bindings)
        if name == 'shadow':
            positional, named = parsed_arguments(arguments)
            elevation = named.get('elevation') or (positional[0] if positional else None)
            shadow_elevation = resolved_dp_expression(elevation, parameter_bindings or {}) if elevation else None
        if shadow_elevation is not None:
            style["surface"]["shadows"] = [{
                "color": "#1A000000",
                "offset_x_dp": 0.0,
                "offset_y_dp": round(shadow_elevation * 0.2, 3),
                "blur_radius_dp": shadow_elevation,
                "spread_radius_dp": 0.0,
            }]
            provenance_paths.append("style.surface.shadows")
        size_section = style["layout"]
        size_prefix = "style.layout"
        if name == "size":
            bindings = {**(parameter_bindings or {}), **(call.get('local_values') or {})}
            for axis, value in zip(("width", "height"), size_arguments(arguments, bindings)):
                if value is not None:
                    size_section[f"{axis}_dp"] = value
                    provenance_paths.append(f"{size_prefix}.{axis}_dp")
        elif name in {"width", "requiredWidth", "height", "requiredHeight"}:
            axis = 'width' if name in {'width', 'requiredWidth'} else 'height'
            bindings = {**(parameter_bindings or {}), **(call.get('local_values') or {})}
            value = resolved_dp_expression(arguments, bindings)
            path = f'{size_prefix}.{axis}_dp'
            if value is not None:
                size_section[f'{axis}_dp'] = value
                provenance_paths.append(path)
            elif not re.fullmatch(r'IntrinsicSize\.(?:Min|Max)', arguments.strip()):
                unresolved.append({'path': path, 'expression': arguments,
                                   'reason': 'dimension depends on the selected source input'})
        elif name == "padding":
            padding = direct_padding(arguments, dimensions)
            if padding is not None:
                style["layout"]["padding_dp"] = padding
                provenance_paths.append("style.layout.padding_dp")
        elif name == "aspectRatio":
            match = re.search(r"-?[0-9]+(?:\.[0-9]+)?", arguments)
            if match is not None:
                style["layout"]["aspect_ratio"] = number(match.group(0))
                provenance_paths.append("style.layout.aspect_ratio")
        elif name == "alpha":
            match = re.search(r"[0-9]+(?:\.[0-9]+)?", arguments)
            if match is not None:
                style["surface"]["alpha"] = number(match.group(0))
                provenance_paths.append("style.surface.alpha")
        elif name in {"rotate", "scale"}:
            positional, named = parsed_arguments(arguments)
            common = named.get("scale") or (positional[0] if len(positional) == 1 else None)
            expressions = {"rotation_degrees": named.get("degrees") or common} if name == "rotate" else {
                f"scale_{axis}": named.get(f"scale{axis.upper()}") or
                (positional[index] if len(positional) > 1 else common)
                for index, axis in enumerate(("x", "y"))
            }
            for field, expression in expressions.items():
                value = numeric_literal(expression)
                style["transform"][field] = value
                path = f"style.transform.{field}"
                if value is not None:
                    provenance_paths.append(path)
                else:
                    unresolved.append({"path": path, "expression": arguments, "reason": "unresolved transform"})
        elif name == "background":
            match = HEX_COLOR_PATTERN.search(arguments)
            if 'Brush.' in arguments:
                positional, named = parsed_arguments(arguments)
                brush = named.get('brush') or (positional[0] if len(positional) == 1 else '')
                gradient = constant_linear_gradient(brush) if not (set(named) - {'brush'}) else None
                style['surface']['background'] = gradient
                if gradient is not None:
                    provenance_paths.append('style.surface.background')
                else:
                    unresolved.append({'path': 'style.surface.background', 'expression': arguments,
                                       'reason': 'gradient endpoints, colors or brush kind are not resolved'})
            elif match is not None:
                raw = match.group(1).replace("0x", "#")
                style["surface"]["background"] = {"type": "solid", "color": raw.upper()}
                provenance_paths.append("style.surface.background")
            elif (
                match := re.fullmatch(
                    r"MaterialTheme\.colorScheme\.([A-Za-z_][A-Za-z0-9_]*)",
                    arguments.strip(),
                )
            ) and match.group(1) in (theme_colors or {}):
                style["surface"]["background"] = {
                    "type": "solid",
                    "color": theme_colors[match.group(1)],
                }
                provenance_paths.append("style.surface.background")
            elif arguments:
                unresolved.append(
                    {"path": "style.surface.background", "expression": arguments, "reason": "theme or dynamic source expression"}
                )
        elif name == "clip":
            positional, named = parsed_arguments(arguments)
            shape_expression = named.get('shape') or (positional[0] if positional else '')
            shape = shape_surface(evaluate_expression(shape_expression, {}), style['layout'].get('layout_direction'),
                                  [style['layout'].get(axis + '_dp') for axis in ('width', 'height')])
            if shape is not None:
                style['surface'].update(shape)
                style["surface"]["clip"] = True
                provenance_paths.append("style.surface.clip")
                provenance_paths.extend('style.surface.' + key for key, value in shape.items() if value is not None)
            else:
                unresolved.append({'path': 'style.surface.clip', 'expression': arguments,
                                   'reason': 'shape needs resolved corners and layout direction'})
        elif name == "border":
            positional, named = parsed_arguments(arguments)
            stroke_expression = named.get('border') or (positional[0] if positional else '')
            stroke = evaluate_expression(stroke_expression, {})
            if isinstance(stroke, dict) and stroke.get('kind') == 'border_stroke':
                positional = [f"{stroke['width_dp']:g}.dp", f"Color(0x{stroke['color'][1:]})", *positional[1:]]
            width_expression = named.get('width') or (positional[0] if positional else None)
            color_expression = named.get('color') or (positional[1] if len(positional) > 1 else None)
            border_values = {'MaterialTheme.colorScheme.' + key: color for key, color in (theme_colors or {}).items()}
            width = resolved_dp_expression(width_expression or '', parameter_bindings or {})
            border_color = evaluate_expression(color_expression or '', border_values)
            if width is not None and width >= 0 and isinstance(border_color, str) and re.fullmatch(r'#[0-9A-Fa-f]{8}', border_color):
                style['surface']['border'] = {'width_dp': width, 'color': border_color, 'style': 'solid'}
                provenance_paths.append('style.surface.border')
            else:
                unresolved.append({'path': 'style.surface.border', 'expression': arguments,
                                   'reason': 'border requires a resolved dp width and color'})
            shape_expression = named.get('shape') or (positional[2] if len(positional) > 2 else None)
            if shape_expression:
                shape = shape_surface(evaluate_expression(shape_expression, {}), style['layout'].get('layout_direction'))
                if shape:
                    style['surface'].update(shape)
                    provenance_paths.extend('style.surface.' + key for key, value in shape.items() if value is not None)
                else:
                    unresolved.append({'path': 'style.surface.corner_radius_dp', 'expression': shape_expression,
                                       'reason': 'border shape requires resolved corners'})
        elif name == "dashedBorder" or (name == "then" and "dashedBorder" in arguments):
            width = re.search(
                r"strokeWidth\s*=\s*([0-9]+(?:\.[0-9]+)?)\.dp",
                arguments,
            )
            radius = re.search(
                r"cornerRadiusDp\s*=\s*([0-9]+(?:\.[0-9]+)?)\.dp",
                arguments,
            )
            color = HEX_COLOR_PATTERN.search(arguments)
            theme_role = re.search(
                r"color\s*=\s*MaterialTheme\.colorScheme\.([A-Za-z_][A-Za-z0-9_]*)",
                arguments,
            )
            border_color = (
                color.group(1).replace("0x", "#").upper()
                if color is not None
                else (theme_colors or {}).get(theme_role.group(1))
                if theme_role is not None
                else None
            )
            if width is not None and border_color is not None:
                style["surface"]["border"] = {
                    "width_dp": number(width.group(1)),
                    "color": border_color,
                    "style": "dashed",
                }
                provenance_paths.append("style.surface.border")
            if radius is not None:
                value = number(radius.group(1))
                style["surface"]["corner_radius_dp"] = {
                    "top_left": value,
                    "top_right": value,
                    "bottom_right": value,
                    "bottom_left": value,
                }
                provenance_paths.append("style.surface.corner_radius_dp")
    if style['surface'].get('corner_sizes'):
        sizes = style['surface']['corner_sizes']
        style['surface'].update(shape_surface(
            {'kind': 'rounded_corner', 'absolute': True, 'corners': [sizes[key] for key in CORNERS]},
            None, [style['layout'].get(axis + '_dp') for axis in ('width', 'height')]))
    provenance = []
    if provenance_paths:
        provenance.append(
            {
                "paths": sorted(set(provenance_paths)),
                "origin": "source_resolved",
                "source": f"{call['source']}:{call['line']}",
            }
        )
    provenance.extend(asset_provenance)
    return style, provenance, unresolved
