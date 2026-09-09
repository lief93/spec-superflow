import unittest

from generate_lanhu_source_page import evaluate_expression, UNRESOLVED
import test_ui_state_semantics as semantics
from test_layout_mapping_contract import render_nodes


class MaterialHomeContainersTest(unittest.TestCase):
    def test_missing_surface_defaults_are_required_not_silent_null(self):
        from component_required_facts import build_required_facts
        from test_generate_lanhu_source_page import source_component
        for kind in ('Card', 'Surface', 'Scaffold'):
            with self.subTest(kind=kind):
                node = source_component('surface', kind, parent_id=None, sibling_index=0)
                node['style']['surface']['background'] = None
                facts = build_required_facts(node)
                background = next(f for f in facts if f['path'] == 'style.surface.background')
                self.assertEqual(background['status'], 'unresolved')
                node['style']['surface']['background'] = {'type': 'solid', 'color': '#00000000'}
                background = next(f for f in build_required_facts(node) if f['path'] == 'style.surface.background')
                self.assertEqual(background['status'], 'default_resolved')

    def test_missing_image_scale_is_not_falsely_default_resolved(self):
        from component_required_facts import build_required_facts
        from test_generate_lanhu_source_page import source_component
        node = source_component('image', 'Image', parent_id=None, sibling_index=0)
        node['style']['asset']['content_scale'] = None
        scale = next(f for f in build_required_facts(node) if f['path'] == 'style.asset.content_scale')
        self.assertEqual(scale['status'], 'unresolved')

    def test_weight_decisions_record_actual_parent_and_constraint(self):
        for lazy, flow, axis in [('LazyColumn', 'Column', 'height'), ('LazyRow', 'Row', 'width')]:
            for finite in (False, True):
                with self.subTest(lazy=lazy, finite=finite):
                    bound = f'(Modifier.{axis}(200.dp))' if finite else ''
                    page = self.project(f'{lazy} {{ item {{ {flow}{bound} {{ Spacer(Modifier.weight(1f)) }} }} }}')
                    _, gate, _ = render_nodes(page['components'])
                    decision = next(d for d in gate['layout_decisions'] if d['kind'] == 'weight')
                    self.assertEqual(decision['parent_type'], flow)
                    self.assertEqual(decision['axis'], axis)
                    self.assertEqual(decision['outcome'], 'applied' if finite else 'source_no_op')
                    self.assertEqual(decision['constraint'], 'bounded' if finite else 'unbounded')
                    self.assertTrue(decision['constraint_source_id'])
                    check = next(c for c in gate['checks'] if c['component_id'] == decision['component_id'] and c['path'] == 'source.modifiers.weight')
                    self.assertIn(decision, check['decisions'])

    def test_weight_on_invalid_parent_is_not_emitted_or_reported_consumed(self):
        page = self.project('Box { Spacer(Modifier.weight(1f)) }')
        output, gate, renderer = render_nodes(page['components'])
        self.assertNotIn('.layoutWeight(', output)
        decision = next(d for d in gate['layout_decisions'] if d['kind'] == 'weight')
        self.assertEqual(decision['outcome'], 'unresolved')
        self.assertEqual(decision['parent_type'], 'Box')
        self.assertTrue(any(c['path'] == 'source.modifiers.weight' for c in gate['failures']))
        self.assertTrue(renderer.unresolved)

    def test_fill_decisions_keep_each_axis_separate(self):
        page = self.project('LazyColumn { item { Box(Modifier.fillMaxSize()) {} } }')
        _, gate, _ = render_nodes(page['components'])
        decisions = [d for d in gate['layout_decisions'] if d['kind'] == 'sizing' and d['path'] == 'source.modifiers.fillmaxsize']
        self.assertEqual({(d['axis'], d['outcome']) for d in decisions},
                         {('width', 'applied'), ('height', 'source_no_op')})

    def test_failed_layout_decision_cannot_be_overridden_by_path_record(self):
        from ui_migration.contracts.consumption import build_target_phase_consumption_gate
        from test_generate_lanhu_source_page import source_component
        node = source_component('child', 'Box', parent_id=None, sibling_index=0)
        path = 'source.modifiers.fillmaxsize'
        node['required_facts'] = [{'path': path, 'status': 'resolved'}]
        decisions = [dict(component_id='child', path=path, outcome='unresolved',
                          reason='unsupported intrinsic main-axis fill')]
        gate = build_target_phase_consumption_gate({'components': [node]}, {'child'}, set(), {},
            {'child': {path}}, decisions)
        self.assertTrue(any(f['path'] == path for f in gate['failures']))

    def test_transparent_surface_and_missing_surface_reach_target_gate(self):
        from test_generate_lanhu_source_page import source_component
        for background, expected in ((None, 'fail'), ({'type': 'solid', 'color': '#00000000'}, 'pass')):
            node = source_component('surface', 'Surface', parent_id=None, sibling_index=0)
            node['style']['surface']['background'] = background
            output, gate, _ = render_nodes([node])
            failures = [c for c in gate['failures'] if c['path'] == 'style.surface.background']
            self.assertEqual(bool(failures), expected == 'fail')
            self.assertIn(".id('surface')", output)

    def project(self, body, values=None, declarations=''):
        helper = semantics.UiStateSemanticsTest()
        return helper.strict(helper.source(body, declarations), values or {})

    def test_surface_retains_content_fill_and_inherited_content_color(self):
        page = self.project('''Surface(color = Color(0xFF332255), contentColor = Color.White,
            modifier = Modifier.padding(horizontal = 20.dp).fillMaxWidth().clip(RoundedCornerShape(16.dp))) {
            Column(Modifier.fillMaxWidth().padding(16.dp)) { Text("Auto Tracking", fontSize = 22.sp) }
        }''')
        surface = next(n for n in page['components'] if n['type'] == 'Surface')
        self.assertEqual(surface['style']['surface']['background'], {'type': 'solid', 'color': '#FF332255'})
        output, _, renderer = render_nodes(page['components'])
        self.assertIn("Text('Auto Tracking')", output)
        self.assertIn(".backgroundColor('#FF332255')", output)
        self.assertIn(".fontColor('#FFFFFFFF')", output)
        self.assertFalse(any(u.get('kind') == 'unsupported_page_component' for u in renderer.unresolved))

    def test_animated_visibility_fixed_states_keep_or_remove_whole_subtree(self):
        body = '''Column { AnimatedVisibility(visible = entries.isNotEmpty()) {
            Column { Text("Cash"); Text("Available Balance") }
        }; Text("Breakdown") }'''
        for entries, visible in ((['Cash'], True), ([], False)):
            with self.subTest(visible=visible):
                page = self.project(body, {'entries': entries})
                output, _, _ = render_nodes(page['components'])
                self.assertEqual("Text('Cash')" in output, visible)
                self.assertEqual("Text('Available Balance')" in output, visible)
                self.assertIn("Text('Breakdown')", output)

    def test_safe_member_elvis_preserves_known_text_not_sample(self):
        for user, expected in (({'name': 'Alex Morgan'}, 'Alex Morgan'), (None, ''), ({'name': None}, '')):
            self.assertEqual(evaluate_expression('user?.name ?: ""', {'user': user}), expected)
        self.assertIs(evaluate_expression('unknown?.name ?: ""', {}), UNRESOLVED)

    def test_conditional_spacer_let_consumes_only_specified_axis(self):
        declarations = '''
@Composable
fun Space(height: Dp = Dp.Unspecified, width: Dp = Dp.Unspecified) {
    Spacer(Modifier.let { if (height != Dp.Unspecified) it.height(height) else it }
        .let { if (width != Dp.Unspecified) it.width(width) else it })
}
'''
        page = self.project('Column { Space(height = 15.dp); Space(width = 10.dp) }', declarations=declarations)
        spacers = [n for n in page['components'] if n['type'] == 'Spacer']
        self.assertEqual(len(spacers), 2)
        self.assertEqual(spacers[0]['style']['layout']['height_dp'], 15)
        self.assertIsNone(spacers[0]['style']['layout']['width_dp'])
        self.assertEqual(spacers[1]['style']['layout']['width_dp'], 10)
        self.assertIsNone(spacers[1]['style']['layout']['height_dp'])

    def test_row_scope_business_component_is_expanded(self):
        page = self.project('Row { Heading() }', declarations='''
@Composable
fun RowScope.Heading() { Column(Modifier.weight(1f)) { Text("Auto Tracking") } }
''')
        output, _, _ = render_nodes(page['components'])
        self.assertIn("'Auto Tracking'", output)
        self.assertIn('Text(props.', output)
        self.assertIn('.layoutWeight(1)', output)

    def test_positional_image_painter_keeps_local_resource(self):
        page = self.project('Image(rememberAsyncImagePainter(R.drawable.hand), contentDescription = null, modifier = Modifier.size(90.dp))')
        image = next(n for n in page['components'] if n['type'] == 'Image')
        self.assertEqual(image['style']['asset']['resource'], 'hand')

    def test_copy_text_style_consumes_base_and_overrides(self):
        from real_page_pipeline import static_style_for_call
        call = {'component': 'Text', 'source': 'Page.kt', 'line': 1, 'semantic_arguments': {
            'text': {'expression': '"Title"'},
            'style': {'expression': 'MaterialTheme.typography.labelMedium.copy(fontWeight = FontWeight.SemiBold, color = Color.White)'},
        }}
        style, _, _ = static_style_for_call(call, {}, None)
        self.assertEqual(style['typography']['font_size_sp'], 12)
        self.assertEqual(style['typography']['font_weight'], 600)
        self.assertEqual(style['typography']['color'], '#FFFFFFFF')

    def test_unique_source_color_token_is_available_to_surface(self):
        from generate_lanhu_source_page import project_source_page
        helper = semantics.UiStateSemanticsTest()
        page = helper.source('Surface(color = DarkCard, contentColor = LightText) { Text("Title") }')
        page['source_tokens'] = [
            {'name': 'DarkCard', 'kind': 'color', 'argb_hex': '#FF332244'},
            {'name': 'LightText', 'kind': 'color', 'argb_hex': '#FFEEEEEE'},
        ]
        projected = helper.strict(page, {})
        surface = next(n for n in projected['components'] if n['type'] == 'Surface')
        self.assertEqual(surface['style']['surface']['background'], {'type': 'solid', 'color': '#FF332244'})
        self.assertEqual(surface['style']['typography']['color'], '#FFEEEEEE')

    def test_remembered_initial_text_size_retains_unit_value(self):
        page = self.project('Label(size = 20.sp)', declarations='''
@Composable
fun Label(size: TextUnit) {
    val textSize by remember { mutableStateOf(size) }
    Text("Amount", fontSize = textSize)
}
''')
        text = next(n for n in page['components'] if n['type'] == 'Text')
        self.assertEqual(text['style']['typography']['font_size_sp'], 20)

    def test_custom_canvas_retains_declared_layout_but_does_not_claim_draw_support(self):
        page = self.project('Row { Canvas(Modifier.size(100.dp)) {}; Text("Date") }')
        canvas = next(n for n in page['components'] if n['type'] == 'Canvas')
        output, gate, _ = render_nodes(page['components'])
        self.assertIn(".id('" + canvas['semantic_key'] + "')", output)
        self.assertIn('.width(this.layoutPx(100))', output)
        self.assertIn("Text('Date')", output)
        self.assertEqual(gate['verdict'], 'fail')

    def test_lazy_row_does_not_fill_vertical_viewport(self):
        page = self.project('Column { LazyRow { item { Box(Modifier.size(150.dp, 90.dp)) {} } }; Text("Next") }')
        output, _, _ = render_nodes(page['components'])
        row = output.split('Scroll() {', 1)[1].split('.scrollable(', 1)[0]
        self.assertNotIn(".height('100%')", row)

    def test_extended_theme_roles_reach_background_and_text(self):
        page = self.project('Box(Modifier.background(MaterialTheme.extra.card)) { Text("Title", color = MaterialTheme.extra.ink) }', declarations='''
data class ExtraColors(val card: Color, val ink: Color)
val LightExtra = ExtraColors(card = Color(0xFF123456), ink = Color(0xFFEEEEEE))
val LocalExtra = staticCompositionLocalOf { LightExtra }
val MaterialTheme.extra: ExtraColors
    @Composable get() = LocalExtra.current
''')
        box = next(n for n in page['components'] if n['type'] == 'Box')
        text = next(n for n in page['components'] if n['type'] == 'Text')
        self.assertEqual(box['style']['surface']['background'], {'type': 'solid', 'color': '#FF123456'})
        self.assertEqual(text['style']['typography']['color'], '#FFEEEEEE')

    def test_vertical_divider_stretches_intrinsic_row_through_padding_wrappers(self):
        page = self.project('''Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp)
            .height(IntrinsicSize.Min).background(Color.Black).padding(16.dp)) {
            Text("Income")
            VerticalDivider(thickness = 0.5.dp)
            Text("Expense")
        }''')
        output, _, _ = render_nodes(page['components'])
        self.assertIn("Text('Income')", output)
        self.assertIn("Text('Expense')", output)
        divider = output.split('Divider()', 1)[1].split("Text('Expense')", 1)[0]
        self.assertIn('.height(0)', divider)
        self.assertIn('.alignSelf(ItemAlign.Stretch)', divider)

    def test_explicit_divider_height_is_not_reset_for_intrinsic_parent(self):
        page = self.project('''Row(Modifier.height(IntrinsicSize.Min)) {
            Text("Income")
            VerticalDivider(modifier = Modifier.height(24.dp))
            Text("Expense")
        }''')
        output, _, _ = render_nodes(page['components'])
        divider = output.split('Divider()', 1)[1].split("Text('Expense')", 1)[0]
        self.assertNotIn('.height(0)', divider)
        self.assertIn('.height(this.layoutPx(24))', divider)

    def test_intrinsic_divider_reset_is_limited_to_flow_cross_axis(self):
        for container, modifier, divider_type, axis in [
            ('Box', 'height', 'VerticalDivider', 'height'),
            ('Row', 'width', 'HorizontalDivider', 'width'),
            ('Column', 'height', 'VerticalDivider', 'height'),
        ]:
            with self.subTest(container=container, divider=divider_type):
                page = self.project(f'{container}(Modifier.{modifier}(IntrinsicSize.Min)) {{ {divider_type}() }}')
                output, _, _ = render_nodes(page['components'])
                divider = output.split('Divider()', 1)[1]
                self.assertNotIn(f'.{axis}(0)', divider)

    def test_fill_on_unbounded_scroll_axis_is_ignored_but_finite_parent_is_preserved(self):
        for scroll, flow, fill, axis, bound in [
            ('verticalScroll', 'Row', 'fillMaxHeight', 'height', ''),
            ('horizontalScroll', 'Column', 'fillMaxWidth', 'width', ''),
            ('verticalScroll', 'Row', 'fillMaxHeight', 'height', 'Box(Modifier.height(80.dp))'),
            ('horizontalScroll', 'Column', 'fillMaxWidth', 'width', 'Box(Modifier.width(80.dp))'),
            ('verticalScroll', 'Row', 'fillMaxHeight', 'height', 'Box(Modifier.heightIn(max = 80.dp))'),
            ('horizontalScroll', 'Column', 'fillMaxWidth', 'width', 'Box(Modifier.widthIn(max = 80.dp))'),
        ]:
            body = f'{flow} {{ Text("Action", modifier = Modifier.{fill}()) }}'
            if bound:
                body = bound + ' { ' + body + ' }'
            with self.subTest(scroll=scroll, bound=bound):
                page = self.project(f'Column(Modifier.{scroll}(rememberScrollState())) {{ {body} }}')
                output, _, _ = render_nodes(page['components'])
                label = output.split("Text('Action')", 1)[1].split('.id(', 1)[0]
                self.assertEqual(f".{axis}('100%')" in label, bool(bound), label)

    def test_lazy_container_has_implicit_unbounded_item_axis(self):
        for lazy, flow, axis in [('LazyColumn', 'Row', 'height'), ('LazyRow', 'Column', 'width')]:
            with self.subTest(lazy=lazy):
                page = self.project(f'''{lazy}(Modifier.fillMaxSize()) {{ item {{
                    {flow} {{ Text("Action", modifier = Modifier.fillMax{axis.title()}()) }}
                }} }}''')
                output, _, _ = render_nodes(page['components'])
                label = output.split("Text('Action')", 1)[1].split('.id(', 1)[0]
                self.assertNotIn(f".{axis}('100%')", label)

    def test_weight_uses_incoming_scroll_constraint_not_native_viewport(self):
        for lazy, flow, axis in [('LazyColumn', 'Column', 'height'), ('LazyRow', 'Row', 'width')]:
            for finite in (False, True):
                with self.subTest(lazy=lazy, finite=finite):
                    bound = f'(Modifier.{axis}(200.dp))' if finite else ''
                    page = self.project(f'''{lazy} {{ item {{ {flow}{bound} {{
                        Text("Before"); Spacer(Modifier.weight(1f)); Text("After")
                    }} }} }}''')
                    output, _, renderer = render_nodes(page['components'])
                    spacer = output.split('Blank()', 1)[1].split("Text('After')", 1)[0]
                    self.assertEqual('.layoutWeight(1)' in spacer, finite, spacer)
                    if not finite:
                        self.assertIn(f'.{axis}(0)', spacer)
                    self.assertFalse(any('weight' in str(u) for u in renderer.unresolved))

    def test_card_omitted_colors_resolve_material_theme_defaults(self):
        from ui_migration.frontend.theme import selected_theme_colors
        defaults = selected_theme_colors({'color_schemes': [{'variant': 'light', 'constructor': 'lightColorScheme', 'roles': {}}]})
        self.assertEqual(defaults.get('surfaceContainerHighest'), '#FFE6E0E9')
        from real_page_pipeline import static_style_for_call
        for expression in (None, 'CardDefaults.cardColors()', 'CardDefaults.cardColors(containerColor = Color.White)'):
            arguments = {} if expression is None else {'colors': {'expression': expression}}
            call = {'component': 'Card', 'source': 'Page.kt', 'line': 1, 'semantic_arguments': arguments}
            style, _, _ = static_style_for_call(call, {}, None, theme_colors={
                'surfaceContainerHighest': '#FFE6E0E9', 'onSurface': '#FF201A1A'})
            self.assertEqual(style['surface']['background'], {'type': 'solid',
                'color': '#FFFFFFFF' if expression and 'White' in expression else '#FFE6E0E9'})


if __name__ == '__main__':
    unittest.main()
