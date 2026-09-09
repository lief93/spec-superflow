"""Evaluate only inventory-proven record constructors and pure source helpers."""
from kotlin_psi import parse_expression
from ui_migration.semantics.expressions import LayoutDimension, LayoutExpressionError
from ui_migration.semantics.syntax import call_from, qualified_name
from ui_migration.frontend.source_symbols import resolve_functions


class SourceRecord(dict):
    """Constructor field order is retained for Kotlin data-class destructuring."""
    pass


def matches_source_type(value, name):
    if value is None:
        return name.endswith('?')
    name = name.removesuffix('?')
    from ui_migration.contracts.resource_values import is_resource_value, validate_resource_value
    if is_resource_value(value):
        spec = validate_resource_value(value)
        expected = {'Color': ('color', None), 'String': ('string', None),
                    'Dp': ('dimension', 'dp'), 'TextUnit': ('dimension', 'sp'),
                    'Int': ('number', None), 'Long': ('number', None),
                    'Float': ('number', None), 'Double': ('number', None)}
        return expected.get(name) == (spec['kind'], spec.get('sourceUnit'))
    checks = {
        'Int': lambda v: type(v) is int, 'Long': lambda v: type(v) is int,
        'Float': lambda v: type(v) in (int, float), 'Double': lambda v: type(v) in (int, float),
        'String': lambda v: isinstance(v, str), 'Boolean': lambda v: type(v) is bool,
        'Color': lambda v: isinstance(v, str) and len(v) == 9 and v.startswith('#'),
        'Dp': lambda v: isinstance(v, LayoutDimension) and v.unit == 'dp',
        'TextUnit': lambda v: isinstance(v, LayoutDimension) and v.unit == 'sp',
    }
    return checks[name](value) if name in checks else True


def bind_arguments(call, parameters, context, seen, *, partial=False):
    names = {p['name'] for p in parameters}
    if len(call.arguments) > len(parameters) or any(a.get('name') and a['name'] not in names for a in call.arguments):
        raise LayoutExpressionError('source argument signature mismatch')
    local = dict(context.values)
    scoped = context.scoped(local, {})
    for index, parameter in enumerate(parameters):
        name = parameter['name']
        argument = call.argument(name, index)
        # A trailing lambda belongs to the last parameter, even after omitted defaults.
        if call.arguments and call.arguments[-1].get('name') is None and call.arguments[-1]['value'].get('kind')=='lambda':
            if index==len(parameters)-1:
                argument = call.arguments[-1]['value']
            elif index==len(call.arguments)-1:
                argument = None
        try:
            if argument is not None:
                local[name] = context.value(argument, seen)
            elif isinstance(parameter.get('default'), str):
                local[name] = scoped.value(parse_expression(parameter['default']), seen)
            else:
                raise LayoutExpressionError('missing source parameter: ' + name)
        except LayoutExpressionError:
            if not partial:
                raise
            local[name] = context.unresolved
            expression = argument.get('text') if argument is not None else parameter.get('default')
            if isinstance(expression, str) and expression.strip() != name:
                scoped.bindings[name] = expression
    return scoped


