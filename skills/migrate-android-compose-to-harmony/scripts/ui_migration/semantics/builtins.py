"""Bounded pure Kotlin operations on already parsed receiver/argument nodes."""
import math
from ui_migration.semantics.literals import display_value
from ui_migration.semantics.syntax import call_from, is_standard_call


def builtin_value(node, context, seen):
    evaluate = lambda child: context.value(child, seen)
    if node.get('kind') == 'qualified' and node['selector'].get('kind') == 'name':
        member = node['selector']['name']
        if member in ('values', 'keys'):
            receiver = evaluate(node['receiver'])
            if isinstance(receiver, dict):
                return list(receiver.values() if member == 'values' else receiver.keys())
        if member in ('size', 'length'):
            receiver = evaluate(node['receiver'])
            if receiver is None and node['safe']:
                return None
            if isinstance(receiver, (list, tuple, dict, str, frozenset)):
                return len(receiver)
    call = call_from(node)
    if call is None:
        return context.unresolved
    empty_collections = {'emptyList': list, 'emptySet': frozenset, 'emptyMap': dict}
    if not call.arguments and call.qualified_name in (
        *empty_collections, *(f'kotlin.collections.{name}' for name in empty_collections)
    ):
        return empty_collections[call.name]()
    if call.receiver is not None and call.name in ('toDp', 'roundToPx') and not call.arguments:
        from ui_migration.semantics.expressions import LayoutDimension
        dimension = evaluate(call.receiver)
        density = context.values.get('LocalDensity.current', {})
        if isinstance(dimension, LayoutDimension) and dimension.unit == 'sp' and isinstance(density, dict):
            font_scale, pixels = density.get('fontScale'), density.get('density')
            if type(font_scale) in (int, float) and font_scale > 0:
                dp = dimension.value * font_scale
                if call.name == 'toDp':
                    return LayoutDimension(dp, 'dp')
                if type(pixels) in (int, float) and pixels > 0:
                    return math.floor(dp * pixels + .5)
    if call.qualified_name in ('listOf', 'kotlin.collections.listOf'):
        return [evaluate(argument['value']) for argument in call.arguments]
    imports = context.values.get('__source_imports') or {}
    if call.name == 'arrayOf' or imports.get(call.name) == 'kotlin.arrayOf':
        if is_standard_call(call, 'kotlin.arrayOf', imports,
                            set(context.bindings) | set(context.values) |
                            {f['name'] for f in context.values.get('__source_functions', [])}):
            return [evaluate(argument['value']) for argument in call.arguments]
    if call.qualified_name in ('mapOf', 'kotlin.collections.mapOf'):
        pairs = [evaluate(a['value']) for a in call.arguments]
        if all(isinstance(p, tuple) and len(p) == 2 and isinstance(p[0], (str, int, bool)) for p in pairs):
            return dict(pairs)
    if call.qualified_name in ('setOf', 'kotlin.collections.setOf'):
        values = [evaluate(a['value']) for a in call.arguments]
        if all(type(v) in (str, int, float, bool) for v in values):
            return frozenset(values)
    if call.qualified_name in ('lazy', 'kotlin.lazy') and len(call.arguments) == 1:
        function = call.arguments[0]['value']
        if function['kind'] == 'lambda':
            return evaluate(function['body'])
    if call.qualified_name in ('run', 'kotlin.run') and len(call.arguments) == 1:
        function = call.arguments[0]['value']
        if function['kind'] == 'lambda' and not function.get('parameters'):
            return evaluate(function['body'])
    if call.receiver is not None and not call.arguments and call.name in ('flatten', 'toSet'):
        receiver = evaluate(call.receiver)
        if isinstance(receiver, (list, tuple, frozenset)):
            if call.name == 'flatten' and all(isinstance(v, (list, tuple, frozenset)) for v in receiver):
                return [item for group in receiver for item in group]
            if call.name == 'toSet' and all(type(v) in (str, int, float, bool) for v in receiver):
                return frozenset(receiver)
    if call.qualified_name in ('floor', 'kotlin.math.floor') and len(call.arguments) == 1:
        value = evaluate(call.arguments[0]['value'])
        return math.floor(value) if type(value) in (int, float) else context.unresolved
    if call.receiver is not None and call.name in ('contains', 'split') and len(call.arguments) == 1:
        receiver = evaluate(call.receiver)
        argument = evaluate(call.arguments[0]['value'])
        if call.name == 'contains' and isinstance(receiver, (list, tuple, dict, str, frozenset)):
            if argument is context.unresolved or (isinstance(receiver, str) and not isinstance(argument, str)):
                return context.unresolved
            if isinstance(receiver, (dict, frozenset)):
                try:
                    hash(argument)
                except TypeError:
                    return context.unresolved
            return argument in receiver
        if call.name == 'split' and isinstance(receiver, str) and isinstance(argument, str) and argument:
            return receiver.split(argument)
    if call.receiver is not None and call.name in ('find', 'firstOrNull', 'indexOfFirst', 'map', 'filter', 'any', 'all', 'none') and len(call.arguments) == 1:
        receiver = evaluate(call.receiver)
        function = call.arguments[0]['value']
        if isinstance(receiver, (list, tuple)) and function['kind'] == 'lambda':
            parameters = function['parameters'] or ['it']
            if len(parameters) != 1:
                return context.unresolved
            result = []
            for index, value in enumerate(receiver):
                local = context.scoped({**context.values, parameters[0]: value})
                matched = local.value(function['body'], seen)
                if call.name == 'map':
                    if matched is context.unresolved:
                        return context.unresolved
                    result.append(matched)
                    continue
                if type(matched) is not bool:
                    return context.unresolved
                if call.name == 'filter':
                    if matched:
                        result.append(value)
                elif call.name in ('any', 'none') and matched:
                    return call.name == 'any'
                elif call.name == 'all' and not matched:
                    return False
                elif call.name in ('find', 'firstOrNull') and matched:
                    return value
                elif call.name == 'indexOfFirst' and matched:
                    return index
            if call.name in ('map', 'filter'):
                return result
            if call.name in ('any', 'all', 'none'):
                return call.name != 'any'
            return -1 if call.name == 'indexOfFirst' else None
    if call.receiver is not None and call.name == 'replace' and len(call.arguments) == 2:
        receiver = evaluate(call.receiver)
        arguments = [evaluate(a['value']) for a in call.arguments]
        if isinstance(receiver, str) and all(isinstance(a, str) for a in arguments):
            return receiver.replace(*arguments)
    if call.receiver is None or call.arguments:
        return context.unresolved
    if call.name not in ('isEmpty', 'isNotEmpty', 'isNullOrEmpty', 'orEmpty', 'toInt', 'toString', 'roundToInt', 'asString', 'trim', 'lowercase', 'uppercase'):
        return context.unresolved
    receiver = evaluate(call.receiver)
    if receiver is None and call.safe:
        return None
    if call.name == 'isNullOrEmpty' and (receiver is None or isinstance(receiver, (list, tuple, dict, str, frozenset))):
        return not receiver
    if isinstance(receiver, str) and call.name in ('trim', 'lowercase', 'uppercase'):
        return {'trim': str.strip, 'lowercase': str.lower, 'uppercase': str.upper}[call.name](receiver)
    if call.name == 'orEmpty' and isinstance(receiver, (list, tuple, dict, str, frozenset)):
        return receiver
    if call.name in ('isEmpty', 'isNotEmpty') and isinstance(receiver, (list, tuple, dict, str, frozenset)):
        return bool(receiver) if call.name == 'isNotEmpty' else not receiver
    if call.name == 'toInt' and type(receiver) in (int, float):
        return int(receiver)
    if call.name == 'roundToInt' and type(receiver) in (int, float):
        return math.floor(receiver + 0.5)
    if call.name == 'toString' and (receiver is None or type(receiver) in (int, float, bool, str)):
        return display_value(receiver)
    if call.name == 'asString':
        if isinstance(receiver, str):
            return receiver
        if isinstance(receiver, dict) and isinstance(receiver.get('__string__'), str):
            return receiver['__string__']
    return context.unresolved
