"""Shared lexical source resolution; ambiguous symbols are never picked arbitrarily.

This is not compiler type resolution. Overloads remain candidates for the bounded
argument evaluator; UI expansion must report ambiguity rather than merge bodies.
"""
from collections import defaultdict, Counter
from kotlin_psi import parse_declarations, parse_expression
from page_component_catalog import CONTROL_FAMILIES
from ui_migration.semantics.syntax import call_from, qualified_name


def function_identity(function):
    return f"{function['source']}:{function['start']}:{function['name']}"


def function_fq_name(function):
    return '.'.join(filter(None, (function.get('package'), function.get('owner'), function['name'])))


def resolve_functions(functions, name, source=None, imports=None, package=None, wildcards=(), owner=None):
    imports = imports or {}
    prefix, dot, suffix = name.partition('.')
    imported = imports.get(prefix)
    target = imported + ('.' + suffix if dot else '') if imported else None
    if dot:
        targets = {target or name, '.'.join(filter(None, (package, name)))}
        return [f for f in functions if function_fq_name(f) in targets]
    local = [f for f in functions if f['source']==source and f['name']==name
             and f.get('owner') in (None, owner)]
    if local:
        owned = [f for f in local if owner and f.get('owner')==owner]
        return owned or local
    if target:
        return [f for f in functions if function_fq_name(f)==target]
    same_package = [f for f in functions if f.get('package')==package and f['name']==name and not f.get('owner')]
    if same_package:
        return same_package
    return [f for f in functions if f.get('package') in wildcards and f['name']==name and not f.get('owner')]


def expression_calls(node):
    if not isinstance(node, dict):
        return
    if node.get('kind')=='callable_reference':
        from ui_migration.semantics.syntax import Call
        yield Call(node['name'], (), reference=True)
        return
    call = call_from(node)
    if call:
        yield call
        if call.receiver:
            yield from expression_calls(call.receiver)
        for argument in call.arguments:
            yield from expression_calls(argument['value'])
        return
    for value in node.values():
        if isinstance(value, dict):
            yield from expression_calls(value)
        elif isinstance(value, list):
            for child in value:
                yield from expression_calls(child)


def expression_names(node):
    if isinstance(node, dict):
        name = qualified_name(node)
        if name:
            yield name
        for value in node.values():
            yield from expression_names(value)
    elif isinstance(node, list):
        for value in node:
            yield from expression_names(value)


def matches_argument_shape(function, call):
    parameters = function['parameters']
    names = {p['name'] for p in parameters}
    if len(call.arguments)>len(parameters):
        return False
    assigned = set()
    for index, argument in enumerate(call.arguments):
        name = argument.get('name')
        if name:
            if name not in names:
                return False
        else:
            # Kotlin's trailing lambda binds the final function parameter.
            name = parameters[-1]['name'] if argument['value'].get('kind')=='lambda' and index==len(call.arguments)-1 else parameters[index]['name']
        if name in assigned:
            return False
        assigned.add(name)
    return all(p['name'] in assigned or p.get('default') is not None for p in parameters)


