"""Inventory source-side API gaps without executing any project extension."""
import hashlib
from collections import Counter
from kotlin_psi import KotlinPsiSyntaxError, parse_expression
from ui_migration.semantics.syntax import call_from
from .builtins import BUILTIN_REGISTRY


def calls_in(node):
    call = call_from(node)
    if call:
        yield call
        if call.receiver:
            yield from calls_in(call.receiver)
        for argument in call.arguments:
            yield from calls_in(argument['value'])
        return
    for value in node.values():
        if isinstance(value, dict):
            yield from calls_in(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    yield from calls_in(item)


def scan_source_page(page):
    from ui_migration.contracts.source_storage import unpack_source_page
    page = unpack_source_page(page)
    functions = {(f['source'], f['name']): f for f in page.get('source_functions', [])}
    source_symbols = {'.'.join(p for p in (f.get('package'), f.get('owner'), f['name']) if p)
                      for f in functions.values()}
    records = {}
    for component in page.get('components', []):
        source = component.get('source') or {}
        function = functions.get((source.get('source'), source.get('composable')), {})
        imports = function.get('imports', {})
        arguments = (component.get('arguments') or {}).get('semantic') or {}
        expressions = [(key, value.get('expression')) for key, value in arguments.items() if isinstance(value, dict)]
        expressions.extend(('modifier', 'Modifier.' + m['name'] + '(' + str(m.get('arguments') or '') + ')')
                           for m in component.get('modifiers', []) if m.get('name'))
        # Include transitive lexical bindings; a wrapper reference is not a new API.
        expressions.extend(('binding:' + key, value) for key, value in {
            **(component.get('parameter_bindings') or {}), **(component.get('local_values') or {})}.items())
        for field, expression in expressions:
            if not isinstance(expression, str):
                continue
            try:
                calls = list(calls_in(parse_expression(expression)))
            except KotlinPsiSyntaxError:
                calls = []
            for call in calls:
                symbol = call.qualified_name
                first, dot, rest = symbol.partition('.')
                qualified = imports.get(first, first) + (dot + rest if dot else '')
                adapter = BUILTIN_REGISTRY.select(symbol, imports)
                if adapter:
                    category = 'builtin_adapter'
                elif qualified in source_symbols or any(f['name'] == call.name and f.get('source') == source.get('source') for f in functions.values()):
                    category = 'source_wrapper'
                elif field == 'modifier' and symbol.startswith('Modifier.'):
                    category = 'core_modifier_candidate'
                elif field.startswith('binding:') or field.startswith('on'):
                    category = 'state_or_business_call'
                else:
                    category = 'api_gap_candidate'
                key = (qualified, category)
                record = records.setdefault(key, {'symbol': qualified, 'category': category,
                    'adapter': adapter.id if adapter else None,
                    'capability': adapter.capability if adapter else {'painter': 'image', 'imageVector': 'image',
                    'model': 'image', 'fontFamily': 'font', 'color': 'background', 'shape': 'shape',
                    'border': 'border'}.get(field), 'occurrences': []})
                item = {'component_id': component['id'], 'source': source, 'field': field,
                        'expression': expression, 'argument_names': [a.get('name') for a in call.arguments]}
                if item not in record['occurrences']:
                    record['occurrences'].append(item)
    rows = sorted(records.values(), key=lambda r: (r['category'], r['symbol']))
    return {'schema': 'ui-migration.api-scan.v1', 'page': page.get('page'),
            'scope': 'selected page layout expressions and their collected bindings; not all app business APIs',
            'project_code_executed': False, 'counts': dict(Counter(r['category'] for r in rows)),
            'builtin_adapters': BUILTIN_REGISTRY.inventory(), 'apis': rows}


def skeleton(record):
    symbol = record['symbol']
    identifier = hashlib.sha256(symbol.encode()).hexdigest()[:12]
    capability = record['capability']
    if capability is None:
        return None
    return (f'# Candidate only: {symbol}. Confirm semantics against the listed source calls.\n'
            'from ui_migration.frontend.api_adapters.registry import ApiAdapter\n'
            'from ui_migration.frontend.page_model import UNRESOLVED\n\n'
            'def evaluate(call, context, seen):\n'
            '    return UNRESOLVED\n\n'
            f'ADAPTERS = [ApiAdapter("project.{identifier}", {capability!r}, ({symbol!r},), evaluate)]\n')
