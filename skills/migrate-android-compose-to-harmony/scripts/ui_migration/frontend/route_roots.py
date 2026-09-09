"""Verified navigation destinations, not a blanket multi-root layout fallback."""
import copy
from page_snapshot import empty_style
from .source_symbols import function_identity
from ui_migration.semantics.syntax import call_from


def find_page_host(index, source, name, declaration_id=None):
    matches = []

    def official(call, function, symbol):
        if index.resolve(call, function):
            return False
        qualified = function['imports'].get(call.qualified_name, call.qualified_name)
        return qualified == 'androidx.navigation.compose.' + symbol or (
            qualified == symbol and 'androidx.navigation.compose' in function.get('wildcard_imports', []))

    def lambdas(call):
        return [a['value']['body'] for a in call.arguments if a['value'].get('kind') == 'lambda']

    def expression(call, key, default):
        value = next((a['value'] for a in call.arguments if a.get('name') == key), None)
        return value['text'] if value is not None else default

    def walk(node, function, host=None, destination=None):
        if node.get('kind') == 'block':
            for statement in node['statements']:
                walk(statement, function, host, destination)
            return
        call = call_from(node)
        if call is None:
            return
        if official(call, function, 'NavHost'):
            for body in lambdas(call):
                walk(body, function, call)
        elif host and official(call, function, 'composable'):
            for body in lambdas(call):
                walk(body, function, host, call)
        elif destination:
            targets = index.resolve(call, function)
            if len(targets) == 1 and (targets[0]['source'], targets[0]['name']) == (source, name) and (
                    declaration_id is None or function_identity(targets[0]) == declaration_id):
                route = destination.argument('route')
                matches.append({'kind': 'navigation_destination', 'layout': 'overlay',
                    'source': function['source'], 'composable': function['name'],
                    'declaration_id': function_identity(function), 'line': function['line'],
                    'route_expression': route.get('text') if route else None,
                    'modifier_expression': expression(host, 'modifier', 'Modifier'),
                    'content_alignment': expression(host, 'contentAlignment', 'Alignment.TopStart')})
            # Do not look through an intervening Row/Column or callback lambda.
        elif host is None:
            # Locate NavHost in UI containers, but not in event/value lambdas.
            from page_component_catalog import CONTROL_FAMILIES
            containers = set(CONTROL_FAMILIES.get('layout', [])) | {'Column', 'Row', 'Box', 'Surface'}
            if call.name in containers:
                for body in lambdas(call):
                    walk(body, function)

    for function in index.functions:
        walk(function['body'], function)
    unique = []
    for host in matches:
        if host not in unique:
            unique.append(host)
    # A function reused in distinct route hosts has no unique external layout.
    return unique[0] if len(unique) == 1 else None


def attach_page_host(payload):
    host = payload.get('page_host')
    if not host or host.get('kind') != 'navigation_destination' or host.get('layout') != 'overlay':
        return payload
    if any(n.get('source', {}).get('route_content_host') for n in payload.get('components', [])):
        return payload
    result = copy.deepcopy(payload)
    nodes = result['components']
    roots = [n for n in nodes if n.get('parent_id') is None]
    if not roots:
        return result
    identifier = 'compose-route-content-host'
    while any(n['id'] == identifier for n in nodes):
        identifier += '-host'
    for i, node in enumerate(roots):
        node.update(parent_id=identifier, sibling_index=i)
    nodes.insert(0, {'id': identifier, 'source_component_id': identifier, 'semantic_key': identifier,
        'type': 'Box', 'parent_id': None, 'sibling_index': 0, 'children_ids': [n['id'] for n in roots],
        'style': empty_style(), 'arguments': {'semantic': {
            'contentAlignment': {'expression': host['content_alignment']}}},
        'modifiers': [{'name': 'sourceExpression', 'source_expression': host['modifier_expression']}],
        'source': {**host, 'route_content_host': True, 'attributes': []}, 'unresolved': [], 'provenance': []})
    return result
