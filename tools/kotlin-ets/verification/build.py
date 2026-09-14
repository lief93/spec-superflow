"""Build new APK and main/test HAPs with installed platform SDKs."""
import argparse
import json
from pathlib import Path

from common import DEVECO, Evidence, build_env, sha, write_json


def verify_inputs(run):
    config = json.loads((run / 'inputs.json').read_text())
    binding = run / 'frozen-inputs.json'
    if binding.exists():
        frozen = json.loads(binding.read_text())
        assert sha(frozen['manifest']) == frozen['manifest_sha256'], 'Frozen manifest drift'
        assert frozen['source_sha256'] == config['source_sha256']
        config = {**config, 'original_source': config['source'],
                  'source': frozen['source'], 'tool_root': frozen['tool_root']}
    assert sha(config['source']) == config['source_sha256'], 'Source drift: create a new run'
    assert sha(run / 'android/app/src/main/java/Page.kt') == config['source_sha256']
    for source, item in config['generated'].items():
        assert sha(source) == sha(item['copy']) == item['sha256'], 'Generated input drift'
    return config


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('run', type=Path)
    p.add_argument('--platform', choices=['android', 'harmony', 'both'], default='both')
    a = p.parse_args()
    run = a.run.resolve()
    config = verify_inputs(run)
    e = Evidence(run / ('build-' + a.platform))
    env = build_env()
    outputs = {}
    if a.platform in ('android', 'both'):
        e.run('android-build', [run / 'android/gradlew', ':app:assembleDebug', '--offline',
              '--no-daemon', '--max-workers=2', '-Pandroid.useAndroidX=true',
              '-Dorg.gradle.jvmargs=-Xmx2g'], cwd=run / 'android', env=env, timeout=600)
        outputs['apk'] = run / 'android/app/build/outputs/apk/debug/app-debug.apk'
    if a.platform in ('harmony', 'both'):
        assert config['generated'], 'Actual generated ETS is required'
        e.run('ohpm-install', [DEVECO / 'tools/ohpm/bin/ohpm', 'install'], cwd=run / 'harmony', env=env)
        for target in ('default', 'ohosTest'):
            e.run('harmony-' + target, [DEVECO / 'tools/hvigor/bin/hvigorw', 'assembleHap', '--mode',
                  'module', '-p', 'module=entry@' + target, '-p', 'product=default', '--no-daemon'],
                  cwd=run / 'harmony', env=env, timeout=600)
            haps = list((run / 'harmony/entry/build/default/outputs' / target).glob('*-signed.hap'))
            assert len(haps) == 1, haps
            outputs['main_hap' if target == 'default' else 'test_hap'] = haps[0]
    verify_inputs(run)
    manifest = run / 'packages.json'
    packages = json.loads(manifest.read_text()) if manifest.exists() else {}
    packages.update({key: {'path': str(path), 'sha256': sha(path)} for key, path in outputs.items()})
    write_json(manifest, packages)
    print(json.dumps(packages, indent=2))


if __name__ == '__main__':
    main()
