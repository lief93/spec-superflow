"""Carry reached value declarations and invocation syntax, not evaluated bodies."""
import copy

from kotlin_psi import parse_expression
from ui_migration.semantics.syntax import call_from, qualified_name
from .source_symbols import resolve_functions, function_identity, matches_argument_shape

BUILTINS = {'listOf': 'kotlin.collections.listOf', 'arrayOf': 'kotlin.arrayOf', 'repeat': 'kotlin.repeat'}

class SourceProgramProjector:
    def __init__(self, payload):
        self.functions = [f for f in payload.get('source_functions', []) if f.get('top_level')]
        self.records = [r for r in payload.get('source_records', []) if r.get('top_level')]
        self.reached = {}
        self.used_records = {}

    @staticmethod
    def scope(declaration):
        return dict(source=declaration.get('source'), imports=declaration.get('imports', {}),
                    package=declaration.get('package'), owner=declaration.get('owner'),
                    wildcards=declaration.get('wildcard_imports', []))

    def record(self, name, scope):
        candidates = resolve_functions(self.records, name, **scope)
        if len(candidates) != 1:
            return None
        record = candidates[0]
        key = record['source'] + ':' + record['name']
        if key not in self.used_records:
            self.used_records[key] = copy.deepcopy(record)
            local = self.used_records[key]
            local['record_types'] = {}
            for field in local['properties']:
                if field.get('default') is not None:
                    field['default_tree'] = self.tree(parse_expression(field['default']), self.scope(record))
                name = field.get('type', '').rstrip('?')
                if target := self.record(name, self.scope(record)):
                    local['record_types'][name] = target
        return key

    def declaration(self, function):
        key = function_identity(function)
        if key in self.reached:
            return key
        self.reached[key] = {'id': key, **{k: copy.deepcopy(function.get(k)) for k in
            ('name', 'source', 'owner', 'receiver', 'return_type', 'annotations', 'parameters')}}
        scope = self.scope(function)
        for parameter in self.reached[key]['parameters']:
            if parameter.get('default'):
                parameter['default_tree'] = self.tree(parse_expression(parameter['default']), scope)
        self.reached[key]['body'] = self.tree(function['body'], scope)
        # Type references are resolved in the declaration's scope, never by a
        # global short-name match. Unsupported compound types are diagnosed later.
        types = [function.get('return_type')] + [p.get('type') for p in function['parameters']]
        self.reached[key]['record_types'] = {}
        for name in types:
            if name and (target := self.record(name.rstrip('?'), scope)):
                self.reached[key]['record_types'][name.rstrip('?')] = target
        return key

    def tree(self, node, scope, bindings=None, seen=(), parameters=()):
        if not isinstance(node, dict):
            return copy.deepcopy(node)
        name = qualified_name(node)
        if bindings and name in bindings and name not in seen and len(seen) < 32:
            value = self.tree(parse_expression(str(bindings[name])), scope, bindings, (*seen, name), parameters)
            if name in parameters:
                value['bound_parameter'] = name
            return value
        result = {k: self.tree(v, scope, bindings, seen, parameters) if isinstance(v, dict) else
                  [self.tree(c, scope, bindings, seen, parameters) if isinstance(c, dict) else c for c in v]
                  if isinstance(v, list) else v for k, v in node.items()}
        call = call_from(node)
        if call and not (bindings and call.qualified_name in bindings):
            candidates = [f for f in resolve_functions(self.functions, call.qualified_name, **scope)
                          if matches_argument_shape(f, call) and 'Composable' not in f.get('annotations', [])]
            if len(candidates) == 1:
                result['source_function'] = self.declaration(candidates[0])
            elif len(candidates) > 1:
                result['source_error'] = 'ambiguous source value method: ' + call.qualified_name
            elif key := self.record(call.qualified_name, scope):
                result['source_record'] = key
            elif call.name in BUILTINS:
                imported = scope.get('imports', {}).get(call.name)
                if call.qualified_name == BUILTINS[call.name] or (call.qualified_name == call.name
                        and imported in (None, BUILTINS[call.name]) and not scope.get('wildcards')):
                    result['source_builtin'] = call.name
        return result

    def reference(self, tree, bindings, environment, parameters=(), source_context=None):
        source = environment.get('__source_file')
        context = source_context or {}
        callers = [f for f in self.functions if f['source'] == source and
                   (function_identity(f) == context.get('declaration_id') if context.get('declaration_id') else f['name'] == context.get('composable'))]
        caller = callers[0] if len(callers) == 1 else {}
        scope = self.scope({**caller, 'source': source, 'owner': environment.get('__source_owner'),
                            'imports': environment.get('__source_imports', {})})
        result = self.tree(tree, scope, bindings, parameters=parameters)

        def has_method(value):
            if isinstance(value, dict):
                return 'source_function' in value or 'source_error' in value or any(has_method(v) for v in value.values())
            return isinstance(value, list) and any(has_method(v) for v in value)

        return result if has_method(result) else None

    def payload(self):
        return {'schema': 'ui-migration.source-program.v1', 'functions': list(self.reached.values()),
                'records': [{'id': key, **value} for key, value in self.used_records.items()]}
