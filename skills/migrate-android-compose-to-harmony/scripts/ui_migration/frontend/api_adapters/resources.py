import re
from ui_migration.frontend.page_model import UNRESOLVED
from .arguments import argument
from .registry import ApiAdapter


def resource(call, context, seen):
    if len(call.arguments) != 1:
        return UNRESOLVED
    return argument(call, context, seen, 'resId' if call.name == 'StringResource' else 'id')


def string_resource(call, context, seen):
    identifier = call.argument('id')
    template = context.value(identifier, seen)
    if len(call.arguments) == 1:
        return template
    if not isinstance(template, str):
        return UNRESOLVED
    values = [context.value(item['value'], seen) for item in call.arguments if item['value'] is not identifier]
    result, cursor, sequential = [], 0, 0
    for match in re.finditer(r'%(?:(\d+)\$)?([sd%])', template):
        literal = template[cursor:match.start()]
        if '%' in literal:
            return UNRESOLVED
        result.append(literal)
        if match[2] == '%':
            if match[1]:
                return UNRESOLVED
            result.append('%')
        else:
            index = int(match[1]) - 1 if match[1] else sequential
            if not match[1]:
                sequential += 1
            if not 0 <= index < len(values):
                return UNRESOLVED
            value = values[index]
            if value is UNRESOLVED or (match[2] == 'd' and type(value) is not int):
                return UNRESOLVED
            if value is not None and type(value) not in (str, int, float, bool):
                return UNRESOLVED
            result.append('null' if value is None else str(value).lower() if type(value) is bool else str(value))
        cursor = match.end()
    if '%' in template[cursor:]:
        return UNRESOLVED
    return ''.join(result) + template[cursor:]


def painter(call, context, seen):
    return argument(call, context, seen, 'model')


def request_builder(call, context, seen):
    return {'kind': 'image_request', 'model': UNRESOLVED}


def request_data(call, context, seen):
    return {'kind': 'image_request', 'model': argument(call, context, seen, 'data')}


def request_build(call, context, seen):
    if call.arguments:
        return UNRESOLVED
    return context.receiver['model']


def request_crossfade(call, context, seen):
    # Fade timing does not change the final loaded-state image source.
    value = argument(call, context, seen, 'enable' if call.argument('enable') is not None else 'durationMillis')
    if type(value) is not bool and not (type(value) is int and value >= 0):
        return UNRESOLVED
    return context.receiver


ADAPTERS = (
    ApiAdapter('coil.request-builder', 'image', ('coil.request.ImageRequest.Builder',
               'coil3.request.ImageRequest.Builder'), request_builder, aliases=('ImageRequest.Builder',)),
    ApiAdapter('coil.request-data', 'image', ('data',), request_data, receiver_kind='image_request'),
    ApiAdapter('coil.request-build', 'image', ('build',), request_build, receiver_kind='image_request'),
    ApiAdapter('coil.request-crossfade', 'image', ('crossfade',), request_crossfade, receiver_kind='image_request'),
    ApiAdapter('compose.painter-resource', 'image', ('androidx.compose.ui.res.painterResource',), resource,
               aliases=('painterResource',)),
    ApiAdapter('compose.vector-resource', 'image', ('androidx.compose.ui.res.vectorResource',
               'androidx.compose.ui.graphics.vector.ImageVector.vectorResource',
               'androidx.compose.ui.graphics.vector.ImageVector.Companion.vectorResource'), resource,
               aliases=('ImageVector.vectorResource', 'ImageVector.Companion.vectorResource')),
    ApiAdapter('compose.string-resource', 'text', ('androidx.compose.ui.res.stringResource',), string_resource,
               aliases=('stringResource',)),
    ApiAdapter('coil.async-painter', 'image', ('coil.compose.rememberAsyncImagePainter',
               'coil3.compose.rememberAsyncImagePainter'), painter, aliases=('rememberAsyncImagePainter',)),
    ApiAdapter('legacy.ui-text-resource', 'text', ('UiText.StringResource',), resource),
)
