"""Code-polymorphic resource translation; never reads a resource's final value."""
from abc import ABC, abstractmethod

from ui_migration.contracts.style_tokens import validate_token_mappings
from .registry import ApiAdapter


class KeyedResourceAdapter(ABC):
    def __init__(self, adapter_id, symbols, kind, *, key_parameter='key',
                 parameters=(), source_unit=None, target_unit=None):
        self.adapter_id, self.symbols, self.kind = adapter_id, tuple(symbols), kind
        self.key_parameter, self.parameters = key_parameter, tuple(parameters)
        self.units = {} if source_unit is None else {'sourceUnit':source_unit, 'targetUnit':target_unit}

    @abstractmethod
    def harmony_target(self, key, arguments):
        """Return module/export/member and literal call arguments, or None if unsupported."""

    def declaration(self):
        capability = {'color':'background', 'string':'text', 'dimension':'size', 'number':'size'}[self.kind]
        return ApiAdapter(self.adapter_id, capability, self.symbols, self.evaluate)

    def evaluate(self, call, context, seen):
        names = (self.key_parameter, *self.parameters)
        if len(call.arguments) != len(names) or any(a.get('name') and a['name'] not in names for a in call.arguments):
            return context.unresolved
        values = {}
        for index, name in enumerate(names):
            argument = call.argument(name, index)
            if argument is None:
                return context.unresolved
            values[name] = context.value(argument, seen)
        key = values.pop(self.key_parameter)
        if not isinstance(key, str) or not key:
            return context.unresolved
        target = self.harmony_target(key, values)
        if target is None:
            return context.unresolved
        spec = {'kind':self.kind, 'target':target, **self.units}
        validate_token_mappings({'resource':spec})
        return {'kind':'platform_resource_reference', 'key':key, 'reference':spec}
