"""Read-only preflight against the two authorized device IDs only."""
import argparse
from pathlib import Path
from common import ANDROID, HARMONY, DEVECO, Evidence, build_env, sha, write_json

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    e = Evidence(a.output.resolve())
    commands = {
        'android-sdk': ANDROID + ['shell', 'getprop', 'ro.build.version.sdk'],
        'android-fingerprint': ANDROID + ['shell', 'getprop', 'ro.build.fingerprint'],
        'android-size': ANDROID + ['shell', 'wm', 'size'],
        'android-density': ANDROID + ['shell', 'wm', 'density'],
        'android-locale': ANDROID + ['shell', 'getprop', 'persist.sys.locale'],
        'harmony-screen': HARMONY + ['shell', 'hidumper', '-s', 'RenderService', '-a', 'screen'],
        'harmony-product': HARMONY + ['shell', 'param', 'get', 'const.product.software.version'],
        'harmony-locale': HARMONY + ['shell', 'param', 'get', 'persist.global.locale'],
        'java': [DEVECO / 'jbr/Contents/Home/bin/java', '-version'],
        'hvigor': [DEVECO / 'tools/hvigor/bin/hvigorw', '--version'],
    }
    for name, command in commands.items():
        e.run(name, command, env=build_env())
    write_json(e.directory / 'tool-identities.json', {str(command[0]): sha(command[0]) for command in commands.values()})
