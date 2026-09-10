"""Source file boundaries through the actual parser and page CLI."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_page_commands
from test_business_components import compile_page
from ui_migration.arkui.source_modules import render_modules, source_file
from ui_migration.arkui.source_modules import page_file, validate_outputs
from ui_migration.common import ArkUIPageError
from ui_migration.common import MANIFEST_SCHEMA


class SourceModulesTest(unittest.TestCase):
    def test_module_write_failure_restores_complete_old_output_set(self):
        from generate_harmony_theme_resources import commit_payloads
        import os
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            first, second, obsolete = (root/name for name in ('A.ets', 'B.ets', 'Old.ets'))
            for path in (first, second, obsolete):
                path.write_bytes(b'old')
            replace = os.replace
            def fail_write(source, destination):
                if destination == second and Path(source).name != '.B.ets.compose-theme-backup':
                    raise OSError('write failure')
                return replace(source, destination)
            with patch('generate_harmony_theme_resources.os.replace', fail_write), self.assertRaisesRegex(OSError, 'write failure'):
                commit_payloads({first:b'new-a', second:b'new-b'}, {obsolete})
            self.assertEqual([path.read_bytes() for path in (first, second, obsolete)], [b'old']*3)

    def test_backup_cleanup_failure_does_not_remove_committed_modules(self):
        from generate_harmony_theme_resources import commit_payloads
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            first, second, obsolete = (root/name for name in ('A.ets', 'B.ets', 'Old.ets'))
            for path in (first, second, obsolete):
                path.write_bytes(b'old')
            unlink = Path.unlink
            def fail_cleanup(path, *args, **kwargs):
                if path.name == '.B.ets.compose-theme-backup':
                    raise OSError('cleanup failure')
                return unlink(path, *args, **kwargs)
            with patch.object(Path, 'unlink', fail_cleanup), self.assertRaisesRegex(OSError, 'cleanup failure'):
                commit_payloads({first:b'new-a', second:b'new-b'}, {obsolete})
            self.assertEqual(first.read_bytes(), b'new-a')
            self.assertEqual(second.read_bytes(), b'new-b')
            self.assertFalse(obsolete.exists())
            self.assertEqual((root/'.B.ets.compose-theme-backup').read_bytes(), b'old')

    def test_names_arguments_and_strings_are_preserved(self):
        _, _, _, renderer, code = compile_page('''
@Composable fun Page() { Column { Caption("this.Caption( stays text"); Caption("Two") } }
@Composable fun Caption(label: String) { Text(label) }
''')
        files, report = render_modules(code, renderer.root, renderer.business_components,
            Path('/tmp/generated'), Path('/tmp/generated/Page.ets'), 'test')
        output = files[Path('/tmp/generated/Page.ets')].decode()
        self.assertIn('export function Caption(label: string)', output)
        self.assertIn('Caption("this.Caption( stays text")', output)
        self.assertIn('Caption("Two")', output)
        self.assertEqual(output.count('Text('), 1)
        self.assertNotIn('migrationContext', output)
        self.assertEqual(report['definitions'][0]['source'], 'Page.kt')

    def test_runtime_context_keeps_state_and_helpers_typed(self):
        _, _, _, renderer, code = compile_page('''
@Composable fun Page() { Shell { Text("Body") } }
@Composable fun Shell(content: @Composable () -> Unit) { Scaffold(topBar = { Text("Title") }) { content() } }
''')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files, report = render_modules(code, renderer.root, renderer.business_components, root, root/'Page.ets', 'test')
            combined = '\n'.join(data.decode() for data in files.values())
            self.assertIsNotNone(report['context_parameter'])
            self.assertIn('scaffold0Topbar: number', combined)
            self.assertIn('migrationContext.scaffold0Topbar = Number(area.height)', combined)
            self.assertIn('renderBusinessSlot(', combined)
            self.assertIn('export interface BusinessSlot', combined)

    def test_source_parameter_does_not_shadow_global_helper(self):
        _, _, _, renderer, code = compile_page('''
@Composable fun Page() { Label("Hello") }
@Composable fun Label(renderLabel: String) { Text(renderLabel) }
''')
        files, report = render_modules(code, renderer.root, renderer.business_components,
            Path('/tmp/generated'), Path('/tmp/generated/Page.ets'), 'test')
        output = files[Path('/tmp/generated/Page.ets')].decode()
        self.assertIn('export function Label(renderLabel: string)', output)
        self.assertIn('renderLabel2({ renderLabel: renderLabel', output)
        self.assertEqual(report['renamed_methods'], {'renderLabel':'renderLabel2'})

    def test_source_path_is_not_flattened_and_cannot_escape(self):
        self.assertEqual(source_file('feature/src/main/kotlin/example/Card.kt'),
                         'feature/src/main/kotlin/example/Card.ets')
        for name in ('../Card.kt', '/Card.kt', '_migration/Card.kt', 'Card.txt'):
            with self.subTest(name=name), self.assertRaises(ArkUIPageError):
                source_file(name)

    def test_legacy_entry_and_obsolete_outputs_keep_ownership_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory).resolve()
            output = target/'entry/src/main/ets/generated'
            output.mkdir(parents=True)
            page = output/'GeneratedPage.ets'
            obsolete = output/'Old.ets'
            shared = output/'Shared.ets'
            root = {'source':'Page.kt', 'composable':'Page'}
            for path in (page, obsolete, shared):
                path.write_bytes(b'old')
            manifest = target/'.migration/arkui-pages/first.json'
            manifest.parent.mkdir(parents=True)
            record = {'schema':MANIFEST_SCHEMA, 'generator':'migrate-android-compose-to-harmony',
                      'module':'entry', 'root':root, 'outputs':{
                          p.relative_to(target).as_posix():{'sha256':hashlib.sha256(b'old').hexdigest()}
                          for p in (page, obsolete, shared)}}
            record['outputs'][page.relative_to(target).as_posix()]['root_component'] = 'Page'
            manifest.write_text(json.dumps(record))
            self.assertEqual(page_file(root, output, target, manifest), page)
            other = {**record, 'outputs':{shared.relative_to(target).as_posix():
                                         {'sha256':hashlib.sha256(b'old').hexdigest()}}}
            (manifest.parent/'second.json').write_text(json.dumps(other))
            deletions = validate_outputs(target, 'entry', page, manifest, root, True, {page:b'new'})
            self.assertEqual(deletions, {obsolete})
            with self.assertRaisesRegex(ArkUIPageError, 'shared generated module differs'):
                validate_outputs(target, 'entry', page, manifest, root, True, {page:b'new', shared:b'new'})
            self.assertEqual(validate_outputs(target, 'entry', page, manifest, root, True,
                {page:b'new', shared:b'old'}), {obsolete})
            shared.write_bytes(b'hand edit')
            with self.assertRaisesRegex(ArkUIPageError, 'changed after generation'):
                validate_outputs(target, 'entry', page, manifest, root, True, {page:b'new'})

    def test_imports_are_rebased_from_each_source_file(self):
        _, _, _, renderer, code = compile_page('''
@Composable fun Page() { Caption("One") }
@Composable fun Caption(label: String) { Text(label) }
''')
        definition = next(d for d in renderer.business_components.definitions.values() if d['type'] == 'Caption')
        definition['identity']['source'] = 'ui/Caption.kt'
        code = "import { Palette } from './theme/Palette';\n" + code
        files, _ = render_modules(code, renderer.root, renderer.business_components,
            Path('/tmp/generated'), Path('/tmp/generated/Page.ets'), 'test')
        caption = files[Path('/tmp/generated/ui/Caption.ets')].decode()
        self.assertIn('from "../theme/Palette"', caption)
        self.assertIn('export function Caption(label: string)', caption)
        self.assertIn('from "./ui/Caption"', files[Path('/tmp/generated/Page.ets')].decode())


class SourceModulesCommandsTest(unittest.TestCase):
    setUp = test_page_commands.PageCommandsTest.setUp
    run_tool = test_page_commands.PageCommandsTest.run_tool
    full_args = test_page_commands.PageCommandsTest.full_args

    def prepare(self, complete=False):
        (self.source/'Page.kt').unlink()
        files = {
            'screens/Profile.kt': '''package example
import example.ui.Header
import example.ui.Shell
@Composable fun Page() { Column { Header("First"); Header("Second"); Shell { Text("Slot") }; Image(painterResource(R.drawable.logo), contentDescription = "Logo") } }
''',
            'ui/Header.kt': '''package example.ui
@Composable fun Header(title: String) { Column { Caption(title); Caption("Subtitle"); Label(title) } }
@Composable fun Caption(label: String) { Text(label) }
@Composable fun Label(renderLabel: String) { Text(renderLabel) }
''',
            'ui/Shell.kt': '''package example.ui
@Composable fun Shell(content: @Composable () -> Unit) { Scaffold(topBar = { Text("Top") }) { content() } }
''',
        }
        if complete:
            files['screens/Profile.kt'] = files['screens/Profile.kt'].replace(
                'Shell { Text("Slot") }', 'Shell("Top")')
            files['ui/Header.kt'] = files['ui/Header.kt'].replace('Text(label)', 'Text(label, color = Color.Black)').replace(
                'Text(renderLabel)', 'Text(renderLabel, color = Color.Black)')
            files['ui/Shell.kt'] = '''package example.ui
@Composable fun Shell(title: String) { Scaffold(containerColor = Color.White, contentColor = Color.Black, topBar = { Text(title, color = Color.Black) }) { Text("Body", color = Color.Black) } }
'''
        for relative, value in files.items():
            path = self.source/relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value)
        self.snapshot = self.root/'snapshot2'
        self.contract = self.root/'contract2.json'
        self.run_tool('prepare_safe_snapshot.py', '--source', self.source, '--snapshot', self.snapshot)
        self.run_tool('analyze_compose_project.py', '--snapshot', self.snapshot, '--output', self.contract)
        args = self.full_args()
        args[args.index('--root-source')+1] = 'screens/Profile.kt'
        return args

    def generate(self, complete=False):
        result = self.run_tool('migrate_compose_page.py', *self.prepare(complete), '--no-auto-component-reuse')
        target = self.root/'harmony'
        page = Path(result['arkui']['output'])
        manifest = Path(result['arkui']['manifest'])
        return result, target, page, manifest

    def test_explicit_style_page_has_complete_generation_verdict(self):
        result, target, page, manifest = self.generate(complete=True)
        self.assertTrue(result['generation_complete'], result.get('diagnosis'))
        self.assertEqual(result['verdict'], 'pass')
        self.assertTrue((target/'entry/src/main/ets/generated/ui/Header.ets').is_file())
        self.assertTrue((target/'entry/src/main/ets/generated/ui/Shell.ets').is_file())

    def test_complete_page_keeps_source_files_and_nested_calls(self):
        result, target, page, manifest = self.generate()
        base = target/'entry/src/main/ets/generated'
        self.assertEqual(page, (base/'screens/Profile.ets').resolve())
        header = base/'ui/Header.ets'
        shell = base/'ui/Shell.ets'
        self.assertTrue(header.is_file())
        self.assertTrue(shell.is_file())
        self.assertIn('from "../ui/Header"', page.read_text())
        self.assertIn('Header("First")', page.read_text())
        self.assertIn('Header("Second")', page.read_text())
        self.assertNotIn('export function Header', page.read_text())
        self.assertIn('export function Header(title: string)', header.read_text())
        self.assertIn('Caption(props.title)', header.read_text())
        self.assertEqual(header.read_text().count('Text('), 2)
        self.assertIn('export function Label(renderLabel: string)', header.read_text())
        self.assertIn('renderLabel2({ renderLabel: renderLabel', header.read_text())
        self.assertIn('export function', shell.read_text())
        recorded = json.loads(manifest.read_text())
        for relative, record in recorded['outputs'].items():
            self.assertEqual(hashlib.sha256((target/relative).read_bytes()).hexdigest(), record['sha256'])
        self.assertEqual(len(recorded['source_organization']['definitions']), 4)
        self.run_tool('generate_arkui_page.py', '--target', target, '--page-json',
                      self.root/'run/lanhu/version_json.json', '--force')
        header.write_text('// manual change\n' + header.read_text())
        failure = self.run_tool('generate_arkui_page.py', '--target', target, '--page-json',
                      self.root/'run/lanhu/version_json.json', '--force', expected=1)
        self.assertIn('changed after generation', failure.stdout)
        self.assertTrue(header.read_text().startswith('// manual change'))

    def test_unowned_component_file_is_not_replaced(self):
        args = self.prepare()
        target = self.root/'harmony'
        self.run_tool('init_harmony_project.py', '--output', target, '--contract', self.contract,
                      '--project-name', 'Modules', '--bundle-name', 'com.example.modules', '--sdk-version', '6.0.0(20)')
        header = target/'entry/src/main/ets/generated/ui/Header.ets'
        header.parent.mkdir(parents=True)
        header.write_text('// business-owned file')
        failure = self.run_tool('migrate_compose_page.py', *args, '--no-auto-component-reuse', expected=1)
        self.assertIn('unowned generated output', failure.stdout)
        self.assertEqual(header.read_text(), '// business-owned file')
        self.assertFalse((target/'entry/src/main/ets/generated/screens/Profile.ets').exists())


if __name__ == '__main__':
    unittest.main()
