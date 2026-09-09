"""Validate and decode embedded business UI variants, never external state files."""
import copy

from ui_migration.common import ArkUIPageError


def decode_catalogs(version, decode):
    catalogs = version.get('meta', {}).get('migration', {}).get('componentUiStates', [])
    definitions = {d['id']:d for d in version.get('meta', {}).get('migration', {}).get('componentDefinitions', [])}
    result = {}
    for catalog in catalogs:
        if catalog.get('schema') != 'ui-migration.component-ui-states.v1':
            raise ArkUIPageError('invalid business component UI state schema')
        definition = definitions.get(catalog.get('definition_id'), {})
        if definition.get('type') != catalog.get('name') or definition.get('parameters', []) != catalog.get('parameters'):
            raise ArkUIPageError('component UI state declaration must match the source definition')
        variants = catalog.get('variants', [])
        ids = [v.get('id') for v in variants]
        if not ids or len(ids) != len(set(ids)) or catalog.get('selected') not in ids or not all(isinstance(v,str) for v in ids):
            raise ArkUIPageError('component UI state IDs must be unique and include selected state')
        record = {k:copy.deepcopy(v) for k,v in catalog.items() if k != 'variants'}
        record['variants'] = []
        for index, variant in enumerate(variants):
            layer = variant['layer']
            mapping = {}
            def inventory(node):
                mapping[node['id']] = node['id'] + '__ui_' + str(index)
                for child in node.get('layers', []):
                    inventory(child)
            inventory(layer)
            def rename(value):
                if isinstance(value, str):
                    return mapping.get(value, value)
                if isinstance(value, dict):
                    return {k:rename(v) for k,v in value.items()}
                if isinstance(value, list):
                    return [rename(v) for v in value]
                return value
            document = {'meta':copy.deepcopy(version['meta']), 'assets':copy.deepcopy(version['assets']),
                        'artboard':copy.deepcopy(version['artboard'])}
            document['meta']['migration'].pop('componentUiStates', None)
            document['meta']['sourceGeneration'] = rename(variant['source_generation'])
            document['artboard']['layers'] = [rename(layer)]
            page = decode(document)
            roots = [n for n in page['components'] if n['parent_id'] is None]
            if len(roots) != 1 or roots[0].get('definition_id') != catalog['definition_id']:
                raise ArkUIPageError('component UI variant must belong to the declared business definition')
            record['variants'].append({'id':variant['id'], 'page':page, 'root':roots[0],
                                       'condition':variant.get('condition')})
        if catalog['instance_id'] in result:
            raise ArkUIPageError('duplicate business component UI state instance')
        result[catalog['instance_id']] = record
    return result
