"""Resolve unknown values using the consumer's expected type, without object mappings."""
from ui_migration.frontend.api_adapters.keyed_resources import KeyedResourceAdapter


class ProjectValueAdapter(KeyedResourceAdapter):
    def resolve(self, reference):
        owner, _, key = reference.symbol.rpartition('.')
        # These are project library identities, not names of UI parameters.
        owners = {'dimension': 'company.theme.Dimensions', 'color': 'company.theme.Colors'}
        if owner != owners[self.kind] or not key:
            return None
        method = 'fontSize' if self.kind == 'dimension' else 'color'
        return {'key': key, 'target': {
            'module': './ProjectTypography', 'export': 'ProjectTypography',
            'member': method, 'arguments': [key],
        }}


# Empty symbols: normal values/context resolve first, then dispatch by expected type.
ADAPTERS = [
    ProjectValueAdapter('project.text-size', (), 'dimension',
                        source_unit='sp', target_unit='fp').declaration(),
    ProjectValueAdapter('project.color', (), 'color').declaration(),
]
