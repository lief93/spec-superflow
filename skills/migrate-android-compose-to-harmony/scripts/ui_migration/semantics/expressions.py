"""Project Kotlin PSI layout expressions into one ordered, fixed-state modifier chain."""
import json
import operator
from dataclasses import dataclass
from kotlin_psi import parse_expression
from ui_migration.semantics.literals import literal_value
from ui_migration.semantics.syntax import qualified_name
from ui_migration.semantics.errors import LayoutExpressionError, KnownValueError


DP_UNSPECIFIED = object()


@dataclass(frozen=True)
class LayoutDimension:
    value: float
    unit: str


def dimension_operation(op, left, right):
    if isinstance(left, LayoutDimension) and isinstance(right, LayoutDimension):
        if left.unit != right.unit:
            raise LayoutExpressionError('layout arithmetic cannot mix dimension units')
        if op in ('+', '-'):
            return LayoutDimension(left.value + right.value if op == '+' else left.value - right.value, left.unit)
        if op == '/':
            return left.value / right.value
        comparison = {'==': operator.eq, '!=': operator.ne, '<': operator.lt, '<=': operator.le,
                      '>': operator.gt, '>=': operator.ge}.get(op)
        if comparison:
            return comparison(left.value, right.value)
    elif isinstance(left, LayoutDimension) and type(right) in (int, float) and op in ('*', '/'):
        return LayoutDimension(left.value * right if op == '*' else left.value / right, left.unit)
    elif isinstance(right, LayoutDimension) and type(left) in (int, float) and op == '*':
        return LayoutDimension(left * right.value, right.unit)
    raise LayoutExpressionError('unsupported dimension arithmetic')


LAYOUT_ARGUMENT_FIELDS = {'contentAlignment': 'alignment', 'alignment': 'alignment',
                         'contentPadding': 'padding_dp',
                         'horizontalAlignment': 'alignment', 'verticalAlignment': 'alignment',
                         'horizontalArrangement': 'horizontal_arrangement', 'verticalArrangement': 'vertical_arrangement'}


def needs_layout_projection(node):
    if node.get('modifier_projection'):
        return False
    return any(m.get('syntax_expression') for m in node.get('modifiers') or []) or bool(
        set(((node.get('arguments') or {}).get('semantic') or {})) & LAYOUT_ARGUMENT_FIELDS.keys())


