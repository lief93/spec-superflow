import unittest

from analyze_compose_project import extract_semantic_ui_calls
from generate_lanhu_source_page import project_source_page
from test_generate_lanhu_source_page import source_component
from test_layout_mapping_contract import render_nodes


class InputDecorationLayoutTest(unittest.TestCase):
    def nodes(self, expression=None, values=None, support_text=None):
        field = source_component('field', 'BasicTextField', parent_id=None,
                                 sibling_index=0, text='123', children_ids=['decoration'])
        field['style']['input'] = {'single_line': False}
        decoration = source_component('decoration', 'DecorationBox', parent_id='field',
                                      sibling_index=0)
        decoration['source']['decoration_kind'] = 'material3-outlined'
        decoration['style']['layout']['padding_dp'] = dict(left=16, right=16, top=14, bottom=14)
        decoration['style']['surface']['border'] = dict(width_dp=1, color='#FFCFCFD3', style='solid')
        if expression is not None:
            decoration['arguments'] = {'semantic': {'supportingText': {'expression': expression}}}
        nodes = [field, decoration]
        if support_text:
            decoration['children_ids'] = ['support']
            child = source_component('support', 'Text', parent_id='decoration',
                                     sibling_index=0, text=support_text, font_size_sp=12)
            child['slot_argument_name'] = 'supportingText'
            nodes.append(child)
        payload = {'page': {'id': 'input', 'state': 'default'}, 'components': nodes}
        fixture = {'schema': 'android-to-harmony.page-state-fixture.v1',
                   'page': payload['page'], 'values': values or {}}
        return project_source_page(payload, fixture)[0]['components']

    def test_framework_owner_is_retained_in_source_inventory(self):
        body = 'OutlinedTextFieldDefaults.DecorationBox(supportingText = {})'
        call = extract_semantic_ui_calls('Page.kt', body, 'Page', body, 0, set(), {}, {})[0]
        self.assertEqual(call.get('decoration_kind'), 'material3-outlined')
        body = 'ProjectTheme.DecorationBox(supportingText = {})'
        call = extract_semantic_ui_calls('Page.kt', body, 'Page', body, 0, set(), {}, {})[0]
        self.assertIsNone(call.get('decoration_kind'))

    def test_empty_nonnull_slot_keeps_minimum_region_in_single_json_render(self):
        nodes = self.nodes('{ if (error != null) Text(error) }', {'error': None})
        facts = nodes[1]['source'].get('input_decoration', {})
        self.assertIs(facts.get('supporting_text'), True)
        output, _, renderer = render_nodes(nodes)
        self.assertIn(".id('decoration__supporting')", output)
        self.assertIn('minHeight: this.layoutPx(16)', output)
        self.assertNotIn('floating label/supporting layout is not resolved', str(renderer.unresolved))

    def test_absent_null_and_conditional_null_do_not_add_blank_region(self):
        for expression in (None, 'null', 'if (hasError) { Text("Error") } else null'):
            with self.subTest(expression=expression):
                nodes = self.nodes(expression, {'hasError': False})
                self.assertIs(nodes[1]['source'].get('input_decoration', {}).get('supporting_text'), False)
                output, _, _ = render_nodes(nodes)
                self.assertNotIn(".id('decoration__supporting')", output)

    def test_support_content_is_below_bordered_row_not_a_trailing_icon(self):
        nodes = self.nodes('{ Text("Invalid card") }', support_text='Invalid card')
        output, _, renderer = render_nodes(nodes)
        self.assertIn("Text('Invalid card')", output)
        self.assertIn(".id('decoration__supporting')", output)
        self.assertLess(output.index(".id('decoration')"), output.index("Text('Invalid card')"))
        self.assertIn('top: this.layoutPx(4)', output)
        self.assertNotIn('floating label/supporting layout is not resolved', str(renderer.unresolved))

    def test_editor_has_minimum_line_and_owns_vertical_padding(self):
        output, _, _ = render_nodes(self.nodes('{}'))
        self.assertIn(".id('decoration__text_line')", output)
        self.assertIn('minHeight: this.layoutPx(24)', output)
        self.assertIn(".id('decoration__text_padding')", output)
        self.assertIn('top: this.layoutPx(14)', output)
        row_modifiers = output.split(".id('decoration')", 1)[1].split('Column()', 1)[0]
        self.assertNotIn('top: this.layoutPx(14)', row_modifiers)

    def test_unknown_slot_presence_is_not_silently_absent(self):
        nodes = self.nodes('externalSlot')
        self.assertTrue(any(n.get('path') == 'source.input_decoration.supporting_text'
                            for n in nodes[1]['unresolved']))


if __name__ == '__main__':
    unittest.main()
