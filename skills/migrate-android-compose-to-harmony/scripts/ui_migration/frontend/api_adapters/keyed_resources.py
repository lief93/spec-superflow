"""Code-polymorphic resource translation; never reads a resource's final value."""
from dataclasses import dataclass
from collections.abc import Mapping

from ui_migration.contracts.style_tokens import validate_token_mappings
from .registry import ApiAdapter, frozen


@dataclass(frozen=True)
class ResourceReference:
    symbol: str
    kind: str
    key: str | None
    arguments: Mapping[str, object]


class KeyedResourceAdapter:
    def __init__(self, adapter_id, symbols, kind, *, key_parameter='key',
                 parameters=(), source_unit=None, target_unit=None):
        self.adapter_id, self.symbols, self.kind = adapter_id, tuple(symbols), kind
        self.key_parameter, self.parameters = key_parameter, tuple(parameters)
        self.units = {} if source_unit is None else {'sourceUnit':source_unit, 'targetUnit':target_unit}

    def harmony_target(self, key, arguments):
        """Return module/export/member and literal call arguments, or None if unsupported."""
        raise NotImplementedError('implement resolve(reference) or harmony_target(key, arguments)')

    def resolve(self, reference):
        """Return key/target; projects can translate the suggested key using source identity."""
        if reference.key is None:
            return None
        arguments = {name: value for name, value in reference.arguments.items() if name != self.key_parameter}
        target = self.harmony_target(reference.key, arguments)
        return {'key': reference.key, 'target': target} if target is not None else None

    def declaration(self):
        capability = {'color':'background', 'string':'text', 'dimension':'size', 'number':'size'}[self.kind]
        return ApiAdapter(self.adapter_id, capability, self.symbols, self.evaluate, access='resource')

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
        resolved = self.resolve(reference)
        if resolved is None:
            return context.unresolved
        if not isinstance(resolved, dict) or set(resolved) != {'key', 'target'} or not isinstance(resolved['key'], str) or not resolved['key']:
            raise ValueError('resource resolution requires a nonempty key and target')
        spec = {'kind':self.kind, 'target':resolved['target'], **self.units}
        validate_token_mappings({'resource':spec})
        return {'kind':'platform_resource_reference', 'key':resolved['key'], 'reference':spec}
