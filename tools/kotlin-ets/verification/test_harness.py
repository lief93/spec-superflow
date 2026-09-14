import tempfile
from pathlib import Path
import unittest

from common import ADB, HDC, Evidence
from hypium import report
from capture import assert_android_foreground


class HarnessTests(unittest.TestCase):
    def test_launch_guard_rejects_previous_app_after_start_timeout(self):
        assert_android_foreground('topResumedActivity=ActivityRecord{1 u0 dev.ets.verification/.MainActivity t1}')
        for raw in ('', 'topResumedActivity=ActivityRecord{1 u0 by.alexandr7035.banking.debug/example.program.ContactFixtureActivity t64}'):
            with self.assertRaisesRegex(AssertionError, 'Expected verification foreground'):
                assert_android_foreground(raw)

    def test_other_devices_rejected_before_subprocess(self):
        with tempfile.TemporaryDirectory() as directory:
            e = Evidence(directory)
            for command in ([ADB, '-s', '192.168.1.78:5555', 'shell', 'true'],
                            [HDC, '-t', 'unauthorized', 'shell', 'true'], [ADB, 'shell', 'true']):
                with self.assertRaisesRegex(AssertionError, 'Unauthorized device'):
                    e.run('must-not-execute', command)
            self.assertEqual(e.records, [])

    def test_report_rejects_empty_skipped_failed_and_incomplete(self):
        def output(summary):
            return 'fourPagesBackAndCallback\n' + summary + '\nOHOS_REPORT_CODE: 0\nyour test finished!!!'
        good = output('Tests run: 1, Failure: 0, Error: 0, Pass: 1, Ignore: 0')
        self.assertEqual(report(good)['passed'], 1)
        for bad in ('', good.replace('Tests run: 1', 'Tests run: 0'),
                    good.replace('Failure: 0', 'Failure: 1'), good.replace('Error: 0', 'Error: 1'),
                    good.replace('Ignore: 0', 'Ignore: 1'), good.replace('Pass: 1', 'Pass: 0'),
                    good.replace('your test finished!!!', ''), good + '\nSkipSpec: 1', good + good):
            with self.assertRaises(AssertionError):
                report(bad)

    def test_evidence_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'commands.json').write_text('[]')
            with self.assertRaisesRegex(AssertionError, 'Keep prior evidence'):
                Evidence(directory)


if __name__ == '__main__':
    unittest.main(verbosity=2)
