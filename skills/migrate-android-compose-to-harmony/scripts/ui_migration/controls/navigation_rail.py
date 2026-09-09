from .navigation_bar import NavigationBar
from .base import RenderResult


class NavigationRail(NavigationBar):
    name = 'NavigationRail'
    slots = frozenset({'header', 'content'})

    def render(self, context):
        p = context.prefix
        return RenderResult([p + 'Column({ space: ' + context.length(8) + ' }) {',
            *context.body('Column', context.slot('header')), *context.body('Column', context.slot('content')),
            p + '}', p + '  .width(' + context.length(80) + ").height('100%')",
            p + '  .alignItems(HorizontalAlign.Center)'])
