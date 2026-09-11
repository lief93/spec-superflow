"""Render explicit component-library calls; no frontend or project code loading."""
import json

from ui_migration.contracts.component_reuse import validate_reuse
from ui_migration.naming import NameScope


class ComponentReuseEmitter:
    def __init__(self, root_name, business_components):
        self.modules, self.instances = {}, []
        self.import_names = NameScope({root_name})
        self.business_components = business_components

    def imported(self, module, symbol):
        key = (module, symbol)
        if key not in self.modules:
            self.modules[key] = self.import_names.allocate('Reused' + symbol)
        return self.modules[key]

    def value(self, value):
        if value == {'kind':'omitted_argument'}:
            return 'undefined'
        if value == {'kind':'empty_callback'}:
            return '() => {}'
        if isinstance(value, dict):
            from ui_migration.contracts.resource_values import is_resource_value, validate_resource_value
            spec = validate_resource_value(value) if is_resource_value(value) else value
            target = spec['target']
            expression = self.imported(target['module'], target['export']) + '.' + target['member']
            if 'arguments' in target:
                expression += '(' + ', '.join(self.value(v) for v in target['arguments']) + ')'
            if 'fallback' in spec:
                expression = '(' + expression + ' ?? ' + self.value(spec['fallback']) + ')'
            return expression
        return json.dumps(value, ensure_ascii=False)

    def render(self, component, children, render_slot, indent):
        record = validate_reuse(component['source']['component_reuse'])
        roots = [root for items in record['slots'].values() for root in items]
        if len(roots) != len(children) or set(roots) != {child['id'] for child in children}:
            raise ValueError('component reuse slots must account for every direct child')
        alias = self.imported(record['target']['module'], record['target']['export'])
        from ui_migration.contracts.component_interfaces import signature
        declaration = self.business_components.definitions.get(component.get('definition_id'), {})
        types = {p['name']:p.get('target_type') for p in signature(declaration.get('parameters', []))}
        arguments = []
        for name, value in record['properties'].items():
            expression = self.value(value)
            source = record.get('property_parameters', {}).get(name)
            reference = component.get('source', {}).get('invocation_names', {}).get(source)
            kind = types.get(source)
            if reference and kind:
                expression = self.business_components.bind({'id':component['id'], 'source':{'property_bindings':{
                    'source.reused_property.' + name:reference}}}, 'source.reused_property.' + name, expression, kind)
            arguments.append(expression if record.get('call_style') == 'positional' else name + ': ' + expression)
        self.instances.append({'component_id': component['id'], **record})
        by_id = {child['id']: child for child in children}
        for name, ids in record['slots'].items():
            method = 'render' + record['target']['export'] + name[:1].upper() + name[1:]
            invocation = self.business_components.capture(None, method,
                lambda: [line for root in ids for line in render_slot(by_id[root], 4)])
            call = self.business_components.call(invocation)
            arguments.append(name + ': () => { ' + call + ' }')
        arguments = ', '.join(arguments)
        if record.get('call_style') != 'positional':
            arguments = '{ ' + arguments + ' }'
        return [' ' * indent + alias + '(' + arguments + ')']

    def imports(self, module_path=lambda value: value):
        from ui_migration.common import arkts_string
        return ["import { " + symbol + ' as ' + alias + " } from " + arkts_string(module_path(module)) + ";"
                for (module, symbol), alias in self.modules.items()]
