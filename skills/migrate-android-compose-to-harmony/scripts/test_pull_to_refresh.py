from __future__ import annotations

import unittest

from analyze_compose_project import extract_semantic_ui_calls
from component_required_facts import build_required_facts
from page_snapshot import normalize_style, PageSnapshotError
from test_generate_lanhu_source_page import source_component
from test_layout_mapping_contract import render_nodes
import test_page_input_surface as input_tests


class PullToRefreshTest(unittest.TestCase):
    def nodes(self, refreshing='false', **arguments):
        root, unresolved = input_tests.InputSurfaceTest().source('PullToRefreshBox',
            {'isRefreshing': refreshing, **arguments},
            [{'name': 'fillMaxSize', 'arguments': ''}])
        root.update(id='refresh', semantic_key='refresh', parent_id=None, sibling_index=0)
        first = source_component('first', 'Text', parent_id='refresh', sibling_index=0,
                                 text='Account', font_size_sp=16)
        second = source_component('second', 'Text', parent_id='refresh', sibling_index=1,
                                  text='Balance', font_size_sp=16)
        for text in (first, second):
            text['style']['typography'].update(font_weight=400, color='#FF000000')
        root['children_ids'] = ['first', 'second']
        return [root, first, second], unresolved

    def test_inventory_keeps_refresh_state_and_content_slots(self):
        body = 'PullToRefreshBox(isRefreshing = false, onRefresh = {}, indicator = { Text("Wait") }) { Text("Account") }'
        calls = extract_semantic_ui_calls('Home.kt', body, 'Home', body, 0, set(), {}, {})
        call = next(c for c in calls if c['component'] == 'PullToRefreshBox')
        self.assertEqual(call['semantic_arguments']['isRefreshing']['expression'], 'false')
        self.assertIn('indicator', call['semantic_arguments'])

    def test_business_wrapper_passes_modifier_and_fixed_state_to_native_container(self):
        import test_ui_state_semantics as semantics
        test = semantics.UiStateSemanticsTest()
        page = test.source('Column { RefreshPanel(Modifier.weight(1f), loading) { Text("Account") } }', '''
@Composable
fun RefreshPanel(modifier: Modifier, refreshing: Boolean, content: @Composable BoxScope.() -> Unit) {
    PullToRefreshBox(isRefreshing = refreshing, modifier = modifier, onRefresh = {}) { content() }
}
''')
        for value in (True, False):
            projected = test.strict(page, {'loading': value})
            refresh = next(n for n in projected['components'] if n['type'] == 'PullToRefreshBox')
            self.assertIs(refresh['style']['state']['refreshing'], value)
            self.assertTrue(any(m['name'] == 'weight' for m in refresh['modifiers']))
            self.assertEqual(test.texts(projected), ['Account'])

    def test_both_states_preserve_box_children_and_consume_state(self):
        for state in ('false', 'true'):
            with self.subTest(state=state):
                nodes, unresolved = self.nodes(state)
                self.assertEqual(unresolved, [])
                self.assertIs(nodes[0]['style']['state'].get('refreshing'), state == 'true')
                output, gate, renderer = render_nodes(nodes)
                self.assertIn('Stack() {', output)
                self.assertNotIn('Refresh({', output)
                self.assertEqual('LoadingProgress()' in output, state == 'true')
                self.assertIn("Text('Account')", output)
                self.assertIn("Text('Balance')", output)
                self.assertIn('.alignContent(Alignment.TopStart)', output)
                self.assertIn('style.state.refreshing', renderer.android_page_applied_component_paths['refresh'])
                self.assertEqual(gate['verdict'], 'pass', gate['failures'])
                self.assertNotIn('.onRefreshing(', output)

    def test_explicit_alignment_and_weight_survive_without_reference_coordinates(self):
        nodes, _ = self.nodes(contentAlignment='Alignment.BottomEnd')
        column = source_component('column', 'Column', parent_id=None, sibling_index=0,
                                  width_dp=300, height_dp=200)
        nodes[0]['parent_id'] = 'column'
        column['children_ids'] = ['refresh']
        nodes[0]['modifiers'] = [{'name': 'weight', 'arguments': '1f'},
                                 {'name': 'fillMaxWidth', 'arguments': ''}]
        nodes[-1]['modifiers'] = [{'name': 'align', 'arguments': 'Alignment.CenterEnd'}]
        output, gate, _ = render_nodes([column, *nodes])
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        self.assertIn('.layoutWeight(1)', output)
        self.assertIn('.alignContent(Alignment.BottomEnd)', output)
        self.assertIn('.layoutGravity(LocalizedAlignment.END)', output)
        changed, _, _ = render_nodes([column, *nodes], perturb_reference_frames=True)
        self.assertEqual(output, changed)

    def test_unknown_state_is_not_silently_defaulted(self):
        nodes, unresolved = self.nodes('state.loading')
        self.assertTrue(unresolved)
        self.assertIsNone(nodes[0]['style']['state'].get('refreshing'))
        facts = build_required_facts(nodes[0])
        self.assertTrue(any(f['path'] == 'style.state.refreshing' and
                            f['status'] in {'symbolic', 'unresolved'} for f in facts))

    def test_refreshing_schema_accepts_only_boolean(self):
        for value in ('true', 1, {}):
            with self.assertRaises(PageSnapshotError):
                normalize_style({'state': {'refreshing': value}}, 'style')

    def test_refresh_indicator_uses_theme_colors_and_does_not_move_content(self):
        from real_page_pipeline import static_style_for_call
        nodes, _ = self.nodes('true')
        style, _, unresolved = static_style_for_call(
            {'source': 'Home.kt', 'line': 1, 'component': 'PullToRefreshBox',
             'semantic_arguments': {'isRefreshing': {'expression': 'true'}}},
            {}, None, theme_colors={'onSurfaceVariant': '#FF123456', 'surfaceContainerHigh': '#FFF0F0F0'})
        self.assertEqual(unresolved, [])
        nodes[0]['style']['control'] = style['control']
        output, gate, _ = render_nodes(nodes)
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        self.assertIn(".color('#FF123456')", output)
        self.assertIn(".backgroundColor('#FFF0F0F0')", output)
        self.assertIn('.translate({ y: this.layoutPx(40) })', output)
        self.assertNotIn('Refresh({', output)
        self.assertEqual(output.count('.translate('), 1)

    def test_custom_indicator_is_not_silently_replaced_with_native_default(self):
        nodes, _ = self.nodes(indicator='{ CustomIndicator() }')
        facts = build_required_facts(nodes[0])
        self.assertTrue(any(f['source_name'] == 'indicator' and f['status'] == 'unresolved' for f in facts))


if __name__ == '__main__':
    unittest.main()
