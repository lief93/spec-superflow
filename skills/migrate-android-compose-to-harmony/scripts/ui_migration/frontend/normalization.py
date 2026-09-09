from __future__ import annotations
import copy
import re
from component_required_facts import build_required_facts, normalized_layout_rules, number_expression, parsed_arguments
from page_snapshot import empty_style
from typing import Any
from ui_migration.frontend.page_model import nested_modifier_arguments, semantic_expression, style_group


def expand_material_touch_targets(payload: dict[str, Any]) -> None:
    """Separate a button's painted surface from minimumInteractiveComponentSize."""
    by_id = {node['id']: node for node in payload['components']}
    additions = []
    for node in list(payload['components']):
        minimum = node.get('source', {}).get('material_touch_height_dp')
        if node['type'] not in {'Button', 'TextButton', 'OutlinedButton'} or not minimum:
            continue
        layout = node['style']['layout']
        rules = node.get('layout_rules') or normalized_layout_rules(node)
        if layout.get('height_dp') is not None or any(
                r.get('kind') == 'sizing' and 'height' in r.get('axes', []) for r in rules):
            continue
        body = copy.deepcopy(node)
        body.update(id=node['id'] + '--paint', semantic_key=node['semantic_key'] + '--paint',
                    parent_id=node['id'], sibling_index=0, modifiers=[], layout_rules=[])
        body['style']['layout']['height_dp'] = None
        fill_width = layout.get('width_dp') is not None or any(r.get('kind') == 'weight' or
            (r.get('kind') == 'sizing' and r.get('mode') == 'fill_parent' and 'width' in r.get('axes', [])) for r in rules)
        if fill_width:
            body['modifiers'] = [{'name': 'fillMaxWidth', 'arguments': ''}]
            body['layout_rules'] = normalized_layout_rules(body)
        for child in body['children_ids']:
            by_id[child]['parent_id'] = body['id']
        outer_style = empty_style()
        outer_style['layout'].update(copy.deepcopy(layout), padding_dp=None, alignment='Center')
        outer_style['state'].update(node['style']['state'])
        modifier_index = len(node.get('modifiers', []))
        node.setdefault('modifiers', []).append({'name': 'sizeIn', 'arguments': f'minHeight = {minimum}.dp',
            'origin': 'Material3.minimumInteractiveComponentSize'})
        node.update(type='Box', component_kind='platform', arguments={}, children_ids=[body['id']],
            style=outer_style, layout_rules=rules + [{'kind': 'constraints', 'limits': {'minHeight': minimum},
                'source_modifier_index': modifier_index}],
            source={**node['source'], 'material_touch_wrapper': True}, unresolved=[])
        node['source'].pop('style_token_references', None)
        additions.append(body)
    payload['components'].extend(additions)


