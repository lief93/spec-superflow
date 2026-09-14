"""Fresh-install the exact built APK, then Harmony main HAP before test HAP."""
import argparse
import json
from pathlib import Path

from common import ANDROID, HARMONY, Evidence, sha, write_json
from build import verify_inputs


def install(run, platform):
    verify_inputs(run)
    packages = json.loads((run / 'packages.json').read_text())
    e = Evidence(run / ('install-' + platform))
    required = ['apk'] if platform == 'android' else ['main_hap', 'test_hap']
    for key in required:
        assert sha(packages[key]['path']) == packages[key]['sha256']
    if platform == 'android':
        e.run('uninstall', ANDROID + ['uninstall', 'dev.ets.verification'], check=False)
        result = e.run('install', ANDROID + ['install', packages['apk']['path']])
        assert b'Success' in result, result
        raw = e.run('installed-path', ANDROID + ['shell', 'pm', 'path', 'dev.ets.verification']).decode()
        remote = raw.strip().removeprefix('package:')
        pulled = e.directory / 'installed.apk'
        e.run('pull-installed', ANDROID + ['pull', remote, str(pulled)])
        assert sha(pulled) == packages['apk']['sha256']
    else:
        e.run('uninstall', HARMONY + ['uninstall', 'com.joker.kit'], check=False)
        for key in required:
            result = e.run('install-' + key, HARMONY + ['install', packages[key]['path']])
            assert b'successfully' in result.lower(), result
        raw = e.run('bundle-info', HARMONY + ['shell', 'bm', 'dump', '-n', 'com.joker.kit']).decode()
        info = json.loads(raw[raw.index('{'):])
        remote = {item['name']: item['hapPath'] for item in info['hapModuleInfos']}
        observations = {}
        for name, key in [('entry', 'main_hap'), ('entry_test', 'test_hap')]:
            output = e.run('installed-' + name, HARMONY + ['shell', 'sha256sum', remote[name]], check=False).decode()
            if 'Permission denied' in output:
                observations[name] = {'direct_readback': 'permission-denied', 'binding': 'fresh install command + local payload hash + runtime generated hash'}
            else:
                actual = output.split()[0]
                assert actual == packages[key]['sha256'], ('Installed HAP hash differs', key, actual)
                observations[name] = {'direct_readback': actual}
        write_json(e.directory / 'remote-paths.json', remote)
        write_json(e.directory / 'readback.json', observations)
    for key in required:
        assert sha(packages[key]['path']) == packages[key]['sha256']
    write_json(e.directory / 'identity.json', {key: packages[key] for key in required})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('run', type=Path)
    p.add_argument('--platform', choices=['android', 'harmony'], required=True)
    a = p.parse_args()
    install(a.run.resolve(), a.platform)
