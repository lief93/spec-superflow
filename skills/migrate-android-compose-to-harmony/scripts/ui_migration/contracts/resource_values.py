"""Typed platform calls used as values, independent of business parameter names."""
import re
from .style_tokens import validate_target, validate_token_mappings


def validate_object_type(source_type, target_type):
    if not isinstance(source_type, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*', source_type):
        raise ValueError('object source type requires a named Kotlin type')
    if not isinstance(target_type, dict) or set(target_type) != {'module', 'export'}:
        raise ValueError('object target type requires module/export')
    validate_target({**target_type, 'member': target_type['export']})


def is_resource_value(value):
    return isinstance(value, dict) and value.get('kind') == 'platform_resource_reference'


def validate_resource_value(value):
    if not is_resource_value(value) or set(value) != {'kind', 'key', 'reference'}:
        raise ValueError('resource value requires kind/key/reference')
    if not isinstance(value['key'], str) or not value['key']:
        raise ValueError('resource key must be a nonempty string')
    spec = value['reference']
    if isinstance(spec, dict) and spec.get('kind') == 'object':
        if set(spec) - {'properties'} != {'kind', 'sourceType', 'targetType', 'target'}:
            raise ValueError('object reference requires sourceType/targetType/target')
        validate_object_type(spec['sourceType'], spec['targetType'])
        validate_target(spec['target'])
        properties = spec.get('properties', {})
        if not isinstance(properties, dict):
            raise ValueError('object properties must be a mapping of source member names')
        for name, reference in properties.items():
            if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name):
                raise ValueError('object property requires a source member identifier')
            validate_resource_value({'kind': 'platform_resource_reference',
                                     'key': value['key'], 'reference': reference})
    else:
        validate_token_mappings({'resource':spec})
    return spec


def resource_property(value, name):
    """Return a declared member reference, never expose resource metadata as source fields."""
    spec = validate_resource_value(value)
    reference = spec.get('properties', {}).get(name) if spec['kind'] == 'object' else None
    if reference is None:
        return None
    return {'kind': 'platform_resource_reference', 'key': value['key'], 'reference': reference}
