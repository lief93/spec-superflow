"""Map a token family without registering each individual token."""
from ui_migration.frontend.api_adapters.keyed_resources import KeyedResourceAdapter


class ProjectTypographyAdapter(KeyedResourceAdapter):
    def resolve(self, reference):
        owner, _, key = reference.symbol.rpartition('.')
        if owner != 'company.theme.TypographyTokens' or not key:
            return None

        def target(member):
            return {'module': './ProjectTypography', 'export': 'ProjectTypography',
                    'member': member, 'arguments': [key]}

        def dimension(member):
            return {'kind': 'dimension', 'sourceUnit': 'sp', 'targetUnit': 'fp',
                    'target': target(member)}

        return {
            'key': key,
            'target': target('getStyle'),
            'properties': {
                'fontSize': dimension('fontSize'),
                'fontWeight': {'kind': 'number', 'target': target('fontWeight')},
                'color': {'kind': 'color', 'target': target('color')},
                'lineHeight': dimension('lineHeight'),
            },
        }


ADAPTERS = [ProjectTypographyAdapter(
    'project.typography', ('company.theme.TypographyTokens.*',), 'object',
    source_type='androidx.compose.ui.text.TextStyle',
    target_type={'module': './ProjectTypography', 'export': 'ProjectTextStyle'},
).declaration()]
