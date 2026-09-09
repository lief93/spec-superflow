from .base import Control, RenderResult


class DropdownMenuItem(Control):
    name = 'DropdownMenuItem'
    slots = frozenset({'text', 'leadingIcon', 'trailingIcon'})
    arguments = frozenset({'enabled', 'onClick', 'colors'})

    def project(self, context):
        enabled = context.boolean('enabled', True)
        context.node['style']['state']['enabled'] = enabled
        palette = context.palette()
        roles = {'text': 'textColor', 'leadingIcon': 'leadingIconColor', 'trailingIcon': 'trailingIconColor'}
        styles = {}
        for slot, key in roles.items():
            default = context.color(key, 'MaterialTheme.colorScheme.onSurface' if slot == 'text' else 'MaterialTheme.colorScheme.onSurfaceVariant')
            disabled_key = 'disabled' + key[0].upper() + key[1:]
            color = palette.get(disabled_key if enabled is False else key, default)
            if enabled is False and disabled_key not in palette and color:
                color = '#61' + color[-6:]
            styles[slot] = {'color': color}
        return {'kind': self.name, 'slot_styles': styles}

    def render(self, context):
        p = context.prefix
        lines = [p + 'Row({ space: ' + context.length(12) + ' }) {',
                 *context.body('Row', context.slot('leadingIcon')),
                 p + '  Column() {', *context.body('Column', context.slot('text'), 4), p + '  }',
                 p + '    .layoutWeight(1).alignItems(HorizontalAlign.Start)',
                 *context.body('Row', context.slot('trailingIcon')), p + '}',
                 p + '  .constraintSize({ minHeight: ' + context.length(48) + ', minWidth: ' + context.length(112) + ' })',
                 p + '  .padding({ left: ' + context.length(12) + ', right: ' + context.length(12) + ' })',
                 p + '  .alignItems(VerticalAlign.Center)']
        return RenderResult(lines)
