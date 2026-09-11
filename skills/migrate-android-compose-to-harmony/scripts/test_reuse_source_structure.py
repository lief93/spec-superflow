from pathlib import Path
import unittest

import test_component_reuse as reuse
from ui_migration.arkui.source_modules import render_modules


EXTENSION = '''from ui_migration.frontend.component_reuse import ComponentAdapter
ADAPTERS = []
COMPONENT_ADAPTERS = [
    ComponentAdapter('shell', 'example.Shell', './Shell', 'Shell', slots={'content':'content'}),
    ComponentAdapter('panel', 'example.Panel', './Panel', 'Panel', slots={'content':'content'}),
]
'''
DECLARATIONS = '''
@Composable fun Shell(content: @Composable () -> Unit) { Column { content() } }
@Composable fun Panel(content: @Composable () -> Unit) { Column { content() } }
'''


class ReuseSourceStructureTest(unittest.TestCase):
    def generate(self, body, declarations=DECLARATIONS, extension=EXTENSION):
        _, code, result, renderer = reuse.ComponentReuseTest.generate(self, body, declarations, extension)
        files, report = render_modules(code, renderer.root, renderer.business_components,
            Path('/tmp/reuse-structure'), Path('/tmp/reuse-structure/Page.ets'))
        return '\n'.join(value.decode() for value in files.values()), result, report

    def test_nested_reuse_keeps_calls_without_fact_props(self):
        code, result, _ = self.generate('Shell { Panel { Text("Body", color = Color.Black) } }')
        self.assertIn('import { Shell }', code)
        self.assertIn('import { Panel }', code)
        self.assertIn('Shell({ content: () => { this.ShellContent() } })', code)
        self.assertRegex(code, r'ShellContent\(\) \{\s+Panel\(\{ content: \(\) => \{ this.PanelContent\(\) \} \}\)')
        self.assertRegex(code, r"PanelContent\(\) \{\s+Text\('Body'\)")
        self.assertNotIn('Reused', code)
        self.assertNotIn('renderShellContent', code)
        self.assertNotIn('renderPanelContent', code)
        self.assertNotIn('Props', code)
        self.assertNotIn('BusinessSlot', code)
        self.assertNotIn('export function ShellContent', code)
        self.assertNotIn('migrationContext', code)
        self.assertEqual(code.count("Text('Body')"), 1)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_external_parameter_is_forwarded_without_slot_props(self):
        code, _, _ = self.generate('Outer("Body")', DECLARATIONS + '''
@Composable fun Outer(title: String) { Shell { Panel { Text(title, color = Color.Black) } } }
''')
        self.assertIn('export function Outer(migrationContext: MigrationRenderContext, title: string)', code)
        self.assertIn('Text(title)', code)
        self.assertIn('ShellContent(title)', code)
        self.assertIn('PanelContent(title)', code)
        self.assertNotIn('Props', code)
        self.assertIn('migrationContext.ShellContent(title)', code)
        self.assertIn('this.PanelContent(title)', code)
        self.assertNotIn('renderShellContent', code)
        self.assertNotIn('renderPanelContent', code)

    def test_native_control_name_collision_keeps_alias(self):
        code, _, _ = self.generate('Column { Shell { Text("Slot", color = Color.Black) }; Text("Native", color = Color.Black) }',
            extension=EXTENSION.replace("'./Shell', 'Shell'", "'./Shell', 'Text'"))
        self.assertIn('import { Text as ReusedText }', code)
        self.assertIn('ReusedText(', code)
        self.assertIn("Text('Native')", code)

    def test_source_component_inside_reused_slot_keeps_its_dispatcher(self):
        code, result, _ = self.generate('Shell { Local { Text("Body", color = Color.Black) } }', DECLARATIONS + '''
@Composable fun Local(content: @Composable () -> Unit) { Column { content() } }
''')
        self.assertIn('Shell({ content: () => { this.ShellContent() } })', code)
        self.assertIn('export function Local(', code)
        self.assertIn('renderBusinessSlot(', code)
        self.assertIn('export interface BusinessSlot', code)
        self.assertIn('kind: 0', code)
        self.assertIn('slot.kind === 0', code)
        self.assertNotIn('slot.kind === 1', code)
        self.assertEqual(code.count('Text('), 1)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_source_function_in_separate_file_keeps_slot_receiver(self):
        _, code, _, renderer = reuse.ComponentReuseTest.generate(self, 'Outer("Body")', DECLARATIONS + '''
@Composable fun Outer(title: String) { Shell { Text(title, color = Color.Black) } }
''', EXTENSION)
        definition = next(d for d in renderer.business_components.definitions.values() if d['type'] == 'Outer')
        definition['identity']['source'] = 'ui/Outer.kt'
        files, _ = render_modules(code, renderer.root, renderer.business_components,
            Path('/tmp/reuse-structure'), Path('/tmp/reuse-structure/Page.ets'))
        page = files[Path('/tmp/reuse-structure/Page.ets')].decode()
        outer = files[Path('/tmp/reuse-structure/Outer.ets')].decode()
        self.assertIn('Outer(this, "Body")', page)
        self.assertIn('ShellContent(title: string)', page)
        self.assertIn('Text(title)', page)
        self.assertIn('export function Outer(migrationContext: MigrationRenderContext, title: string)', outer)
        self.assertIn('migrationContext.ShellContent(title)', outer)
        self.assertNotIn('Props', outer)
        self.assertNotIn('Text(', outer)

    def test_two_exports_with_same_name_do_not_merge(self):
        code, _, _ = self.generate('Shell { Panel { Text("Body", color = Color.Black) } }',
            extension=EXTENSION.replace("'./Panel', 'Panel'", "'./Panel', 'Shell'"))
        self.assertIn('import { Shell } from "./Shell"', code)
        self.assertIn('import { Shell as ReusedShell2 } from "./Panel"', code)
        self.assertIn('ReusedShell2(', code)

    def test_root_component_collision_keeps_alias(self):
        code, _, _ = self.generate('Shell { Text("Body", color = Color.Black) }',
            extension=EXTENSION.replace("'./Shell', 'Shell'", "'./Shell', 'Page'"))
        self.assertIn('import { Page as ReusedPage }', code)
        self.assertIn('export struct Page', code)
        self.assertIn('ReusedPage({ content:', code)

    def test_source_parameter_name_is_not_shadowed_by_import(self):
        code, _, _ = self.generate('Outer("Body")', DECLARATIONS + '''
@Composable fun Outer(Shell: String) { Shell { Text(Shell, color = Color.Black) } }
''')
        self.assertIn('import { Shell as ReusedShell }', code)
        self.assertIn('export function Outer(migrationContext: MigrationRenderContext, Shell: string)', code)
        self.assertIn('Text(Shell)', code)

    def test_import_alias_spelling_in_properties_and_strings_is_preserved(self):
        _, code, _, renderer = reuse.ComponentReuseTest.generate(self,
            'Shell { Text("ReusedShell", color = Color.Black) }', DECLARATIONS, EXTENSION)
        code = code.replace('build() {', '''private data: Details = { ReusedShell: 'Value' }
  build() {''')
        code += '\ninterface Details { ReusedShell: string }\n'
        files, _ = render_modules(code, renderer.root, renderer.business_components,
            Path('/tmp/reuse-structure'), Path('/tmp/reuse-structure/Page.ets'))
        output = '\n'.join(value.decode() for value in files.values())
        self.assertIn('import { Shell }', output)
        self.assertIn("Text('ReusedShell')", output)
        self.assertIn("{ ReusedShell: 'Value' }", output)
        self.assertIn('ReusedShell: string', output)
