"""Fixed-state Material control defaults. Color roles resolve against the source theme."""
from .page_model import semantic_expression, UNRESOLVED
from .values import evaluate_expression


SELECTIONS = {'Checkbox', 'RadioButton', 'Switch'}
PROGRESS = {'LinearProgressIndicator', 'CircularProgressIndicator'}


class MaterialControlDefaults:
    def __init__(self, node, environment):
        self.node, self.environment = node, environment
        self.expression = semantic_expression(node, 'colors')
        value = evaluate_expression(self.expression, environment) if self.expression else {'kind': 'material_colors', 'values': {}}
        resolved = node.get('source', {}).get('resolved_material_colors') or {}
        if self.expression and resolved.get('expression') == self.expression:
            value = {'kind': 'material_colors', 'values': resolved['values']}
        self.colors = value['values'] if isinstance(value, dict) and value.get('kind') == 'material_colors' else None

    def assign(self, path, value, expression):
        group, field = path.split('.')
        full = 'style.' + path
        self.node['unresolved'] = [u for u in self.node.get('unresolved', []) if u.get('path') != full]
        if value is UNRESOLVED or value is None:
            self.node['style'][group][field] = None
            self.node['unresolved'].append({'path': full, 'expression': expression,
                'reason': 'Material default requires a resolved source theme/color/state'})
        else:
            self.node['style'][group][field] = value
            self.node.setdefault('provenance', []).append({'paths': [full], 'origin': 'source_resolved',
                'source': 'Material3 baseline: ' + expression})
        return value

    def color(self, key, role, alpha=None):
        if self.colors is None:
            return UNRESOLVED
        if key in self.colors:
            return self.colors[key]
        value = evaluate_expression('MaterialTheme.colorScheme.' + role, self.environment)
        if isinstance(value, str) and value.startswith('#') and len(value) == 9:
            if alpha is not None:
                value = f'#{round(int(value[1:3], 16) * alpha):02X}' + value[3:]
            return value
        return UNRESOLVED

    def apply(self):
        kind = self.node['type']
        if kind in PROGRESS:
            for argument, path, role in [('color', 'control.active_color', 'primary'),
                    ('trackColor', 'control.inactive_color', 'secondaryContainer')]:
                if not semantic_expression(self.node, argument):
                    # Baseline circular progress has no track by default.
                    value = '#00000000' if kind == 'CircularProgressIndicator' and argument == 'trackColor' else self.color('', role)
                    self.assign(path, value, 'MaterialTheme.colorScheme.' + role)
            if not semantic_expression(self.node, 'strokeWidth'):
                self.assign('control.stroke_width_dp', 4, 'ProgressIndicatorDefaults.CircularStrokeWidth')
            self.node['source']['material_size'] = ({'width_dp': 40, 'height_dp': 40}
                if kind == 'CircularProgressIndicator' else {'width_dp': 240, 'height_dp': 4})
            return
        if kind not in SELECTIONS:
            return
        enabled = self.node['style']['state'].get('enabled')
        selected = self.node['style']['state'].get('selected' if kind == 'RadioButton' else 'checked')
        if type(enabled) is not bool or type(selected) is not bool:
            for path in ('control.active_color', 'control.inactive_color'):
                self.assign(path, UNRESOLVED, 'enabled/checked/selected')
            return
        disabled = not enabled
        alpha = .38 if disabled else None
        if kind == 'Checkbox':
            active = self.color('disabledCheckedColor' if disabled else 'checkedColor', 'onSurface' if disabled else 'primary', alpha)
            inactive = self.color('disabledUncheckedColor' if disabled else 'uncheckedColor', 'onSurface' if disabled else 'onSurfaceVariant', alpha)
            mark = self.color('checkmarkColor', 'onPrimary')
            width, height = 20, 20
        elif kind == 'RadioButton':
            active = self.color('disabledSelectedColor' if disabled else 'selectedColor', 'onSurface' if disabled else 'primary', alpha)
            inactive = self.color('disabledUnselectedColor' if disabled else 'unselectedColor', 'onSurface' if disabled else 'onSurfaceVariant', alpha)
            mark = active
            width, height = 20, 20
        else:
            active = self.color('disabledCheckedTrackColor' if disabled else 'checkedTrackColor', 'onSurface' if disabled else 'primary', .12 if disabled else None)
            inactive = self.color('disabledUncheckedTrackColor' if disabled else 'uncheckedTrackColor', 'surfaceContainerHighest', .12 if disabled else None)
            key = ('disabled' + ('Checked' if selected else 'Unchecked') if disabled else 'checked' if selected else 'unchecked') + 'ThumbColor'
            mark = self.color(key, ('surface' if selected else 'onSurface') if disabled else 'onPrimary' if selected else 'outline', .38 if disabled and not selected else None)
            width, height = 52, 32
        self.assign('control.active_color', active, self.expression or 'selected Material color token')
        self.assign('control.inactive_color', inactive, self.expression or 'unselected Material color token')
        self.assign('typography.color', mark, self.expression or 'Material mark/thumb color token')
        self.node['source']['material_selection'] = {'width_dp': width, 'height_dp': height,
            'minimum_interactive_dp': self.environment.get('LocalMinimumInteractiveComponentSize.current', 48)}
        if kind == 'Switch' and semantic_expression(self.node, 'thumbContent'):
            self.node['unresolved'].append({'path': 'source.material_selection.thumbContent',
                'expression': semantic_expression(self.node, 'thumbContent'),
                'reason': 'custom Switch thumb content requires a slot renderer'})
