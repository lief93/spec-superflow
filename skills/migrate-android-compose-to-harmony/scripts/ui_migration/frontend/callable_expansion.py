"""Select an inventoried UI body using a fixed-state callable value."""
from kotlin_psi import parse_expression
from ui_migration.frontend.values import value_resolver
from ui_migration.semantics.callables import SourceCallable, call_target
from ui_migration.semantics.syntax import call_from, syntax_shape
from ui_migration.semantics.expressions import LayoutExpressionError
from ui_migration.frontend.source_symbols import resolve_functions


def select_template(payload, invocation, environment):
    expression = invocation.get('expression', invocation['name'])
    call = call_from(parse_expression(expression+'('+','.join(invocation.get('arguments', []))+')'))
    resolver = value_resolver({}, environment)
    target = call_target(call, resolver) if call else resolver.unresolved
    if not isinstance(target, SourceCallable):
        return None, None, 'content call target is unresolved; no body was guessed'
    templates = payload.get('source_callable_templates', [])
    source = target.context.values.get('__source_file')
    if target.syntax['kind']=='lambda':
        candidates = [t for t in templates if t['source']==source and t.get('expression')
                      and syntax_shape(parse_expression(t['expression']))==syntax_shape(target.syntax)]
    else:
        functions = resolve_functions(environment.get('__source_functions', []), target.syntax['name'],
            source=source, imports=target.context.values.get('__source_imports', {}))
        candidates = [t for t in templates if any(t['source']==f['source'] and t['name']==f['name'] for f in functions)]
    if len(candidates)!=1:
        return None, None, 'content body is missing or ambiguous in source inventory'
    selected = candidates[0]
    try:
        if target.syntax['kind']=='lambda':
            scope = target.bind(call.arguments,resolver)
        else:
            from ui_migration.frontend.source_values import bind_arguments
            scope = bind_arguments(call, selected['parameters'], resolver, ())
        # Framework/inset context belongs to the invocation, local captures to the definition.
        local = {**environment, **scope.values}
        for name, binding in scope.bindings.items():
            if name not in local or local[name] is resolver.unresolved:
                local[name] = scope.value(parse_expression(binding))
        return selected, local, None
    except LayoutExpressionError as error:
        return None, None, str(error)
