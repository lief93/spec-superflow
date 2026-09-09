"""Window-owned Compose content, separated from normal parent measurement."""
from page_snapshot import empty_style
from .page_model import semantic_expression, UNRESOLVED
from .values import evaluate_expression
from .shapes import shape_surface

OVERLAY_TYPES = {'AlertDialog', 'Dialog', 'ModalBottomSheet'}


def project_overlay(node, environment, slots):
    if node['type'] not in OVERLAY_TYPES:
        return
    def value(name, default):
        return evaluate_expression(semantic_expression(node, name) or default, environment)
    def issue(name, reason):
        node.setdefault('unresolved', []).append({'path': 'source.overlay.' + name,
            'expression': semantic_expression(node, name) or name, 'reason': reason})
    sheet = node['type'] == 'ModalBottomSheet'
    properties = value('properties', 'DialogProperties()')
    if not isinstance(properties, dict) or properties.get('kind') != 'dialog_properties':
        issue('properties', 'custom window properties require an explicit adapter')
        properties = {}
    facts = {'kind': node['type'], 'dismiss_on_back': properties.get('dismissOnBackPress', True),
        'dismiss_on_outside': properties.get('dismissOnClickOutside', True),
        'platform_width': properties.get('usePlatformDefaultWidth', True),
        'max_width_dp': 640 if sheet else 560, 'inset_dp': 0 if sheet or properties.get('usePlatformDefaultWidth') is False else 28,
        'scrim_color': '#52000000', 'drag_handle': 'custom' if 'dragHandle' in slots else
            'none' if semantic_expression(node, 'dragHandle') == 'null' else 'default',
        'gestures_enabled': True, 'business_callbacks_migrated': False}
    if sheet:
        gestures = value('sheetGesturesEnabled', 'true')
        if type(gestures) is bool:
            facts['gestures_enabled'] = gestures
        else:
            issue('sheetGesturesEnabled', 'sheet gesture state must resolve to boolean')
        maximum = value('sheetMaxWidth', '640.dp')
        if type(maximum) in (int, float) and maximum > 0:
            facts['max_width_dp'] = maximum
        else:
            issue('sheetMaxWidth', 'sheet width must resolve to positive dp')
        if semantic_expression(node, 'sheetState'):
            issue('sheetState', 'custom sheet state/partial anchors are not translated; content remains in preview')
        if semantic_expression(node, 'contentWindowInsets'):
            issue('contentWindowInsets', 'custom sheet window inset callback requires resolved native insets')
    scrim = semantic_expression(node, 'scrimColor')
    if scrim:
        color = evaluate_expression(scrim, environment)
        if isinstance(color, str) and color.startswith('#'):
            facts['scrim_color'] = color
        else:
            issue('scrimColor', 'scrim color is unresolved')
    if node['type'] != 'Dialog':
        surface = node['style']['surface']
        color = value('containerColor', 'MaterialTheme.colorScheme.surfaceContainerHigh' if not sheet else
                      'MaterialTheme.colorScheme.surfaceContainerLow')
        if isinstance(color, str) and color.startswith('#'):
            surface['background'] = {'type': 'solid', 'color': color}
        else:
            issue('containerColor', 'Material overlay container color requires the project theme')
        shape = semantic_expression(node, 'shape')
        if shape:
            resolved = shape_surface(evaluate_expression(shape, environment),
                                     node['style']['layout'].get('layout_direction'), (None, None))
            if resolved:
                surface.update(resolved)
            else:
                issue('shape', 'overlay shape is unresolved')
        else:
            from .component_defaults import has_source_owner
            if has_source_owner(node, 'surface.corner_radius_dp'):
                node['source']['overlay'] = facts
                return
            surface['corner_radius_dp'] = dict(top_left=28, top_right=28, bottom_left=0 if sheet else 28, bottom_right=0 if sheet else 28)
    node['source']['overlay'] = facts


def overlay_host(roots, nodes):
    """Only window-owned siblings may accompany one ordinary page layout root."""
    normal = [i for i in roots if nodes[i]['type'] not in OVERLAY_TYPES]
    if len(roots) < 2 or len(normal) > 1 or not any(nodes[i]['type'] in OVERLAY_TYPES for i in roots):
        return None
    identifier = 'compose-window-content-host'
    while identifier in nodes:
        identifier += '-host'
    source = nodes[roots[0]]['source']
    return {'id': identifier, 'source_component_id': identifier, 'semantic_key': identifier,
        'type': 'Box', 'parent_id': None, 'sibling_index': 0, 'children_ids': roots,
        'style': empty_style(), 'arguments': {}, 'modifiers': [{'name': 'fillMaxSize', 'arguments': ''}],
        'source': {'source': source.get('source'), 'composable': source.get('composable'), 'window_content_host': True, 'attributes': []},
        'unresolved': []}
