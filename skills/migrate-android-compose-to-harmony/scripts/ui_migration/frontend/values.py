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
    @staticmethod
    def member_value(receiver, name):
        from ui_migration.contracts.resource_values import is_resource_value, resource_property
        if not is_resource_value(receiver):
            return UNRESOLVED
        value = resource_property(receiver, name)
        if value is None:
            raise LayoutExpressionError('resource object has no mapped property: ' + name)
        return value

    CONSTANTS = {
        'Color.White': '#FFFFFFFF', 'Color.Black': '#FF000000',
        'Color.Gray': '#FF888888', 'Color.Transparent': '#00000000',
        'Color.Red': '#FFFF0000', 'Color.Green': '#FF00FF00', 'Color.Blue': '#FF0000FF',
        'Color.Yellow': '#FFFFFF00', 'Color.Cyan': '#FF00FFFF', 'Color.Magenta': '#FFFF00FF',
        'Color.LightGray': '#FFCCCCCC', 'Color.DarkGray': '#FF444444',
        'Color.Unspecified': {'kind': 'color_unspecified'},
        'CircleShape': {'kind': 'circle'},
        'RectangleShape': {'kind': 'rounded_corner', 'radius_dp': 0},
        'LayoutDirection.Rtl': 'rtl', 'LayoutDirection.Ltr': 'ltr',
        'androidx.compose.ui.unit.LayoutDirection.Rtl': 'rtl',
        'androidx.compose.ui.unit.LayoutDirection.Ltr': 'ltr',
    }

    def typed_fallback(self, node, source_type, context, seen, reason):
        registry = context.values.get('__api_registry', BUILTIN_REGISTRY)
        if not registry._fallbacks:
            return UNRESOLVED
        source_type = source_type.removesuffix('?').strip()
        imports = context.values.get('__source_imports') or {}
        source_type = imports.get(source_type, source_type)
        expected_type = source_type
        qualified_types = {'androidx.compose.ui.graphics.Color': 'Color',
            'androidx.compose.ui.unit.Dp': 'Dp', 'androidx.compose.ui.unit.TextUnit': 'TextUnit',
            **{'kotlin.' + name: name for name in ('String', 'Int', 'Long', 'Float', 'Double')}}
        source_type = qualified_types.get(source_type, source_type)
        if (source_type not in {'Color', 'String', 'Dp', 'TextUnit', 'Int', 'Long', 'Float', 'Double'}
                and ('object', source_type) not in registry._fallbacks):
            return UNRESOLVED
        if 'cyclic or over-deep' in reason or 'ambiguous' in reason:
            return UNRESOLVED
        path = qualified_name(node)
        if path in context.bindings:
            bound, trace = context.bound(path, seen)
            return context.typed_value(bound, source_type, trace)
        kind = node['kind']
        if kind == 'return':
            return context.typed_value(node['value'], source_type, seen)
        if kind == 'block':
            scoped, terminal = context.block(node, seen)
            return scoped.typed_value(terminal, source_type, seen)
        if kind in ('if', 'when'):
            try:
                branch = context.branch(node, seen)
            except LayoutExpressionError:
                pass  # An adapter may translate the entire dynamic expression, never one guessed branch.
            else:
                return context.typed_value(branch, source_type, seen)
        if kind == 'binary' and node['operator'] == '?:':
            left = context.typed_value(node['left'], source_type, seen)
            if left is None:
                return context.typed_value(node['right'], source_type, seen)
            result = self.coalesce(left, node['right'], context, seen)
            return left if result is UNRESOLVED else result
        # A known consumer type follows source helpers whose return type is inferred.
        # Declaration scopes and cycle/overload checks remain owned by source_values.
        value = source_property_value(path, context, seen, expected_type=expected_type) if path else UNRESOLVED
        if value is not UNRESOLVED:
            return value
        call = call_from(node)
        if call:
            scope = source_function_scope(call, context, seen)
            if scope:
                scoped, body, trace = scope
                return scoped.typed_value(body, scoped.values.get('__return_type') or expected_type, trace)
        return registry.fallback_value(node, source_type, context, seen, reason)


    def coalesce(self, left, right, context, seen):
        from ui_migration.contracts.resource_values import is_resource_value, validate_resource_value
        if not is_resource_value(left):
            return UNRESOLVED
        spec = validate_resource_value(left)
        if 'fallback' in spec:
            return left
        fallback = context.value(right, seen)
        if isinstance(fallback, LayoutDimension):
            if fallback.unit != spec.get('sourceUnit'):
                raise LayoutExpressionError('resource fallback dimension unit mismatch')
            fallback = fallback.value
        result = {**left, 'reference': {**spec, 'fallback': fallback}}
        try:
            validate_resource_value(result)
        except ValueError as error:
            raise LayoutExpressionError(str(error)) from error
        return result

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
        registry = context.values.get('__api_registry', BUILTIN_REGISTRY)
        if path:
            value = registry.property_value(path, context, seen)
            if value is not UNRESOLVED:
                return value
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
        match = registry.resolve(call, context, seen)
        if match:
            return registry.evaluate(node, context, seen, match)
        if call.name in ('collectAsState', 'collectAsStateWithLifecycle') and call.receiver is not None:
            return collected_state(call, context, seen)
        return source_call_value(call, context, seen)

    def expand_modifier(self, node, context, seen, prefix):
        call = call_from(node)
        if call.name == 'composed':
            factories = [argument['value'] for argument in call.arguments
                         if argument.get('name') in (None, 'factory')
                         and argument['value'].get('kind') == 'lambda']
            if len(factories) != 1 or factories[0].get('parameters'):
                raise LayoutExpressionError('composed requires one receiver factory lambda')
            scoped = context.scoped(dict(context.values))
            scoped.modifier_receivers['this'] = (prefix if call.receiver is not None
                else context.modifier_receivers.get('this', []))
            return scoped.chain(factories[0]['body'], seen)
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
                             value_syntax=SOURCE_VALUES.value_syntax, coalesce_value=SOURCE_VALUES.coalesce,
                             typed_fallback=SOURCE_VALUES.typed_fallback, member_value=SOURCE_VALUES.member_value)


def evaluate_expression(expression, environment, *, preserve_units=False, source_type=None):
    value = expression.strip()
    if value in environment and environment[value] is not UNRESOLVED:
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
        result = value_resolver({}, environment).typed_value(parse_expression(value), source_type)
        return result.value if isinstance(result, LayoutDimension) and not preserve_units else result
    except (LayoutExpressionError, KotlinPsiSyntaxError):
        return UNRESOLVED
