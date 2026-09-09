"""Typed UI-only constructors, evaluated through PSI argument bindings."""
from ui_migration.frontend.page_model import UNRESOLVED
from ui_migration.semantics.expressions import LayoutDimension
from ui_migration.semantics.syntax import qualified_name
from .registry import ApiAdapter


def fixed_cells(call, context, seen):
    node = call.argument('count', 0)
    value = context.value(node, seen) if node else UNRESOLVED
    return {'kind': 'grid_cells', 'mode': 'fixed', 'value': value} if type(value) is int and 0 < value <= 200 else UNRESOLVED


def adaptive_cells(call, context, seen):
    node = call.argument('minSize', 0)
    value = context.value(node, seen) if node else UNRESOLVED
    return {'kind': 'grid_cells', 'mode': 'adaptive', 'value': value.value} if isinstance(value, LayoutDimension) and value.unit == 'dp' and value.value > 0 else UNRESOLVED


def spaced_by(call, context, seen):
    node = call.argument('space', 0)
    value = context.value(node, seen) if node else UNRESOLVED
    if not isinstance(value, LayoutDimension) or value.unit != 'dp':
        return UNRESOLVED
    if call.argument('alignment', 1) is not None:
        return UNRESOLVED
    return {'kind': 'arrangement', 'mode': 'Start', 'space_dp': value.value}


def drawer_state(call, context, seen):
    node = call.argument('initialValue', 0)
    name = qualified_name(node) if node else None
    if name not in {'DrawerValue.Open', 'DrawerValue.Closed'}:
        value = context.value(node, seen) if node else UNRESOLVED
        name = value if isinstance(value, str) else None
    if name in {'DrawerValue.Open', 'DrawerValue.Closed'}:
        return {'kind': 'drawer_state', 'open': name.endswith('.Open')}
    return UNRESOLVED


ADAPTERS = (
    ApiAdapter('compose.arrangement-spacing', 'size', ('androidx.compose.foundation.layout.Arrangement.spacedBy',),
        spaced_by, aliases=('Arrangement.spacedBy',)),
    ApiAdapter('compose.grid-fixed', 'size', ('androidx.compose.foundation.lazy.grid.GridCells.Fixed',
        'androidx.compose.foundation.lazy.staggeredgrid.StaggeredGridCells.Fixed'), fixed_cells,
        aliases=('GridCells.Fixed', 'StaggeredGridCells.Fixed')),
    ApiAdapter('compose.grid-adaptive', 'size', ('androidx.compose.foundation.lazy.grid.GridCells.Adaptive',
        'androidx.compose.foundation.lazy.staggeredgrid.StaggeredGridCells.Adaptive'), adaptive_cells,
        aliases=('GridCells.Adaptive', 'StaggeredGridCells.Adaptive')),
    ApiAdapter('compose.drawer-state', 'state', ('androidx.compose.material3.rememberDrawerState',),
        drawer_state, aliases=('rememberDrawerState',)),
)
