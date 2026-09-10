"""Existing project integration without migration project markers."""
import json
from pathlib import Path
import unittest

import test_page_commands
from test_component_discovery import component
from ui_migration.target_access import metadata_directory


class ExistingTargetTest(unittest.TestCase):
    run_tool = test_page_commands.PageCommandsTest.run_tool
    full_args = test_page_commands.PageCommandsTest.full_args

    def setUp(self):
        test_page_commands.PageCommandsTest.setUp(self)
        self.target = self.root / 'harmony'
        self.module = 'portfolio_plus'
        self.main = self.target / self.module / 'src/main'
        self.scan = self.main / 'ets/business'
        self.output = self.main / 'ets/view/onboarding'
        self.scan.mkdir(parents=True)
        (self.main / 'resources/base/element').mkdir(parents=True)
        (self.target / 'build-profile.json5').write_text('{"modules":[{"name":"portfolio_plus","srcPath":"./portfolio_plus"}]}')
        (self.target / 'oh-package.json5').write_text('{"name":"company-app","version":"1.0.0"}')
        (self.main / 'module.json5').write_text('{"module":{"name":"portfolio_plus","type":"har","deviceTypes":["phone"]}}')
        (self.scan / 'Caption.ets').write_text(component(fields='@Prop title: string = ""'))
        (self.main / 'resources/base/element/color.json').write_text('{"color":[{"name":"company_brand","value":"#123456"}]}\n')
        self.originals = {p: p.read_bytes() for p in self.target.rglob('*') if p.is_file()}
        self.metadata = self.root / 'records'

    def args(self, run='run'):
        args = self.full_args()
        args[args.index('--output-dir') + 1] = self.root / run
        return args + ['--module', self.module, '--component-dir', self.scan,
                       '--page-output-dir', self.output, '--existing-target',
                       '--target-metadata-dir', self.metadata]

    def test_full_pipeline_and_repeat_preserve_existing_project(self):
        result = self.run_tool('migrate_compose_page.py', *self.args())
        page = self.output / 'Page.ets'
        self.assertEqual(Path(result['arkui']['output']), page.resolve())
        self.assertIn('from "../../business/Caption"', page.read_text())
        self.assertIn('ReusedCaption', page.read_text())
        self.assertTrue((self.main / 'resources/base/media/logo.svg').is_file())
        self.assertFalse((self.target / '.migration').exists())
        for path, content in self.originals.items():
            self.assertEqual(path.read_bytes(), content)
        self.assertTrue(Path(result['arkui']['manifest']).is_relative_to(self.metadata.resolve()))
        before = page.read_bytes()
        self.run_tool('migrate_compose_page.py', *self.args('again'), '--force')
        self.assertEqual(page.read_bytes(), before)
        self.run_tool('generate_arkui_page.py', '--target', self.target, '--module', self.module,
            '--page-json', self.root / 'again/lanhu/version_json.json', '--page-output-dir', self.output,
            '--existing-target', '--target-metadata-dir', self.root / 'lost-records', '--force', expected=1)
        self.assertEqual(page.read_bytes(), before)
        page.write_text('// hand edit\n' + page.read_text())
        failed = self.run_tool('generate_arkui_page.py', '--target', self.target, '--module', self.module,
            '--page-json', self.root / 'again/lanhu/version_json.json', '--page-output-dir', self.output,
            '--existing-target', '--target-metadata-dir', self.metadata, '--force', expected=1)
        self.assertIn('changed after generation', failed.stdout)
        self.assertTrue(page.read_text().startswith('// hand edit'))

    def test_existing_mode_is_explicit_and_checked_before_generation(self):
        args = self.args()
        del args[args.index('--existing-target'):]
        failed = self.run_tool('migrate_compose_page.py', *args, expected=1)
        self.assertIn('marker', failed.stdout)
        self.assertFalse((self.root / 'run/source-page.json').exists())
        with self.assertRaisesRegex(ValueError, 'separate'):
            metadata_directory(self.target, self.module, True, self.target / 'records')
        with self.assertRaisesRegex(ValueError, 'missing'):
            metadata_directory(self.target, 'missing', True, self.metadata)
        (self.main / 'ets/link').symlink_to(self.root, target_is_directory=True)
        args = self.args('unsafe')
        args[args.index('--page-output-dir') + 1] = self.main / 'ets/link/page'
        self.run_tool('migrate_compose_page.py', *args, expected=1)
        self.assertFalse((self.root / 'unsafe').exists())

    def test_unowned_page_is_never_overwritten(self):
        self.output.mkdir(parents=True)
        page = self.output / 'Page.ets'
        page.write_text('// hand-written page\n')
        self.run_tool('migrate_compose_page.py', *self.args(), '--force', expected=1)
        self.assertEqual(page.read_text(), '// hand-written page\n')
        self.assertFalse((self.target / '.migration').exists())
        page.unlink()
        outside = self.root / 'missing-outside.ets'
        page.symlink_to(outside)
        self.run_tool('generate_arkui_page.py', '--target', self.target, '--module', self.module,
            '--page-json', self.root / 'run/lanhu/version_json.json', '--page-output-dir', self.output,
            '--existing-target', '--target-metadata-dir', self.metadata, '--force', expected=1)
        self.assertTrue(page.is_symlink())
        self.assertFalse(outside.exists())

    def test_unowned_vector_is_not_overwritten(self):
        media = self.main / 'resources/base/media'
        media.mkdir()
        vector = media / 'logo.svg'
        vector.write_text('<svg><!-- company asset --></svg>')
        failed = self.run_tool('migrate_compose_page.py', *self.args(), expected=1)
        report = json.loads(failed.stdout)
        self.assertEqual(report['failed_stage'], 'drawables')
        self.assertIn('unowned vector', (self.root / 'run/03-drawables.stdout.log').read_text())
        self.assertEqual(vector.read_text(), '<svg><!-- company asset --></svg>')
        self.assertFalse((self.target / '.migration').exists())

    def test_unowned_theme_file_is_preserved(self):
        from unittest.mock import patch
        from generate_harmony_theme_resources import generate, ThemeResourceError
        output = self.main / 'resources/base/element/migration_color.json'
        output.write_text('{"color":[]}')
        plan = ({'generated_color': '#FF000000'}, {}, {}, [], [], [], [])
        with patch('generate_harmony_theme_resources.build_candidate_resources', return_value=plan):
            with self.assertRaisesRegex(ThemeResourceError, 'unowned theme file'):
                generate(self.contract, self.target, self.module, True,
                         existing_target=True, target_metadata_dir=self.metadata)
        self.assertEqual(output.read_text(), '{"color":[]}')

    def test_theme_name_collision_and_modified_generated_resource(self):
        from unittest.mock import patch
        from generate_harmony_theme_resources import generate, ThemeResourceError
        plan = ({'company_brand': '#FF000000'}, {}, {}, [], [], [], [])
        with patch('generate_harmony_theme_resources.build_candidate_resources', return_value=plan):
            with self.assertRaisesRegex(ThemeResourceError, 'conflicts'):
                generate(self.contract, self.target, self.module, True,
                         existing_target=True, target_metadata_dir=self.metadata)
        for path, data in self.originals.items():
            self.assertEqual(path.read_bytes(), data)
        plan = ({'generated_color': '#FF000000'}, {}, {}, [], [], [], [])
        with patch('generate_harmony_theme_resources.build_candidate_resources', return_value=plan):
            generate(self.contract, self.target, self.module, True,
                     existing_target=True, target_metadata_dir=self.metadata)
        output = self.main / 'resources/base/element/migration_color.json'
        output.write_text('{"color":[{"name":"hand_edit","value":"#FFFFFF"}]}')
        failed = self.run_tool('generate_harmony_theme_resources.py', '--target', self.target,
            '--module', self.module, '--contract', self.contract, '--force',
            '--existing-target', '--target-metadata-dir', self.metadata, expected=1)
        self.assertIn('changed', failed.stdout)
        self.assertIn('hand_edit', output.read_text())

    def test_empty_theme_does_not_create_invalid_empty_resource_file(self):
        self.run_tool('generate_harmony_theme_resources.py', '--target', self.target,
            '--module', self.module, '--contract', self.contract,
            '--existing-target', '--target-metadata-dir', self.metadata)
        self.assertFalse((self.main / 'resources/base/element/migration_color.json').exists())
        for path, content in self.originals.items():
            self.assertEqual(path.read_bytes(), content)

    def test_opaque_copy_and_font_consumer_use_external_ledger(self):
        import hashlib
        from ui_migration.arkui.resources import load_page_font_faces
        source = self.root / 'opaque-source'
        asset = source / 'app/src/main/res/font/body.ttf'
        asset.parent.mkdir(parents=True)
        asset.write_bytes(b'synthetic font bytes, hash verification only')
        snapshot = self.root / 'opaque-snapshot'
        self.run_tool('prepare_safe_snapshot.py', '--source', source, '--snapshot', snapshot)
        destination = self.main / 'resources/rawfile/body.ttf'
        args = ['--manifest', snapshot / '.android-to-harmony-safe.json', '--asset-path',
                'app/src/main/res/font/body.ttf', '--target', self.target, '--destination', destination,
                '--existing-target', '--target-metadata-dir', self.metadata]
        self.run_tool('copy_local_asset.py', *args)
        self.assertFalse(self.run_tool('copy_local_asset.py', *args)['changed'])
        metadata = metadata_directory(self.target, self.module, True, self.metadata)
        page = {'font_faces': [{'family': 'Body', 'resource': 'body', 'weight': 400}]}
        faces = load_page_font_faces(self.target.resolve(), self.module, page, metadata)
        self.assertEqual(faces[0]['sha256'], hashlib.sha256(asset.read_bytes()).hexdigest())
        self.assertFalse((self.target / '.migration').exists())
        destination.write_bytes(b'hand edit')
        failed = self.run_tool('copy_local_asset.py', *args, '--force', expected=1)
        self.assertIn('changed', failed.stdout)
        self.assertEqual(destination.read_bytes(), b'hand edit')

    def test_metadata_is_bound_to_target_and_module_and_rejects_symlinks(self):
        from ui_migration.target_access import check_manifest_outputs
        first = metadata_directory(self.target, self.module, True, self.metadata)
        self.assertTrue(first.is_relative_to(self.metadata.resolve()))
        first.mkdir(parents=True)
        manifest = first / 'page.json'
        for relative in ('../outside.ets', f'{self.module}/src/main/module.json5'):
            manifest.write_text(json.dumps({'outputs': {relative: {}}}))
            with self.assertRaises(ValueError):
                check_manifest_outputs(self.target.resolve(), self.module, manifest)
        link = self.root / 'records-link'
        link.symlink_to(self.metadata, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symbolic'):
            metadata_directory(self.target, self.module, True, link)


if __name__ == '__main__':
    unittest.main()
