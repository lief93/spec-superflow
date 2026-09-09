from .base import Control, RenderResult


class TabRow(Control):
    name = 'TabRow'
    slots = frozenset({'tabs', 'content', 'indicator', 'divider'})
    arguments = frozenset({'selectedTabIndex', 'containerColor', 'contentColor'})
    indicator_height = 2

    def project(self, context):
        selected = context.value('selectedTabIndex')
        if type(selected) is not int or selected < 0:
            context.issue('selectedTabIndex', 'tab index must be a non-negative integer')
            selected = None
        context.background(context.color('containerColor', 'MaterialTheme.colorScheme.surface'))
        return {'kind': self.name, 'selected': selected,
            'indicator_color': context.color('contentColor', 'MaterialTheme.colorScheme.primary')}

    def render(self, context):
        p = context.prefix
        tabs = [*context.slot('tabs'), *context.slot('content')]
        lines = [p + 'Column() {', p + '  Row() {']
        for index, tab in enumerate(tabs):
            lines.extend([p + '    Stack() {', *context.child(tab, 'Column', context.indent + 6)])
            if index == context.facts.get('selected') and not context.slot('indicator'):
                color = context.facts.get('indicator_color')
                if color:
                    lines.extend([p + '      Rect().height(' + context.length(self.indicator_height) + ").width('100%')",
                                  p + '        .fill(' + context.quote(color) + ').align(Alignment.Bottom)'])
            lines.extend([p + '    }', p + '      .layoutWeight(1)'])
        lines.extend([p + '  }', p + "    .width('100%')", *context.body('Stack', context.slot('indicator')),
                      *context.body('Column', context.slot('divider')), p + '}', p + "  .width('100%')"])
        return RenderResult(lines)
