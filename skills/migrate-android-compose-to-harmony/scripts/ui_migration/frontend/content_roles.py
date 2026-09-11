"""Prove non-emitting expressions without treating @Composable as a visual node."""


def returns_only_value(node):
    kind = node.get('kind')
    # Creating a lambda/reference does not execute its body.
    if kind in {'name', 'lambda', 'callable_reference'}:
        return True
    if kind == 'literal':
        return all(p.get('kind') == 'text' or (
            p.get('kind') == 'expression' and returns_only_value(p['value'])) for p in node.get('parts', []))
    if kind == 'qualified':
        return returns_only_value(node['receiver']) and returns_only_value(node['selector'])
    if kind == 'if':
        return all(returns_only_value(node[key]) for key in ('condition', 'yes', 'no') if node.get(key))
    # Calls and blocks remain subject to content/dependency analysis, even if
    # their result is assigned to a local variable.
    return False


def refine_value_roles(index, functions):
    """Use PSI expression positions, without guessing from callable names.

    An argument/initializer needs a value, not a child builder. Known UI effects
    take precedence; mixed value/UI functions are retained with a diagnostic.
    This is bounded source analysis, not Kotlin compiler return-type inference.
    """
    from .source_symbols import function_identity
    from ui_migration.semantics.syntax import call_from
    from page_component_catalog import CONTROL_FAMILIES
    from kotlin_psi import parse_expression

    native = {name for family, names in CONTROL_FAMILIES.items() if family != 'internal' for name in names}
    emitting, dependencies, value_uses = set(), {}, set()
    invoked_slots = {function_identity(f): set() for f in functions}
    callable_bodies = {}
    unresolved_invocations = set()

    def invoked_body(call, function):
        if call.name != 'invoke' or call.receiver is None:
            return None
        key = (function_identity(function), call.receiver.get('text'),
               tuple((a.get('name'), a['value'].get('text')) for a in call.arguments))
        if key not in callable_bodies:
            from .values import value_resolver
            from ui_migration.semantics.callables import SourceCallable, call_target
            context = value_resolver(function.get('global_values', {}), {
                '__source_functions': functions, '__source_properties': index.properties,
                '__source_file': function['source'], '__source_owner': function.get('owner'),
                '__source_imports': function.get('imports', {})})
            target = call_target(call, context)
            callable_bodies[key] = None
            if isinstance(target, SourceCallable):
                syntax, values = None, target.context.values
                if target.syntax['kind'] == 'lambda':
                    syntax = target.syntax['body']
                else:
                    from .source_values import source_function_scope
                    from ui_migration.semantics.syntax import Call
                    receiver = target.syntax.get('receiver')
                    reference = Call(target.syntax['name'], call.arguments,
                        receiver if receiver and receiver.get('kind') != 'missing' else None)
                    from ui_migration.semantics.expressions import LayoutExpressionError
                    try:
                        resolved = source_function_scope(reference, target.context, ())
                    except LayoutExpressionError:
                        resolved = None
                    if resolved is not None:
                        context, syntax, _ = resolved
                        values = context.values
                if syntax is not None:
                    scope = {**function, 'source': values.get('__source_file'),
                             'owner': values.get('__source_owner'), 'imports': values.get('__source_imports', {})}
                    callable_bodies[key] = (syntax, scope)
        return callable_bodies[key]

    def executed_arguments(call, targets, function):
        imported = function.get('imports', {}).get(call.name, call.qualified_name)
        if not targets and imported.rsplit('.', 1)[-1] in native | {
                'run', 'let', 'with', 'apply', 'also', 'remember', 'forEach', 'forEachIndexed', 'repeat'}:
            return [a['value'] for a in call.arguments]
        arguments = []
        for target in targets:
            for j, parameter in enumerate(target['parameters']):
                if parameter['name'] not in invoked_slots.get(function_identity(target), ()):
                    continue
                value = call.argument(parameter['name'], j)
                if call.arguments and not call.arguments[-1].get('name') and call.arguments[-1]['value'].get('kind') == 'lambda':
                    if j == len(target['parameters'])-1:
                        value = call.arguments[-1]['value']
                    elif j == len(call.arguments)-1:
                        value = None
                if value is not None:
                    arguments.append(value)
        return arguments

    def executed_calls(node, function, seen=(), classification_owner=None):
        if not isinstance(node, dict) or node.get('kind') in {'lambda', 'callable_reference'}:
            return
        classification_owner = classification_owner or function_identity(function)
        call = call_from(node)
        if call:
            yield call, function
            yield from executed_calls(call.receiver, function, seen, classification_owner)
            body = invoked_body(call, function)
            if body is not None:
                syntax, scope = body
                identity = (scope['source'], syntax.get('text'))
                if identity not in seen:
                    yield from executed_calls(syntax, scope, (*seen, identity), classification_owner)
            elif call.name == 'invoke' and call.receiver is not None:
                unresolved_invocations.add(classification_owner)
            targets = index.resolve(call, function)
            executed = executed_arguments(call, targets, function)
            for argument in call.arguments:
                value = argument['value']
                if value.get('kind') == 'lambda':
                    if any(value is item for item in executed):
                        yield from executed_calls(value.get('body'), function, seen, classification_owner)
                else:
                    yield from executed_calls(value, function, seen, classification_owner)
            return
        for value in node.values():
            if isinstance(value, dict):
                yield from executed_calls(value, function, seen, classification_owner)
            elif isinstance(value, list):
                for child in value:
                    yield from executed_calls(child, function, seen, classification_owner)

    # Only proven slot invocation executes a supplied lambda; annotations alone
    # also describe lambdas that a function stores or returns for later use.
    changed = True
    while changed:
        before = len(emitting) + sum(map(len, invoked_slots.values()))
        for function in functions:
            identity = function_identity(function)
            dependencies[identity] = set()
            slots = {p['name'] for p in function['parameters'] if '@Composable' in (p.get('type') or '')}
            for call, scope in executed_calls(function['body'], function):
                targets = index.resolve(call, scope)
                dependencies[identity].update(function_identity(t) for t in targets)
                imported = scope.get('imports', {}).get(call.name, call.qualified_name)
                invoked = call.name if call.receiver is None else (
                    call.receiver.get('name') if call.name == 'invoke' else None)
                if not targets and invoked in slots:
                    invoked_slots[identity].add(invoked)
                    emitting.add(identity)
                if not targets and imported.rsplit('.', 1)[-1] in native:
                    emitting.add(identity)
                for argument in executed_arguments(call, targets, scope):
                    if argument.get('kind') == 'name' and argument['name'] in slots:
                        invoked_slots[identity].add(argument['name'])
        emitting.update(identity for identity, targets in dependencies.items() if targets & emitting)
        changed = len(emitting) + sum(map(len, invoked_slots.values())) != before

    def visit(node, function, needs_value=False):
        if not isinstance(node, dict):
            return
        kind = node.get('kind')
        if kind == 'callable_reference':
            return
        call = call_from(node)
        if call:
            if needs_value:
                value_uses.update(function_identity(t) for t in index.resolve(call, function))
            if call.receiver:
                visit(call.receiver, function, True)
            for argument in call.arguments:
                value = argument['value']
                visit(value, function, value.get('kind') != 'lambda')
            return
        if kind == 'block':
            statements = node.get('statements', [])
            for i, statement in enumerate(statements):
                visit(statement, function, needs_value and i == len(statements)-1)
            return
        if kind in {'local', 'return'}:
            visit(node.get('value'), function, True)
            return
        if kind == 'lambda':
            visit(node.get('body'), function)
            return
        if kind == 'if':
            visit(node.get('condition'), function, True)
            for key in ('yes', 'no'):
                visit(node.get(key), function, needs_value)
            return
        for value in node.values():
            if isinstance(value, dict):
                visit(value, function, needs_value or kind in {'binary', 'unary', 'qualified', 'index'})
            elif isinstance(value, list):
                for child in value:
                    visit(child, function, needs_value)

    for function in functions:
        visit(function['body'], function)
        for parameter in function['parameters']:
            if isinstance(parameter.get('default'), str):
                visit(parse_expression(parameter['default']), function, True)
    # Forward the expected-value use through expression-bodied helper returns.
    changed = True
    while changed:
        before = len(value_uses)
        for function in functions:
            identity = function_identity(function)
            if identity in value_uses or index.roles[identity] == 'value':
                visit(function['body'], function, True)
        changed = len(value_uses) != before
    index.mixed_value_functions = []
    for function in functions:
        identity = function_identity(function)
        role = index.roles[identity]
        if role == 'modifier':
            continue
        if identity in emitting:
            if role == 'value' or identity in value_uses:
                index.mixed_value_functions.append(identity)
            index.roles[identity] = 'content'
        # Unknown invocation effects stay on the diagnostic-producing content path.
        elif (identity in value_uses and identity not in unresolved_invocations
              and not function.get('return_type') and function['body'].get('kind') != 'block'):
            index.roles[identity] = 'value'
