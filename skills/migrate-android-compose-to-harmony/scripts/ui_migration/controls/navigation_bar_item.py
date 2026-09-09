from .base import Control, RenderResult


class NavigationBarItem(Control):
    name = 'NavigationBarItem'
    slots = frozenset({'icon', 'label'})
    arguments = frozenset({'selected', 'enabled', 'alwaysShowLabel', 'onClick', 'colors'})

    def project(self, context):
        selected = context.boolean('selected', None)
        enabled = context.boolean('enabled', True)
        context.node['style']['state']['enabled'] = enabled
        palette = context.palette()
        icon_color = context.color('iconColor', 'MaterialTheme.colorScheme.onSecondaryContainer' if selected else 'MaterialTheme.colorScheme.onSurfaceVariant')
        text_color = context.color('textColor', 'MaterialTheme.colorScheme.onSurface' if selected else 'MaterialTheme.colorScheme.onSurfaceVariant')
        icon_color = palette.get('disabledIconColor' if enabled is False else 'selectedIconColor' if selected else 'unselectedIconColor', icon_color)
        text_color = palette.get('disabledTextColor' if enabled is False else 'selectedTextColor' if selected else 'unselectedTextColor', text_color)
        if enabled is False:
            if 'disabledIconColor' not in palette and icon_color:
                icon_color = '#61' + icon_color[-6:]
            if 'disabledTextColor' not in palette and text_color:
                text_color = '#61' + text_color[-6:]
        return {'kind': self.name, 'selected': selected,
            'slot_styles': {'icon': {'color': icon_color}, 'label': {'color': text_color,
                'typography': {'font_size_sp': 12, 'line_height_sp': 16, 'font_weight': 500, 'letter_spacing_sp': 0.5}}},
            'always_show_label': context.boolean('alwaysShowLabel', True),
            'indicator_color': palette.get('indicatorColor', context.color('indicatorColor', 'MaterialTheme.colorScheme.secondaryContainer'))}

    def render(self, context):
        p = context.prefix
        lines = [p + 'Column({ space: ' + context.length(4) + ' }) {',
                 p + '  Stack() {', *context.body('Stack', context.slot('icon'), 4), p + '  }',
                 p + '    .width(' + context.length(64) + ').height(' + context.length(32) + ')',
                 p + '    .borderRadius(' + context.length(16) + ')']
        if context.facts.get('selected') is True and context.facts.get('indicator_color'):
            lines.append(p + '    .backgroundColor(' + context.quote(context.facts['indicator_color']) + ')')
        label = context.body('Column', context.slot('label'))
        if label and context.facts.get('always_show_label') is False and context.facts.get('selected') is False:
            lines += [p + '  Column() {', *['  ' + line for line in label], p + '  }.visibility(Visibility.None)']
        else:
            lines += label
        lines += [p + '}', p + '  .alignItems(HorizontalAlign.Center).justifyContent(FlexAlign.Center)']
        return RenderResult(lines, {'source.control', 'style.state.selected'})
