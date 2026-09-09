"""Material 3 baseline tokens projected before project overrides; no target defaults."""
from .page_model import semantic_expression, UNRESOLVED
from .values import evaluate_expression
from .shapes import shape_surface
from .component_defaults import has_source_owner
from .material_controls import MaterialControlDefaults, SELECTIONS, PROGRESS


DEFAULT_CONTROL_TYPES = {'Button', 'TextButton', 'OutlinedButton', 'TextField', 'OutlinedTextField',
    'IconButton', 'IconToggleButton', 'Card', 'Surface', 'Divider', 'HorizontalDivider', 'VerticalDivider'} | SELECTIONS | PROGRESS


def project_material_defaults(node, environment, children=()):
    kind = node['type']
    if kind in DEFAULT_CONTROL_TYPES:
        node['source']['material_defaults_profile'] = 'material3-baseline'
    MaterialControlDefaults(node, environment).apply()
    style = node['style']
    surface, typography = style['surface'], style['typography']

    def assign(path, value):
        group, field = path.split('.')
        style[group][field] = value
        node['unresolved'] = [u for u in node.get('unresolved', []) if u.get('path') != 'style.' + path]
        node.setdefault('provenance', []).append({'paths': ['style.' + path], 'origin': 'source_resolved',
            'source': 'Material3 baseline default: ' + kind})

    def role(name):
        return evaluate_expression('MaterialTheme.colorScheme.' + name, environment)

    def paint(path, value):
        if isinstance(value, str) and value.startswith('#') and len(value) == 9:
            assign(path, {'type': 'solid', 'color': value} if path == 'surface.background' else value)

    if kind in {'Button', 'TextButton', 'OutlinedButton', 'Card'}:
        defaults = MaterialControlDefaults(node, environment)
        colors_expr = semantic_expression(node, 'colors')
        enabled = style['state'].get('enabled')
        for path, part, token in [('surface.background', 'ContainerColor',
                    'surfaceContainerHighest' if kind == 'Card' else 'primary'),
                ('typography.color', 'ContentColor', 'onSurface' if kind == 'Card' else 'onPrimary' if kind == 'Button' else 'primary')]:
            # A colors object owns only its provided entries, not every default token.
            if not has_source_owner(node, path) or colors_expr:
                key = ('disabled' + part) if enabled is False else part[0].lower() + part[1:]
                if type(enabled) is not bool:
                    value = UNRESOLVED
                elif defaults.colors is not None and key not in defaults.colors and part == 'ContainerColor' and kind in {'TextButton', 'OutlinedButton'}:
                    value = '#00000000'
                elif enabled is False and kind != 'Card':
                    value = defaults.color(key, 'onSurface', .12 if part == 'ContainerColor' else .38)
                else:
                    value = defaults.color(key, token)
                if kind == 'Card' and enabled is False and part == 'ContainerColor' and defaults.colors is not None and key not in defaults.colors:
                    value = UNRESOLVED  # Disabled Card composites elevation-dependent tokens.
                defaults.assign(path, {'type': 'solid', 'color': value} if path == 'surface.background' and isinstance(value, str) else value,
                    colors_expr or 'MaterialTheme.colorScheme.' + token)

    if kind in {'Button', 'TextButton', 'OutlinedButton'}:
        node['source']['material_size'] = {'min_width_dp': 58, 'min_height_dp': 40}
        minimum = environment.get('LocalMinimumInteractiveComponentSize.current', 48)
        if type(minimum) in (int, float):
            node['source']['material_touch_height_dp'] = minimum
        if not has_source_owner(node, 'surface.corner_radius_dp'):
            shape = shape_surface(evaluate_expression('CircleShape', environment), 'ltr')
            if shape:
                surface.update(shape)
        if not semantic_expression(node, 'contentPadding'):
            horizontal = 12 if kind == 'TextButton' else 24
            node.setdefault('arguments', {}).setdefault('semantic', {})['contentPadding'] = {
                'expression': f'PaddingValues(horizontal = {horizontal}.dp, vertical = 8.dp)'}
            assign('layout.padding_dp', dict(left=horizontal, right=horizontal, top=8, bottom=8))
        if kind == 'OutlinedButton' and not has_source_owner(node, 'surface.border'):
            color = role('outline')
            if style['state'].get('enabled') is False:
                base = role('onSurface')
                color = '#1F' + base[-6:] if isinstance(base, str) else None
            if isinstance(color, str):
                assign('surface.border', {'width_dp': 1, 'color': color, 'style': 'solid'})

    if kind in {'Card', 'Surface'} and not has_source_owner(node, 'surface.corner_radius_dp'):
        expression = 'MaterialTheme.shapes.medium' if kind == 'Card' else 'RectangleShape'
        value = evaluate_expression(expression, environment)
        if value is UNRESOLVED and expression not in environment:
            value = evaluate_expression('RoundedCornerShape(12.dp)' if kind == 'Card' else 'RoundedCornerShape(0.dp)', environment)
        shape = shape_surface(value, 'rtl' if environment.get('LocalLayoutDirection.current') == 'LayoutDirection.Rtl' else 'ltr')
        if shape:
            surface.update(shape)
        else:
            MaterialControlDefaults(node, environment).assign('surface.corner_radius_dp', UNRESOLVED, expression)

    if kind in {'IconButton', 'IconToggleButton'}:
        defaults = MaterialControlDefaults(node, environment)
        enabled = style['state'].get('enabled')
        checked = style['state'].get('checked') if kind == 'IconToggleButton' else False
        if not has_source_owner(node, 'surface.background') or semantic_expression(node, 'colors'):
            key = 'disabledContainerColor' if enabled is False else 'checkedContainerColor' if checked else 'containerColor'
            value = defaults.colors.get(key, '#00000000') if defaults.colors is not None else UNRESOLVED
            defaults.assign('surface.background', {'type': 'solid', 'color': value} if isinstance(value, str) else UNRESOLVED,
                semantic_expression(node, 'colors') or 'IconButtonDefaults transparent container')
        if not has_source_owner(node, 'typography.color') or semantic_expression(node, 'colors'):
            key = 'disabledContentColor' if enabled is False else 'checkedContentColor' if checked else 'contentColor'
            value = defaults.color(key, 'onSurface' if enabled is False else 'primary' if checked else 'onSurfaceVariant', .38 if enabled is False else None)
            defaults.assign('typography.color', value, semantic_expression(node, 'colors') or 'IconButtonDefaults content color')
        node['source']['material_size'] = {'min_width_dp': 48, 'min_height_dp': 48}

    if kind in {'Divider', 'HorizontalDivider', 'VerticalDivider'} and not semantic_expression(node, 'color'):
        color = role('outlineVariant')
        MaterialControlDefaults(node, environment).assign('control.active_color', color, 'MaterialTheme.colorScheme.outlineVariant')

    if kind not in {'TextField', 'OutlinedTextField'}:
        return
    enabled = style['state'].get('enabled')
    error = evaluate_expression(semantic_expression(node, 'isError') or 'false', environment)
    focused = environment.get('__focused_component_id') == node['id']
    colors_expr = semantic_expression(node, 'colors')
    colors = evaluate_expression(colors_expr, environment) if colors_expr else {'kind': 'material_colors', 'values': {}}
    if not isinstance(colors, dict) or colors.get('kind') != 'material_colors' or type(error) is not bool or type(enabled) is not bool:
        node.setdefault('unresolved', []).append({'path': 'source.material_input', 'expression': colors_expr or 'isError/enabled',
            'reason': 'Material input appearance requires known colors and fixed state'})
        return
    state = 'disabled' if not enabled else 'error' if error else 'focused' if focused else 'unfocused'
    values = colors['values']

    def color(part, default_role, alpha=None):
        key = state + part
        value = values.get(key, role(default_role))
        if key not in values and alpha and isinstance(value, str):
            value = '#' + alpha + value[-6:]
        return value

    text_color = color('TextColor', 'onSurface', '61' if not enabled else None)
    outline_color = color('BorderColor' if kind == 'OutlinedTextField' else 'IndicatorColor',
        'onSurface' if not enabled else 'error' if error else 'primary' if focused else 'outline', '1F' if not enabled else None)
    label_color = color('LabelColor', 'onSurface' if not enabled else 'error' if error else 'primary' if focused else 'onSurfaceVariant', '61' if not enabled else None)
    if not has_source_owner(node, 'surface.background') or colors_expr:
        background = values.get(state + 'ContainerColor', '#00000000' if kind == 'OutlinedTextField' else role('surfaceContainerHighest'))
        paint('surface.background', background)
    if not has_source_owner(node, 'typography.font_size_sp'):
        for field, value in [('font_size_sp', 16), ('line_height_sp', 24), ('letter_spacing_sp', 0.5), ('font_weight', 400)]:
            if typography.get(field) is None:
                assign('typography.' + field, value)
    if not semantic_expression(node, 'textStyle'):
        paint('typography.color', text_color)
    if not has_source_owner(node, 'surface.corner_radius_dp'):
        assign('surface.corner_radius_dp', dict(top_left=4, top_right=4,
            bottom_left=4 if kind == 'OutlinedTextField' else 0, bottom_right=4 if kind == 'OutlinedTextField' else 0))
    if not has_source_owner(node, 'surface.border') and isinstance(outline_color, str) and kind == 'OutlinedTextField':
        assign('surface.border', {'width_dp': 2 if focused else 1, 'color': outline_color, 'style': 'solid'})
    label_nodes = [c for c in children if c['type'] == 'Text']
    label = None
    if semantic_expression(node, 'label') and len(label_nodes) == 1:
        child = label_nodes[0]
        expr = semantic_expression(child, 'text')
        if not expr:
            positional = child.get('arguments', {}).get('positional', [])
            expr = positional[0].get('expression') if positional else ''
        label = evaluate_expression(expr, environment)
    floating = bool(style['content'].get('text')) or focused
    node['source']['material_input'] = {'kind': kind, 'min_width_dp': 280, 'min_height_dp': 56,
        'label_top_inset_dp': 8 if semantic_expression(node, 'label') and kind == 'OutlinedTextField' else 0,
        'label': label if isinstance(label, str) else None, 'label_color': label_color if isinstance(label_color, str) else None,
        'floating': floating, 'focused': focused, 'indicator_color': outline_color if isinstance(outline_color, str) else None,
        'indicator_width_dp': 2 if focused else 1}
    if isinstance(label, str) and not floating:
        assign('content.placeholder', label)
    elif semantic_expression(node, 'label'):
        node.setdefault('unresolved', []).append({'path': 'source.material_input.label', 'expression': semantic_expression(node, 'label'),
            'reason': 'floating or compound Material label requires a dedicated decoration layout'})
    # Reserve the standard input content inset independently of outer Modifier.padding.
    node['source']['material_input']['content_padding_dp'] = dict(left=16, right=16, top=16, bottom=16)