class LayoutExpressions:
    def __init__(self, bindings, values, evaluate_leaf, unresolved, serialize_modifier=None, *, evaluate_node=None, expand_chain=None, value_syntax=None, coalesce_value=None):
        self.bindings = bindings
        self.values = values
        self.evaluate_leaf = evaluate_leaf
        self.unresolved = unresolved
        self.modifier_receivers = {}
        self.serialize_modifier = serialize_modifier
        self.evaluate_node = evaluate_node
        self.expand_chain = expand_chain
        self.value_syntax = value_syntax
        self.coalesce_value = coalesce_value

    def leaf(self, node, seen):
        if self.evaluate_node is not None:
            return self.evaluate_node(node, self, seen)
        return self.evaluate_leaf(node.get('text', ''), self.values)

    def scoped(self, values, bindings=None):
        result = LayoutExpressions(self.bindings if bindings is None else bindings, values,
                                 self.evaluate_leaf, self.unresolved, self.serialize_modifier,
                                 evaluate_node=self.evaluate_node, expand_chain=self.expand_chain, value_syntax=self.value_syntax,
                                 coalesce_value=self.coalesce_value)
        result.modifier_receivers = dict(self.modifier_receivers)
        return result

    def bound(self, name, seen):
        if name in seen or len(seen) >= 64:
            raise LayoutExpressionError(f'cyclic or over-deep layout reference: {name}')
        expression = self.bindings.get(name)
        if not isinstance(expression, str) or expression.strip() == name:
            raise LayoutExpressionError(f'unknown layout reference: {name}')
        return parse_expression(expression), seen + (name,)

    def value(self, node, seen=()):
        known = self.values.get(node.get('text'), self.unresolved)
        if known is not self.unresolved:
            return known
        path = qualified_name(node)
        if path in self.values and self.values[path] is not self.unresolved:
            return self.values[path]
        if path == 'Dp.Unspecified':
            return DP_UNSPECIFIED
        kind = node['kind']
        if kind in ('lambda', 'callable_reference'):
            from ui_migration.semantics.callables import SourceCallable
            return SourceCallable(node, self)
        if kind == 'index':
            receiver = self.value(node['receiver'], seen)
            indices = [self.value(index, seen) for index in node['indices']]
            if len(indices)==1 and isinstance(receiver, (list, tuple, dict)):
                try:
                    return receiver[indices[0]]
                except (IndexError, KeyError, TypeError):
                    raise LayoutExpressionError('unknown collection index')
        if kind == 'object':
            record = {}
            scoped = self.scoped({**self.values, 'this': record})
            for property in node['properties']:
                try:
                    value = scoped.value(property['value'], seen) if not property['mutable'] else self.unresolved
                except LayoutExpressionError:
                    value = self.unresolved
                record[property['name']] = value
                scoped.values.setdefault(property['name'], value)
            return record
        if kind == 'literal':
            try:
                return literal_value(node, lambda child: self.value(child, seen))
            except (ValueError, TypeError) as error:
                raise LayoutExpressionError(str(error)) from error
        if kind == 'name':
            name = node['name']
            known = self.values.get(name, self.unresolved)
            if known is not self.unresolved:
                return known
            if name in self.bindings:
                bound, path = self.bound(name, seen)
                return self.value(bound, path)
            result = self.leaf(node, seen)
            if result is not self.unresolved:
                return result
            raise LayoutExpressionError(f'unknown fixed-state name: {name}')
        if kind in ('if', 'when'):
            return self.value(self.branch(node, seen), seen)
        if kind == 'return':
            return self.value(node['value'], seen)
        if kind == 'block':
            scoped, terminal = self.block(node, seen)
            return scoped.value(terminal, seen)
        if kind == 'try' and not node.get('hasFinally'):
            try:
                return self.value(node['body'], seen)
            except KnownValueError:
                handlers = [h for h in node['catches'] if h['type'] in ('IllegalArgumentException', 'java.lang.IllegalArgumentException')]
                if handlers:
                    return self.value(handlers[0]['body'], seen)
                raise
        if kind == 'qualified' and node['selector']['kind'] == 'name':
            if node['selector']['name'] in ('dp', 'sp'):
                scalar = self.value(node['receiver'], seen)
                if type(scalar) in (int, float):
                    return LayoutDimension(scalar, node['selector']['name'])
            try:
                receiver = self.value(node['receiver'], seen)
                key = node['selector']['name']
                if receiver is None and node['safe']:
                    return None
                if isinstance(receiver, dict) and key in receiver:
                    if receiver[key] is not self.unresolved:
                        return receiver[key]
                    raise LayoutExpressionError('unknown fixed-state member: ' + key)
            except LayoutExpressionError:
                pass
        if kind == 'binary':
            op = node['operator']
            left = self.value(node['left'], seen)
            if op == '&&' and left is False:
                return False
            if op == '||' and left is True:
                return True
            if op == '?:':
                if self.coalesce_value:
                    result = self.coalesce_value(left, node['right'], self, seen)
                    if result is not self.unresolved:
                        return result
                return left if left is not None else self.value(node['right'], seen)
            right = self.value(node['right'], seen)
            if op == 'to':
                return (left, right)
            if op == '+' and isinstance(left, frozenset) and isinstance(right, frozenset):
                return left | right
            if op in ('==', '!=') and (left is None or right is None):
                return (left is right) if op == '==' else (left is not right)
            if op in ('in', '!in'):
                if not isinstance(right, (list, tuple, dict, str)):
                    raise LayoutExpressionError('membership requires a known collection')
                try:
                    return (left in right) if op == 'in' else (left not in right)
                except TypeError as error:
                    raise LayoutExpressionError(str(error)) from error
            if op in ('==', '!=') and (left is DP_UNSPECIFIED or right is DP_UNSPECIFIED):
                return (left is right) if op == '==' else (left is not right)
            if isinstance(left, LayoutDimension) or isinstance(right, LayoutDimension):
                try:
                    return dimension_operation(op, left, right)
                except ZeroDivisionError as error:
                    raise LayoutExpressionError('division by zero in layout expression') from error
            if op in ('&&', '||'):
                if type(left) is not bool or type(right) is not bool:
                    raise LayoutExpressionError('layout logical operands must be booleans')
                return left and right if op == '&&' else left or right
            operations = {'==': operator.eq, '!=': operator.ne, '<': operator.lt, '<=': operator.le,
                          '>': operator.gt, '>=': operator.ge, '+': operator.add, '-': operator.sub,
                          '*': operator.mul, '/': operator.truediv, '%': operator.mod}
            if op in operations:
                try:
                    if op == '/' and type(left) is int and type(right) is int:
                        return int(left / right)
                    return operations[op](left, right)
                except (TypeError, ZeroDivisionError) as error:
                    raise LayoutExpressionError(str(error)) from error
        if kind == 'unary':
            value = self.value(node['value'], seen)
            if node['operator'] == '!' and type(value) is bool:
                return not value
            if node['operator'] in ('-', '+') and type(value) in (int, float):
                return -value if node['operator'] == '-' else value
            if node['operator'] in ('-', '+') and isinstance(value, LayoutDimension):
                return LayoutDimension(-value.value if node['operator'] == '-' else value.value, value.unit)
        if kind == 'type_check':
            value = self.value(node['value'], seen)
            if not isinstance(value, dict) or not isinstance(value.get('__type'), str):
                raise LayoutExpressionError('type check requires a known constructor')
            matches = value['__type'] == node['type']
            return not matches if node['negated'] else matches
        # Framework constants/constructors use the existing bounded value adapters.
        # Control flow and reference lookup above never fall back to text scanning.
        if kind in ('literal', 'call', 'qualified'):
            result = self.leaf(node, seen)
            if result is not self.unresolved:
                return result
        raise LayoutExpressionError('unknown fixed-state value: ' + node.get('text', kind))

    def block(self, node, seen):
        statements = node.get('statements', [])
        if not statements:
            raise LayoutExpressionError('empty value block')
        scoped = self.scoped(dict(self.values))
        mutable = set()
        def statement_value(statement):
            kind = statement['kind']
            if kind == 'missing':
                return
            if kind == 'local':
                value = scoped.value(statement['value'], seen)
                if statement.get('delegated'):
                    if not isinstance(value, dict) or 'value' not in value:
                        raise LayoutExpressionError('unknown delegated source value')
                    value = value['value']
                scoped.values[statement['name']] = value
                if statement['mutable']:
                    mutable.add(statement['name'])
            elif kind in ('if', 'when'):
                statement_value(scoped.branch(statement, seen))
            elif kind == 'block':
                for child in statement['statements']:
                    statement_value(child)
            elif kind == 'binary' and statement['operator'] == '=' and statement['left'].get('name') in mutable:
                scoped.values[statement['left']['name']] = scoped.value(statement['right'], seen)
            else:
                raise LayoutExpressionError('value block cannot execute nonlocal effects')
        for statement in statements[:-1]:
            statement_value(statement)
        terminal = statements[-1]
        return scoped, terminal['value'] if terminal['kind'] == 'return' else terminal

    def branch(self, node, seen):
        if node['kind'] == 'when':
            has_subject = node['subject']['kind'] != 'missing'
            subject = self.value(node['subject'], seen) if has_subject else True
            for entry in node['entries']:
                if entry['otherwise']:
                    return entry['body']
                for condition in entry['conditions']:
                    value = self.value(condition, seen)
                    if not has_subject and type(value) is not bool:
                        raise LayoutExpressionError('subjectless when requires boolean conditions')
                    if (condition['kind'] == 'type_check' and value is True) or (
                            condition['kind'] != 'type_check' and value == subject):
                        return entry['body']
            raise LayoutExpressionError('fixed state matches no when branch')
        value = self.value(node['condition'], seen)
        if type(value) is not bool:
            raise LayoutExpressionError('layout condition requires an explicit boolean state')
        return node['yes'] if value else node['no']

    def render(self, node, seen=()):
        kind = node['kind']
        if self.evaluate_node is not None:
            try:
                value = self.value(node, seen)
                if self.value_syntax is not None:
                    syntax = self.value_syntax(value)
                    if syntax is not None:
                        return syntax
                if isinstance(value, LayoutDimension):
                    return f'{value.value:g}.{value.unit}'
                if isinstance(value, str) and len(value) == 9 and value.startswith('#'):
                    return 'Color(0x' + value[1:] + ')'
            except LayoutExpressionError:
                pass
        if kind == 'name':
            name = node['name']
            if name in self.bindings and self.bindings[name].strip() != name:
                bound, path = self.bound(name, seen)
                return self.render(bound, path)
            value = self.values.get(name, self.unresolved)
            if value is None or type(value) in (bool, int, float, str):
                if isinstance(value, str) and len(value) == 9 and value.startswith('#'):
                    try:
                        int(value[1:], 16)
                        return 'Color(0x' + value[1:] + ')'
                    except ValueError:
                        pass
                return json.dumps(value)
            return node['text']
        if kind in ('if', 'when'):
            return self.render(self.branch(node, seen), seen)
        if kind == 'block' and len(node['statements']) == 1:
            return self.render(node['statements'][0], seen)
        if kind == 'qualified':
            receiver = self.render(node['receiver'], seen)
            selector = node['selector']
            if selector.get('kind') == 'name' and selector.get('name') in ('width', 'height'):
                constructor = parse_expression(receiver)
                if constructor.get('kind') == 'qualified' and constructor['receiver'].get('text') == 'androidx.compose.ui.unit':
                    constructor = constructor['selector']
                if constructor.get('kind') == 'call' and constructor['callee'].get('name') == 'DpSize':
                    args = constructor['arguments']
                    member = selector['name']
                    selected = next((a['value'] for a in args if a.get('name') == member), None)
                    positional = [a['value'] for a in args if not a.get('name')]
                    index = 0 if member == 'width' else 1
                    if selected is None and len(positional) > index:
                        selected = positional[index]
                    if selected is not None:
                        return self.render(selected, seen)
            suffix = selector['text'] if selector['kind'] == 'name' else self.render(selector, seen)
            return receiver + ('?.' if node['safe'] else '.') + suffix
        if kind == 'call':
            if node['trailingLambda']:
                return node['text']
            args = [(a.get('name') + ' = ' if a.get('name') else '') + self.render(a['value'], seen)
                    for a in node['arguments']]
            return node['callee']['text'] + '(' + ', '.join(args) + ')'
        if kind == 'binary':
            expanded = {**node, 'left': parse_expression(self.render(node['left'], seen)),
                        'right': parse_expression(self.render(node['right'], seen))}
            value = self.value(expanded, seen)
            return f'{value.value:g}.{value.unit}' if isinstance(value, LayoutDimension) else json.dumps(value)
        if kind == 'unary':
            return node['operator'] + self.render(node['value'], seen)
        return node.get('text', '')

    def chain(self, node, seen=()):
        if node['kind'] == 'name':
            if node['name'] in self.modifier_receivers:
                return list(self.modifier_receivers[node['name']])
            if node['name'] == 'Modifier':
                return []
            bound, path = self.bound(node['name'], seen)
            return self.chain(bound, path)
        if node['kind'] in ('if', 'when'):
            return self.chain(self.branch(node, seen), seen)
        if node['kind'] == 'block':
            scoped, terminal = self.block(node, seen)
            return scoped.chain(terminal, seen)
        if node['kind'] == 'return':
            return self.chain(node['value'], seen)
        if node.get('text') == 'Modifier.Companion':
            return []
        if node['kind']=='call' and self.expand_chain is not None:
            expanded = self.expand_chain(node, self, seen, [])
            if expanded is not self.unresolved:
                return expanded
        if node['kind'] != 'qualified' or node['safe'] or node['selector']['kind'] != 'call':
            raise LayoutExpressionError('unsupported modifier expression: ' + node.get('text', ''))
        prefix = self.chain(node['receiver'], seen)
        call = node['selector']
        name = call['callee'].get('name')
        if name == 'let':
            if len(call['arguments']) != 1 or call['arguments'][0]['value']['kind'] != 'lambda':
                raise LayoutExpressionError('Modifier.let requires a single lambda')
            function = call['arguments'][0]['value']
            parameters = function['parameters'] or ['it']
            if len(parameters) != 1:
                raise LayoutExpressionError('Modifier.let needs one receiver parameter')
            scoped = self.scoped(self.values)
            scoped.modifier_receivers = {**self.modifier_receivers, parameters[0]: prefix}
            return scoped.chain(function['body'], seen)
        if name == 'then':
            if len(call['arguments']) != 1 or call['trailingLambda']:
                raise LayoutExpressionError('Modifier.then requires one modifier expression')
            return prefix + self.chain(call['arguments'][0]['value'], seen)
        if self.expand_chain is not None:
            expanded = self.expand_chain(node, self, seen, prefix)
            if expanded is not self.unresolved:
                return expanded
        if self.serialize_modifier is None:
            raise LayoutExpressionError('modifier serialization adapter is required')
        # This tokenizer only sees an already-selected single operation; it cannot
        # traverse branches or resolve bindings independently.
        operation = self.serialize_modifier('Modifier.' + self.render(call, seen))
        if len(operation) != 1 or operation[0]['name'] != name:
            raise LayoutExpressionError('cannot serialize selected modifier: ' + call['text'])
        return prefix + operation
