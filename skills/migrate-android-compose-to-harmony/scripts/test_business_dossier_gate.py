"""The direct dossier path is exercised through the two user-facing CLIs."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parent


class BusinessDossierGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.snapshot = self.root / 'snapshot'
        self.snapshot.mkdir()
        source = 'fun save(value: Int): Int { require(value > 0); return value }\n'
        (self.snapshot / 'Page.kt').write_text(source)
        (self.snapshot / '.android-to-harmony-safe.json').write_text(json.dumps({
            'schema': 'android-to-harmony.safe-snapshot.v1',
            'text_files': ['Page.kt'], 'text_file_count': 1,
            'text_file_sha256': {'Page.kt': hashlib.sha256(source.encode()).hexdigest()},
        }))
        self.target = self.root / 'target'
        self.target.mkdir()
        self.dossier = self.root / 'DOSSIER.md'
        self.dossier.write_text('''# Page

## Business chains

| Chain / trigger | Source rule and data effect | Target | Checks and current result |
| --- | --- | --- | --- |
| save | Reject nonpositive values, preserve the value. [save](Page.kt#L1-L1) | pending | `Save.positive` `Save.invalid` |
''')
        self.baseline = self.root / 'baseline.json'
        result, _ = self.run_gate('validate_behavior_contract_v2.py', 'source', '--output', self.baseline)
        self.assertEqual(result.returncode, 0, result.stdout)

    def run_gate(self, entry='validate_behavior_contract_v2.py', phase='source', *extra):
        baseline_args = ([] if phase == 'source' or '--source-baseline' in extra else
                         ['--source-baseline', str(self.baseline)])
        scope_args = ['--source-file', 'Page.kt'] if phase == 'source' and '--source-file' not in extra else []
        command = [sys.executable, '-B', str(SCRIPTS / entry), '--dossier', str(self.dossier),
                   '--phase', phase, '--snapshot', str(self.snapshot), '--target', str(self.target),
                   *baseline_args, *scope_args, *map(str, extra)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertTrue(result.stdout.strip(), result.stderr)
        return result, json.loads(result.stdout)

    def test_source_dossier_needs_real_source_but_not_contract_psi_or_reviewer(self):
        result, report = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(report['chains'], ['save'])
        self.assertTrue(report['references_valid'])
        self.assertFalse(report['business_verified'])
        self.assertFalse(report['runtime_complete'])
        self.dossier.write_text(self.dossier.read_text().replace('Page.kt#L1-L1', 'Missing.kt#L1-L1'))
        result, report = self.run_gate()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('Missing.kt', ' '.join(report['errors']))

    def implement(self):
        self.production = self.target / 'entry/src/main/ets'
        self.production.mkdir(parents=True)
        (self.production / 'Rule.mjs').write_text(
            'export function save(value, store) {\n'
            '  if (value <= 0) throw new Error("invalid");\n'
            '  store.value = value; return store.value;\n}\n')
        (self.production / 'Page.mjs').write_text(
            'import {save} from "./Rule.mjs";\n'
            'const store = {value: 0};\n'
            'export function click(value) { return {display: save(value, store)}; }\n')
        target = ('[entry](entry/src/main/ets/Page.mjs#L3-L3) '
                  '[implementation](entry/src/main/ets/Rule.mjs#L1-L4) '
                  '[binding](entry/src/main/ets/Page.mjs#L1-L2) '
                  '[consumer](entry/src/main/ets/Page.mjs#L3-L3)')
        self.dossier.write_text(self.dossier.read_text().replace('| pending |', '| ' + target + ' |'))

    def test_implementation_requires_all_chain_anchors_in_production_files(self):
        self.implement()
        result, report = self.run_gate(phase='implementation')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(report['references_valid'])
        self.assertFalse(report['checks_passed'])
        original = self.dossier.read_text()
        for bad in ('[notes](entry/src/main/ets/Page.mjs#L1-L2)',
                    '[binding](entry/src/main/ets/Missing.mjs#L1-L2)',
                    '[binding](entry/src/main/ets/Page.mjs#L5-L8)'):
            with self.subTest(reference=bad):
                self.dossier.write_text(original.replace('[binding](entry/src/main/ets/Page.mjs#L1-L2)', bad))
                result, report = self.run_gate(phase='implementation')
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertFalse(report['references_valid'])

    def checks(self):
        (self.target / 'behavior.test.mjs').write_text('''import test from 'node:test';
import assert from 'node:assert/strict';
import {click} from './entry/src/main/ets/Page.mjs';
test('Save.positive', () => assert.deepEqual(click(7), {display: 7}));
test('Save.invalid', () => assert.throws(() => click(0), /invalid/));
''')
        return ['--', 'node', '--test', '--test-reporter=junit', 'behavior.test.mjs']

    def test_target_runs_real_checks_and_rejects_stub_and_disconnected_caller(self):
        self.implement()
        command = self.checks()
        result, report = self.run_gate('validate_behavior_contract_v2.py', 'target', *command)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(report['checks_passed'])
        self.assertEqual(report['execution']['exit_code'], 0)
        self.assertEqual(set(report['execution']['passed_tests']), {'Save.positive', 'Save.invalid'})
        self.assertFalse(report['runtime_complete'])
        rule = self.production / 'Rule.mjs'
        rule_original = rule.read_text()
        page = self.production / 'Page.mjs'
        page_original = page.read_text()
        for label, path, mutated in [
            ('stub', rule, 'export function save(value, store) {\n return 7;\n\n}\n'),
            ('unwired', page, page_original.replace('save(value, store)', 'value')),
            ('wrong result consumer', page, page_original.replace('display: save', 'unused: save')),
        ]:
            with self.subTest(mutation=label):
                path.write_text(mutated)
                result, report = self.run_gate('validate_behavior_contract_v2.py', 'target', *command)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertFalse(report['checks_passed'])
                self.assertTrue(report['references_valid'])
                self.assertNotEqual(report['execution']['exit_code'], 0)
                rule.write_text(rule_original)
                page.write_text(page_original)

    def test_page_cli_uses_same_direct_gate_without_running_generators(self):
        result, report = self.run_gate('migrate_compose_page.py')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(report['artifact_type'], 'business_dossier_validation')
        self.assertEqual(list(self.target.iterdir()), [])
        self.implement()
        result, report = self.run_gate('migrate_compose_page.py', 'target', *self.checks())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(report['checks_passed'])
        (self.production / 'Rule.mjs').unlink()
        result, report = self.run_gate('migrate_compose_page.py', 'target', *self.checks())
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertNotIn('execution', report)

    def test_failed_real_test_identifies_its_business_chain_for_repair(self):
        self.implement()
        command = self.checks()
        rule = self.production / 'Rule.mjs'
        rule.write_text(rule.read_text().replace('if (value <= 0)', 'if (false)'))
        for entry in ('validate_behavior_contract_v2.py', 'migrate_compose_page.py'):
            with self.subTest(entry=entry):
                result, report = self.run_gate(entry, 'target', *command)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertFalse(report['checks_passed'])
                self.assertEqual(report['failed_checks'], [
                    {'test': 'Save.invalid', 'chains': ['save'], 'status': 'failure'}])
                self.assertIn('Save.invalid', ' '.join(report['errors']))
                self.assertIn('save', ' '.join(report['errors']))

    def test_completion_rejects_missing_skipped_and_summary_only_results(self):
        self.implement()
        result, report = self.run_gate('validate_behavior_contract_v2.py', 'target')
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('executed checks', ' '.join(report['errors']))
        command = self.checks()
        tests = self.target / 'behavior.test.mjs'
        original = tests.read_text()
        for change in (original.replace("test('Save.invalid'", "test.skip('Save.invalid'"),
                       original.replace("'Save.invalid'", "'Other.test'")):
            tests.write_text(change)
            result, report = self.run_gate('migrate_compose_page.py', 'target', *command)
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertFalse(report['checks_passed'])

        for xml in ('build succeeded', '<testsuite tests="2"/>',
                    '<testsuite tests="2" failures="1"><testcase name="Save.positive"/>'
                    '<testcase name="Save.invalid"/></testsuite>'):
            result, report = self.run_gate('validate_behavior_contract_v2.py', 'target',
                                         '--', sys.executable, '-c', 'print(' + repr(xml) + ')')
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertFalse(report['checks_passed'])
            self.assertTrue(report['references_valid'])

    def test_equals_option_reaches_the_same_gate(self):
        result = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'migrate_compose_page.py'),
            '--dossier=' + str(self.dossier), '--phase=source', '--snapshot=' + str(self.snapshot),
            '--source-file=Page.kt'],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['chains'], ['save'])

    def test_references_reject_stale_snapshot_traversal_symlinks_and_test_code(self):
        original = self.dossier.read_text()
        (self.snapshot / 'Page.kt').write_text('fun changed() {}\n')
        result, report = self.run_gate()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('manifest_hash_mismatch', ' '.join(report['errors']))
        # Restore the exact originally approved source bytes.
        (self.snapshot / 'Page.kt').write_text(
            'fun save(value: Int): Int { require(value > 0); return value }\n')
        for anchor in ('../snapshot/Page.kt#L1-L1', 'Page.kt#L2-L3', 'Page.kt#save'):
            self.dossier.write_text(original.replace('Page.kt#L1-L1', anchor))
            result, report = self.run_gate()
            self.assertEqual(result.returncode, 1, result.stdout)
        self.dossier.write_text(original)
        self.implement()
        rule = self.production / 'Rule.mjs'
        content = rule.read_text()
        outside = self.root / 'Rule.mjs'
        outside.write_text(content)
        rule.unlink()
        rule.symlink_to(outside)
        result, report = self.run_gate(phase='implementation')
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('symbolic link', ' '.join(report['errors']))
        rule.unlink()
        rule.write_text(content)
        test_rule = self.target / 'entry/src/ohosTest/ets/Rule.mjs'
        test_rule.parent.mkdir(parents=True)
        test_rule.write_text(content)
        self.dossier.write_text(self.dossier.read_text().replace(
            'entry/src/main/ets/Rule.mjs', 'entry/src/ohosTest/ets/Rule.mjs'))
        result, report = self.run_gate(phase='implementation')
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('production source', ' '.join(report['errors']))

    def test_current_checks_cannot_reuse_changed_code_or_dossier(self):
        self.implement()
        command = self.checks()
        tests = self.target / 'behavior.test.mjs'
        original = tests.read_text()
        rule = self.production / 'Rule.mjs'
        rule_original = rule.read_text()
        dossier_original = self.dossier.read_text()
        for path in (rule, self.dossier):
            with self.subTest(changed=path.name):
                tests.write_text(original + '\nimport {appendFileSync} from "node:fs";\n'
                    + 'appendFileSync(' + json.dumps(str(path)) + ', "\\n// changed\\n");\n')
                result, report = self.run_gate('validate_behavior_contract_v2.py', 'target', *command)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertFalse(report['checks_passed'])
                self.assertIn('changed during', ' '.join(report['errors']))
                rule.write_text(rule_original)
                self.dossier.write_text(dossier_original)

    def test_timeout_is_failed_check_not_a_pass_or_uncaught_error(self):
        self.implement()
        result, report = self.run_gate('validate_behavior_contract_v2.py', 'target',
            '--timeout', '0.05', '--', sys.executable, '-c', 'import time; time.sleep(2)')
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertFalse(report['checks_passed'])
        self.assertIn('timed out', ' '.join(report['errors']))

    def test_target_cannot_be_the_protected_source_tree(self):
        # Protection is checked before reading target anchors or running a command.
        self.target = self.snapshot
        result, report = self.run_gate(phase='implementation')
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('source and target must be separate', ' '.join(report['errors']))
        self.assertNotIn('execution', report)

    def test_deleting_a_chain_and_its_tests_cannot_shrink_the_source_baseline(self):
        second = '| load | Preserve stored value. [load](Page.kt#L1-L1) | pending | `Load.value` |\n'
        self.dossier.write_text(self.dossier.read_text() + second)
        baseline = self.root / 'source-baseline.json'
        result, _ = self.run_gate('validate_behavior_contract_v2.py', 'source', '--output', baseline)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.implement()
        # Delete the whole second chain, not just its result or target reference.
        self.dossier.write_text('\n'.join(line for line in self.dossier.read_text().splitlines()
                                          if not line.startswith('| load |')))
        result, report = self.run_gate('migrate_compose_page.py', 'target',
            '--source-baseline', baseline, *self.checks())
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('source baseline', ' '.join(report['errors']))
        self.assertIn('load', ' '.join(report['errors']))

    def test_source_baseline_cannot_omit_a_method_or_data_rule_from_selected_files(self):
        source = ('fun save(value: Int): Int { require(value > 0); return value }\n'
                  'fun load(account: Int) = rows.filter { it.account == account }\n')
        (self.snapshot / 'Page.kt').write_text(source)
        marker = self.snapshot / '.android-to-harmony-safe.json'
        manifest = json.loads(marker.read_text())
        manifest['text_file_sha256']['Page.kt'] = hashlib.sha256(source.encode()).hexdigest()
        marker.write_text(json.dumps(manifest))
        result, report = self.run_gate('validate_behavior_contract_v2.py', 'source',
                                      '--source-file', 'Page.kt')
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('Page.kt:2', ' '.join(report['errors']))
        self.dossier.write_text(self.dossier.read_text() +
            '| load | Filter by account. [load](Page.kt#L2-L2) | pending | `Load.account` |\n')
        result, report = self.run_gate('validate_behavior_contract_v2.py', 'source',
                                      '--source-file', 'Page.kt')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(report['source_coverage']['complete'])

    def test_data_rules_and_effect_order_are_checked_through_the_real_target_entry(self):
        source = ('fun visible(rows: List<Row>, account: Int) = rows.filter { it.account == account }\n'
                  'fun select() { first = true; second = false }\n'
                  'fun move() { destination.addAll(source); source.clear() }\n')
        (self.snapshot / 'Page.kt').write_text(source)
        marker = self.snapshot / '.android-to-harmony-safe.json'
        manifest = json.loads(marker.read_text())
        manifest['text_file_sha256']['Page.kt'] = hashlib.sha256(source.encode()).hexdigest()
        marker.write_text(json.dumps(manifest))
        header = self.dossier.read_text().split('| save |')[0]
        self.dossier.write_text(header + ''.join([
            '| account | Keep account ownership. [visible](Page.kt#L1-L1) | pending | `Data.account` |\n',
            '| settings | Preserve mutual exclusion. [select](Page.kt#L2-L2) | pending | `Data.settings` |\n',
            '| move | Move before clearing. [move](Page.kt#L3-L3) | pending | `Data.move` |\n']))
        self.baseline = self.root / 'data-baseline.json'
        result, _ = self.run_gate('validate_behavior_contract_v2.py', 'source', '--output', self.baseline)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.implement()
        rule = self.production / 'Rule.mjs'
        rule.write_text('export function visible(rows, account) { return rows.filter(r => r.account === account); }\n'
                        'export function select(state) { state.first = true; state.second = false; }\n'
                        'export function move(source, destination) { destination.push(...source); source.length = 0; }\n\n')
        page = self.production / 'Page.mjs'
        page.write_text('import {visible, select, move} from "./Rule.mjs";\n'
                        'export const state = {first: false, second: true};\n'
                        'export const page = {visible, select: () => select(state), move};\n')
        tests = self.target / 'data.test.mjs'
        tests.write_text('''import test from 'node:test';
import assert from 'node:assert/strict';
import {page, state} from './entry/src/main/ets/Page.mjs';
test('Data.account', () => assert.deepEqual(page.visible([{id: 1, account: 7}, {id: 2, account: 8}], 7), [{id: 1, account: 7}]));
test('Data.settings', () => {page.select(); assert.deepEqual(state, {first: true, second: false});});
test('Data.move', () => {const source = [4, 5], destination = [1]; page.move(source, destination); assert.deepEqual(destination, [1, 4, 5]); assert.deepEqual(source, []);});
''')
        command = ['--', 'node', '--test', '--test-reporter=junit', 'data.test.mjs']
        original = rule.read_text()
        result, report = self.run_gate('migrate_compose_page.py', 'target', *command)
        self.assertEqual(result.returncode, 0, result.stdout)
        for wrong in (original.replace('rows.filter(r => r.account === account)', 'rows'),
                      original.replace('state.second = false;', ''),
                      original.replace('destination.push(...source); source.length = 0;',
                                       'source.length = 0; destination.push(...source);')):
            with self.subTest(mutation=wrong):
                rule.write_text(wrong)
                result, report = self.run_gate('migrate_compose_page.py', 'target', *command)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertTrue(report['source_coverage']['complete'])
                self.assertFalse(report['checks_passed'])
                self.assertNotEqual(report['execution']['exit_code'], 0)

    def test_source_baseline_is_not_overwritten_by_a_later_source_check(self):
        original = self.baseline.read_bytes()
        result, report = self.run_gate('validate_behavior_contract_v2.py', 'source', '--output', self.baseline)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('existing source baseline', ' '.join(report['errors']))
        self.assertEqual(self.baseline.read_bytes(), original)

    def test_target_requires_source_baseline_and_cannot_remove_a_required_case(self):
        self.implement()
        result = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'migrate_compose_page.py'),
            '--dossier', str(self.dossier), '--snapshot', str(self.snapshot), '--target', str(self.target),
            '--phase', 'implementation'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('source baseline is required', result.stdout)
        self.dossier.write_text(self.dossier.read_text().replace(' `Save.invalid`', ''))
        result, report = self.run_gate('migrate_compose_page.py', 'target', *self.checks())
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('source baseline', ' '.join(report['errors']))
        self.assertNotIn('execution', report)


if __name__ == '__main__':
    unittest.main()
