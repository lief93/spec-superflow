from .base import Control, RenderResult


class NavigationDrawer(Control):
    name = 'NavigationDrawer'
    slots = frozenset({'drawerContent', 'content'})
    arguments = frozenset({'drawerState', 'gesturesEnabled', 'scrimColor'})

    def project(self, context):
        state = context.value('drawerState', {'kind': 'drawer_state', 'open': False})
        opened = state.get('open') if isinstance(state, dict) and state.get('kind') == 'drawer_state' else None
        if type(opened) is not bool:
            context.issue('drawerState', 'drawer state must resolve to Open or Closed')
        return {'kind': self.name, 'open': opened,
            'gestures': context.boolean('gesturesEnabled', True),
            'scrim': context.value('scrimColor', '#52000000')}

    def render(self, context):
        p = context.prefix
        opened = context.facts.get('open')
        if type(opened) is not bool:
            context.issue('source.control.open', 'drawer visibility is unresolved')
        name = context.declare(self.name, lambda name: [
            '  @State private ' + name + 'Visible: boolean = ' + str(opened is True).lower(), ''])
        alignment = 'End' if context.node['style']['layout'].get('layout_direction') == 'rtl' else 'Start'
        lines = [p + 'Stack() {', *context.body('Stack', context.slot('content')),
            p + '  if (this.' + name + 'Visible) {',
            p + "    Rect().width('100%').height('100%')",
            p + '      .fill(' + context.quote(context.facts.get('scrim') or '#52000000') + ')',
            p + '      .onClick(() => { this.' + name + 'Visible = false })',
            p + '    Column() {', *context.body('Column', context.slot('drawerContent'), 6), p + '    }',
            p + "      .width('100%').height('100%')",
            p + '      .constraintSize({ maxWidth: ' + context.length(360) + ' })',
            p + '      .align(Alignment.' + alignment + ').onClick(() => {})',
            p + '  }', p + '}', p + '  .alignContent(Alignment.TopStart)']
        context.issue('source.control.back', 'drawer outside dismissal is local; host back-event integration is not translated')
        if context.facts.get('gestures'):
            context.issue('source.control.gestures', 'drawer open/close UI is retained; edge-swipe gesture recognition is not translated')
        return RenderResult(lines)
