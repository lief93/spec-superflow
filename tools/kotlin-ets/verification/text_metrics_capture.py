"""Measure SDK text layout only; not generated-translation acceptance."""
import argparse
from pathlib import Path
from capture import Capture, bounds, tagged
from common import sha, write_json

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    capture = Capture(args.run.resolve(), 'harmony', 'text-metrics-1')
    capture.installed_identity()
    capture.start()
    capture.environment()
    path, tree = capture.tree('metrics')
    geometry = {name: bounds(tagged(tree, name)) for name in (
        'title-natural', 'title-line', 'title-half', 'chapter-half',
        'body-half', 'body-line', 'button-half', 'button-line',
        'title-measured', 'chapter-measured', 'body-measured')}
    pid = capture.command('font-metrics-pid', 'shell', 'pidof', 'com.joker.kit').decode().strip()
    capture.command('native-font-metrics', 'shell', 'hilog', '-x', '-P', pid, '-T', 'NativeFontMetrics')
    screenshot = capture.screenshot('metrics')
    result = {'diagnostic_only': True, 'bounds': geometry,
              'heights': {name: b[3] - b[1] for name, b in geometry.items()},
              'tree': str(path), 'tree_sha256': sha(path),
              'image': str(screenshot), 'image_sha256': sha(screenshot)}
    write_json(capture.directory / 'result.json', result)
    print(result)