def expand_surface_padding(payload: dict[str, Any]) -> None:
    """Keep modifier padding outside a native surface, not in its content padding."""
    from analyze_compose_project import ordered_modifier_chain
    from ui_migration.frontend.bindings import bind_source_expression, direct_padding
    from ui_migration.frontend.styles import static_style_for_call

    additions = []
    by_id = {node['id']: node for node in payload['components']}
    native_surfaces = {'Button', 'TextButton', 'OutlinedButton', 'IconButton', 'IconToggleButton', 'Card', 'Surface'}
    layout_modifiers = {'padding', 'fillMaxWidth', 'fillMaxHeight', 'fillMaxSize',
                        'wrapContentWidth', 'wrapContentHeight', 'wrapContentSize',
                        'width', 'height', 'size', 'widthIn', 'heightIn', 'sizeIn', 'weight', 'align'}
    for node in list(payload['components']):
        if node.get('component_kind') == 'project' or (node.get('source') or {}).get('custom_component'):
            continue
        bindings = {**(node.get('parameter_bindings') or {}), **(node.get('local_values') or {})}

        def flatten(modifiers):
            result = []
            for modifier in modifiers:
                expression = bind_source_expression(str(modifier.get('arguments') or ''), bindings)
                if modifier.get('name') == 'then' and re.match(r'^Modifier\b', expression):
                    result.extend(flatten(ordered_modifier_chain(expression)))
                else:
                    result.extend(ordered_modifier_chain(f"Modifier.{modifier['name']}({expression})"))
            return result

        chain = flatten(node.get('modifiers') or [])
        boundary = next((i for i, m in enumerate(chain) if m['name'] not in layout_modifiers), len(chain))
        prefix, rest = chain[:boundary], chain[boundary:]
        if not any(m['name'] == 'padding' for m in prefix):
            continue
        if node['type'] not in native_surfaces and not any(
            m['name'] in {'background', 'border', 'dashedBorder', 'shadow', 'clip'} for m in rest
        ) and not (node['type'] in {'Row', 'Column', 'Box', 'LazyColumn', 'LazyRow'}
                   and sum(m['name'] == 'padding' for m in prefix) > 1):
            continue
        # More layout changes after drawing need their own ordered lowering.
        if any(m['name'] in layout_modifiers - {'padding'} for m in rest):
            continue

        def modifier_style(modifiers):
            call = {'component': 'Box', 'source': node.get('source', {}).get('source', ''),
                    'line': node.get('source', {}).get('line', 0),
                    'ordered_modifier_chain': modifiers}
            return static_style_for_call(call, {}, None, bindings)[0]['layout']

        layers = []
        for modifier in prefix:
            layout = modifier_style([modifier])
            if modifier['name'] == 'padding' and layout.get('padding_dp') is None:
                break
            rules = normalized_layout_rules({'modifiers': [modifier]})
            if modifier['name'] != 'padding' and not rules and not any(
                layout.get(axis + '_dp') is not None for axis in ('width', 'height')
            ):
                break
            layers.append((layout, modifier))
        if len(layers) != len(prefix):
            continue

        body = copy.deepcopy(node)
        body.update(id=node['id'] + '--surface', semantic_key=node['semantic_key'] + '--surface',
                    sibling_index=0, modifiers=rest)
        body['layout_rules'] = normalized_layout_rules(body)
        body_layout = body['style']['layout']
        for axis in ('width', 'height'):
            if any(layout.get(axis + '_dp') is not None for layout, _ in layers):
                body_layout[axis + '_dp'] = None
        if node['type'] in native_surfaces:
            expression = bind_source_expression(semantic_expression(node, 'contentPadding'), bindings)
            dimensions = [(float(value), unit) for value, unit in re.findall(r'(-?\d+(?:\.\d+)?)\.(dp|sp)\b', expression)]
            body_layout['padding_dp'] = direct_padding(expression, dimensions) if expression else None
        else:
            body_layout['padding_dp'] = modifier_style(rest).get('padding_dp')

        wrappers = []
        fill_axes = set()
        for i, (layout, modifier) in enumerate(layers):
            wrapper_id = node['id'] if i == 0 else node['id'] + f'--outer-{i}'
            wrapper = {'id': wrapper_id, 'semantic_key': node['semantic_key'] if i == 0 else wrapper_id,
                       'type': 'Box', 'component_kind': 'platform', 'arguments': {},
                       'parent_id': node['parent_id'] if i == 0 else wrappers[-1]['id'],
                       'sibling_index': node.get('sibling_index', 0) if i == 0 else 0,
                       'children_ids': [], 'style': empty_style(),
                       'source': {**node.get('source', {}), 'attributes': [], 'surface_padding_layer': i},
                       'modifiers': [{'name': 'fillMax' + axis.title(), 'arguments': ''} for axis in sorted(fill_axes)] + [modifier]}
            wrapper['style']['layout'].update(layout, alignment='TopStart')
            wrapper['source'].pop('style_token_references', None)
            if wrappers:
                wrappers[-1]['children_ids'] = [wrapper_id]
            wrappers.append(wrapper)
            for rule in normalized_layout_rules(wrapper):
                if rule['kind'] == 'sizing' and rule['mode'] == 'fill_parent':
                    fill_axes.update(rule['axes'])
            fill_axes.update(axis for axis in ('width', 'height') if layout.get(axis + '_dp') is not None)
        body['modifiers'] = [{'name': 'fillMax' + axis.title(), 'arguments': ''} for axis in sorted(fill_axes)] + rest
        body['layout_rules'] = normalized_layout_rules(body)
        body['parent_id'] = wrappers[-1]['id']
        wrappers[-1]['children_ids'] = [body['id']]
        for child_id in body['children_ids']:
            by_id[child_id]['parent_id'] = body['id']
        node.clear()
        node.update(wrappers[0])
        additions.extend([*wrappers[1:], body])
    payload['components'].extend(additions)


