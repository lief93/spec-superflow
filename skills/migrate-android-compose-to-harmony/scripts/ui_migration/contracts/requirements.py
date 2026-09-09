"""Shared required visual semantics; never supplies guessed framework values."""
from dataclasses import dataclass
from typing import Any

from page_component_catalog import CONTROL_FAMILIES
from ui_migration.contracts.style_tokens import has_token_reference

KNOWN_TYPES = frozenset(name for names in CONTROL_FAMILIES.values() for name in names)


def value_at(node, path):
    value = node
    for key in path.split('.'):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def layout_parent(node, nodes):
    parent = nodes.get(node.get('parent_id'))
    seen = set()
    while parent and (parent.get('source') or {}).get('custom_component'):
        if parent['id'] in seen:
            return None
        seen.add(parent['id'])
        parent = nodes.get(parent.get('parent_id'))
    return parent


def requirement_context(node, nodes):
    parent = layout_parent(node, nodes)
    state = (node.get('style') or {}).get('state') or {}
    return dict(component_type=node.get('type'), layout_parent_id=(parent or {}).get('id'),
        layout_parent_type=(parent or {}).get('type'),
        layout_scope=layout_scope(parent),
        fixed_state={key: state.get(key) for key in ('visible', 'enabled', 'selected', 'checked', 'refreshing')})


def layout_scope(parent):
    kind = (parent or {}).get('type')
    return {'Card': 'Column', 'Button': 'Row', 'TextButton': 'Row', 'OutlinedButton': 'Row',
            'BoxWithConstraints': 'Box', 'Surface': 'Box', 'PullToRefreshBox': 'Box',
            'IconButton': 'Box', 'IconToggleButton': 'Box',
            'FloatingActionButton': 'Box', 'SmallFloatingActionButton': 'Box'}.get(kind, kind)


@dataclass(frozen=True)
class RequiredProperty:
    path: str
    reason: str


FAMILY_PROPERTIES = {
    'text': ('content.text', 'typography.font_size_sp', 'typography.font_weight', 'typography.color'),
    'input': ('content.text', 'typography.font_size_sp', 'typography.font_weight', 'typography.color',
              'input.single_line', 'input.read_only', 'input.password', 'input.keyboard_type', 'input.ime_action'),
    'image': ('asset.resource', 'asset.content_scale'),
    'refresh': ('state.refreshing',),
    'range': ('control.value', 'control.minimum', 'control.maximum', 'control.steps'),
    'divider': ('control.active_color', 'control.stroke_width_dp'),
}
TYPE_PROPERTIES = {
    kind: tuple(RequiredProperty('style.' + path, f'{family} visual semantics require {path}') for path in paths)
    for family, paths in FAMILY_PROPERTIES.items() for kind in CONTROL_FAMILIES[family]
}
MATERIAL_BACKGROUNDS = {
    'Card', 'Surface', 'Scaffold', 'Button', 'TextButton', 'OutlinedButton',
    'FloatingActionButton', 'SmallFloatingActionButton', 'TextField', 'OutlinedTextField',
    'TopAppBar', 'CenterAlignedTopAppBar', 'BottomAppBar',
}
STATE_FIELDS = {'Checkbox': 'checked', 'Switch': 'checked', 'RadioButton': 'selected',
                'IconToggleButton': 'checked'}
DEFAULT_EXPRESSIONS = {
    ('Card', 'style.surface.background'): 'CardDefaults.cardColors().containerColor',
    ('Surface', 'style.surface.background'): 'MaterialTheme.colorScheme.surface',
    ('Scaffold', 'style.surface.background'): 'MaterialTheme.colorScheme.background',
    **{(kind, 'style.asset.content_scale'): 'ContentScale.Fit' for kind in CONTROL_FAMILIES['image']},
}
PLAIN_BACKGROUNDS = {
    kind for family in ('row', 'column', 'text', 'image', 'spacer', 'constraint')
    for kind in CONTROL_FAMILIES[family]
} | {'Box', 'BoxWithConstraints', 'BasicTextField', 'PullToRefreshBox', 'AnimatedVisibility', 'AnimatedContent', 'IconButton'}


