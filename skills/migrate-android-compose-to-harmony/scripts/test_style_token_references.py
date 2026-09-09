import json
import tempfile
import unittest
from pathlib import Path

from test_project_style_definitions import ProjectStyleDefinitionsTest as StyleHelpers
from test_partial_page_generation import PartialPageGenerationTest as PageHelpers
from ui_migration.frontend.project_styles import build_style_definitions, validate_style_definitions
from generate_arkui_page import Renderer, derive_page_root
from generate_lanhu_source_page import project_source_page
from analyze_compose_project import analyze
from real_page_pipeline import build_source_page_spec


def token(kind, member, source_unit=None, target_unit=None):
    result = {'kind': kind, 'target': {'module': '@company/design', 'export': 'AppTokens', 'member': member}}
    if source_unit:
        result.update(sourceUnit=source_unit, targetUnit=target_unit)
    return result


class StyleTokenReferencesTest(unittest.TestCase):
    def definitions(self):
        result = build_style_definitions(StyleHelpers().contract())
        result['tokenMappings'] = {
            'AppTokens.body': token('dimension', 'fontSizeBody', 'sp', 'fp'),
            'AppTokens.ink': token('color', 'textPrimary'),
            'AppTokens.canvas': token('color', 'surface'),
            'AppTokens.radius': token('dimension', 'radius', 'dp', 'vp'),
        }
        return result

    def generate(self, body, definitions=None, values=None):
        source = StyleHelpers().page(definitions or self.definitions(), body)
        helper = PageHelpers()
        self.addCleanup(helper.doCleanups)
        _, _, loaded = helper.generate_page(source, values)
        return loaded, Renderer(derive_page_root(loaded), set(), {}, loaded).render()

    def test_single_json_preserves_reference_and_resolved_value(self):
        loaded, output = self.generate('Text("Hello", fontSize = AppTokens.body, color = AppTokens.ink)',
            values={'AppTokens.body': 19, 'AppTokens.ink': '#FF102030'})
        node = next(n for n in loaded['components'] if n['type'] == 'Text')
        self.assertEqual(node['style']['typography']['font_size_sp'], 19)
        self.assertEqual(node['source']['style_token_references']['typography.font_size_sp']['android'], 'AppTokens.body')
        self.assertIn("import { AppTokens as StyleToken0 } from '@company/design';", output)
        self.assertIn('.fontSize(StyleToken0.fontSizeBody)', output)
        self.assertIn('.fontColor(StyleToken0.textPrimary)', output)
        self.assertEqual(output.count('import { AppTokens'), 1)

    def test_modifier_background_and_shape(self):
        _, output = self.generate('Box(Modifier.size(80.dp).background(AppTokens.canvas).clip(RoundedCornerShape(AppTokens.radius))) {}',
            values={'AppTokens.canvas': '#FFABCDEF', 'AppTokens.radius': 12})
        self.assertIn('.backgroundColor(StyleToken0.surface)', output)
        self.assertEqual(output.count('.backgroundColor(StyleToken0.surface)'), 1)
        self.assertIn('.borderRadius(StyleToken0.radius)', output)

    def test_equal_literal_is_not_a_token(self):
        _, output = self.generate('Text("Hello", fontSize = 19.sp, color = Color(0xFF102030))')
        self.assertNotIn('StyleToken', output)

    def test_missing_value_keeps_reference_without_faking_resolved_fact(self):
        loaded, output = self.generate('Text("Hello", fontSize = AppTokens.body)')
        node = next(n for n in loaded['components'] if n['type'] == 'Text')
        self.assertFalse(any(u['path'] == 'style.typography.font_size_sp' for u in node['unresolved']))
        self.assertIsNone(node['style']['typography']['font_size_sp'])
        self.assertIn('.fontSize(StyleToken0.fontSizeBody)', output)

    def test_invalid_units_and_import_code_are_rejected(self):
        for mutate in (lambda s: s.update(targetUnit='vp'),
                       lambda s: s['target'].update(export='X; evil()'),
                       lambda s: s['target'].update(module="x'\n")):
            definitions = self.definitions()
            mutate(definitions['tokenMappings']['AppTokens.body'])
            with self.assertRaises(ValueError):
                validate_style_definitions(definitions)

    def test_project_default_reference_but_explicit_literal_wins(self):
        definitions = self.definitions()
        definitions['componentDefaults'] = {'Text': {'typography.color': {'expression': 'AppTokens.ink'}}}
        _, output = self.generate('Column { Text("Default"); Text("Explicit", color = Color.Red) }',
            definitions, {'AppTokens.ink': '#FF102030'})
        self.assertEqual(output.count('.fontColor(StyleToken0.textPrimary)'), 1)
        self.assertIn(".fontColor('#FFFF0000')", output)

    def test_forwarded_parameter_and_import_alias(self):
        code = '''package example
import androidx.compose.runtime.Composable
import company.theme.AppTokens as Tokens
@Composable fun Label(size: TextUnit) { Text("Forwarded", fontSize = size) }
@Composable fun Page() { Label(size = Tokens.body) }
'''
        definitions = self.definitions()
        definitions['tokenMappings']['company.theme.AppTokens.body'] = definitions['tokenMappings'].pop('AppTokens.body')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'Page.kt').write_text(code)
            contract = analyze(root, {}, {'Page.kt': code})
            source = build_source_page_spec(contract, 'Page.kt', 'Page', 'page', 'default', 'test', root,
                                            style_definitions=definitions)
            helper = PageHelpers()
            self.addCleanup(helper.doCleanups)
            _, _, loaded = helper.generate_page(source, {'Tokens.body': 19})
        output = Renderer(derive_page_root(loaded), set(), {}, loaded).render()
        self.assertIn('.fontSize(StyleToken0.fontSizeBody)', output)

    def test_known_branch_selects_reference_unknown_branch_does_not_guess(self):
        body = 'Text("Hello", fontSize = if (selected) AppTokens.body else 12.sp)'
        _, output = self.generate(body, values={'selected': True, 'AppTokens.body': 19})
        self.assertIn('.fontSize(StyleToken0.fontSizeBody)', output)
        _, output = self.generate(body, values={'selected': False})
        self.assertNotIn('StyleToken', output)
        loaded, output = self.generate(body)
        self.assertNotIn('StyleToken', output)

    def test_textstyle_and_button_color_arguments(self):
        _, output = self.generate('Column { Text("Styled", style = TextStyle(fontSize = AppTokens.body, color = AppTokens.ink)); Button(colors = ButtonDefaults.buttonColors(containerColor = AppTokens.canvas)) { Text("Button") } }',
            values={'AppTokens.body': 19, 'AppTokens.ink': '#FF102030', 'AppTokens.canvas': '#FFABCDEF'})
        self.assertIn('.fontSize(StyleToken0.fontSizeBody)', output)
        self.assertIn('.fontColor(StyleToken0.textPrimary)', output)
        self.assertIn('.backgroundColor(StyleToken0.surface)', output)
        self.assertEqual(output.count('.backgroundColor(StyleToken0.surface)'), 1)

    def test_no_fixture_generation_and_refresh_preserve_mapping(self):
        from argparse import Namespace
        from generate_lanhu_source_page import generate
        from generate_arkui_page import load_lanhu_page_input
        from ui_migration.frontend.project_styles import prepare_style_definitions
        definitions = self.definitions()
        source = StyleHelpers().page(definitions, 'Text("Hello", fontSize = AppTokens.body)')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'contract.json').write_text(json.dumps(StyleHelpers().contract()))
            (root/'styles.json').write_text(json.dumps(definitions))
            refreshed = prepare_style_definitions(root/'contract.json', root/'styles.json', refresh=True)
            self.assertEqual(refreshed['tokenMappings'], definitions['tokenMappings'])
            (root/'source.json').write_text(json.dumps(source))
            generate(Namespace(source_page=root/'source.json', state_fixture=None, output_dir=root/'out',
                viewport_width_dp=360, viewport_height_dp=760, slice_scale=2, device='test'))
            loaded = load_lanhu_page_input(root/'out/version_json.json')
            (root/'source.json').unlink()
            (root/'styles.json').unlink()
            output = Renderer(derive_page_root(loaded), set(), {}, loaded).render()
        self.assertIn('.fontSize(StyleToken0.fontSizeBody)', output)

    def test_all_scalar_properties_emit_references(self):
        definitions = self.definitions()
        definitions['tokenMappings'].update({
            'AppTokens.weight': token('number', 'weight'),
            'AppTokens.family': token('string', 'family'),
            'AppTokens.line': token('dimension', 'line', 'sp', 'fp'),
            'AppTokens.spacing': token('dimension', 'spacing', 'sp', 'fp')})
        _, output = self.generate('Text("Hello", fontWeight = AppTokens.weight, fontFamily = AppTokens.family, lineHeight = AppTokens.line, letterSpacing = AppTokens.spacing)', definitions)
        for method, member in [('fontWeight', 'weight'), ('fontFamily', 'family'), ('lineHeight', 'line'), ('letterSpacing', 'spacing')]:
            self.assertIn(f'.{method}(StyleToken0.{member})', output)

    def test_unconsumed_reference_is_not_silent(self):
        loaded, _ = self.generate('Box(Modifier.size(40.dp)) {}')
        node = next(n for n in loaded['components'] if n['type'] == 'Box')
        node['source']['style_token_references'] = {'typography.font_size_sp': {
            'android': 'AppTokens.body', **self.definitions()['tokenMappings']['AppTokens.body']}}
        renderer = Renderer(derive_page_root(loaded), set(), {}, loaded)
        renderer.render()
        self.assertTrue(any('not consumed' in u['reason'] for u in renderer.unresolved))

    def test_surface_padding_does_not_paint_outer_wrapper(self):
        loaded, output = self.generate('Surface(Modifier.padding(24.dp), color = AppTokens.canvas) { Text("Content") }',
            values={'AppTokens.canvas': '#FFABCDEF'})
        self.assertEqual(output.count('.backgroundColor(StyleToken0.surface)'), 1)
        for node in loaded['components']:
            if 'surface_padding_layer' in node['source']:
                self.assertFalse(node['source'].get('style_token_references'))

    def test_composite_token_is_not_replaced_with_untransformed_reference(self):
        loaded, output = self.generate('Text("Hello", fontSize = AppTokens.body * 2)', values={'AppTokens.body':19})
        self.assertNotIn('.fontSize(StyleToken', output)
        self.assertTrue(any('composite expression' in u['reason'] for n in loaded['components'] for u in n['unresolved']))

    def test_property_unit_mismatch_is_reported(self):
        loaded, output = self.generate('Text("Hello", fontSize = AppTokens.radius)', values={'AppTokens.radius':12})
        self.assertNotIn('.fontSize(StyleToken', output)
        self.assertTrue(any('does not match' in u['reason'] for n in loaded['components'] for u in n['unresolved']))

    def test_modules_with_same_export_name_get_distinct_import_aliases(self):
        definitions = self.definitions()
        definitions['tokenMappings']['AppTokens.ink']['target']['module'] = '@company/palette'
        _, output = self.generate('Text("Hello", fontSize = AppTokens.body, color = AppTokens.ink)', definitions)
        self.assertIn("import { AppTokens as StyleToken0 } from '@company/design';", output)
        self.assertIn("import { AppTokens as StyleToken1 } from '@company/palette';", output)
        self.assertIn('.fontSize(StyleToken0.fontSizeBody)', output)
        self.assertIn('.fontColor(StyleToken1.textPrimary)', output)


if __name__ == '__main__':
    unittest.main()
