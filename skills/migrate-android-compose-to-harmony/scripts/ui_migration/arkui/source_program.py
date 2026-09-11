"""Bounded typed lowering of source value methods carried by page JSON.

Unknown calls/types fail closed. A successful call retains its method boundary;
it is never replaced by the selected preview's evaluated return value.
"""
import copy
import json
import re

from ui_migration.naming import source_identifier
from ui_migration.contracts.identity import require_safe_relative_source


class UnsupportedValueMethod(ValueError):
    pass

# Module-level globals used by the value emitter and native UI emitters. Source
# declarations must not shadow conversions, SDK imports or enum references.
INTRINSICS = {
    'String', 'Number', 'Math', 'undefined', 'NaN', 'Infinity',
    'drawing', 'LengthMetrics', 'UIContext', 'Color', 'Alignment',
    'GradientDirection', 'BorderStyle', 'HitTestMode', 'FontWeight', 'FontStyle',
    'TextDecorationType', 'ImageFit', 'CheckBoxShape', 'ToggleType', 'ProgressType',
    'ItemAlign', 'VerticalAlign', 'HorizontalAlign', 'LineBreakStrategy',
    'TextAlign', 'TextOverflow', 'FlexAlign', 'ColorFilter', 'BlendMode',
    'ImageRenderMode', 'LocalizedAlignment', 'FlexDirection', 'ScrollDirection',
    'BarState', 'Visibility', 'Direction', 'EnterKeyType',
}

def identifier(name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name):
        raise UnsupportedValueMethod('unsupported source identifier: ' + str(name))
    return source_identifier(name)


