"""Physical input oracle for the actual independent ModifierOrder fixture."""
import argparse
from pathlib import Path
import re
import time
from capture import Capture
from common import sha, write_json

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('run', type=Path)
    p.add_argument('--platform', choices=['android', 'harmony'], required=True)
    p.add_argument('--attempt', default='1')
    a = p.parse_args()
    capture = Capture(a.run.resolve(), a.platform, 'modifier-physical-' + a.attempt)
    original = {}
    observations = []
    try:
        if a.platform == 'android':
            for key, value in [('size', '1320x2856'), ('density', '560')]:
                original[key] = capture.command('original-' + key, 'shell', 'wm', key).decode()
                capture.command('normalize-' + key, 'shell', 'wm', key, value)
        capture.start()
        capture.environment()
        for name, point in [('initial', None), ('outer-ring', (7, 28)), ('inner-ring', (7, 84)), ('inner-painted', (49, 84))]:
            if point:
                capture.command(name, *(['shell', 'input', 'tap'] if a.platform == 'android'
                                else ['shell', 'uitest', 'uiInput', 'click']), *point)
            time.sleep(0.8)
            path, tree = capture.tree(name)
            text = [n['text'] for n in tree if re.fullmatch(r'Hits \d+', n.get('text', ''))]
            assert len(text) == 1, (name, text)
            image = capture.screenshot(name)
            observations.append({'probe': name, 'point': point, 'text': text[0],
                                 'tree': str(path), 'tree_sha256': sha(path),
                                 'image': str(image), 'image_sha256': sha(image)})
            write_json(capture.directory / 'observations.json', observations)
    finally:
        for key, raw in original.items():
            override = re.search(r'Override \w+:\s*(\S+)', raw)
            capture.command('restore-' + key, 'shell', 'wm', key, override.group(1) if override else 'reset')
