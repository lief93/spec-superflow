"""Typed, declarative cross-platform style references, not executable snippets."""
import re


PROPERTY_TYPES = {
    'typography.font_size_sp': ('dimension', 'sp', 'fp'),
    'typography.line_height_sp': ('dimension', 'sp', 'fp'),
    'typography.letter_spacing_sp': ('dimension', 'sp', 'fp'),
    'typography.color': ('color', None, None),
    'typography.font_weight': ('number', None, None),
    'typography.font_family': ('string', None, None),
    'surface.background': ('color', None, None),
    'surface.corner_radius_dp': ('dimension', 'dp', 'vp'),
}


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
        if set(spec) != expected:
            raise ValueError(f'{name}: invalid token fields')
        if spec['kind'] == 'dimension' and (spec.get('sourceUnit'), spec.get('targetUnit')) not in {('sp', 'fp'), ('dp', 'vp')}:
            raise ValueError(f'{name}: only sp/fp and dp/vp numeric token pairs are supported')
        target = spec['target']
        if not isinstance(target, dict) or set(target) != {'module', 'export', 'member'}:
            raise ValueError(f'{name}: target requires module/export/member')
        for field, pattern in [('export', identifier), ('member', member), ('module', r'[@A-Za-z0-9_./-]+')]:
            if not isinstance(target[field], str) or not re.fullmatch(pattern, target[field]):
                raise ValueError(f'{name}: unsafe or invalid target {field}')
    return mappings


def validate_property_token(path, spec):
    expected = PROPERTY_TYPES.get(path)
    actual = (spec['kind'], spec.get('sourceUnit'), spec.get('targetUnit'))
    if actual != expected:
        raise ValueError(f'{path}: token type/unit {actual} does not match {expected}')
