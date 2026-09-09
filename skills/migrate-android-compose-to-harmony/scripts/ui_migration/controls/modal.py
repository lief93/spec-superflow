"""Native modal lifecycle shared by dialog and bottom-sheet controls."""
from .base import Control, RenderResult


class ModalControl(Control):
    arguments = frozenset({'onDismissRequest', 'properties', 'containerColor', 'shape',
        'tonalElevation', 'scrimColor', 'sheetState', 'sheetMaxWidth', 'sheetGesturesEnabled',
        'contentWindowInsets', 'titleContentColor', 'textContentColor', 'iconContentColor'})

    def project(self, context):
        if context.expression('tonalElevation') and context.value('tonalElevation') != 0:
            context.issue('tonalElevation', 'explicit tonal elevation overlay is not translated')
        return {'kind': self.name}

    def render(self, context):
        p = context.prefix
        return RenderResult([p + 'Column() {', *context.body(), p + '}'],
                            {'source.control', 'source.overlay'},
                            lambda lines: self.modal(context, lines))

    def modal(self, context, lines, policy=None):
        facts = policy if policy is not None else context.node.get('source', {}).get('overlay', {})
        p = context.prefix
        sheet = self.name == 'ModalBottomSheet'
        def declaration(name):
            state = name + 'Visible'
            body = ['  @State private ' + state + ': boolean = ' + str(facts.get('initial_visibility', True)).lower(),
                    '  @Builder', '  private ' + name + '() {']
            if sheet:
                body.extend('    ' + line.lstrip() if not line.startswith(p) else '    ' + line[len(p):] for line in lines)
            else:
                body.extend(['    Stack() {',
                    "      Rect().width('100%').height('100%')",
                    '        .fill(' + context.quote(facts.get('scrim_color', '#52000000')) + ')'])
                if facts.get('dismiss_on_outside', True):
                    body.append('        .onClick(() => { this.' + state + ' = false })')
                body.append('      Column() {')
                body.extend('        ' + line[len(p):] for line in lines)
                body.extend(['      }', "        .width('100%')"])
                if facts.get('platform_width', True):
                    body.append('        .constraintSize({ maxWidth: ' + context.length(facts.get('max_width_dp', 560)) + ' })')
                if facts.get('full_height'):
                    body.append("        .height('100%')")
                body.extend([
                    '        .padding({ left: ' + context.length(facts.get('inset_dp', 28)) + ', right: ' + context.length(facts.get('inset_dp', 28)) + ' })',
                    '        .onClick(() => {})', '    }', "      .width('100%').height('100%')",
                    '      .alignContent(Alignment.' + facts.get('alignment', 'Center') + ')'])
            body.extend(['  }', ''])
            return body
        name = context.declare(self.name, declaration)
        state = name + 'Visible'
        if sheet:
            options = 'height: SheetSize.FIT_CONTENT, showClose: false, dragBar: false'
            options += ', maskColor: ' + context.quote(facts.get('scrim_color', '#52000000'))
            options += ', width: ' + str(facts.get('max_width_dp', 640))
            if not facts.get('gestures_enabled', True):
                context.issue('source.overlay.gestures_enabled', 'disabling all native sheet dragging needs a custom sheet controller')
            return [p + 'Stack() {}', p + '  .width(0).height(0)',
                p + '  .bindSheet($$this.' + state + ', this.' + name + '(), { ' + options + ' })']
        options = 'backgroundColor: Color.Transparent, modalTransition: ModalTransition.NONE'
        options += ', onWillDismiss: (action: DismissContentCoverAction) => { '
        options += 'this.' + state + ' = false; action.dismiss()' if facts.get('dismiss_on_back', True) else ''
        options += ' }'
        return [p + 'Stack() {}', p + '  .width(0).height(0)',
            p + '  .bindContentCover($$this.' + state + ', this.' + name + '(), { ' + options + ' })']
