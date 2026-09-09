from ui_migration.frontend.page_model import UNRESOLVED
from .arguments import argument
from .registry import ApiAdapter


def remember(call, context, seen):
    functions = [arg['value'] for arg in call.arguments if arg['value']['kind'] == 'lambda']
    if len(functions) != 1:
        return UNRESOLVED
    return context.value(functions[0]['body'], seen)


def mutable_state(call, context, seen):
    return {'value': argument(call, context, seen, 'value')}


def collected_state(call, context, seen):
    if call.receiver is None:
        return UNRESOLVED
    return {'value': context.value(call.receiver, seen)}


def dialog_properties(call, context, seen):
    defaults = {'dismissOnBackPress': True, 'dismissOnClickOutside': True, 'usePlatformDefaultWidth': True}
    for arg in call.arguments:
        name = arg.get('name')
        if name not in defaults:
            return UNRESOLVED
        value = context.value(arg['value'], seen)
        if type(value) is not bool:
            return UNRESOLVED
        defaults[name] = value
    return {'kind': 'dialog_properties', **defaults}


ADAPTERS = (
    ApiAdapter('compose.dialog-properties', 'state', ('androidx.compose.ui.window.DialogProperties',),
               dialog_properties, aliases=('DialogProperties',)),
    ApiAdapter('compose.remember', 'state', ('androidx.compose.runtime.remember',), remember, aliases=('remember',)),
    ApiAdapter('compose.mutable-state', 'state', ('androidx.compose.runtime.mutableStateOf',), mutable_state, aliases=('mutableStateOf',)),
    ApiAdapter('compose.collected-state', 'state', ('androidx.compose.runtime.collectAsState',
        'androidx.lifecycle.compose.collectAsStateWithLifecycle'), collected_state,
        aliases=('collectAsState', 'collectAsStateWithLifecycle')),
)
