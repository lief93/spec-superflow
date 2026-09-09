"""Project selected image sources and tint without retaining inventory guesses."""
import re

from ui_migration.contracts.material_icons import material_icon_identity
from ui_migration.frontend.page_model import IMAGE_TYPES, UNRESOLVED, style_group
from ui_migration.frontend.values import evaluate_expression


def argument_expression(node, *names, positional=False):
    arguments = node.get('arguments') or {}
    semantic = arguments.get('semantic') or {}
    candidates = [semantic.get(name) for name in names]
    if positional:
        candidates.extend((arguments.get('positional') or [])[:1])
    for candidate in candidates:
        if isinstance(candidate, dict):
            expression = candidate.get('resolved_local_expression') or candidate.get('expression')
            if isinstance(expression, str):
                return expression
    return None


def project_image(node, environment, sources):
    if node.get('type') not in IMAGE_TYPES:
        return
    asset = style_group(node, 'asset')

    def fact(field, value, expression, evidence=None):
        path = 'style.asset.' + field
        asset[field] = None if value is UNRESOLVED else value
        node['unresolved'] = [u for u in node.get('unresolved', []) if u.get('path') != path]
        provenance = node.setdefault('provenance', [])
        for entry in provenance:
            if path in entry.get('paths', []):
                entry['paths'] = [p for p in entry['paths'] if p != path]
        provenance[:] = [entry for entry in provenance if entry.get('paths')]
        if value is UNRESOLVED:
            node['unresolved'].append({'path': path, 'expression': expression,
                                      'reason': 'selected image fact could not be resolved'})
        else:
            provenance.append({'paths': [path], 'origin': 'source_resolved',
                               'source': ' '.join((evidence or expression).split())})

    expression = argument_expression(node, 'painter', 'imageVector', 'model', positional=True)
    if expression is not None or asset.get('resource') is not None:
        resolved = evaluate_expression(expression, environment) if expression is not None else asset['resource']
        source_expression = expression or asset['resource']
        if isinstance(resolved, dict) and resolved.get('kind') == 'image_vector_reference':
            resolved = resolved['expression']
        resource = resolved if isinstance(resolved, str) and resolved.strip() else UNRESOLVED
        if isinstance(resource, str):
            uri = re.fullmatch(r'android\.resource://[A-Za-z0-9_.]+/(?:drawable|mipmap)/([a-z][a-z0-9_]*)', resource)
            if uri and uri.group(1) in sources:
                resource = uri.group(1)
        previous = asset.get('resource')
        fact('resource', resource, source_expression)
        evidence = sources.get(resource, {}) if isinstance(resource, str) else {}
        for field in ('sha256', 'width_dp', 'height_dp'):
            if field in evidence:
                fact(field, evidence[field], source_expression, evidence.get('path'))
            elif previous != resource:
                fact(field, UNRESOLVED, source_expression)
        if isinstance(resource, str) and material_icon_identity(resource):
            for field in ('width_dp', 'height_dp'):
                fact(field, 24, source_expression)

    tint = argument_expression(node, 'tint' if node['type'] == 'Icon' else 'colorFilter')
    if tint is None and node['type'] == 'Icon':
        tint = 'LocalContentColor.current'
    if tint is not None:
        value = evaluate_expression(tint, environment)
        if value is None or isinstance(value, dict) and value.get('kind') == 'color_unspecified':
            fact('tint', None, tint)
        elif isinstance(value, str) and re.fullmatch(r'#[0-9A-Fa-f]{8}', value):
            fact('tint', value.upper(), tint)
        else:
            fact('tint', UNRESOLVED, tint)
