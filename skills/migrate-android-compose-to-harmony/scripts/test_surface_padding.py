import unittest

from analyze_compose_project import extract_semantic_ui_calls
from real_page_pipeline import static_style_for_call
from test_generate_lanhu_source_page import source_component
from test_layout_mapping_contract import render_nodes


class SurfacePaddingTest(unittest.TestCase):
    def test_toggle_icon_keeps_child_and_external_padding(self):
        output, _, renderer = self.render('''IconToggleButton(checked = false,
            onCheckedChange = {}, modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)) {}''',
            node_type='IconToggleButton')
        self.assertIn("Text('Proceed')", output)
        button = next(n for n in renderer.android_page_by_id.values() if n['type'] == 'IconToggleButton')
        self.assertEqual(button['style']['layout']['padding_dp'], None)
        self.assertIn('minWidth: this.layoutPx(48)', output)

    def test_image_padding_precedes_size_and_named_clip(self):
        _, _, renderer = self.render('''Image(painterResource(R.drawable.cover), null,
            modifier = Modifier.padding(16.dp).size(40.dp, 40.dp)
                .clip(shape = RoundedCornerShape(4.dp)))''', node_type='Image')
        nodes = renderer.android_page_by_id
        image = next(n for n in nodes.values() if n['type'] == 'Image')
        self.assertTrue(image['style']['surface']['clip'])
        self.assertEqual(image['style']['surface']['corner_radius_dp']['top_left'], 4)
        parent = nodes[image['parent_id']]
        self.assertEqual(parent['style']['layout']['width_dp'], 40)
        self.assertEqual(nodes[parent['parent_id']]['style']['layout']['padding_dp']['left'], 16)

    def render(self, body, bindings=None, node_type='Button'):
        call = extract_semantic_ui_calls('Page.kt', body, 'Page', body, 0, set(), {}, {})[0]
        root = source_component('root', 'Column', parent_id=None, sibling_index=0, children_ids=['item'])
        item = source_component('item', node_type, parent_id='root', sibling_index=0, children_ids=['text'])
        item['style'], item['provenance'], item['unresolved'] = static_style_for_call(call, {}, None, bindings)
        item['modifiers'] = call['ordered_modifier_chain']
        item['arguments'] = {'semantic': call['semantic_arguments']}
        item['parameter_bindings'] = bindings or {}
        text = source_component('text', 'Text', parent_id='item', sibling_index=0, text='Proceed', font_size_sp=16)
        return render_nodes([root, item, text])

    def test_button_outer_padding_does_not_replace_content_padding(self):
        output, _, renderer = self.render('''Button(modifier = Modifier.fillMaxWidth()
            .padding(horizontal = 24.dp).then(Modifier.wrapContentHeight()),
            contentPadding = PaddingValues(16.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Color.Black)) {}''')
        nodes = renderer.android_page_by_id
        button = next(n for n in nodes.values() if n['type'] == 'Button')
        self.assertEqual(button['style']['layout']['padding_dp'], dict(left=16, right=16, top=16, bottom=16))
        parent = nodes[button['parent_id']]
        ancestors = []
        while parent['id'] != 'root':
            ancestors.append(parent)
            parent = nodes[parent['parent_id']]
        self.assertTrue(any(n['style']['layout']['padding_dp'] == dict(left=24, right=24, top=0, bottom=0) for n in ancestors))
        self.assertTrue(all(n['style']['surface']['background'] is None for n in ancestors))
        self.assertIn('.padding(this.layoutPx(16))', output)
        self.assertNotIn('.position(', output)

    def test_card_modifier_reference_keeps_both_sides_of_background(self):
        _, _, renderer = self.render('''Box(Modifier.padding(horizontal = 24.dp)
            .then(Modifier.background(Color(0xFFFFFFFF)).padding(paddingValues))) {}''',
            bindings={'paddingValues': 'PaddingValues(vertical = 16.dp)'}, node_type='Box')
        nodes = renderer.android_page_by_id
        surface = next(n for n in nodes.values() if n['style']['surface']['background'])
        self.assertEqual(surface['style']['layout']['padding_dp'], dict(left=0, right=0, top=16, bottom=16))
        outer = nodes[surface['parent_id']]
        self.assertEqual(outer['style']['layout']['padding_dp'], dict(left=24, right=24, top=0, bottom=0))
        self.assertIsNone(outer['style']['surface']['background'])

    def test_repeated_external_padding_is_not_last_write_wins(self):
        _, _, renderer = self.render('''Button(modifier = Modifier.padding(4.dp).padding(8.dp),
            contentPadding = PaddingValues(16.dp)) {}''')
        nodes = renderer.android_page_by_id
        button = next(n for n in nodes.values() if n['type'] == 'Button')
        self.assertEqual(button['style']['layout']['padding_dp']['left'], 16)
        parent = nodes[button['parent_id']]
        self.assertEqual(parent['style']['layout']['padding_dp']['left'], 8)
        self.assertEqual(nodes[parent['parent_id']]['style']['layout']['padding_dp']['left'], 4)

    def test_padding_after_background_stays_inside_surface(self):
        _, _, renderer = self.render('Box(Modifier.background(Color(0xFFFFFFFF)).padding(16.dp)) {}', node_type='Box')
        item = renderer.android_page_by_id['item']
        self.assertEqual(item['style']['layout']['padding_dp']['left'], 16)
        self.assertEqual(item['parent_id'], 'root')
        self.assertEqual(item['style']['surface']['background']['color'], '#FFFFFFFF')


if __name__ == '__main__':
    unittest.main()
