"""Build/run source-specific Compose layout and boundary instrumentation."""
import argparse
import json
from pathlib import Path
from common import ANDROID, Evidence, build_env, sha, write_json

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('run', type=Path)
    p.add_argument('--stage', choices=['build', 'run'], required=True)
    p.add_argument('--attempt', default='1')
    p.add_argument('--online', action='store_true', help='Allow Gradle to fetch missing test runtime artifacts')
    a = p.parse_args()
    run = a.run.resolve()
    e = Evidence(run / ('instrument-' + a.stage + '-' + a.attempt))
    if a.stage == 'build':
        e.run('build-test', [run / 'android/gradlew', ':app:assembleDebugAndroidTest', *([] if a.online else ['--offline']),
              '--no-daemon', '--max-workers=2', '-Pandroid.useAndroidX=true', '-Dorg.gradle.jvmargs=-Xmx2g'],
              cwd=run / 'android', env=build_env(), timeout=600)
        apk = run / 'android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk'
        write_json(run / 'test-apk.json', {'path': str(apk), 'sha256': sha(apk)})
    else:
        apk = json.loads((run / 'test-apk.json').read_text())
        assert sha(apk['path']) == apk['sha256']
        e.run('uninstall-test', ANDROID + ['uninstall', 'dev.ets.verification.test'], check=False)
        out = e.run('install-test', ANDROID + ['install', apk['path']])
        assert b'Success' in out
        before = {}
        try:
            for key, value in [('size', '1320x2856'), ('density', '560')]:
                before[key] = e.run('original-' + key, ANDROID + ['shell', 'wm', key]).decode()
                e.run('normalize-' + key, ANDROID + ['shell', 'wm', key, value])
            raw = e.run('instrument', ANDROID + ['shell', 'am', 'instrument', '-w', '-r',
                        'dev.ets.verification.test/androidx.test.runner.AndroidJUnitRunner'], timeout=180).decode()
            logs = e.run('layout-boundary-log', ANDROID + ['logcat', '-d', '-v', 'raw', '-s',
                        'ModifierGeometry:I', 'ModifierBoundary:I', '*:S']).decode()
            records = [json.loads(line) for line in logs.splitlines() if line.startswith('{')]
            write_json(e.directory / 'observations.json', records)
            assert 'OK (1 test)' in raw and 'FAILURES' not in raw and 'INSTRUMENTATION_FAILED' not in raw, raw
            write_json(e.directory / 'report.json', {'status': 'pass', 'tests': 1, 'test_apk': apk})
        finally:
            import re
            for key, original in before.items():
                override = re.search(r'Override \w+:\s*(\S+)', original)
                e.run('restore-' + key, ANDROID + ['shell', 'wm', key, override.group(1) if override else 'reset'])
