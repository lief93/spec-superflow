import io
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest

from migrate_compose_page import PageRun
from ui_migration.progress import Progress, checkpoint, phase, tracked


class ProgressLogsTest(unittest.TestCase):
    def test_heartbeat_reports_current_unit_without_stdout(self):
        stream = io.StringIO()
        with Progress('test', interval=0.02, stream=stream):
            with phase('parse'):
                checkpoint('psi-declarations', unit='Page.kt', completed=0, total=2)
                deadline = time.monotonic() + 2
                while 'heartbeat' not in stream.getvalue() and time.monotonic() < deadline:
                    time.sleep(0.01)
        events = [json.loads(line.removeprefix('[progress] ')) for line in stream.getvalue().splitlines()]
        heartbeat = next(event for event in events if event['event'] == 'heartbeat')
        self.assertEqual(heartbeat['unit'], 'Page.kt')
        self.assertEqual(heartbeat['completed'], 0)
        self.assertGreater(heartbeat['checkpoint_age_s'], 0)
        self.assertTrue(any(e['event'] == 'phase-finished' and e['phase'] == 'parse' for e in events))

    def test_failed_phase_and_real_completion_counts_are_recorded(self):
        stream = io.StringIO()
        with self.assertRaisesRegex(ValueError, 'bad input'):
            with Progress('test', stream=stream):
                self.assertEqual(list(tracked(['a', 'b'], 'files')), ['a', 'b'])
                with phase('write'):
                    raise ValueError('bad input')
        events = [json.loads(line.removeprefix('[progress] ')) for line in stream.getvalue().splitlines()]
        self.assertTrue(any(e.get('completed') == e.get('total') == 2 for e in events))
        self.assertTrue(any(e['event'] == 'phase-failed' and e['error'] == 'bad input' for e in events))
        self.assertEqual(events[-1]['event'], 'failed')

    def test_child_logs_and_running_report_exist_before_exit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            child = root/'slow.py'
            release = root/'release'
            child.write_text('import json, sys, time\nfrom pathlib import Path\n'
                'print("first-checkpoint", file=sys.stderr, flush=True)\n'
                'deadline=time.monotonic()+5\n'
                f'while not Path({str(release)!r}).exists() and time.monotonic()<deadline: time.sleep(.01)\n'
                'print(json.dumps({"ok":True}))\n')
            run = PageRun(SimpleNamespace(output_dir=root, target=root/'target'))
            run.created = True
            results, errors = [], []
            def work():
                try:
                    results.append(run.tool('slow-stage', str(child)))
                except BaseException as error:
                    errors.append(error)
            thread = threading.Thread(target=work)
            thread.start()
            try:
                log = root/'00-slow-stage.stderr.log'
                deadline = time.monotonic()+3
                while time.monotonic()<deadline:
                    if log.exists() and 'first-checkpoint' in log.read_text():
                        break
                    time.sleep(.01)
                self.assertIn('first-checkpoint', log.read_text())
                self.assertTrue(thread.is_alive())
                report = json.loads((root/'result.json').read_text())
                self.assertEqual(report['current_stage'], 'slow-stage')
                self.assertEqual(report['stages'][0]['status'], 'running')
                self.assertIsNotNone(report['stages'][0]['pid'])
            finally:
                release.touch()
                thread.join(timeout=8)
            self.assertFalse(thread.is_alive())
            self.assertFalse(errors, errors)
            self.assertEqual(results, [{'ok':True}])
            report = json.loads((root/'result.json').read_text())
            self.assertEqual(report['stages'][0]['exit_code'], 0)
            self.assertEqual(report['stages'][0]['status'], 'completed')

    def test_failed_child_retains_log_and_exit_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            child = root/'fail.py'
            child.write_text('import sys\nprint("failure detail", file=sys.stderr)\nsys.exit(7)\n')
            run = PageRun(SimpleNamespace(output_dir=root, target=root/'target'))
            run.created = True
            with self.assertRaisesRegex(ValueError, 'failure detail'):
                run.tool('broken', str(child))
            report = json.loads((root/'result.json').read_text())
            self.assertEqual(report['stages'][0]['exit_code'], 7)
            self.assertEqual(report['stages'][0]['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
