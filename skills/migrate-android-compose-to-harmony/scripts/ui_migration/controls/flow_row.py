from .base import Control, RenderResult


class FlowRow(Control):
    name = 'FlowRow'
    arguments = frozenset({'maxItemsInEachRow', 'maxLines', 'horizontalArrangement', 'verticalArrangement'})

    def project(self, context):
        limit = context.value('maxItemsInEachRow')
        max_lines = context.value('maxLines')
        if limit is not None:
            context.issue('maxItemsInEachRow', 'finite per-line item caps require an additional measured flow policy')
        if max_lines is not None:
            context.issue('maxLines', 'line clipping/overflow content is not translated')
        return {'kind': self.name, 'horizontal': context.arrangement('horizontalArrangement'),
                'vertical': context.arrangement('verticalArrangement')}

    def render(self, context):
        p = context.prefix
        horizontal = context.facts.get('horizontal') or {}
        vertical = context.facts.get('vertical') or {}
        if vertical.get('mode') not in (None, 'Start', 'Top'):
            context.issue('source.control.vertical', 'vertical surplus-space distribution is not translated; line spacing is preserved')
        align = {'Start': 'Start', 'End': 'End', 'Center': 'Center', 'SpaceBetween': 'SpaceBetween',
                 'SpaceAround': 'SpaceAround', 'SpaceEvenly': 'SpaceEvenly'}
        lines = [p + 'Flex({ direction: FlexDirection.Row, wrap: FlexWrap.Wrap, alignItems: ItemAlign.Start, justifyContent: FlexAlign.' +
                 align.get(horizontal.get('mode'), 'Start') + ', space: { main: ' +
                 context.metrics(horizontal.get('space_dp', 0)) + ', cross: ' + context.metrics(vertical.get('space_dp', 0)) + ' } }) {']
        for child in context.children:
            lines += [p + '  Column() {', *context.child(child, 'Column', context.indent + 4), p + '  }',
                      p + '    .flexShrink(0)']
        lines += [p + '}']
        return RenderResult(lines, {'source.control', 'style.layout.horizontal_arrangement', 'style.layout.vertical_arrangement'})
