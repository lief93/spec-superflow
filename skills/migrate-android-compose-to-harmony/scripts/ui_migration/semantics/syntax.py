"""Structured Kotlin call access shared by bounded value adapters."""
from dataclasses import dataclass


def syntax_shape(node):
    """Compare PSI structure independently of source whitespace and comments."""
    if isinstance(node, list):
        return [syntax_shape(item) for item in node]
    if isinstance(node, dict):
        return {key: syntax_shape(value) for key, value in node.items()
                if key != 'text' or node.get('kind') == 'literal' and 'parts' not in node}
    return node


def qualified_name(node):
    if node.get('kind') == 'name':
        return node['name']
    if node.get('kind') == 'qualified' and not node['safe']:
        receiver, selector = qualified_name(node['receiver']), qualified_name(node['selector'])
        if receiver and selector:
            return receiver + '.' + selector
    return None


@dataclass(frozen=True)
class Call:
    name: str
    arguments: tuple
    receiver: dict | None = None
    safe: bool = False
    reference: bool = False

    @property
    def qualified_name(self):
        owner = qualified_name(self.receiver) if self.receiver else None
        return owner + '.' + self.name if owner else self.name

    def argument(self, name, index=0):
        named = [a['value'] for a in self.arguments if a.get('name') == name]
        if named:
            return named[0]
        if index < len(self.arguments) and not self.arguments[index].get('name'):
            return self.arguments[index]['value']
        return None


def call_from(node):
    receiver = None
    safe = False
    if node.get('kind') == 'qualified':
        receiver, safe, node = node['receiver'], node['safe'], node['selector']
    if node.get('kind') != 'call':
        return None
    name = qualified_name(node['callee'])
    return Call(name, tuple(node['arguments']), receiver, safe) if name else None