def expand_ordered_layout_modifiers(payload: dict[str, Any]) -> None:
    """Retain constant layout modifier nesting; never reconstruct it from frames."""
    additions = []
    original_nodes = list(payload['components'])
    by_id = {node['id']: node for node in original_nodes}
    for node in original_nodes:
        if not any(f['path'] == 'source.modifiers.order' for f in build_required_facts(node)):
            continue
        chain = node.get('modifiers') or []
        if node.get('component_kind') == 'project' or node.get('layout_rules') or semantic_expression(node, 'contentPadding'):
            continue
        layers = []
        sized_axes = set()
        for modifier in chain:
            name, expression = modifier.get('name'), str(modifier.get('arguments') or '')
            positional, named = parsed_arguments(expression)
            fields = {}
            if name == 'padding':
                if len(positional) == 1 and not named:
                    amount = number_expression(positional[0], 'dp')
                    values = dict.fromkeys(('left', 'top', 'right', 'bottom'), amount)
                elif not positional and named and not set(named) - {'horizontal', 'vertical', 'start', 'end', 'top', 'bottom'}:
                    values = {side: number_expression(named.get(key, named.get(axis, '0.dp')), 'dp')
                              for side, key, axis in [('left', 'start', 'horizontal'), ('right', 'end', 'horizontal'),
                                                      ('top', 'top', 'vertical'), ('bottom', 'bottom', 'vertical')]}
                    if values['left'] != values['right'] and style_group(node, 'layout').get('layout_direction') not in {'ltr', 'rtl'}:
                        break
                    if style_group(node, 'layout').get('layout_direction') == 'rtl':
                        values['left'], values['right'] = values['right'], values['left']
                else:
                    break
                if any(v is None or v < 0 for v in values.values()):
                    break
                fields['padding_dp'] = values
            elif name in {'size', 'width', 'height'}:
                axes = ['width', 'height'] if name == 'size' else [name]
                if sized_axes.intersection(axes):
                    break
                if len(positional) == 1 and not named:
                    fields = {axis + '_dp': number_expression(positional[0], 'dp') for axis in axes}
                elif not positional and set(named) == set(axes):
                    fields = {axis + '_dp': number_expression(named[axis], 'dp') for axis in axes}
                else:
                    break
                if any(value is None or value <= 0 for value in fields.values()):
                    break
                sized_axes.update(axes)
            else:
                break
            layers.append(fields)
        if len(layers) != len(chain):
            continue
        body = copy.deepcopy(node)
        body['id'] = node['id'] + '--content'
        body['semantic_key'] = str(node.get('semantic_key') or node['id']) + '--content'
        body['modifiers'] = []
        body.pop('required_facts', None)
        for key in ('width_dp', 'height_dp', 'padding_dp'):
            body['style']['layout'][key] = None
        for child in body.get('children_ids') or []:
            by_id[child]['parent_id'] = body['id']
        inherited_axes = set()
        wrapper_nodes = []
        for index, fields in enumerate(layers):
            wrapper_id = node['id'] if index == 0 else node['id'] + f'--modifier-{index}'
            wrapper = {'id': wrapper_id, 'type': 'Box', 'semantic_key': wrapper_id,
                       'parent_id': node['parent_id'] if index == 0 else wrapper_nodes[-1]['id'],
                       'sibling_index': node.get('sibling_index', 0) if index == 0 else 0,
                       'children_ids': [], 'arguments': {}, 'component_kind': 'platform',
                       'source': {**node.get('source', {}), 'modifier_layer': index},
                       'style': empty_style(), 'modifiers': []}
            wrapper['style']['layout'].update(fields, alignment='TopStart')
            wrapper['source'].pop('style_token_references', None)
            wrapper['style']['layout']['layout_direction'] = style_group(node, 'layout').get('layout_direction')
            wrapper['modifiers'] = [{'name': 'fillMax' + axis.title(), 'arguments': ''}
                                    for axis in sorted(inherited_axes) if axis + '_dp' not in fields]
            if wrapper_nodes:
                wrapper_nodes[-1]['children_ids'] = [wrapper_id]
            wrapper_nodes.append(wrapper)
            inherited_axes.update(axis for axis in ('width', 'height') if axis + '_dp' in fields)
        body['parent_id'] = wrapper_nodes[-1]['id']
        body['sibling_index'] = 0
        body['modifiers'] = [{'name': 'fillMax' + axis.title(), 'arguments': ''} for axis in sorted(inherited_axes)]
        wrapper_nodes[-1]['children_ids'] = [body['id']]
        node.clear()
        node.update(wrapper_nodes[0])
        additions.extend([*wrapper_nodes[1:], body])
    payload['components'].extend(additions)


