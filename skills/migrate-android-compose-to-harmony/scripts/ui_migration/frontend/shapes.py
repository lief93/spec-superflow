"""One source shape adapter for semantic arguments, clips and backgrounds."""
from ui_migration.semantics.expressions import LayoutDimension

CORNERS = ('top_left', 'top_right', 'bottom_right', 'bottom_left')


def corner(value):
    if isinstance(value, LayoutDimension) and value.unit == 'dp' and value.value >= 0:
        return {'value': value.value, 'unit': 'dp'}
    if type(value) is int and 0 <= value <= 100:
        return {'value': value, 'unit': 'percent'}
    if type(value) is float and value >= 0:
        return {'value': value, 'unit': 'px'}
    return None


def shape_value(call, context, seen):
    arguments = call.arguments
    absolute = call.name == 'AbsoluteRoundedCornerShape'
    if len(arguments) == 1 and arguments[0].get('name') in (None, 'size', 'percent'):
        size = corner(context.value(arguments[0]['value'], seen))
        if size:
            return {'kind': 'rounded_corner', 'radius_' + size['unit']: size['value']}
        return context.unresolved
    names = ('topLeft', 'topRight', 'bottomRight', 'bottomLeft') if absolute else (
        'topStart', 'topEnd', 'bottomEnd', 'bottomStart')
    percent = any(str(arg.get('name', '')).endswith('Percent') for arg in arguments)
    keys = tuple(name + 'Percent' for name in names) if percent else names
    if not arguments or any(arg.get('name') not in keys for arg in arguments):
        return context.unresolved
    sizes = {}
    for arg in arguments:
        size = corner(context.value(arg['value'], seen))
        if size is None or (percent != (size['unit'] == 'percent')):
            return context.unresolved
        sizes[arg['name']] = size
    units = {value['unit'] for value in sizes.values()}
    if len(units) != 1:
        return context.unresolved
    default = {'value': 0, 'unit': next(iter(units))}
    return {'kind': 'rounded_corner', 'absolute': absolute,
            'corners': [sizes.get(key, default) for key in keys]}


def shape_surface(value, direction, dimensions=()):
    if not isinstance(value, dict):
        return None
    if value.get('kind') == 'circle':
        sizes = [{'value': 50, 'unit': 'percent'}] * 4
    elif value.get('kind') == 'rounded_corner':
        sizes = value.get('corners')
        if sizes is None:
            unit = next((unit for unit in ('dp', 'px', 'percent') if 'radius_' + unit in value), None)
            if unit is None:
                return None
            sizes = [{'value': value['radius_' + unit], 'unit': unit}] * 4
        elif not value.get('absolute'):
            if any(size != sizes[0] for size in sizes) and direction not in ('ltr', 'rtl'):
                return None
            if direction == 'rtl':
                sizes = [sizes[1], sizes[0], sizes[3], sizes[2]]
    else:
        return None
    if all(size['unit'] == 'dp' for size in sizes):
        return {'corner_radius_dp': dict(zip(CORNERS, [size['value'] for size in sizes])),
                'corner_sizes': None}
    reference = None
    if len(dimensions) == 2 and all(type(size) in (int, float) and size >= 0 for size in dimensions) and all(
        size['unit'] in ('dp', 'percent') for size in sizes
    ):
        minimum = min(dimensions)
        radii = [minimum * size['value'] / 100 if size['unit'] == 'percent' else size['value'] for size in sizes]
        for first, second in ((0, 3), (1, 2)):
            total = radii[first] + radii[second]
            if total > minimum:
                radii[first] *= minimum / total
                radii[second] *= minimum / total
        reference = dict(zip(CORNERS, radii))
    return {'corner_radius_dp': reference, 'corner_sizes': dict(zip(CORNERS, sizes))}
