"""Portable behavior tests through the collection and normal validator CLIs."""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_behavior_contract_v2 import contract, inventory, scenario_results
from validate_behavior_contract_v2 import validate

SCRIPTS = Path(__file__).resolve().parent
FAMILIES = ["ownership", "events_state_navigation", "data", "async_lifecycle",
            "validation_security", "scenarios_evidence"]


def fixture(root, text=None):
    root.mkdir(exist_ok=True)
    text = text or ('class TasksViewModel {\n'
            ' var loading = false\n'
            ' fun refresh() { loading = true; repository.refresh(); loading = false }\n'
            '}\n')
    (root / 'Tasks.kt').write_text(text)
    digest = hashlib.sha256(text.encode()).hexdigest()
    (root / '.android-to-harmony-safe.json').write_text(json.dumps({
        'schema': 'android-to-harmony.safe-snapshot.v1', 'text_files': ['Tasks.kt'],
        'text_file_count': 1, 'text_file_sha256': {'Tasks.kt': digest},
        'source_git': {'revision': 'source-rev'},
    }))
    c, i = contract(), inventory()
    for item in i['items']:
        item['source_evidence'] = ['source']
    c['scenarios'][0]['android_evidence'] = ['source']
    c['collection'] = {
        'schema_version': 'behavior-collection.v1', 'status': 'reviewed',
        'source_revision': 'source-rev',
        'anchors': [{'id': 'source', 'kind': 'source', 'path': 'Tasks.kt',
                     'start_line': 1, 'end_line': 4, 'file_sha256': digest,
                     'span_sha256': digest}],
        'entities': [{'id': 'page', 'kind': 'page', 'owner_id': None,
                      'source_inventory_ids': ['INV-ACTION-REFRESH', 'INV-STATE-LOADING'],
                      'anchor_ids': ['source']}],
        'relationships': [],
        'facts': [
            {'id': 'act', 'kind': 'action', 'owner_id': 'page',
             'contract_ids': ['ACTION-REFRESH'], 'source_inventory_ids': ['INV-ACTION-REFRESH'],
             'anchor_ids': ['source'], 'trigger': 'tap refresh', 'handler': 'refresh',
             'outcomes': ['loading true then false on normal return'],
             'source_expressions': ['fun refresh()', 'repository.refresh()']},
            {'id': 'state', 'kind': 'state', 'owner_id': 'page',
             'contract_ids': ['STATE-LOADING'], 'source_inventory_ids': ['INV-STATE-LOADING'],
             'anchor_ids': ['source'], 'initial': 'false', 'lifetime': 'ViewModel',
             'writes': ['act'], 'source_expressions': ['var loading = false']},
            {'id': 'scenario', 'kind': 'scenario', 'owner_id': 'page',
             'contract_ids': ['SCN-REFRESH'], 'source_inventory_ids': ['INV-ACTION-REFRESH'],
             'anchor_ids': ['source'], 'action_ids': ['act'], 'given': 'page shown',
             'when': 'refresh', 'then': ['loading toggles'], 'evidence_kind': 'source'},
        ],
        'categories': [],
    }
    for family in FAMILIES:
        refs = {'ownership': ['page'], 'events_state_navigation': ['act', 'state'],
                'scenarios_evidence': ['scenario']}.get(family, [])
        c['collection']['categories'].append({
            'family': family, 'disposition': 'applicable' if refs else 'not_applicable',
            'rationale': 'Bounded UI handler source only; dependency internals outside scope',
            'anchor_ids': ['source'], 'record_ids': refs,
        })
    return c, i


