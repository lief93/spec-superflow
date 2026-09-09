from ui_migration.frontend.page_model import UNRESOLVED
from ui_migration.semantics.expressions import LayoutDimension, KnownValueError
from .arguments import argument
from .registry import ApiAdapter


ANDROID_COLOR_NAMES = {
    'black': 0xFF000000, 'darkgray': 0xFF444444, 'gray': 0xFF888888,
    'lightgray': 0xFFCCCCCC, 'white': 0xFFFFFFFF, 'red': 0xFFFF0000,
    'green': 0xFF00FF00, 'blue': 0xFF0000FF, 'yellow': 0xFFFFFF00,
    'cyan': 0xFF00FFFF, 'magenta': 0xFFFF00FF, 'aqua': 0xFF00FFFF,
    'fuchsia': 0xFFFF00FF, 'darkgrey': 0xFF444444, 'grey': 0xFF888888,
    'lightgrey': 0xFFCCCCCC, 'lime': 0xFF00FF00, 'maroon': 0xFF800000,
    'navy': 0xFF000080, 'olive': 0xFF808000, 'purple': 0xFF800080,
    'silver': 0xFFC0C0C0, 'teal': 0xFF008080,
}


def parse_color(call, context, seen):
    value = argument(call, context, seen, 'colorString')
    if not isinstance(value, str):
        return UNRESOLVED
    if value.lower() in ANDROID_COLOR_NAMES:
        return ANDROID_COLOR_NAMES[value.lower()]
    if len(value) in (7, 9) and value.startswith('#'):
        try:
            return int(value[1:], 16) | (0xFF000000 if len(value) == 7 else 0)
        except ValueError:
            pass
    raise KnownValueError('invalid Android hex color')


def gradient(call, context, seen):
    if any(item.get('name') not in (None, 'colors', 'tileMode') for item in call.arguments):
        return UNRESOLVED
    tile = call.argument('tileMode')
    if tile is not None and tile.get('text') not in ('TileMode.Clamp', 'androidx.compose.ui.graphics.TileMode.Clamp'):
        return UNRESOLVED
    colors = argument(call, context, seen, 'colors')
    if not isinstance(colors, list) or len(colors) < 2 or not all(
            isinstance(c, str) and len(c) == 9 and c.startswith('#') for c in colors):
        return UNRESOLVED
    return {'kind': 'linear_brush', 'colors': colors,
            'axis': {'horizontalGradient': 'horizontal', 'verticalGradient': 'vertical', 'linearGradient': 'linear'}[call.name]}


def color(call, context, seen):
    if len(call.arguments) != 1:
        return UNRESOLVED
    value = argument(call, context, seen, 'value')
    return f'#{value:08X}' if type(value) is int and 0 <= value <= 0xFFFFFFFF else UNRESOLVED


def copy_color(call, context, seen):
    color_value = context.receiver
    channels = {name: int(color_value[i:i+2], 16) / 255 for name, i in [('alpha', 1), ('red', 3), ('green', 5), ('blue', 7)]}
    for item in call.arguments:
        name = item.get('name'); value = context.value(item['value'], seen)
        if name not in channels or type(value) not in (int, float) or not 0 <= value <= 1:
            return UNRESOLVED
        channels[name] = value
    return '#' + ''.join(f'{int(v * 255 + 0.5):02X}' for v in channels.values())


def argb(call, context, seen):
    if call.arguments:
        return UNRESOLVED
    value = int(context.receiver[1:], 16)
    return value - 0x100000000 if value >= 0x80000000 else value


def luminance(call, context, seen):
    value = argument(call, context, seen, 'color')
    if type(value) is not int:
        return UNRESOLVED
    channels = [(value >> shift & 255) / 255 for shift in (16, 8, 0)]
    linear = [c / 12.92 if c < 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722)))


def tint(call, context, seen):
    if len(call.arguments) != 1:
        return UNRESOLVED
    return argument(call, context, seen, 'color')


def border(call, context, seen):
    width = argument(call, context, seen, 'width')
    color_value = argument(call, context, seen, 'color', 1)
    if isinstance(width, LayoutDimension) and width.unit == 'dp' and width.value >= 0 and isinstance(color_value, str) and len(color_value) == 9 and color_value.startswith('#'):
        return {'kind': 'border_stroke', 'width_dp': width.value, 'color': color_value, 'style': 'solid'}
    return UNRESOLVED


ADAPTERS = (
    ApiAdapter('android.parse-color', 'background', ('android.graphics.Color.parseColor',), parse_color),
    ApiAdapter('compose.color', 'background', ('androidx.compose.ui.graphics.Color',), color, aliases=('Color',)),
    ApiAdapter('compose.copy-color', 'background', ('copy',), copy_color, receiver_kind='color'),
    ApiAdapter('compose.color-argb', 'background', ('toArgb',), argb, receiver_kind='color'),
    ApiAdapter('android.color-luminance', 'background', ('androidx.core.graphics.ColorUtils.calculateLuminance',), luminance),
    ApiAdapter('compose.tint', 'image', ('androidx.compose.ui.graphics.ColorFilter.tint',), tint, aliases=('ColorFilter.tint',)),
    ApiAdapter('compose.border-stroke', 'border', ('androidx.compose.foundation.BorderStroke',), border, aliases=('BorderStroke',)),
    ApiAdapter('compose.axis-gradient', 'background', ('androidx.compose.ui.graphics.Brush.horizontalGradient',
               'androidx.compose.ui.graphics.Brush.verticalGradient', 'androidx.compose.ui.graphics.Brush.linearGradient'), gradient,
               aliases=('Brush.horizontalGradient', 'Brush.verticalGradient', 'Brush.linearGradient')),
)
