"""Source Page's exact equidistant adjacent-touch oracle, diagnostic only."""
import argparse
from pathlib import Path
import re
import time
from capture import Capture
from common import sha, write_json

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    capture = Capture(args.run.resolve(), 'android', 'gap-oracle-1')
    original = {}
    result = {'diagnostic_only': True, 'observations': []}
    try:
        for key, value in [('size', '1320x2856'), ('density', '560')]:
            original[key] = capture.command('original-' + key, 'shell', 'wm', key).decode()
            capture.command('normalize-' + key, 'shell', 'wm', key, value)
        capture.installed_identity()
        capture.start()
        capture.environment()
        capture.state('basis', 0, 0)
        paints = capture.states[0]['indicators']
        middle = (paints[1]['bounds'][2] + paints[2]['bounds'][0]) // 2
        y = (paints[2]['bounds'][1] + paints[2]['bounds'][3]) // 2
        for index, x in enumerate((middle - 1, middle, middle + 1)):
            capture.start()
            _, initial = capture.tree(f'before-{index}')
            texts = {n.get('text') for n in initial}
            assert {'Page 1 of 4', 'Callback 0', 'Chapter 1', 'Continue'} <= texts
            capture.command(f'tap-{index}', 'shell', 'input', 'tap', x, y)
            time.sleep(1.2)
            path, tree = capture.tree(f'after-{index}')
            labels = [n['text'] for n in tree if re.fullmatch(r'Page [1-4] of 4', n.get('text', ''))]
            assert len(labels) == 1
            image = capture.screenshot(f'after-{index}')
            result['observations'].append({'point': [x, y], 'label': labels[0],
                                           'tree': str(path), 'tree_sha256': sha(path),
                                           'image': str(image), 'image_sha256': sha(image)})
            write_json(capture.directory / 'result.json', result)
        print(result)
    finally:
        for key, raw in original.items():
            override = re.search(r'Override \w+:\s*(\S+)', raw)
            capture.command('restore-' + key, 'shell', 'wm', key, override.group(1) if override else 'reset')
