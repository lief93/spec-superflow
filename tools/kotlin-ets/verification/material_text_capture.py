"""Retain real MaterialText component geometry, separately from typography tests."""
import argparse
from pathlib import Path
import re
from capture import Capture, bounds
from common import sha, write_json

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--platform', choices=['android', 'harmony'], required=True)
    args = parser.parse_args()
    capture = Capture(args.run.resolve(), args.platform, 'material-text-1')
    original = {}
    try:
        if args.platform == 'android':
            for key, value in [('size', '1320x2856'), ('density', '560')]:
                original[key] = capture.command('original-' + key, 'shell', 'wm', key).decode()
                capture.command('normalize-' + key, 'shell', 'wm', key, value)
        capture.installed_identity()
        capture.start()
        capture.environment()
        path, tree = capture.tree('layout')
        geometry = {}
        for text in ('Body', 'Large body', 'Wrapped label', 'Explicit label', 'Body restored'):
            matches = [n for n in tree if n.get('text') == text and n.get('_effectively_visible', True)]
            assert len(matches) == 1, (text, matches)
            geometry[text] = bounds(matches[0])
        image = capture.screenshot('layout')
        result = {'diagnostic_only': True, 'bounds': geometry,
                  'labels_nonoverlapping': geometry['Wrapped label'][2] <= geometry['Explicit label'][0],
                  'tree': str(path), 'tree_sha256': sha(path),
                  'image': str(image), 'image_sha256': sha(image)}
        write_json(capture.directory / 'result.json', result)
        print(result)
    finally:
        for key, raw in original.items():
            override = re.search(r'Override \w+:\s*(\S+)', raw)
            capture.command('restore-' + key, 'shell', 'wm', key, override.group(1) if override else 'reset')
