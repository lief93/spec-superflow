"""Observe a native touch-dispatch API diagnostic, not translation acceptance."""
import argparse
from pathlib import Path
import time
from capture import Capture, bounds, tagged
from common import sha, write_json

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--attempt', default='1')
    parser.add_argument('--tie-only', action='store_true')
    args = parser.parse_args()
    capture = Capture(args.run.resolve(), 'harmony', 'touch-dispatch-' + args.attempt)
    capture.installed_identity()
    capture.start()
    capture.environment()
    path, tree = capture.tree('initial')
    assert tagged(tree, 'result')['text'] == 'Selected -1 Hits 0'
    geometry = {name: bounds(tagged(tree, name)) for name in ['touch-row'] +
                [f'{kind}-{i}' for kind in ('paint', 'target') for i in range(4)]}
    image = capture.screenshot('initial')
    result = {'diagnostic_only': True, 'geometry': geometry, 'observations': [],
              'initial_tree_sha256': sha(path), 'initial_image_sha256': sha(image)}
    points = [(62, 56, 0), (90, 56, 1), (118, 56, 2), (146, 56, 3),
              (103, 56, 1), (105, 56, 2), (106, 56, 2), (118, 56, 2),
              (40, 56, None), (168, 56, None), (118, 34, None)]
    if args.tie_only:
        points = [(104, 56, None)]
    for i, (x, y, selected) in enumerate(points):
        pixels = [int(x * 3.5 + 0.5), int(y * 3.5 + 0.5)]
        capture.command('tap-' + str(i), 'shell', 'uitest', 'uiInput', 'click', *pixels)
        time.sleep(0.6)
        path, tree = capture.tree('after-' + str(i))
        observed = tagged(tree, 'result')['text']
        expected = None if selected is None else f'Selected {selected} Hits {i + 1}'
        result['observations'].append({'point_vp': [x, y], 'point_px': pixels,
                                       'observed': observed, 'expected': expected,
                                       'tree': str(path), 'tree_sha256': sha(path)})
        write_json(capture.directory / 'result.json', result)
    pid = capture.command('touch-log-pid', 'shell', 'pidof', 'com.joker.kit').decode().strip()
    capture.command('native-touch-log', 'shell', 'hilog', '-x', '-P', pid)
    image = capture.screenshot('final')
    result['final_image_sha256'] = sha(image)
    result['status'] = 'observed' if args.tie_only else (
        'pass' if all(x['expected'] is None or x['observed'] == x['expected'] for x in result['observations']) else 'fail')
    write_json(capture.directory / 'result.json', result)
    print(result)
