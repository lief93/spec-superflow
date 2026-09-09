from .modal import ModalControl
from .base import RenderResult


class AlertDialog(ModalControl):
    name = 'AlertDialog'
    slots = frozenset({'icon', 'title', 'text', 'confirmButton', 'dismissButton'})

    def project(self, context):
        facts = super().project(context)
        facts['slot_styles'] = {
            'icon': {'color': context.color('iconContentColor', 'MaterialTheme.colorScheme.secondary')},
            'title': {'color': context.color('titleContentColor', 'MaterialTheme.colorScheme.onSurface'),
                'typography': {'font_size_sp': 24, 'line_height_sp': 32, 'font_weight': 400, 'letter_spacing_sp': 0}},
            'text': {'color': context.color('textContentColor', 'MaterialTheme.colorScheme.onSurfaceVariant'),
                'typography': {'font_size_sp': 14, 'line_height_sp': 20, 'font_weight': 400, 'letter_spacing_sp': 0.25}}}
        return facts

    def render(self, context):
        p, length = context.prefix, context.length
        lines = [p + 'Column() {']
        for slot, bottom in [('icon', 16), ('title', 16), ('text', 24)]:
            if context.slot(slot):
                lines += [p + '  Column() {', *context.body('Column', context.slot(slot), 4), p + '  }',
                    p + "    .width('100%')", p + '    .alignItems(HorizontalAlign.' + ('Center' if slot == 'icon' or (slot == 'title' and context.slot('icon')) else 'Start') + ')',
                    p + '    .margin({ bottom: ' + length(bottom) + ' })']
        lines += [p + '  Row({ space: ' + length(8) + ' }) {',
            *context.body('Row', context.slot('dismissButton'), 4),
            *context.body('Row', context.slot('confirmButton'), 4), p + '  }',
            p + "    .width('100%').justifyContent(FlexAlign.End)", p + '}',
            p + '  .padding(' + length(24) + ')', p + "  .width('100%')"]
        return RenderResult(lines, {'source.control', 'source.overlay'}, lambda lines: self.modal(context, lines))