class SourceSymbolIndex:
    @classmethod
    def from_root(cls, root):
        return cls({path.relative_to(root).as_posix(): path.read_text(encoding='utf-8')
                    for path in sorted(root.rglob('*.kt'))
                    if not {'build', '.gradle', '.git'}.intersection(path.relative_to(root).parts)})

    def __init__(self, files):
        self.syntax = {path: parse_declarations(text) for path, text in files.items()
                       if path.endswith(('.kt', '.kts'))}
        self.functions = []
        self.properties = []
        self._resolved = {}
        for path, syntax in self.syntax.items():
            for function in syntax['functions']:
                self.functions.append({**function, 'source':path, 'imports':syntax['imports'],
                    'wildcard_imports':syntax['wildcardImports']})
            self.properties.extend({**p, 'source':path, 'package':syntax['package'],
                                    'imports':syntax['imports'], 'wildcard_imports':syntax['wildcardImports']}
                                   for p in syntax['globalProperties'])
        self.by_source = defaultdict(list)
        for function in self.functions:
            self.by_source[function['source']].append(function)
        self.edges = {}
        self.roles = {function_identity(f): self._initial_role(f) for f in self.functions}
        for function in self.functions:
            edges = []
            for call in expression_calls(function['body']):
                targets = self.resolve(call, function)
                edges.append((call, targets))
            for property in self.referenced_properties(function):
                for call in expression_calls(parse_expression(property['expression'])):
                    edges.append((call, self.resolve(call, property)))
            self.edges[function_identity(function)] = edges
        # Helpers that emit content inherit its role; value factories never become UI.
        changed = True
        while changed:
            changed = False
            for function in self.functions:
                identity = function_identity(function)
                if self.roles[identity] != 'unknown':
                    continue
                if any(self.roles[function_identity(t)]=='content'
                       for _, targets in self.edges[identity] for t in targets):
                    self.roles[identity] = 'content'
                    changed = True

    def _type(self, text, source, seen=()):
        if not text or text in seen:
            return text
        syntax = self.syntax[source]
        imported = syntax['imports'].get(text)
        for path, candidate in self.syntax.items():
            for alias in candidate.get('typeAliases', []):
                fq = '.'.join(filter(None, (candidate['package'], alias['name'])))
                if (path==source and alias['name']==text) or imported==fq or (
                    candidate['package']==syntax['package'] and alias['name']==text):
                    return self._type(alias['type'], path, seen+(text,))
        return imported or text

    def _initial_role(self, function):
        receiver = self._type(function.get('receiver'), function['source']) or ''
        result = self._type(function.get('return_type'), function['source'])
        if receiver.rsplit('.',1)[-1]=='Modifier' or (result or '').rsplit('.',1)[-1]=='Modifier':
            return 'modifier'
        if result and result!='Unit':
            return 'value'
        annotations = {self._type(a, function['source']).rsplit('.',1)[-1] for a in function['annotations']}
        if 'Composable' in annotations or receiver.rsplit('.',1)[-1] in {
            'LazyListScope','LazyGridScope','LazyStaggeredGridScope'}:
            return 'content'
        # Receiver-lambda builders describe UI without being composable themselves.
        for parameter in function['parameters']:
            kind = self._type(parameter.get('type'), function['source']) or ''
            if '@Composable' in kind or any(kind.rsplit('.',1)[-1]==scope or scope+'.' in kind for scope in (
                'LazyListScope','LazyGridScope','LazyStaggeredGridScope')):
                return 'content'
        return 'unknown' if function['body']['kind']=='block' else 'value'

    def resolve(self, call, function):
        key = (function['source'], function.get('owner'), call.qualified_name, call.receiver is not None, call.reference,
               tuple((a.get('name'),a['value'].get('kind')) for a in call.arguments))
        if key in self._resolved:
            return self._resolved[key]
        syntax = self.syntax[function['source']]
        scope = dict(source=function['source'], imports=syntax['imports'], package=syntax['package'],
                     wildcards=syntax['wildcardImports'], owner=function.get('owner'))
        targets = []
        if call.receiver:
            targets = resolve_functions(self.functions, call.qualified_name, **scope)
            if not targets:
                targets = [f for f in resolve_functions(self.functions, call.name, **scope) if f.get('receiver')]
        else:
            targets = resolve_functions(self.functions, call.name, **scope)
        targets = [f for f in targets if call.reference or matches_argument_shape(f, call)]
        self._resolved[key] = targets
        return targets

    def visible_properties(self, function, name):
        syntax = self.syntax[function['source']]
        return resolve_functions(self.properties, name, source=function['source'], imports=syntax['imports'],
                                 package=syntax['package'], wildcards=syntax['wildcardImports'],
                                 owner=function.get('owner'))

    def referenced_properties(self, function):
        pending = [(function, function['body'])]
        seen = set()
        while pending:
            scope, expression = pending.pop()
            parameters = {p['name'] for p in scope.get('parameters', [])}
            for name in set(expression_names(expression)) - parameters:
                properties = self.visible_properties(scope, name)
                if len(properties)!=1:
                    continue
                property = properties[0]
                identity = (property['source'],property.get('owner'),property['name'])
                if identity in seen:
                    continue
                seen.add(identity)
                yield property
                pending.append((property, parse_expression(property['expression'])))

    def global_values(self, function):
        names = {p['name'] for p in self.properties} | set(self.syntax[function['source']]['imports'])
        values = {}
        for name in names:
            candidates = self.visible_properties(function, name)
            if len(candidates)==1:
                values[name] = candidates[0]['expression']
        return values

    def ui_functions(self, source):
        return [f for f in self.by_source[source] if self.roles[function_identity(f)]=='content']

    def trace(self, source, name):
        pending = [f for f in self.by_source[source] if f['name']==name]
        visited, edges, unresolved = {}, [], []
        while pending:
            function = pending.pop()
            identity = function_identity(function)
            if identity in visited:
                continue
            visited[identity] = {'id':identity, 'source':function['source'], 'name':function['name'],
                'line':function['line'], 'role':self.roles[identity]}
            for call, targets in self.edges[identity]:
                edge = {'caller':identity, 'expression':call.qualified_name,
                        'targets':[function_identity(t) for t in targets]}
                edge['status'] = 'resolved' if len(targets)==1 else 'ambiguous' if targets else 'external_or_dynamic'
                edges.append(edge)
                if len(targets)>1:
                    unresolved.append({**edge, 'reason':'source symbol needs overload/receiver resolution'})
                pending.extend(targets)
        return {'root':{'source':source,'name':name}, 'definitions':list(visited.values()),
                'edges':edges, 'unresolved':unresolved,
                'scope':'syntactic dependencies; selected-state evaluation decides active branches'}

    def reconcile_content(self, trace, reached, calls=None):
        reached = {(item['source'], item['composable']) for item in reached}
        missing = [item for item in trace['definitions'] if item['role']=='content'
                   and (item['source'], item['name']) not in reached]
        missing_controls = []
        if calls is not None:
            native = {name for family, names in CONTROL_FAMILIES.items() if family!='internal' for name in names}
            actual = Counter((c['source'],c['composable'],c['component']) for c in calls)
            expected = Counter()
            functions = {function_identity(f):f for f in self.functions}
            for item in trace['definitions']:
                if item['role']!='content':
                    continue
                function = functions[item['id']]
                for call in expression_calls(function['body']):
                    name = function['imports'].get(call.name, call.qualified_name).rsplit('.',1)[-1]
                    if name in native and not self.resolve(call,function):
                        expected[function['source'],function['name'],name] += 1
            missing_controls = [{'source':source,'function':name,'component':component,
                                 'expected_count':count,'inventoried_count':actual[source,name,component]}
                                for (source,name,component),count in expected.items()
                                if actual[source,name,component]<count]
        return {'stage':'before_page_generation', 'verdict':'fail' if missing or missing_controls else 'pass',
                'missing_content_definitions':missing,
                'missing_native_controls':missing_controls,
                'scope':'reachable content definitions and catalogued native call counts; not runtime geometry or full Kotlin typing'}
