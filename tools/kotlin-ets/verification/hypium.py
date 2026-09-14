"""Retain actual HDC Hypium output and require a nonempty clean final report."""
import argparse
import json
from pathlib import Path
import re
from common import HARMONY, Evidence, sha, write_json


def report(raw, case='fourPagesBackAndCallback'):
    counts = re.findall(r'Tests run: (\d+), Failure: (\d+), Error: (\d+), Pass: (\d+), Ignore: (\d+)', raw)
    assert len(counts) == 1, 'Missing or ambiguous Hypium summary'
    total, failures, errors, passed, ignored = map(int, counts[0])
    assert total >= 1 and passed == total and failures == errors == ignored == 0, counts
    assert case in raw, 'Wrong test suite'
    assert 'OHOS_REPORT_CODE: 0' in raw and 'your test finished!!!' in raw, 'Incomplete runner report'
    assert not re.search(r'SkipSpec: [1-9]', raw), 'Skipped test'
    return {'tests': total, 'passed': passed, 'failures': failures, 'errors': errors, 'ignore': ignored}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('run', type=Path)
    p.add_argument('--attempt', default='1')
    p.add_argument('--case', default='fourPagesBackAndCallback')
    a = p.parse_args()
    root = a.run.resolve()
    directory = root / ('hypium-' + a.attempt)
    directory.mkdir(exist_ok=False)
    packages = json.loads((root / 'packages.json').read_text())
    installed = json.loads((root / 'install-harmony/identity.json').read_text())
    for key in ('main_hap', 'test_hap'):
        assert installed[key] == packages[key]
        assert sha(packages[key]['path']) == packages[key]['sha256']
    e = Evidence(directory / 'commands')
    e.run('stop-main', HARMONY + ['shell', 'aa', 'force-stop', 'com.joker.kit'])
    raw = e.run('hypium', HARMONY + ['shell', 'aa', 'test', '-b', 'com.joker.kit',
                '-m', 'entry_test', '-s', 'unittest', 'OpenHarmonyTestRunner', '-s', 'timeout', '180000'],
                timeout=240).decode()
    try:
        result = {'status': 'pass', **report(raw, a.case), 'packages': installed}
    except BaseException as error:
        write_json(directory / 'report.json', {'status': 'fail', 'error': repr(error)})
        raise
    write_json(directory / 'report.json', result)
    print(json.dumps(result, indent=2))
