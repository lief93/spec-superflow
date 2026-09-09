from kotlin_psi import parse_expression
from ui_migration.frontend.page_model import UNRESOLVED
from ui_migration.semantics.expressions import LayoutExpressionError
from ui_migration.semantics.syntax import syntax_shape, call_from
from .registry import ApiAdapter


def text_style(call, context, seen, base=None):
    properties = dict(base or {})
    for item in call.arguments:
        if not item.get('name'):
            return UNRESOLVED
        try:
            expression = context.render(item['value'], seen)
        except LayoutExpressionError:
            expression = item['value']['text']
        properties[item['name']] = expression
    return {'kind': 'text_style', 'properties': properties}


def copy_style(call, context, seen):
    return text_style(call, context, seen, context.receiver['properties'])


def annotated_string(call, context, seen):
    text = call.argument('text', 0)
    value = context.value(text, seen) if text else UNRESOLVED
    spans = call.argument('spanStyles', 1)
    ranges = context.value(spans, seen) if spans else []
    if not isinstance(value, str):
        return UNRESOLVED
    return {'kind': 'annotated_string', 'text': value, 'span_styles': ranges}


def style_range(call, context, seen):
    result = {name: context.value(call.argument(name, index), seen)
              for index, name in enumerate(('item', 'start', 'end'))}
    return result


def merge_style(call, context, seen):
    other = context.value(call.argument('other', 0), seen)
    if isinstance(other, dict) and other.get('kind') == 'text_style':
        return {'kind': 'text_style', 'properties': {**context.receiver['properties'], **other['properties']}}
    return UNRESOLVED


def font_family(call, context, seen):
    # A family declaration preserves identity; its asset availability is a later gate.
    shape = syntax_shape(list(call.arguments))
    candidates = [t for t in context.values.get('__source_tokens', ()) if t.get('kind') == 'font_family'
                  and t.get('source') == context.values.get('__source_file')
                  and (candidate := call_from(parse_expression(t['expression']))) is not None
                  and syntax_shape(list(candidate.arguments)) == shape]
    return {'kind': 'font_family_reference', 'name': candidates[0]['name']} if len(candidates) == 1 else UNRESOLVED


ADAPTERS = (
    ApiAdapter('compose.annotated-string', 'font', ('androidx.compose.ui.text.AnnotatedString',), annotated_string, aliases=('AnnotatedString',)),
    ApiAdapter('compose.annotated-range', 'font', ('androidx.compose.ui.text.AnnotatedString.Range',), style_range, aliases=('AnnotatedString.Range',)),
    ApiAdapter('compose.paragraph-style', 'font', ('androidx.compose.ui.text.ParagraphStyle',), text_style, aliases=('ParagraphStyle',)),
    ApiAdapter('compose.to-span-style', 'font', ('toSpanStyle',), lambda call, context, seen: context.receiver, receiver_kind='text_style'),
    ApiAdapter('compose.merge-text-style', 'font', ('merge',), merge_style, receiver_kind='text_style'),
    ApiAdapter('compose.text-style', 'font', ('androidx.compose.ui.text.TextStyle',), text_style, aliases=('TextStyle',)),
    ApiAdapter('compose.font-family', 'font', ('androidx.compose.ui.text.font.FontFamily',), font_family, aliases=('FontFamily',)),
    ApiAdapter('compose.copy-text-style', 'font', ('copy',), copy_style, receiver_kind='text_style'),
)
