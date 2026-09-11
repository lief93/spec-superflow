"""Resolve API identity before dispatch; adapters return values, not UI trees."""
from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Callable
from collections.abc import Mapping

from ui_migration.frontend.page_model import UNRESOLVED
from ui_migration.semantics.expressions import LayoutDimension, LayoutExpressionError
from ui_migration.semantics.syntax import Call, call_from


class AdapterConflict(ValueError):
    pass


CAPABILITIES = frozenset({'image', 'font', 'background', 'shape', 'border', 'size', 'text', 'state', 'value'})


@dataclass(frozen=True)
class ApiAdapter:
    id: str
    capability: str
    symbols: tuple[str, ...]
    evaluate: Callable
    aliases: tuple[str, ...] = ()
    receiver_kind: str | None = None
    access: str = 'call'
    fallback_type: tuple | None = None
    fallback: Callable | None = None


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
    symbol: str | None = None


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
        self._resource_owners = {}
        self._fallbacks = {}
        for adapter in self.adapters:
            if not isinstance(adapter, ApiAdapter) or adapter.capability not in CAPABILITIES or not callable(adapter.evaluate):
                raise ValueError('invalid API adapter declaration')
            if not adapter.id or adapter.id in ids or not (adapter.symbols or adapter.fallback_type):
                raise AdapterConflict('duplicate/empty adapter id or symbols: ' + adapter.id)
            ids.add(adapter.id)
            if adapter.access not in {'call', 'resource'}:
                raise ValueError('invalid API access kind')
            if adapter.access == 'resource':
                if adapter.aliases or adapter.receiver_kind:
                    raise ValueError('resource adapters require qualified symbols')
            if adapter.fallback_type is not None:
                if adapter.access != 'resource' or not callable(adapter.fallback):
                    raise ValueError('typed fallback requires a resource resolver')
                self._fallbacks.setdefault(adapter.fallback_type, []).append(adapter)
            for symbol in adapter.symbols:
                if adapter.access == 'resource' and symbol.endswith('.*'):
                    owner = symbol[:-2]
                    if owner in self._resource_owners:
                        raise AdapterConflict('duplicate resource owner: ' + owner)
                    self._resource_owners[owner] = adapter
                    continue
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

    @staticmethod
    def qualified_symbol(name, imports):
        first, separator, suffix = name.partition('.')
        return imports.get(first, first) + (separator + suffix if separator else '')

    def select(self, name, imports):
        first = name.partition('.')[0]
        resolved = self.qualified_symbol(name, imports)
        exact = self._symbols.get(resolved)
        owner = self._resource_owners.get(resolved.rpartition('.')[0])
        if exact and owner and exact is not owner:
            raise AdapterConflict('ambiguous resource symbol: ' + resolved)
        if exact or owner:
            return exact or owner
        if first in imports:
            return None
        candidates = self._aliases.get(name, [])
        if len(candidates) > 1:
            raise AdapterConflict('ambiguous API alias: ' + name)
        return candidates[0] if candidates else None

    def property_value(self, name, context, seen):
        imports = context.values.get('__source_imports') or {}
        adapter = self.select(name, imports)
        if adapter is None or adapter.access != 'resource':
            return UNRESOLVED
        restricted = AdapterContext(ReadOnlyValues(context.values), context.value, context.render)
        result = adapter.evaluate(Call(self.qualified_symbol(name, imports), (), reference=True), restricted, seen)
        validate_value(result)
        return result

    def resolve(self, call, context, seen):
        adapter = self.select(call.qualified_name, context.values.get('__source_imports') or {}) if call else None
        symbol = None
        if adapter is None and call and context.values.get('__source_functions'):
            from ui_migration.frontend.source_values import source_function_candidates
            from ui_migration.frontend.source_symbols import function_fq_name, matches_argument_shape
            functions = [f for f in source_function_candidates(call, context) if matches_argument_shape(f, call)]
            mapped = [(function_fq_name(f), self.select(function_fq_name(f), {})) for f in functions]
            if any(candidate for _, candidate in mapped):
                if len(functions) != 1:
                    raise LayoutExpressionError('ambiguous source overload for adapter: ' + call.name)
                symbol, adapter = mapped[0]
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
        return AdapterMatch(adapter, receiver, symbol) if adapter else None

    def evaluate(self, node, context, seen, match=None):
        call = call_from(node)
        match = match or self.resolve(call, context, seen)
        if match is None:
            return UNRESOLVED
        restricted = AdapterContext(ReadOnlyValues(context.values), context.value, context.render,
                                    receiver=match.receiver)
        if match.adapter.access == 'resource':
            call = Call(match.symbol or self.qualified_symbol(call.qualified_name, context.values.get('__source_imports') or {}),
                        call.arguments, safe=call.safe)
        result = match.adapter.evaluate(call, restricted, seen)
        validate_value(result)
        return result

    def inventory(self):
        return [{'id': a.id, 'capability': a.capability, 'symbols': list(a.symbols),
                 'aliases': list(a.aliases), 'receiver_kind': a.receiver_kind,
                 **({'access': a.access} if a.access != 'call' else {}),
                 **({'fallback_type': list(a.fallback_type)} if a.fallback_type else {})} for a in self.adapters]

    def fallback_value(self, node, source_type, context, seen, reason):
        types = {'Color': ('color', None), 'String': ('string', None),
                 'Dp': ('dimension', 'dp'), 'TextUnit': ('dimension', 'sp'),
                 'Int': ('number', None), 'Long': ('number', None),
                 'Float': ('number', None), 'Double': ('number', None)}
        restricted = AdapterContext(ReadOnlyValues(context.values), context.value, context.render)
        for adapter in self._fallbacks.get(types.get(source_type, ('object', source_type)), ()):
            result = adapter.fallback(node, source_type, restricted, seen, reason)
            validate_value(result)
            if result is not UNRESOLVED:
                return result
        return UNRESOLVED