def source_function_scope(call, context, seen, receiver_type=None):
    owner = qualified_name(call.receiver) if call.receiver else context.values.get('__source_owner')
    inventory = context.values.get('__source_functions', [])
    caller = next((f for f in inventory + context.values.get('__source_properties', [])
                   if f['source']==context.values.get('__source_file')), {})
    scope = dict(source=context.values.get('__source_file'), imports=context.values.get('__source_imports'),
                 package=caller.get('package'), wildcards=caller.get('wildcard_imports', []),
                 owner=context.values.get('__source_owner'))
    functions = resolve_functions(inventory, call.qualified_name, **scope)
    if not functions and call.receiver is not None:
        functions = [f for f in resolve_functions(inventory, call.name, **scope) if f.get('receiver')]
    if receiver_type:
        functions = [f for f in functions if (f.get('receiver') or '').rsplit('.',1)[-1] == receiver_type
                     or not f.get('receiver') and (f.get('return_type') or '').rsplit('.',1)[-1] == receiver_type]
    elif call.receiver is None:
        functions = [f for f in functions if not f.get('receiver') and f.get('owner') == owner]
    else:
        functions = [f for f in functions if f.get('owner') == owner or f.get('receiver')]
    same_file = [f for f in functions if f['source'] == context.values.get('__source_file')]
    if same_file:
        functions = same_file
    candidates = []
    for function in functions:
        identity = f"function:{function['source']}:{function['line']}"
        if identity in seen or len(seen) >= 64:
            raise LayoutExpressionError('cyclic or over-deep source function: ' + function['name'])
        path = seen + (identity,)
        try:
            scoped = bind_arguments(call, function['parameters'], context, path, partial=True)
            globals = function.get('global_values', {})
            parameter_names = {parameter['name'] for parameter in function['parameters']}
            if context.values.get('__source_properties'):
                for name in globals.keys() - parameter_names:
                    scoped.bindings.pop(name, None)
            else:
                scoped.bindings = {**scoped.bindings, **globals}
            for name in globals.keys() - parameter_names:
                scoped.values[name] = context.unresolved
            for parameter in function['parameters']:
                value = scoped.values[parameter['name']]
                # The evaluator retains opaque resource IDs as names, not Android ints.
                # Type filtering resolves overloads; it is not a Kotlin type checker.
                if len(functions) > 1 and not matches_source_type(value, parameter.get('type', '')):
                    raise LayoutExpressionError('source overload type mismatch')
                if parameter['type'] == 'Dp' and not (isinstance(value, LayoutDimension) and value.unit == 'dp'):
                    raise LayoutExpressionError('Dp overload mismatch')
                if parameter['type'] == 'Shape' and not isinstance(value, dict):
                    raise LayoutExpressionError('Shape overload mismatch')
            if function.get('receiver') and receiver_type != 'Modifier':
                scoped.values['this'] = context.value(call.receiver, path)
                if isinstance(scoped.values['this'], dict):
                    for name, value in scoped.values['this'].items():
                        if name not in parameter_names:
                            scoped.values[name] = value
            scoped.values.update(__source_file=function['source'], __source_owner=function.get('owner'),
                                 __source_imports=function.get('imports', {}))
            candidates.append((scoped, function['body'], path))
        except LayoutExpressionError:
            continue
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        raise LayoutExpressionError('ambiguous source overload: ' + call.name)
    return None


def source_property_value(name, context, seen):
    functions = context.values.get('__source_functions', [])
    source = context.values.get('__source_file')
    properties = context.values.get('__source_properties', [])
    caller = next((f for f in functions + properties if f['source']==source), {})
    candidates = resolve_functions(properties, name, source=source,
        imports=context.values.get('__source_imports'), package=caller.get('package'),
        wildcards=caller.get('wildcard_imports', []), owner=context.values.get('__source_owner'))
    if len(candidates)!=1:
        return context.unresolved
    property = candidates[0]
    identity = 'property:' + property['source'] + ':' + str(property.get('owner')) + ':' + property['name']
    if identity in seen or len(seen)>=64:
        raise LayoutExpressionError('cyclic or over-deep source property: ' + name)
    local = dict(context.values)
    # Caller-local values must not shadow the declaration's global dependencies.
    for candidate in properties:
        local.pop(candidate['name'], None)
    local.update(__source_file=property['source'], __source_owner=property.get('owner'),
                 __source_imports=property.get('imports', {}))
    return context.scoped(local, {}).value(property.get('value_syntax') or parse_expression(property['expression']), seen+(identity,))


