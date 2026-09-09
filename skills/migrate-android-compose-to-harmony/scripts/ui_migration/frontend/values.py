"""Source framework values share the same PSI scope as layout and typography."""
from kotlin_psi import KotlinPsiSyntaxError, parse_expression
from ui_migration.frontend.page_model import UNRESOLVED
from ui_migration.frontend.source_values import source_call_value, source_function_scope, source_property_value
from ui_migration.semantics.builtins import builtin_value
from ui_migration.semantics.expressions import LayoutDimension, LayoutExpressionError, LayoutExpressions
from ui_migration.semantics.syntax import call_from, qualified_name
from ui_migration.frontend.api_adapters.builtins import BUILTIN_REGISTRY
from ui_migration.frontend.api_adapters.state import collected_state


class SourceValues:
    CONSTANTS = {
        'Color.White': '#FFFFFFFF', 'Color.Black': '#FF000000',
        'Color.Gray': '#FF888888', 'Color.Transparent': '#00000000',
        'Color.Red': '#FFFF0000', 'Color.Green': '#FF00FF00', 'Color.Blue': '#FF0000FF',
        'Color.Yellow': '#FFFFFF00', 'Color.Cyan': '#FF00FFFF', 'Color.Magenta': '#FFFF00FF',
        'Color.LightGray': '#FFCCCCCC', 'Color.DarkGray': '#FF444444',
        'Color.Unspecified': {'kind': 'color_unspecified'},
        'CircleShape': {'kind': 'circle'},
    }


    def evaluate_node(self, node, context, seen):
        path = qualified_name(node)
        parts = (path or '').split('.')
        if len(parts) >= 3 and parts[-3] == 'R' and parts[-2] in ('drawable', 'mipmap'):
            return parts[-1]
        icon_path = path or ''
        imports = context.values.get('__source_imports') or {}
        if (icon_path.startswith('androidx.compose.material.icons.Icons.') or
                icon_path.startswith('Icons.') and imports.get('Icons') == 'androidx.compose.material.icons.Icons'):
            return {'kind': 'image_vector_reference', 'expression': icon_path}
        if path in self.CONSTANTS:
            return self.CONSTANTS[path]
        if path and context.values.get('__source_properties'):
            value = source_property_value(path, context, seen)
            if value is not UNRESOLVED:
                return value
        result = builtin_value(node, context, seen)
        if result is not UNRESOLVED:
            return result
        call = call_from(node)
        if call is None:
            return UNRESOLVED
        registry = context.values.get('__api_registry', BUILTIN_REGISTRY)
        match = registry.resolve(call, context, seen)
        if match:
            return registry.evaluate(node, context, seen, match)
        if call.name in ('collectAsState', 'collectAsStateWithLifecycle') and call.receiver is not None:
            return collected_state(call, context, seen)
        return source_call_value(call, context, seen)

    def expand_modifier(self, node, context, seen, prefix):
        call = call_from(node)
        inset_key = {'statusBarsPadding': 'WindowInsets.statusBars',
                     'navigationBarsPadding': 'WindowInsets.navigationBars'}.get(call.name)
        if inset_key and not call.arguments:
            insets = context.values.get(inset_key)
            edges = ('left', 'top', 'right', 'bottom')
            if not isinstance(insets, dict) or set(insets) != set(edges) or not all(
                type(value) in (int, float) and 0 <= value < float('inf') for value in insets.values()
            ):
                return UNRESOLVED
            consumed = dict(context.values.get('__consumed_window_insets', {}))
            for modifier in prefix:
                for edge, value in modifier.get('consumed_insets_dp', {}).items():
                    consumed[edge] = max(consumed.get(edge, 0), value)
            padding = {edge: max(0, insets[edge] - consumed.get(edge, 0)) for edge in edges}
            args = ', '.join(('start' if edge == 'left' else 'end' if edge == 'right' else edge)
                             + f' = {value:g}.dp' for edge, value in padding.items())
            modifiers = context.serialize_modifier('Modifier.padding(' + args + ')')
            modifiers[0].update(consumed_insets_dp=insets, original_expression=call.name + '()',
                                inset_source=inset_key)
            return prefix + modifiers
        function = source_function_scope(call, context, seen, 'Modifier')
        if function is None:
            return UNRESOLVED
        scoped, body, path = function
        scoped.modifier_receivers['this'] = prefix
        return scoped.chain(body, path)

    @staticmethod
    def value_syntax(value):
        if not isinstance(value, dict):
            return None
        if value.get('kind') == 'text_style':
            return 'TextStyle(' + ', '.join(name + ' = ' + expression for name, expression in value['properties'].items()) + ')'
        if value.get('kind') == 'font_family_reference':
            return value['name']
        if value.get('kind') == 'padding_values':
            return 'PaddingValues(' + ', '.join(f'{key} = {number:g}.dp' for key, number in value['edges'].items()) + ')'
        if value.get('kind') == 'border_stroke':
            return f"BorderStroke({value['width_dp']:g}.dp, Color(0x{value['color'][1:]}))"
        if value.get('kind') == 'linear_brush':
            colors = ', '.join('Color(0x' + color[1:] + ')' for color in value['colors'])
            return 'Brush.' + value['axis'] + 'Gradient(listOf(' + colors + '))'
        if value.get('kind') == 'circle':
            return 'CircleShape'
        if value.get('kind') != 'rounded_corner':
            return None
        def length(size):
            number = format(size['value'], 'g')
            return number + {'dp': '.dp', 'px': 'f', 'percent': ''}[size['unit']]
        corners = value.get('corners')
        if corners is None:
            unit = next((u for u in ('dp', 'px', 'percent') if 'radius_' + u in value), None)
            return 'RoundedCornerShape(' + length({'value': value['radius_' + unit], 'unit': unit}) + ')' if unit else None
        names = ('topLeft', 'topRight', 'bottomRight', 'bottomLeft') if value.get('absolute') else ('topStart', 'topEnd', 'bottomEnd', 'bottomStart')
        arguments = ', '.join(name + ('Percent' if size['unit'] == 'percent' else '') + ' = ' + length(size) for name, size in zip(names, corners))
        return ('AbsoluteRoundedCornerShape' if value.get('absolute') else 'RoundedCornerShape') + '(' + arguments + ')'

SOURCE_VALUES = SourceValues()


def value_resolver(bindings, values, serialize_modifier=None):
    return LayoutExpressions(bindings, values, None, UNRESOLVED, serialize_modifier,
                             evaluate_node=SOURCE_VALUES.evaluate_node, expand_chain=SOURCE_VALUES.expand_modifier,
                             value_syntax=SOURCE_VALUES.value_syntax)


def evaluate_expression(expression, environment, *, preserve_units=False):
    value = expression.strip()
    if value in environment:
        result = environment[value]
        return result.value if isinstance(result, LayoutDimension) and not preserve_units else result
    if value.startswith('#') and len(value) == 9:
        try:
            int(value[1:], 16)
            return value.upper()
        except ValueError:
            return UNRESOLVED
    if value == 'None':
        return None
    try:
        result = value_resolver({}, environment).value(parse_expression(value))
        return result.value if isinstance(result, LayoutDimension) and not preserve_units else result
    except (LayoutExpressionError, KotlinPsiSyntaxError):
        return UNRESOLVED
