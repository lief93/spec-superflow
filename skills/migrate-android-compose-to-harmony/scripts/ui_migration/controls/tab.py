from .base import Control, RenderResult


class Tab(Control):
    name = 'Tab'
    slots = frozenset({'text', 'icon', 'content'})
    arguments = frozenset({'selected', 'enabled', 'onClick', 'selectedContentColor', 'unselectedContentColor'})

    def project(self, context):
        selected = context.boolean('selected', None)
        context.node['style']['state']['enabled'] = context.boolean('enabled', True)
        color = context.color('selectedContentColor' if selected else 'unselectedContentColor',
                              'MaterialTheme.colorScheme.primary' if selected else 'MaterialTheme.colorScheme.onSurfaceVariant')
        return {'kind': self.name, 'selected': selected, 'content_color': color,
            'slot_styles': {'text': {'typography': {'font_size_sp': 14, 'line_height_sp': 20,
                'font_weight': 500, 'letter_spacing_sp': 0.1}}}}

    def render(self, context):
        p = context.prefix
        children = [*context.slot('icon'), *context.slot('text'), *context.slot('content')]
        lines = [p + 'Column({ space: ' + context.length(8) + ' }) {',
                 *context.body('Column', children), p + '}',
                 p + '  .constraintSize({ minHeight: ' + context.length(72 if context.slot('icon') and context.slot('text') else 48) + ' })',
                 p + '  .justifyContent(FlexAlign.Center).alignItems(HorizontalAlign.Center)']
        return RenderResult(lines, {'source.control', 'style.state.selected'})
