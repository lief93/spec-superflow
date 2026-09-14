"""Record native WrappedBuilder probe bounds; not translation acceptance."""
import argparse
from pathlib import Path
import re

from capture import Capture, bounds, tagged
from common import sha, write_json


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--attempt', default='slot-probe-1')
    parser.add_argument('--platform', choices=['android', 'harmony'], default='harmony')
    args = parser.parse_args()
    capture = Capture(args.run.resolve(), args.platform, args.attempt)
    original = {}
    if args.platform == 'android':
        for key, value in [('size', '1320x2856'), ('density', '560')]:
            original[key] = capture.command('original-' + key, 'shell', 'wm', key).decode()
            capture.command('normalize-' + key, 'shell', 'wm', key, value)
    capture.installed_identity()
    try:
        capture.start()
        capture.environment()
        path, tree = capture.tree('layout')
        for axis in ('column', 'row'):
            for name in ('before', 'one', 'two', 'after'):
                tagged(tree, axis + '-' + name)
        screenshot = capture.screenshot('layout')
    finally:
        for key, raw in original.items():
            override = re.search(r'Override \w+:\s*(\S+)', raw)
            capture.command('restore-' + key, 'shell', 'wm', key, override.group(1) if override else 'reset')
    geometry = {axis + '-' + name: bounds(tagged(tree, axis + '-' + name))
                for axis in ('column', 'row')
                for name in ('before', 'one', 'two', 'after')}
    origin = geometry['column-before']
    row = geometry['row-before']
    errors = []
    if row[1] - origin[1] != 280:
        errors.append('Row does not follow the complete 80vp Column')
    for index, name in enumerate(('before', 'one', 'two', 'after')):
        for axis in ('column', 'row'):
            actual = geometry[axis + '-' + name]
            left = origin[0] if axis == 'column' else row[0] + index * 140
            top = origin[1] + index * 70 if axis == 'column' else row[1]
            if actual != (left, top, left + 140, top + 70):
                errors.append(f'{axis}-{name}: {actual}')
    result = {'status': 'fail' if errors else 'pass', 'diagnostic_only': True,
              'bounds': geometry, 'errors': errors,
              'tree': str(path), 'tree_sha256': sha(path),
              'image': str(screenshot), 'image_sha256': sha(screenshot)}
    write_json(capture.directory / 'result.json', result)
    print(result)
    assert not errors, errors
