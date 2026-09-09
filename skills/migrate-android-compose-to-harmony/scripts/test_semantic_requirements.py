import unittest

from component_required_facts import required_fact_gate
from ui_migration.contracts.consumption import build_target_phase_consumption_gate
from ui_migration.contracts.requirements import MATERIAL_BACKGROUNDS, merge_requirement_facts
from test_generate_lanhu_source_page import source_component
from test_layout_mapping_contract import render_nodes


class SemanticRequirementsTest(unittest.TestCase):
    def node(self, kind='Box', identity='node', parent=None):
        return source_component(identity, kind, parent_id=parent, sibling_index=0)

    def failures(self, nodes):
        return {(f['component_id'], f['path']) for f in required_fact_gate(nodes)['failures']}

    def test_every_material_surface_requires_paint_even_without_required_facts(self):
        for kind in MATERIAL_BACKGROUNDS:
            with self.subTest(kind=kind):
                node = self.node(kind)
                self.assertIn(('node', 'style.surface.background'), self.failures([node]))
                gate = build_target_phase_consumption_gate({'components': [node]}, {'node'}, set(), {}, {})
                self.assertTrue(any(f['path'] == 'style.surface.background' for f in gate['failures']))

    def test_transparent_paint_is_a_value_not_missing(self):
        node = self.node('Button')
        node['style']['surface']['background'] = {'type': 'solid', 'color': '#00000000'}
        self.assertNotIn(('node', 'style.surface.background'), self.failures([node]))

    def test_plain_container_has_explicit_no_paint_reason(self):
        for kind in ('Row', 'Column', 'Box', 'LazyColumn', 'Spacer'):
            node = self.node(kind)
            paint = next(f for f in merge_requirement_facts(node) if f['path'] == 'style.surface.background')
            self.assertEqual(paint['status'], 'not_applicable')
            self.assertIn('no implicit background', paint['reason'])

    def test_forged_resolved_and_not_applicable_cannot_hide_missing_default(self):
        for status in ('resolved', 'default_resolved', 'not_applicable'):
            node = self.node('Card')
            node['required_facts'] = [dict(path='style.surface.background', status=status)]
            self.assertIn(('node', 'style.surface.background'), self.failures([node]))

    def test_symbolic_required_fact_cannot_pass_source_gate(self):
        node = self.node()
        node['required_facts'] = [dict(path='style.surface.border', status='symbolic')]
        self.assertIn(('node', 'style.surface.border'), self.failures([node]))

    def test_required_paint_erased_after_resolution_is_detected(self):
        node = self.node()
        node['required_facts'] = [dict(path='style.surface.background', status='resolved', expression='Color.Red')]
        self.assertIn(('node', 'style.surface.background'), self.failures([node]))

    def test_weight_scope_uses_actual_parent_not_business_wrapper(self):
        for kind, valid in (('Row', True), ('Column', True), ('Card', True), ('Button', True), ('Box', False)):
            parent = self.node(kind, 'parent')
            wrapper = self.node('MyItem', 'wrapper', 'parent')
            wrapper['source']['custom_component'] = True
            child = self.node('Spacer', 'child', 'wrapper')
            child['layout_rules'] = [dict(kind='weight', value=1, fill=True)]
            self.assertEqual(('child', 'source.modifiers.weight') in self.failures([parent, wrapper, child]), not valid)

    def test_alignment_is_not_text_alignment_and_depends_on_scope(self):
        for kind, align, valid in (('Box', 'CenterEnd', True), ('Row', 'CenterEnd', False),
                                  ('Row', 'CenterVertically', True), ('Column', 'End', True),
                                  ('Card', 'End', True), ('Button', 'CenterVertically', True)):
            parent = self.node(kind, 'parent')
            child = self.node('Box', 'child', 'parent')
            child['layout_rules'] = [dict(kind='alignment', value='Alignment.' + align)]
            self.assertEqual(('child', 'source.modifiers.align') in self.failures([parent, child]), not valid)

    def test_unknown_selected_state_fails_but_false_is_a_value(self):
        for kind, field in (('Checkbox', 'checked'), ('Switch', 'checked'), ('RadioButton', 'selected'), ('IconToggleButton', 'checked')):
            for value in (None, False, True):
                node = self.node(kind)
                node['style']['state'][field] = value
                self.assertEqual(('node', 'style.state.' + field) in self.failures([node]), value is None)

    def test_unknown_enabled_state_is_not_silently_enabled(self):
        node = self.node('Button')
        node['style']['state']['enabled'] = None
        self.assertIn(('node', 'style.state.enabled'), self.failures([node]))
        node['style']['state']['enabled'] = False
        self.assertNotIn(('node', 'style.state.enabled'), self.failures([node]))

    def test_both_gates_report_the_same_component_parent_state_context(self):
        parent = self.node('Row', 'parent')
        child = self.node('Button', 'child', 'parent')
        child['style']['state']['enabled'] = False
        source = required_fact_gate([parent, child])
        target = build_target_phase_consumption_gate({'components': [parent, child]}, {'parent', 'child'}, set(), {}, {})
        a = next(f for f in source['failures'] if f['path'] == 'style.surface.background')
        b = next(f for f in target['failures'] if f['path'] == 'style.surface.background')
        self.assertEqual(a['context'], b['context'])
        self.assertEqual(a['context']['layout_parent_type'], 'Row')
        self.assertFalse(a['context']['fixed_state']['enabled'])

    def test_native_size_mode_does_not_require_fake_numeric_dimensions(self):
        node = self.node()
        facts = merge_requirement_facts(node)
        self.assertTrue(all(f['status'] == 'not_applicable' for f in facts if f['path'] in
                            ('style.layout.width_dp', 'style.layout.height_dp')))

    def test_input_and_image_missing_values_are_not_silently_ignored(self):
        for kind, path in (('BasicTextField', 'style.input.single_line'), ('Text', 'style.typography.color'),
                           ('Image', 'style.asset.resource'), ('VerticalDivider', 'style.control.active_color')):
            self.assertIn(('node', path), self.failures([self.node(kind)]))

    def test_missing_fact_does_not_delete_component_or_stop_generation(self):
        node = self.node('Card')
        output, gate, _ = render_nodes([node])
        self.assertIn(".id('node')", output)
        self.assertEqual(gate['verdict'], 'fail')

    def test_card_internal_column_scope_is_shared_with_emitter(self):
        parent = self.node('Card', 'parent')
        parent['children_ids'] = ['child']
        parent['style']['surface']['background'] = {'type': 'solid', 'color': '#FFFFFFFF'}
        parent['style']['layout']['height_dp'] = 200
        child = self.node('Spacer', 'child', 'parent')
        child['modifiers'] = [dict(name='weight', arguments='1f')]
        output, gate, _ = render_nodes([parent, child])
        self.assertIn('.layoutWeight(1)', output)
        self.assertFalse(any(f['path'] == 'source.modifiers.weight' for f in gate['failures']))


if __name__ == '__main__':
    unittest.main()
