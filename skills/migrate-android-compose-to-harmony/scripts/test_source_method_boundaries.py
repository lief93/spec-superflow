from pathlib import Path
import unittest

import test_keyed_resources as helpers
from ui_migration.arkui.source_modules import render_modules


EXTENSION = '''from ui_migration.frontend.component_reuse import ComponentAdapter
ADAPTERS = []
COMPONENT_ADAPTERS = [
    ComponentAdapter('shell', 'example.Shell', '../components/Shell', 'Shell', slots={'content':'content'}),
    ComponentAdapter('panel', 'example.Panel', '../components/Panel', 'Panel', slots={'content':'content'}),
]
'''
DECLARATIONS = '''
@Composable fun Shell(content: @Composable () -> Unit) { Column { content() } }
@Composable fun Panel(content: @Composable () -> Unit) { Column { content() } }
'''


def target(name, extra=''):
    return ('@Component\nexport struct ' + name + ' {\n'
            '@BuilderParam content: () => void\n' + extra + '\n'
            'build() { Column() { this.content() } }\n}')


class SourceMethodBoundariesTest(unittest.TestCase):
    def generate(self, body, declarations=DECLARATIONS, files=None, extension=EXTENSION):
        page, code, result, renderer = helpers.KeyedResourcesTest.generate(self, body,
            declarations, extension, harmony_files=files if files is not None else {
                'components/Shell.ets':target('Shell'), 'components/Panel.ets':target('Panel')})
        files, report = render_modules(code, renderer.root, renderer.business_components,
            Path('/tmp/method-boundaries'), Path('/tmp/method-boundaries/Page.ets'))
        return '\n'.join(v.decode() for v in files.values()), page, result, report

    def test_verified_single_slot_keeps_nested_ui_inline(self):
        code, page, result, report = self.generate('Shell { Panel { Text("Body", color = Color.Black) } }')
        self.assertRegex(code, r'Shell\(\{\s*\}\)\s*\{\s*Panel\(\{\s*\}\)\s*\{\s*Text\(\x27Body\x27\)')
        self.assertNotIn('ShellContent', code)
        self.assertNotIn('PanelContent', code)
        self.assertNotIn('renderAndroidPageSnapshot', code)
        self.assertNotIn('Props', code)
        self.assertEqual(code.count("Text('Body')"), 1)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        reuse = next(c for c in page['components'] if c['type'] == 'Shell')['source']['component_reuse']
        self.assertEqual(reuse['target_content_slot'], 'content')
        self.assertEqual(report['slot_lowerings'][0]['representation'], 'trailing-content')

    def test_source_method_and_parameter_stay_at_source_boundary(self):
        code, _, _, _ = self.generate('Outer("Body")', DECLARATIONS + '''
@Composable fun Outer(title: String) { Shell { Panel { Text(title, color = Color.Black) } } }
''')
        self.assertIn('export function Outer(title: string)', code)
        self.assertIn('Text(title)', code)
        self.assertNotIn('migrationContext', code)
        self.assertNotIn('Props', code)
        self.assertNotIn('ShellContent(', code)
        self.assertNotIn('PanelContent(', code)

    def test_only_one_mapped_slot_does_not_hide_second_target_slot(self):
        code, page, _, report = self.generate('Shell { Text("Body", color = Color.Black) }', files={
            'components/Shell.ets':target('Shell', '@BuilderParam header: () => void = () => {}')})
        self.assertIn('content: () => { this.ShellContent() }', code)
        reuse = next(c for c in page['components'] if c['type'] == 'Shell')['source']['component_reuse']
        self.assertNotIn('target_content_slot', reuse)
        self.assertEqual(report['slot_lowerings'][0]['representation'], 'local-builder')
        self.assertIn('target', report['slot_lowerings'][0]['reason'])

    def test_uninspected_package_export_does_not_infer_inline_support(self):
        code, _, _, _ = self.generate('Shell { Text("Body", color = Color.Black) }',
            extension=EXTENSION.replace('../components/Shell', '@company/ui'))
        self.assertIn('content: () => { this.ShellContent() }', code)

    def test_private_target_slot_also_disables_trailing_content(self):
        code, page, _, _ = self.generate('Shell { Text("Body", color = Color.Black) }', files={
            'components/Shell.ets':target('Shell', '@BuilderParam private header: () => void = () => {}')})
        self.assertIn('content: () => { this.ShellContent() }', code)

    def test_parameterized_target_slot_is_not_a_trailing_slot(self):
        code, _, _, _ = self.generate('Shell { Text("Body", color = Color.Black) }', files={
            'components/Shell.ets':target('Shell').replace('content: () => void', 'content: (index: number) => void')})
        self.assertIn('content: () => { this.ShellContent() }', code)

    def test_entry_ui_is_in_build_without_synthetic_method(self):
        code, _, _, _ = self.generate('Text("Body", color = Color.Black)')
        self.assertNotIn('renderAndroidPageSnapshot', code)
        self.assertRegex(code, r'build\(\)\s*\{[\s\S]*Text\(\x27Body\x27\)')

    def test_style_import_preserves_export_name_and_calls(self):
        _, code, _, renderer = helpers.KeyedResourcesTest.generate(self,
            'Text(Copy.text("body", "Ada"), color = Color.Black)')
        files, _ = render_modules(code, renderer.root, renderer.business_components,
            Path('/tmp/method-boundaries'), Path('/tmp/method-boundaries/Page.ets'))
        code = '\n'.join(v.decode() for v in files.values())
        self.assertIn('import { AppCopy }', code)
        self.assertIn("AppCopy.read('body', 'Ada')", code)
        self.assertNotIn('StyleToken0', code)


if __name__ == '__main__':
    unittest.main()
