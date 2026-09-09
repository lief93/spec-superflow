import unittest

from test_component_defaults import ComponentDefaultsTest
from test_partial_page_generation import PartialPageGenerationTest
from generate_arkui_page import Renderer, derive_page_root


THEME = {'primary': '#FF123456', 'onPrimary': '#FFFFFFFF', 'onSurface': '#FF112233',
         'onSurfaceVariant': '#FF445566', 'outline': '#FF778899', 'outlineVariant': '#FF8899AA',
         'surface': '#FFEEEEEE', 'surfaceContainerHighest': '#FFDDDDEE',
         'primaryContainer': '#FFCCDDFF', 'onPrimaryContainer': '#FF001122',
         'secondaryContainer': '#FFDDEEFF'}
VALUES = {'MaterialTheme.colorScheme.' + k: v for k, v in THEME.items()}


class FrameworkControlDefaultsTest(unittest.TestCase):
    def generate(self, body, values=None):
        source = ComponentDefaultsTest().page(body, {})
        helper = PartialPageGenerationTest()
        self.addCleanup(helper.doCleanups)
        _, _, page = helper.generate_page(source, VALUES | (values or {}))
        renderer = Renderer(derive_page_root(page), set(), {}, page)
        return page, renderer.render()

    def test_selection_colors_reach_native_without_project_overrides(self):
        for kind, argument, method in [('Checkbox', 'checked', 'selectedColor'),
                                        ('RadioButton', 'selected', 'radioStyle'),
                                        ('Switch', 'checked', 'selectedColor')]:
            with self.subTest(kind=kind):
                page, code = self.generate(f'{kind}({argument} = true)')
                node = next(n for n in page['components'] if n['type'] == kind)
                self.assertEqual(node['style']['control']['active_color'], THEME['primary'])
                self.assertIn('.' + method + '(', code)
                self.assertIn(THEME['primary'], code)
                self.assertIn('material_selection', node['source'])

    def test_explicit_color_factory_does_not_erase_other_default_colors(self):
        page, code = self.generate('Checkbox(checked = true, colors = CheckboxDefaults.colors(checkedColor = Color.Red))')
        node = next(n for n in page['components'] if n['type'] == 'Checkbox')
        self.assertEqual(node['style']['control']['active_color'], '#FFFF0000')
        self.assertEqual(node['style']['control']['inactive_color'], THEME['onSurfaceVariant'])
        self.assertIn(".selectedColor('#FFFF0000')", code)

    def test_disabled_selection_tokens_not_native_disabled_alpha(self):
        page, code = self.generate('Checkbox(checked = false, enabled = false)')
        node = next(n for n in page['components'] if n['type'] == 'Checkbox')
        self.assertEqual(node['style']['control']['inactive_color'], '#61112233')
        self.assertIn('#61112233', code)

    def test_unknown_explicit_colors_remain_unresolved(self):
        page, _ = self.generate('Checkbox(checked = true, colors = missingColors)')
        node = next(n for n in page['components'] if n['type'] == 'Checkbox')
        self.assertIsNone(node['style']['control']['active_color'])
        self.assertTrue(any('colors' in u.get('expression', '').lower() for u in node['unresolved']))

    def test_default_icon_button_is_transparent_and_uses_content_color(self):
        page, code = self.generate('IconButton(onClick = {}) { Text("Icon") }')
        node = next(n for n in page['components'] if n['type'] == 'IconButton')
        self.assertEqual(node['style']['surface']['background']['color'], '#00000000')
        self.assertEqual(node['style']['typography']['color'], THEME['onSurfaceVariant'])
        self.assertIn(".backgroundColor('#00000000')", code)

    def test_icon_button_content_color_reaches_nested_icon_not_only_container(self):
        page, _ = self.generate('IconButton(onClick = {}) { Box { Icon(imageVector = Icons.Default.Add, contentDescription = null) } }')
        icon = next(n for n in page['components'] if n['type'] == 'Icon')
        self.assertEqual(icon['style']['asset']['tint'], THEME['onSurfaceVariant'])
        page, _ = self.generate('IconButton(onClick = {}) { Icon(imageVector = Icons.Default.Add, contentDescription = null, tint = Color.Red) }')
        icon = next(n for n in page['components'] if n['type'] == 'Icon')
        self.assertEqual(icon['style']['asset']['tint'], '#FFFF0000')

    def test_progress_has_theme_track_and_stroke_but_explicit_values_win(self):
        page, code = self.generate('LinearProgressIndicator(progress = 0.5f)')
        node = next(n for n in page['components'] if n['type'] == 'LinearProgressIndicator')
        self.assertEqual(node['style']['control']['active_color'], THEME['primary'])
        self.assertEqual(node['style']['control']['stroke_width_dp'], 4)
        self.assertIn('.style({ strokeWidth: 4 })', code)
        page, _ = self.generate('CircularProgressIndicator(progress = 0.5f, color = Color.Red, strokeWidth = 2.dp)')
        node = next(n for n in page['components'] if n['type'] == 'CircularProgressIndicator')
        self.assertEqual(node['style']['control']['active_color'], '#FFFF0000')
        self.assertEqual(node['style']['control']['stroke_width_dp'], 2)

    def test_default_button_minimum_is_framework_geometry_not_target_guess(self):
        page, code = self.generate('Button { Text("Go") }')
        node = next(n for n in page['components'] if n['type'] == 'Button')
        self.assertEqual(node['source']['material_size'], {'min_width_dp': 58, 'min_height_dp': 40})
        self.assertIn('minHeight: this.layoutPx(40)', code)
        wrapper = next(n for n in page['components'] if n['id'] == node['parent_id'])
        self.assertTrue(wrapper['source']['material_touch_wrapper'])
        self.assertIn('minHeight: this.layoutPx(48)', code)

    def test_explicit_height_and_disabled_minimum_touch_do_not_expand(self):
        for body, values in [('Button(modifier = Modifier.height(60.dp)) { Text("Go") }', {}),
                             ('Button { Text("Go") }', {'LocalMinimumInteractiveComponentSize.current': 0})]:
            page, code = self.generate(body, values)
            self.assertFalse(any(n['source'].get('material_touch_wrapper') for n in page['components']))
            self.assertNotIn('minHeight: this.layoutPx(48)', code)

    def test_partial_button_colors_keep_unspecified_framework_entries(self):
        page, code = self.generate('Button(colors = ButtonDefaults.buttonColors(contentColor = Color.Red)) { Text("Save") }')
        node = next(n for n in page['components'] if n['type'] == 'Button')
        self.assertEqual(node['style']['surface']['background']['color'], THEME['primary'])
        self.assertEqual(node['style']['typography']['color'], '#FFFF0000')
        self.assertIn(THEME['primary'], code)

    def test_filled_input_indicator_and_theme_placeholder_font_reach_backend(self):
        page, code = self.generate('TextField(value = "", onValueChange = {}, label = { Text("Name") })')
        node = next(n for n in page['components'] if n['type'] == 'TextField')
        self.assertEqual(node['style']['surface']['background']['color'], THEME['surfaceContainerHighest'])
        self.assertIn('width: { bottom: this.layoutPx(1) }', code)
        self.assertIn('placeholderFont({ size: 16, weight: 400 })', code)

    def test_explicit_sizes_and_one_dp_divider_are_not_overwritten(self):
        page, code = self.generate('Column { HorizontalDivider(thickness = 1.dp, color = Color.Red); CircularProgressIndicator(progress = 0.5f, modifier = Modifier.size(16.dp)) }')
        self.assertIn('.strokeWidth(1)', code)
        self.assertIn('.width(this.layoutPx(16))', code)
        self.assertNotIn('.width(this.layoutPx(40))', code)

    def test_null_border_and_transparent_background_are_explicit_not_missing(self):
        page, _ = self.generate('OutlinedButton(border = null, colors = ButtonDefaults.outlinedButtonColors(containerColor = Color.Transparent)) { Text("Save") }')
        node = next(n for n in page['components'] if n['type'] == 'OutlinedButton')
        self.assertIsNone(node['style']['surface']['border'])
        self.assertEqual(node['style']['surface']['background']['color'], '#00000000')

    def test_framework_palette_fills_absent_roles_not_unknown_or_explicit_ones(self):
        from ui_migration.frontend.theme import selected_theme_colors
        from analyze_compose_project import extract_compose_theme_tokens
        inventory = extract_compose_theme_tokens({'Theme.kt': 'val colors = lightColorScheme(primary = Color.Red, outline = missingOutline)'})
        colors = selected_theme_colors(inventory)
        self.assertEqual(colors['primary'], '#FFFF0000')
        self.assertEqual(colors['onSurfaceVariant'], '#FF49454F')
        self.assertEqual(colors['secondaryContainer'], '#FFE8DEF8')
        self.assertNotIn('outline', colors)


if __name__ == '__main__':
    unittest.main()
