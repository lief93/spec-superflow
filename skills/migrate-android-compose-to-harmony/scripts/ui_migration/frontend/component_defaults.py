"""Project style overrides above framework defaults, below explicit source properties."""
from __future__ import annotations

import copy
from dataclasses import dataclass

from page_snapshot import empty_style, normalize_style, PageSnapshotError
from .page_model import UNRESOLVED
from .values import evaluate_expression


@dataclass(frozen=True)
class PropertyRule:
    arguments: tuple[str, ...]
    modifiers: tuple[str, ...] = ()


# Each extension must identify the source owners as well as its JSON destination.
PROPERTIES = {
    'surface.background': PropertyRule(('colors', 'color', 'containerColor'), ('background',)),
    'surface.corner_radius_dp': PropertyRule(('shape',), ('clip', 'background', 'border')),
    'surface.border': PropertyRule(('border',), ('border',)),
    'typography.color': PropertyRule(('color', 'contentColor', 'colors', 'style', 'textStyle')),
    'typography.font_size_sp': PropertyRule(('fontSize', 'style', 'textStyle')),
    'typography.font_weight': PropertyRule(('fontWeight', 'style', 'textStyle')),
    'typography.line_height_sp': PropertyRule(('lineHeight', 'style', 'textStyle')),
    'typography.letter_spacing_sp': PropertyRule(('letterSpacing', 'style', 'textStyle')),
}


def normalize_property(path, value):
    group, field = path.split('.')
    if path == 'surface.background' and isinstance(value, str):
        value = {'type': 'solid', 'color': value}
    if path == 'surface.corner_radius_dp' and type(value) in (int, float):
        value = dict.fromkeys(('top_left', 'top_right', 'bottom_right', 'bottom_left'), value)
    style = empty_style()
    style[group][field] = value
    try:
        return normalize_style(style, 'componentDefaults')[group][field]
    except PageSnapshotError as error:
        raise ValueError(str(error)) from error


def validate_component_defaults(defaults):
    if not isinstance(defaults, dict):
        raise ValueError('componentDefaults must be an object keyed by component type')
    for component, properties in defaults.items():
        if not isinstance(component, str) or not component or not isinstance(properties, dict):
            raise ValueError('componentDefaults require named component/property objects')
        for path, spec in properties.items():
            if path not in PROPERTIES:
                raise ValueError(f'unsupported component default property: {path}')
            if not isinstance(spec, dict) or set(spec) not in ({'value'}, {'expression'}):
                raise ValueError(f'{component}.{path} requires exactly value or expression')
            if 'expression' in spec:
                if not isinstance(spec['expression'], str) or not spec['expression'].strip():
                    raise ValueError('component default expression must be nonempty')
            elif spec['value'] is None:
                raise ValueError('omit defaults instead of using null; use explicit transparency or zero')
            else:
                normalize_property(path, spec['value'])
    return defaults


def has_source_owner(node, path):
    rule = PROPERTIES[path]
    arguments = node.get('arguments') or {}
    semantic = arguments.get('semantic') or {}
    invocation = {a.get('name') for a in arguments.get('invocation', [])}
    if any(name in semantic or name in invocation for name in rule.arguments):
        return True
    # An unresolved modifier could own this property; never replace it with an override.
    return any(m.get('name') in (*rule.modifiers, 'unresolvedExpression')
               for m in node.get('modifiers', []))


class ComponentStyleDefaults:
    def __init__(self, definitions):
        self.overrides = validate_component_defaults(definitions.get('componentDefaults', {}))

    def apply(self, node, environment):
        for path, spec in self.overrides.get(node['type'], {}).items():
            if has_source_owner(node, path):
                continue
            group, field = path.split('.')
            value = (evaluate_expression(spec['expression'], {**environment, 'componentState': node['style']['state']})
                     if 'expression' in spec else copy.deepcopy(spec['value']))
            resolved_path = 'style.' + path
            error = None
            if value is UNRESOLVED or value is None:
                error = 'project component default requires a resolved value'
            else:
                try:
                    value = normalize_property(path, value)
                except ValueError as exc:
                    error = str(exc)
            node['unresolved'] = [u for u in node.get('unresolved', []) if u.get('path') != resolved_path]
            if error:
                node['style'][group][field] = None
                node['unresolved'].append({'path': resolved_path, 'expression': str(spec.get('expression', spec.get('value'))),
                                           'reason': error})
                continue
            node['style'][group][field] = value
            if path == 'surface.corner_radius_dp':
                node['style']['surface']['corner_sizes'] = None
            node.setdefault('provenance', []).append({'paths': [resolved_path], 'origin': 'source_resolved',
                'source': f'project styleDefinitions.componentDefaults.{node["type"]}.{path}'})
