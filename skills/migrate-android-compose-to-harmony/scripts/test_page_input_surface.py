from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from component_required_facts import build_required_facts
from page_snapshot import normalize_style, PageSnapshotError
from real_page_pipeline import static_style_for_call
import test_page_property_coverage as coverage
from test_layout_mapping_contract import render_nodes


class InputSurfaceTest(unittest.TestCase):
    def source(self, kind='BasicTextField', arguments=None, modifiers=None):
        if kind in {'BasicTextField', 'TextField', 'OutlinedTextField'}:
            arguments = {'textStyle': 'TextStyle(fontSize = 16.sp, fontWeight = FontWeight.Normal, color = Color.Black)', **(arguments or {})}
        call = {'source': 'Sample.kt', 'line': 1, 'component': kind,
                'semantic_arguments': {k: {'expression': v} for k, v in (arguments or {}).items()},
                'ordered_modifier_chain': modifiers or []}
        style, _, unresolved = static_style_for_call(call, {}, None)
        node = coverage.PagePropertyCoverageTest().node(kind)
        node.update(style=style, arguments={'semantic': call['semantic_arguments']},
                    modifiers=call['ordered_modifier_chain'])
        return node, unresolved

    def test_password_readonly_keyboard_flow_reaches_native_consumer(self):
        node, unresolved = self.source(arguments={'value': '"secret"', 'singleLine': 'true',
            'readOnly': 'true', 'visualTransformation': 'PasswordVisualTransformation()',
            'keyboardOptions': 'KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Done)'})
        self.assertEqual(unresolved, [])
        self.assertEqual(node['style']['input']['password'], True)
        self.assertEqual(node['style']['input']['read_only'], True)
        self.assertTrue(all(f['status'] != 'unresolved' for f in build_required_facts(node)))
        output, gate, _ = render_nodes([node])
        for code in ('.type(InputType.Password)', '.showPassword(false)',
                     '.onWillChange(() => false)', '.enableKeyboardOnFocus(false)',
                     '.enterKeyType(EnterKeyType.Done)'):
            self.assertIn(code, output)
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])

    def test_multiline_uses_textarea_not_singleline_input(self):
        node, unresolved = self.source(arguments={'value': '""', 'singleLine': 'false', 'readOnly': 'false',
            'keyboardOptions': 'KeyboardOptions(keyboardType = KeyboardType.Email, imeAction = ImeAction.Next)'})
        self.assertEqual(unresolved, [])
        output, gate, _ = render_nodes([node])
        self.assertIn('TextArea({', output)
        self.assertIn('.type(TextAreaType.EMAIL)', output)
        self.assertNotIn('.showPasswordIcon(', output)
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])

    def test_multiline_text_escapes_line_breaks_in_generated_source(self):
        node, _ = self.source(arguments={'value': '"first\\nsecond"', 'singleLine': 'false'})
        output, gate, _ = render_nodes([node])
        self.assertIn("TextArea({ text: 'first\\nsecond' })", output)
        self.assertNotIn("text: 'first\nsecond'", output)
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])

    def test_dynamic_input_and_unknown_keyboard_options_block(self):
        for argument, expression in [('readOnly', 'state.locked'), ('visualTransformation', 'mask'),
                ('singleLine', 'state.compact'), ('keyboardOptions', 'KeyboardOptions(autoCorrectEnabled = false)')]:
            node, unresolved = self.source(arguments={argument: expression})
            self.assertTrue(unresolved, argument)
            self.assertTrue(any(f['status'] == 'unresolved' for f in build_required_facts(node)), argument)

    def test_password_keyboard_does_not_imply_visual_mask(self):
        node, _ = self.source(arguments={'value': '""', 'singleLine': 'true', 'visualTransformation': 'VisualTransformation.None',
            'keyboardOptions': 'KeyboardOptions(keyboardType = KeyboardType.Password)'})
        output, gate, _ = render_nodes([node])
        self.assertIn('.showPassword(true)', output)
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])

    def test_target_rejects_unsupported_input_combinations(self):
        for arguments in [{'singleLine': 'false', 'visualTransformation': 'PasswordVisualTransformation()'},
                          {'singleLine': 'true', 'keyboardOptions': 'KeyboardOptions(imeAction = ImeAction.Previous)'}]:
            node, _ = self.source(arguments={'value': '""', **arguments})
            _, gate, _ = render_nodes([node])
            self.assertEqual(gate['verdict'], 'fail')

    def test_relative_asymmetric_corners_need_direction(self):
        from component_required_facts import constant_corner_radius
        expression = 'RoundedCornerShape(topStart = 2.dp, topEnd = 8.dp)'
        self.assertIsNone(constant_corner_radius(expression))
        self.assertEqual(constant_corner_radius(expression, 'rtl'),
            {'top_left': 8, 'top_right': 2, 'bottom_right': 0, 'bottom_left': 0})

    def test_input_schema_rejects_invalid_values(self):
        for field, value in [('single_line', 'true'), ('read_only', 1), ('password', 'mask'),
                              ('keyboard_type', 'not-a-keyboard'), ('ime_action', 'submit-magic')]:
            with self.assertRaises(PageSnapshotError):
                normalize_style({'input': {field: value}}, 'style')

    def test_gradients_do_not_collapse_to_first_color(self):
        for method, direction in [('horizontalGradient', 'Right'), ('verticalGradient', 'Bottom')]:
            node, unresolved = self.source('Box', modifiers=[{'name': 'background',
                'arguments': f'Brush.{method}(colors = listOf(Color(0xFFFF0000), Color(0xFF0000FF)))'}])
            self.assertEqual(unresolved, [])
            self.assertEqual(node['style']['surface']['background']['type'], 'linear_gradient')
            output, gate, _ = render_nodes([node])
            self.assertIn('.linearGradient(', output)
            self.assertIn('GradientDirection.' + direction, output)
            self.assertIn("['#FFFF0000', 0]", output)
            self.assertIn("['#FF0000FF', 1]", output)
            self.assertEqual(gate['verdict'], 'pass', gate['failures'])

    def test_unsupported_gradient_cannot_become_solid(self):
        for expr in ('Brush.horizontalGradient(listOf(Color.Red, state.color))',
                     'Brush.horizontalGradient(listOf(Color.Red, Color.Blue), startX = 12f)',
                     'Brush.radialGradient(listOf(Color.Red, Color.Blue))'):
            node, unresolved = self.source('Box', modifiers=[{'name': 'background', 'arguments': expr}])
            self.assertIsNone(node['style']['surface']['background'])
            self.assertTrue(unresolved)

    def test_gradient_schema_rejects_invalid_stops(self):
        for stops in ([0, .5, 1], [.8, .2]):
            with self.assertRaises(PageSnapshotError):
                normalize_style({'surface': {'background': {'type': 'linear_gradient',
                    'colors': ['#FF000000', '#FFFFFFFF'], 'stops': stops}}}, 'style')

    def test_asymmetric_absolute_corners_are_not_flattened(self):
        node, unresolved = self.source('Box', modifiers=[{'name': 'clip', 'arguments':
            'AbsoluteRoundedCornerShape(topLeft = 2.dp, topRight = 4.dp, bottomRight = 6.dp, bottomLeft = 8.dp)'}])
        self.assertEqual(unresolved, [])
        self.assertEqual(node['style']['surface']['corner_radius_dp'],
            {'top_left': 2, 'top_right': 4, 'bottom_right': 6, 'bottom_left': 8})
        output, gate, _ = render_nodes([node])
        self.assertIn('.borderRadius({ topLeft: 2, topRight: 4, bottomRight: 6, bottomLeft: 8 })', output)
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])


if __name__ == '__main__':
    unittest.main()
