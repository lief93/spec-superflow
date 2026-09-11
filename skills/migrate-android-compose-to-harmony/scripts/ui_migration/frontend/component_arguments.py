"""Default-only arguments for automatically selected target components."""
from .page_model import UNRESOLVED


OMITTED = {'kind': 'omitted_argument'}


def placeholder(kind):
    types = kind.split('|')
    if 'null' in types:
        return None
    defaults = {'string': '', 'ResourceStr': '', 'number': 0, 'Length': 0,
                'boolean': False, 'ResourceColor': '#FF000000',
                '()=>void': {'kind': 'empty_callback'}}
    return next((value for name, value in defaults.items() if name in types), UNRESOLVED)


def bind_default_arguments(adapter, definition, node):
    properties, slots, diagnostics, decisions = {}, {}, [], []

    def report(name, action, expression, reason):
        decisions.append({'parameter':name, 'action':action, 'reason':reason})
        diagnostics.append({'path':'source.component_reuse.parameters.' + name,
            'expression':expression if isinstance(expression, str) else name,
            'reason':'component reuse parameter ' + action + ': ' + reason})

    bindings = node.get('invocation_bindings') or {}
    for parameter in definition.get('parameters', []):
        name = parameter['name']
        report(name, 'source argument omitted', bindings.get(name, parameter.get('default')),
               'automatic reuse uses target defaults only; use an explicit component adapter to pass source values')
    for parameter in adapter.target_parameters:
        name, kind = parameter['name'], parameter['type']
        if not parameter['required']:
            if adapter.call_style == 'positional':
                properties[name] = OMITTED.copy()
            decisions.append({'parameter':name, 'action':'omitted', 'reason':'target default/optional property'})
            continue
        value = placeholder(kind)
        if value is UNRESOLVED or (parameter['slot'] and kind != '()=>void'):
            raise ValueError('required target parameter ' + name + ': ' + kind +
                             ' has no valid default; use an explicit component adapter')
        if parameter['slot']:
            slots[name] = []
        else:
            properties[name] = value
        report(name, 'defaulted', name, 'required target parameter; placeholder=' + repr(value))

    # Preserve middle argument positions while leaving trailing defaults to the callee.
    if adapter.call_style == 'positional':
        while properties and next(reversed(properties.values())) == OMITTED:
            properties.popitem()
    return {'properties':properties, 'slots':slots, 'property_parameters':{},
            'diagnostics':diagnostics, 'binding_decisions':decisions}
