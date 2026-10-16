"""Exercise the public CLIs, including intake and actual single-JSON generation."""
import hashlib
import json
import os
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
        self.root = Path(self.temp.name).resolve()
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
        self.behavior_fixture_index = 0

    def run_tool(self, script, *args, expected=0):
        result = subprocess.run([sys.executable, str(SCRIPTS/script), *map(str,args)],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, expected, result.stdout+result.stderr)
        return json.loads(result.stdout) if expected == 0 else result

    def run_page_evidence(self, run_root, target, scope_id, name, *, expected=0):
        from test_evidence_runner import FAKE_TOOL
        run_root = Path(run_root).resolve()
        target = Path(target).resolve()
        sdk = self.root/'fake-sdk'
        deveco = self.root/'fake-deveco'
        tool = sdk/'default/openharmony/toolchains/hdc'
        tool.parent.mkdir(parents=True, exist_ok=True)
        deveco.mkdir(exist_ok=True)
        tool.write_text(FAKE_TOOL)
        tool.chmod(0o755)
        haps = [target/'entry/build/default'/filename
                for filename in ('entry-default.hap', 'entry-ohosTest.hap')]
        haps[0].parent.mkdir(parents=True, exist_ok=True)
        for hap in haps:
            hap.write_bytes(b'controlled-page-test-hap')
        environment = os.environ.copy()
        environment['DEVECO_HOME'] = str(deveco)
        environment['DEVECO_SDK_HOME'] = str(sdk)
        result = subprocess.run([
            sys.executable, str(SCRIPTS/'evidence_runner.py'), 'run',
            '--target', str(target), '--run-root', str(run_root),
            '--gate', 'ui_tests', '--name', name,
            '--slice-id', scope_id, '--demand-id', 'SCN-PAGE',
            '--test-report-from-stdout', '--test-report-format', 'hypium-text',
            '--ui-main-hap', str(haps[0]), '--ui-test-hap', str(haps[1]),
            '--device-kind', 'emulator', '--device-id', 'emulator-1',
            '--os-version', 'HarmonyOS 6', '--api-version', '24', '--', str(tool),
            '-t', 'emulator-1', 'shell', 'aa', 'test', '-b', 'com.example.evidence',
            '-m', 'entry_test', '-s', 'unittest', 'OpenHarmonyTestRunner',
        ], capture_output=True, text=True, timeout=120, env=environment)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

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
            '--sdk-version', '6.0.0(20)', '--viewport-width-dp', '360', '--viewport-height-dp', '740',
            '--deterministic-candidate']

    def ai_args(self):
        args = self.full_args()
        args.remove('--deterministic-candidate')
        state = self.root/'runtime-state.json'
        state.write_text(json.dumps({
            'schema': 'android-to-harmony.page-state-fixture.v1',
            'page': {'id': 'page', 'state': 'default'},
            'values': {},
        }))
        android_page = self.root/'android-page.json'
        android_page.write_text(json.dumps({
            'schema': 'android-to-harmony.page-snapshot.v2',
            'platform': 'android',
            'page': {'id': 'page', 'state': 'default'},
            'capture': {'screenshot': {'sha256': 'a' * 64}},
            'viewport': {'density': 3.0, 'font_scale': 1.0},
            'components': [],
        }))
        theme = self.root/'android-theme-facts.json'
        theme.write_text(json.dumps({
            'schema': 'android-to-harmony.compose-theme-facts.v1',
            'platform': 'android',
            'theme_id': 'test-light',
            'capture': {
                'sdk_int': 35,
                'density': 3.0,
                'font_scale': 1.0,
                'layout_direction': 'ltr',
            },
            'theme': {'colors': {}, 'typography': {}, 'shapes': {}},
            'provenance': [],
            'unresolved': [],
        }))
        args += [
            '--state-fixture', state,
            '--android-page-json', android_page,
            '--android-theme-facts', theme,
        ]
        return args

    def behavior_materials(self, *, implemented=False):
        from audit_behavior_source import census, digest
        self.behavior_fixture_index += 1
        fixture_root = self.root/f'behavior-{self.behavior_fixture_index}'
        fixture_root.mkdir()
        state_args = self.ai_args()
        state = Path(state_args[state_args.index('--state-fixture') + 1])
        android_page = Path(state_args[state_args.index('--android-page-json') + 1])
        android_theme = Path(state_args[state_args.index('--android-theme-facts') + 1])
        closure_path = fixture_root/'closure.json'
        self.run_tool(
            'generate_effective_page_closure.py', '--contract', self.contract,
            '--style-definitions', self.styles, '--root-source', 'Page.kt',
            '--root-composable', 'Page', '--page-id', 'page', '--state-id', 'default',
            '--state-fixture', state, '--android-page-json', android_page,
            '--android-theme-facts', android_theme, '--output', closure_path,
        )
        closure = json.loads(closure_path.read_text())
        scope = closure['business_transcription']['scope']
        current = census(self.snapshot, scope)
        self.assertFalse(current['unresolved'], current['unresolved'])
        source_path = self.snapshot/'Page.kt'
        source_text = source_path.read_text()
        source_sha = hashlib.sha256(source_text.encode()).hexdigest()
        inventory = {
            'schema_version':'behavior-source-inventory.v1',
            'source_revision':scope['source_revision'],
            'scope_id':scope['id'],
            'items':[{'id':'INV-PAGE', 'category':'action', 'summary':'Render the selected page',
                      'source_evidence':['source']}],
        }
        expressions = [item['expression'] for item in current['obligations']]
        contract = {
            'schema_version':'behavior-contract.v2',
            'identity':{'contract_id':'page-contract', 'source_revision':scope['source_revision']},
            'scope':{'included_scopes':[scope['id']], 'excluded':[]},
            'screens':[{'id':'page'}], 'states':[],
            'actions':[{'id':'ACTION-PAGE', 'trigger':'open page', 'guard':'page selected',
                'handler_chain':['Page'], 'transition':'not visible -> visible',
                'effects':['render selected page'], 'observable_results':['page content visible'],
                'scenario_ids':['SCN-PAGE'], 'source_inventory_ids':['INV-PAGE']}],
            'navigation':[], 'domain':{}, 'data_flows':[], 'async_states':[],
            'platform_effects':{'items':[], 'none_reason':'not applicable'},
            'lifecycle':[], 'observables':[{'id':'OBS-PAGE'}],
            'scenarios':[{'id':'SCN-PAGE', 'action_ids':['ACTION-PAGE'], 'given':'selected page',
                'when':'page opens', 'then':['page content visible'], 'android_evidence':['source'],
                'target_test':'DemoUiTest.opensDemo'}],
            'traceability':{'source_inventory':'inventory.json', 'target_implementation':[{
                'id':'ACTION-PAGE', 'status':'implemented' if implemented else 'missing',
                'target':'Index.ets#build' if implemented else None,
            }]},
            'unresolved':[],
            'collection':{
                'schema_version':'behavior-collection.v1', 'status':'complete',
                'source_revision':scope['source_revision'],
                'anchors':[{'id':'source', 'kind':'source', 'path':'Page.kt', 'start_line':1,
                    'end_line':len(source_text.splitlines()), 'file_sha256':source_sha,
                    'span_sha256':source_sha}],
                'entities':[{'id':'page', 'kind':'page', 'owner_id':None,
                    'source_inventory_ids':['INV-PAGE'], 'anchor_ids':['source']}],
                'relationships':[],
                'facts':[{'id':'act', 'kind':'action', 'owner_id':'page',
                    'contract_ids':['ACTION-PAGE'], 'source_inventory_ids':['INV-PAGE'],
                    'anchor_ids':['source'], 'trigger':'open page', 'handler':'Page',
                    'outcomes':['page content visible'], 'source_expressions':expressions},
                    {'id':'scenario', 'kind':'scenario', 'owner_id':'page',
                    'contract_ids':['SCN-PAGE'], 'source_inventory_ids':['INV-PAGE'],
                    'anchor_ids':['source'], 'action_ids':['act'], 'given':'selected page',
                    'when':'page opens', 'then':['page content visible'],
                    'evidence_kind':'source'}],
                'categories':[],
            },
        }
        for family in ('ownership', 'events_state_navigation', 'data', 'async_lifecycle',
                       'validation_security', 'scenarios_evidence'):
            records = {'ownership':['page'], 'events_state_navigation':['act'],
                       'scenarios_evidence':['scenario']}.get(family, [])
            contract['collection']['categories'].append({
                'family':family, 'disposition':'applicable' if records else 'not_applicable',
                'rationale':'Bounded selected-page fixture', 'anchor_ids':['source'],
                'record_ids':records,
            })
        contract['source_closure'] = {
            'schema_version':'behavior-source-closure.v1',
            'census_sha256':current['census_sha256'],
            'inventory_sha256':digest(inventory),
            'bindings':[{'obligation_id':item['id'],
                'record_ids':['page'] if item['kind'] == 'declaration' else ['act'],
                'scenario_ids':['SCN-PAGE']} for item in current['obligations']],
        }
        review = {
            'schema_version':'behavior-source-review.v1', 'verdict':'pass',
            'reviewer':'page command fixture reviewer', 'scope_sha256':current['scope_sha256'],
            'census_sha256':current['census_sha256'], 'contract_sha256':digest(contract),
            'unresolved':[], 'dependency_edges':current['dependency_edges'],
            'external_dependencies':current['external_dependencies'],
            'expectations':[{'id':'page-rendering', 'summary':'The selected page renders its source content.',
                'obligation_ids':[item['id'] for item in current['obligations']],
                'record_ids':['page', 'act'], 'scenario_ids':['SCN-PAGE']}],
        }
        paths = {}
        for name, value in (('contract', contract), ('inventory', inventory), ('review', review)):
            paths[name] = fixture_root/f'{name}.json'
            paths[name].write_text(json.dumps(value))
        return paths, contract, inventory, review

    @staticmethod
    def behavior_args(paths, *, include_review=False):
        args = ['--behavior-contract', paths['contract'],
                '--behavior-inventory', paths['inventory']]
        if include_review:
            args.extend(['--behavior-source-review', paths['review']])
        return args

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
        closure_reference = result['effective_page_closure']
        closure_path = Path(closure_reference['path'])
        closure = json.loads(closure_path.read_text())
        self.assertEqual(
            closure_reference['sha256'],
            hashlib.sha256(closure_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(closure_reference['status'], 'candidate_complete')
        self.assertEqual(closure_reference['visible_component_count'], len(closure['visible_components']))
        self.assertEqual(closure['schema'], 'android-to-harmony.effective-page-closure.v1')
        self.assertEqual(closure['source_scope']['status'], 'ready')
        self.assertEqual(
            {item['path'] for item in closure['source_scope']['entry_files']},
            {'Page.kt'},
        )
        self.assertNotIn('obligations', closure['business_transcription'])
        stages = [stage['stage'] for stage in result['stages']]
        self.assertLess(stages.index('effective-page-closure'), stages.index('source-page'))
        self.assertLess(stages.index('source-page'), stages.index('lanhu'))
        events = [json.loads(line) for line in Path(result['progress_log']).read_text().splitlines()]
        self.assertTrue(any(e['phase'] == 'reuse-analysis' for e in events))
        self.assertTrue(any(e['event'] == 'phase-start' and e['phase'] == 'source-page' for e in events))
        self.assertIsNone(result['current_stage'])
        self.assertNotIn('analysis', [s['stage'] for s in result['stages']])
        source_stage = next(s for s in result['stages'] if s['stage'] == 'source-page')
        self.assertIn('build-source-page', (self.root/'run'/source_stage['stderr']).read_text())
        self.assertTrue((self.root/'harmony/entry/src/main/resources/base/media/logo.svg').is_file())

    def test_default_command_stops_after_closure_when_behavior_specification_is_missing(self):
        result = self.run_tool('migrate_compose_page.py', *self.ai_args(), expected=1)
        report = json.loads(result.stdout)
        self.assertFalse(report['ok'])
        self.assertEqual(report['status'], 'business_specification_required')
        self.assertEqual(report['failed_stage'], 'behavior-source-validation')
        self.assertFalse(report['business_verified'])
        self.assertFalse(report['implementation_complete'])
        self.assertEqual(report['deterministic_generation']['status'], 'not_run')
        self.assertNotIn('source_page', report)
        self.assertNotIn('version_json', report)
        self.assertNotIn('arkui', report)
        self.assertEqual(
            [stage['stage'] for stage in report['stages']],
            ['effective-page-closure'],
        )
        closure_reference = report['effective_page_closure']
        closure_path = Path(closure_reference['path'])
        closure = json.loads(closure_path.read_text())
        self.assertEqual(
            closure_reference['sha256'],
            hashlib.sha256(closure_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(report['ai_implementation']['status'], 'blocked')
        self.assertTrue(report['ai_implementation']['requires_source_reading'])
        self.assertEqual(report['ai_implementation']['source_scope_entry_count'], 1)
        self.assertEqual(report['ai_implementation']['ui_transcription'], 'required_from_scoped_source')
        self.assertEqual(report['ai_implementation']['business_transcription'], 'specification_required')
        self.assertEqual(closure['runtime_facts']['origin'], 'android-page-snapshot-v2')
        self.assertEqual(closure['runtime_theme']['theme_id'], 'test-light')
        self.assertEqual(
            report['ai_implementation']['source_scope_sha256'],
            closure['source_scope']['sha256'],
        )
        self.assertTrue(Path(report['behavior_source_scope']).is_file())
        self.assertFalse((self.root/'harmony').exists())
        self.assertFalse((self.root/'harmony/entry/src/main/ets/generated').exists())
        self.assertFalse((self.root/'run/source-page.json').exists())
        self.assertFalse((self.root/'run/lanhu').exists())

    def test_default_command_rejects_placeholder_behavior_artifacts(self):
        placeholders = self.root/'placeholders'
        placeholders.mkdir()
        paths = {}
        for name in ('contract', 'inventory', 'review'):
            paths[name] = placeholders/f'{name}.json'
            paths[name].write_text('{}')
        result = self.run_tool('migrate_compose_page.py', *self.ai_args(),
            *self.behavior_args(paths), expected=1)
        report = json.loads(result.stdout)
        self.assertEqual(report['failed_stage'], 'behavior-source-validation')
        self.assertEqual(report['status'], 'business_specification_required')
        self.assertFalse(report['business_verified'])
        self.assertFalse((self.root/'harmony').exists())

    def test_default_command_accepts_bound_scope_and_rejects_a_replaced_page_entry(self):
        paths, _, _, _ = self.behavior_materials()
        scope = json.loads((paths['contract'].parent/'closure.json').read_text())['business_transcription']['scope']
        scope_path = self.root/'selected-scope.json'
        scope_path.write_text(json.dumps(scope))
        result = self.run_tool('migrate_compose_page.py', *self.ai_args(),
            *self.behavior_args(paths), '--behavior-source-scope', scope_path)
        self.assertEqual(result['status'], 'ready_for_ai_implementation')
        scope['entry_symbols']['Page.kt'] = ['AnotherHandler']
        scope_path.write_text(json.dumps(scope))
        args = self.ai_args()
        args[args.index('--output-dir') + 1] = self.root/'wrong-scope-run'
        failed = self.run_tool('migrate_compose_page.py', *args,
            *self.behavior_args(paths), '--behavior-source-scope', scope_path, expected=1)
        self.assertIn('generated page roots', failed.stdout)

    def test_default_command_accepts_current_page_behavior_specification(self):
        paths, _, _, _ = self.behavior_materials()
        paths['review'].unlink()
        result = self.run_tool('migrate_compose_page.py', *self.ai_args(),
            *self.behavior_args(paths))
        self.assertEqual(result['status'], 'ready_for_ai_implementation')
        self.assertEqual(result['behavior_source_validation']['verdict'], 'pass')
        self.assertTrue(result['behavior_source_validation']['source_complete'])
        self.assertEqual(result['behavior_source_validation']['semantic_review']['verdict'], 'not_provided')
        self.assertFalse(result['business_verified'])
        self.assertFalse(result['migration_complete'])
        self.assertIsNone(result.get('failed_stage'))
        self.assertTrue((self.root/'run/agent-state.json').is_file())
        self.assertEqual(
            [stage['stage'] for stage in result['stages']],
            ['effective-page-closure', 'behavior-source-validation', 'target'],
        )

    def test_default_command_reports_review_failure_separately_from_business_gate(self):
        paths, _, _, review = self.behavior_materials()
        review['contract_sha256'] = '0' * 64
        for name, content, message in (
            ('stale', json.dumps(review), 'review contract is stale'),
            ('rejected', '{"verdict":"fail"}', 'pending/unresolved'),
            ('malformed', '{broken', 'cannot read source review'),
            ('absent', None, 'cannot read source review'),
        ):
            with self.subTest(review=name):
                if content is None:
                    paths['review'].unlink()
                else:
                    paths['review'].write_text(content)
                args = self.ai_args()
                args[args.index('--output-dir') + 1] = self.root/f'{name}-review-run'
                result = self.run_tool('migrate_compose_page.py', *args,
                    *self.behavior_args(paths, include_review=True))
                self.assertEqual(result['status'], 'ready_for_ai_implementation')
                validation = result['behavior_source_validation']
                self.assertEqual(validation['verdict'], 'pass')
                self.assertEqual(validation['semantic_review']['verdict'], 'fail')
                self.assertTrue(any(message in item for item in validation['semantic_review']['errors']))
                self.assertFalse(result['business_verified'])

    def test_default_command_rejects_behavior_specification_for_another_page_scope(self):
        from audit_behavior_source import digest
        paths, contract, inventory, review = self.behavior_materials()
        contract['scope']['included_scopes'] = ['page:another:Page']
        inventory['scope_id'] = 'page:another:Page'
        contract['source_closure']['inventory_sha256'] = digest(inventory)
        review['contract_sha256'] = digest(contract)
        paths['contract'].write_text(json.dumps(contract))
        paths['inventory'].write_text(json.dumps(inventory))
        paths['review'].write_text(json.dumps(review))
        result = self.run_tool('migrate_compose_page.py', *self.ai_args(),
            *self.behavior_args(paths), expected=1)
        validation = json.loads((self.root/'run/01-behavior-source-validation.stdout.log').read_text())
        self.assertTrue(any('scope does not match' in item for item in validation['errors']))
        self.assertFalse((self.root/'harmony').exists())

    def test_page_business_completion_rejects_missing_target_mapping(self):
        paths, _, _, _ = self.behavior_materials()
        results = paths['contract'].parent/'results.json'
        results.write_text(json.dumps({'schema_version':'behavior-scenario-results.v1',
            'contract_id':'page-contract', 'source_revision':json.loads(paths['inventory'].read_text())['source_revision'],
            'target_revision':'pending', 'scenarios':[{'id':'SCN-PAGE', 'verdict':'pass',
                'evidence':['missing.json']}]}))
        result = self.run_tool('migrate_compose_page.py', *self.ai_args(),
            *self.behavior_args(paths), '--behavior-scenario-results', results, expected=1)
        report = json.loads(result.stdout)
        self.assertEqual(report['failed_stage'], 'behavior-target-validation')
        self.assertEqual(report['status'], 'business_verification_failed')
        validation_stage = next(item for item in report['stages']
                                if item['stage'] == 'behavior-target-validation')
        validation = json.loads((self.root/'run'/validation_stage['stdout']).read_text())
        self.assertTrue(any('not implemented' in item for item in validation['errors']))
        self.assertFalse(report['business_verified'])

    def test_page_business_completion_rejects_missing_scenario_evidence(self):
        paths, _, inventory, _ = self.behavior_materials(implemented=True)
        results = paths['contract'].parent/'results.json'
        results.write_text(json.dumps({'schema_version':'behavior-scenario-results.v1',
            'contract_id':'page-contract', 'source_revision':inventory['source_revision'],
            'target_revision':'pending', 'scenarios':[{'id':'SCN-PAGE', 'verdict':'pass',
                'evidence':[]}]}))
        result = self.run_tool('migrate_compose_page.py', *self.ai_args(),
            *self.behavior_args(paths), '--behavior-scenario-results', results, expected=1)
        report = json.loads(result.stdout)
        validation_stage = next(item for item in report['stages']
                                if item['stage'] == 'behavior-target-validation')
        validation = json.loads((self.root/'run'/validation_stage['stdout']).read_text())
        self.assertTrue(any('lacks target evidence' in item for item in validation['errors']))
        self.assertFalse(report['business_verified'])

    def test_preinitialized_owned_target_completes_without_separate_contract_attachment(self):
        paths, _, inventory, _ = self.behavior_materials(implemented=True)
        target = self.root/'harmony'
        self.run_tool('init_harmony_project.py', '--output', target,
            '--project-name', 'TestPage', '--bundle-name', 'com.example.testpage',
            '--sdk-version', '6.0.0(20)')
        page = target/'entry/src/main/ets/pages/Index.ets'
        original_page = page.read_bytes()
        ready = self.run_tool('migrate_compose_page.py', *self.ai_args(),
            *self.behavior_args(paths))
        self.assertEqual(ready['status'], 'ready_for_ai_implementation')
        self.assertEqual(page.read_bytes(), original_page)
        self.run_page_evidence(ready['evidence_run_root'], target,
            inventory['scope_id'], 'preinitialized-page')
        receipt = json.loads((target/'.migration/evidence/preinitialized-page.json').read_text())
        results = paths['contract'].parent/'results.json'
        results.write_text(json.dumps({'schema_version':'behavior-scenario-results.v1',
            'contract_id':'page-contract', 'source_revision':inventory['source_revision'],
            'target_revision':receipt['target_revision'], 'scenarios':[{'id':'SCN-PAGE',
                'verdict':'pass', 'evidence':['.migration/evidence/preinitialized-page.json']}]}))
        args = self.ai_args()
        args[args.index('--output-dir') + 1] = self.root/'verified-run'
        verified = self.run_tool('migrate_compose_page.py', *args,
            *self.behavior_args(paths), '--behavior-scenario-results', results)
        self.assertEqual(verified['status'], 'page_business_verified')
        self.assertTrue(verified['business_verified'])
        self.assertEqual(page.read_bytes(), original_page)

        attached = target/'.migration/source-contract.json'
        original_contract = attached.read_bytes()
        for name, damaged in (('changed', b'{}'), ('missing', None)):
            with self.subTest(name=name):
                if damaged is None:
                    attached.unlink()
                else:
                    attached.write_bytes(damaged)
                args[args.index('--output-dir') + 1] = self.root/f'{name}-contract-run'
                rejected = self.run_tool('migrate_compose_page.py', *args,
                    *self.behavior_args(paths), expected=1)
                self.assertFalse(json.loads(rejected.stdout)['ok'])
                if damaged is None:
                    self.assertFalse(attached.exists())
                else:
                    self.assertEqual(attached.read_bytes(), damaged)
                attached.write_bytes(original_contract)

    def test_page_business_completion_accepts_current_attested_scenario_evidence(self):
        paths, _, inventory, _ = self.behavior_materials(implemented=True)
        scope_id = inventory['scope_id']
        ready = self.run_tool('migrate_compose_page.py', *self.ai_args(),
            *self.behavior_args(paths))
        self.assertEqual(ready['status'], 'ready_for_ai_implementation')
        target = self.root/'harmony'
        self.assertEqual(ready['evidence_run_root'], str(self.root/'run'))
        self.run_page_evidence(ready['evidence_run_root'], target, scope_id, 'page-behavior')
        receipt = json.loads(
            (target/'.migration/evidence/page-behavior.json').read_text())
        results = paths['contract'].parent/'results.json'
        results.write_text(json.dumps({'schema_version':'behavior-scenario-results.v1',
            'contract_id':'page-contract', 'source_revision':inventory['source_revision'],
            'target_revision':receipt['target_revision'], 'scenarios':[{'id':'SCN-PAGE',
                'verdict':'pass', 'evidence':['.migration/evidence/page-behavior.json']}]}))
        args = self.ai_args()
        args[args.index('--output-dir') + 1] = self.root/'verified-run'
        result = self.run_tool('migrate_compose_page.py', *args,
            *self.behavior_args(paths), '--behavior-scenario-results', results)
        self.assertEqual(result['status'], 'page_business_verified')
        self.assertTrue(result['business_verified'])
        self.assertTrue(result['behavior_target_validation']['runtime_complete'])
        self.assertEqual(result['behavior_target_validation']['semantic_review']['verdict'], 'not_provided')
        self.assertFalse(result['behavior_target_validation']['application_complete'])
        self.assertFalse(result['migration_complete'])
        self.assertFalse(result['implementation_complete'])
        self.assertEqual([item['stage'] for item in result['stages']],
            ['effective-page-closure', 'behavior-source-validation',
             'behavior-target-validation'])
        paths['review'].write_text('{"verdict":"fail"}')
        args[args.index('--output-dir') + 1] = self.root/'rejected-review-verified-run'
        independent = self.run_tool('migrate_compose_page.py', *args,
            *self.behavior_args(paths, include_review=True), '--behavior-scenario-results', results)
        self.assertTrue(independent['business_verified'])
        self.assertEqual(independent['behavior_target_validation']['semantic_review']['verdict'], 'fail')
        page = target/'entry/src/main/ets/pages/Index.ets'
        page.write_text(page.read_text() + '\n// changed after evidence capture\n')
        args[args.index('--output-dir') + 1] = self.root/'stale-evidence-run'
        rejected = self.run_tool('migrate_compose_page.py', *args,
            *self.behavior_args(paths), '--behavior-scenario-results', results, expected=1)
        self.assertFalse(json.loads(rejected.stdout)['business_verified'])
        validation = json.loads((self.root/'stale-evidence-run/behavior-target-validation.json').read_text())
        self.assertTrue(any('target revision is stale' in error for error in validation['errors']))

    def test_page_evidence_rejects_mismatched_and_stale_run_identity(self):
        paths, _, inventory, _ = self.behavior_materials(implemented=True)
        scope_id = inventory['scope_id']
        self.run_tool('migrate_compose_page.py', *self.ai_args(),
            *self.behavior_args(paths))
        state_path = self.root/'run/agent-state.json'
        original = json.loads(state_path.read_text())
        cases = (
            ('mismatched', ('paths', 'target'), str(self.root/'other-target'),
             'run paths do not belong'),
            ('stale', ('artifacts', 'contract_sha256'), '0' * 64,
             'migration contract is missing or changed'),
        )
        for name, keys, value, message in cases:
            with self.subTest(name=name):
                changed = json.loads(json.dumps(original))
                changed[keys[0]][keys[1]] = value
                state_path.write_text(json.dumps(changed))
                result = self.run_page_evidence(
                    self.root/'run', self.root/'harmony', scope_id,
                    f'page-{name}', expected=1)
                self.assertIn(message, result.stdout)
                self.assertFalse(
                    (self.root/f'harmony/.migration/evidence/page-{name}.json').exists())
        state_path.write_text(json.dumps(original))

    def test_default_command_does_not_require_generator_viewport_arguments(self):
        args = self.ai_args()
        for name in ('--viewport-width-dp', '--viewport-height-dp'):
            index = args.index(name)
            del args[index:index + 2]
        paths, _, _, _ = self.behavior_materials()
        result = self.run_tool('migrate_compose_page.py', *args, *self.behavior_args(paths))
        self.assertEqual(result['status'], 'ready_for_ai_implementation')
        self.assertEqual(
            [stage['stage'] for stage in result['stages']],
            ['effective-page-closure', 'behavior-source-validation', 'target'],
        )

    def test_default_command_requires_runtime_inputs_before_writing(self):
        args = self.full_args()
        args.remove('--deterministic-candidate')
        result = self.run_tool('migrate_compose_page.py', *args, expected=1)
        self.assertIn('--android-page-json', result.stdout)
        self.assertIn('--android-theme-facts', result.stdout)
        self.assertIn('--state-fixture', result.stdout)
        self.assertFalse((self.root/'run').exists())

    def test_unresolved_visibility_preserves_all_branches_for_business_specification(self):
        (self.source/'Page.kt').write_text('''package example
import androidx.compose.runtime.Composable
@Composable fun Page(showDetails: Boolean) {
  if (showDetails) { Text("Details") } else { Text("Summary") }
}
''')
        args = self.ai_args()
        del args[:4]
        args += ['--source', self.source]
        result = self.run_tool('migrate_compose_page.py', *args, expected=1)
        report = json.loads(result.stdout)
        self.assertEqual(report['failed_stage'], 'behavior-source-validation')
        self.assertEqual(report['status'], 'business_specification_required')
        self.assertEqual(report['ai_implementation']['runtime_state_selection'], 'unresolved')
        self.assertFalse(report['business_verified'])
        self.assertFalse(report['implementation_complete'])
        closure = json.loads(Path(report['effective_page_closure']['path']).read_text())
        self.assertEqual(closure['status'], 'candidate_requires_runtime_facts')
        alternatives = json.dumps(closure['unresolved_branch_components'])
        self.assertIn('Details', alternatives)
        self.assertIn('Summary', alternatives)
        self.assertTrue(Path(report['behavior_source_scope']).is_file())
        self.assertFalse((self.root/'harmony').exists())

    def test_unresolved_visibility_allows_reviewed_whole_page_handoff_not_completion(self):
        from audit_behavior_source import census, digest
        (self.source/'Page.kt').write_text('''package example
import androidx.compose.runtime.Composable
@Composable fun Page(showDetails: Boolean) {
  if (showDetails) { Text("Details") } else { Text("Summary") }
}
''')
        self.snapshot = self.root/'whole-page-snapshot'
        self.contract = self.root/'whole-page-contract.json'
        self.run_tool('prepare_safe_snapshot.py', '--source', self.source, '--snapshot', self.snapshot)
        self.run_tool('analyze_compose_project.py', '--snapshot', self.snapshot, '--output', self.contract)
        paths, contract, _, review = self.behavior_materials()
        # Test-only reviewed source model covers both branches, not a selected screenshot.
        contract['collection']['facts'].append({
            'id':'visibility', 'kind':'check', 'owner_id':'page',
            'contract_ids':[], 'source_inventory_ids':['INV-PAGE'],
            'anchor_ids':['source'], 'condition':'showDetails',
            'on_valid':'Text("Details")', 'on_invalid':'Text("Summary")',
            'availability':'available',
            'source_expressions':contract['collection']['facts'][0]['source_expressions'],
        })
        scope = json.loads((paths['contract'].parent/'closure.json').read_text())['business_transcription']['scope']
        decisions = {o['id'] for o in census(self.snapshot, scope)['obligations'] if o['kind'] == 'decision'}
        for binding in contract['source_closure']['bindings']:
            if binding['obligation_id'] in decisions:
                binding['record_ids'] = ['visibility']
        category = next(c for c in contract['collection']['categories']
                        if c['family'] == 'validation_security')
        category.update(disposition='applicable', record_ids=['visibility'])
        review['expectations'][0]['record_ids'].append('visibility')
        review['contract_sha256'] = digest(contract)
        paths['contract'].write_text(json.dumps(contract))
        paths['review'].write_text(json.dumps(review))
        result = self.run_tool('migrate_compose_page.py', *self.ai_args(), *self.behavior_args(paths))
        self.assertEqual(result['status'], 'ready_for_ai_implementation')
        self.assertEqual(result['ai_implementation']['runtime_state_selection'], 'unresolved')
        self.assertEqual(result['effective_page_closure']['status'], 'candidate_requires_runtime_facts')
        self.assertEqual(result['behavior_source_validation']['verdict'], 'pass')
        self.assertFalse(result['implementation_complete'])
        self.assertFalse(result['business_verified'])
        self.assertFalse(result['visual_verified'])
        self.assertEqual(result['deterministic_generation']['status'], 'not_run')
        self.assertTrue((self.root/'run/agent-state.json').is_file())

    def test_default_command_exposes_dynamic_collection_but_still_requires_behavior_specification(self):
        (self.source/'Page.kt').write_text('''package example
import androidx.compose.runtime.Composable
@Composable fun Page(items: List<String>) {
  Column { items.forEach { item -> Text(item) } }
}
''')
        args = self.ai_args()
        del args[:4]
        args += ['--source', self.source]
        result = self.run_tool('migrate_compose_page.py', *args, expected=1)
        report = json.loads(result.stdout)
        self.assertEqual(report['status'], 'business_specification_required')
        self.assertEqual(report['effective_page_closure']['status'], 'candidate_ready_for_ai')
        self.assertGreater(report['effective_page_closure']['unresolved_branch_component_count'], 0)
        self.assertEqual(report['ai_implementation']['runtime_state_selection'], 'resolved')
        self.assertEqual(report['ai_implementation']['dynamic_source_obligations'], 'required')
        self.assertFalse((self.root/'harmony').exists())

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
        self.assertIn('Caption({  })', Path(result['arkui']['output']).read_text())
        self.assertFalse(result['generation_complete'])
        self.assertGreater(result['diagnosis']['counts']['defaulted'], 0)
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
        args = self.ai_args()
        index = args.index('--state-fixture')
        args[index + 1] = fixture
        result = self.run_tool('migrate_compose_page.py', *args, expected=1)
        report = json.loads(result.stdout)
        self.assertEqual(report['failed_stage'], 'effective-page-closure')
        self.assertEqual(report['diagnosis']['issues'][0]['impact'], 'execution')
        self.assertIn(report['error'], report['diagnosis']['issues'][0]['reasons'])
        self.assertTrue(Path(report['diagnosis_report']).is_file())
        self.assertFalse((self.root/'harmony').exists())

    def test_deterministic_candidate_requires_a_viewport_before_writing(self):
        args = self.full_args()
        for name in ('--viewport-width-dp', '--viewport-height-dp'):
            index = args.index(name)
            del args[index:index + 2]
        result = self.run_tool('migrate_compose_page.py', *args, expected=1)
        self.assertIn('--deterministic-candidate requires', result.stdout)
        self.assertFalse((self.root/'run').exists())

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
