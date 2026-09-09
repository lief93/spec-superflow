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
        if sum(adapter.matches(d) for d in self.definitions.values()) != 1:
            raise ValueError('component selector matches multiple source definitions; specify source/declaration_id')
        declared = {p['name']: p for p in definition.get('parameters', [])}
        if set(adapter.parameters) & set(adapter.slots):
            raise ValueError('parameter cannot also be a content slot')
        if set(declared) != set(adapter.parameters) | set(adapter.slots):
            raise ValueError('component adapter must account for every parameter: ' +
                             ', '.join(sorted(set(declared) ^ (set(adapter.parameters) | set(adapter.slots)))))
        if len(set(adapter.parameters.values()) | set(adapter.slots.values())) != len(declared):
            raise ValueError('duplicate target parameter or slot')
        bindings = node.get('invocation_bindings') or {}
        arguments = {}
        for name in declared:
            if name not in adapter.parameters:
                continue
            expression = bindings.get(name, declared[name].get('default'))
            if not isinstance(expression, str):
                raise ValueError('component parameter has no value: ' + name)
            value = evaluate(name, expression, arguments)
            if value is UNRESOLVED:
                raise ValueError('component parameter is unresolved: ' + name + ' = ' + expression)
            arguments[name] = value
        slots = {}
        roots = node.get('source', {}).get('caller_slot_roots', {})
        for name, target in adapter.slots.items():
            parameter_type = str(declared[name].get('type', '')).replace(' ', '')
            if '@Composable' not in parameter_type or '()->Unit' not in parameter_type:
                raise ValueError('only no-argument composable slots are supported: ' + name)
            if name not in roots:
                raise ValueError('content slot requires explicit caller content: ' + name)
            slots[target] = list(roots[name])
        properties = adapter.properties(arguments)
        if not isinstance(properties, dict):
            raise ValueError('component adapter properties must be an object')
        # Keyed API adapters can delegate the final value to the Harmony library.
        properties = {k: ({'kind': 'resource', 'target': v['reference']['target']}
                          if isinstance(v, dict) and v.get('kind') == 'platform_resource_reference' else v)
                      for k, v in properties.items()}
        record = {'schema': 'ui-migration.component-reuse.v1', 'adapter_id': adapter.id,
                  'definition_id': definition['id'], 'android': adapter.android,
                  'target': {'module': adapter.module, 'export': adapter.export},
                  'properties': properties, 'slots': slots}
        if type(adapter).properties is ComponentAdapter.properties:
            record['property_parameters'] = {target:source for source, target in adapter.parameters.items()}
        return validate_reuse(record)
