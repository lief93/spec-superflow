"""Record actual SourceValues initializer counts on either authorized device."""
import argparse
from collections import Counter
from pathlib import Path
import re
import time
from capture import Capture
from common import sha, write_json

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--platform', choices=['android', 'harmony'], required=True)
    args = parser.parse_args()
    capture = Capture(args.run.resolve(), args.platform, 'source-values-1')
    original = {}
    observations = []
    try:
        if args.platform == 'android':
            for key, value in [('size', '1320x2856'), ('density', '560')]:
                original[key] = capture.command('original-' + key, 'shell', 'wm', key).decode()
                capture.command('normalize-' + key, 'shell', 'wm', key, value)
        capture.installed_identity()
        capture.start()
        capture.environment()
        for token in ('initial', 'settled'):
            time.sleep(1.2)
            path, tree = capture.tree(token)
            texts = Counter(n.get('text') for n in tree if n.get('text') and n.get('_effectively_visible', True))
            assert texts == Counter({'Value 1': 2, 'Count 2': 1}), (token, texts)
            image = capture.screenshot(token)
            observations.append({'token': token, 'counts': dict(texts),
                                 'tree': str(path), 'tree_sha256': sha(path),
                                 'image': str(image), 'image_sha256': sha(image)})
        write_json(capture.directory / 'result.json', {'status': 'pass', 'observations': observations})
        print(observations)
    except BaseException as error:
        write_json(capture.directory / 'result.json', {'status': 'fail', 'error': repr(error), 'observations': observations})
        raise
    finally:
        for key, raw in original.items():
            override = re.search(r'Override \w+:\s*(\S+)', raw)
            capture.command('restore-' + key, 'shell', 'wm', key, override.group(1) if override else 'reset')
