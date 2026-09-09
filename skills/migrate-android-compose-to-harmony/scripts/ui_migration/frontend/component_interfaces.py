"""Freeze declaration types and typed call arguments before exporting the one JSON."""
from kotlin_psi import parse_expression, KotlinPsiSyntaxError
from ui_migration.contracts.component_interfaces import signature, value_matches
from ui_migration.frontend.page_model import UNRESOLVED


def state_parameters(definition):
    names = {p['name'] for p in definition.get('parameters', [])}
    found = set()

    def visit(value):
        if isinstance(value, dict):
            if value.get('kind') == 'name' and value.get('name') in names:
                found.add(value['name'])
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for call in definition.get('ui_template', {}).get('calls', []):
        expressions = [(call.get('visibility_condition') or {}).get('expression')]
        expressions.extend(path.get('condition') for path in call.get('ui_state_path', []))
        for expression in expressions:
            if isinstance(expression, str):
                try:
                    visit(parse_expression(expression))
                except KotlinPsiSyntaxError:
                    pass
    return [p['name'] for p in definition.get('parameters', []) if p['name'] in found]


def project_interface(node, definition, evaluate):
    parameters = signature(definition.get('parameters', []))
    bindings = node.get('invocation_bindings') or {}
    arguments, resolved = [], {}
    for parameter in parameters:
        name = parameter['name']
        expression = bindings.get(name, parameter['default_expression'])
        argument = {'name':name, 'expression':expression, 'status':'unresolved'}
        if parameter['status'] != 'resolved':
            argument['reason'] = parameter['reason']
        elif isinstance(expression, str):
            value = evaluate(name, expression, resolved)
            tree = parameter['type']
            if tree['kind'] == 'function':
                try:
                    syntax = parse_expression(expression)
                    if syntax.get('kind') == 'lambda' and not syntax.get('statements') and syntax.get('text', '').strip() == '{}':
                        value = {'kind':'empty_callback'}
                except KotlinPsiSyntaxError:
                    pass
            if value is not UNRESOLVED and value_matches(value, tree):
                argument.update(status='resolved', value=value)
                resolved[name] = value
            else:
                argument['reason'] = 'argument does not resolve to declared type ' + parameter['kotlin_type']
        else:
            argument['reason'] = 'required source parameter has no argument'
        arguments.append(argument)
    return {'schema':'ui-migration.component-interface.v1', 'definition_id':definition['id'],
            'name':definition['type'], 'parameters':parameters, 'arguments':arguments,
            'state_parameters':state_parameters(definition),
            'render_scope':'selected-source-state'}
