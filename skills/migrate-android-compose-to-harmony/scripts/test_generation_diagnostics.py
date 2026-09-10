import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from page_snapshot import PageSnapshotError, bounded_string, finite_number, normalize_unresolved, optional_color
from test_generate_lanhu_source_page import source_component
from test_layout_mapping_contract import render_nodes
from ui_migration.contracts.lanhu_storage import unpack_lanhu_document
from ui_migration.progress import Progress


SCRIPTS = Path(__file__).resolve().parent


class GenerationDiagnosticsTest(unittest.TestCase):
    def test_reason_reports_actual_value_type_length_and_controls(self):
        for value in ('', None, 12, {}, 'line one\x00line two', ' \n\t'):
            with self.subTest(value=repr(value)[:40]):
                with self.assertRaises(PageSnapshotError) as raised:
                    normalize_unresolved([{'path': 'source.state', 'expression': 'state',
                                           'reason': value}], 'node.migration.unresolved')
                message = str(raised.exception)
                self.assertIn('node.migration.unresolved[0].reason', message)
                self.assertIn('actual=', message)
                self.assertIn('type=' + type(value).__name__, message)
                if isinstance(value, (str, dict)):
                    self.assertIn('length=' + str(len(value)), message)
                if value == 'line one\x00line two':
                    self.assertIn(r'line one\x00line two', message)
                    self.assertIn('control_positions=[8]', message)
                self.assertNotIn('\n', message)
                self.assertLess(len(message), 700)

    def test_shared_validators_report_bad_values_without_changing_valid_values(self):
        for function, value in ((optional_color, 'LocalContentColor.current'),
                                (finite_number, 'dimension'), (bounded_string, '')):
            with self.subTest(function=function.__name__):
                with self.assertRaises(PageSnapshotError) as raised:
                    function(value, 'node.style.property')
                self.assertIn('actual=' + repr(value), str(raised.exception))
        self.assertEqual(optional_color('#FF123456', 'color'), '#FF123456')
        self.assertEqual(bounded_string('normal reason', 'reason'), 'normal reason')

    def test_large_actual_value_is_bounded(self):
        with self.assertRaises(PageSnapshotError) as raised:
            bounded_string('start' + 'x' * 100000 + 'end', 'reason')
        self.assertIn('length=100008', str(raised.exception))
        self.assertIn('start', str(raised.exception))
        self.assertIn('end', str(raised.exception))
        self.assertLess(len(str(raised.exception)), 500)

    def test_library_logging_is_opt_in_and_does_not_change_generated_code(self):
        node = source_component('label', 'Text', parent_id=None, sibling_index=0,
                                text='Progress check', font_size_sp=16)
        quiet = io.StringIO()
        with contextlib.redirect_stderr(quiet):
            before, _, _ = render_nodes([node])
        self.assertEqual(quiet.getvalue(), '')
        stream = io.StringIO()
        with Progress('test', stream):
            after, _, _ = render_nodes([node])
        self.assertEqual(before, after)
        self.assertIn('render-components', stream.getvalue())

    def run_cli(self, script, *args, success=True):
        result = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                                text=True, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0 if success else 1, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        events = [json.loads(line.removeprefix('[progress] '))
                  for line in result.stderr.splitlines() if line.startswith('[progress] ')]
        return payload, events

    def test_real_lanhu_and_arkui_cli_progress_and_validation_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            node = source_component('label', 'Text', parent_id=None, sibling_index=0,
                                    text='Progress check', font_size_sp=16)
            node['source']['attributes'] = []
            source = root / 'source.json'
            source.write_text(json.dumps({'schema': 'android-to-harmony.source-page-spec.v1',
                'page': {'id': 'sample', 'state': 'default'},
                'root': node['source'], 'components': [node], 'component_definitions': []}))
            _, events = self.run_cli('generate_lanhu_source_page.py', '--source-page', source,
                '--output-dir', root / 'lanhu', '--viewport-width-dp', 360, '--viewport-height-dp', 800)
            for name in ('read-source-json', 'calculate-layout', 'build-lanhu-layers', 'write-version-json'):
                self.assertTrue(any(e['event'] == 'phase-start' and e['phase'] == name for e in events), name)
                self.assertTrue(any(e['event'] == 'phase-finished' and e['phase'] == name for e in events), name)
            self.assertEqual(events[-1]['event'], 'finished')
            target = root / 'target'
            self.run_cli('init_harmony_project.py', '--output', target,
                         '--project-name', 'Diagnostics', '--bundle-name', 'com.example.diagnostics')
            version = root / 'lanhu/version_json.json'
            _, events = self.run_cli('generate_arkui_page.py', '--target', target, '--page-json', version)
            for name in ('read-version-json', 'validate-lanhu-document', 'render-arkts', 'write-arkui-output'):
                self.assertTrue(any(e['event'] == 'phase-start' and e['phase'] == name for e in events), name)
                self.assertTrue(any(e['event'] == 'phase-finished' and e['phase'] == name for e in events), name)
            self.assertEqual(events[-1]['event'], 'finished')
            pages = list(target.glob('entry/src/main/ets/generated/*.ets'))
            self.assertTrue(pages)
            self.assertIn('Progress check', pages[0].read_text())
            document = unpack_lanhu_document(json.loads(version.read_text()))
            reason = 'unsupported modifier expression:\n' + ('long source excerpt\n' * 50)
            document['artboard']['layers'][0]['migration']['unresolved'] = [
                {'path': 'source.modifiers.unresolvedexpression', 'expression': 'composed { unknown() }',
                 'reason': reason}]
            version.write_text(json.dumps(document))
            payload, _ = self.run_cli('generate_arkui_page.py', '--target', target,
                                     '--page-json', version, '--force')
            self.assertTrue(payload['ok'])
            self.assertIn('Progress check', pages[0].read_text())
            document['artboard']['layers'][0]['migration']['unresolved'] = [
                {'path': 'source.state', 'expression': 'state', 'reason': 'bad\x00reason'}]
            version.write_text(json.dumps(document))
            payload, events = self.run_cli('generate_arkui_page.py', '--target', target,
                                          '--page-json', version, '--force', success=False)
            self.assertIn(r"actual='bad\x00reason'", payload['error'])
            self.assertIn('unresolved[0].reason', payload['error'])
            failure = next(e for e in events if e['event'] == 'phase-failed'
                           and e['phase'] == 'validate-lanhu-document')
            self.assertIn(r"actual='bad\x00reason'", failure['error'])
            self.assertEqual(events[-1]['event'], 'failed')


if __name__ == '__main__':
    unittest.main()
