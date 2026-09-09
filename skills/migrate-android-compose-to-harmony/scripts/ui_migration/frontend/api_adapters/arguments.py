from ui_migration.semantics.expressions import LayoutExpressionError


def argument(call, context, seen, name, index=0):
    node = call.argument(name, index)
    if node is None:
        raise LayoutExpressionError('missing argument: ' + call.qualified_name + '.' + name)
    return context.value(node, seen)
