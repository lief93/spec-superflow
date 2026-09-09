"""Fixed-state Material item semantics, independent of target rendering."""
from .page_model import semantic_expression, UNRESOLVED
from .values import evaluate_expression


def item_colors(node, environment):
    expression = semantic_expression(node, 'colors')
    if not expression:
        return {}
    value = evaluate_expression(expression, environment)
    return value['values'] if isinstance(value, dict) and value.get('kind') == 'material_colors' else None


def project_material_item(node, environment, slots=()):
    kind = node['type']
    if kind not in {'ListItem', 'FilterChip', 'ExtendedFloatingActionButton', 'TopAppBar', 'CenterAlignedTopAppBar', 'LargeFlexibleTopAppBar'}:
        return
    colors = item_colors(node, environment)
    style = node['style']
    if kind == 'ExtendedFloatingActionButton':
        background = evaluate_expression(semantic_expression(node, 'containerColor') or 'MaterialTheme.colorScheme.primaryContainer', environment)
        if isinstance(background, str) and background.startswith('#'):
            style['surface']['background'] = {'type': 'solid', 'color': background}
        if style['surface']['corner_radius_dp'] is None:
            style['surface']['corner_radius_dp'] = dict.fromkeys(('top_left', 'top_right', 'bottom_right', 'bottom_left'), 16)
        expanded = evaluate_expression(semantic_expression(node, 'expanded') or 'true', environment)
        node['source']['material_item'] = {'min_height_dp': 56, 'horizontal_padding_dp': 16,
            'gap_dp': 12, 'expanded': expanded if isinstance(expanded, bool) else None}
        return
    def theme(role):
        return evaluate_expression('MaterialTheme.colorScheme.' + role, environment)
    def color(key, role):
        value = colors.get(key, theme(role)) if colors is not None else UNRESOLVED
        return value if isinstance(value, str) and value.startswith('#') else None
    selected = style['state'].get('selected')
    enabled = style['state'].get('enabled') is not False
    role = 'secondaryContainer' if kind == 'FilterChip' and selected else 'surface'
    key = ('selectedContainerColor' if selected else 'containerColor') if kind == 'FilterChip' else 'containerColor'
    if kind == 'FilterChip' and not enabled:
        key = 'disabledSelectedContainerColor' if selected else 'disabledContainerColor'
    background = color(key, role)
    if kind == 'FilterChip' and not selected and colors is not None and key not in colors:
        background = '#00000000'
    if background:
        style['surface']['background'] = {'type': 'solid', 'color': background}
        node['unresolved'] = [u for u in node.get('unresolved', []) if u.get('path') != 'style.surface.background']
    elif not any(u.get('path') == 'style.surface.background' for u in node.get('unresolved', [])):
        node.setdefault('unresolved', []).append({'path': 'style.surface.background',
            'expression': semantic_expression(node, 'colors') or 'MaterialTheme.colorScheme.' + role,
            'reason': 'Material container color requires the selected theme and state'})
    if kind in {'TopAppBar', 'CenterAlignedTopAppBar', 'LargeFlexibleTopAppBar'}:
        inset_expression = semantic_expression(node, 'windowInsets')
        insets = evaluate_expression(inset_expression, environment) if inset_expression else environment.get('WindowInsets.statusBars')
        consumed = environment.get('__consumed_window_insets', {})
        top = max(0, insets.get('top', 0) - consumed.get('top', 0)) if isinstance(insets, dict) else None
        if top is None:
            node.setdefault('unresolved', []).append({'path': 'source.appbar.top_inset_dp',
                'expression': inset_expression or 'TopAppBarDefaults.windowInsets', 'reason': 'window inset runtime fact is unavailable'})
        large = kind == 'LargeFlexibleTopAppBar'
        height = 152 if large and 'subtitle' in slots else 120 if large else 64
        height_expression = semantic_expression(node, 'expandedHeight')
        if height_expression:
            value = evaluate_expression(height_expression, environment)
            height = value if type(value) in (int, float) else height
        node['source']['appbar'] = {'content_height_dp': height, 'top_inset_dp': top,
            'expanded': large, 'title_baseline_bottom_dp': 28 if large else None}
    if kind == 'FilterChip':
        if style['surface']['corner_radius_dp'] is None:
            style['surface']['corner_radius_dp'] = dict.fromkeys(('top_left', 'top_right', 'bottom_right', 'bottom_left'), 8)
        if not selected and style['surface']['border'] is None:
            outline = theme('outlineVariant')
            if isinstance(outline, str):
                style['surface']['border'] = {'width_dp': 1, 'color': outline, 'style': 'solid'}
        minimum = environment.get('LocalMinimumInteractiveComponentSize.current', 48)
        node['source']['material_item'] = {'min_height_dp': 32, 'horizontal_padding_dp': 16, 'gap_dp': 8,
            'start_padding_dp': 8 if 'leadingIcon' in slots else 16,
            'end_padding_dp': 8 if 'trailingIcon' in slots else 16,
            'minimum_interactive_dp': minimum if type(minimum) in (int, float) else None}
    elif kind == 'ListItem':
        lines = 3 if 'overlineContent' in slots and 'supportingContent' in slots else 2 if 'supportingContent' in slots else 1
        node['source']['material_item'] = {'min_height_dp': {1: 56, 2: 72, 3: 88}[lines],
            'horizontal_padding_dp': 16, 'vertical_padding_dp': 12 if lines == 3 else 8, 'gap_dp': 16}


def material_content_color(parent, slot, environment):
    colors = item_colors(parent, environment)
    if colors is None:
        return None
    kind = parent['type']
    if kind == 'ExtendedFloatingActionButton':
        value = evaluate_expression(semantic_expression(parent, 'contentColor') or 'MaterialTheme.colorScheme.onPrimaryContainer', environment)
        return value if isinstance(value, str) else None
    if kind == 'ListItem':
        key, role = {'supportingContent': ('supportingTextColor', 'onSurfaceVariant'),
                     'leadingContent': ('leadingIconColor', 'onSurfaceVariant'),
                     'trailingContent': ('trailingIconColor', 'onSurfaceVariant'),
                     'overlineContent': ('overlineColor', 'onSurfaceVariant')}.get(slot, ('headlineColor', 'onSurface'))
    elif kind == 'FilterChip':
        selected = evaluate_expression(semantic_expression(parent, 'selected') or '', environment)
        part = {'leadingIcon': 'LeadingIcon', 'trailingIcon': 'TrailingIcon'}.get(slot, 'Label')
        key = ('selected' + part + 'Color') if selected is True else part[0].lower() + part[1:] + 'Color'
        role = 'onSecondaryContainer' if selected is True else 'onSurfaceVariant'
    elif kind in {'TopAppBar', 'CenterAlignedTopAppBar', 'LargeFlexibleTopAppBar'}:
        key, role = {'actions': ('actionIconContentColor', 'onSurfaceVariant'),
                     'navigationIcon': ('navigationIconContentColor', 'onSurface')}.get(slot, ('titleContentColor', 'onSurface'))
    else:
        return None
    value = colors.get(key, evaluate_expression('MaterialTheme.colorScheme.' + role, environment))
    return value if isinstance(value, str) else None


def material_text_defaults(parent, slot):
    if (parent.get('type') == 'FilterChip' and slot == 'label') or (parent.get('type') == 'ExtendedFloatingActionButton' and slot == 'text'):
        return {'font_size_sp': 14, 'line_height_sp': 20, 'font_weight': 500, 'letter_spacing_sp': 0.1}
    return None
