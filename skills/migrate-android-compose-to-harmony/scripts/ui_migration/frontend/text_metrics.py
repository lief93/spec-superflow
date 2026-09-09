from ui_migration.semantics.expressions import LayoutExpressionError
from ui_migration.semantics.syntax import call_from


def text_metric_properties(name, tree, resolver):
    """Resolve explicit Compose paragraph metrics without substituting platform defaults."""
    call = call_from(tree)
    if name == 'lineBreak':
        expression = resolver.render(tree)
        presets = {'LineBreak.Simple': 'simple', 'LineBreak.Heading': 'heading', 'LineBreak.Paragraph': 'paragraph'}
        if expression not in presets:
            raise LayoutExpressionError('custom line break requires explicit platform rule mapping')
        return {'line_break': presets[expression]}
    if name == 'platformStyle':
        if call is None or call.name != 'PlatformTextStyle':
            raise LayoutExpressionError('platformStyle requires resolved PlatformTextStyle')
        node = call.argument('includeFontPadding', 0)
        value = resolver.value(node) if node else None
        if type(value) is not bool:
            raise LayoutExpressionError('includeFontPadding is unresolved')
        return {'include_font_padding': value}
    if name == 'lineHeightStyle':
        if call is None or call.name != 'LineHeightStyle':
            raise LayoutExpressionError('lineHeightStyle requires resolved LineHeightStyle')
        result = {}
        choices = (
            ('alignment', 0, 'line_height_alignment', {'Center': 'center', 'Top': 'top', 'Bottom': 'bottom', 'Proportional': 'proportional'}),
            ('trim', 1, 'line_height_trim', {'None': 'none', 'Both': 'both', 'FirstLineTop': 'first_line_top', 'LastLineBottom': 'last_line_bottom'}),
        )
        for argument, index, field, mapping in choices:
            node = call.argument(argument, index)
            expression = resolver.render(node) if node else ''
            value = mapping.get(expression.rsplit('.', 1)[-1])
            if value is None:
                raise LayoutExpressionError('unresolved line height ' + argument)
            result[field] = value
        return result
    return None
