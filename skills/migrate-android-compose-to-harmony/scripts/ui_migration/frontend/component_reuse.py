"""Project-owned component adapters, separate from scalar resource API adapters."""
from dataclasses import dataclass, field

from ui_migration.contracts.component_reuse import validate_reuse
from ui_migration.frontend.page_model import UNRESOLVED


@dataclass(frozen=True)
class ComponentAdapter:
    id: str
    android: str
    module: str
    export: str
    parameters: dict[str, str] = field(default_factory=dict)
    slots: dict[str, str] = field(default_factory=dict)
    source: str | None = None
    declaration_id: str | None = None

    def matches(self, definition):
        identity = definition.get('identity') or {}
        return (definition.get('component_kind') == 'project_component'
                and identity.get('qualified_name') == self.android
                and (self.source is None or identity.get('source') == self.source)
                and (self.declaration_id is None or identity.get('declaration_id') == self.declaration_id))

    def properties(self, arguments):
        """Override for project-specific value/unit conversion, never raw ArkTS."""
        return {target: arguments[source] for source, target in self.parameters.items()}

    def argument(self, name, expression, arguments, evaluate):
        return evaluate(name, expression, arguments)

    def bind(self, definition, node, evaluate):
        """Explicit adapters must still account for the complete source interface."""
        declared = {p['name']: p for p in definition.get('parameters', [])}
        if set(self.parameters) & set(self.slots):
            raise ValueError('parameter cannot also be a content slot')
        if set(declared) != set(self.parameters) | set(self.slots):
            raise ValueError('component adapter must account for every parameter: ' +
                             ', '.join(sorted(set(declared) ^ (set(self.parameters) | set(self.slots)))))
        if len(set(self.parameters.values()) | set(self.slots.values())) != len(declared):
            raise ValueError('duplicate target parameter or slot')
        bindings = node.get('invocation_bindings') or {}
        arguments = {}
        for name in declared:
            if name not in self.parameters:
                continue
            expression = bindings.get(name, declared[name].get('default'))
            if not isinstance(expression, str):
                raise ValueError('component parameter has no value: ' + name)
            value = self.argument(name, expression, arguments, evaluate)
            if value is UNRESOLVED:
                raise ValueError('component parameter is unresolved: ' + name + ' = ' + expression)
            arguments[name] = value
        slots = {}
        roots = node.get('source', {}).get('caller_slot_roots', {})
        for name, target in self.slots.items():
            parameter_type = str(declared[name].get('type', '')).replace(' ', '')
            if '@Composable' not in parameter_type or '()->Unit' not in parameter_type:
                raise ValueError('only no-argument composable slots are supported: ' + name)
            if name not in roots:
                raise ValueError('content slot requires explicit caller content: ' + name)
            slots[target] = list(roots[name])
        record = {'properties': self.properties(arguments), 'slots': slots}
        if type(self).properties is ComponentAdapter.properties or getattr(self, 'preserve_parameter_names', False):
            record['property_parameters'] = {target:source for source, target in self.parameters.items()}
        return record


class ComponentReuse:
    def __init__(self, adapters, definitions):
        self.definitions = {d['id']: d for d in definitions}
        self.adapters = tuple(adapters)
        ids = set()
        for adapter in self.adapters:
            if not isinstance(adapter, ComponentAdapter) or not adapter.id or adapter.id in ids:
                raise ValueError('invalid or duplicate component adapter')
            ids.add(adapter.id)

    def resolve(self, node, evaluate):
        definition = self.definitions.get(node.get('definition_id'), {})
        matches = [a for a in self.adapters if a.matches(definition)]
        if not matches:
            return None
        if len(matches) != 1:
            raise ValueError('ambiguous component adapters: ' + ', '.join(a.id for a in matches))
        adapter = matches[0]
        if getattr(adapter, 'error', None):
            raise ValueError(adapter.error)
        if sum(adapter.matches(d) for d in self.definitions.values()) != 1:
            raise ValueError('component selector matches multiple source definitions; specify source/declaration_id')
        bound = adapter.bind(definition, node, evaluate)
        properties = bound['properties']
        if not isinstance(properties, dict):
            raise ValueError('component adapter properties must be an object')
        # Keyed API adapters can delegate the final value to the Harmony library.
        properties = {k: ({'kind': 'resource', 'target': v['reference']['target']}
                          if isinstance(v, dict) and v.get('kind') == 'platform_resource_reference'
                          and v['reference']['kind'] != 'object' else v)
                      for k, v in properties.items()}
        record = {'schema': 'ui-migration.component-reuse.v1', 'adapter_id': adapter.id,
                  'definition_id': definition['id'], 'android': adapter.android,
                  'target': {'module': adapter.module, 'export': adapter.export},
                  **bound, 'properties': properties}
        if getattr(adapter, 'call_style', 'properties') != 'properties':
            record['call_style'] = adapter.call_style
        return validate_reuse(record)
