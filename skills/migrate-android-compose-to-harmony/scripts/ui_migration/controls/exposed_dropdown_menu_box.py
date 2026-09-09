from .base import Control, RenderResult


class ExposedDropdownMenuBox(Control):
    name = 'ExposedDropdownMenuBox'
    arguments = frozenset({'expanded', 'onExpandedChange'})

    def project(self, context):
        return {'kind': self.name, 'expanded': context.boolean('expanded', None)}

    def render(self, context):
        p = context.prefix
        return RenderResult([p + 'Column() {', *context.body(), p + '}'])
