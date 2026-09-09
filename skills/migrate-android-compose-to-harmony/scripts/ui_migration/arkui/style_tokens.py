"""Emit only validated references carried by the single page JSON."""
from ui_migration.contracts.style_tokens import validate_token_mappings, validate_property_token
from ui_migration.common import arkts_string


class StyleTokenEmitter:
    def __init__(self):
        self.modules = {}
        self.consumed = set()

    def expression(self, component, path):
        reference = component.get('source', {}).get('style_token_references', {}).get(path)
        if reference is None:
            return None
        spec = {key: value for key, value in reference.items() if key != 'android'}
        validate_token_mappings({reference['android']: spec})
        validate_property_token(path, spec)
        target = spec['target']
        key = (target['module'], target['export'])
        alias = self.modules.setdefault(key, f'StyleToken{len(self.modules)}')
        self.consumed.add((component['id'], path))
        return alias + '.' + target['member']

    def imports(self):
        return [f'import {{ {symbol} as {alias} }} from {arkts_string(module)};'
                for (module, symbol), alias in self.modules.items()]
