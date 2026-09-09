"""Declaration-based component signatures, independent of the selected UI state."""
import math
import re


class ComponentTypeError(ValueError):
    pass


class TypeParser:
    """A bounded type grammar, not expression evaluation or source-code rewriting."""
    def __init__(self, source):
        self.tokens = re.findall(r'->|[A-Za-z_][\w.]*|[^\s]', source)
        self.index = 0

    def take(self, token=None):
        if self.index == len(self.tokens):
            raise ComponentTypeError('incomplete type')
        value = self.tokens[self.index]
        if token is not None and value != token:
            raise ComponentTypeError('expected ' + token)
        self.index += 1
        return value

    def peek(self, token):
        return self.index < len(self.tokens) and self.tokens[self.index] == token

    def parse(self, depth=0):
        if depth > 16:
            raise ComponentTypeError('type nesting exceeds supported depth')
        if self.peek('@'):
            raise ComponentTypeError('composable/annotated parameter needs a target builder/type mapping')
        if self.peek('('):
            self.take('(')
            arguments = []
            while not self.peek(')'):
                name = 'arg' + str(len(arguments))
                if self.index + 1 < len(self.tokens) and self.tokens[self.index + 1] == ':':
                    name = self.take()
                    self.take(':')
                arguments.append({'name':name, 'type':self.parse(depth + 1)})
                if not self.peek(','):
                    break
                self.take(',')
            self.take(')')
            if self.peek('->'):
                self.take('->')
                result = self.parse(depth + 1)
                node = {'kind':'function', 'arguments':arguments, 'result':result}
            elif len(arguments) == 1:
                node = arguments[0]['type']
            else:
                raise ComponentTypeError('unsupported parenthesized type')
        else:
            name = self.take().removeprefix('kotlin.').removeprefix('collections.')
            scalar = {'String':'string', 'Boolean':'boolean', 'Byte':'number', 'Short':'number',
                      'Int':'number', 'Float':'number', 'Double':'number', 'Unit':'void'}
            if name in scalar:
                node = {'kind':'scalar', 'target':scalar[name], 'source':name}
            elif name in {'List', 'MutableList', 'Array', 'Set', 'MutableSet', 'Map', 'MutableMap'}:
                self.take('<')
                first = self.parse(depth + 1)
                values = [first]
                if name in {'Map', 'MutableMap'}:
                    self.take(',')
                    values.append(self.parse(depth + 1))
                self.take('>')
                node = {'kind':'collection', 'source':name, 'items':values}
            else:
                raise ComponentTypeError('no equivalent target type registered for ' + name)
        if self.peek('?'):
            self.take('?')
            node = {'kind':'nullable', 'inner':node}
        return node


def type_text(node):
    kind = node['kind']
    if kind == 'scalar':
        return node['target']
    if kind == 'nullable':
        return '(' + type_text(node['inner']) + ') | null'
    if kind == 'function':
        return '(' + ', '.join(arg['name'] + ': ' + type_text(arg['type']) for arg in node['arguments']) + ') => ' + type_text(node['result'])
    target = {'List':'ReadonlyArray', 'MutableList':'Array', 'Array':'Array', 'Set':'ReadonlySet',
              'MutableSet':'Set', 'Map':'ReadonlyMap', 'MutableMap':'Map'}[node['source']]
    return target + '<' + ', '.join(type_text(value) for value in node['items']) + '>'


def signature(parameters):
    result = []
    for parameter in parameters:
        entry = {'name':parameter['name'], 'kotlin_type':parameter.get('type'),
                 'default_expression':parameter.get('default'), 'status':'resolved'}
        try:
            parser = TypeParser(parameter.get('type') or '')
            tree = parser.parse()
            if parser.index != len(parser.tokens) or type_text(tree) == 'void':
                raise ComponentTypeError('unsupported parameter type')
            entry.update(type=tree, target_type=type_text(tree))
        except ComponentTypeError as error:
            entry.update(status='unresolved', target_type=None, reason=str(error))
        result.append(entry)
    return result


def value_matches(value, node):
    if node['kind'] == 'nullable':
        return value is None or value_matches(value, node['inner'])
    if node['kind'] == 'function':
        return (isinstance(value, dict) and value.get('kind') == 'empty_callback'
                and type_text(node['result']) == 'void')
    if node['kind'] == 'collection':
        if node['source'] in {'List','MutableList','Array'}:
            return isinstance(value, list) and all(value_matches(v, node['items'][0]) for v in value)
        return False
    source = node['source']
    if source == 'String':
        return type(value) is str
    if source == 'Boolean':
        return type(value) is bool
    if source in {'Byte','Short','Int'}:
        bits = {'Byte':8,'Short':16,'Int':32}[source]
        return type(value) is int and -(2 ** (bits-1)) <= value < 2 ** (bits-1)
    return type(value) in (float, int) and math.isfinite(value)