class SourceProgramEmitter:
    def __init__(self, program, diagnostic, reserved=()):
        if program and program.get('schema') != 'ui-migration.source-program.v1':
            raise ValueError('unsupported source program schema; regenerate page JSON')
        self.functions = {f['id']: f for f in program.get('functions', [])}
        self.records = {r['id']: r for r in program.get('records', [])}
        self.diagnostic = diagnostic
        self.reserved = set(reserved) | INTRINSICS
        self.symbols = {source_identifier(d['name']) for d in [*self.functions.values(), *self.records.values()]}
        self.parameter_types = lambda component: {}
        self.clear()

    def clear(self):
        self.declarations = {}
        self.signatures = {}
        self.active = set()
        self.consumed = []
        self.failures = []
        self.budget = 0

    def tick(self):
        self.budget += 1
        if self.budget > 10000:
            raise UnsupportedValueMethod('source value method exceeds bounded expression budget')

    def expression(self, component, path):
        tree = component.get('source', {}).get('method_references', {}).get(path)
        if tree is None:
            return None
        checkpoint = (copy.deepcopy(self.declarations), dict(self.signatures))
        self.budget = 0
        try:
            env = {}
            def referenced(value, name):
                if isinstance(value, dict):
                    return value.get('bound_parameter') == name or any(referenced(v, name) for v in value.values())
                return isinstance(value, list) and any(referenced(v, name) for v in value)
            for name, kind in self.parameter_types(component).items():
                if referenced(tree, name):
                    env[name] = (self.binding_name(name, env), self.type(kind), False)
            code, kind = self.value(tree, env)
            expected = {'content.text': 'String', 'content.content_description': 'String',
                        'typography.font_size_sp': 'number', 'typography.line_height_sp': 'number',
                        'typography.letter_spacing_sp': 'number', 'surface.corner_radius_dp': 'number'}
            required = expected.get(path)
            if required is None or not (kind == required or required == 'number' and kind in ('Int', 'Double')):
                raise UnsupportedValueMethod('unsupported value method consumer/type: ' + path + '/' + kind)
            self.consumed.append({'component_id': component['id'], 'path': path, 'expression': code})
            return code
        except (UnsupportedValueMethod, KeyError, TypeError, RecursionError) as error:
            self.declarations, self.signatures = checkpoint
            self.active.clear()
            reason = 'source value method not preserved: ' + str(error)
            self.failures.append({'component_id': component['id'], 'path': path, 'reason': reason})
            self.diagnostic(component, 'source.method_references.' + path, reason)
            return None

    def name(self, declaration):
        name = identifier(declaration['name'])
        if name in self.reserved:
            raise UnsupportedValueMethod('source value name conflicts with UI/import: ' + name)
        previous = self.declarations.get(name)
        if previous and previous['id'] != declaration['id']:
            raise UnsupportedValueMethod('ambiguous target declaration name: ' + name)
        return name

    def binding_name(self, name, env):
        target = identifier(name)
        if target in INTRINSICS or target in self.symbols or target in {v[0] for v in env.values()}:
            raise UnsupportedValueMethod('source binding has a target name collision: ' + name)
        return target

    def type(self, name, record_types=None):
        if not isinstance(name, str):
            raise UnsupportedValueMethod('missing explicit source type')
        name = name.strip()
        if name.endswith('?'):
            return self.type(name[:-1], record_types) + '?'
        match = re.fullmatch(r'(?:List|Array)<(.+)>', name)
        if match:
            return 'List<' + self.type(match[1], record_types) + '>'
        if name in ('String', 'Boolean', 'Int', 'Double', 'Unit'):
            return name
        target = (record_types or {}).get(name)
        if target:
            return self.record(target)
        raise UnsupportedValueMethod('unsupported source type: ' + name)

    def target_type(self, kind):
        if kind.endswith('?'):
            return self.target_type(kind[:-1]) + ' | null'
        if kind.startswith('List<'):
            return '(' + self.target_type(kind[5:-1]) + ')[]' if kind[5:-1].endswith('?') else self.target_type(kind[5:-1]) + '[]'
        return {'String': 'string', 'Boolean': 'boolean', 'Int': 'number', 'Double': 'number', 'Unit': 'void'}.get(kind, kind)

    @staticmethod
    def compatible(actual, expected):
        return actual == expected or expected.endswith('?') and actual in ('null', expected[:-1])

    def require(self, actual, expected):
        if not self.compatible(actual, expected):
            raise UnsupportedValueMethod('source type mismatch: ' + actual + ' -> ' + expected)

    def record(self, key):
        record = self.records[key]
        name = self.name(record)
        if name in self.declarations:
            return name
        if not record.get('plain') or key in self.active:
            raise UnsupportedValueMethod('record needs unsupported body/inheritance or recursive type: ' + name)
        self.active.add(key)
        fields, parameters, body = [], [], []
        kinds, field_names = {}, set()
        for field in record['properties']:
            field_name = identifier(field['name'])
            if field_name in field_names or field_name in INTRINSICS or field_name in self.symbols:
                raise UnsupportedValueMethod('record field/constructor binding collision: ' + field_name)
            field_names.add(field_name)
            kind = self.type(field['type'], record.get('record_types'))
            kinds[field['name']] = kind
            fields.append('  ' + ('' if field.get('mutable') else 'readonly ') + field_name + ': ' + self.target_type(kind) + ';')
            parameter = field_name + ': ' + self.target_type(kind)
            if field.get('default') is not None:
                value, actual = self.value(field['default_tree'], {n: (identifier(n), t, False) for n, t in kinds.items() if n != field['name']})
                self.require(actual, kind)
                parameter += ' = ' + value
            parameters.append(parameter)
            body.append('    this.' + field_name + ' = ' + field_name + ';')
        code = 'export class ' + name + ' {\n' + '\n'.join(fields) + '\n  constructor(' + ', '.join(parameters) + ') {\n' + '\n'.join(body) + '\n  }\n}'
        self.declarations[name] = {'id': key, 'name': name, 'source': require_safe_relative_source(record['source']), 'code': code, 'kind': 'record', 'fields': kinds}
        self.active.remove(key)
        return name

    def function(self, key):
        function = self.functions[key]
        name = self.name(function)
        if key in self.signatures:
            return self.signatures[key]
        if key in self.active:
            raise UnsupportedValueMethod('recursive value method is not supported: ' + name)
        if function.get('owner') or function.get('receiver') or function.get('annotations'):
            raise UnsupportedValueMethod('member/extension/annotated value method requires a mapping: ' + name)
        self.active.add(key)
        env, parameters, kinds = {}, [], []
        for parameter in function['parameters']:
            p = self.binding_name(parameter['name'], env)
            kind = self.type(parameter['type'], function.get('record_types'))
            declaration = p + ': ' + self.target_type(kind)
            if parameter.get('default') is not None:
                code, actual = self.value(parameter['default_tree'], env)
                self.require(actual, kind)
                declaration += ' = ' + code
            parameters.append(declaration)
            kinds.append(kind)
            env[parameter['name']] = (p, kind, False)
        body = function['body']
        expected = self.type(function['return_type'], function.get('record_types')) if function.get('return_type') else None
        if body['kind'] == 'block':
            expected = expected or 'Unit'
            lines, returns = self.statements(body, env, expected)
            if expected != 'Unit' and not returns:
                raise UnsupportedValueMethod('not all paths return a value: ' + name)
        else:
            code, actual = self.value(body, env)
            expected = expected or actual
            self.require(actual, expected)
            lines = ['return ' + code + ';']
        code = 'export function ' + name + '(' + ', '.join(parameters) + '): ' + self.target_type(expected) + ' {\n' + '\n'.join('  ' + line for line in lines) + '\n}'
        self.declarations[name] = {'id': key, 'name': name, 'source': require_safe_relative_source(function['source']), 'code': code, 'kind': 'function'}
        self.active.remove(key)
        self.signatures[key] = (name, kinds, expected)
        return self.signatures[key]

    def arguments(self, tree, parameters, kinds, env):
        raw = tree.get('arguments', [])
        assigned = {}
        for index, argument in enumerate(raw):
            name = argument.get('name') or (parameters[index]['name'] if index < len(parameters) else None)
            if name is None or name in assigned or name not in {p['name'] for p in parameters}:
                raise UnsupportedValueMethod('invalid source call arguments')
            assigned[name] = argument['value']
        ordered = []
        for parameter, kind in zip(parameters, kinds):
            value = assigned.get(parameter['name'])
            if value is None:
                if parameter.get('default') is not None:
                    ordered.append('undefined')
                    continue
                raise UnsupportedValueMethod('missing source argument: ' + parameter['name'])
            code, actual = self.value(value, env)
            self.require(actual, kind)
            ordered.append(code)
        # Reordering named arguments is safe only for this pure expression subset.
        return ', '.join(ordered)

    def value(self, tree, env):
        self.tick()
        if tree.get('bound_parameter') in env:
            return env[tree['bound_parameter']][:2]
        if tree.get('source_error'):
            raise UnsupportedValueMethod(tree['source_error'])
        kind = tree['kind']
        call = tree['selector'] if kind == 'qualified' and tree.get('selector', {}).get('kind') == 'call' else tree
        if key := tree.get('source_function'):
            name, kinds, result = self.function(key)
            if name in env:
                raise UnsupportedValueMethod('source method is shadowed by a local value: ' + name)
            return name + '(' + self.arguments(call, self.functions[key]['parameters'], kinds, env) + ')', result
        if key := tree.get('source_record'):
            name = self.record(key)
            parameters = self.records[key]['properties']
            kinds = list(self.declarations[name]['fields'].values())
            return 'new ' + name + '(' + self.arguments(call, parameters, kinds, env) + ')', name
        if kind == 'name':
            if tree['name'] not in env:
                raise UnsupportedValueMethod('unbound source value: ' + tree['name'])
            return env[tree['name']][:2]
        if kind == 'literal':
            text = tree.get('text', '')
            if 'parts' in tree:
                parts = []
                for part in tree['parts']:
                    if part['kind'] == 'text':
                        parts.append(json.dumps(part['value'], ensure_ascii=True))
                    else:
                        code, actual = self.value(part['value'], env)
                        if actual not in ('String', 'Boolean', 'Int'):
                            raise UnsupportedValueMethod('unsupported string interpolation type: ' + actual)
                        parts.append('String(' + code + ')')
                return '(' + ' + '.join(parts or ['""']) + ')', 'String'
            if text in ('true', 'false'):
                return text, 'Boolean'
            if text == 'null':
                return text, 'null'
            if re.fullmatch(r'[0-9]+', text) and int(text) <= 2147483647:
                return text, 'Int'
            if re.fullmatch(r'[0-9]+\.[0-9]+', text):
                return text, 'Double'
            raise UnsupportedValueMethod('unsupported Kotlin literal: ' + text)
        if kind == 'qualified' and tree['selector']['kind'] == 'name':
            receiver, actual = self.value(tree['receiver'], env)
            field = tree['selector']['name']
            if tree.get('safe') or actual.endswith('?'):
                raise UnsupportedValueMethod('nullable property access requires explicit lowering')
            if field in ('size', 'length') and (actual.startswith('List<') or actual == 'String'):
                return receiver + '.length', 'Int'
            record = self.declarations.get(actual)
            if not record or field not in record.get('fields', {}):
                raise UnsupportedValueMethod('unsupported property: ' + actual + '.' + field)
            return receiver + '.' + identifier(field), record['fields'][field]
        if tree.get('source_builtin') in ('listOf', 'arrayOf') and tree['source_builtin'] not in env:
            values = [self.value(a['value'], env) for a in call['arguments']]
            if not values or len({v[1] for v in values}) != 1:
                raise UnsupportedValueMethod('collection requires a nonempty homogeneous element type')
            return '[' + ', '.join(v[0] for v in values) + ']', 'List<' + values[0][1] + '>'
        if kind == 'binary':
            left, a = self.value(tree['left'], env)
            right, b = self.value(tree['right'], env)
            operator = tree['operator']
            if operator in ('==', '!=') and 'null' in (a, b) and (a.endswith('?') or b.endswith('?') or a == b):
                return '(' + left + (' === ' if operator == '==' else ' !== ') + right + ')', 'Boolean'
            if operator == '+' and a == b == 'String':
                return '(' + left + ' + ' + right + ')', 'String'
            if a == b and a in ('Int', 'Double') and operator in ('+', '-', '*'):
                if a == 'Int':
                    code = 'Math.imul(' + left + ', ' + right + ')' if operator == '*' else '((' + left + ' ' + operator + ' ' + right + ') | 0)'
                else:
                    code = '(' + left + ' ' + operator + ' ' + right + ')'
                return code, a
            if a == b and a in ('Int', 'Double', 'String', 'Boolean') and operator in ('==', '!=', '<', '<=', '>', '>='):
                if operator not in ('==', '!=') and a == 'Boolean':
                    raise UnsupportedValueMethod('invalid Boolean comparison')
                operator = {'==': '===', '!=': '!=='}.get(operator, operator)
                return '(' + left + ' ' + operator + ' ' + right + ')', 'Boolean'
            if a == b == 'Boolean' and operator in ('&&', '||'):
                return '(' + left + ' ' + operator + ' ' + right + ')', 'Boolean'
            raise UnsupportedValueMethod('unsupported typed binary operation: ' + a + ' ' + operator + ' ' + b)
        if kind == 'unary' and tree['operator'] in ('!', '-', '+'):
            code, actual = self.value(tree['value'], env)
            operator = tree['operator']
            if operator == '!' and actual == 'Boolean':
                return '(!' + code + ')', actual
            if operator in ('-', '+') and actual in ('Int', 'Double'):
                return '(' + operator + code + (' | 0)' if actual == 'Int' else ')'), actual
            raise UnsupportedValueMethod('unsupported unary type: ' + actual)
        if kind == 'if':
            condition, actual = self.value(tree['condition'], env)
            self.require(actual, 'Boolean')
            yes, a = self.value(self.single(tree['yes']), env)
            no, b = self.value(self.single(tree['no']), env)
            self.require(a, b)
            return '(' + condition + ' ? ' + yes + ' : ' + no + ')', a
        if kind == 'when':
            branches = self.when_branches(tree, env)
            code, actual = self.value(self.single(branches[-1][1]), env)
            for condition, body in reversed(branches[:-1]):
                yes, kind = self.value(self.single(body), env)
                self.require(kind, actual)
                code = '(' + condition + ' ? ' + yes + ' : ' + code + ')'
            return code, actual
        raise UnsupportedValueMethod('unsupported source expression: ' + str(tree.get('text') or kind)[:300])

    def when_branches(self, tree, env):
        subject = tree['subject']
        if subject['kind'] not in ('name', 'literal', 'missing'):
            raise UnsupportedValueMethod('when subject needs single-evaluation lowering')
        value, kind = self.value(subject, env) if subject['kind'] != 'missing' else (None, None)
        if kind is not None and kind not in ('String', 'Boolean', 'Int', 'Double'):
            raise UnsupportedValueMethod('unsupported when subject type: ' + kind)
        entries = tree['entries']
        if not entries or not entries[-1]['otherwise'] or any(e['otherwise'] for e in entries[:-1]):
            raise UnsupportedValueMethod('when needs an explicit final else branch')
        branches = []
        for entry in entries:
            conditions = []
            for condition in entry['conditions']:
                code, actual = self.value(condition, env)
                self.require(actual, kind or 'Boolean')
                conditions.append('(' + value + ' === ' + code + ')' if value else code)
            branches.append((' || '.join(conditions), entry['body']))
        return branches

    @staticmethod
    def single(tree):
        if tree.get('kind') == 'block' and len(tree['statements']) == 1:
            return tree['statements'][0]
        return tree

    def statements(self, tree, env, result_type):
        self.tick()
        env = dict(env)
        nodes = tree['statements'] if tree['kind'] == 'block' else [tree]
        lines, returns = [], False
        for node in nodes:
            if returns:
                raise UnsupportedValueMethod('unreachable statement after return')
            kind = node['kind']
            if kind == 'local':
                if node.get('delegated') or node['name'] in env:
                    raise UnsupportedValueMethod('delegated or shadowed local variable')
                code, actual = self.value(node['value'], env)
                if node.get('type'):
                    self.require(actual, self.type(node['type']))
                name = self.binding_name(node['name'], env)
                env[node['name']] = (name, actual, bool(node.get('mutable')))
                lines.append(('let ' if node.get('mutable') else 'const ') + name + ': ' + self.target_type(actual) + ' = ' + code + ';')
            elif kind == 'return':
                code, actual = self.value(node['value'], env)
                self.require(actual, result_type)
                lines.append('return ' + code + ';')
                returns = True
            elif kind == 'binary' and node['operator'] == '=' and node['left']['kind'] == 'name':
                variable = env.get(node['left']['name'])
                if not variable or not variable[2]:
                    raise UnsupportedValueMethod('assignment requires a mutable local')
                code, actual = self.value(node['right'], env)
                self.require(actual, variable[1])
                lines.append(variable[0] + ' = ' + code + ';')
            elif kind == 'if':
                condition, actual = self.value(node['condition'], env)
                self.require(actual, 'Boolean')
                yes, a = self.statements(node['yes'], env, result_type)
                no, b = self.statements(node['no'], env, result_type) if node['no']['kind'] != 'missing' else ([], False)
                lines.extend(['if (' + condition + ') {', *['  ' + line for line in yes], '}'])
                if no:
                    lines.extend(['else {', *['  ' + line for line in no], '}'])
                returns = a and b
            elif kind == 'for':
                code, actual = self.value(node['collection'], env)
                if not actual.startswith('List<') or node.get('parameter') in env:
                    raise UnsupportedValueMethod('for requires a collection and an unshadowed item')
                name = self.binding_name(node['parameter'], env)
                body, _ = self.statements(node['body'], {**env, node['parameter']: (name, actual[5:-1], False)}, result_type)
                lines.extend(['for (const ' + name + ' of ' + code + ') {', *['  ' + line for line in body], '}'])
            elif node.get('source_builtin') == 'repeat' and 'repeat' not in env:
                arguments = node.get('arguments', [])
                if len(arguments) != 2 or arguments[1]['value']['kind'] != 'lambda':
                    raise UnsupportedValueMethod('repeat requires count and one lambda')
                count, actual = self.value(arguments[0]['value'], env)
                self.require(actual, 'Int')
                action = arguments[1]['value']
                if len(action['parameters']) > 1:
                    raise UnsupportedValueMethod('repeat needs one index parameter')
                parameter = (action['parameters'] or ['it'])[0]
                name = self.binding_name(parameter, env)
                if parameter in env:
                    raise UnsupportedValueMethod('repeat index shadows a source local')
                limit = '_repeatCount'
                while limit in env or limit == name:
                    limit = '_' + limit
                body, _ = self.statements(action['body'], {**env, parameter: (name, 'Int', False)}, result_type)
                lines.extend(['{', '  const ' + limit + ': number = ' + count + ';',
                    '  for (let ' + name + ': number = 0; ' + name + ' < ' + limit + '; ' + name + '++) {',
                    *['    ' + line for line in body], '  }', '}'])
            elif kind == 'when':
                branches = self.when_branches(node, env)
                complete = True
                for index, (condition, branch) in enumerate(branches):
                    body, returned = self.statements(branch, env, result_type)
                    complete = complete and returned
                    if len(branches) == 1:
                        lines.extend(body)
                        continue
                    prefix = 'else' if index == len(branches) - 1 else ('if' if index == 0 else 'else if') + ' (' + condition + ')'
                    lines.extend([prefix + ' {', *['  ' + line for line in body], '}'])
                returns = complete
            else:
                raise UnsupportedValueMethod('unsupported source statement: ' + str(node.get('text') or kind)[:300])
        return lines, returns

    def code(self):
        return '\n\n'.join(d['code'] for d in self.declarations.values())

    def report(self):
        return {'functions': [{k: d[k] for k in ('name', 'source', 'kind')} for d in self.declarations.values()],
                'consumed': self.consumed, 'unsupported': self.failures,
                'scope': 'bounded pure value methods; root UI state and external effects are not reconstructed'}
