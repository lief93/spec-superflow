"""Typed source-declaration facades over private fixed-state rendering helpers."""
import json

from ui_migration.contracts.component_interfaces import signature, value_matches
from ui_migration.naming import source_identifier


def literal(value):
    if isinstance(value, dict) and value.get('kind') == 'empty_callback':
        return '() => {}'
    return json.dumps(value, ensure_ascii=False)


def state_guard(record):
    return tuple((a['name'], literal(a['value'])) for a in record['arguments']
                 if a['name'] in record.get('state_parameters', [])
                 and a['status'] == 'resolved' and type(a.get('value')) in (str, int, float, bool))


class ComponentInterfaces:
    def __init__(self, owner, diagnostic):
        self.owner, self.diagnostic = owner, diagnostic
        self.entries = {}

    def contract(self, component, definition):
        record = component.get('source', {}).get('component_interface')
        if record is None:
            self.diagnostic(component, 'source.component_interface',
                            'declaration-based interface missing; regenerate the source page JSON')
            return None
        parameters = signature(definition.get('parameters', []))
        if record.get('definition_id') != definition['id'] or record.get('parameters') != parameters:
            raise ValueError('component interface does not match source declaration')
        unsupported = [p for p in parameters if p['status'] != 'resolved']
        for parameter in unsupported:
            self.diagnostic(component, 'source.component_interface.' + parameter['name'], parameter['reason'])
        if unsupported:
            return None
        names = [p['name'] for p in parameters]
        if len(set(names)) != len(names) or any(source_identifier(n) != n for n in names):
            self.diagnostic(component, 'source.component_interface', 'parameter names cannot be preserved as valid ArkTS identifiers')
            return None
        if [a.get('name') for a in record.get('arguments', [])] != names:
            raise ValueError('component call must retain every declared argument in order')
        for parameter, argument in zip(parameters, record['arguments']):
            if argument['status'] == 'resolved' and not value_matches(argument.get('value'), parameter['type']):
                raise ValueError('component argument does not match declared type: ' + parameter['name'])
        return record

    def call(self, component, definition, invocation, record):
        key = definition['id']
        if key not in self.entries:
            preferred = definition['type']
            peers = [d for d in self.owner.definitions.values() if d['type'] == preferred]
            if len(peers) > 1:
                preferred += 'By' + ''.join(p['name'][:1].upper() + p['name'][1:] for p in record['parameters'])
            self.entries[key] = {'name':self.owner.names.allocate(preferred),
                                 'parameters':record['parameters'], 'variants':[], 'definition_id':key}
        entry = self.entries[key]
        unresolved = [a for a in record['arguments'] if a['status'] != 'resolved']
        for argument in unresolved:
            self.diagnostic(component, 'source.component_interface.' + argument['name'], argument['reason'])
        declared_types = {p['name']:p['target_type'] for p in record['parameters']}
        constants = [(a.path, a.expression) for a in invocation.arguments
                     if a.path != 'semantic_key' and declared_types.get(a.source_name) != a.kind]
        variant_key = (invocation.name, constants)
        variant = next((v for v in entry['variants'] if v['key'] == variant_key), None)
        if variant is None:
            guard = state_guard(record)
            if entry['variants'] and (not guard or any(not v['guard'] or v['guard'] == guard for v in entry['variants'])):
                self.diagnostic(component, 'source.component_interface.state',
                                'observed layouts cannot be distinguished by resolved source state parameters; retaining private preview')
                return self.owner.call(invocation, component)
            variant = {'invocation':invocation, 'record':record, 'key':variant_key, 'guard':guard}
            entry['variants'].append(variant)
        if unresolved:
            # Keep the known preview, but never invent callback/model argument values.
            return self.owner.call(invocation, component)
        values = []
        for parameter, argument in zip(record['parameters'], record['arguments']):
            reference = component.get('source', {}).get('invocation_names', {}).get(parameter['name'])
            value = self.owner.bind({'id':component['id'], 'source':{'property_bindings':{
                'source.argument.' + parameter['name']: reference or ''}}},
                'source.argument.' + parameter['name'], literal(argument['value']), parameter['target_type'])
            values.append(value)
        return 'this.' + entry['name'] + '(' + ', '.join(values) + ')'

    def declarations(self):
        lines = []
        for entry in self.entries.values():
            parameters = entry['parameters']
            types = {p['name']:p['target_type'] for p in parameters}
            lines.extend(['  @Builder', '  private ' + entry['name'] + '(' +
                          ', '.join(p['name'] + ': ' + p['target_type'] for p in parameters) + ') {'])
            variants = entry['variants']
            for index, variant in enumerate(variants):
                invocation, record = variant['invocation'], variant['record']
                # Only source state parameters may select an observed layout.
                if len(variants) > 1:
                    guard = [name + ' === ' + value for name, value in variant['guard']]
                    lines.append('    ' + ('if' if index == 0 else 'else if') + ' (' + ' && '.join(guard) + ') {')
                fields = []
                for argument in invocation.arguments:
                    reference = argument.source_name
                    expression = reference if types.get(reference) == argument.kind else argument.expression
                    fields.append(argument.name + ': ' + expression)
                call_args = ['{ ' + ', '.join(fields) + ' }'] if fields else []
                call_args.extend(self.owner.slot_value(slot) for slot in invocation.slots)
                lines.append(('      ' if len(variants)>1 else '    ') + 'this.' + invocation.name + '(' + ', '.join(call_args) + ')')
                if len(variants)>1:
                    lines.append('    }')
            lines.extend(['  }', ''])
        return lines

    def report(self):
        return [{'definition_id':v['definition_id'], 'name':v['name'], 'parameters':v['parameters'],
                 'render_scope':'selected-source-state', 'semantic_key_scope':'definition-relative',
                 'observed_layout_count':len(v['variants'])} for v in self.entries.values()]