def source_call_value(call, context, seen):
    if call is None:
        return context.unresolved
    from ui_migration.semantics.callables import SourceCallable, call_target
    target = call_target(call, context, seen)
    if isinstance(target, SourceCallable):
        identity = 'closure:' + target['expression']
        if identity in seen or len(seen)>=64:
            raise LayoutExpressionError('cyclic or over-deep callable')
        if target.syntax['kind']=='lambda':
            return target.bind(call.arguments, context, seen).value(target.syntax['body'], seen+(identity,))
        from ui_migration.semantics.syntax import Call
        reference = Call(target.syntax['name'], call.arguments,
                         target.syntax.get('receiver') if target.syntax.get('receiver',{}).get('kind')!='missing' else None)
        scope = source_function_scope(reference, target.context, seen+(identity,))
        if scope:
            scoped, body, path = scope
            return scoped.value(body, path)
    if call.receiver is not None and call.name.startswith('component') and not call.arguments:
        index = call.name.removeprefix('component')
        if index.isdigit():
            value = context.value(call.receiver, seen)
            if isinstance(value, SourceRecord) and 0 < int(index) <= len(value):
                return list(value.values())[int(index) - 1]
    inventory = context.values.get('__source_value_inventory') or {}
    function = source_function_scope(call, context, seen)
    if function:
        scoped, body, path = function
        return scoped.value(body, path)
    owner = qualified_name(call.receiver) if call.receiver else None
    identity = 'call:' + call.qualified_name
    if identity in seen or len(seen) >= 64:
        raise LayoutExpressionError('cyclic or over-deep source call: ' + call.qualified_name)
    path = seen + (identity,)
    constructor = (context.values.get('__constructors__') or {}).get(call.qualified_name)
    if isinstance(constructor, dict):
        fields = constructor.get('fields')
        if not isinstance(fields, list) or not all(isinstance(field, str) for field in fields):
            return context.unresolved
        scoped = bind_arguments(call, [{'name': name} for name in fields], context, path)
        record = {'__type': call.qualified_name, **{name: scoped.values[name] for name in fields}}
        string_field = constructor.get('string_field')
        if isinstance(record.get(string_field), str):
            record['__string__'] = record[string_field]
        return record
    records = [item for item in inventory.get('classes', []) if item['name'] == call.qualified_name]
    if len(records) == 1:
        scoped = bind_arguments(call, records[0]['properties'], context, path, partial=True)
        return SourceRecord((p['name'], scoped.values[p['name']]) for p in records[0]['properties'])
    classes = [item for item in inventory.get('classes', []) if item.get('name') == owner]
    if len(classes) == 1:
        factories = [factory for factory in classes[0].get('factories', [])
                     if factory.get('name') == call.name and factory.get('static_record') is True]
        if len(factories) != 1:
            return context.unresolved
        factory = factories[0]
        scoped = bind_arguments(call, factory.get('parameters', []), context, path)
        for name, expression in factory.get('local_values', {}).items():
            try:
                scoped.values[name] = scoped.value(parse_expression(expression), path)
            except LayoutExpressionError:
                scoped.values[name] = context.unresolved
        constructor_call = call_from(parse_expression(factory['return_expression']))
        if constructor_call is None or constructor_call.qualified_name != owner:
            return context.unresolved
        record_scope = bind_arguments(constructor_call, classes[0].get('properties', []), scoped, path, partial=True)
        return {field['name']: record_scope.values[field['name']] for field in classes[0].get('properties', [])}
    helpers = [item for item in inventory.get('string_helpers', []) if item.get('name') == call.name]
    if call.receiver is not None and len(helpers) == 1 and helpers[0].get('kind') == 'group_string':
        helper = helpers[0]
        value = context.value(call.receiver, path)
        scoped = bind_arguments(call, helper.get('parameters', []), context, path)
        group, separator = scoped.values.get(helper['group_parameter']), scoped.values.get(helper['separator_parameter'])
        if isinstance(value, str) and type(group) is int and group > 0 and isinstance(separator, str):
            return separator.join(value[i:i + group] for i in range(0, len(value), group))
    return context.unresolved
