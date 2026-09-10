import hashlib
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from analyze_compose_project import analyze
from real_page_pipeline import build_source_page_spec
from generate_lanhu_source_page import generate
from generate_arkui_page import Renderer, derive_page_root, load_lanhu_page_input
import test_project_style_definitions as style_helpers
from ui_migration.frontend.project_styles import build_style_definitions
from ui_migration.contracts.consumption import build_target_phase_consumption_gate
from ui_migration.contracts.style_tokens import validate_token_reference


EXTENSION = '''from ui_migration.frontend.api_adapters.keyed_resources import KeyedResourceAdapter

class Colors(KeyedResourceAdapter):
    def harmony_target(self, key, arguments):
        return {"module":"./CompanyResources", "export":"AppColors", "member":"resolve", "arguments":[key]}

class Copy(KeyedResourceAdapter):
    def harmony_target(self, key, arguments):
        return {"module":"./CompanyResources", "export":"AppCopy", "member":"read", "arguments":[key, arguments["name"]]}

class Sizes(KeyedResourceAdapter):
    def harmony_target(self, key, arguments):
        return {"module":"./CompanyResources", "export":"AppSizes", "member":"font", "arguments":[key]}

ADAPTERS = [Colors("company.color", ("company.Colors.get",), "color").declaration(),
            Copy("company.copy", ("company.Copy.text",), "string", parameters=("name",)).declaration(),
            Sizes("company.size", ("company.Sizes.get",), "dimension", source_unit="sp", target_unit="fp").declaration()]
'''


