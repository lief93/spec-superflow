import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_generate_lanhu_source_page import source_component
from test_layout_mapping_contract import render_nodes


class OrderedLayoutTest(unittest.TestCase):
    def nodes(self, chain):
        root = source_component('root', 'Column', parent_id=None, sibling_index=0, children_ids=['item'])
        item = source_component('item', 'Row', parent_id='root', sibling_index=0, children_ids=['label'])
        item['modifiers'] = [{'name': name, 'arguments': expr} for name, expr in chain]
        label = source_component('label', 'Text', parent_id='item', sibling_index=0, text='X')
        label['style']['typography'].update(font_size_sp=14, font_weight=400, color='#FF222222')
        return [root, item, label]

    def test_padding_before_size_becomes_outer_wrapper_and_inner_native_row(self):
        output, gate, renderer = render_nodes(self.nodes([('padding', '8.dp'), ('size', '40.dp')]))
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        outer = renderer.android_page_by_id['item']
        inner = renderer.android_page_by_id[outer['children_ids'][0]]
        self.assertEqual(outer['type'], 'Box')
        self.assertEqual(outer['style']['layout']['padding_dp']['left'], 8)
        self.assertEqual(inner['style']['layout']['width_dp'], 40)
        self.assertIn('Row()', output)
        self.assertNotIn('.position(', output)
        altered, _, _ = render_nodes(self.nodes([('padding', '8.dp'), ('size', '40.dp')]), perturb_reference_frames=True)
        self.assertEqual(output, altered)

    def test_repeated_padding_preserves_sum_as_nested_native_layers(self):
        output, gate, renderer = render_nodes(self.nodes([('padding', '4.dp'), ('padding', '8.dp'), ('size', '40.dp')]))
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        paddings = [n['style']['layout']['padding_dp'] for n in renderer.android_page_by_id.values()]
        self.assertTrue(any(p and p['left'] == 4 for p in paddings))
        self.assertTrue(any(p and p['left'] == 8 for p in paddings))

    def test_ambiguous_draw_order_and_duplicate_axis_sizes_remain_unresolved(self):
        for chain in [[('padding', '8.dp'), ('background', 'Color.Red'), ('width', '40.dp')],
                      [('padding', '8.dp'), ('width', '40.dp'), ('width', '80.dp')]]:
            output, gate, renderer = render_nodes(self.nodes(chain))
            self.assertIn("Text('X')", output)
            self.assertTrue(renderer.unresolved)
            self.assertEqual(gate['verdict'], 'fail')


if __name__ == '__main__':
    unittest.main()
