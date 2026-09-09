import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from analyze_compose_project import analyze, extract_compose_theme_tokens
from real_page_pipeline import build_source_page_spec
from generate_lanhu_source_page import project_source_page
from ui_migration.frontend.project_styles import (
    build_style_definitions, load_style_definitions, prepare_style_definitions,
)


ROOT = 'app/src/main/java/example/Page.kt'
THEME = '''
val palette = lightColorScheme(primary = Color(0xFF123456), surface = Color(0xFFABCDEF))
val typography = Typography(titleMedium = TextStyle(fontSize = 19.sp))
@Composable fun Theme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = palette, typography = typography, content = content)
}
'''


class ProjectStyleDefinitionsTest(unittest.TestCase):
    def contract(self):
        return {'ui': {'compose_theme_token_inventory': extract_compose_theme_tokens({'Theme.kt': THEME})}}

    def page(self, definitions, body='Surface { Text("Hello") }'):
        code = 'package example\nimport androidx.compose.runtime.Composable\n@Composable\nfun Page() {\n' + body + '\n}'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / ROOT
            source.parent.mkdir(parents=True)
            source.write_text(code)
            contract = analyze(root, {}, {ROOT: code})
            return build_source_page_spec(contract, ROOT, 'Page', 'page', 'default', 'test', root,
                                          style_definitions=definitions)

    def test_extracts_colors_typography_and_source_providers(self):
        result = build_style_definitions(self.contract())
        self.assertEqual(result['theme']['colors']['primary'], '#FF123456')
        self.assertIn('19.sp', result['theme']['textStyles']['titleMedium']['expression'])
        self.assertTrue(result['sourceInventory']['theme_applications'])
        self.assertNotIn('sha256', result)

    def test_existing_file_is_reused_without_reading_contract_or_extracting(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'styles.json'
            contract = Path(directory) / 'contract.json'
            contract.write_text(json.dumps(self.contract()))
            first = prepare_style_definitions(contract, output)
            before = output.read_bytes()
            contract.unlink()
            with patch('ui_migration.frontend.project_styles.build_style_definitions', side_effect=AssertionError('rescanned')):
                self.assertEqual(prepare_style_definitions(contract, output), first)
            self.assertEqual(output.read_bytes(), before)

    def test_refresh_explicitly_replaces_old_styles(self):
        with tempfile.TemporaryDirectory() as directory:
            output, contract = Path(directory) / 'styles.json', Path(directory) / 'contract.json'
            contract.write_text(json.dumps(self.contract()))
            first = prepare_style_definitions(contract, output)
            contract.write_text(json.dumps(self.contract()).replace('FF123456', 'FF654321'))
            self.assertEqual(prepare_style_definitions(contract, output), first)
            self.assertEqual(prepare_style_definitions(contract, output, refresh=True)['theme']['colors']['primary'], '#FF654321')

    def test_malformed_cache_fails_without_silent_rebuild(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'styles.json'
            output.write_text('{}')
            with self.assertRaises(ValueError):
                load_style_definitions(output)

    def test_cached_theme_drives_source_and_fixed_state_without_fresh_theme(self):
        definitions = build_style_definitions(self.contract())
        source = self.page(definitions)
        self.assertEqual(source['style_definitions'], definitions)
        surface = next(n for n in source['components'] if n['type'] == 'Surface')
        self.assertEqual(surface['style']['surface']['background']['color'], '#FFABCDEF')
        projected, _ = project_source_page(source, {'schema': 'android-to-harmony.page-state-fixture.v1',
            'page': source['page'], 'values': {}, 'symbols': {}}, allow_unresolved=True)
        surface = next(n for n in projected['components'] if n['type'] == 'Surface')
        self.assertEqual(surface['style']['surface']['background']['color'], '#FFABCDEF')
        self.assertEqual(definitions, source['style_definitions'])

    def test_explicit_color_and_transparency_override_global_default(self):
        definitions = build_style_definitions(self.contract())
        for expression, expected in [('Color.Transparent', '#00000000'), ('Color(0xFF102030)', '#FF102030')]:
            with self.subTest(expression=expression):
                page = self.page(definitions, 'Surface(color = ' + expression + ') {}')
                surface = next(n for n in page['components'] if n['type'] == 'Surface')
                self.assertEqual(surface['style']['surface']['background']['color'], expected)

    def test_unknown_explicit_color_is_not_replaced_with_global_default(self):
        page = self.page(build_style_definitions(self.contract()), 'Surface(color = unknownColor) {}')
        surface = next(n for n in page['components'] if n['type'] == 'Surface')
        self.assertIsNone(surface['style']['surface']['background'])
        self.assertTrue(any(u['path'] == 'style.surface.background' for u in surface['unresolved']))

    def test_plain_box_null_does_not_acquire_surface_background(self):
        page = self.page(build_style_definitions(self.contract()), 'Box {}')
        self.assertIsNone(next(n for n in page['components'] if n['type'] == 'Box')['style']['surface']['background'])

    def test_missing_theme_stays_unknown(self):
        page = self.page(build_style_definitions({'ui': {}}))
        self.assertIsNone(next(n for n in page['components'] if n['type'] == 'Surface')['style']['surface']['background'])

    def test_single_lanhu_json_embeds_styles_without_external_dependency(self):
        source = self.page(build_style_definitions(self.contract()), 'Surface {}')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'source.json'
            path.write_text(json.dumps(source))
            command = [sys.executable, str(Path(__file__).with_name('generate_lanhu_source_page.py')),
                       '--source-page', str(path), '--output-dir', str(root / 'page'),
                       '--viewport-width-dp', '360', '--viewport-height-dp', '800']
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            from ui_migration.contracts.lanhu_storage import unpack_lanhu_document
            version = unpack_lanhu_document(json.loads((root / 'page/version_json.json').read_text()))
            self.assertEqual(version['meta']['migration']['styleDefinitions'], source['style_definitions'])


if __name__ == '__main__':
    unittest.main()
