from ui_migration.frontend.page_model import UNRESOLVED
from ui_migration.frontend.shapes import shape_value
from ui_migration.semantics.expressions import LayoutDimension
from .arguments import argument
from .registry import ApiAdapter


def size(call, context, seen):
    width = argument(call, context, seen, 'width')
    height = argument(call, context, seen, 'height', 1)
    if all(isinstance(value, LayoutDimension) and value.unit == 'dp' for value in (width, height)):
        return {'width': width, 'height': height}
    return UNRESOLVED


def padding_values(call, context, seen):
    positional = [a for a in call.arguments if not a.get('name')]
    named = {a['name']: a['value'] for a in call.arguments if a.get('name')}
    if len(positional) == 1 and not named:
        value = context.value(positional[0]['value'], seen)
        values = dict.fromkeys(('start', 'top', 'end', 'bottom'), value)
    elif not positional and not set(named) - {'all', 'horizontal', 'vertical', 'start', 'top', 'end', 'bottom'}:
        resolved = {key: context.value(value, seen) for key, value in named.items()}
        zero = LayoutDimension(0, 'dp')
        values = {side: resolved.get(side, resolved.get(axis, resolved.get('all', zero)))
                  for side, axis in [('start', 'horizontal'), ('end', 'horizontal'), ('top', 'vertical'), ('bottom', 'vertical')]}
    else:
        return UNRESOLVED
    if not all(isinstance(v, LayoutDimension) and v.unit == 'dp' and v.value >= 0 for v in values.values()):
        return UNRESOLVED
    return {'kind': 'padding_values', 'edges': {key: value.value for key, value in values.items()}}


ADAPTERS = (
    ApiAdapter('compose.padding-values', 'size', ('androidx.compose.foundation.layout.PaddingValues',), padding_values, aliases=('PaddingValues',)),
    ApiAdapter('compose.dp-size', 'size', ('androidx.compose.ui.unit.DpSize',), size, aliases=('DpSize',)),
    ApiAdapter('compose.rounded-shape', 'shape', ('androidx.compose.foundation.shape.RoundedCornerShape',),
               shape_value, aliases=('RoundedCornerShape',)),
    ApiAdapter('compose.absolute-rounded-shape', 'shape', ('androidx.compose.foundation.shape.AbsoluteRoundedCornerShape',),
               shape_value, aliases=('AbsoluteRoundedCornerShape',)),
)
