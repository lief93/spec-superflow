from dataclasses import dataclass, field
from typing import Callable


@dataclass
class ProjectionContext:
    node: dict
    expression: Callable
    evaluate: Callable
    unresolved: object
    slots: tuple[str, ...]

    def issue(self, name, reason):
        self.node.setdefault('unresolved', []).append({
            'path': 'source.control.' + name,
            'expression': self.expression(name) or self.node['type'] + '.' + name, 'reason': reason})

    def value(self, name, default=None):
        expression = self.expression(name)
        if not expression:
            return default
        value = self.evaluate(expression)
        if value is self.unresolved:
            self.issue(name, 'UI argument is unresolved; no replacement value was invented')
            return None
        return value

    def boolean(self, name, default):
        value = self.value(name, default)
        if type(value) is not bool:
            self.issue(name, 'expected a resolved boolean')
            return None
        return value

    def color(self, name, token):
        value = self.value(name, self.evaluate(token))
        if isinstance(value, str) and value.startswith('#'):
            return value
        self.issue(name, 'color requires a resolved theme value or a target token adapter')
        return None

    def background(self, color):
        if color is not None:
            self.node['style']['surface']['background'] = {'type': 'solid', 'color': color}

    def palette(self):
        value = self.value('colors', {'kind': 'material_colors', 'values': {}})
        if isinstance(value, dict) and value.get('kind') == 'material_colors':
            return value['values']
        self.issue('colors', 'component colors require a supported Material color constructor')
        return {}

    def arrangement(self, name):
        expression = self.expression(name)
        modes = {f'Arrangement.{value}': value for value in ('Start', 'End', 'Center', 'SpaceBetween', 'SpaceAround', 'SpaceEvenly', 'Top', 'Bottom')}
        if not expression:
            return {'kind': 'arrangement', 'mode': 'Start', 'space_dp': 0}
        if expression in modes:
            return {'kind': 'arrangement', 'mode': modes[expression], 'space_dp': 0}
        value = self.value(name)
        if isinstance(value, dict) and value.get('kind') == 'arrangement':
            return value
        self.issue(name, 'arrangement requires a supported alignment or spacedBy value')
        return None


@dataclass
class RenderResult:
    lines: list[str]
    consumed: set[str] = field(default_factory=lambda: {'source.control'})
    finalize: Callable | None = None


@dataclass
class RenderContext:
    node: dict
    children: list[dict]
    indent: int
    child: Callable
    length: Callable
    issue: Callable
    declare: Callable
    quote: Callable
    metrics: Callable

    @property
    def prefix(self):
        return ' ' * self.indent

    @property
    def facts(self):
        return self.node.get('source', {}).get('control', {})

    def slot(self, name):
        return [c for c in self.children if c.get('source', {}).get('slot_argument_name', 'content') == name]

    def body(self, parent='Column', children=None, extra=2):
        return [line for child in (self.children if children is None else children)
                for line in self.child(child, parent, self.indent + extra)]


class Control:
    name = ''
    slots = frozenset({'content'})
    arguments = frozenset()

    def project(self, context):
        return {'kind': self.name}

    def render(self, context):
        raise NotImplementedError
