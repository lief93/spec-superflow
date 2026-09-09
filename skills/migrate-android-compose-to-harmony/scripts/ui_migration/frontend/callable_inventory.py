"""PSI-backed content templates, kept out of the active page until invocation."""
from ui_migration.frontend.source_symbols import expression_calls
from page_component_catalog import CONTROL_FAMILIES


def lambda_functions(index, source):
    result = []
    native = {name for names in CONTROL_FAMILIES.values() for name in names}
    content = {f['name'] for f in index.functions
               if index.roles.get(f"{f['source']}:{f['start']}:{f['name']}")=='content'}
    for entry in index.syntax[source].get('lambdas', []):
        syntax = entry['expression']
        if not any(call.name in native or call.name in content for call in expression_calls(syntax['body'])):
            continue
        owner = next((f for f in index.by_source[source] if f['start']<=entry['start']<f['end']), {})
        parameters = [{'name':name,'type':'Any','default':None}
                      for name in syntax.get('parameters', []) if name]
        result.append({**owner, 'source':source,'name':f"__content_{entry['start']}",
            'start':entry['start'],'end':entry['end'],'line':entry['line'],
            'body_start':entry['body_start'],'body':syntax['body'],
            'parameters':parameters,'parameters_text':'('+', '.join(p['name']+': Any' for p in parameters)+')',
            'callable_expression':syntax['text'], 'annotations':['Composable'], 'return_type':'Unit'})
    return result


def callable_field_names(syntax):
    return {p['name'] for c in syntax.get('recordClasses', []) for p in c['properties']
            if '->' in p['type']}
