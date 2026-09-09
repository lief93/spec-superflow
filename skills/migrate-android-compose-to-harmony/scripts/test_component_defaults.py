import copy
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from generate_lanhu_source_page import project_source_page, generate
from generate_arkui_page import Renderer, derive_page_root, load_lanhu_page_input
from test_project_style_definitions import ProjectStyleDefinitionsTest as Helpers
from test_partial_page_generation import PartialPageGenerationTest
from ui_migration.frontend.project_styles import build_style_definitions, prepare_style_definitions
from ui_migration.frontend.component_defaults import validate_component_defaults


class ComponentDefaultsTest(unittest.TestCase):
    def page(self, body, overrides):
        helper = Helpers()
        definitions = build_style_definitions(helper.contract())
        definitions['componentDefaults'] = overrides
        return helper.page(definitions, body)

    def projected(self, page, values=None):
        result, _ = project_source_page(page, {'schema': 'android-to-harmony.page-state-fixture.v1',
            'page': page['page'], 'values': values or {}, 'symbols': {}}, allow_unresolved=True)
        return result

    def test_red_blue_projects_and_explicit_transparency(self):
        for color in ('#FFFF0000', '#FF0000FF'):
            source = self.page('Column { Button { Text("Default") }; Button(colors = ButtonDefaults.buttonColors(containerColor = Color.Transparent)) { Text("Explicit") } }',
                               {'Button': {'surface.background': {'value': color}}})
            before = copy.deepcopy(source)
            nodes = [n for n in self.projected(source)['components'] if n['type'] == 'Button']
            self.assertEqual(nodes[0]['style']['surface']['background']['color'], color)
            self.assertEqual(nodes[1]['style']['surface']['background']['color'], '#00000000')
            self.assertEqual(source, before)

    def test_theme_reference_and_state_use_shared_evaluator(self):
        page = self.page('Button(enabled = false) { Text("Disabled") }', {'Button': {
            'surface.background': {'expression': 'if (componentState.enabled) MaterialTheme.colorScheme.primary else Color(0xFF778899)'}}})
        node = next(n for n in self.projected(page)['components'] if n['type'] == 'Button')
        self.assertEqual(node['style']['surface']['background']['color'], '#FF778899')
        page = self.page('Button { Text("Theme") }', {'Button': {
            'surface.background': {'expression': 'MaterialTheme.colorScheme.primary'}}})
        node = next(n for n in self.projected(page)['components'] if n['type'] == 'Button')
        self.assertEqual(node['style']['surface']['background']['color'], '#FF123456')

    def test_unknown_explicit_setting_is_never_overwritten(self):
        page = self.page('Surface(color = unknownColor) {}', {'Surface': {
            'surface.background': {'value': '#FFFF0000'}}})
        node = next(n for n in self.projected(page)['components'] if n['type'] == 'Surface')
        self.assertIsNone(node['style']['surface']['background'])
        self.assertTrue(any(u['path'] == 'style.surface.background' for u in node['unresolved']))

    def test_unknown_project_setting_does_not_fall_back_to_framework(self):
        page = self.page('Surface {}', {'Surface': {'surface.background': {'expression': 'missingPalette'}}})
        node = next(n for n in self.projected(page)['components'] if n['type'] == 'Surface')
        self.assertIsNone(node['style']['surface']['background'])
        self.assertTrue(any('project component default' in u['reason'] for u in node['unresolved']))

    def test_zero_radius_and_explicit_text_size_win(self):
        page = self.page('Column { Surface(shape = RoundedCornerShape(0.dp)) {}; Text("Size", fontSize = 12.sp); Text("Default") }', {
            'Surface': {'surface.corner_radius_dp': {'value': 8}},
            'Text': {'typography.font_size_sp': {'value': 20}}})
        nodes = self.projected(page)['components']
        surface = next(n for n in nodes if n['type'] == 'Surface')
        self.assertEqual(set(surface['style']['surface']['corner_radius_dp'].values()), {0})
        self.assertEqual([n['style']['typography']['font_size_sp'] for n in nodes if n['type'] == 'Text'], [12, 20])

    def test_refresh_preserves_project_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract, output = root/'contract.json', root/'styles.json'
            contract.write_text(json.dumps(Helpers().contract()))
            definitions = prepare_style_definitions(contract, output)
            definitions['componentDefaults'] = {'Button': {'surface.background': {'value': '#FFFF0000'}}}
            output.write_text(json.dumps(definitions))
            self.assertEqual(prepare_style_definitions(contract, output, refresh=True)['componentDefaults'], definitions['componentDefaults'])

    def test_invalid_rules_fail_instead_of_silently_ignored(self):
        for spec in ({'bad': {'value': 2}}, {'surface.background': {'value': None}},
                     {'surface.background': {'value': '#FFFF0000', 'expression': 'color'}},
                     {'typography.font_size_sp': {'value': -2}}):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                validate_component_defaults({'Button': spec})

    def test_single_json_reaches_generated_arkui(self):
        page = self.page('Button { Text("Default") }', {'Button': {'surface.background': {'value': '#FFFF0000'}}})
        helper = PartialPageGenerationTest()
        self.addCleanup(helper.doCleanups)
        _, _, loaded = helper.generate_page(page)
        output = Renderer(derive_page_root(loaded), set(), {}, loaded).render()
        self.assertIn(".backgroundColor('#FFFF0000')", output)

    def test_no_fixture_cli_still_applies_overrides(self):
        page = self.page('Surface {}', {'Surface': {'surface.background': {'value': '#FF0000FF'}}})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'source.json'
            source.write_text(json.dumps(page))
            generate(Namespace(source_page=source, state_fixture=None, output_dir=root/'out',
                viewport_width_dp=360, viewport_height_dp=760, slice_scale=2, device='test'))
            loaded = load_lanhu_page_input(root/'out/version_json.json')
            output = Renderer(derive_page_root(loaded), set(), {}, loaded).render()
            self.assertIn(".backgroundColor('#FF0000FF')", output)

    def test_no_override_retains_framework_default(self):
        source = self.page('Surface {}', {})
        node = next(n for n in self.projected(source)['components'] if n['type'] == 'Surface')
        self.assertEqual(node['style']['surface']['background']['color'], '#FFABCDEF')


if __name__ == '__main__':
    unittest.main()
