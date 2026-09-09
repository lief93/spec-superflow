import unittest

from analyze_compose_project import extract_semantic_ui_calls
from real_page_pipeline import static_style_for_call, bind_source_expression
from test_generate_lanhu_source_page import source_component
from test_layout_mapping_contract import render_nodes
from generate_lanhu_source_page import project_source_page


class NativePageCompositionTest(unittest.TestCase):
    def test_local_modifier_variable_keeps_size_and_width_constraints(self):
        from test_ui_state_semantics import UiStateSemanticsTest
        page = UiStateSemanticsTest().source('''val picture = Modifier.heightIn(min = 180.dp).fillMaxWidth()
            Image(painter = painterResource(R.drawable.icon), contentDescription = null, modifier = picture)''')
        image = next(n for n in page['components'] if n['type'] == 'Image')
        self.assertEqual([m['name'] for m in image['modifiers']], ['heightIn', 'fillMaxWidth'])

    def test_comments_between_arguments_do_not_hide_modifier_or_text(self):
        body = '''Image(painter = painterResource(R.drawable.photo),
            contentDescription = null, // decorative
            modifier = Modifier.size(40.dp) // fixed image
                .padding(4.dp),
        )'''
        calls = extract_semantic_ui_calls('Page.kt', body, 'Page', body, 0, set(), {}, {})
        image = next(c for c in calls if c['component'] == 'Image')
        self.assertEqual([m['name'] for m in image['ordered_modifier_chain']], ['size', 'padding'])
        self.assertEqual(image['positional_arguments'], [])
        from analyze_compose_project import normalize_expression, split_named_argument
        self.assertEqual(split_named_argument('/* note */ text = "https://test/a"'), ('text', '"https://test/a"'))
        normalized = normalize_expression('Modifier.size(40.dp) // note\n .padding(4.dp)')
        self.assertNotIn('// note', normalized)
        self.assertIn('\n', normalized)
        from kotlin_psi import parse_expression
        from ui_migration.semantics.syntax import call_from
        self.assertEqual(call_from(parse_expression(normalized)).name, 'padding')
        self.assertEqual(normalize_expression('"https://test/a"'), '"https://test/a"')

    def test_parameter_member_access_survives_forwarding(self):
        self.assertEqual(bind_source_expression('card.value', {'card': 'state.card'}), 'state.card.value')
        self.assertEqual(bind_source_expression('value', {'value': 'card.value', 'card': 'state.card'}), 'state.card.value')

    def test_trailing_comma_is_not_an_empty_positional_argument(self):
        body = 'CardNumberField(title = "Card Number", value = state.value,)'
        calls = extract_semantic_ui_calls('Page.kt', body, 'Page', body, 0, set(),
            {'CardNumberField': [{'source': 'Field.kt', 'composable': 'CardNumberField'}]},
            {'CardNumberField': [{'name': 'title', 'type': 'String'}, {'name': 'value', 'type': 'String'}]})
        arguments = calls[0]['custom_composable']['arguments']
        self.assertEqual([a['name'] for a in arguments], ['title', 'value'])

    def test_native_named_and_trailing_slots_are_not_flattened(self):
        body = '''Scaffold(topBar = { CenterAlignedTopAppBar(
            title = { Text("Title") }, navigationIcon = { IconButton(onClick = {}) { Text("Back") } }
        ) }) { padding -> Column { Text("Body") } }'''
        calls = extract_semantic_ui_calls('Page.kt', body, 'Page', body, 0, set(), {}, {})
        by_type = {c['component']: c for c in calls if c['component'] != 'Text'}
        self.assertEqual(by_type['CenterAlignedTopAppBar'].get('slot_argument_name'), 'topBar')
        self.assertEqual(by_type['Column'].get('slot_argument_name'), 'content')
        self.assertEqual(by_type['IconButton'].get('slot_argument_name'), 'navigationIcon')
        self.assertEqual(next(c for c in calls if any(p.get('expression') == '"Title"'
                         for p in c.get('positional_arguments', []))).get('slot_argument_name'), 'title')

    def test_text_style_binds_color_and_direct_color_wins(self):
        call = dict(source='Page.kt', line=1, component='Text', positional_arguments=[],
                    ordered_modifier_chain=[], semantic_arguments={
                        'style': {'expression': 'TextStyle(fontSize = 16.sp, color = contentColor)'}})
        style, _, _ = static_style_for_call(call, {}, None, {'contentColor': 'Color.White'})
        self.assertEqual(style['typography']['color'], '#FFFFFFFF')
        call['semantic_arguments']['color'] = {'expression': 'Color.Black'}
        style, _, _ = static_style_for_call(call, {}, None, {'contentColor': 'Color.White'})
        self.assertEqual(style['typography']['color'], '#FF000000')

    def test_then_padding_is_not_lost(self):
        call = dict(source='Page.kt', line=1, component='Column', semantic_arguments={},
                    ordered_modifier_chain=[{'name': 'then', 'arguments':
                        'Modifier.verticalScroll(rememberScrollState()).padding(vertical = 16.dp, horizontal = 24.dp)'}])
        style, _, _ = static_style_for_call(call, {}, None)
        self.assertEqual(style['layout']['padding_dp'], dict(left=24, right=24, top=16, bottom=16))

    def test_appbar_slot_alignment_survives_single_json(self):
        bar = source_component('bar', 'CenterAlignedTopAppBar', parent_id=None, sibling_index=0,
                               children_ids=['back', 'title'])
        back = source_component('back', 'IconButton', parent_id='bar', sibling_index=0)
        title = source_component('title', 'Text', parent_id='bar', sibling_index=1, text='Title', font_size_sp=16)
        back['slot_argument_name'], title['slot_argument_name'] = 'navigationIcon', 'title'
        output, _, _ = render_nodes([bar, back, title])
        self.assertIn("left: { anchor: '__container__', align: HorizontalAlign.Start }", output)
        self.assertIn("middle: { anchor: '__container__', align: HorizontalAlign.Center }", output)
        self.assertNotIn('.position(', output)

    def test_scaffold_keeps_content_and_bar(self):
        scaffold = source_component('screen', 'Scaffold', parent_id=None, sibling_index=0, children_ids=['bar', 'form'])
        bar = source_component('bar', 'Text', parent_id='screen', sibling_index=0, text='Title', font_size_sp=16)
        form = source_component('form', 'BasicTextField', parent_id='screen', sibling_index=1, text='4111', font_size_sp=16)
        bar['slot_argument_name'], form['slot_argument_name'] = 'topBar', 'content'
        output, _, _ = render_nodes([scaffold, bar, form])
        self.assertIn("Text('Title')", output)
        self.assertIn("TextInput({ text: '4111'", output)
        self.assertNotIn('.position(', output)

    def test_short_scroll_is_start_aligned(self):
        node = source_component('scroll', 'Column', parent_id=None, sibling_index=0, children_ids=['label'])
        node['modifiers'] = [{'name': 'verticalScroll', 'arguments': 'rememberScrollState()'}]
        label = source_component('label', 'Text', parent_id='scroll', sibling_index=0, text='Short', font_size_sp=16)
        output, _, _ = render_nodes([node, label])
        self.assertIn('.align(Alignment.TopStart)', output)

    def test_scaffold_content_padding_consumes_measured_bar_height(self):
        root = source_component('screen', 'Scaffold', parent_id=None, sibling_index=0, children_ids=['bar', 'body'])
        root['source']['trailing_lambda_parameters'] = ['pv']
        bar = source_component('bar', 'Text', parent_id='screen', sibling_index=0, text='Title', font_size_sp=16)
        body = source_component('body', 'Column', parent_id='screen', sibling_index=1)
        bar['slot_argument_name'], body['slot_argument_name'] = 'topBar', 'content'
        body['modifiers'] = [{'name': 'padding', 'arguments':
            'top = pv.calculateTopPadding() + 16.dp, bottom = pv.calculateBottomPadding() + 40.dp, start = 24.dp, end = 24.dp'}]
        output, _, _ = render_nodes([root, bar, body])
        self.assertIn('this.scaffold0Topbar = Number(area.height)', output)
        self.assertIn('top: this.scaffold0Topbar + 16', output)
        self.assertIn('bottom: this.scaffold0Bottombar + 40', output)
        self.assertIn('left: 24', output)

    def test_local_android_resource_requires_manifest_asset(self):
        node = source_component('photo', 'AsyncImage', parent_id=None, sibling_index=0)
        node['style']['asset']['resource'] = 'android.resource://example.app/drawable/car'
        payload = {'page': {'id': 'p', 'state': 's'}, 'components': [node],
                   'source_assets': [{'resource': 'car', 'sha256': 'a' * 64}]}
        fixture = {'schema': 'android-to-harmony.page-state-fixture.v1', 'page': payload['page']}
        projected, _ = project_source_page(payload, fixture)
        asset = projected['components'][0]['style']['asset']
        self.assertEqual(asset['resource'], 'car')
        self.assertEqual(asset['sha256'], 'a' * 64)
        payload['source_assets'] = []
        projected, _ = project_source_page(payload, fixture)
        self.assertTrue(projected['components'][0]['style']['asset']['resource'].startswith('android.resource:'))

    def test_match_parent_overlay_does_not_measure_the_box(self):
        box = source_component('box', 'Box', parent_id=None, sibling_index=0, children_ids=['text', 'overlay'])
        text = source_component('text', 'Text', parent_id='box', sibling_index=0, text='Value', font_size_sp=16)
        overlay = source_component('overlay', 'Box', parent_id='box', sibling_index=1)
        overlay['modifiers'] = [{'name': 'matchParentSize', 'arguments': ''}]
        output, _, _ = render_nodes([box, text, overlay])
        self.assertIn('.overlay(this.pageMatchParent0()', output)
        self.assertIn('this.pageMatchParent0Width = current.width', output)
        self.assertIn('.width(this.pageMatchParent0Width)', output)


if __name__ == '__main__':
    unittest.main()
