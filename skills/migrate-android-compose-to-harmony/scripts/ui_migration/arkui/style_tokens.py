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
        self.consumed.add((component['id'], path))
        return self.target_expression(target)

    def target_expression(self, target):
        from ui_migration.contracts.style_tokens import validate_target
        validate_target(target)
        key = (target['module'], target['export'])
        alias = self.modules.setdefault(key, f'StyleToken{len(self.modules)}')
        expression = alias + '.' + target['member']
        if 'arguments' in target:
            arguments = [arkts_string(v) if isinstance(v, str) else json.dumps(v) for v in target['arguments']]
            expression += '(' + ', '.join(arguments) + ')'
        return expression

    def value(self, value):
        from ui_migration.contracts.resource_values import is_resource_value, validate_resource_value
        from ui_migration.arkui.component_interfaces import literal
        if is_resource_value(value):
            return self.target_expression(validate_resource_value(value)['target'])
        if isinstance(value, list):
            return '[' + ', '.join(self.value(item) for item in value) + ']'
        return literal(value)

    def imports(self):
        return [f'import {{ {symbol} as {alias} }} from {arkts_string(module)};'
                for (module, symbol), alias in self.modules.items()]
