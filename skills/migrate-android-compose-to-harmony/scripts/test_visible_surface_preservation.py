import unittest

import test_material_home_containers as home
from test_layout_mapping_contract import render_nodes


class VisibleSurfacePreservationTest(unittest.TestCase):
    def project(self, body, declarations=''):
        return home.MaterialHomeContainersTest().project(body, declarations=declarations)

    def test_dimension_references_and_literals_share_unit_policy(self):
        from ui_migration.frontend.values import evaluate_expression
        from ui_migration.semantics.expressions import LayoutDimension
        dimension = LayoutDimension(5, 'dp')
        for expression in ('5.dp', 'thickness'):
            self.assertEqual(evaluate_expression(expression, {'thickness': dimension}), 5)
            self.assertEqual(evaluate_expression(expression, {'thickness': dimension}, preserve_units=True), dimension)

    def test_small_visible_surfaces_are_not_filtered_by_size(self):
        for size in (0.5, 1, 2):
            for kind in ('Box', 'Spacer', 'Image'):
                with self.subTest(size=size, kind=kind):
                    modifier = f'Modifier.size({size}.dp).background(Color.Black)'
                    body = (f'Image(painterResource(R.drawable.missing), null, {modifier})'
                            if kind == 'Image' else f'{kind}({modifier})' + (' {}' if kind == 'Box' else ''))
                    page = self.project('Column { ' + body + ' }')
                    node = next(n for n in page['components'] if n['type'] == kind)
                    output, _, _ = render_nodes(page['components'])
                    self.assertIn(".id('" + node['semantic_key'] + "')", output)
                    self.assertIn(".backgroundColor('#FF000000')", output)
                    self.assertIn(f'.height(this.layoutPx({size:g}))', output)

    def test_color_copy_keeps_background_alpha_through_surface_wrapper(self):
        page = self.project('Box(Modifier.clip(RoundedCornerShape(16.dp)).background(Base.copy(alpha = 0.6f)).padding(16.dp)) { Text("Balance") }',
                            'val Base = Color(0xFFF1F1FA)')
        output, _, _ = render_nodes(page['components'])
        self.assertIn(".backgroundColor('#99F1F1FA')", output)

    def test_modifier_extension_preserves_one_dp_border(self):
        page = self.project('Text("This Week", modifier = Modifier.roundedBorder().padding(8.dp))', '''
@Composable
fun Modifier.roundedBorder(radius: Dp = 16.dp, color: Color? = null): Modifier {
    return this.border(1.dp, color ?: Color.Gray, RoundedCornerShape(radius))
}
''')
        output, _, _ = render_nodes(page['components'])
        self.assertIn('.border({', output)
        self.assertIn("color: '#FF888888'", output)
        self.assertNotIn('roundedBorder', [n['type'] for n in page['components']])

    def test_source_list_factory_and_find_select_actual_icon(self):
        import test_ui_state_semantics as semantics
        source = semantics.UiStateSemanticsTest().source('''
val icon = Choices.items().find { it.slug == selected }?.icon ?: R.drawable.wallet
Image(painterResource(icon), null, Modifier.size(16.dp))
''', '''
data class Choice(val icon: Int, val slug: String) {
    companion object {
        fun unused() = Choice(0, "unused")
    }
}
object Choices {
    fun items() = listOf(make("Cash", R.drawable.cash)) + listOf(make("Wallet", R.drawable.wallet))
    fun make(name: String, icon: Int): Choice { return Choice(icon, name.slug()) }
}
fun String.slug(): String { return this.trim().lowercase().replace(' ', '_') }
''')
        for selected, expected in [('cash', 'cash'), ('wallet', 'wallet'), ('not-found', 'wallet')]:
            page = semantics.UiStateSemanticsTest().strict(source, {
                'selected': selected, 'R.drawable.cash': 'cash', 'R.drawable.wallet': 'wallet'})
            image = next(n for n in page['components'] if n['type'] == 'Image')
            self.assertEqual(image['style']['asset']['resource'], expected)

    def test_source_color_helper_preserves_valid_and_error_branches(self):
        import test_ui_state_semantics as semantics
        helper = semantics.UiStateSemanticsTest()
        source = helper.source('Spacer(Modifier.size(1.dp, 24.dp).background(pickColor(code)))', '''
fun pickColor(code: String?, fallback: Color = Color.Gray): Color {
    return if (code.isNullOrEmpty()) { fallback } else {
        try { Color(android.graphics.Color.parseColor(code)) }
        catch (e: IllegalArgumentException) { fallback }
    }
}
''')
        for code, expected in [('#FD3C4A', '#FFFD3C4A'), ('RED', '#FFFF0000'), ('invalid', '#FF888888'), (None, '#FF888888')]:
            page = helper.strict(source, {'code': code})
            output, _, _ = render_nodes(page['components'])
            self.assertIn(f".backgroundColor('{expected}')", output)

    def test_unknown_color_does_not_select_error_fallback(self):
        import test_ui_state_semantics as semantics
        helper = semantics.UiStateSemanticsTest()
        source = helper.source('Box(Modifier.size(20.dp).background(pickColor(code))) {}', '''
fun pickColor(code: String): Color {
    return try { Color(android.graphics.Color.parseColor(code)) }
    catch (e: IllegalArgumentException) { Color.Gray }
}
''')
        page = helper.strict(source, {})
        output, gate, _ = render_nodes(page['components'])
        self.assertNotIn(".backgroundColor('#FF888888')", output)
        self.assertIn('.height(this.layoutPx(20))', output)
        self.assertEqual(gate['verdict'], 'fail')

    def test_direct_named_and_positional_thin_borders_have_same_output(self):
        for kind in ('Box', 'Row', 'Column', 'Text'):
            borders = []
            for arguments in ('0.5.dp, Color.Black, RoundedCornerShape(8.dp)',
                              'width = 0.5.dp, color = Color.Black, shape = RoundedCornerShape(8.dp)'):
                body = f'{kind}(' + ('"Label", ' if kind == 'Text' else '') + f'Modifier.border({arguments}))'
                page = self.project(body + ('' if kind == 'Text' else ' {}'))
                node = next(n for n in page['components'] if n['type'] == kind)
                borders.append(node['style']['surface']['border'])
                output, _, _ = render_nodes(page['components'])
                self.assertIn('.border({', output)
            self.assertEqual(borders[0], borders[1])
            self.assertEqual(borders[0]['width_dp'], 0.5)

    def test_modifier_overloads_forward_parameters_and_select_condition(self):
        declarations = '''
fun Modifier.stroke(radius: Dp = 8.dp) = this.border(1.dp, Color.Black, RoundedCornerShape(radius))
fun Modifier.stroke(shape: Shape) = this.border(1.dp, Color.White, shape)
fun Modifier.optionalStroke(enabled: Boolean) = if (enabled) this.stroke(12.dp) else this
'''
        for expression, width, color in [('stroke()', 1, '#FF000000'),
                                         ('stroke(CircleShape)', 1, '#FFFFFFFF'),
                                         ('optionalStroke(true)', 1, '#FF000000'),
                                         ('optionalStroke(false)', None, None)]:
            page = self.project(f'Box(Modifier.size(20.dp).{expression}) {{}}', declarations)
            node = next(n for n in page['components'] if n['type'] == 'Box')
            border = node['style']['surface']['border']
            if width is None:
                self.assertIsNone(border)
            else:
                self.assertEqual(border['width_dp'], width)
                self.assertEqual(border['color'], color)
                if expression == 'stroke(CircleShape)':
                    self.assertEqual(node['style']['surface']['corner_sizes']['top_left'], {'unit': 'percent', 'value': 50})


if __name__ == '__main__':
    unittest.main()
