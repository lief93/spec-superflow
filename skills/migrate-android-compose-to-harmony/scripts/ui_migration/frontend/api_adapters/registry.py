"""Resolve API identity before dispatch; adapters return values, not UI trees."""
from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Callable
from collections.abc import Mapping

from ui_migration.frontend.page_model import UNRESOLVED
from ui_migration.semantics.expressions import LayoutDimension, LayoutExpressionError
from ui_migration.semantics.syntax import call_from


class AdapterConflict(ValueError):
    pass


CAPABILITIES = frozenset({'image', 'font', 'background', 'shape', 'border', 'size', 'text', 'state'})


@dataclass(frozen=True)
class ApiAdapter:
    id: str
    capability: str
    symbols: tuple[str, ...]
    evaluate: Callable
    aliases: tuple[str, ...] = ()
    receiver_kind: str | None = None


def frozen(value):
    if isinstance(value, dict):
        return MappingProxyType({key: frozen(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(frozen(item) for item in value)
    return value


@dataclass(frozen=True)
class AdapterContext:
    values: object
    value: Callable
    render: Callable
    unresolved: object = UNRESOLVED
    receiver: object = UNRESOLVED


@dataclass(frozen=True)
class AdapterMatch:
    adapter: ApiAdapter
    receiver: object = UNRESOLVED


class ReadOnlyValues(Mapping):
    def __init__(self, values):
        self._values = values

    def __getitem__(self, key):
        if key == '__api_registry':
            raise KeyError(key)
        return frozen(self._values[key])

    def __iter__(self):
        return (key for key in self._values if key != '__api_registry')

    def __len__(self):
        return len(self._values) - int('__api_registry' in self._values)


def validate_value(value):
    if value is UNRESOLVED or value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if isinstance(value, LayoutDimension):
        if value.unit not in {'dp', 'sp', 'px'} or not math.isfinite(value.value):
            raise ValueError('adapter returned an invalid dimension')
        return
    if isinstance(value, (list, tuple, frozenset)):
        for item in value:
            validate_value(item)
        return
    if isinstance(value, dict):
        if any(key in value for key in ('components', 'parent_id', 'children_ids', 'frame', 'bbox', 'arkts', 'visible')):
            raise ValueError('API adapter must return a semantic value, not layout or visibility overrides')
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError('adapter record keys must be strings')
            validate_value(item)
        return
    raise ValueError('adapter returned a non-semantic or non-finite value')


class AdapterRegistry:
    def __init__(self, adapters, identities=(), component_adapters=()):
        self.adapters = tuple(adapters)
        self.identities = tuple(identities)
        self.component_adapters = tuple(component_adapters)
        self._symbols, self._aliases, self._members, ids = {}, {}, {}, set()
        for adapter in self.adapters:
            if not isinstance(adapter, ApiAdapter) or adapter.capability not in CAPABILITIES or not callable(adapter.evaluate):
                raise ValueError('invalid API adapter declaration')
            if not adapter.id or adapter.id in ids or not adapter.symbols:
                raise AdapterConflict('duplicate/empty adapter id or symbols: ' + adapter.id)
            ids.add(adapter.id)
            for symbol in adapter.symbols:
                if adapter.receiver_kind:
                    key = (adapter.receiver_kind, symbol)
                    if key in self._members:
                        raise AdapterConflict('duplicate typed member API: ' + str(key))
                    self._members[key] = adapter
                    continue
                if symbol in self._symbols:
                    raise AdapterConflict('duplicate API symbol: ' + symbol)
                self._symbols[symbol] = adapter
            for alias in adapter.aliases:
                self._aliases.setdefault(alias, []).append(adapter)

    def select(self, name, imports):
        first, separator, suffix = name.partition('.')
        resolved = imports.get(first, first) + (separator + suffix if separator else '')
        if first in imports:
            return self._symbols.get(resolved)
        exact = self._symbols.get(name)
        if exact:
            return exact
        candidates = self._aliases.get(name, [])
        if len(candidates) > 1:
            raise AdapterConflict('ambiguous API alias: ' + name)
        return candidates[0] if candidates else None

    def resolve(self, call, context, seen):
        adapter = self.select(call.qualified_name, context.values.get('__source_imports') or {}) if call else None
        receiver = UNRESOLVED
        if adapter is None and call and call.receiver is not None and any(name == call.name for _, name in self._members):
            try:
                receiver = context.value(call.receiver, seen)
            except LayoutExpressionError:
                receiver = UNRESOLVED
            kind = receiver.get('kind') if isinstance(receiver, dict) else None
            if isinstance(receiver, str) and len(receiver) == 9 and receiver.startswith('#'):
                kind = 'color'
            adapter = self._members.get((kind, call.name))
        return AdapterMatch(adapter, receiver) if adapter else None

    def evaluate(self, node, context, seen, match=None):
        call = call_from(node)
        match = match or self.resolve(call, context, seen)
        if match is None:
            return UNRESOLVED
        restricted = AdapterContext(ReadOnlyValues(context.values), context.value, context.render,
                                    receiver=match.receiver)
        result = match.adapter.evaluate(call, restricted, seen)
        validate_value(result)
        return result

    def inventory(self):
        return [{'id': a.id, 'capability': a.capability, 'symbols': list(a.symbols),
                 'aliases': list(a.aliases), 'receiver_kind': a.receiver_kind} for a in self.adapters]
