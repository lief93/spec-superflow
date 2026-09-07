from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from component_required_facts import build_required_facts
from real_page_pipeline import static_style_for_call
from test_generate_lanhu_source_page import source_component
from test_layout_mapping_contract import render_nodes


class PagePropertyCoverageTest(unittest.TestCase):
    def node(self, kind='Text'):
        node = source_component('sample', kind, parent_id=None, sibling_index=0,
                                text='Example' if kind == 'Text' else None,
                                width_dp=180, height_dp=60)
        if kind == 'Text':
            node['style']['typography'].update(font_size_sp=16, font_weight=400, color='#FF222222')
        return node

    def test_source_generates_explicit_font_and_state_values(self):
        call = {'source': 'Sample.kt', 'line': 1, 'component': 'Text',
                'semantic_arguments': {key: {'expression': value} for key, value in {
                    'text': '"Example"', 'fontStyle': 'FontStyle.Italic',
                    'letterSpacing': '1.25.sp', 'enabled': 'false',
                }.items()}, 'ordered_modifier_chain': []}
        style, _, unresolved = static_style_for_call(call, {}, None)
        self.assertEqual(style['typography']['font_style'], 'italic')
        self.assertEqual(style['typography']['letter_spacing_sp'], 1.25)
        self.assertFalse(style['state']['enabled'])
        self.assertEqual(unresolved, [])
        node = self.node()
        node.update(style=style, arguments={'semantic': call['semantic_arguments']})
        paths = {f['path'] for f in build_required_facts(node)}
        self.assertTrue({'style.typography.font_style', 'style.typography.letter_spacing_sp',
                         'style.state.enabled'}.issubset(paths))

    def test_dynamic_enabled_is_not_replaced_with_true(self):
        call = {'source': 'Sample.kt', 'line': 1, 'component': 'Button',
                'semantic_arguments': {'enabled': {'expression': 'uiState.canSubmit'}},
                'ordered_modifier_chain': []}
        style, _, unresolved = static_style_for_call(call, {}, None)
        self.assertIsNone(style['state']['enabled'])
        self.assertIn('style.state.enabled', {v['path'] for v in unresolved})

    def test_text_style_and_direct_precedence_preserve_all_simple_properties(self):
        call = {'source': 'Sample.kt', 'line': 1, 'component': 'Text',
            'semantic_arguments': {
                'style': {'expression': 'TextStyle(fontStyle = FontStyle.Italic, letterSpacing = 2.sp, fontWeight = FontWeight.Light, textAlign = TextAlign.End, textDecoration = TextDecoration.Underline)'},
                'letterSpacing': {'expression': '0.5.sp'},
            }, 'ordered_modifier_chain': []}
        style, _, unresolved = static_style_for_call(call, {}, None)
        self.assertEqual(unresolved, [])
        self.assertEqual(style['typography']['font_style'], 'italic')
        self.assertEqual(style['typography']['letter_spacing_sp'], .5)
        self.assertEqual(style['typography']['font_weight'], 300)
        self.assertEqual(style['typography']['text_align'], 'end')
        self.assertEqual(style['typography']['decoration'], 'underline')

    def test_unresolved_font_argument_cannot_keep_a_theme_default(self):
        call = {'source': 'Sample.kt', 'line': 1, 'component': 'Text',
            'semantic_arguments': {'style': {'expression': 'TextStyle(fontSize = 16.sp)'},
                                   'fontSize': {'expression': 'state.dynamicSize'}},
            'ordered_modifier_chain': []}
        style, _, unresolved = static_style_for_call(call, {}, None)
        self.assertIsNone(style['typography']['font_size_sp'])
        self.assertIn('style.typography.font_size_sp', {v['path'] for v in unresolved})

    def test_explicit_appbar_background_is_generated_not_accidentally_transparent(self):
        for expression, color in [('Color.Transparent', '#00000000'), ('Color(0xFF123456)', '#FF123456')]:
            call = {'source': 'Sample.kt', 'line': 1, 'component': 'TopAppBar',
                'semantic_arguments': {'colors': {'expression': f'TopAppBarDefaults.topAppBarColors(containerColor = {expression})'}},
                'ordered_modifier_chain': []}
            style, _, _ = static_style_for_call(call, {}, None)
            self.assertEqual(style['surface']['background'], {'type': 'solid', 'color': color})
            node = self.node('TopAppBar')
            node['style']['surface']['background'] = style['surface']['background']
            node['arguments'] = {'semantic': call['semantic_arguments']}
            self.assertTrue(all(f['status'] == 'resolved' for f in build_required_facts(node)))
            output, gate, _ = render_nodes([node])
            self.assertIn(f".backgroundColor('{color}')", output)
            self.assertEqual(gate['verdict'], 'pass', gate['failures'])

    def test_source_generates_scale_and_rotation_without_guessing(self):
        call = {'source': 'Sample.kt', 'line': 1, 'component': 'Box',
                'ordered_modifier_chain': [
                    {'name': 'scale', 'arguments': 'scaleX = -1f, scaleY = 0.5f'},
                    {'name': 'rotate', 'arguments': '30f'}]}
        style, _, unresolved = static_style_for_call(call, {}, None)
        self.assertEqual(style['transform']['scale_x'], -1)
        self.assertEqual(style['transform']['scale_y'], .5)
        self.assertEqual(style['transform']['rotation_degrees'], 30)
        node = self.node('Box')
        node.update(style=style, modifiers=call['ordered_modifier_chain'])
        self.assertTrue(all(f['status'] == 'resolved' for f in build_required_facts(node)))
        self.assertEqual(unresolved, [])

    def test_simple_fields_are_emitted_not_only_marked(self):
        cases = [
            ('typography', 'font_style', 'italic', '.fontStyle(FontStyle.Italic)'),
            ('typography', 'decoration', 'none', '.decoration({ type: TextDecorationType.None })'),
            ('state', 'enabled', False, '.enabled(false)'),
            ('state', 'visible', False, '.visibility(Visibility.None)'),
            ('content', 'content_description', 'Accessible sample', ".accessibilityText('Accessible sample')"),
            ('transform', 'rotation_degrees', 30, '.rotate({ angle: 30 })'),
            ('transform', 'scale_x', -1, '.scale({ x: -1, y: 1 })'),
            ('transform', 'translation_x_dp', 12, '.translate({ x: this.layoutPx(12) })'),
        ]
        for section, field, value, expected in cases:
            with self.subTest(field=field):
                node = self.node()
                node['style'].setdefault(section, {})[field] = value
                output, gate, _ = render_nodes([node])
                self.assertIn(expected, output)
                self.assertEqual(gate['verdict'], 'pass', gate['failures'])

    def test_input_value_placeholder_and_overflow_use_input_api(self):
        node = self.node('BasicTextField')
        node['style']['content'].update(text='Typed', placeholder='Enter name')
        node['style']['typography']['overflow'] = 'ellipsis'
        output, gate, _ = render_nodes([node])
        self.assertIn("TextInput({ text: 'Typed', placeholder: 'Enter name' })", output)
        self.assertIn('.textOverflow(TextOverflow.Ellipsis)', output)
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])

    def test_unimplemented_selection_states_fail_instead_of_disappearing(self):
        for field in ('selected', 'checked'):
            node = self.node()
            node['style']['state'][field] = True
            _, gate, _ = render_nodes([node])
            self.assertIn('style.state.' + field, {f['path'] for f in gate['failures']})

    def test_empty_flow_containers_keep_their_native_type(self):
        for kind in ('Row', 'Column', 'LazyRow', 'LazyColumn'):
            node = self.node(kind)
            output, gate, _ = render_nodes([node])
            self.assertIn(('Row' if 'Row' in kind else 'Column') + '()', output)
            self.assertEqual(gate['verdict'], 'pass', gate['failures'])

    def test_constraint_dimensions_use_runtime_pixel_rounding(self):
        node = self.node('Box')
        node['modifiers'] = [{'name': 'widthIn', 'arguments': 'min = 40.5.dp, max = 120.dp'}]
        output, gate, _ = render_nodes([node])
        self.assertIn('.constraintSize({ minWidth: this.layoutPx(40.5), maxWidth: this.layoutPx(120) })', output)
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])

    def test_explicit_unmapped_native_arguments_are_not_silently_accepted(self):
        for kind, argument, expression in (
            ('TextField', 'visualTransformation', 'CustomMaskTransformation()'),
            ('TextField', 'label', '{ Text("Account") }'),
            ('LazyColumn', 'reverseLayout', 'true'),
        ):
            node = self.node(kind)
            node['arguments'] = {'semantic': {argument: {'expression': expression}}}
            facts = build_required_facts(node)
            self.assertTrue(any(f['path'] == 'source.arguments.' + argument.lower()
                                and f['status'] == 'unresolved' for f in facts))

    def test_icon_tint_is_generated_and_consumed(self):
        call = {'source': 'Sample.kt', 'line': 1, 'component': 'Icon',
                'semantic_arguments': {'tint': {'expression': 'Color(0xFF123456)'}},
                'ordered_modifier_chain': []}
        style, _, unresolved = static_style_for_call(call, {}, None)
        self.assertEqual(style['asset']['tint'], '#FF123456')
        self.assertEqual(unresolved, [])
        node = self.node('Icon')
        node['style']['asset'].update(resource='sample_icon', tint=style['asset']['tint'], content_scale='fit')
        output, gate, _ = render_nodes([node], resources={'media:sample_icon'})
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        self.assertIn('.colorFilter(', output)

    def test_catalog_accounts_for_every_schema_field_and_renderer_type(self):
        from page_snapshot import STYLE_SECTIONS
        from page_component_catalog import CONTROL_FAMILIES, FIELD_AUDIT, NATIVE_CONTAINERS, NATIVE_LEAVES, NATIVE_BUTTONS
        self.assertEqual(set(FIELD_AUDIT), {f'{section}.{field}' for section, fields in STYLE_SECTIONS.items() for field in fields})
        names = [name for family in CONTROL_FAMILIES.values() for name in family]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), NATIVE_CONTAINERS | NATIVE_LEAVES | NATIVE_BUTTONS)
        self.assertEqual(len(set(names) - set(CONTROL_FAMILIES['internal'])), 36)

    def test_text_measurement_fields_are_not_misclassified_as_paint_only(self):
        from generate_arkui_page import target_fact_phase
        self.assertEqual(target_fact_phase('style.typography.font_size_sp'), 'measure')
        self.assertEqual(target_fact_phase('style.content.text'), 'measure')
        self.assertEqual(target_fact_phase('style.typography.text_align'), 'layout')
        self.assertEqual(target_fact_phase('style.typography.color'), 'draw')

    def test_all_declared_android_types_consume_shared_visual_fields(self):
        from page_component_catalog import CONTROL_FAMILIES
        for family, kinds in CONTROL_FAMILIES.items():
            if family == 'internal':
                continue
            for kind in kinds:
                with self.subTest(kind=kind):
                    node = self.node(kind)
                    if family == 'text':
                        node['style']['typography'].update(font_size_sp=16, font_weight=400, color='#FF222222')
                        node['style']['content']['text'] = 'Example'
                    if family == 'input':
                        node['style']['content']['text'] = ''
                    if family == 'image':
                        node['style']['asset'].update(resource='sample_icon', content_scale='fit')
                    if family == 'selection':
                        node['style']['state']['selected' if kind == 'RadioButton' else 'checked'] = True
                    if family in {'range', 'progress'}:
                        node['style'].setdefault('control', {}).update(value=.5, minimum=0, maximum=1)
                    if family == 'range':
                        node['style']['control']['steps'] = 3
                    node['style']['state']['enabled'] = False
                    node['style']['surface']['alpha'] = .5
                    node['style']['layout']['padding_dp'] = dict.fromkeys(('left', 'right', 'top', 'bottom'), 8)
                    output, gate, _ = render_nodes([node], resources={'media:sample_icon'})
                    self.assertIn('.enabled(false)', output)
                    self.assertIn('.opacity(0.5)', output)
                    self.assertIn('.padding(this.layoutPx(8))', output)
                    self.assertEqual(gate['verdict'], 'pass', gate['failures'])

    def test_partial_shadow_and_border_never_pass_as_fully_consumed(self):
        shadow = {'color': '#33000000', 'offset_x_dp': 0, 'offset_y_dp': 2,
                  'blur_radius_dp': 4, 'spread_radius_dp': 0}
        cases = [('shadows', [shadow, shadow]),
                 ('shadows', [{**shadow, 'spread_radius_dp': 5}]),
                 ('border', {'width_dp': 1, 'color': '#FF000000', 'style': 'dashed', 'dash_dp': [4, 8]}),
                 ('border', {'edges': {'left': {'width_dp': 1, 'color': '#FF000000'}}})]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                node = self.node('Box')
                node['style']['surface'][field] = copy.deepcopy(value)
                _, gate, renderer = render_nodes([node])
                self.assertIn('style.surface.' + field, {f['path'] for f in gate['failures']})
                self.assertTrue(renderer.unresolved)


if __name__ == '__main__':
    unittest.main()
