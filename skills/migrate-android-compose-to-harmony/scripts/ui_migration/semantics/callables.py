"""Lexically scoped function values. Captures are evaluator state, never page facts."""
from ui_migration.semantics.errors import LayoutExpressionError


class SourceCallable(dict):
    def __init__(self, syntax, context):
        super().__init__(kind='function_reference', expression=syntax['text'])
        self.syntax = syntax
        self.context = context.scoped(dict(context.values), dict(context.bindings))

    def bind(self, arguments, caller, seen=()):
        parameters = self.syntax.get('parameters') or ['it']
        if len(arguments) > len(parameters):
            raise LayoutExpressionError('callable argument count mismatch')
        values = [caller.value(a['value'], seen) for a in arguments]
        return self.context.scoped({**self.context.values, **dict(zip(parameters, values))})


def call_target(call, context, seen=()):
    if call.name == 'invoke' and call.receiver is not None:
        node = call.receiver
    elif call.receiver is not None:
        node = {'kind':'qualified','receiver':call.receiver,
                'selector':{'kind':'name','name':call.name,'text':call.name},'safe':call.safe,
                'text':call.receiver.get('text','')+'.'+call.name}
    else:
        node = {'kind':'name','name':call.name,'text':call.name}
    try:
        return context.value(node, seen)
    except LayoutExpressionError:
        return context.unresolved
