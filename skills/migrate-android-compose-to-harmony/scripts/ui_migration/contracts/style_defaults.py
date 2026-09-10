"""Reported visual degradation at the target input validation boundary."""
import copy

from page_snapshot import PageSnapshotError, normalize_style
from ui_migration.contracts.style_tokens import validate_token_reference


DEFAULTS = {
    'layout.padding_dp': dict.fromkeys(('left', 'top', 'right', 'bottom'), 0),
    'layout.margin_dp': dict.fromkeys(('left', 'top', 'right', 'bottom'), 0),
    'layout.layout_direction': 'ltr', 'layout.z_index': 0,
    'surface.background': {'type': 'none'},
    'surface.corner_radius_dp': dict.fromkeys(('top_left', 'top_right', 'bottom_right', 'bottom_left'), 0),
    'surface.corner_sizes': None, 'surface.border': None, 'surface.shadows': [],
    'surface.alpha': 1, 'surface.clip': False,
    'typography.font_size_sp': 16, 'typography.font_weight': 400,
    'typography.font_style': 'normal', 'typography.font_family': None,
    'typography.letter_spacing_sp': 0, 'typography.line_height_sp': 24,
    'typography.text_align': 'start', 'typography.max_lines': 2147483647,
    'typography.min_lines': 1, 'typography.overflow': 'clip',
    'typography.color': '#FF000000', 'typography.decoration': 'none',
    'typography.soft_wrap': True, 'typography.baseline_shift': 0,
    'typography.include_font_padding': True, 'typography.line_height_alignment': 'proportional',
    'typography.line_height_trim': 'none', 'typography.line_break': 'simple',
    'asset.content_scale': 'fit', 'asset.tint': '#FF000000',
    'transform.translation_x_dp': 0, 'transform.translation_y_dp': 0,
    'transform.scale_x': 1, 'transform.scale_y': 1, 'transform.rotation_degrees': 0,
    'content.text': '', 'content.placeholder': '', 'content.content_description': '',
    'control.value': 0, 'control.minimum': 0, 'control.maximum': 1,
    'control.steps': 0, 'control.active_color': '#FF000000',
    'control.inactive_color': '#FFBDBDBD', 'control.stroke_width_dp': 4,
}


def apply_style_defaults(record, component_id, *, facts_key='requiredFacts'):
    """Only repair known visual properties; identities, state and resources stay strict."""
    style = record.get('style')
    if not isinstance(style, dict):
        return []
    source = record.get('source') or {}
    references = source.get('style_token_references') or {}
    pending = record.get('unresolved') or []
    facts = record.get(facts_key) or []
    warnings = []
    replaced = set()

    def replace(path, reason):
        group, field = path.split('.')
        full_path = 'style.' + path
        diagnostics = [u for u in pending if u.get('path') == full_path]
        old = style.get(group, {}).get(field)
        fallback = copy.deepcopy(DEFAULTS[path])
        style.setdefault(group, {})[field] = fallback
        warnings.append({'component_id': component_id, 'path': full_path,
            'expression': next((u['expression'] for u in diagnostics if u.get('expression')), str(old)),
            'original_value': old, 'fallback': fallback, 'reason': reason,
            'kind': 'style_default_applied', 'diagnostics': copy.deepcopy(diagnostics)})
        replaced.add(full_path)

    for path in DEFAULTS:
        group, field = path.split('.')
        if group in style and not isinstance(style[group], dict):
            continue
        full_path = 'style.' + path
        if path in references:
            # A valid target expression outranks a stale unresolved literal.
            validate_token_reference(references[path], path)
            style.setdefault(group, {})[field] = None
            replaced.add(full_path)
            continue
        unresolved = any(u.get('path') == full_path for u in pending) or any(
            f.get('path') == full_path and f.get('status') in {'symbolic', 'unresolved'} for f in facts)
        raw = style.get(group, {}).get(field)
        if not unresolved:
            try:
                normalize_style({group: {field: raw}}, full_path)
            except PageSnapshotError as error:
                reason = str(error)
            else:
                continue
        else:
            reason = 'unresolved visual property; migration default used, verify appearance'
        replace(path, reason)

    # Validate coupled constraints as well as individual field types.
    for group, lower, upper, strict in [('control', 'minimum', 'maximum', True),
                                       ('typography', 'min_lines', 'max_lines', False)]:
        values = style.get(group, {})
        if not isinstance(values, dict):
            continue
        a, b = values.get(lower), values.get(upper)
        if type(a) in {int, float} and type(b) in {int, float} and (a >= b if strict else a > b):
            for field in (lower, upper):
                replace(group + '.' + field, 'inconsistent bounds; migration defaults used')
    record['unresolved'] = [u for u in pending if u.get('path') not in replaced]
    for item in facts:
        if item.get('path') in replaced:
            item.update(status='default_resolved', reason='target reference or reported migration default')
    return warnings


def prepare_style_defaults(version):
    """Run after storage decoding and before strict Lanhu document validation."""
    warnings = []

    def visit(layer):
        if not isinstance(layer, dict):
            return
        migration = layer.get('migration')
        if isinstance(migration, dict):
            applied = apply_style_defaults(migration, layer.get('id'))
            warnings.extend(applied)
            if any(w['path'] == 'style.content.text' for w in applied) and layer.get('type') == 'text':
                layer['text'] = migration['style']['content']['text']
        children = layer.get('layers')
        if isinstance(children, list):
            for child in children:
                visit(child)

    visit(version.get('artboard'))
    return warnings
