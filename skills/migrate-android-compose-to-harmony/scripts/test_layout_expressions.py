import unittest

from generate_lanhu_source_page import project_source_page
import test_dp_size
from test_layout_mapping_contract import render_nodes


class LayoutExpressionTest(unittest.TestCase):
    def project(self, body, declarations='', values=None):
        source = test_dp_size.DpSizeTest().source_page(body, declarations)
        fixture = {'schema': 'android-to-harmony.page-state-fixture.v1',
                   'page': source['page'], 'values': values or {}}
        return project_source_page(source, fixture)[0]

    def test_circle_clip_with_fixed_size_reaches_normalized_json_and_renderer(self):
        for modifiers in ('size(150.dp).clip(CircleShape)', 'clip(CircleShape).size(150.dp)'):
            with self.subTest(modifiers=modifiers):
                page = self.project(f'Box(Modifier.{modifiers}.background(Color(0xFFBCC3FF))) {{}}')
                box = next(n for n in page['components'] if n['type']=='Box')
                expected = dict.fromkeys(['top_left','top_right','bottom_left','bottom_right'],75)
                self.assertEqual(box['style']['surface']['corner_radius_dp'], expected)
                output, _, _ = render_nodes(page['components'])
                self.assertIn('.borderRadius({ topLeft: this.pageCorners', output)
                self.assertIn('Minimum * 0.5', output)
                self.assertIn('.clip(true)', output)

    def test_circle_clip_in_unselected_branch_does_not_leak(self):
        body = 'Box(Modifier.size(150.dp).then(if (rounded) Modifier.clip(CircleShape) else Modifier)) {}'
        for rounded in (True,False):
            page = self.project(body,values={'rounded':rounded})
            box = next(n for n in page['components'] if n['type']=='Box')
            self.assertEqual(bool(box['style']['surface']['clip']),rounded)
            self.assertEqual(box['style']['surface']['corner_radius_dp'] is not None,rounded)

    def test_resource_failure_does_not_override_selected_source_branch(self):
        body = 'Column { if (showAvatar) { AsyncImage(model = avatar, contentDescription = null, modifier = Modifier.size(150.dp)) }; Text("Contact") }'
        for shown in (True,False):
            page = self.project(body,values={'showAvatar':shown})
            self.assertEqual(sum(n['type']=='AsyncImage' for n in page['components']),int(shown))
            for node in page['components']:
                node.pop('visibility_condition', None)
            output, _, _ = render_nodes(page['components'])
            self.assertEqual('.height(this.layoutPx(150))' in output,shown)
            self.assertIn("Text('Contact')",output)

    def test_conditional_padding_and_forwarded_fill_share_selected_modifier_chain(self):
        declarations = '''
@Composable
fun Header(modifier: Modifier = Modifier, actionLabel: String? = null) {
    Row(Modifier.background(Color.Transparent)
        .then(if (actionLabel == null) Modifier.padding(vertical = 12.dp) else Modifier)
        .then(modifier), horizontalArrangement = Arrangement.SpaceBetween) {
        Box(Modifier.size(20.dp)) {}
    }
}
'''
        for label, expected in [('"Edit"', None), ('null', {'left': 0, 'right': 0, 'top': 12, 'bottom': 12})]:
            with self.subTest(label=label):
                page = self.project(f'Header(Modifier.fillMaxWidth(), {label})', declarations)
                row = next(n for n in page['components'] if n['type'] == 'Row')
                self.assertEqual(row['style']['layout']['padding_dp'], expected)
                self.assertTrue(any(r.get('mode') == 'fill_parent' and r.get('axes') == ['width']
                                    for r in row['layout_rules']))
                self.assertFalse(any(m['name'] == 'then' for m in row['modifiers']))

    def test_aliases_nested_conditions_and_reused_instances_remain_independent(self):
        page = self.project('''Column {
    Header("Edit", Modifier.fillMaxWidth())
    Header(null, Modifier.fillMaxWidth(0.5f))
}''', '''
@Composable
fun Header(label: String?, incoming: Modifier) {
    val alias = incoming
    Row(Modifier.then(if (label != null && enabled) alias else {
        if (!enabled) Modifier.height(30.dp) else alias.padding(vertical = 12.dp)
    })) {}
}
''', {'enabled': True})
        rows = [n for n in page['components'] if n['type'] == 'Row']
        self.assertEqual([n['layout_rules'][0]['fraction'] for n in rows], [1, 0.5])
        self.assertEqual([n['style']['layout']['padding_dp'] for n in rows],
                         [None, {'left': 0, 'right': 0, 'top': 12, 'bottom': 12}])

    def test_unknown_condition_never_applies_either_branch(self):
        page = self.project('Box(Modifier.then(if (unknown) Modifier.padding(12.dp) else Modifier.width(50.dp))) {}')
        box = next(n for n in page['components'] if n['type'] == 'Box')
        self.assertIsNone(box['style']['layout']['padding_dp'])
        self.assertIsNone(box['style']['layout']['width_dp'])
        self.assertTrue(box['modifier_projection']['failures'])
        output, gate, _ = render_nodes(page['components'])
        self.assertEqual(gate['verdict'], 'fail')
        self.assertIn(f".id('{box['semantic_key']}')", output)

    def test_when_and_conditional_argument_choose_only_current_layout(self):
        for mode, expected in [(0, 8), (1, 16), (5, 24)]:
            page = self.project('''Box(Modifier.then(when (mode) {
                0 -> Modifier.padding(8.dp)
                1, 2 -> Modifier.padding(16.dp)
                else -> Modifier.padding(24.dp)
            }).height(if (expanded) 100.dp else 40.dp)) {}''', values={'mode': mode, 'expanded': False})
            box = next(n for n in page['components'] if n['type'] == 'Box')
            self.assertEqual(box['style']['layout']['padding_dp'], dict.fromkeys(['left', 'right', 'top', 'bottom'], expected))
            self.assertEqual(box['style']['layout']['height_dp'], 40)

    def test_cyclic_modifier_alias_is_diagnostic_not_recursive_or_guessed(self):
        page = self.project('val first = second\nval second = first\nBox(Modifier.then(first)) {}')
        box = next(n for n in page['components'] if n['type'] == 'Box')
        self.assertTrue(box['modifier_projection']['failures'])
        self.assertEqual(box['modifiers'][0]['name'], 'unresolvedExpression')

    def test_real_psi_distinguishes_strings_from_calls_and_preserves_precedence(self):
        from kotlin_psi import parse_expression
        tree = parse_expression('if (a || b && !c) Modifier.padding(12.dp) else Modifier')
        self.assertEqual(tree['kind'], 'if')
        self.assertEqual(tree['condition']['operator'], '||')
        self.assertEqual(tree['condition']['right']['operator'], '&&')
        literal = parse_expression('"Modifier.padding(99.dp)"')
        self.assertEqual(literal['kind'], 'literal')

    def test_named_business_slot_keeps_native_text_inside_custom_drawing_owner(self):
        page = self.project('Ring(innerComponent = { Text("Progress", fontSize = 18.sp, color = Color.Black) })', '''
@Composable
fun Ring(innerComponent: @Composable () -> Unit) {
    Column(Modifier.size(300.dp).drawBehind { drawCircle(Color.Red) }) {
        innerComponent()
    }
}
''')
        self.assertTrue(any(n['style']['content']['text'] == 'Progress' for n in page['components']))
        output, _, renderer = render_nodes(page['components'])
        self.assertIn("'Progress'", output)
        self.assertIn('Text(props.', output)
        self.assertIn('this.renderBusinessSlot(slot0)', output)
        self.assertTrue(any('draw' in str(u).lower() for u in renderer.unresolved))

    def test_multiline_drawing_does_not_discard_preceding_size_or_slot(self):
        page = self.project('''Column(Modifier.then(Modifier.size(240.dp).drawBehind {
            val radius = size.width / 2
            drawCircle(Color.Red, radius)
        })) { Text("Progress") }''')
        column = next(n for n in page['components'] if n['type'] == 'Column')
        self.assertFalse(column['modifier_projection']['failures'])
        self.assertEqual(column['style']['layout']['width_dp'], 240)
        self.assertEqual(column['style']['layout']['height_dp'], 240)
        self.assertEqual([m['name'] for m in column['modifiers']], ['size', 'drawBehind'])
        output, _, renderer = render_nodes(page['components'])
        self.assertIn("Text('Progress')", output)
        self.assertTrue(any('draw' in str(u).lower() for u in renderer.unresolved))

    def test_layout_arguments_use_the_same_fixed_state_and_parameter_scope(self):
        for expanded, arrangement, alignment in [(True, 'SpaceBetween', 'Bottom'), (False, 'Start', 'Top')]:
            page = self.project('Header(wide = expanded)', '''
@Composable
fun Header(wide: Boolean) {
    val main = if (wide) Arrangement.SpaceBetween else Arrangement.Start
    Row(Modifier.fillMaxWidth(), horizontalArrangement = main,
        verticalAlignment = if (wide) Alignment.Bottom else Alignment.Top) { Text("A") }
}
''', {'expanded': expanded})
            row = next(n for n in page['components'] if n['type'] == 'Row')
            self.assertEqual(row['style']['layout']['horizontal_arrangement'], 'Arrangement.' + arrangement)
            self.assertEqual(row['style']['layout']['alignment'], alignment)
            output, _, _ = render_nodes(page['components'])
            self.assertIn('.alignItems(VerticalAlign.' + alignment + ')', output)
            self.assertIn('.justifyContent(FlexAlign.' + arrangement + ')', output)

    def test_calculated_scalar_arguments_are_evaluated_before_style_extraction(self):
        page = self.project('Box(Modifier.padding((base + 4).dp).alpha(0.25f * 2)) {}', values={'base': 8})
        box = next(n for n in page['components'] if n['type'] == 'Box')
        self.assertEqual(box['style']['layout']['padding_dp'], dict.fromkeys(['left', 'right', 'top', 'bottom'], 12))
        self.assertEqual(box['style']['surface']['alpha'], 0.5)

    def test_static_modifier_condition_is_projected_without_a_state_file(self):
        source = test_dp_size.DpSizeTest().source_page('Box(Modifier.padding(if (true) 12.dp else 24.dp)) {}')
        output, _, _ = render_nodes(source['components'])
        self.assertIn('.padding(this.layoutPx(12))', output)
        self.assertNotIn('this.layoutPx(24)', output)

    def test_modifier_alias_preserves_multiline_kotlin_syntax(self):
        page = self.project('''val artwork = Modifier.size(240.dp).drawBehind {
            val radius = size.width / 2
            drawCircle(Color.Red, radius)
        }
        Box(Modifier.then(artwork)) {}''')
        box = next(n for n in page['components'] if n['type'] == 'Box')
        self.assertFalse(box['modifier_projection']['failures'])
        self.assertEqual(box['style']['layout']['width_dp'], 240)

    def test_dimension_arithmetic_keeps_dp_units(self):
        page = self.project('''val height = 24.dp
            Box(Modifier.size(width = height * 1.5f, height = height + 4.dp)) {}''')
        box = next(n for n in page['components'] if n['type'] == 'Box')
        self.assertEqual(box['style']['layout']['width_dp'], 36)
        self.assertEqual(box['style']['layout']['height_dp'], 28)

    def test_intrinsic_height_is_a_layout_rule_not_an_unknown_scalar(self):
        page = self.project('Row(Modifier.height(IntrinsicSize.Max)) { Text("A") }')
        row = next(n for n in page['components'] if n['type'] == 'Row')
        self.assertTrue(any(r['kind'] == 'intrinsic_size' for r in row['layout_rules']))
        self.assertFalse(any(u['path'] == 'style.layout.height_dp' for u in row['unresolved']))


if __name__ == '__main__':
    unittest.main()
