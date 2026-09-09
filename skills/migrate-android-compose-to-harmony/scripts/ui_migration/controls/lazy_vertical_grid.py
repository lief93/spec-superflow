from .base import Control, RenderResult


class LazyVerticalGrid(Control):
    name = 'LazyVerticalGrid'
    arguments = frozenset({'columns', 'userScrollEnabled', 'reverseLayout', 'horizontalArrangement', 'verticalArrangement', 'verticalItemSpacing'})
    container = 'Grid'
    item = 'GridItem'

    def project(self, context):
        columns = context.value('columns')
        if not isinstance(columns, dict) or columns.get('kind') != 'grid_cells':
            context.issue('columns', 'columns require GridCells.Fixed or GridCells.Adaptive')
            columns = None
        reverse = context.boolean('reverseLayout', False)
        if reverse is True:
            context.issue('reverseLayout', 'reverse layout includes scroll origin and cannot be replaced by reversing child order')
        vertical = context.arrangement('verticalArrangement')
        if context.expression('verticalItemSpacing'):
            spacing = context.value('verticalItemSpacing')
            if type(spacing) in (int, float):
                vertical = {'kind': 'arrangement', 'mode': 'Start', 'space_dp': spacing}
        return {'kind': self.name, 'columns': columns, 'horizontal': context.arrangement('horizontalArrangement'), 'vertical': vertical,
            'scroll_enabled': context.boolean('userScrollEnabled', True)}

    def render(self, context):
        p = context.prefix
        lines = [p + self.container + '() {']
        for child in context.children:
            lines += [p + '  ' + self.item + '() {', *context.child(child, 'Column', context.indent + 4), p + '  }']
        lines += [p + '}']
        columns = context.facts.get('columns')
        if isinstance(columns, dict):
            if columns.get('mode') == 'fixed':
                template = ' '.join(['1fr'] * columns['value'])
                lines.append(p + '  .columnsTemplate(' + context.quote(template) + ')')
            else:
                name = context.declare(self.name + 'Columns', lambda name: ['  @State private ' + name + ': number = 1', ''])
                horizontal = context.facts.get('horizontal') or {}
                gap = horizontal.get('space_dp', 0)
                padding = context.node['style']['layout'].get('padding_dp') or {}
                inset = sum(padding.get(side, 0) for side in ('left', 'right'))
                if columns['value'] + gap > 0:
                    lines.extend([p + '  .columnsTemplate("1fr ".repeat(this.' + name + ').trim())',
                        p + '  .onAreaChange((_old, area) => { this.' + name + ' = Math.max(1, Math.floor((Number(area.width) - ' +
                        str(inset) + ' + ' + str(gap) + ') / ' + str(columns['value'] + gap) + ')) })'])
                else:
                    context.issue('source.control.columns', 'adaptive minimum size plus gap must be positive')
        else:
            context.issue('source.control.columns', 'grid track definition is unresolved')
        if type(context.facts.get('scroll_enabled')) is bool:
            lines.append(p + '  .enableScrollInteraction(' + str(context.facts['scroll_enabled']).lower() + ')')
        for attribute, field in [('columnsGap', 'horizontal'), ('rowsGap', 'vertical')]:
            arrangement = context.facts.get(field)
            if isinstance(arrangement, dict):
                lines.append(p + '  .' + attribute + '(' + context.length(arrangement['space_dp']) + ')')
                if arrangement['mode'] not in {'Start', 'Top'}:
                    context.issue('source.control.' + field, 'grid surplus-space arrangement requires an additional track policy')
        return RenderResult(lines, {'source.control', 'style.layout.horizontal_arrangement', 'style.layout.vertical_arrangement'})
