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
        events = [json.loads(line) for line in Path(result['progress_log']).read_text().splitlines()]
        self.assertTrue(any(e['phase'] == 'reuse-analysis' for e in events))
        self.assertTrue(any(e['event'] == 'phase-start' and e['phase'] == 'source-page' for e in events))
        self.assertIsNone(result['current_stage'])
        self.assertNotIn('analysis', [s['stage'] for s in result['stages']])
        source_stage = next(s for s in result['stages'] if s['stage'] == 'source-page')
        self.assertIn('build-source-page', (self.root/'run'/source_stage['stderr']).read_text())
        self.assertTrue((self.root/'harmony/entry/src/main/resources/base/media/logo.svg').is_file())

    def test_full_command_preserves_repeat_title_and_intrinsic_image_dimensions(self):
        from generate_arkui_page import load_lanhu_page_input
        (self.source/'Page.kt').write_text('''package example
import androidx.compose.runtime.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.background
import androidx.compose.material3.Text
import androidx.compose.foundation.Image
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.*
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.*
@Composable fun Page() {
    val focusRequester = remember { FocusRequester() }
    val currentPage = 2
    Column {
        Text("Title", color = Color.Black, fontSize = 16.sp,
             modifier = Modifier.focusRequester(focusRequester).padding(8.dp))
        Row { repeat(4) { index ->
            Box(Modifier.size(8.dp).background(if (currentPage == index) Color.Red else Color.Black)) {}
            Spacer(Modifier.width(4.dp))
        } }
        if (currentPage in arrayOf(0, 1, 2)) { Text("Next", color = Color.Black) }
        else { Text("Explore", color = Color.Black) }
        Image(painterResource(R.drawable.logo), contentDescription = "Logo")
    }
}
''')
        (self.source/'app/src/main/res/drawable/logo.xml').write_text(
            '<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="96dp" android:height="48dp" '
            'android:viewportWidth="96" android:viewportHeight="48"><path android:fillColor="#FF123456" '
            'android:pathData="M0,0L96,0L96,48L0,48Z"/></vector>')
        args = self.full_args(); del args[:4]; args += ['--source', self.source]
        result = self.run_tool('migrate_compose_page.py', *args)
        code = Path(result['arkui']['output']).read_text()
        page = load_lanhu_page_input(self.root/'run/lanhu/version_json.json')
        self.assertEqual(len([n for n in page['components'] if n['type']=='Box']), 4)
        self.assertEqual([n['style']['content']['text'] for n in page['components'] if n['type']=='Text'], ['Title', 'Next'])
        self.assertFalse(any(n.get('slot_invocation') for n in page['components']))
        image = next(n for n in page['components'] if n['type']=='Image')
        self.assertEqual((image['style']['asset']['width_dp'], image['style']['asset']['height_dp']), (96, 48))
        self.assertIn('maxWidth: 96, maxHeight: 48', code)
        self.assertIn('.aspectRatio(2)', code)
        self.assertIn("Text('Title')", code)
        self.assertNotIn("Text('Explore')", code)
        self.assertEqual(code.count('.backgroundColor('), 4)
        self.assertEqual(result['arkui']['input_mode'], 'page-json-only')
        self.assertTrue((self.root/'harmony/entry/src/main/resources/base/media/logo.svg').is_file())

    def test_full_command_previews_unknown_branch_and_retains_alternative(self):
        from ui_migration.contracts.lanhu_storage import unpack_lanhu_document
        (self.source/'Page.kt').write_text('''package example
import androidx.compose.runtime.Composable
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.*
@Composable fun Page(currentPage: Int) {
    Column {
        Text("Title", color = Color.Black, fontSize = 16.sp)
        if (currentPage < 3) {
            Text("Next", fontSize = 18.sp, color = Color.Red, modifier = Modifier.height(30.dp))
        } else {
            Text("Explore", fontSize = 24.sp, color = Color.Blue, modifier = Modifier.height(90.dp))
        }
        Text("Footer", color = Color.Black, fontSize = 16.sp)
    }
}
''')
        args = self.full_args(); del args[:4]; args += ['--source', self.source]
        result = self.run_tool('migrate_compose_page.py', *args)
        code = Path(result['arkui']['output']).read_text()
        self.assertIn("Text('Next')", code)
        self.assertNotIn("Text('Explore')", code)
        document = unpack_lanhu_document(json.loads((self.root/'run/lanhu/version_json.json').read_text()))
        projection = document['meta']['sourceGeneration']['stateProjection']
        self.assertFalse(projection['selection_complete'])
        alternative = next(n for n in projection['retained_components'] if n['type']=='Text')
        self.assertEqual(alternative['style']['content']['text'], 'Explore')
        self.assertEqual(alternative['style']['typography']['font_size_sp'], 24)
        issues = result['diagnosis']['issues']
        self.assertTrue(any(i['code']=='state_preview_default' and i['status']=='deferred_dynamic' for i in issues))
        self.assertTrue((self.root/'run/diagnosis.md').is_file())
        self.assertFalse(result['visual_verified'])

    def test_full_command_accepts_raw_source(self):
        args = self.full_args(); del args[:4]; args += ['--source', self.source]
        result = self.run_tool('migrate_compose_page.py', *args)
        self.assertTrue((self.root/'run/snapshot/.android-to-harmony-safe.json').exists())
        analysis = next(s for s in result['stages'] if s['stage'] == 'analysis')
        log = (self.root/'run'/analysis['stderr']).read_text()
        for name in ('psi-declarations', 'function-dependencies', 'symbol-resolution', 'call-closures', 'write-contract'):
            self.assertIn(name, log)
        self.assertTrue(Path(result['arkui']['output']).is_file())

    def test_full_command_auto_reuses_existing_target_and_can_opt_out(self):
        self.run_tool('migrate_compose_page.py', *self.full_args())
        library = self.root/'harmony/entry/src/main/ets/components/Caption.ets'
        library.parent.mkdir(parents=True)
        content = '''@Component
export struct Caption {
  @Prop title: string = ""
  build() { Text(this.title) }
}
'''
        library.write_text(content)
        args = self.full_args()
        args[args.index('--output-dir') + 1] = self.root/'run-auto'
        result = self.run_tool('migrate_compose_page.py', *args, '--force')
        self.assertIn('ReusedCaption({ title: "Hello" })', Path(result['arkui']['output']).read_text())
        discovery = json.loads((self.root/'run-auto/lanhu/component-discovery.json').read_text())
        self.assertTrue(any(d['status'] == 'matched' for d in discovery['decisions']))
        self.assertEqual(library.read_text(), content)
        args[args.index('--output-dir') + 1] = self.root/'run-no-auto'
        result = self.run_tool('migrate_compose_page.py', *args, '--force', '--no-auto-component-reuse')
        self.assertNotIn('ReusedCaption', Path(result['arkui']['output']).read_text())
        self.assertEqual(library.read_text(), content)

    def test_caller_owned_outputs_pass_full_command_with_a_context_warning(self):
        (self.source/'Page.kt').write_text('''package example
import androidx.compose.runtime.Composable
@Composable fun Page() { Box(Modifier.size(80.dp, 40.dp)); Box(Modifier.size(80.dp, 40.dp)) }
''')
        args = self.full_args(); del args[:4]; args += ['--source', self.source]
        result = self.run_tool('migrate_compose_page.py', *args)
        self.assertEqual(result['verdict'], 'pass', result)
        self.assertTrue(result['generation_complete'])
        self.assertFalse(result['visual_verified'])
        self.assertTrue(any(w['path'] == 'layout.root_host' for w in result['warnings']))
        manifest = json.loads(Path(result['arkui']['manifest']).read_text())
        self.assertFalse(manifest['unresolved'])
        self.assertEqual(manifest['verdict'], 'pass')
        self.assertTrue(any(w['path'] == 'layout.root_host' for w in manifest['warnings']))
        self.assertEqual(Path(result['arkui']['output']).read_text().count('Stack()'), 3)

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
        self.assertIn('尚有', markdown)
        self.assertEqual(result['diagnosis']['unresolved_count'], sum(
            count for status, count in result['diagnosis']['counts'].items() if status != 'resolved_reference'))
        comparison = self.root/'comparison.json'
        comparison.write_text(json.dumps({'schema': 'android-to-harmony.local-image-comparison.v1',
            'component_inventories': [], 'viewport_compatibility': {}}))
        refreshed = self.run_tool('diagnose_page_fidelity.py', '--run-dir',
            Path(result['diagnosis_report']).parent, '--comparison-report', comparison)
        self.assertFalse(refreshed['comparable'])
        self.assertIn('P0', Path(refreshed['diagnosis_report']).read_text())

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
