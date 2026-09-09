"""Native paging from explicit page groups, never a horizontally scrolling Row."""
from ui_migration.contracts.pager import validate_pager


def pager_lines(renderer, component, bounds, indent):
    prefix = ' ' * indent
    pager = component.get('source', {}).get('pager')
    if not isinstance(pager, dict):
        renderer.add_page_json_unresolved(component, 'source.pager', 'missing pager state and page inventory')
        return [prefix + 'Stack() {}'], set()
    validate_pager(pager, component['children_ids'])
    pages = pager['pages']
    lines = [prefix + 'Swiper() {']
    for roots in pages:
        lines.append(prefix + '  Stack() {')
        for node_id in roots:
            lines.extend(renderer.page_snapshot_component_lines(renderer.android_page_by_id[node_id], bounds, 'Stack', indent + 4))
        axis = 'width' if pager['axis'] == 'horizontal' else 'height'
        cross = 'height' if axis == 'width' else 'width'
        lines.extend([prefix + '  }', prefix + "    ." + axis + "('100%')"])
        if renderer.layout.page_snapshot_has_explicit_axis_size(component, cross) or renderer.layout.page_snapshot_stretched_axis(component, cross):
            lines.append(prefix + "    ." + cross + "('100%')")
        if pager.get('alignment') is not None:
            lines.append(prefix + '    .alignContent(Alignment.' + pager['alignment'] + ')')
    lines.extend([prefix + '}', prefix + '  .index(' + str(pager['initial_page']) + ')',
        prefix + '  .loop(false)', prefix + '  .autoPlay(false)', prefix + '  .indicator(false)',
        prefix + '  .vertical(' + str(pager['axis'] == 'vertical').lower() + ')'])
    enabled = pager.get('user_scroll_enabled')
    if type(enabled) is bool:
        lines.append(prefix + '  .disableSwipe(' + str(not enabled).lower() + ')')
    spacing = pager.get('page_spacing_dp')
    if spacing is not None:
        lines.append(prefix + '  .itemSpace(' + renderer.lengths.length(spacing) + ')')
    padding = pager.get('content_padding_dp')
    if padding is not None:
        start, end, cross_start, cross_end = ('start', 'end', 'top', 'bottom') if pager['axis'] == 'horizontal' else ('top', 'bottom', 'start', 'end')
        lines.extend([prefix + '  .prevMargin(' + renderer.lengths.length(padding[start]) + ', false)',
                      prefix + '  .nextMargin(' + renderer.lengths.length(padding[end]) + ', false)'])
        axes = ('top', 'bottom') if pager['axis'] == 'horizontal' else ('left', 'right')
        lines.append(prefix + '  .padding({ ' + axes[0] + ': ' + renderer.lengths.length(padding[cross_start])
            + ', ' + axes[1] + ': ' + renderer.lengths.length(padding[cross_end]) + ' })')
    return lines, {'source.pager'}
