"""Independent source denominator, exercised through maintainer/normal CLIs."""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_behavior_collection import fixture
from test_behavior_contract_v2 import scenario_results
from audit_behavior_source import digest

SCRIPTS = Path(__file__).resolve().parent


def write_snapshot(root, files, revision='source-rev'):
    root.mkdir(parents=True, exist_ok=True)
    for path, text in files.items():
        destination = root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text)
    (root / '.android-to-harmony-safe.json').write_text(json.dumps({
        'schema': 'android-to-harmony.safe-snapshot.v1',
        'text_files': sorted(files), 'text_file_count': len(files),
        'text_file_sha256': {p: hashlib.sha256(t.encode()).hexdigest() for p, t in files.items()},
        'source_git': {'revision': revision},
    }))


def run_cli(script, *args):
    result = subprocess.run([sys.executable, '-B', str(SCRIPTS / script), *map(str, args)],
                            capture_output=True, text=True)
    return result, json.loads(result.stdout) if result.stdout.strip() else {}


def bind_source_closure(root, c, i):
    """Complete, independently understood portable refresh fixture; not a real-app oracle."""
    scope = {'schema_version': 'behavior-source-scope.v1', 'id': i['scope_id'],
             'kind': 'page', 'source_revision': i['source_revision'], 'entry_paths': ['Tasks.kt']}
    (root / 'scope.json').write_text(json.dumps(scope))
    result, census = run_cli('audit_behavior_source.py', 'census', '--snapshot', root / 'snapshot',
                            '--scope', root / 'scope.json')
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    # This portable control models the actual provided ViewModel, not an
    # imaginary rendered list or UI callback absent from its source snapshot.
    action = c['actions'][0]
    action.update(trigger='invoke refresh', guard='TasksViewModel instance',
        effects=['writes loading true then false on normal return'], observable_results=['loading toggles'])
    if any('repository.refresh()' in o['expression'] for o in census['obligations']):
        action['effects'].append('invokes repository.refresh between loading writes')
    for scenario in c['scenarios']:
        scenario.update(given='TasksViewModel instance', when='invoke refresh', then=['loading toggles'])
    c['collection']['facts'][0].update(trigger='invoke refresh')
    # Match existing evidence expressions, not generated claims of semantic meaning.
    c['source_closure'] = {'schema_version': 'behavior-source-closure.v1',
        'census_sha256': census['census_sha256'], 'inventory_sha256': digest(i), 'bindings': []}
    for obligation in census['obligations']:
        matches = [f['id'] for f in c['collection']['facts']
                   if obligation['expression'] in f.get('source_expressions', [])]
        if obligation['kind'] == 'declaration':
            matches = ['page']
        c['source_closure']['bindings'].append({'obligation_id': obligation['id'],
            'record_ids': matches, 'scenario_ids': ['SCN-REFRESH']})
    return census


def reviewed_fixture(root, c, census):
    review = {'schema_version': 'behavior-source-review.v1', 'verdict': 'pass',
        'reviewer': 'portable fixture author', 'scope_sha256': census['scope_sha256'],
        'census_sha256': census['census_sha256'], 'contract_sha256': digest(c),
        'unresolved': [], 'expectations': [{
            'id': 'refresh-loading', 'summary': 'Refresh writes loading true then false; no runtime proof.',
            'obligation_ids': [o['id'] for o in census['obligations']],
            'record_ids': ['page', 'act', 'state'], 'scenario_ids': ['SCN-REFRESH']}],
        'dependency_edges': census['dependency_edges'],
        'external_dependencies': census['external_dependencies']}
    (root / 'review.json').write_text(json.dumps(review))
    return review


