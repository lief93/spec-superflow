"""Executed source/target observations compared through the public command."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name('compare_behavior_traces.py')


class CompareBehaviorTracesTests(unittest.TestCase):
    def test_missing_malformed_reordered_and_type_drift_cannot_pass(self):
        source = 'OBS={"phase":"one","value":true}\nOBS={"phase":"two","value":0}\n'
        cases = {
            'both-empty': ('', ''),
            'both-truncated': (source.splitlines()[0], source.splitlines()[0]),
            'missing-target': (source, ''),
            'extra-target': (source, source + source.splitlines()[0]),
            'order': (source, '\n'.join(reversed(source.splitlines()))),
            'type': (source, source.replace('true', '1')),
            'malformed': (source, source.replace('true', '')),
            'duplicate-field': (source, source.replace('true', '0,"value":true')),
            'non-finite': (source.replace('true', 'NaN'), source.replace('true', 'NaN')),
            'non-object': ('OBS=null\nOBS=null', 'OBS=null\nOBS=null'),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, (left, right) in cases.items():
                with self.subTest(name=name):
                    (root / 'left').write_text(left)
                    (root / 'right').write_text(right)
                    result = subprocess.run([sys.executable, '-B', str(SCRIPT),
                        '--source', str(root / 'left'), '--target', str(root / 'right'),
                        '--source-prefix', 'OBS=', '--target-prefix', 'OBS=',
                        '--expected-records', '2'], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertEqual(json.loads(result.stdout)['verdict'], 'fail')

    def test_compares_ordered_native_observations_without_reimplementing_business(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'android.log').write_text(
                'instrumentation started\nOBS={"phase":"before","locations":["Tokyo","Hidden"]}\n'
                'OBS={"phase":"after","locations":["Hidden"]}\n')
            (root / 'harmony.log').write_text(
                'I Application: TRACE {"locations":["Tokyo","Hidden"],"phase":"before"}\n'
                'I Application: TRACE {"locations":["Hidden"],"phase":"after"}\n')
            command = [sys.executable, '-B', str(SCRIPT), '--source', str(root / 'android.log'),
                       '--target', str(root / 'harmony.log'), '--source-prefix', 'OBS=',
                       '--target-prefix', 'TRACE ', '--expected-records', '2']
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report['verdict'], 'pass')
            self.assertEqual(report['records_compared'], 2)
            self.assertFalse(report['business_verified'])
            self.assertEqual(len(report['source']['sha256']), 64)
            (root / 'harmony.log').write_text(
                'I Application: TRACE {"phase":"before","locations":["Tokyo","Hidden"]}\n'
                'I Application: TRACE {"phase":"after","locations":["Tokyo"]}\n')
            changed = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(changed.returncode, 1, changed.stdout + changed.stderr)
            self.assertEqual(json.loads(changed.stdout)['differences'][0]['record'], 1)
