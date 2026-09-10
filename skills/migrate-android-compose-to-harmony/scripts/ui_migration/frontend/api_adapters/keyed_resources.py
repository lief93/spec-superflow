"""Code-polymorphic resource translation; never reads a resource's final value."""
from dataclasses import dataclass
from collections.abc import Mapping

from ui_migration.contracts.resource_values import validate_object_type, validate_resource_value
from .registry import ApiAdapter, frozen


@dataclass(frozen=True)
class ResourceReference:
    symbol: str
    kind: str
    key: str | None
    arguments: Mapping[str, object]
    expression: str = ''
    source_type: str | None = None
    source_file: str | None = None
    reason: str | None = None


class KeyedResourceAdapter:
    def __init__(self, adapter_id, symbols, kind, *, key_parameter='key',
                 parameters=(), source_unit=None, target_unit=None, source_type=None, target_type=None):
        self.adapter_id, self.symbols, self.kind = adapter_id, tuple(symbols), kind
        self.key_parameter, self.parameters = key_parameter, tuple(parameters)
        self.units = {} if source_unit is None else {'sourceUnit':source_unit, 'targetUnit':target_unit}
        self.object_types = {}
        if kind == 'object':
            validate_object_type(source_type, target_type)
            if source_unit is not None or target_unit is not None:
                raise ValueError('object adapters do not have scalar units')
            self.object_types = {'sourceType':source_type, 'targetType':dict(target_type)}
        elif source_type is not None or target_type is not None:
            raise ValueError('source_type/target_type are for object adapters')

    def harmony_target(self, key, arguments):
        """Return module/export/member and literal call arguments, or None if unsupported."""
        raise NotImplementedError('implement resolve(reference) or harmony_target(key, arguments)')

    def resolve(self, reference):
        """Return key/target, plus optional object properties keyed by source member name."""
        if reference.key is None:
            return None
        arguments = {name: value for name, value in reference.arguments.items() if name != self.key_parameter}
        target = self.harmony_target(reference.key, arguments)
        return {'key': reference.key, 'target': target} if target is not None else None

    def declaration(self):
        capability = {'color':'background', 'string':'text', 'dimension':'size', 'number':'size', 'object':'value'}[self.kind]
        return ApiAdapter(self.adapter_id, capability, self.symbols, self.evaluate, access='resource',
            fallback_type=(self.kind, self.object_types.get('sourceType', self.units.get('sourceUnit'))),
            fallback=self.evaluate_fallback)

    def evaluate_fallback(self, node, source_type, context, seen, reason):
        from ui_migration.semantics.syntax import qualified_name, call_from
        from ui_migration.semantics.expressions import LayoutExpressionError
        from .registry import AdapterRegistry
        call = call_from(node)
        name = qualified_name(node) or (call.qualified_name if call else '')
        symbol = AdapterRegistry.qualified_symbol(name, context.values.get('__source_imports') or {})
        # A member name is not evidence of a resource key. The project owns extraction.
        values = {}
        for index, argument in enumerate(call.arguments if call else ()):
            try:
                values[argument.get('name') or str(index)] = context.value(argument['value'], seen)
            except LayoutExpressionError:
                values[argument.get('name') or str(index)] = context.unresolved
        reference = ResourceReference(symbol, self.kind, None, frozen(values),
            node.get('text', ''), source_type, context.values.get('__source_file'), reason)
        return self.resource_value(self.resolve(reference), context)

    def evaluate(self, call, context, seen):
        names = (self.key_parameter, *self.parameters)
        legacy = type(self).resolve is KeyedResourceAdapter.resolve
        if not call.reference and legacy and (len(call.arguments) != len(names) or any(a.get('name') and a['name'] not in names for a in call.arguments)):
            return context.unresolved
        values = {}
        for index, argument in enumerate(call.arguments):
            name = argument.get('name') or (names[index] if index < len(names) else str(index))
            if name in values:
                return context.unresolved
            values[name] = context.value(argument['value'], seen)
        key = call.name.rsplit('.', 1)[-1] if call.reference else values.get(self.key_parameter)
        reference = ResourceReference(call.qualified_name, self.kind,
            key if isinstance(key, str) and key else None, frozen(values))
        return self.resource_value(self.resolve(reference), context)

    def resource_value(self, resolved, context):
        if resolved is None:
            return context.unresolved
        optional = {'properties'} if self.kind == 'object' else set()
        if not isinstance(resolved, dict) or set(resolved) - optional != {'key', 'target'} or not isinstance(resolved['key'], str) or not resolved['key']:
            raise ValueError('resource resolution requires a nonempty key and target')
        spec = {'kind':self.kind, 'target':resolved['target'], **self.units, **self.object_types}
        if 'properties' in resolved:
            spec['properties'] = resolved['properties']
        value = {'kind':'platform_resource_reference', 'key':resolved['key'], 'reference':spec}
        validate_resource_value(value)
        return value
