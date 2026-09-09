from .base import Control, RenderResult


class DropdownMenu(Control):
    name = 'DropdownMenu'
    arguments = frozenset({'expanded', 'onDismissRequest', 'containerColor'})

    def project(self, context):
        context.background(context.color('containerColor', 'MaterialTheme.colorScheme.surfaceContainer'))
        return {'kind': self.name, 'expanded': context.boolean('expanded', None)}

    def render(self, context):
        p = context.prefix
        expanded = context.facts.get('expanded')
        if type(expanded) is not bool:
            context.issue('source.control.expanded', 'popup visibility is unresolved')
        lines = [p + 'Column() {', *context.body(), p + '}',
                 p + '  .padding({ top: ' + context.length(8) + ', bottom: ' + context.length(8) + ' })']
        def finish(lines):
            def declaration(name):
                return ['  @State private ' + name + 'Visible: boolean = false',
                        '  private ' + name + 'Anchored: boolean = false',
                        '  @Builder', '  private ' + name + '() {',
                        *['    ' + line[len(p):] for line in lines], '  }', '']
            name = context.declare(self.name, declaration)
            return [p + 'Stack() {}', p + "  .width('100%').height(0)",
                    p + '  .onAreaChange((_old, area) => { if (!this.' + name + 'Anchored && Number(area.width) > 0) { this.' +
                    name + 'Anchored = true; this.' + name + 'Visible = ' + str(expanded is True).lower() + ' } })',
                    p + '  .bindPopup(this.' + name + 'Visible, { builder: this.' + name +
                    '(), placement: Placement.BottomLeft, enableArrow: false, autoCancel: true, '
                    'onStateChange: (event) => { this.' + name + 'Visible = event.isVisible } })']
        return RenderResult(lines, finalize=finish)
