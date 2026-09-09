"""Material icon identity shared by source projection, import and rendering."""
import re


def material_icon_identity(expression):
    if not isinstance(expression, str):
        return None
    match = re.fullmatch(r'(?:androidx\.compose\.material\.icons\.)?Icons\.(AutoMirrored\.)?(Default|Filled|Outlined|Rounded|Sharp|TwoTone)\.([A-Z][A-Za-z0-9]*)', expression)
    if not match:
        return None
    mirrored, style, name = match.groups()
    style = 'Filled' if style == 'Default' else style
    path = ('automirrored/' if mirrored else '') + style.lower() + '/' + name + '.kt'
    resource = 'compose_icon_' + ('automirrored_' if mirrored else '') + style.lower() + '_' + name.lower()
    return path, resource
