import unittest

from generate_lanhu_source_page import evaluate_expression, UNRESOLVED
from layout_expressions import LayoutDimension, LayoutExpressions
from kotlin_psi import parse_expression
import test_ui_state_semantics as semantics


class FixedStateValueParityTest(unittest.TestCase):
    def test_nullable_dimension_condition_selects_explicit_text_size(self):
        for expression, expected in [('30.sp == null', False), ('30.dp != null', True), ('null == 30.sp', False)]:
            self.assertEqual(evaluate_expression(expression, {}), expected)
        helper = semantics.UiStateSemanticsTest()
        source = helper.source('Caption(size = 30.sp)', '''
@Composable fun Caption(size: TextUnit?) {
Text("Amount", style = if (size == null) TextStyle(fontSize = 16.sp) else TextStyle(fontSize = size))
}
''')
        page = helper.strict(source, {})
        self.assertEqual(next(n for n in page['components'] if n['type']=='Text')['style']['typography']['font_size_sp'], 30)

    def test_ambient_source_binding_uses_provider_not_page_style_override(self):
        helper = semantics.UiStateSemanticsTest()
        source = helper.source('Text("Title", style = UI.typo.title)', '''
object ThemeFactory {
fun typography() = object : Styles {
    override val title = TextStyle(fontSize = 32.sp, color = Color.Black)
}
}
''')
        fixture = {'schema': 'android-to-harmony.page-state-fixture.v1', 'page': source['page'],
                   'source_bindings': {'UI.typo': 'ThemeFactory.typography()'}}
        page = semantics.project_source_page(source, fixture)[0]
        self.assertEqual(page['components'][0]['style']['typography']['font_size_sp'], 32)

    def test_local_font_family_is_preserved_through_style_record(self):
        from ui_migration.frontend.values import value_resolver
        expression = 'FontFamily(Font(R.font.body, FontWeight.Normal))'
        values = {'__source_file': 'Theme.kt', '__source_tokens': [{
            'source': 'Theme.kt', 'kind': 'font_family', 'name': 'bodyFamily', 'expression': expression}]}
        resolver = value_resolver({}, values)
        # A lambda is not executed; a block is evaluated only as a source function body.
        block = parse_expression('{ val font = ' + expression + '; TextStyle(fontFamily = font, fontSize = 20.sp) }')['body']
        self.assertEqual(resolver.value(block)['properties']['fontFamily'], 'bodyFamily')

    def test_object_member_does_not_replace_captured_local_of_same_name(self):
        from ui_migration.frontend.values import value_resolver
        tree = parse_expression('''{ val h1 = 40.sp
return object : Styles {
    override val h1 = TextStyle(fontSize = h1)
    override val number = TextStyle(fontSize = h1)
} }''')['body']
        value = value_resolver({}, {}).value(tree)
        self.assertEqual(value['number']['properties']['fontSize'], '40.sp')

    def test_source_theme_object_keeps_independent_style_members(self):
        helper = semantics.UiStateSemanticsTest()
        source = helper.source('''Column {
val theme = ThemeFactory.typography()
Text("Title", style = theme.title.copy(fontWeight = FontWeight.Bold))
Text("Caption", style = theme.caption)
}''', '''
object ThemeFactory {
fun typography(): Styles {
    val titleSize = 32.sp
    return object : Styles {
        override val title = TextStyle(fontSize = titleSize, color = Color.Black)
        override val caption = TextStyle(fontSize = 12.sp, color = unknownInk)
    }
}
}
''')
        page = helper.strict(source, {})
        title, caption = [n for n in page['components'] if n['type'] == 'Text']
        self.assertEqual(title['style']['typography']['font_size_sp'], 32)
        self.assertEqual(title['style']['typography']['font_weight'], 700)
        self.assertEqual(caption['style']['typography']['font_size_sp'], 12)
        self.assertIsNone(caption['style']['typography']['color'])

    def test_text_style_extension_preserves_base_and_explicit_overrides(self):
        helper = semantics.UiStateSemanticsTest()
        source = helper.source('''Column { val base = TextStyle(fontSize = 20.sp)
Text("Accounts", style = base.emphasized(fontWeight = FontWeight.ExtraBold))
Text("Partial", style = unavailableTheme.emphasized(fontWeight = FontWeight.Bold))
}''', '''
fun TextStyle.emphasized(color: Color = Color.Black, fontWeight: FontWeight = FontWeight.Medium) =
    this.copy(color = color, fontWeight = fontWeight)
''')
        page = helper.strict(source, {})
        first, second = [node for node in page['components'] if node['type'] == 'Text']
        self.assertEqual(first['style']['typography']['font_size_sp'], 20)
        self.assertEqual(first['style']['typography']['font_weight'], 800)
        self.assertEqual(second['style']['typography']['font_weight'], 700)
        self.assertTrue(any('unavailableTheme' in str(item) for item in second['unresolved']))

    def test_value_and_modifier_paths_select_the_same_branch(self):
        expressions = [
            'if (active && entries.isNotEmpty()) 12.dp else 4.dp',
            'when { active && entries.isNotEmpty() -> 12.dp; else -> 4.dp }',
            'when (active) { true -> if (entries.isNotEmpty()) 12.dp else 4.dp; else -> 4.dp }',
        ]
        for active, entries, expected in [(True, [1], 12), (True, [], 4), (False, [1], 4)]:
            values = {'active': active, 'entries': entries}
            for expression in expressions:
                with self.subTest(expression=expression, values=values):
                    self.assertEqual(evaluate_expression(expression, values), expected)
                    result = LayoutExpressions({}, values, evaluate_expression, UNRESOLVED).value(parse_expression(expression))
                    self.assertEqual(result, LayoutDimension(expected, 'dp'))

    def test_operators_inside_text_are_not_treated_as_control_flow(self):
        for literal in ['"a < b"', '"if (x) left else right"', '"a  b"', '"x || y"']:
            with self.subTest(literal=literal):
                self.assertEqual(evaluate_expression(literal, {}), literal[1:-1])

    def test_arithmetic_precedence_and_parentheses_are_shared(self):
        for expression, expected in [('2 + 3 * 4', 14), ('(2 + 3) * 4', 20),
                                     ('(2 + 3).dp', 5), ('18.dp / 2', 9),
                                     ('if (true) 18.dp / 2 else 4.dp', 9)]:
            with self.subTest(expression=expression):
                self.assertEqual(evaluate_expression(expression, {}), expected)

    def test_unselected_unknown_branch_is_not_evaluated(self):
        self.assertEqual(evaluate_expression('when (active) { true -> 12.dp; else -> unavailable() }', {'active': True}), 12)
        self.assertIs(evaluate_expression('when (active) { true -> 12.dp; else -> 4.dp }', {}), UNRESOLVED)
        self.assertIs(evaluate_expression('unavailable()', {}), UNRESOLVED)

    def test_text_style_and_padding_share_multilevel_state_parameters(self):
        helper = semantics.UiStateSemanticsTest()
        source = helper.source('Panel(enabled = selected)', '''
@Composable
fun Panel(enabled: Boolean) { Caption(active = enabled) }
@Composable
fun Caption(active: Boolean) {
    Text("Caption", fontSize = when (active) { true -> 20.sp; else -> 12.sp },
        color = when (active) { true -> Color.White; else -> Color.Gray },
        modifier = Modifier.padding(when (active) { true -> 12.dp; else -> 4.dp }))
}
''')
        for selected, size, padding, color in [(True, 20, 12, '#FFFFFFFF'), (False, 12, 4, '#FF888888')]:
            with self.subTest(selected=selected):
                page = helper.strict(source, {'selected': selected})
                text = next(n for n in page['components'] if n['type'] == 'Text')
                self.assertEqual(text['style']['typography']['font_size_sp'], size)
                self.assertEqual(text['style']['typography']['color'], color)
                self.assertEqual(text['style']['layout']['padding_dp']['top'], padding)

    def test_text_style_copy_resolves_parameters_and_preserves_direct_precedence(self):
        helper = semantics.UiStateSemanticsTest()
        source = helper.source('Caption(active = selected, ink = selectedColor)', '''
@Composable
fun Caption(active: Boolean, ink: Color) {
    val caption = MaterialTheme.typography.labelSmall.copy(
        color = ink, fontSize = if (active) 20.sp else 12.sp)
    Text("Styled", style = caption.copy(fontWeight = FontWeight.Bold))
    Text("Direct", style = caption, color = Color.White, fontSize = 18.sp)
}
''')
        for active, size, ink in [(True, 20, '#FF123456'), (False, 12, '#FF654321')]:
            page = helper.strict(source, {'selected': active, 'selectedColor': ink})
            texts = {n['style']['content']['text']: n for n in page['components'] if n['type'] == 'Text'}
            style = texts['Styled']['style']['typography']
            self.assertEqual(style['color'], ink)
            self.assertEqual(style['font_size_sp'], size)
            self.assertEqual(style['font_weight'], 700)
            self.assertEqual(texts['Direct']['style']['typography']['color'], '#FFFFFFFF')
            self.assertEqual(texts['Direct']['style']['typography']['font_size_sp'], 18)

    def test_unknown_copy_property_does_not_discard_other_style_properties(self):
        helper = semantics.UiStateSemanticsTest()
        source = helper.source('Text("Styled", style = TextStyle(color = ink, fontSize = 22.sp))')
        page = helper.strict(source, {})
        text = next(n for n in page['components'] if n['type'] == 'Text')
        self.assertEqual(text['style']['typography']['font_size_sp'], 22)
        self.assertIsNone(text['style']['typography']['color'])
        self.assertTrue(any(n['path'] == 'style.typography.color' for n in text['unresolved']))


if __name__ == '__main__':
    unittest.main()
