import unittest

from analyze_compose_project import extract_semantic_ui_calls, compact_parameters
from real_page_pipeline import static_style_for_call
import real_page_pipeline
from test_generate_lanhu_source_page import source_component
from test_layout_mapping_contract import render_nodes
import generate_lanhu_source_page as source_page


def parse_style(body, bindings=None, theme=None):
    call = extract_semantic_ui_calls('Page.kt', body, 'Page', body, 0, set(), {}, {})[0]
    return static_style_for_call(call, {}, None, bindings, theme_colors=theme)[0]


class StaticUiPreservationTest(unittest.TestCase):
    def test_business_card_preserves_native_children_and_source_surface(self):
        style = parse_style('''Card(colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primary),
            shape = RoundedCornerShape(4.dp)) { Text("Card") }''',
            theme={'primary': '#FF100D40', 'onPrimary': '#FFFFFFFF'})
        self.assertEqual(style['surface']['background'], dict(type='solid', color='#FF100D40'))
        self.assertEqual(set(style['surface']['corner_radius_dp'].values()), {4})
        self.assertTrue(style['surface']['clip'])
        root = source_component('root', 'Row', parent_id=None, sibling_index=0, children_ids=['business'])
        business = source_component('business', 'SmallBusinessCard', parent_id='root', sibling_index=0,
                                    children_ids=['card'])
        business['source']['custom_component'] = True
        card = source_component('card', 'Card', parent_id='business', sibling_index=0, children_ids=['first', 'second'])
        card['style'] = style
        first = source_component('first', 'Text', parent_id='card', sibling_index=0, text='First', height_dp=10)
        second = source_component('second', 'Text', parent_id='card', sibling_index=1, text='Second', height_dp=20)
        output, gate, renderer = render_nodes([root, business, card, first, second])
        self.assertIn(".id('card')", output)
        self.assertIn(".backgroundColor('#FF100D40')", output)
        self.assertIn('.borderRadius(4)', output)
        self.assertRegex(output, r"Column\(\) \{\s+Text\('First'\)")
        self.assertLess(output.index("Text('First')"), output.index("Text('Second')"))
        self.assertNotIn(".id('business')", output)
        self.assertNotIn('unsupported component Card', str(renderer.unresolved))
        self.assertFalse([failure for failure in gate['failures'] if failure['component_id'] == 'card'])
        self.assertTrue({'business', 'card', 'first', 'second'} <= renderer.android_page_processed_component_ids)

    def test_card_unknown_elevation_retains_children_and_reports_only_effect(self):
        body = '''Card(elevation = CardDefaults.cardElevation(
            defaultElevation = 9.dp)) { Text("Still present") }'''
        call = extract_semantic_ui_calls('Page.kt', body, 'Page', body, 0, set(), {}, {})[0]
        style, _, unresolved = static_style_for_call(call, {}, None)
        self.assertTrue(any('elevation' in x['path'] for x in unresolved))
        card = source_component('card', 'Card', parent_id=None, sibling_index=0, children_ids=['text'])
        card['style'], card['unresolved'] = style, unresolved
        text = source_component('text', 'Text', parent_id='card', sibling_index=0, text='Still present')
        output, _, _ = render_nodes([card, text])
        self.assertIn("Text('Still present')", output)

    def test_source_light_theme_keeps_framework_defaults_and_explicit_overrides(self):
        inventory = {'color_schemes': [{'variant': 'light', 'constructor': 'lightColorScheme', 'roles': {
            'primary': {'expression': 'Color(0xFF100D40)'},
            'onSurface': {'expression': 'Color(0xFF112233)'},
        }}]}
        colors = real_page_pipeline.selected_theme_colors(inventory)
        self.assertEqual(colors['onPrimary'], '#FFFFFFFF')
        self.assertEqual(colors['onSurface'], '#FF112233')
        self.assertEqual(colors['error'], '#FFB3261E')
        style = parse_style('''Button(colors = ButtonDefaults.buttonColors(
            containerColor = MaterialTheme.colorScheme.primary,
            contentColor = MaterialTheme.colorScheme.onPrimary)) {}''', theme=colors)
        self.assertEqual(style['typography']['color'], '#FFFFFFFF')
        self.assertEqual(style['surface']['background']['color'], '#FF100D40')
        inventory['color_schemes'][0]['roles']['onPrimary'] = {'expression': 'state.customColor'}
        self.assertNotIn('onPrimary', real_page_pipeline.selected_theme_colors(inventory))

    def test_outlined_decoration_preserves_transparent_fill_and_real_border(self):
        body = '''OutlinedTextFieldDefaults.DecorationBox(enabled = true, isError = false,
            colors = TextFieldDefaults.colors(unfocusedContainerColor = Color.Transparent,
                unfocusedIndicatorColor = Color(0xFFCFCFD3)),
            container = { OutlinedTextFieldDefaults.ContainerBox(true, false, interactionSource,
                colors, RoundedCornerShape(4.dp)) })'''
        style = parse_style(body)
        self.assertEqual(style['surface']['background']['color'], '#00000000')
        self.assertEqual(style['surface']['border'],
                         dict(width_dp=1, color='#FFCFCFD3', style='solid'))
        field = source_component('field', 'BasicTextField', parent_id=None, sibling_index=0,
                                 text='123', children_ids=['decoration'])
        decoration = source_component('decoration', 'DecorationBox', parent_id='field', sibling_index=0)
        decoration['style'] = style
        output, _, _ = render_nodes([field, decoration])
        self.assertIn("color: '#FFCFCFD3'", output)
        self.assertIn('.border(', output)

    def test_outlined_decoration_selected_error_and_disabled_border(self):
        for enabled, error, expected in [('true', 'true', '#FF112233'), ('false', 'true', '#FF445566')]:
            style = parse_style(f'''OutlinedTextFieldDefaults.DecorationBox(enabled = {enabled},
                isError = {error}, colors = TextFieldDefaults.colors(
                    unfocusedIndicatorColor = Color.Black, errorIndicatorColor = Color(0xFF112233),
                    disabledIndicatorColor = Color(0xFF445566)),
                container = {{ OutlinedTextFieldDefaults.ContainerBox({enabled}, {error}, interactionSource,
                    colors, RoundedCornerShape(4.dp)) }})''')
            self.assertEqual(style['surface']['border']['color'], expected)

    def test_button_content_color_is_resolved_into_descendant_text_before_render(self):
        button = source_component('button', 'Button', parent_id=None, sibling_index=0, children_ids=['row'])
        button['style']['typography']['color'] = '#FFFFFFFF'
        row = source_component('row', 'Row', parent_id='button', sibling_index=0,
                               children_ids=['label', 'override', 'unknown'])
        label = source_component('label', 'Text', parent_id='row', sibling_index=0, text='Save Card')
        override = source_component('override', 'Text', parent_id='row', sibling_index=1, text='Override')
        override['style']['typography']['color'] = '#FF123456'
        unknown = source_component('unknown', 'Text', parent_id='row', sibling_index=2, text='Unknown')
        unknown['unresolved'] = [{'path': 'style.typography.color', 'expression': 'state.color',
                                  'reason': 'unresolved explicit color'}]
        payload = {'components': [button, row, label, override, unknown]}
        source_page.resolve_native_content_colors(payload)
        self.assertEqual(label['style']['typography']['color'], '#FFFFFFFF')
        self.assertEqual(override['style']['typography']['color'], '#FF123456')
        self.assertIsNone(unknown['style']['typography']['color'])
        output, _, _ = render_nodes(payload['components'])
        self.assertIn(".fontColor('#FFFFFFFF')", output)
        self.assertTrue(any(p['origin'] == 'source_resolved' for p in label['provenance']))

    def test_error_color_condition_is_selected_before_comparison_parsing(self):
        self.assertEqual(source_page.evaluate_expression(
            'if (error != null) { "#FF112233" } else { "#FFCFCFD3" }', {'error': None}), '#FFCFCFD3')
        self.assertEqual(source_page.evaluate_expression(
            'if (error != null) { "#FF112233" } else { "#FFCFCFD3" }', {'error': 'Invalid'}), '#FF112233')

    def test_modifier_argument_reaches_native_body_without_wrapper_layout(self):
        style = parse_style('Row(modifier = modifier) { Text("Child") }',
                            {'modifier': 'Modifier.padding(horizontal = 24.dp).fillMaxWidth()'})
        self.assertEqual(style['layout']['padding_dp'], dict(left=24, right=24, top=0, bottom=0))
        style = parse_style('Box(modifier = modifier.then(Modifier.fillMaxWidth())) {}',
                            {'modifier': 'Modifier.padding(top = 16.dp)'})
        self.assertEqual(style['layout']['padding_dp']['top'], 16)
        untouched = parse_style('Box(Modifier.fillMaxWidth()) {}', {'modifier': 'Modifier.padding(24.dp)'})
        self.assertIsNone(untouched['layout']['padding_dp'])

    def test_long_static_default_is_not_truncated(self):
        value = 'TextFieldDefaults.colors(' + ', '.join(
            f'{state}ContainerColor = Color.Transparent' for state in ('focused', 'unfocused', 'disabled', 'error'))
        value += ', focusedIndicatorColor = Color(0xFF123456), unfocusedIndicatorColor = Color.Black)'
        self.assertGreater(len(value), 240)
        parameters = compact_parameters('colors: TextFieldColors = ' + value)
        self.assertEqual(parameters[0]['default'], value)

    def test_decoration_named_slots_preserve_ownership(self):
        body = 'DecorationBox(label = { Text("Label") }, trailingIcon = { Box { Text("Icon") } })'
        calls = extract_semantic_ui_calls('Page.kt', body, 'Page', body, 0, set(), {}, {})
        self.assertEqual(next(c for c in calls if c['component'] == 'Box')['slot_argument_name'], 'trailingIcon')
        self.assertEqual(next(c for c in calls if c['component'] == 'Text')['slot_argument_name'], 'label')

    def test_button_static_colors_and_shape_are_source_facts(self):
        style = parse_style('''Button(onClick = {},
            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF123456),
                contentColor = Color.White), shape = RoundedCornerShape(30.dp),
            contentPadding = PaddingValues(16.dp)) { Text("OK") }''')
        self.assertEqual(style['surface']['background'], {'type': 'solid', 'color': '#FF123456'})
        self.assertEqual(set(style['surface']['corner_radius_dp'].values()), {30})
        self.assertEqual(style['typography']['color'], '#FFFFFFFF')
        self.assertEqual(style['layout']['padding_dp']['top'], 16)

    def test_button_explicit_disabled_colors_use_static_state(self):
        style = parse_style('''Button(onClick = {}, enabled = false,
            colors = ButtonDefaults.buttonColors(containerColor = Color.White,
                disabledContainerColor = Color(0xFF123456), disabledContentColor = Color.Black)) {}''')
        self.assertEqual(style['surface']['background']['color'], '#FF123456')
        self.assertEqual(style['typography']['color'], '#FF000000')

    def test_unknown_text_keeps_control_and_does_not_copy_parent_text(self):
        root = source_component('root', 'Column', parent_id=None, sibling_index=0, children_ids=['text', 'input'])
        root['style']['content']['text'] = 'Must not leak into child'
        text = source_component('text', 'Text', parent_id='root', sibling_index=0, text=None, font_size_sp=20)
        field = source_component('input', 'BasicTextField', parent_id='root', sibling_index=1, text=None)
        for node in (text, field):
            node['unresolved'] = [{'path': 'style.content.text', 'expression': 'formatBusinessValue(state)',
                                   'reason': 'business expression is outside static UI scope'}]
        output, _, renderer = render_nodes([root, text, field])
        self.assertIn("Text('')", output)
        self.assertIn("TextInput({ text: '' })", output)
        self.assertIn(".id('text')", output)
        self.assertIn(".id('input')", output)
        self.assertNotIn("Text('Must not leak", output)
        self.assertTrue(any(item.get('path') == 'style.content.text' for item in renderer.unresolved))

    def test_custom_function_with_two_roots_keeps_siblings_without_new_layout(self):
        root = source_component('root', 'Column', parent_id=None, sibling_index=0, children_ids=['function'])
        function = source_component('function', 'ProjectContent', parent_id='root', sibling_index=0,
                                    children_ids=['first', 'second'])
        function['source']['custom_component'] = True
        first = source_component('first', 'Text', parent_id='function', sibling_index=0, text='First')
        second = source_component('second', 'Text', parent_id='function', sibling_index=1, text='Second')
        output, _, _ = render_nodes([root, function, first, second])
        self.assertIn("Text('First')", output)
        self.assertIn("Text('Second')", output)
        self.assertNotIn(".id('function')", output)
        self.assertLess(output.index("Text('First')"), output.index("Text('Second')"))

    def test_input_decoration_padding_and_trailing_icon_are_rendered(self):
        field = source_component('field', 'BasicTextField', parent_id=None, sibling_index=0,
                                 text='123', children_ids=['decoration'])
        field['style']['input'] = {'single_line': True}
        decoration = source_component('decoration', 'DecorationBox', parent_id='field', sibling_index=0,
                                      children_ids=['icon'])
        decoration['style']['layout']['padding_dp'] = dict(left=16, right=16, top=14, bottom=14)
        icon = source_component('icon', 'Text', parent_id='decoration', sibling_index=0, text='Icon')
        icon['slot_argument_name'] = 'trailingIcon'
        output, _, _ = render_nodes([field, decoration, icon])
        self.assertIn("TextInput({ text: '123' })", output)
        self.assertIn("Text('Icon')", output)
        self.assertIn('top: this.layoutPx(14)', output)
        self.assertIn(".id('decoration')", output)
        self.assertIn('.padding(0)', output)


if __name__ == '__main__':
    unittest.main()
