"""Compose pager state is UI data, evaluated through the shared PSI context."""
from ui_migration.frontend.page_model import UNRESOLVED
from .registry import ApiAdapter


def pager_state(call, context, seen):
    count = call.argument('pageCount', 2)
    if count is None:
        lambdas = [a['value'] for a in call.arguments if not a.get('name') and a['value'].get('kind') == 'lambda']
        count = lambdas[-1] if lambdas else None
    if count is None or count.get('kind') != 'lambda':
        return UNRESOLVED
    count = context.value(count['body'], seen)
    def value(name, index, default):
        node = call.argument(name, index)
        return context.value(node, seen) if node is not None and node.get('kind') != 'lambda' else default
    initial = value('initialPage', 0, 0)
    offset = value('initialPageOffsetFraction', 1, 0)
    if type(count) is not int or count < 0 or type(initial) is not int or initial < 0 or type(offset) not in (int, float):
        return UNRESOLVED
    return {'kind': 'pager_state', 'pageCount': count, 'currentPage': initial,
            'currentPageOffsetFraction': offset}


ADAPTERS = (ApiAdapter('compose.pager-state', 'state',
    ('androidx.compose.foundation.pager.rememberPagerState',), pager_state, aliases=('rememberPagerState',)),)
