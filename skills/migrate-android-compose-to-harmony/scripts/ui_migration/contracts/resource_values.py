"""Typed platform calls used as values, independent of business parameter names."""
from .style_tokens import validate_token_mappings


def is_resource_value(value):
    return isinstance(value, dict) and value.get('kind') == 'platform_resource_reference'


def validate_resource_value(value):
    if not is_resource_value(value) or set(value) != {'kind', 'key', 'reference'}:
        raise ValueError('resource value requires kind/key/reference')
    if not isinstance(value['key'], str) or not value['key']:
        raise ValueError('resource key must be a nonempty string')
    validate_token_mappings({'resource':value['reference']})
    return value['reference']
