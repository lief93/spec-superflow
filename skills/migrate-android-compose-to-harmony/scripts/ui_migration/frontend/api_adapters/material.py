from .registry import ApiAdapter


def colors(call, context, seen):
    values = {}
    for arg in call.arguments:
        name = arg.get('name')
        if not name:
            return context.unresolved
        value = context.value(arg['value'], seen)
        if not isinstance(value, str) or not value.startswith('#') or len(value) != 9:
            return context.unresolved
        values[name] = value
    return {'kind': 'material_colors', 'values': values}


ADAPTERS = (ApiAdapter('material.TopAppBarColors', 'background',
    ('androidx.compose.material3.TopAppBarColors',), colors, aliases=('TopAppBarColors',)),
    ApiAdapter('material.OutlinedTextFieldDefaults.colors', 'background',
    ('androidx.compose.material3.OutlinedTextFieldDefaults.colors',), colors, aliases=('OutlinedTextFieldDefaults.colors',)),
    ApiAdapter('material.TextFieldDefaults.colors', 'background',
    ('androidx.compose.material3.TextFieldDefaults.colors',), colors, aliases=('TextFieldDefaults.colors',))) + tuple(ApiAdapter('material.' + owner + '.' + method, 'background',
    ('androidx.compose.material3.' + owner + '.' + method,), colors,
    aliases=(owner + '.' + method,)) for owner, method in (
        ('ListItemDefaults', 'colors'), ('FilterChipDefaults', 'filterChipColors'),
        ('NavigationBarItemDefaults', 'colors'), ('NavigationRailItemDefaults', 'colors'),
        ('MenuDefaults', 'itemColors'),
        ('CardDefaults', 'cardColors'), ('ButtonDefaults', 'buttonColors'),
        ('CheckboxDefaults', 'colors'), ('RadioButtonDefaults', 'colors'),
        ('SwitchDefaults', 'colors'), ('IconButtonDefaults', 'iconButtonColors'),
        ('IconButtonDefaults', 'iconToggleButtonColors'),
        ('ButtonDefaults', 'textButtonColors'), ('ButtonDefaults', 'outlinedButtonColors'),
        ('TopAppBarDefaults', 'topAppBarColors'), ('TopAppBarDefaults', 'centerAlignedTopAppBarColors')))
