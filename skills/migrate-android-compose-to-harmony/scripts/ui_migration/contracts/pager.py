"""Typed page groups and bounded native pager options in the single JSON."""
import math


def validate_pager(pager, children):
    count, index = pager.get('page_count'), pager.get('initial_page')
    if type(count) is not int or not 0 <= count <= 200 or type(index) is not int or not 0 <= index < max(count, 1):
        raise ValueError('invalid pager count/initial page')
    if pager.get('axis') not in {'horizontal', 'vertical'}:
        raise ValueError('invalid pager axis')
    if pager.get('alignment') not in {None, 'TopStart', 'Start', 'BottomStart', 'Top', 'TopEnd'}:
        raise ValueError('invalid pager alignment')
    if pager.get('user_scroll_enabled') is not None and type(pager['user_scroll_enabled']) is not bool:
        raise ValueError('invalid pager user_scroll_enabled')
    def length(value):
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    spacing = pager.get('page_spacing_dp')
    if spacing is not None and not length(spacing):
        raise ValueError('invalid pager spacing')
    padding = pager.get('content_padding_dp')
    if padding is not None and (not isinstance(padding, dict) or set(padding) != {'start', 'end', 'top', 'bottom'}
                                or not all(length(v) for v in padding.values())):
        raise ValueError('invalid pager padding')
    pages = pager.get('pages')
    if not isinstance(pages, list) or len(pages) != count or not all(
        isinstance(page, list) and all(isinstance(i, str) for i in page) for page in pages):
        raise ValueError('invalid pager page groups')
    flattened = [i for page in pages for i in page]
    if flattened != children or len(set(flattened)) != len(flattened):
        raise ValueError('pager page groups do not match child inventory')
