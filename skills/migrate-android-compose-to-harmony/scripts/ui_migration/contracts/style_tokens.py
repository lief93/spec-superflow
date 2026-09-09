"""Typed, declarative cross-platform style references, not executable snippets."""
import re
import math


PROPERTY_TYPES = {
    'content.text': ('string', None, None),
    'content.placeholder': ('string', None, None),
    'content.content_description': ('string', None, None),
    'typography.font_size_sp': ('dimension', 'sp', 'fp'),
    'typography.line_height_sp': ('dimension', 'sp', 'fp'),
    'typography.letter_spacing_sp': ('dimension', 'sp', 'fp'),
    'typography.color': ('color', None, None),
    'typography.font_weight': ('number', None, None),
    'typography.font_family': ('string', None, None),
    'surface.background': ('color', None, None),
    'surface.corner_radius_dp': ('dimension', 'dp', 'vp'),
    'asset.tint': ('color', None, None),
    'control.active_color': ('color', None, None),
    'control.inactive_color': ('color', None, None),
}


def validate_target(target):
    identifier = r'[A-Za-z_][A-Za-z_0-9]*'
    member = identifier + r'(?:\.' + identifier + r')*'
    if not isinstance(target, dict) or set(target) not in (
        {'module', 'export', 'member'}, {'module', 'export', 'member', 'arguments'}):
        raise ValueError('target requires module/export/member and optional call arguments')
    for field, pattern in [('export', identifier), ('member', member), ('module', r'[@A-Za-z0-9_./-]+')]:
        if not isinstance(target[field], str) or not re.fullmatch(pattern, target[field]):
            raise ValueError(f'unsafe or invalid target {field}')
    if 'arguments' in target:
        if not isinstance(target['arguments'], list):
            raise ValueError('target arguments must be a list of literal values')
        for value in target['arguments']:
            if value is not None and type(value) not in (str, bool, int, float):
                raise ValueError('target arguments must be literal values, not code')
            if type(value) is float and not math.isfinite(value):
                raise ValueError('target arguments must be finite')


def validate_token_reference(reference, path):
    if not isinstance(reference, dict):
        raise ValueError('token reference must be an object')
    if 'key' in reference and (not isinstance(reference['key'], str) or not reference['key']):
        raise ValueError('resource key must be a nonempty string')
    spec = {k:v for k,v in reference.items() if k not in {'android', 'key'}}
    validate_token_mappings({reference.get('android', ''): spec})
    validate_property_token(path, spec)


def has_token_reference(component, path):
    reference = (component.get('source') or {}).get('style_token_references', {}).get(path.removeprefix('style.'))
    if reference is None:
        return False
    try:
        validate_token_reference(reference, path.removeprefix('style.'))
    except (ValueError, KeyError, TypeError):
        return False
    return True


def validate_token_mappings(mappings):
    if not isinstance(mappings, dict):
        raise ValueError('tokenMappings must be an object')
    identifier = r'[A-Za-z_][A-Za-z_0-9]*'
    member = identifier + r'(?:\.' + identifier + r')*'
    for name, spec in mappings.items():
        if not isinstance(name, str) or not re.fullmatch(member, name):
            raise ValueError('tokenMappings require qualified Android references')
        if not isinstance(spec, dict) or spec.get('kind') not in {'color', 'dimension', 'number', 'string'}:
            raise ValueError(f'{name}: unsupported token kind')
        expected = {'kind', 'target'} | ({'sourceUnit', 'targetUnit'} if spec['kind'] == 'dimension' else set())
        if set(spec) - {'fallback'} != expected:
            raise ValueError(f'{name}: invalid token fields')
        if 'fallback' in spec:
            fallback = spec['fallback']
            if spec['kind'] == 'string':
                valid = isinstance(fallback, str)
            elif spec['kind'] == 'color':
                valid = isinstance(fallback, str) and re.fullmatch(r'#[0-9A-Fa-f]{8}', fallback)
            else:
                valid = type(fallback) in (int, float) and math.isfinite(fallback)
            if not valid:
                raise ValueError(f'{name}: resource fallback must match token type')
        if spec['kind'] == 'dimension' and (spec.get('sourceUnit'), spec.get('targetUnit')) not in {('sp', 'fp'), ('dp', 'vp')}:
            raise ValueError(f'{name}: only sp/fp and dp/vp numeric token pairs are supported')
        validate_target(spec['target'])
    return mappings


def validate_property_token(path, spec):
    expected = PROPERTY_TYPES.get(path)
    actual = (spec['kind'], spec.get('sourceUnit'), spec.get('targetUnit'))
    if actual != expected:
        raise ValueError(f'{path}: token type/unit {actual} does not match {expected}')
