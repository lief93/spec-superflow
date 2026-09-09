from .base import Control, RenderResult


class NavigationBar(Control):
    name = 'NavigationBar'
    arguments = frozenset({'containerColor', 'contentColor'})

    def project(self, context):
        context.background(context.color('containerColor', 'MaterialTheme.colorScheme.surfaceContainer'))
        return {'kind': self.name}

    def render(self, context):
        p = context.prefix
        lines = [p + 'Row() {']
        for child in context.children:
            lines.extend([p + '  Stack() {', *context.child(child, 'Column', context.indent + 4),
                          p + '  }', p + '    .layoutWeight(1)'])
        lines.extend([p + '}', p + "  .width('100%')", p + '  .constraintSize({ minHeight: ' + context.length(80) + ' })'])
        return RenderResult(lines)