class BehaviorSourceClosureTests(unittest.TestCase):
    def test_literal_before_bounded_dependency_keeps_exact_source_expressions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            files = {
                'Page.kt': 'package demo\nfun Page(worker: Worker) { worker.send() }\n',
                'Worker.kt': 'package demo\nprivate const val TAG = "Worker" // label\n'
                             'class Worker {\n'
                             '    fun unrelated() { service.start() }\n'
                             '    fun send() { log(TAG); disk.write() }\n'
                             '}\n',
            }
            write_snapshot(root / 'snapshot', files)
            scope = {'schema_version': 'behavior-source-scope.v1', 'id': 'page', 'kind': 'page',
                     'source_revision': 'source-rev', 'entry_paths': ['Page.kt'],
                     'entry_symbols': {'Page.kt': ['Page']}, 'definition_boundaries': [{
                         'path': 'Worker.kt', 'symbol': 'Worker',
                         'behavior_ranges': [{'start_line': 5, 'end_line': 5}],
                         'context_reason': 'Only send is reached; the other method remains reading context.',
                         'resolved_dependencies': [], 'unresolved': []}]}
            (root / 'scope.json').write_text(json.dumps(scope))
            result, report = run_cli('audit_behavior_source.py', 'census', '--snapshot',
                                    root / 'snapshot', '--scope', root / 'scope.json')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            expressions = [o['expression'] for o in report['obligations']]
            self.assertIn('fun send() { log(TAG); disk.write() }', expressions)
            self.assertFalse(any('unrelated' in e for e in expressions))
            for obligation in report['obligations']:
                self.assertIn(obligation['expression'], files[obligation['path']])

    def test_page_boundary_can_identify_one_same_named_extension_without_dropping_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            files = {
                'Page.kt': 'package demo\nfun Page(tag: Tag) { tag.toJson() }\n',
                'Types.kt': 'package demo\nclass Tag\nclass Task\n',
                'Json.kt': 'package demo\n'
                           'fun Tag.toJson() { saveTag() }\n'
                           'fun Task.toJson() { backgroundTask() }\n',
                'Save.kt': 'package demo\nfun saveTag() { disk.write() }\n',
                'Background.kt': 'package demo\nfun backgroundTask() { service.start() }\n',
            }
            write_snapshot(root / 'snapshot', files)
            scope = {'schema_version': 'behavior-source-scope.v1', 'id': 'page', 'kind': 'page',
                     'source_revision': 'source-rev', 'entry_paths': ['Page.kt'],
                     'entry_symbols': {'Page.kt': ['Page']}, 'definition_boundaries': [{
                         'path': 'Json.kt', 'symbol': 'toJson', 'definition_line': 3,
                         'behavior_ranges': [],
                         'context_reason': 'The page receiver is Tag, not Task; keep Task source as context.',
                         'resolved_dependencies': [
                             {'path': 'Json.kt', 'symbol': 'toJson', 'definition_line': 2}],
                         'unresolved': []}]}

            def check(candidate):
                (root / 'scope.json').write_text(json.dumps(candidate))
                return run_cli('audit_behavior_source.py', 'census', '--snapshot',
                               root / 'snapshot', '--scope', root / 'scope.json')

            result, report = check(scope)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            bodies = [o['expression'] for o in report['obligations'] if o['kind'] == 'callable']
            self.assertIn('fun Tag.toJson() { saveTag() }', bodies)
            self.assertFalse(any('backgroundTask' in body for body in bodies))
            self.assertNotIn('Background.kt', [f['path'] for f in report['files']])
            json_file = next(f for f in report['files'] if f['path'] == 'Json.kt')
            self.assertEqual(json_file['sha256'], hashlib.sha256(files['Json.kt'].encode()).hexdigest())
            self.assertEqual(report['reading_context'][0]['definition_line'], 3)
            for invalid in (None, 1, True, '3'):
                with self.subTest(definition_line=invalid):
                    candidate = copy.deepcopy(scope)
                    if invalid is None:
                        candidate['definition_boundaries'][0].pop('definition_line')
                    else:
                        candidate['definition_boundaries'][0]['definition_line'] = invalid
                    self.assertEqual(check(candidate)[0].returncode, 1)
            candidate = copy.deepcopy(scope)
            candidate['definition_boundaries'][0]['resolved_dependencies'][0].pop('definition_line')
            self.assertEqual(check(candidate)[0].returncode, 1)

    def test_grouped_source_bindings_preserve_coverage_and_review_checks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            c, i = fixture(root / 'snapshot', 'class TasksViewModel {\n var loading = false\n'
                          ' fun refresh() { loading = true; loading = false }\n}\n')
            c['collection']['facts'][0]['source_expressions'] = [
                'fun refresh() { loading = true; loading = false }', 'loading = true', 'loading = false']
            current = bind_source_closure(root, c, i)
            reviewed_fixture(root, c, current)
            old = copy.deepcopy(c['source_closure']['bindings'])
            groups = {}
            for binding in old:
                key = (tuple(binding['record_ids']), tuple(binding['scenario_ids']))
                group = groups.setdefault(key, {'obligation_ids': [],
                    'record_ids': binding['record_ids'], 'scenario_ids': binding['scenario_ids']})
                group['obligation_ids'].append(binding['obligation_id'])
            c['source_closure']['bindings'] = list(groups.values())
            self.assertLess(len(groups), len(old))
            def check(candidate):
                (root / 'contract.json').write_text(json.dumps(candidate))
                (root / 'inventory.json').write_text(json.dumps(i))
                return run_cli('validate_behavior_contract_v2.py', '--phase', 'source',
                    '--contract', root / 'contract.json', '--inventory', root / 'inventory.json',
                    '--snapshot', root / 'snapshot', '--source-scope', root / 'scope.json',
                    '--source-review', root / 'review.json')
            # Reformatting cannot transfer an approval bound to the old contract.
            result, report = check(c)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(report['semantic_review']['verdict'], 'fail')
            self.assertTrue(any('review contract is stale' in e for e in report['semantic_review']['errors']))
            reviewed_fixture(root, c, current)
            result, report = check(c)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(report['source_closure']['covered'], len(old))
            self.assertTrue(report['source_complete'])
            self.assertEqual(report['semantic_review']['verdict'], 'pass')
            self.assertFalse(report['runtime_complete'])
            grouped = copy.deepcopy(c)
            # Both serialized forms can coexist without losing any source obligations.
            group = c['source_closure']['bindings'].pop()
            c['source_closure']['bindings'].extend({'obligation_id': key,
                'record_ids': group['record_ids'], 'scenario_ids': group['scenario_ids']}
                for key in group['obligation_ids'])
            reviewed_fixture(root, c, current)
            self.assertEqual(check(c)[0].returncode, 0)
            for case in ('omitted', 'duplicate', 'unknown', 'ambiguous', 'empty', 'unbound-expression'):
                with self.subTest(case=case):
                    candidate = copy.deepcopy(grouped)
                    bindings = candidate['source_closure']['bindings']
                    if case == 'omitted':
                        bindings.pop()
                    elif case == 'duplicate':
                        bindings.append(old[0])
                    elif case == 'unknown':
                        bindings[0]['obligation_ids'].append('f' * 64)
                    elif case == 'ambiguous':
                        bindings[0]['obligation_id'] = old[0]['obligation_id']
                    elif case == 'empty':
                        bindings[0]['obligation_ids'] = []
                    else:
                        candidate['collection']['facts'][0]['source_expressions'].remove('loading = false')
                    reviewed_fixture(root, candidate, current)
                    result, report = check(candidate)
                    self.assertEqual(result.returncode, 1, result.stdout)
                    self.assertFalse(report['source_complete'])

    def test_page_boundary_retains_di_context_without_expanding_application_startup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            files = {
                'Page.kt': 'package demo\nfun Page(app: App) { app.repository.save() }\n',
                'App.kt': 'package demo\nclass App {\n val repository = Repo()\n'
                          ' fun onCreate() { Background().start() }\n}\n',
                'Repo.kt': 'package demo\nclass Repo {\n fun save() { if (ready) { persist() } }\n'
                           ' fun unused() { Background().start() }\n}\n',
                'Persist.kt': 'package demo\nfun persist() { disk.write() }\n',
                'Background.kt': 'package demo\nclass Background { fun start() {} }\n',
            }
            write_snapshot(root / 'snapshot', files)
            scope = {'schema_version': 'behavior-source-scope.v1', 'id': 'page', 'kind': 'page',
                     'source_revision': 'source-rev', 'entry_paths': ['Page.kt'],
                     'entry_symbols': {'Page.kt': ['Page']}, 'definition_boundaries': [
                         {'path': 'App.kt', 'symbol': 'App', 'behavior_ranges': [],
                          'context_reason': 'Already-created application; page uses its repository.',
                          'resolved_dependencies': [{'path': 'Repo.kt', 'symbol': 'Repo'}],
                          'unresolved': []},
                         {'path': 'Repo.kt', 'symbol': 'Repo',
                          'behavior_ranges': [{'start_line': 3, 'end_line': 3}],
                          'context_reason': 'Only save is invoked by this page.',
                          'resolved_dependencies': [], 'unresolved': []},
                     ]}
            (root / 'scope.json').write_text(json.dumps(scope))
            result, report = run_cli('audit_behavior_source.py', 'census', '--snapshot',
                                    root / 'snapshot', '--scope', root / 'scope.json')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual({r['symbol'] for r in report['obligations'] if r['kind'] == 'callable'},
                             {'Page', 'save', 'persist'})
            self.assertEqual({f['path'] for f in report['files']},
                             {'Page.kt', 'App.kt', 'Repo.kt', 'Persist.kt'})
            self.assertTrue(any(o['expression'] == 'if (ready)' for o in report['obligations']))
            self.assertEqual([r['symbol'] for r in report['reading_context']], ['App', 'Repo'])
            self.assertFalse(report['unresolved'])

            # Scope reduction never supplies behavior mappings or a review itself.
            contract = {'source_closure': {'schema_version': 'behavior-source-closure.v1',
                        'census_sha256': report['census_sha256'], 'inventory_sha256': digest({}),
                        'bindings': []}, 'scope': {'included_scopes': ['page']},
                        'identity': {'source_revision': 'source-rev'}}
            for name, value in [('contract', contract), ('inventory', {})]:
                (root / (name + '.json')).write_text(json.dumps(value))
            failed, rejected = run_cli('validate_behavior_contract_v2.py', '--phase', 'source',
                '--contract', root / 'contract.json', '--inventory', root / 'inventory.json',
                '--snapshot', root / 'snapshot', '--source-scope', root / 'scope.json')
            self.assertEqual(failed.returncode, 1)
            required = {o['id'] for o in report['obligations'] if o['kind'] in {'callable', 'decision'}}
            self.assertTrue(required.issubset(set(rejected['source_closure']['missing'])))
            for label, update in [
                ('page root', {'path': 'Page.kt', 'symbol': 'Page'}),
                ('missing dependency', {'resolved_dependencies': [{'path': 'Absent.kt', 'symbol': 'Repo'}]}),
                ('unmapped DI', {'resolved_dependencies': []}),
            ]:
                with self.subTest(label=label):
                    changed = copy.deepcopy(scope)
                    changed['definition_boundaries'][0].update(update)
                    (root / 'scope.json').write_text(json.dumps(changed))
                    failed, rejected = run_cli('audit_behavior_source.py', 'census', '--snapshot',
                        root / 'snapshot', '--scope', root / 'scope.json')
                    self.assertEqual(failed.returncode, 1, rejected)
            changed = copy.deepcopy(scope)
            changed['definition_boundaries'][0].update(resolved_dependencies=[], unresolved=['Unknown DI binding'])
            changed['definition_boundaries'].pop()
            (root / 'scope.json').write_text(json.dumps(changed))
            result, unresolved = run_cli('audit_behavior_source.py', 'census', '--snapshot',
                root / 'snapshot', '--scope', root / 'scope.json')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(unresolved['unresolved'], [{'path': 'App.kt', 'reason': 'Unknown DI binding'}])

    def test_page_boundary_cannot_slice_a_business_method_before_its_effect(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_snapshot(root / 'snapshot', {
                'Page.kt': 'package demo\nfun Page(repo: Repo) { repo.save() }\n',
                'Repo.kt': 'package demo\nclass Repo {\n fun save() {\n  check()\n  persist()\n }\n}\n',
            })
            scope = {'schema_version': 'behavior-source-scope.v1', 'id': 'page', 'kind': 'page',
                     'source_revision': 'source-rev', 'entry_paths': ['Page.kt'],
                     'definition_boundaries': [{'path': 'Repo.kt', 'symbol': 'Repo',
                         'behavior_ranges': [{'start_line': 4, 'end_line': 4}],
                         'context_reason': 'Attempt to keep only the check',
                         'resolved_dependencies': [], 'unresolved': []}]}
            (root / 'scope.json').write_text(json.dumps(scope))
            failed, rejected = run_cli('audit_behavior_source.py', 'census', '--snapshot',
                root / 'snapshot', '--scope', root / 'scope.json')
            self.assertEqual(failed.returncode, 1, rejected)
            self.assertIn('complete callable', str(rejected))

    def test_constructor_annotation_does_not_move_class_body_to_next_top_level_property(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_snapshot(root / 'snapshot', {
                'Page.kt': 'package demo\nfun Page(vm: VM) { vm.save() }\n',
                'VM.kt': 'package demo\n@Owner\nclass VM @Inject constructor() {\n'
                         ' fun save() { persist() }\n}\nval LocalVM = localOf<VM>()\n',
            })
            scope = {'schema_version': 'behavior-source-scope.v1', 'id': 'page', 'kind': 'page',
                     'source_revision': 'source-rev', 'entry_paths': ['Page.kt'],
                     'definition_boundaries': [{'path': 'VM.kt', 'symbol': 'VM',
                         'behavior_ranges': [{'start_line': 4, 'end_line': 4}],
                         'context_reason': 'Page invokes save on an injected VM.',
                         'resolved_dependencies': [], 'unresolved': []}]}
            (root / 'scope.json').write_text(json.dumps(scope))
            result, report = run_cli('audit_behavior_source.py', 'census', '--snapshot',
                root / 'snapshot', '--scope', root / 'scope.json')
            self.assertEqual(result.returncode, 0, report)
            self.assertIn('save', [o.get('symbol') for o in report['obligations']])
            self.assertNotIn('LocalVM', [d['symbol'] for d in report['reached_definitions']])

    def test_source_completion_cannot_satisfy_final_behavior_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            c, i = fixture(root / 'snapshot', 'class TasksViewModel {\n var loading = false\n'
                          ' fun refresh() { loading = true; loading = false }\n}\n')
            c['collection']['facts'][0]['source_expressions'] = [
                'fun refresh() { loading = true; loading = false }', 'loading = true', 'loading = false']
            census = bind_source_closure(root, c, i)
            reviewed_fixture(root, c, census)
            for name, value in [('contract', c), ('inventory', i)]:
                (root / (name + '.json')).write_text(json.dumps(value))
            args = ('--contract', root / 'contract.json', '--inventory', root / 'inventory.json',
                '--snapshot', root / 'snapshot', '--source-scope', root / 'scope.json',
                '--source-review', root / 'review.json')
            result, source = run_cli('validate_behavior_contract_v2.py', '--phase', 'source', *args)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(source['source_complete'])
            self.assertFalse(source['runtime_complete'])
            bindings = {'source_revision': 'source-rev', 'contract_sha256': digest(c),
                        'skill_tree_digest': 'portable-skill'}
            graph = {'schema': 'android-to-harmony.capability-graph.v1', **bindings,
                'coverage': {}, 'nodes': [{'id': 'business:refresh', 'layer': 'business',
                    'status': 'candidate', 'required_gates': ['behavior_contract']}]}
            bundle = {'schema': 'android-to-harmony.gate-evidence-bundle.v1',
                'graph_schema': graph['schema'], **bindings,
                'nodes': [{'node_id': 'business:refresh', 'status': 'verified', 'evidence_ids': ['source']}],
                'evidence': [{'id': 'source', **bindings, 'node_ids': ['business:refresh'],
                    'gate': 'behavior_contract', 'artifact_type': source['artifact_type'],
                    'passed': source['verdict'] == 'pass'}]}
            for name, value in [('graph', graph), ('bundle', bundle)]:
                (root / (name + '.json')).write_text(json.dumps(value))
            result, rejected = run_cli('aggregate_gate_evidence.py', '--graph', root / 'graph.json',
                '--evidence', root / 'bundle.json', '--output', root / 'aggregate.json')
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('cannot satisfy gate', rejected['error'])
            self.assertEqual(source['artifact_type'], 'behavior_source_validation')
            result, target = run_cli('validate_behavior_contract_v2.py', '--phase', 'target', *args)
            self.assertEqual(target['artifact_type'], 'behavior_contract_validation')
            self.assertEqual(result.returncode, 1)
            # Input-load failures must use the same phase-specific discriminator.
            for phase, expected in [('source', 'behavior_source_validation'),
                                    ('target', 'behavior_contract_validation')]:
                result, failure = run_cli('validate_behavior_contract_v2.py', '--phase', phase,
                    '--contract', root / 'absent.json', '--inventory', root / 'inventory.json')
                self.assertEqual(result.returncode, 1)
                self.assertEqual(failure['artifact_type'], expected)

    def test_review_requires_every_named_record_and_scenario(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            c, i = fixture(root / 'snapshot')
            c['collection']['facts'][0]['source_expressions'].extend([
                'fun refresh() { loading = true; repository.refresh(); loading = false }',
                'loading = true', 'loading = false'])
            census = bind_source_closure(root, c, i)
            review = reviewed_fixture(root, c, census)
            for name, value in [('contract', c), ('inventory', i)]:
                (root / (name + '.json')).write_text(json.dumps(value))
            def check():
                return run_cli('validate_behavior_contract_v2.py', '--phase', 'source',
                    '--contract', root / 'contract.json', '--inventory', root / 'inventory.json',
                    '--snapshot', root / 'snapshot', '--source-scope', root / 'scope.json',
                    '--source-review', root / 'review.json')
            result, control = check()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for field, missing in [('record_ids', 'MISSING-RECORD'), ('scenario_ids', 'MISSING-SCENARIO')]:
                with self.subTest(field=field):
                    changed = copy.deepcopy(review)
                    changed['expectations'][0][field].append(missing)
                    (root / 'review.json').write_text(json.dumps(changed))
                    result, rejected = check()
                    self.assertEqual(result.returncode, 0, result.stdout)
                    self.assertTrue(rejected['source_complete'])
                    self.assertEqual(rejected['semantic_review']['verdict'], 'fail')
            (root / 'review.json').write_text(json.dumps(review))
            i['items'][0]['summary'] = 'Different claimed business meaning after review'
            (root / 'inventory.json').write_text(json.dumps(i))
            result, rejected = check()
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertTrue(any('inventory' in e and 'stale' in e for e in rejected['errors']))

    def test_multiline_return_type_binds_body_and_property_accessors_keep_dependencies(self):
        callables = [
            'fun settle(): Unit\n{\n ledger.debit(10)\n}',
            'fun settle():\n Unit\n{\n ledger.debit(10)\n}',
            'fun settle():\n List<\n Int\n >\n{\n return listOf(ledger.debit(10))\n}',
            'fun settle():\n List<\n Int\n >\n=\n listOf(ledger.debit(10))',
        ]
        abstract = 'fun ready():\n List<\n Int\n >'
        for callable_source in callables:
            with self.subTest(source=callable_source), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                write_snapshot(root / 'snapshot', {
                    'Entry.kt': 'package demo\n' + callable_source + '\ninterface Boundary {\n'
                        + abstract + '\n fun next(): Unit\n companion object { val version = 5 }\n}\n',
                    'Dependencies.kt': 'package demo\nval ledger: Ledger\n get() { return Ledger() }\n',
                    'Ledger.kt': 'package demo\nclass Ledger { fun debit(amount: Int): Int = amount }\n',
                })
                scope = {'schema_version': 'behavior-source-scope.v1', 'id': 'settlement', 'kind': 'flow',
                         'source_revision': 'source-rev', 'entry_paths': ['Entry.kt']}
                (root / 'scope.json').write_text(json.dumps(scope))
                result, census = run_cli('audit_behavior_source.py', 'census', '--snapshot',
                    root / 'snapshot', '--scope', root / 'scope.json')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                functions = {o['symbol']: o['expression'] for o in census['obligations'] if o['kind'] == 'callable'}
                self.assertEqual(functions['settle'], callable_source)
                self.assertEqual(functions['ready'], abstract)
                self.assertEqual(functions['next'], 'fun next(): Unit')
                self.assertFalse(census['unresolved'])
                self.assertIn('Ledger.kt', [f['path'] for f in census['files']])
                self.assertTrue(any(o['expression'] == 'return Ledger()' for o in census['obligations']))

    def test_reached_properties_generic_helpers_and_aliases_preserve_complete_definitions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_snapshot(root / 'snapshot', {
                'Entry.kt': 'package demo\nimport store.persist as save\n'
                    'fun send() { ledger.debit(10); save(10) }\n',
                'Dependencies.kt': 'package demo\nval ledger = Ledger()\n'
                    'fun unrelatedScreen() { Unrelated.render() }\n',
                'Ledger.kt': 'package demo\nclass Ledger { var balance = 100; '
                    'fun debit(amount: Int) { balance -= amount }; fun refund() { balance += 10 } }\n',
                'Store.kt': 'package store\nfun <T> persist(value: T) { println(value) }\n',
                'Unrelated.kt': 'package demo\nobject Unrelated { fun render() {} }\n',
            })
            scope = {'schema_version': 'behavior-source-scope.v1', 'id': 'transfer', 'kind': 'flow',
                     'source_revision': 'source-rev', 'entry_paths': ['Entry.kt']}
            (root / 'scope.json').write_text(json.dumps(scope))
            result, census = run_cli('audit_behavior_source.py', 'census', '--snapshot',
                root / 'snapshot', '--scope', root / 'scope.json')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual({f['path'] for f in census['files']},
                             {'Entry.kt', 'Dependencies.kt', 'Ledger.kt', 'Store.kt'})
            callables = {r['symbol'] for r in census['obligations'] if r['kind'] == 'callable'}
            self.assertEqual(callables, {'send', 'debit', 'refund', 'persist'})
            self.assertFalse(census['unresolved'], census['unresolved'])

    def test_blocked_source_cannot_disappear_from_whole_app_or_referenced_dependency(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_snapshot(root / 'snapshot', {'Entry.kt':
                'package demo\nimport demo.MissingRepo\nfun send(repo: MissingRepo) { repo.send() }\n'})
            marker = root / 'snapshot/.android-to-harmony-safe.json'
            manifest = json.loads(marker.read_text())
            manifest['blocked_files'] = [{'path': 'MissingRepo.kt', 'reason': 'potential_credential'}]
            marker.write_text(json.dumps(manifest))
            for kind in ('flow', 'application'):
                scope = {'schema_version': 'behavior-source-scope.v1', 'id': 'send', 'kind': kind,
                    'source_revision': 'source-rev', 'entry_paths': ['Entry.kt']}
                (root / 'scope.json').write_text(json.dumps(scope))
                result, census = run_cli('audit_behavior_source.py', 'census', '--snapshot',
                    root / 'snapshot', '--scope', root / 'scope.json')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertTrue(any(x['path'] == 'MissingRepo.kt' for x in census['unresolved']), census)

    def test_unavailable_project_import_is_not_treated_as_an_external_library(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_snapshot(root / 'snapshot', {'Entry.kt':
                'package demo\nimport demo.generated.loadLedger as load\nfun send() { load().debit() }\n'})
            scope = {'schema_version': 'behavior-source-scope.v1', 'id': 'send', 'kind': 'flow',
                     'source_revision': 'source-rev', 'entry_paths': ['Entry.kt']}
            (root / 'scope.json').write_text(json.dumps(scope))
            result, census = run_cli('audit_behavior_source.py', 'census', '--snapshot',
                root / 'snapshot', '--scope', root / 'scope.json')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(any(x.get('dependency') == 'demo.generated.loadLedger'
                                for x in census['unresolved']), census)

    def test_generated_android_r_import_is_a_platform_resource_dependency(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_snapshot(root / 'snapshot', {'Entry.kt':
                'package demo\nimport demo.R\nfun title(): Int = R.string.title\n'})
            scope = {'schema_version': 'behavior-source-scope.v1', 'id': 'title', 'kind': 'page',
                     'source_revision': 'source-rev', 'entry_paths': ['Entry.kt']}
            (root / 'scope.json').write_text(json.dumps(scope))
            result, census = run_cli('audit_behavior_source.py', 'census', '--snapshot',
                root / 'snapshot', '--scope', root / 'scope.json')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(census['unresolved'], census)
            self.assertIn(
                {'from_path': 'Entry.kt', 'import': 'demo.R'},
                census['external_dependencies'],
            )

    def test_target_requires_current_attested_device_receipt_and_named_scenario(self):
        # Existing external-device boundary fixture executes the real evidence
        # runner. Its fake HDC is test data, never public-project runtime evidence.
        from test_evidence_runner import EvidenceRunnerTests
        owner = EvidenceRunnerTests()
        owner.setUp()
        self.addCleanup(owner.tearDown)
        root = owner.run_root
        marker = root / 'snapshot/.android-to-harmony-safe.json'
        origin = json.loads(marker.read_text())
        c, i = fixture(root / 'snapshot', 'class TasksViewModel {\n var loading = false\n'
                      ' fun refresh() { loading = true; loading = false }\n}\n')
        manifest = json.loads(marker.read_text())
        manifest.update(origin)
        marker.write_text(json.dumps(manifest))
        state_path = root / 'agent-state.json'
        state = json.loads(state_path.read_text())
        state['artifacts']['snapshot_manifest_sha256'] = hashlib.sha256(marker.read_bytes()).hexdigest()
        state_path.write_text(json.dumps(state))
        c['collection']['facts'][0]['source_expressions'] = [
            'fun refresh() { loading = true; loading = false }', 'loading = true', 'loading = false']
        implementation = owner.target / 'entry/src/main/ets/model/TasksViewModel.ets'
        implementation.parent.mkdir(parents=True, exist_ok=True)
        implementation.write_text('export class TasksViewModel { refresh(): void {} }\n')
        for relative in ('entry/src/main/ets/a/Duplicate.ets',
                         'entry/src/main/ets/b/Duplicate.ets',
                         'entry/src/ohosTest/ets/test/OnlyTest.ets'):
            extra = owner.target / relative
            extra.parent.mkdir(parents=True, exist_ok=True)
            extra.write_text('export function refresh(): void {}\n')
        c['traceability']['target_implementation'][0].update(status='implemented', target='TasksViewModel.ets#refresh')
        c['scenarios'][0]['target_test'] = 'DemoUiTest.opensDemo'
        census = bind_source_closure(root, c, i)
        reviewed_fixture(root, c, census)
        tool = owner.make_tool('hdc')
        haps = [owner.target / 'entry/build/default' / name for name in ('entry-default.hap', 'entry-ohosTest.hap')]
        haps[0].parent.mkdir(parents=True)
        for hap in haps:
            hap.write_bytes(b'controlled-test-hap')
        execution = owner.run_runner('run', 'ui_tests', 'behavior', '--slice-id', 'tasks',
            '--demand-id', 'SCN-REFRESH', '--test-report-from-stdout', '--test-report-format', 'hypium-text',
            '--ui-main-hap', str(haps[0]), '--ui-test-hap', str(haps[1]),
            '--device-kind', 'emulator', '--device-id', 'emulator-1',
            '--os-version', 'HarmonyOS 6', '--api-version', '24', '--', str(tool), '-t', 'emulator-1',
            'shell', 'aa', 'test', '-b', 'com.example.evidence', '-m', 'entry_test',
            '-s', 'unittest', 'OpenHarmonyTestRunner')
        self.assertEqual(execution.returncode, 0, execution.stdout + execution.stderr)
        receipt = owner.evidence('behavior')
        results = scenario_results()
        results['target_revision'] = receipt['target_revision']
        results['scenarios'][0]['evidence'] = ['.migration/evidence/behavior.json']
        for name, value in [('contract', c), ('inventory', i), ('results', results)]:
            (root / (name + '.json')).write_text(json.dumps(value))
        def check():
            return run_cli('validate_behavior_contract_v2.py', '--phase', 'target',
                '--contract', root / 'contract.json', '--inventory', root / 'inventory.json',
                '--snapshot', root / 'snapshot', '--source-scope', root / 'scope.json',
                '--source-review', root / 'review.json', '--scenario-results', root / 'results.json',
                '--target', owner.target)
        result, report = check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(report['source_complete'])
        self.assertTrue(report['runtime_complete'])
        self.assertEqual(report['artifact_type'], 'behavior_contract_validation')
        self.assertFalse(report['application_complete'])
        self.assertEqual(report['scenario_results']['percent'], 100.0)
        # A reviewed label and valid execution receipt cannot point at absent,
        # out-of-target, or non-production implementation files.
        mapping = c['traceability']['target_implementation'][0]
        for invalid in ('Missing.ets#refresh', '../TasksViewModel.ets#refresh',
                        'entry/hvigorfile.ts#refresh',
                        'Duplicate.ets#refresh',
                        'entry/src/ohosTest/ets/test/OnlyTest.ets#refresh',
                        'entry/src/main/ets/model/TasksViewModel.ets#'):
            with self.subTest(implementation=invalid):
                mapping['target'] = invalid
                reviewed_fixture(root, c, census)
                (root / 'contract.json').write_text(json.dumps(c))
                rejected, failure = check()
                self.assertEqual(rejected.returncode, 1, rejected.stdout)
                self.assertFalse(failure['runtime_complete'])
                self.assertTrue(any('target implementation source' in e for e in failure['errors']))
        mapping['target'] = 'entry/src/main/ets/model/TasksViewModel.ets#TasksViewModel.refresh'
        reviewed_fixture(root, c, census)
        (root / 'contract.json').write_text(json.dumps(c))
        accepted, report = check()
        self.assertEqual(accepted.returncode, 0, accepted.stdout)
        # Same code with a new snapshot identity still needs a matching execution receipt.
        original_marker = marker.read_text()
        changed_manifest = json.loads(original_marker)
        changed_manifest['audit_revision'] = 'new-snapshot-identity'
        marker.write_text(json.dumps(changed_manifest))
        changed_census = bind_source_closure(root, c, i)
        reviewed_fixture(root, c, changed_census)
        (root / 'contract.json').write_text(json.dumps(c))
        failed, rejected = check()
        self.assertEqual(failed.returncode, 1, failed.stdout)
        self.assertTrue(any('source identity' in e for e in rejected['errors']))
        marker.write_text(original_marker)
        census = bind_source_closure(root, c, i)
        # An otherwise valid result cannot stand for a test absent from the captured run.
        c['scenarios'][0]['target_test'] = 'DemoUiTest.unexecuted'
        reviewed_fixture(root, c, census)
        (root / 'contract.json').write_text(json.dumps(c))
        failed, rejected = check()
        self.assertEqual(failed.returncode, 1, failed.stdout)
        self.assertFalse(rejected['runtime_complete'])
        c['scenarios'][0]['target_test'] = 'DemoUiTest.opensDemo'
        reviewed_fixture(root, c, census)
        (root / 'contract.json').write_text(json.dumps(c))
        (owner.target / 'entry/hvigorfile.ts').write_text('// target changed\n')
        failed, rejected = check()
        self.assertEqual(failed.returncode, 1, failed.stdout)
        self.assertTrue(any('revision' in e for e in rejected['errors']))

    def test_target_cannot_pass_with_an_unexecuted_evidence_filename(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            c, i = fixture(root / 'snapshot', 'class TasksViewModel {\n var loading = false\n'
                          ' fun refresh() { loading = true; loading = false }\n}\n')
            c['collection']['facts'][0]['source_expressions'] = [
                'fun refresh() { loading = true; loading = false }', 'loading = true', 'loading = false']
            c['traceability']['target_implementation'][0].update(status='implemented', target='Index.ets#refresh')
            census = bind_source_closure(root, c, i)
            reviewed_fixture(root, c, census)
            for name, value in [('contract', c), ('inventory', i), ('results', scenario_results())]:
                (root / (name + '.json')).write_text(json.dumps(value))
            result, report = run_cli('validate_behavior_contract_v2.py', '--phase', 'target',
                '--contract', root / 'contract.json', '--inventory', root / 'inventory.json',
                '--snapshot', root / 'snapshot', '--source-scope', root / 'scope.json',
                '--source-review', root / 'review.json', '--scenario-results', root / 'results.json')
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertTrue(report['source_complete'])
            self.assertFalse(report['runtime_complete'])
            self.assertTrue(any('execution evidence' in e for e in report['errors']))
            self.assertEqual(report['scenario_results']['percent'], 0.0)

    def test_local_helper_and_nested_callback_decisions_remain_in_denominator(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_snapshot(root / 'snapshot', {
                'Transfer.kt': 'package demo\nfun transfer() {\n'
                    ' runTask(callback = { if (ready) { applyFee() } else { cancel() } })\n}\n',
                'Fee.kt': 'package demo\nfun applyFee() { total -= 5 }\n',
            })
            scope = {'schema_version': 'behavior-source-scope.v1', 'id': 'transfer',
                'kind': 'flow', 'source_revision': 'source-rev', 'entry_paths': ['Transfer.kt']}
            (root / 'scope.json').write_text(json.dumps(scope))
            result, census = run_cli('audit_behavior_source.py', 'census', '--snapshot',
                root / 'snapshot', '--scope', root / 'scope.json')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('Fee.kt', [x['path'] for x in census['files']])
            decisions = [o['expression'] for o in census['obligations'] if o['kind'] == 'decision']
            self.assertIn('if (ready)', decisions)
            self.assertIn('else', decisions)

    def test_normal_gate_accepts_complete_body_mapping_and_rejects_joint_delete_and_new_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            text = ('class TasksViewModel {\n var loading = false\n'
                    ' fun refresh() { loading = true; loading = false }\n}\n')
            c, i = fixture(root / 'snapshot', text)
            c['collection']['facts'][0]['source_expressions'] = [
                'fun refresh() { loading = true; loading = false }',
                'loading = true', 'loading = false']
            census = bind_source_closure(root, c, i)
            reviewed_fixture(root, c, census)
            def check(candidate):
                (root / 'contract.json').write_text(json.dumps(candidate))
                (root / 'inventory.json').write_text(json.dumps(i))
                return run_cli('validate_behavior_contract_v2.py', '--phase', 'source',
                    '--contract', root / 'contract.json', '--inventory', root / 'inventory.json',
                    '--snapshot', root / 'snapshot', '--source-scope', root / 'scope.json',
                    '--source-review', root / 'review.json')
            result, report = check(c)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(report['source_closure']['coverage_complete'])
            self.assertTrue(report['source_complete'])
            self.assertFalse(report['runtime_complete'])
            self.assertFalse(report['application_complete'])
            # Independently deleting a discovered operation's inventory/fact cannot shrink census.
            changed = copy.deepcopy(c)
            state_ids = {o['id'] for o in census['obligations'] if o['kind'] == 'state'}
            changed['source_closure']['bindings'] = [b for b in changed['source_closure']['bindings']
                                                     if b['obligation_id'] not in state_ids]
            changed['collection']['facts'] = [f for f in changed['collection']['facts'] if f['id'] != 'state']
            changed['collection']['categories'][1]['record_ids'].remove('state')
            changed['collection']['entities'][0]['source_inventory_ids'].remove('INV-STATE-LOADING')
            changed['states'] = []
            i['items'] = [x for x in i['items'] if x['id'] != 'INV-STATE-LOADING']
            failed, rejected = check(changed)
            self.assertEqual(failed.returncode, 1, failed.stdout)
            self.assertEqual(set(rejected['source_closure']['missing']), state_ids)
            # Fresh safe source with an added command invalidates even previously complete bindings.
            write_snapshot(root / 'snapshot', {'Tasks.kt': text.replace('\n}', '\n fun delete() {}\n}')})
            failed, rejected = check(c)
            self.assertEqual(failed.returncode, 1, failed.stdout)
            self.assertTrue(any('census' in e for e in rejected['errors']))

    def test_complete_source_gate_does_not_require_independent_review(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            c, i = fixture(root / 'snapshot', 'class TasksViewModel {\n var loading = false\n'
                          ' fun refresh() { loading = true; loading = false }\n}\n')
            c['collection']['facts'][0]['source_expressions'] = [
                'fun refresh() { loading = true; loading = false }', 'loading = true', 'loading = false']
            c['collection']['status'] = 'complete'
            bind_source_closure(root, c, i)
            (root / 'contract.json').write_text(json.dumps(c))
            (root / 'inventory.json').write_text(json.dumps(i))
            result, report = run_cli('validate_behavior_contract_v2.py', '--phase', 'source',
                '--contract', root / 'contract.json', '--inventory', root / 'inventory.json',
                '--snapshot', root / 'snapshot', '--source-scope', root / 'scope.json')
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertTrue(report['source_closure']['coverage_complete'])
            self.assertTrue(report['source_complete'])
            self.assertEqual(report['semantic_review'], {'verdict': 'not_provided', 'errors': []})
            self.assertFalse(report['runtime_complete'])
            for content in ('{"verdict":"fail"}', '{"verdict":"pass"}', '[]', '{broken', None):
                with self.subTest(review=content):
                    review_path = root / 'optional-review.json'
                    if content is None:
                        review_path.unlink()
                    else:
                        review_path.write_text(content)
                    result, report = run_cli('validate_behavior_contract_v2.py', '--phase', 'source',
                        '--contract', root / 'contract.json', '--inventory', root / 'inventory.json',
                        '--snapshot', root / 'snapshot', '--source-scope', root / 'scope.json',
                        '--source-review', review_path)
                    self.assertEqual(result.returncode, 0, result.stdout)
                    self.assertTrue(report['source_complete'])
                    self.assertEqual(report['semantic_review']['verdict'], 'fail')
                    self.assertTrue(report['semantic_review']['errors'])
            for status in ('pending', 'unknown', None):
                with self.subTest(collection_status=status):
                    c['collection']['status'] = status
                    (root / 'contract.json').write_text(json.dumps(c))
                    result, report = run_cli('validate_behavior_contract_v2.py', '--phase', 'source',
                        '--contract', root / 'contract.json', '--inventory', root / 'inventory.json',
                        '--snapshot', root / 'snapshot', '--source-scope', root / 'scope.json')
                    self.assertEqual(result.returncode, 1, result.stdout)
                    self.assertFalse(report['collection_valid'])
                    self.assertTrue(any('collection' in error for error in report['errors']))
            c['collection']['status'] = 'complete'
            # Without review, dropping a bound source operation still fails mechanically.
            missing = c['source_closure']['bindings'].pop()['obligation_id']
            (root / 'contract.json').write_text(json.dumps(c))
            result, report = run_cli('validate_behavior_contract_v2.py', '--phase', 'source',
                '--contract', root / 'contract.json', '--inventory', root / 'inventory.json',
                '--snapshot', root / 'snapshot', '--source-scope', root / 'scope.json')
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn(missing, report['source_closure']['missing'])
            self.assertFalse(report['source_complete'])

    def test_census_discovers_whole_functions_branches_and_local_dependency_without_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_snapshot(root / 'snapshot', {
                'Transfer.kt': 'package demo\nclass Transfer(val repo: Ledger) {\n'
                    ' fun send(amount: Int) { if (amount <= 0) { return }; repo.debit(amount) }\n'
                    ' fun cancel() = repo.cancel()\n}\n',
                'Ledger.kt': 'package demo\nclass Ledger {\n'
                    ' var balance = 100\n'
                    ' fun debit(amount: Int) { balance -= amount }\n'
                    ' fun cancel() { balance = 100 }\n}\n',
                'Unrelated.kt': 'package elsewhere\nclass Unrelated { fun ignore() {} }\n',
            })
            scope = {'schema_version': 'behavior-source-scope.v1', 'id': 'transfer',
                     'kind': 'flow', 'source_revision': 'source-rev',
                     'entry_paths': ['Transfer.kt']}
            (root / 'scope.json').write_text(json.dumps(scope))
            result, census = run_cli('audit_behavior_source.py', 'census', '--snapshot',
                root / 'snapshot', '--scope', root / 'scope.json')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual([x['path'] for x in census['files']], ['Ledger.kt', 'Transfer.kt'])
            self.assertEqual({(o['path'], o['symbol']) for o in census['obligations']
                              if o['kind'] == 'callable'},
                             {('Transfer.kt', 'send'), ('Transfer.kt', 'cancel'),
                              ('Ledger.kt', 'debit'), ('Ledger.kt', 'cancel')})
            send = next(o for o in census['obligations'] if o.get('symbol') == 'send')
            self.assertIn('repo.debit(amount)', send['expression'])
            self.assertTrue(any(o['kind'] == 'decision' and 'amount <= 0' in o['expression']
                                for o in census['obligations']))
            self.assertTrue(any(o['kind'] == 'operation' and 'balance -= amount' in o['expression']
                                for o in census['obligations']))
            # The denominator is independent and stable: no contract or inventory accepted.
            repeat, same = run_cli('audit_behavior_source.py', 'census', '--snapshot',
                root / 'snapshot', '--scope', root / 'scope.json')
            self.assertEqual(census, same)

    def test_joint_inventory_and_fact_omission_cannot_receive_source_completion(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            c, i = fixture(root / 'snapshot')
            (root / 'contract.json').write_text(json.dumps(c))
            (root / 'inventory.json').write_text(json.dumps(i))
            result, report = run_cli('validate_behavior_contract_v2.py', '--phase', 'source',
                '--contract', root / 'contract.json', '--inventory', root / 'inventory.json',
                '--snapshot', root / 'snapshot')
            # No independent source denominator. Old inventory/collection consistency is insufficient.
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertFalse(report['source_complete'])
            self.assertTrue(any('source closure' in e for e in report['errors']))


if __name__ == '__main__':
    unittest.main()
