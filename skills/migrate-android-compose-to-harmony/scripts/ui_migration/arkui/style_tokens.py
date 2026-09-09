"""Emit only validated references carried by the single page JSON."""
import json
from ui_migration.contracts.style_tokens import validate_token_reference
from ui_migration.common import arkts_string


class StyleTokenEmitter:
    def __init__(self):
        self.modules = {}
        self.consumed = set()

    def expression(self, component, path):
        reference = component.get('source', {}).get('style_token_references', {}).get(path)
        if reference is None:
            return None
        validate_token_reference(reference, path)
        target = reference['target']
        key = (target['module'], target['export'])
        alias = self.modules.setdefault(key, f'StyleToken{len(self.modules)}')
        self.consumed.add((component['id'], path))
        expression = alias + '.' + target['member']
        if 'arguments' in target:
            arguments = [arkts_string(v) if isinstance(v, str) else json.dumps(v) for v in target['arguments']]
            expression += '(' + ', '.join(arguments) + ')'
        return expression

    def imports(self):
        return [f'import {{ {symbol} as {alias} }} from {arkts_string(module)};'
                for (module, symbol), alias in self.modules.items()]
