import unittest
from test_component_defaults import ComponentDefaultsTest
from test_partial_page_generation import PartialPageGenerationTest
from generate_arkui_page import Renderer, derive_page_root


class MaterialDefaultsTest(unittest.TestCase):
    def project(self, body, values=None, overrides=None):
        helper = ComponentDefaultsTest()
        source = helper.page(body, overrides or {})
        return helper.projected(source, values)

    def test_outlined_empty_label_border_and_padding_reach_native_code(self):
        helper = ComponentDefaultsTest()
        page = helper.page('OutlinedTextField(value = "", onValueChange = {}, label = { Text("Amount") })', {})
        generation = PartialPageGenerationTest()
        self.addCleanup(generation.doCleanups)
        _, _, loaded = generation.generate_page(page, {'MaterialTheme.colorScheme.outline': '#FF777777',
            'MaterialTheme.colorScheme.onSurface': '#FF111111', 'MaterialTheme.colorScheme.onSurfaceVariant': '#FF555555'})
        field = next(n for n in loaded['components'] if n['type'] == 'OutlinedTextField')
        self.assertEqual(field['style']['surface']['background']['color'], '#00000000')
        self.assertEqual(field['style']['surface']['border']['color'], '#FF777777')
        self.assertEqual(field['style']['content']['placeholder'], 'Amount')
        output = Renderer(derive_page_root(loaded), set(), {}, loaded).render()
        self.assertIn("placeholder: 'Amount'", output)
        self.assertIn('.width(this.layoutPx(280))', output)
        self.assertIn('.placeholderColor', output)

    def test_explicit_textstyle_does_not_inherit_body_large(self):
        nodes = self.project('Text("Label", style = TextStyle(color = Color(0xFF123456)))')['components']
        text = next(n for n in nodes if n['type'] == 'Text')
        self.assertEqual(text['style']['typography']['font_size_sp'], 14)
        self.assertEqual(text['style']['typography']['letter_spacing_sp'], 0)
        self.assertEqual(text['style']['typography']['color'], '#FF123456')

    def test_appbar_color_constructor_equals_factory(self):
        for expression in ('TopAppBarColors(containerColor = Color(0xFF123456))',
                           'TopAppBarDefaults.topAppBarColors(containerColor = Color(0xFF123456))'):
            page = self.project('TopAppBar(title = { Text("Title") }, colors = '+expression+')', {'WindowInsets.statusBars': {'top': 0}})
            bar = next(n for n in page['components'] if n['type']=='TopAppBar')
            self.assertEqual(bar['style']['surface']['background']['color'], '#FF123456')

    def test_default_button_full_shape_content_insets_and_project_override(self):
        page = self.project('Button { Text("Save") }', overrides={'Button': {'surface.background': {'value': '#FFFF0000'}}})
        button = next(n for n in page['components'] if n['type']=='Button')
        self.assertEqual(button['style']['surface']['background']['color'], '#FFFF0000')
        self.assertEqual(button['style']['surface']['corner_sizes']['top_left'], {'value': 50, 'unit': 'percent'})
        self.assertEqual(button['style']['layout']['padding_dp'], dict(left=24, right=24, top=8, bottom=8))

    def test_error_and_disabled_input_use_different_tokens(self):
        values = {'MaterialTheme.colorScheme.error': '#FFAA0000', 'MaterialTheme.colorScheme.onSurface': '#FF112233'}
        for enabled, error, expected in [('true', 'true', '#FFAA0000'), ('false', 'true', '#1F112233')]:
            page = self.project(f'OutlinedTextField(value = "", onValueChange = {{}}, enabled = {enabled}, isError = {error})', values)
            field = next(n for n in page['components'] if n['type']=='OutlinedTextField')
            self.assertEqual(field['style']['surface']['border']['color'], expected)

    def test_disabled_button_keeps_disabled_content_opacity(self):
        page = self.project('Button(enabled = false) { Text("Save") }', {'MaterialTheme.colorScheme.onSurface': '#FF112233'})
        button = next(n for n in page['components'] if n['type']=='Button')
        self.assertEqual(button['style']['typography']['color'], '#61112233')
        self.assertEqual(button['style']['surface']['background']['color'], '#1F112233')


if __name__ == '__main__':
    unittest.main()
