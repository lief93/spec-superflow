"""Custom scan/output directories through real CLIs and SDK discovery."""
import json
from pathlib import Path
import tempfile
import unittest

import test_page_commands
from test_component_discovery import component
from ui_migration.frontend.component_discovery import target_inventory
from ui_migration.target_paths import ets_directory, page_directory, relocate_import
from ui_migration.arkui.style_tokens import StyleTokenEmitter
from ui_migration.arkui.component_reuse import ComponentReuseEmitter


class TargetPathsTest(unittest.TestCase):
    def test_resolve_default_relative_absolute_and_reject_unsafe_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory).resolve()
            root = target/'entry/src/main/ets'
            root.mkdir(parents=True)
            self.assertEqual(page_directory(target, 'entry'), root/'generated')
            self.assertEqual(page_directory(target, 'entry', 'entry/src/main/ets/screens'), root/'screens')
            self.assertEqual(page_directory(target, 'entry', root/'screens'), root/'screens')
            for path in ('../outside', 'entry/src/main/resources', target.parent/'outside'):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    page_directory(target, 'entry', path)
            (root/'link').symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symbolic'):
                page_directory(target, 'entry', root/'link/screens')
            with self.assertRaises(ValueError):
                ets_directory(target, '../entry')
            (root/'file').write_text('user')
            with self.assertRaisesRegex(ValueError, 'directory'):
                page_directory(target, 'entry', root/'file')

    def test_custom_discovery_excludes_output_and_unselected_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory).resolve()
            root = target/'entry/src/main/ets'
            for relative in ('shared/Card.ets', 'shared/previews/Card.ets', 'other/Card.ets'):
                path = root/relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(component('Card'))
            found = target_inventory(target, 'entry', 'entry/src/main/ets/shared',
                                     'entry/src/main/ets/shared/previews')
            self.assertEqual(found['files'], 1)
            self.assertEqual(found['components'][0]['module'], '../shared/Card')
            with self.assertRaisesRegex(ValueError, 'does not exist'):
                target_inventory(target, 'entry', root/'missing')
            with self.assertRaisesRegex(ValueError, 'must not be inside'):
                target_inventory(target, 'entry', root/'shared', root/'shared')

    def test_all_relative_adapter_imports_rebase_but_packages_do_not(self):
        original = Path('/project/entry/src/main/ets/generated')
        output = Path('/project/entry/src/main/ets/pages/onboarding')
        rebase = lambda name: relocate_import(name, original, output)
        self.assertEqual(rebase('./Bridge'), '../../generated/Bridge')
        self.assertEqual(rebase('../shared/Card'), '../../shared/Card')
        self.assertEqual(rebase('@company/ui'), '@company/ui')
        for emitter in (StyleTokenEmitter(), ComponentReuseEmitter('Page', None)):
            emitter.modules = {('../shared/Theme', 'Theme'): 'ImportedTheme', ('@company/ui', 'Card'): 'ImportedCard'}
            code = '\n'.join(emitter.imports(rebase))
            self.assertIn("from '../../shared/Theme'", code)
            self.assertIn("from '@company/ui'", code)


class CustomTargetCommandsTest(unittest.TestCase):
    setUp = test_page_commands.PageCommandsTest.setUp
    run_tool = test_page_commands.PageCommandsTest.run_tool
    full_args = test_page_commands.PageCommandsTest.full_args

    def test_existing_project_custom_paths_and_owned_regeneration(self):
        target = self.root/'harmony'
        self.run_tool('init_harmony_project.py', '--output', target, '--contract', self.contract,
                      '--project-name', 'CustomPaths', '--bundle-name', 'com.example.custompaths', '--sdk-version', '6.0.0(20)')
        scan = target/'entry/src/main/ets/shared-ui'
        scan.mkdir()
        business = scan/'Caption.ets'
        original = component(fields='@Prop title: string = ""')
        business.write_text(original)
        duplicate = target/'entry/src/main/ets/other/Caption.ets'
        duplicate.parent.mkdir()
        duplicate.write_text(original)
        args = self.full_args() + ['--component-dir', scan,
                                  '--page-output-dir', 'entry/src/main/ets/pages/onboarding']
        result = self.run_tool('migrate_compose_page.py', *args)
        output = target/'entry/src/main/ets/pages/onboarding/Page.ets'
        self.assertEqual(Path(result['arkui']['output']), output.resolve())
        self.assertIn('from "../../shared-ui/Caption"', output.read_text())
        self.assertIn('Caption({  })', output.read_text())
        self.assertFalse(result['generation_complete'])
        self.assertGreater(result['diagnosis']['counts']['defaulted'], 0)
        self.assertFalse((target/'entry/src/main/ets/generated/GeneratedPage.ets').exists())
        self.assertEqual(business.read_text(), original)
        self.assertTrue((self.root/'run/source-page.json').exists())
        discovery = json.loads((self.root/'run/lanhu/component-discovery.json').read_text())
        self.assertEqual(discovery['files'], 1)
        self.assertEqual(discovery['decisions'][0]['status'], 'matched')
        version = self.root/'run/lanhu/version_json.json'
        self.run_tool('generate_arkui_page.py', '--target', target, '--page-json', version,
                      '--page-output-dir', output.parent, '--force')
        self.assertIn('from "../../shared-ui/Caption"', output.read_text())
        output.write_text('// user edit\n' + output.read_text())
        failure = self.run_tool('generate_arkui_page.py', '--target', target, '--page-json', version,
                               '--page-output-dir', output.parent, '--force', expected=1)
        self.assertIn('changed after generation', failure.stdout)
        self.assertTrue(output.read_text().startswith('// user edit'))

    def test_preflight_rejects_outside_output_before_creating_run(self):
        failure = self.run_tool('migrate_compose_page.py', *self.full_args(),
                               '--page-output-dir', self.root/'outside', expected=1)
        self.assertIn('must be inside', failure.stdout)
        self.assertFalse((self.root/'run').exists())


if __name__ == '__main__':
    unittest.main()
