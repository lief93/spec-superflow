"""Resolve pager-specific facts; ordinary child styles stay on the normal path."""
from .page_model import semantic_expression, UNRESOLVED
from .values import evaluate_expression

PAGER_TYPES = {'HorizontalPager', 'VerticalPager'}


def project_pager(node, environment):
    def expression(name):
        if name == 'state' and not semantic_expression(node, name):
            positional = node.get('arguments', {}).get('positional', [])
            if positional:
                return positional[0].get('expression')
        return semantic_expression(node, name) or None

    def value(name, default):
        text = expression(name)
        return evaluate_expression(text, environment) if text is not None else default

    def issue(name, reason):
        node.setdefault('unresolved', []).append({'path': 'source.pager.' + name,
            'expression': expression(name) or name, 'reason': reason})

    state = value('state', UNRESOLVED)
    if not isinstance(state, dict) or state.get('kind') != 'pager_state':
        issue('state', 'pager needs a resolved page count and initial page; page content is retained as a deferred template')
        return None
    count, initial = state['pageCount'], state['currentPage']
    if type(count) is not int or not 0 <= count <= 200 or type(initial) is not int or not 0 <= initial < max(1, count):
        issue('state', 'invalid pager index/count or expansion exceeds 200 pages; no silent truncation')
        return None
    if state.get('currentPageOffsetFraction', 0) != 0:
        issue('state', 'fractional initial scroll offset is not mapped')
    padding = value('contentPadding', {'kind': 'padding_values', 'edges': dict.fromkeys(('start', 'end', 'top', 'bottom'), 0)})
    if not isinstance(padding, dict) or padding.get('kind') != 'padding_values':
        issue('contentPadding', 'pager padding must resolve to PaddingValues')
        padding = None
    spacing = value('pageSpacing', 0)
    if type(spacing) not in (int, float) or spacing < 0:
        issue('pageSpacing', 'page spacing must be a nonnegative dp value')
        spacing = None
    enabled = value('userScrollEnabled', True)
    if type(enabled) is not bool:
        issue('userScrollEnabled', 'scroll enabled must resolve to boolean')
        enabled = None
    horizontal = node['type'] == 'HorizontalPager'
    alignment = expression('verticalAlignment' if horizontal else 'horizontalAlignment')
    allowed = {'Alignment.Top': 'TopStart', 'Alignment.CenterVertically': 'Start', 'Alignment.Bottom': 'BottomStart'} if horizontal else {
        'Alignment.Start': 'TopStart', 'Alignment.CenterHorizontally': 'Top', 'Alignment.End': 'TopEnd'}
    alignment = alignment or ('Alignment.CenterVertically' if horizontal else 'Alignment.CenterHorizontally')
    if alignment not in allowed:
        issue('alignment', 'pager cross-axis alignment is not resolved')
    for name in ('flingBehavior', 'pageNestedScrollConnection', 'snapPosition', 'overscrollEffect'):
        if expression(name) is not None:
            issue(name, 'custom pager scrolling behavior is not translated')
    if expression('pageSize') not in (None, 'PageSize.Fill'):
        issue('pageSize', 'only PageSize.Fill is mapped; fixed/custom page measurement needs a dedicated mapping')
    if value('reverseLayout', False) is not False:
        issue('reverseLayout', 'reverse pager direction is not mapped')
    facts = {'axis': 'horizontal' if horizontal else 'vertical', 'page_count': count,
        'initial_page': initial, 'page_spacing_dp': spacing,
        'content_padding_dp': padding['edges'] if padding else None,
        'user_scroll_enabled': enabled, 'alignment': allowed.get(alignment), 'pages': []}
    node.setdefault('source', {})['pager'] = facts
    node['style']['layout']['alignment'] = None
    return facts
