"""One business builder, explicit UI-only selector, all supported branch bodies."""
from ui_migration.contracts.component_interfaces import signature
from ui_migration.arkui.component_interfaces import literal
from ui_migration.naming import source_identifier


class ComponentUiStates:
    def __init__(self, owner):
        self.owner = owner
        self.entries = {}
        self.coverage = []

    def render(self, component, catalog, render_variant, indent):
        definition = catalog['definition_id']
        parameters = signature(catalog['parameters'])
        entry = self.entries.get(definition)
        if entry is None:
            selector = 'uiState'
            names = {p['name'] for p in parameters}
            while selector in names:
                selector = '_' + selector
            entry = {'name':self.owner.names.allocate(catalog['name']), 'parameters':parameters,
                     'selector':selector, 'variants':[], 'selected':catalog['selected']}
            self.entries[definition] = entry
        invocations = []
        for variant in catalog['variants']:
            invocation = self.owner.capture(definition, catalog['name'],
                lambda v=variant: render_variant(v), 'render')
            invocations.append((variant['id'], invocation))
        if not entry['variants']:
            entry['variants'] = invocations
        elif self.variant_signature(entry['variants'], parameters) != self.variant_signature(invocations, parameters):
            self.owner.diagnostic(component, 'source.component_ui_states',
                'component instances have different non-parameter UI facts; shared-state interface coverage is incomplete')
        arguments = {a['name']:a for a in component.get('source', {}).get('component_interface', {}).get('arguments', [])}
        values = []
        for parameter in parameters:
            argument = arguments.get(parameter['name'], {})
            values.append(literal(argument['value']) if parameter['status'] == 'resolved' and argument.get('status') == 'resolved' else 'null')
        values.append(literal(catalog['selected']))
        return [' '*indent + 'this.' + entry['name'] + '(' + ', '.join(values) + ')']

    @staticmethod
    def variant_signature(variants, parameters):
        types = {p['name']:p.get('target_type') for p in parameters}

        def invocation_signature(invocation):
            return (invocation.name, tuple(
                (arg.name, arg.kind, arg.path,
                 'instance-id' if arg.path == 'semantic_key' else
                 ('parameter', arg.source_name) if types.get(arg.source_name) == arg.kind else arg.expression)
                for arg in invocation.arguments),
                tuple(invocation_signature(slot) for slot in invocation.slots))

        return [(state, invocation_signature(invocation)) for state, invocation in variants]

    def declarations(self):
        interfaces = ['class UiBusinessArgument {}', ''] if self.entries else []
        methods = []
        for entry in self.entries.values():
            parameters = entry['parameters']
            fields = []
            for p in parameters:
                if source_identifier(p['name']) != p['name']:
                    raise ValueError('business UI parameter cannot preserve source name: ' + p['name'])
                # Opaque placeholders deliberately do not promise model/API equivalence.
                kind = '(' + p['target_type'] + ') | null' if p['status'] == 'resolved' else 'UiBusinessArgument | null'
                fields.append(p['name'] + ': ' + kind)
            fields.append(entry['selector'] + ': string = ' + literal(entry['selected']))
            methods.extend(['  @Builder', '  private ' + entry['name'] + '(' + ', '.join(fields) + ') {'])
            types = {p['name']:p.get('target_type') for p in parameters}
            for index, (state, invocation) in enumerate(entry['variants']):
                methods.append('    ' + ('if' if index == 0 else 'else if') + ' (' + entry['selector'] + ' === ' + literal(state) + ') {')
                values = []
                for arg in invocation.arguments:
                    expression = '(' + arg.source_name + ' ?? ' + arg.expression + ')' if types.get(arg.source_name) == arg.kind else arg.expression
                    values.append(arg.name + ': ' + expression)
                args = ['{ ' + ', '.join(values) + ' }'] if values else []
                args.extend(self.owner.slot_value(slot) for slot in invocation.slots)
                methods.append('      this.' + invocation.name + '(' + ', '.join(args) + ')')
                methods.append('    }')
            methods.extend(['  }', ''])
        return interfaces, methods

    def report(self):
        return [{'name':e['name'], 'selector':e['selector'], 'parameters':e['parameters'],
                 'states':[state for state,_ in e['variants']], 'business_verified':False,
                 'scope':'business-component-ui-only',
                 'coverage':[v for v in self.coverage if v['name'] == e['name']]} for e in self.entries.values()]
