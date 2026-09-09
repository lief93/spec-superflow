"""Exercise the public CLIs, including intake and actual single-JSON generation."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).parent


class PageCommandsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='page commands ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'android project'
        self.source.mkdir()
        (self.source/'Page.kt').write_text('''package example
import androidx.compose.runtime.Composable
@Composable fun Page() { Column { Caption("Hello"); Image(painterResource(R.drawable.logo), contentDescription = "Logo") } }
@Composable fun Caption(title: String) { Text(title) }
''')
        drawable = self.source/'app/src/main/res/drawable/logo.xml'
        drawable.parent.mkdir(parents=True)
        drawable.write_text('<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="24dp" android:height="24dp" android:viewportWidth="24" android:viewportHeight="24"><path android:fillColor="#FF123456" android:pathData="M0,0L24,0L24,24L0,24Z"/></vector>')
        self.snapshot = self.root/'snapshot'
        self.contract = self.root/'contract.json'
        self.styles = self.root/'styles.json'
        self.run_tool('prepare_safe_snapshot.py', '--source', self.source, '--snapshot', self.snapshot)
        self.run_tool('analyze_compose_project.py', '--snapshot', self.snapshot, '--output', self.contract)
        self.run_tool('generate_project_style_definitions.py', '--contract', self.contract, '--output', self.styles)

    def run_tool(self, script, *args, expected=0):
        result = subprocess.run([sys.executable, str(SCRIPTS/script), *map(str,args)],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, expected, result.stdout+result.stderr)
        return json.loads(result.stdout) if expected == 0 else result

    def source_args(self):
        return ['--snapshot', self.snapshot, '--contract', self.contract,
            '--style-definitions', self.styles, '--root-source', 'Page.kt',
            '--root-composable', 'Page', '--page-id', 'page', '--state-id', 'default',
            '--output', self.root/'page/source-page.json']

    def full_args(self):
        return ['--snapshot', self.snapshot, '--contract', self.contract,
            '--style-definitions', self.styles, '--root-source', 'Page.kt',
            '--root-composable', 'Page', '--page-id', 'page',
            '--output-dir', self.root/'run', '--target', self.root/'harmony',
            '--project-name', 'TestPage', '--bundle-name', 'com.example.testpage',
            '--sdk-version', '6.0.0(20)', '--viewport-width-dp', '360', '--viewport-height-dp', '740']

    def test_source_command_embeds_explicit_styles_and_original_names(self):
        styles = json.loads(self.styles.read_text())
        styles['componentDefaults'] = {}
        styles['theme']['colors']['primary'] = '#FF123456'
        self.styles.write_text(json.dumps(styles))
        result = self.run_tool('generate_source_page.py', *self.source_args())
        document = json.loads(Path(result['output']).read_text())
        self.assertEqual(document['style_definitions'], styles)
        self.assertEqual(document['root']['composable'], 'Page')
        self.assertGreater(len(document['components']), 1)

    def test_missing_root_is_not_automatically_selected(self):
        args = self.source_args(); index = args.index('--root-composable'); del args[index:index+2]
        result = self.run_tool('generate_source_page.py', *args, expected=2)
        self.assertIn('--root-composable', result.stderr)

    def test_missing_style_file_does_not_fallback(self):
        self.styles.unlink()
        result = self.run_tool('generate_source_page.py', *self.source_args(), expected=1)
        self.assertIn('styles', result.stdout)
        self.assertFalse((self.root/'page/source-page.json').exists())

    def test_wrong_root_lists_candidates(self):
        args = self.source_args(); args[args.index('--root-composable')+1] = 'Absent'
        result = self.run_tool('generate_source_page.py', *args, expected=1)
        self.assertIn('Page', result.stdout)
        self.assertIn('Caption', result.stdout)

    def test_snapshot_must_match_contract(self):
        args = self.source_args(); args[args.index('--snapshot')+1] = self.source
        self.run_tool('generate_source_page.py', *args, expected=1)

    def test_existing_output_is_preserved(self):
        output = self.root/'page/source-page.json'; output.parent.mkdir(); output.write_text('user content')
        self.run_tool('generate_source_page.py', *self.source_args(), expected=1)
        self.assertEqual(output.read_text(), 'user content')

    def test_full_command_generates_code_and_stage_report(self):
        result = self.run_tool('migrate_compose_page.py', *self.full_args())
        output = Path(result['arkui']['output'])
        self.assertTrue(output.is_file())
        self.assertIn('export struct Page', output.read_text())
        self.assertIn('Hello', output.read_text())
        self.assertFalse(result['visual_verified'])
        self.assertTrue(all(s['seconds'] >= 0 for s in result['stages']))
        self.assertEqual(result['inputs']['style_definitions'], str(self.styles.resolve()))
        self.assertEqual(json.loads((self.root/'run/result.json').read_text()), result)
        self.assertEqual(result['arkui']['input_mode'], 'page-json-only')
        self.assertTrue((self.root/'harmony/entry/src/main/resources/base/media/logo.svg').is_file())

    def test_full_command_accepts_raw_source(self):
        args = self.full_args(); del args[:4]; args += ['--source', self.source]
        result = self.run_tool('migrate_compose_page.py', *args)
        self.assertTrue((self.root/'run/snapshot/.android-to-harmony-safe.json').exists())
        self.assertTrue(Path(result['arkui']['output']).is_file())

    def test_full_command_refuses_nested_target_before_writing(self):
        args = self.full_args(); args[args.index('--target')+1] = self.snapshot/'harmony'
        self.run_tool('migrate_compose_page.py', *args, expected=1)
        self.assertFalse((self.snapshot/'harmony').exists())

    def test_state_mismatch_stops_before_target_generation(self):
        fixture = self.root/'state.json'
        fixture.write_text(json.dumps({'schema':'android-to-harmony.page-state-fixture.v1',
            'page':{'id':'other', 'state':'default'}, 'values':{}}))
        result = self.run_tool('migrate_compose_page.py', *self.full_args(), '--state-fixture', fixture, expected=1)
        report = json.loads(result.stdout)
        self.assertEqual(report['failed_stage'], 'lanhu')
        self.assertEqual(report['diagnosis']['issues'][0]['impact'], 'execution')
        self.assertIn(report['error'], report['diagnosis']['issues'][0]['reasons'])
        self.assertTrue(Path(report['diagnosis_report']).is_file())
        self.assertFalse((self.root/'harmony').exists())

    def test_unresolved_does_not_prevent_output_or_claim_complete(self):
        (self.source/'Page.kt').write_text('''package example
import androidx.compose.runtime.Composable
@Composable fun Page() { Text("Known text", color = unknownInk) }
''')
        args = self.full_args(); del args[:4]; args += ['--source', self.source]
        result = self.run_tool('migrate_compose_page.py', *args)
        self.assertEqual(result['status'], 'partial_generation')
        self.assertFalse(result['generation_complete'])
        self.assertEqual(result['verdict'], 'fail')
        self.assertIn('Known text', Path(result['arkui']['output']).read_text())
        issues = result['diagnosis']['issues']
        self.assertTrue(any(i['expression'] == 'unknownInk' for i in issues))
        self.assertTrue(any(o.get('source', {}).get('source') == 'Page.kt'
            for i in issues for o in i['occurrences']))
        markdown = Path(result['diagnosis_report']).read_text()
        self.assertIn('unknownInk', markdown)
        self.assertIn('处理：', markdown)

    def test_explicit_state_reaches_generation(self):
        (self.source/'Page.kt').write_text('''package example
import androidx.compose.runtime.Composable
@Composable fun Page() { if (loading) { Text("Loading") } else { Text("Loaded") } }
''')
        fixture = self.root/'loaded.json'
        fixture.write_text(json.dumps({'schema':'android-to-harmony.page-state-fixture.v1',
            'page':{'id':'page', 'state':'loaded'}, 'values':{'loading':False}}))
        args = self.full_args(); del args[:4]
        result = self.run_tool('migrate_compose_page.py', *args, '--source', self.source,
            '--state-fixture', fixture, '--state-id', 'loaded')
        code = Path(result['arkui']['output']).read_text()
        self.assertIn('Loaded', code)
        self.assertNotIn('Loading', code)

    def test_existing_run_is_not_reused_as_new_evidence(self):
        run = self.root/'run'; run.mkdir(); (run/'result.json').write_text('previous run')
        self.run_tool('migrate_compose_page.py', *self.full_args(), expected=1)
        self.assertEqual((run/'result.json').read_text(), 'previous run')

    def test_existing_target_can_be_used_without_reinitialization(self):
        self.run_tool('migrate_compose_page.py', *self.full_args())
        marker = self.root/'harmony/user-file.txt'; marker.write_text('keep me')
        args = self.full_args(); args[args.index('--output-dir')+1] = self.root/'second run'
        for name in ('--project-name', '--bundle-name', '--sdk-version'):
            index = args.index(name); del args[index:index+2]
        result = self.run_tool('migrate_compose_page.py', *args, '--force')
        self.assertEqual(marker.read_text(), 'keep me')
        self.assertNotIn('target', [s['stage'] for s in result['stages']])

    def test_modified_theme_is_not_overwritten(self):
        self.run_tool('migrate_compose_page.py', *self.full_args())
        target = self.root/'harmony'
        manifest = json.loads((target/'.migration/compose-theme-resources.json').read_text())
        path = target/next(iter(manifest['outputs']))
        path.write_text('user modification')
        args = self.full_args(); args[args.index('--output-dir')+1] = self.root/'second run'
        result = self.run_tool('migrate_compose_page.py', *args, '--force', expected=1)
        self.assertEqual(json.loads(result.stdout)['failed_stage'], 'theme')
        self.assertEqual(path.read_text(), 'user modification')


if __name__ == '__main__':
    unittest.main()
