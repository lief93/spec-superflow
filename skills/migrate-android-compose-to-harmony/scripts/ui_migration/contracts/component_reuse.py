"""Single-JSON contract for an explicitly selected, existing ArkUI component."""
import math
import re

from .style_tokens import validate_target


def identifier(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', value)


def validate_property(value):
    from .resource_values import is_resource_value, validate_resource_value
    if is_resource_value(value):
        validate_resource_value(value)
        return
    if isinstance(value, dict) and value == {'kind':'empty_callback'}:
        return
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if isinstance(value, dict) and set(value) == {'kind', 'target'} and value['kind'] == 'resource':
        validate_target(value['target'])
        return
    raise ValueError('component property requires a literal or structured resource reference')


def validate_reuse(record):
    if not isinstance(record, dict) or record.get('schema') != 'ui-migration.component-reuse.v1':
        raise ValueError('invalid component reuse declaration')
    if record.get('call_style', 'properties') not in {'properties', 'positional'}:
        raise ValueError('invalid component call style')
    if record.get('call_style') == 'positional' and record.get('slots'):
        raise ValueError('positional reuse does not support content slots')
    for field in ('adapter_id', 'definition_id', 'android'):
        if not isinstance(record.get(field), str) or not record[field]:
            raise ValueError('component reuse requires ' + field)
    target = record.get('target')
    if not isinstance(target, dict) or set(target) != {'module', 'export'}:
        raise ValueError('component target requires module/export')
    validate_target({**target, 'member': target['export']})
    properties, slots = record.get('properties'), record.get('slots')
    if not isinstance(properties, dict) or not isinstance(slots, dict):
        raise ValueError('component reuse requires properties and slots objects')
    if set(properties) & set(slots):
        raise ValueError('component properties and slots must have distinct names')
    bindings = record.get('property_parameters', {})
    if not isinstance(bindings, dict) or any(k not in properties or not identifier(v) for k, v in bindings.items()):
        raise ValueError('invalid component property parameter bindings')
    seen = set()
    for name, value in properties.items():
        if not identifier(name):
            raise ValueError('invalid component property name')
        validate_property(value)
    for name, roots in slots.items():
        if not identifier(name) or not isinstance(roots, list):
            raise ValueError('invalid component slot')
        for root in roots:
            if not isinstance(root, str) or root in seen:
                raise ValueError('component slot roots must be unique IDs')
            seen.add(root)
    return record