class BehaviorCollectionTests(unittest.TestCase):
    def assert_collection(self, result, verdict):
        # The public normal-gate response separates collection correctness from
        # independently reviewed source completeness and executed target parity.
        self.assertEqual(json.loads(result.stdout)['collection']['verdict'], verdict,
                         result.stdout + result.stderr)

    def test_nonempty_collection_cannot_bypass_normal_gate(self):
        c = contract()
        c['collection'] = {'status': 'reviewed'}
        result = validate(c, inventory(), phase='source')
        self.assertEqual(result['verdict'], 'fail')
        self.assertTrue(any('collection' in e for e in result['errors']))

    def run_validation(self, root, c, i, phase='source'):
        (root / 'contract.json').write_text(json.dumps(c))
        (root / 'inventory.json').write_text(json.dumps(i))
        command = [sys.executable, '-B', str(SCRIPTS / 'validate_behavior_contract_v2.py'),
            '--phase', phase, '--contract', str(root / 'contract.json'), '--inventory',
            str(root / 'inventory.json'), '--snapshot', str(root / 'snapshot')]
        if phase == 'target':
            (root / 'results.json').write_text(json.dumps(scenario_results()))
            command.extend(['--scenario-results', str(root / 'results.json')])
        return subprocess.run(command, text=True, capture_output=True)

    def test_inventory_behavior_requires_matching_fact_in_both_normal_phases(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            c, i = fixture(root / 'snapshot')
            i['items'].append({'id': 'INV-DATA', 'category': 'data_flow',
                               'record_kind': 'data', 'summary': 'Repository refresh',
                               'source_evidence': ['source']})
            c['data_flows'].append({'id': 'reload', 'source_inventory_ids': ['INV-DATA']})
            c['collection']['entities'].append({'id': 'repo', 'kind': 'dependency',
                'owner_id': 'page', 'symbol': 'Repository', 'anchor_ids': ['source'],
                'source_inventory_ids': ['INV-DATA']})
            c['collection']['facts'].append({'id': 'reload', 'kind': 'data', 'owner_id': 'page',
                'source_inventory_ids': ['INV-DATA'], 'anchor_ids': ['source'],
                'operation': 'refresh', 'dependency_id': 'repo', 'inputs': ['none'],
                'outputs': ['Unit'], 'availability': 'available',
                'source_expressions': ['repository.refresh()']})
            c['collection']['categories'][0]['record_ids'].append('repo')
            c['collection']['categories'][2].update(disposition='applicable', record_ids=['reload'])
            # Context and scenario associations remain; neither replaces the data fact.
            c['collection']['facts'][2]['source_inventory_ids'].append('INV-DATA')
            c['traceability']['target_implementation'][0].update(status='implemented', target='Index.ets#refresh')
            for phase in ('source', 'target'):
                with self.subTest(phase=phase):
                    good = self.run_validation(root, c, i, phase)
                    self.assert_collection(good, 'pass')
                    changed = copy.deepcopy(c)
                    changed['collection']['facts'] = [f for f in changed['collection']['facts'] if f['id'] != 'reload']
                    changed['collection']['categories'][2].update(disposition='not_applicable', record_ids=[])
                    bad = self.run_validation(root, changed, i, phase)
                    self.assert_collection(bad, 'fail')
                    self.assertIn('INV-DATA', json.loads(bad.stdout)['collection']['source_fact_coverage']['missing'])
                    wrong_kind = copy.deepcopy(i)
                    wrong_kind['items'][-1]['record_kind'] = 'lifecycle'
                    self.assert_collection(self.run_validation(root, c, wrong_kind, phase), 'fail')

    def test_bound_collection_and_negative_mutations_through_normal_cli(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            c, i = fixture(root / 'snapshot')
            good = self.run_validation(root, c, i)
            self.assert_collection(good, 'pass')
            mutations = {
                'owner': lambda x: x['facts'][0].pop('owner_id'),
                'category': lambda x: x['categories'].pop(),
                'stale': lambda x: x['anchors'][0].update(file_sha256='0'*64),
                'missing': lambda x: x['anchors'][0].update(path='Absent.kt'),
                'test': lambda x: x['anchors'][0].update(kind='test', symbol='MissingTest.nonexistent'),
                'branch': lambda x: x['facts'][0]['source_expressions'].append('not already terminal'),
                'relation': lambda x: x['relationships'].append({'id': 'broken', 'from_id': 'page', 'to_id': 'absent', 'bindings': []}),
                'empty': lambda x: x['facts'][0].update(outcomes=[]),
                'wrong-outcome-type': lambda x: x['facts'][0].update(outcomes={'description': 'nonempty'}),
                'wrong-fact-kind': lambda x: (x['facts'][0].update(contract_ids=['STATE-LOADING']), x['facts'][1].update(contract_ids=['ACTION-REFRESH'])),
                'unresolved': lambda x: x['categories'][0].update(disposition='unresolved'),
                'branch_pair': lambda x: x['facts'].append({
                    'id': 'branch', 'kind': 'branch', 'owner_id': 'page',
                    'anchor_ids': ['source'], 'source_inventory_ids': ['INV-ACTION-REFRESH'],
                    'selector': 'refresh', 'source_expressions': ['fun refresh()'],
                    'cases': [{'condition': 'loading = true', 'outcome': 'loading = false',
                               'source_clause': 'loading = true; repository.refresh()'}]}),
            }
            for name, mutate in mutations.items():
                with self.subTest(name=name):
                    changed = copy.deepcopy(c)
                    mutate(changed['collection'])
                    if name == 'branch_pair':
                        changed['collection']['categories'][1]['record_ids'].append('branch')
                    result = self.run_validation(root, changed, i)
                    self.assert_collection(result, 'fail')
                    self.assertTrue(json.loads(result.stdout)['collection']['errors'])

    def test_catalog_selection_and_scaffold_are_deterministic_pending(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            c, i = fixture(root / 'snapshot')
            (root / 'inventory.json').write_text(json.dumps(i))
            command = [sys.executable, '-B', str(SCRIPTS / 'collect_behavior_rules.py'),
                       'scaffold', '--inventory', str(root / 'inventory.json')]
            first = subprocess.run(command, text=True, capture_output=True)
            second = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(first.stdout, second.stdout)
            scaffold = json.loads(first.stdout)
            self.assertEqual(scaffold['status'], 'pending')
            self.assertEqual({x['family'] for x in scaffold['categories']}, set(FAMILIES))
            self.assertTrue(all(x['disposition'] == 'unresolved' for x in scaffold['categories']))
            (root / 'collection.json').write_text(json.dumps(c['collection']))
            selected = subprocess.run([*command[:3], 'selected', '--collection',
                str(root / 'collection.json')], text=True, capture_output=True)
            self.assertEqual(selected.returncode, 0, selected.stderr)
            result = json.loads(selected.stdout)
            self.assertEqual(len(result['applicability_index']), 6)
            self.assertEqual(len(result['rules']), 3)

    def test_async_outcomes_require_bound_order_and_explicit_absence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            c, i = fixture(root / 'snapshot')
            fact = {'id': 'async', 'kind': 'async', 'owner_id': 'page',
                    'source_inventory_ids': ['INV-ACTION-REFRESH'], 'anchor_ids': ['source'],
                    'scope': 'refresh function', 'entry': 'loading = true', 'normal': 'loading = false',
                    'failure': 'Invented cleanup', 'cancellation': 'Invented cleanup',
                    'source_expressions': ['loading = true', 'loading = false']}
            c['collection']['facts'].append(fact)
            c['collection']['categories'][3].update(disposition='applicable', record_ids=['async'])
            result = self.run_validation(root, c, i)
            self.assert_collection(result, 'fail')
            self.assertTrue(any('async' in e for e in json.loads(result.stdout)['errors']))
            for outcome in ('failure', 'cancellation'):
                fact[outcome] = {'disposition': 'absent_local', 'scope_anchor_id': 'source',
                                 'rationale': 'No local handler in inspected refresh function'}
            anchor = copy.deepcopy(c['collection']['anchors'][0])
            anchor.update(id='function', start_line=3, end_line=3,
                          span_sha256=hashlib.sha256((root/'snapshot/Tasks.kt').read_text().splitlines(keepends=True)[2].encode()).hexdigest())
            c['collection']['anchors'].append(anchor)
            fact['anchor_ids'].append('function')
            fact['scope_anchor_id'] = 'function'
            good = self.run_validation(root, c, i)
            self.assert_collection(good, 'pass')
            # The normal return write is not evidence of failure/cancellation handling.
            for outcome in ('failure', 'cancellation'):
                changed = copy.deepcopy(c)
                changed['collection']['facts'][-1][outcome] = {
                    'disposition': 'observed', 'scope_anchor_id': 'function',
                    'expression': 'loading = false'}
                bad = self.run_validation(root, changed, i)
                self.assert_collection(bad, 'fail')
            fact['entry'], fact['normal'] = fact['normal'], fact['entry']
            self.assert_collection(self.run_validation(root, c, i), 'fail')

    def test_observed_async_outcome_is_inside_local_handler(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            text = ('class TasksViewModel {\n var loading = false\n'
                    ' fun refresh() { loading = true; try { repository.refresh(); normalDone() } finally { loading = false; status = "idle"; /* status = "busy" */ } }\n}\n')
            c, i = fixture(root / 'snapshot', text)
            c['collection']['facts'].append({'id': 'async', 'kind': 'async', 'owner_id': 'page',
                'source_inventory_ids': ['INV-ACTION-REFRESH'], 'anchor_ids': ['source'],
                'scope_anchor_id': 'source', 'scope': 'refresh', 'entry': 'loading = true',
                'normal': 'normalDone()', 'source_expressions': ['repository.refresh()'],
                **{outcome: {'disposition': 'observed', 'scope_anchor_id': 'source',
                            'expression': 'status = "idle"'} for outcome in ('failure', 'cancellation')}})
            c['collection']['categories'][3].update(disposition='applicable', record_ids=['async'])
            good = self.run_validation(root, c, i)
            self.assert_collection(good, 'pass')
            for outcome in ('failure', 'cancellation'):
                for expression in ('normalDone()', 'status = "busy"'):
                    with self.subTest(outcome=outcome, expression=expression):
                        changed = copy.deepcopy(c)
                        changed['collection']['facts'][-1][outcome]['expression'] = expression
                        bad = self.run_validation(root, changed, i)
                        self.assert_collection(bad, 'fail')

    def test_branch_outcome_cannot_use_an_adjacent_arm(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            text = ('class TasksViewModel {\n var loading = false\n'
                    ' fun refresh() { repository.refresh(); when (kind) { ACTIVE -> if (task.isActive) add(task); COMPLETED -> if (task.isCompleted) add(task) } }\n}\n')
            c, i = fixture(root / 'snapshot', text)
            fact = {'id': 'filter', 'kind': 'branch', 'owner_id': 'page',
                    'source_inventory_ids': ['INV-ACTION-REFRESH'], 'anchor_ids': ['source'],
                    'selector': 'kind', 'source_expressions': ['when (kind)'],
                    'cases': [{'condition': 'COMPLETED', 'outcome': 'task.isCompleted',
                               'source_clause': 'COMPLETED -> if (task.isCompleted) add(task)'}]}
            c['collection']['facts'].append(fact)
            c['collection']['categories'][1]['record_ids'].append('filter')
            good = self.run_validation(root, c, i)
            self.assert_collection(good, 'pass')
            fact['cases'][0].update(outcome='task.isActive', source_clause=
                'ACTIVE -> if (task.isActive) add(task); COMPLETED -> if (task.isCompleted) add(task)')
            bad = self.run_validation(root, c, i)
            self.assert_collection(bad, 'fail')

    def test_test_anchor_resolves_real_method_not_commented_declaration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            c, i = fixture(root / 'snapshot')
            relative = 'app/src/test/java/TasksTest.kt'
            path = root / 'snapshot' / relative
            path.parent.mkdir(parents=True)
            text = 'class TasksTest {\n @Test fun refresh() {}\n}\n// class FakeTest {\n// @Test\n fun nonexistent() {}\n// }\n'
            path.write_text(text)
            digest = hashlib.sha256(text.encode()).hexdigest()
            manifest_path = root / 'snapshot/.android-to-harmony-safe.json'
            manifest = json.loads(manifest_path.read_text())
            manifest['text_files'].append(relative)
            manifest['text_file_count'] += 1
            manifest['text_file_sha256'][relative] = digest
            manifest_path.write_text(json.dumps(manifest))
            anchor = {'id': 'test', 'kind': 'test', 'path': relative, 'start_line': 1,
                      'end_line': 7, 'file_sha256': digest, 'span_sha256': digest, 'symbol': 'TasksTest.refresh'}
            c['collection']['anchors'].append(anchor)
            c['scenarios'][0]['android_evidence'] = ['test']
            self.assert_collection(self.run_validation(root, c, i), 'pass')
            anchor['symbol'] = 'FakeTest.nonexistent'
            result = self.run_validation(root, c, i)
            self.assert_collection(result, 'fail')

    def test_snapshot_hash_drift_and_symlink_fail_before_anchor_reads(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            c, i = fixture(root / 'snapshot')
            path = root / 'snapshot/Tasks.kt'
            original = path.read_text()
            path.write_text(original + '// changed\n')
            result = self.run_validation(root, c, i)
            self.assert_collection(result, 'fail')
            self.assertIn('unsafe snapshot', result.stdout)
            path.unlink()
            outside = root / 'outside.kt'
            outside.write_text(original)
            path.symlink_to(outside)
            result = self.run_validation(root, c, i)
            self.assert_collection(result, 'fail')
            self.assertIn('symbolic_link', result.stdout)

    def test_shared_definition_cannot_be_duplicated_under_distinct_ids(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            c, i = fixture(root / 'snapshot')
            for key in ('vm-1', 'vm-2'):
                c['collection']['entities'].append({'id': key, 'kind': 'definition',
                    'owner_id': 'page', 'symbol': 'TasksViewModel', 'anchor_ids': ['source'],
                    'source_inventory_ids': ['INV-ACTION-REFRESH']})
                c['collection']['categories'][0]['record_ids'].append(key)
            result = self.run_validation(root, c, i)
            self.assert_collection(result, 'fail')
            self.assertIn('duplicate shared definition', result.stdout)

    def test_shared_definition_identity_ignores_supplemental_anchors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            c, i = fixture(root / 'snapshot')
            text = 'package other\nclass TasksViewModel {}\n'
            (root / 'snapshot/Other.kt').write_text(text)
            digest = hashlib.sha256(text.encode()).hexdigest()
            manifest_path = root / 'snapshot/.android-to-harmony-safe.json'
            manifest = json.loads(manifest_path.read_text())
            manifest['text_files'].append('Other.kt')
            manifest['text_file_count'] += 1
            manifest['text_file_sha256']['Other.kt'] = digest
            manifest_path.write_text(json.dumps(manifest))
            c['collection']['anchors'].append({'id': 'other', 'kind': 'source', 'path': 'Other.kt',
                'start_line': 1, 'end_line': 2, 'file_sha256': digest, 'span_sha256': digest})
            for key, primary in [('vm', 'source'), ('other-vm', 'other')]:
                c['collection']['entities'].append({'id': key, 'kind': 'definition', 'owner_id': 'page',
                    'symbol': 'TasksViewModel', 'definition_anchor_id': primary,
                    'anchor_ids': [primary], 'source_inventory_ids': ['INV-ACTION-REFRESH']})
                c['collection']['categories'][0]['record_ids'].append(key)
            good = self.run_validation(root, c, i)
            self.assert_collection(good, 'pass')
            # Supplemental source is not a new definition, even if its path set differs.
            duplicate = copy.deepcopy(c['collection']['entities'][1])
            duplicate.update(id='duplicate-vm', anchor_ids=['source', 'other'])
            c['collection']['entities'].append(duplicate)
            c['collection']['categories'][0]['record_ids'].append('duplicate-vm')
            bad = self.run_validation(root, c, i)
            self.assert_collection(bad, 'fail')
            self.assertIn('duplicate shared definition', bad.stdout)


if __name__ == '__main__':
    unittest.main()