class KeyedResourcesTest(unittest.TestCase):
    def generate(self, body, declarations='', extension=EXTENSION, *, extra_files=None, source_imports='', harmony_files=None,
                 preserve_component_ui_states=False, token_mappings=None):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        source = '''package example
import androidx.compose.runtime.Composable
import company.Colors as Palette
import company.Copy
''' + source_imports + '\n@Composable fun Page() { ' + body + ' }\n' + declarations
        files = {'Page.kt': source, **(extra_files or {})}
        for name, content in files.items():
            (root/name).write_text(content)
        contract = analyze(root, {}, files)
        styles = build_style_definitions(style_helpers.ProjectStyleDefinitionsTest().contract())
        if token_mappings is not None:
            styles['tokenMappings'] = token_mappings
        page = build_source_page_spec(contract, 'Page.kt', 'Page', 'page', 'default', 'test', root,
                                      style_definitions=styles)
        (root/'source.json').write_text(json.dumps(page))
        (root/'adapter.py').write_text(extension)
        (root/'adapters.json').write_text(json.dumps({'schema':'ui-migration.api-adapters.v1', 'modules':[
            {'path':'adapter.py', 'sha256':hashlib.sha256(extension.encode()).hexdigest()}]}))
        if harmony_files is not None:
            for name, content in harmony_files.items():
                path = root/'harmony/entry/src/main/ets'/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
        result = generate(Namespace(source_page=root/'source.json', state_fixture=None, output_dir=root/'out',
            viewport_width_dp=360, viewport_height_dp=760, slice_scale=2, device='test', api_adapters=root/'adapters.json',
            harmony_target=root/'harmony' if harmony_files is not None else None,
            preserve_component_ui_states=preserve_component_ui_states))
        if harmony_files is not None:
            result['discovery'] = json.loads((root/'out/component-discovery.json').read_text())
            import shutil
            if (root/'harmony').exists():
                shutil.rmtree(root/'harmony')
        loaded = load_lanhu_page_input(root/'out/version_json.json')
        # The backend can run after the source and executable extension are gone.
        (root/'source.json').unlink()
        (root/'adapter.py').unlink()
        renderer = Renderer(derive_page_root(loaded), set(), {}, loaded)
        output = renderer.render()
        renderer.test_phase_gate = build_target_phase_consumption_gate(loaded,
            renderer.android_page_processed_component_ids, renderer.android_page_processed_call_ids,
            renderer.android_page_applied_paths, renderer.android_page_applied_component_paths,
            getattr(renderer, 'android_page_layout_decisions', []))
        return loaded, output, result, renderer

    def test_color_key_survives_without_hex_value(self):
        loaded, code, result, renderer = self.generate('Text("Hello", color = Palette.get("text.primary"))')
        node = next(n for n in loaded['components'] if n['type'] == 'Text')
        reference = node['source']['style_token_references']['typography.color']
        self.assertEqual(reference['key'], 'text.primary')
        self.assertEqual(reference['android'], 'company.Colors.get')
        self.assertIsNone(node['style']['typography']['color'])
        self.assertIn(".fontColor(StyleToken0.resolve('text.primary'))", code)
        self.assertFalse(any(u.get('path') == 'style.typography.color' for u in result['unresolved']))
        self.assertFalse(any(u.get('path') == 'style.typography.color' for u in renderer.unresolved))
        self.assertEqual(renderer.test_phase_gate['verdict'], 'pass', renderer.test_phase_gate['failures'])
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_background_is_target_call_not_a_literal(self):
        loaded, code, result, _ = self.generate('Box(Modifier.size(80.dp).background(Palette.get("surface.primary"))) {}')
        self.assertIn(".backgroundColor(StyleToken0.resolve('surface.primary'))", code)
        box = next(n for n in loaded['components'] if n['type'] == 'Box')
        self.assertIsNone(box['style']['surface']['background'])
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_text_key_and_format_arguments_are_not_baked(self):
        loaded, code, result, renderer = self.generate('Text(Copy.text(name = "Alice", key = "greeting"), color = Color.Black)')
        node = next(n for n in loaded['components'] if n['type'] == 'Text')
        self.assertEqual(node['source']['style_token_references']['content.text']['key'], 'greeting')
        self.assertIsNone(node['style']['content']['text'])
        self.assertIn("Text(StyleToken0.read('greeting', 'Alice'))", code)
        self.assertFalse(any(u.get('path') == 'style.content.text' for u in renderer.unresolved))
        self.assertEqual(renderer.test_phase_gate['verdict'], 'pass', renderer.test_phase_gate['failures'])
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_forwarded_key_and_business_component(self):
        _, code, result, _ = self.generate('Label("text.primary")', '''
@Composable fun Label(key: String) { Text("Hello", color = Palette.get(key)) }
''')
        self.assertIn("resolve('text.primary')", code)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_unselected_branch_does_not_emit_reference(self):
        _, code, _, _ = self.generate('Text("Hello", color = if (false) Palette.get("unused") else Color.Red)')
        self.assertNotIn('resolve(', code)
        self.assertIn(".fontColor('#FFFF0000')", code)

    def test_unknown_key_is_not_replaced_or_dropped(self):
        loaded, code, result, _ = self.generate('Text("Hello", color = Palette.get(missingKey))')
        self.assertIn("Text('Hello')", code)
        self.assertNotIn('resolve(', code)
        self.assertFalse(result['generation_complete'])
        self.assertTrue(any(u.get('path') == 'style.typography.color' for u in result['unresolved']))

    def test_dimension_reference_keeps_units_without_literal(self):
        loaded, code, result, renderer = self.generate('Text("Hello", fontSize = company.Sizes.get("body"), color = Color.Black)')
        self.assertIn(".fontSize(StyleToken0.font('body'))", code)
        self.assertIsNone(loaded['components'][0]['style']['typography']['font_size_sp'])
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertEqual(renderer.test_phase_gate['verdict'], 'pass', renderer.test_phase_gate['failures'])

    def test_adapter_can_reject_key_without_inventing_a_fallback(self):
        extension = EXTENSION.replace('return {"module":"./CompanyResources", "export":"AppColors", "member":"resolve", "arguments":[key]}', 'return None')
        _, code, result, _ = self.generate('Text("Hello", color = Palette.get("not.available"))', extension=extension)
        self.assertNotIn('resolve(', code)
        self.assertFalse(result['generation_complete'])

    def test_unknown_format_argument_and_extra_arguments_are_not_discarded(self):
        for call in ('Copy.text("greeting", missingName)', 'Palette.get("text.primary", alpha = 0.5f)'):
            argument = 'text' if call.startswith('Copy') else 'color'
            body = f'Text({call}, color = Color.Black)' if argument == 'text' else f'Text("Hello", color = {call})'
            _, code, result, _ = self.generate(body)
            self.assertFalse(result['generation_complete'])
            self.assertNotIn('StyleToken', code)

    def test_missing_adapter_keeps_unresolved(self):
        _, code, result, _ = self.generate('Text("Hello", color = Palette.get("text.primary"))', extension='ADAPTERS = []')
        self.assertNotIn('resolve(', code)
        self.assertFalse(result['generation_complete'])

    def test_wrong_kind_cannot_satisfy_property(self):
        _, code, result, _ = self.generate('Text("Hello", fontSize = Palette.get("text.primary"))')
        self.assertNotIn('.fontSize(StyleToken', code)
        self.assertTrue(any('does not match' in u.get('reason', '') for u in result['unresolved']))

    def test_transformed_reference_does_not_lose_operation(self):
        _, code, result, _ = self.generate('Text("Hello", color = Palette.get("text.primary").copy(alpha = 0.5f))')
        self.assertNotIn('resolve(', code)
        self.assertFalse(result['generation_complete'])

    def test_unsafe_code_in_member_is_rejected_but_key_is_escaped(self):
        reference = {'android':'Colors.get', 'key':'surface.primary', 'kind':'color',
            'target':{'module':'./Colors', 'export':'Colors', 'member':'resolve', 'arguments':['x\' ); bad()']}}
        validate_token_reference(reference, 'surface.background')
        reference['target']['member'] = 'resolve(); bad'
        with self.assertRaises(ValueError):
            validate_token_reference(reference, 'surface.background')

    def test_valid_reference_does_not_mask_unrelated_missing_size(self):
        _, _, result, _ = self.generate('Text("Hello", color = Palette.get("text.primary"), fontSize = unknownSize)')
        paths = [u.get('path') for u in result['unresolved']]
        self.assertNotIn('style.typography.color', paths)
        self.assertIn('style.typography.font_size_sp', paths)


if __name__ == '__main__':
    unittest.main()