def resolve_scaffold_padding(payload: dict[str, Any]) -> None:
    """Retain the bar-height relationship; only literal extra padding is evaluated."""
    nodes = {node['id']: node for node in payload.get('components', [])}
    for node in nodes.values():
        ancestor = nodes.get(node.get('parent_id'))
        while ancestor and ancestor.get('type') != 'Scaffold':
            ancestor = nodes.get(ancestor.get('parent_id'))
        if not ancestor:
            continue
        parameters = ancestor.get('source', {}).get('trailing_lambda_parameters', [])
        if len(parameters) != 1:
            continue
        from kotlin_psi import parse_expression
        from ui_migration.semantics.syntax import call_from
        from ui_migration.frontend.values import evaluate_expression
        insets_expression = semantic_expression(ancestor, 'contentWindowInsets')
        insets = call_from(parse_expression(insets_expression)) if insets_expression else None
        bar_slots = {nodes[child].get('slot_argument_name') for child in ancestor.get('children_ids', [])}
        if (insets and insets.qualified_name == 'WindowInsets' and len(insets.arguments) == 4
                and all(evaluate_expression(arg['value']['text'], {}) == 0 for arg in insets.arguments)
                and not bar_slots.intersection({'topBar', 'bottomBar'})):
            for modifier in node.get('modifiers', []):
                if modifier.get('name') == 'padding' and modifier.get('arguments', '').strip() == parameters[0]:
                    modifier.update(arguments='0.dp', syntax_expression='padding(0.dp)',
                                    original_expression='padding(' + parameters[0] + ')')
                    node.setdefault('provenance', []).append({'paths': ['style.layout.padding_dp'],
                        'origin': 'source_resolved', 'source': 'Scaffold: ' + insets_expression + '; no bars'})
        for expression in nested_modifier_arguments(node, 'padding'):
            positional, named = parsed_arguments(expression)
            if positional or not named:
                continue
            edges, offsets = {}, {}
            for name, value in named.items():
                edge = {'start': 'left', 'end': 'right'}.get(name, name)
                if edge not in {'left', 'right', 'top', 'bottom'}:
                    break
                match = re.fullmatch(re.escape(parameters[0]) + r'\.calculate(Top|Bottom)Padding\(\)(?:\s*\+\s*(\d+(?:\.\d+)?)\.dp)?', value.strip())
                if match:
                    edges[edge] = 'topBar' if match.group(1) == 'Top' else 'bottomBar'
                    offsets[edge] = float(match.group(2) or 0)
                else:
                    offset = number_expression(value, 'dp')
                    if offset is None:
                        break
                    offsets[edge] = offset
            else:
                if not edges:
                    continue
                padding = dict.fromkeys(('left', 'right', 'top', 'bottom'), 0.0)
                padding.update(offsets)
                node['style']['layout']['padding_dp'] = padding
                node['source']['scaffold_padding'] = {'owner_id': ancestor['id'], 'edges': edges}
                node['unresolved'] = [u for u in node.get('unresolved', []) if u.get('path') != 'style.layout.padding_dp']


def resolve_native_content_colors(payload: dict[str, Any]) -> None:
    # Compose Button provides LocalContentColor through intervening layout/function nodes.
    nodes = {node['id']: node for node in payload.get('components', [])}
    providers = {'Button', 'TextButton', 'OutlinedButton', 'Card', 'Surface', 'IconButton', 'IconToggleButton'}
    for node in nodes.values():
        if node.get('type') not in {'Text', 'BasicText', 'ClickableText', 'Icon'}:
            continue
        group, field = ('asset', 'tint') if node['type'] == 'Icon' else ('typography', 'color')
        target = style_group(node, group)
        path = 'style.' + group + '.' + field
        if target.get(field) is not None:
            continue
        if node['type'] == 'Icon' and semantic_expression(node, 'tint') == 'Color.Unspecified':
            continue
        pending = [item for item in node.get('unresolved', []) if item.get('path') == path]
        if any(item.get('expression') not in {'LocalContentColor.current', 'Color.Unspecified'} for item in pending):
            continue
        parent = nodes.get(node.get('parent_id'))
        while parent is not None:
            if parent.get('type') in providers:
                color = style_group(parent, 'typography').get('color')
                if isinstance(color, str):
                    target[field] = color
                    node['unresolved'] = [item for item in node.get('unresolved', []) if item not in pending]
                    node.setdefault('provenance', []).append({
                        'paths': [path], 'origin': 'source_resolved',
                        'source': parent['id'] + ':LocalContentColor'})
                break
            parent = nodes.get(parent.get('parent_id'))
