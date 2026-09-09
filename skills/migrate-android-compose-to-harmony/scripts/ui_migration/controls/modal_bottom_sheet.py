from .modal import ModalControl
from .base import RenderResult


class ModalBottomSheet(ModalControl):
    name = 'ModalBottomSheet'
    slots = frozenset({'dragHandle', 'content'})

    def project(self, context):
        facts = super().project(context)
        facts['handle_color'] = context.color('dragHandleColor', 'MaterialTheme.colorScheme.onSurfaceVariant')
        return facts

    def render(self, context):
        p = context.prefix
        facts = context.node.get('source', {}).get('overlay', {})
        lines = [p + 'Column() {']
        if facts.get('drag_handle') == 'default':
            lines.extend([p + '  Row() {', p + '    Rect().width(' + context.length(32) + ').height(' + context.length(4) + ')',
                p + '      .radius(2)' + ('.fill(' + context.quote(context.facts['handle_color']) + ')' if context.facts.get('handle_color') else ''), p + '  }',
                p + "    .width('100%').justifyContent(FlexAlign.Center)",
                p + '    .padding(' + context.length(22) + ')'])
        lines.extend([*context.body('Column', context.slot('dragHandle')),
                      *context.body('Column', context.slot('content')), p + '}', p + "  .width('100%')"])
        return RenderResult(lines, {'source.control', 'source.overlay'}, lambda lines: self.modal(context, lines))