def requirement_facts(node: dict[str, Any], nodes: dict | None = None) -> list[dict]:
    kind = node.get('type')
    if (node.get('source') or {}).get('custom_component'):
        return []
    if kind not in KNOWN_TYPES:
        return []
    result = []

    def add(path, reason, *, absent_allowed=False, invalid=False):
        value = value_at(node, path)
        missing = value is None and not has_token_reference(node, path)
        status = 'unresolved' if invalid or (missing and not absent_allowed) else (
            'not_applicable' if missing else 'resolved')
        default = DEFAULT_EXPRESSIONS.get((kind, path))
        if status == 'resolved' and default:
            status = 'default_resolved'
        result.append(dict(path=path, status=status, origin='semantic_contract',
            source_name=str(kind), expression=default, reason=reason))

    for rule in TYPE_PROPERTIES.get(kind, ()):
        add(rule.path, rule.reason)
    if kind in MATERIAL_BACKGROUNDS:
        add('style.surface.background', 'Material paint must resolve for the selected theme and enabled/error state; null is not transparency')
    elif kind in PLAIN_BACKGROUNDS:
        add('style.surface.background', 'this component has no implicit background paint; explicit modifiers are checked separately', absent_allowed=True)
    if kind in STATE_FIELDS:
        field = STATE_FIELDS[kind]
        add('style.state.' + field, 'selected fixed state must be a boolean',
            invalid=type(value_at(node, 'style.state.' + field)) is not bool)
    if kind in set(CONTROL_FAMILIES['button']) | set(CONTROL_FAMILIES['input']) | set(CONTROL_FAMILIES['selection']) | {'Slider'}:
        add('style.state.enabled', 'enabled state selects visuals; unknown is not enabled=true',
            invalid=type(value_at(node, 'style.state.enabled')) is not bool)
    # Missing constants are legal only as native measurement, not guessed frame sizes.
    for axis in ('width', 'height'):
        add(f'style.layout.{axis}_dp', 'no fixed size required; source sizing rules or native measurement own this axis', absent_allowed=True)
    rules = (node.get('source') or {}).get('layoutRules') or node.get('layout_rules') or []
    if nodes is not None:
        parent = layout_parent(node, nodes)
        parent_type = (parent or {}).get('type')
        scope = layout_scope(parent)
        for rule in rules:
            rule_kind = rule.get('kind')
            if rule_kind == 'weight':
                valid = scope in {'Row', 'Column'}
                result.append(dict(path='source.modifiers.weight', status='resolved' if valid else 'unresolved',
                    origin='semantic_contract', source_name=str(kind), expression=None,
                    reason=f'weight requires Row/Column scope; actual layout parent is {parent_type}'))
            elif rule_kind == 'alignment':
                alignment = str(rule.get('value', '')).removeprefix('Alignment.')
                allowed = {'Row': {'Top', 'Bottom', 'CenterVertically'},
                           'Column': {'Start', 'End', 'CenterHorizontally'},
                           'Box': {'TopStart', 'TopCenter', 'TopEnd', 'CenterStart', 'Center', 'CenterEnd', 'BottomStart', 'BottomCenter', 'BottomEnd'}}
                result.append(dict(path='source.modifiers.align', status='resolved' if alignment in allowed.get(scope, set()) else 'unresolved',
                    origin='semantic_contract', source_name=str(kind), expression=alignment,
                    reason=f'child alignment is scoped to its layout parent {parent_type}, not internal text alignment'))
    return result


def merge_requirement_facts(node, nodes=None):
    """Recompute requirements even when the input omitted or mislabeled them."""
    original = [dict(f) for f in node.get('required_facts') or [] if f.get('origin') != 'semantic_contract']
    for fact in original:
        path = fact['path']
        if has_token_reference(node, path):
            fact.update(status='resolved', reason='typed target reference is available; no final literal required for generation')
            continue
        explicit_null = (path == 'style.content.content_description' and fact.get('expression') == 'null') or (
            path == 'style.asset.tint' and fact.get('expression') == 'Color.Unspecified')
        if path.startswith('style.') and fact['status'] in {'resolved', 'default_resolved'} and value_at(node, path) is None and not explicit_null:
            fact.update(status='unresolved', reason='required value is missing despite its resolved label')
    by_path = {f['path']: f for f in original}
    for required in requirement_facts(node, nodes):
        previous = by_path.get(required['path'])
        if previous and previous['status'] in {'unresolved', 'symbolic'}:
            continue
        if previous and required['status'] != 'unresolved':
            continue
        original = [f for f in original if f['path'] != required['path']]
        original.append(required)
    return original
