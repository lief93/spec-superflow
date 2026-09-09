from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from component_required_facts import build_required_facts
from page_snapshot import normalize_style, PageSnapshotError
import test_page_input_surface as input_tests
from test_layout_mapping_contract import render_nodes
from test_generate_lanhu_source_page import source_component


class CommonPageControlsTest(unittest.TestCase):
    def test_kotlin_inventory_preserves_all_new_controls_and_guarded_slots(self):
        from analyze_compose_project import extract_semantic_ui_calls
        body = '''Checkbox(checked = true)
Switch(checked = false, thumbContent = { CustomThumb() })
RadioButton(selected = true)
Slider(value = 25f, valueRange = 10f..40f, steps = 5, thumb = { CustomThumb() })
LinearProgressIndicator(progress = { 0.37f }, trackColor = Color.White)
CircularProgressIndicator(progress = 0.37f, strokeWidth = 4.dp)
Divider(thickness = 2.dp)
HorizontalDivider(thickness = 2.dp)
VerticalDivider(thickness = 2.dp)'''
        calls = extract_semantic_ui_calls('Controls.kt', body, 'Controls', body, 0, set(), {}, {})
        indexed = {call['component']: call for call in calls}
        self.assertEqual(set(indexed), {'Checkbox', 'Switch', 'RadioButton', 'Slider',
            'LinearProgressIndicator', 'CircularProgressIndicator', 'Divider', 'HorizontalDivider', 'VerticalDivider'})
        self.assertEqual(indexed['Slider']['semantic_arguments']['valueRange']['expression'], '10f..40f')
        self.assertIn('thumb', indexed['Slider']['semantic_arguments'])
        self.assertIn('thumbContent', indexed['Switch']['semantic_arguments'])

    def node(self, kind, **arguments):
        return input_tests.InputSurfaceTest().source(kind, arguments)[0]

    def assert_blocked(self, node):
        try:
            _, gate, _ = render_nodes([node])
        except ValueError as error:
            self.assertIn('required component facts', str(error))
        else:
            self.assertEqual(gate['verdict'], 'fail')

    def test_selection_controls_consume_both_states(self):
        for kind, field, constructor, attribute in (
            ('Checkbox', 'checked', 'Checkbox()', '.select('),
            ('Switch', 'checked', 'Toggle({ type: ToggleType.Switch', 'isOn: '),
            ('RadioButton', 'selected', 'Radio({', '.checked('),
        ):
            for value in ('true', 'false'):
                with self.subTest(kind=kind, value=value):
                    node = self.node(kind, **{field: value})
                    from ui_migration.frontend.material_defaults import project_material_defaults
                    from generate_harmony_theme_resources import MATERIAL3_LIGHT_COLOR_DEFAULTS
                    project_material_defaults(node, {'MaterialTheme.colorScheme.' + key: color
                        for key, color in MATERIAL3_LIGHT_COLOR_DEFAULTS.items()})
                    output, gate, renderer = render_nodes([node])
                    self.assertEqual(renderer.unresolved, [])
                    self.assertEqual(gate['verdict'], 'pass', gate['failures'])
                    self.assertIn(constructor, output)
                    self.assertIn(attribute + value, output)
                    self.assertIn('.margin(0)', output)
                    if kind == 'Checkbox':
                        self.assertIn('.shape(CheckBoxShape.ROUNDED_SQUARE)', output)
                    self.assertIn('style.state.' + field,
                        renderer.android_page_applied_component_paths[node['id']])

    def test_missing_and_dynamic_selection_state_fails(self):
        for kind, field in [('Checkbox', 'checked'), ('Switch', 'checked'), ('RadioButton', 'selected')]:
            for args in ({}, {field: 'state.selected'}):
                node = self.node(kind, **args)
                self.assertTrue(any(f['status'] in {'unresolved', 'symbolic'} for f in build_required_facts(node)))
                self.assert_blocked(node)

    def test_range_slider_consumes_value_range_and_discrete_steps(self):
        node = self.node('Slider', value='25f', valueRange='10f..40f', steps='5')
        output, gate, _ = render_nodes([node])
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        self.assertIn('Slider({ value: 25, min: 10, max: 40, step: 5', output)
        self.assertEqual(node['style']['control']['steps'], 5)

    def test_slider_continuous_and_custom_thumb_fail_instead_of_becoming_discrete(self):
        for args in ({'value': '0.5f'}, {'value': '0.5f', 'steps': '3', 'thumb': '{ CustomThumb() }'}):
            node = self.node('Slider', **args)
            self.assert_blocked(node)

    def test_progress_value_not_text_or_fixed_percentage(self):
        for kind, shape in [('LinearProgressIndicator', 'Linear'), ('CircularProgressIndicator', 'Ring')]:
            node = self.node(kind, progress='{ 0.37f }', color='Color(0xFF123456)', trackColor='Color(0xFFEEEEEE)')
            output, gate, _ = render_nodes([node])
            self.assertEqual(gate['verdict'], 'pass', gate['failures'])
            self.assertIn('value: 0.37, total: 1, type: ProgressType.' + shape, output)
            self.assertIn(".color('#FF123456')", output)
            self.assertIn(".backgroundColor('#FFEEEEEE')", output)

    def test_indeterminate_progress_cannot_silently_be_zero(self):
        for kind in ('LinearProgressIndicator', 'CircularProgressIndicator'):
            self.assert_blocked(self.node(kind))

    def test_progress_does_not_claim_conflicting_or_ignored_fields(self):
        node = self.node('LinearProgressIndicator', progress='.5f', trackColor='Color.White')
        node['style']['control'].update(minimum=2, maximum=3)
        self.assert_blocked(node)
        node['style']['control'].update(minimum=0, maximum=1)
        node['style']['surface']['background'] = {'type': 'solid', 'color': '#FF000000'}
        self.assert_blocked(node)

    def test_divider_orientation_and_thickness(self):
        for kind, vertical in [('HorizontalDivider', 'false'), ('VerticalDivider', 'true')]:
            node = self.node(kind, thickness='2.dp', color='Color(0xFF123456)')
            output, gate, _ = render_nodes([node])
            self.assertEqual(gate['verdict'], 'pass', gate['failures'])
            self.assertIn('Divider()', output)
            self.assertIn('.vertical(' + vertical + ')', output)
            self.assertIn('.strokeWidth(2)', output)

    def test_control_schema_rejects_invalid_ranges(self):
        for control in ({'minimum': 4, 'maximum': 2}, {'steps': -1}, {'steps': 1.5}, {'value': float('inf')}):
            with self.assertRaises(PageSnapshotError):
                normalize_style({'control': control}, 'style')

    def test_unknown_material_slots_and_colors_are_not_silent(self):
        for kind, args in [('Checkbox', {'checked': 'true', 'colors': 'customColors'}),
                           ('Switch', {'checked': 'true', 'thumbContent': '{ Icon() }'}),
                           ('LinearProgressIndicator', {'progress': '.5f', 'gapSize': '8.dp'}),
                           ('Divider', {'startIndent': '16.dp'}),
                           ('TextField', {'label': '{ Text("Name") }'})]:
            node = self.node(kind, **args)
            self.assert_blocked(node)

    def test_parent_fraction_uses_target_measurement_not_reference_frame(self):
        root = source_component('root', 'BoxWithConstraints', parent_id=None, sibling_index=0,
                                width_dp=300, height_dp=100)
        child = source_component('child', 'Box', parent_id='root', sibling_index=0, width_dp=20, height_dp=20)
        child['modifiers'] = [{'name': 'offset', 'arguments': 'x = maxWidth * 0.25f, y = -maxHeight * 0.5f'}]
        root['children_ids'] = ['child']
        output, gate, _ = render_nodes([root, child])
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        self.assertIn('current.width', output)
        self.assertIn('current.height', output)
        self.assertIn('@State private pageConstraint0Width', output)
        self.assertIn('this.pageConstraint0Width * 0.25', output)
        self.assertNotIn('.translate({ x: 75', output)
        changed, _, _ = render_nodes([root, child], perturb_reference_frames=True)
        self.assertEqual(output, changed)

    def test_parent_fraction_wrap_constraint_is_explicitly_unsupported(self):
        root = source_component('root', 'BoxWithConstraints', parent_id=None, sibling_index=0)
        child = source_component('child', 'Box', parent_id='root', sibling_index=0, width_dp=20, height_dp=20)
        root['children_ids'] = ['child']
        child['modifiers'] = [{'name': 'offset', 'arguments': 'x = maxWidth * 0.25f'}]
        _, gate, renderer = render_nodes([root, child])
        self.assertEqual(gate['verdict'], 'fail')
        self.assertTrue(any('constraint' in item.get('reason', '') for item in renderer.unresolved))

    def test_soft_wrap_and_min_lines_are_source_facts(self):
        node = self.node('Text', text='"Single line"', softWrap='false', minLines='1',
                         fontSize='16.sp', fontWeight='FontWeight.Normal', color='Color.Black')
        self.assertIs(node['style']['typography'].get('soft_wrap'), False)
        self.assertEqual(node['style']['typography'].get('min_lines'), 1)
        output, gate, _ = render_nodes([node])
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        self.assertIn('.maxLines(1)', output)

    def test_min_lines_uses_font_measurement_not_reference_height(self):
        node = self.node('Text', text='"Sample"', minLines='3', fontSize='16.sp',
                         fontWeight='FontWeight.Normal', color='Color.Black')
        node['style']['typography']['font_family'] = 'SampleFont'
        node['style']['layout']['height_dp'] = None
        faces = [{'alias': 'Sample400', 'match_names': ['samplefont'], 'weight': 400, 'rawfile': 'fonts/sample.ttf'}]
        output, gate, _ = render_nodes([node], font_faces=faces)
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        self.assertIn("nativeMinLinesHeight($rawfile('fonts/sample.ttf'), 16, 0, 3, 0)", output)
        self.assertIn('natural * count + extra * (count - 1)', output)

    def test_unwrapped_hard_breaks_fail_without_losing_lines(self):
        node = self.node('Text', text='"Sample"', softWrap='false', fontSize='16.sp',
                         fontWeight='FontWeight.Normal', color='Color.Black')
        for separator in ('\n', '\r', '\u2028', '\u2029'):
            node['style']['content']['text'] = 'first' + separator + 'second'
            self.assert_blocked(node)

    def test_parent_measurement_and_border_share_one_size_callback(self):
        root = source_component('root', 'BoxWithConstraints', parent_id=None, sibling_index=0,
                                width_dp=300, height_dp=100)
        root['style']['surface']['border'] = {'width_dp': 1, 'color': '#FF000000', 'style': 'solid'}
        root['style']['layout']['padding_dp'] = dict.fromkeys(('top', 'bottom', 'left', 'right'), 8)
        child = source_component('child', 'Box', parent_id='root', sibling_index=0, width_dp=20, height_dp=20)
        child['modifiers'] = [{'name': 'offset', 'arguments': 'x = maxWidth / 4'}]
        root['children_ids'] = ['child']
        output, gate, _ = render_nodes([root, child])
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        self.assertEqual(output.count('.onSizeChange('), 1)
        self.assertIn('Number(current.width) - 16', output)
        self.assertIn('this.pageBorder0Width = current.width', output)

    def test_fill_parent_fraction_uses_finite_scope_and_rejects_unbounded_scroll(self):
        root = source_component('root', 'Column', parent_id=None, sibling_index=0, children_ids=['scope'])
        root['modifiers'] = [{'name': 'verticalScroll', 'arguments': 'rememberScrollState()'}]
        scope = source_component('scope', 'BoxWithConstraints', parent_id='root', sibling_index=0, children_ids=['child'])
        scope['modifiers'] = [{'name': 'fillMaxHeight', 'arguments': ''}]
        child = source_component('child', 'Box', parent_id='scope', sibling_index=0, width_dp=20, height_dp=20)
        child['modifiers'] = [{'name': 'offset', 'arguments': 'y = maxHeight / 4'}]
        _, gate, _ = render_nodes([root, scope, child])
        self.assertEqual(gate['verdict'], 'fail')
        root['modifiers'] = []
        root['style']['layout']['height_dp'] = 120
        output, gate, _ = render_nodes([root, scope, child])
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        self.assertIn('this.pageConstraint0Height * 0.25', output)


if __name__ == '__main__':
    unittest.main()
