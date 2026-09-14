"""Quantify a failed initial pair without weakening the full capture gate."""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageChops, ImageStat
from capture import nodes, tagged, bounds
from common import sha, write_json

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('run', type=Path)
    a = p.parse_args()
    run = a.run.resolve()
    output = run / 'initial-diagnostic'
    output.mkdir(exist_ok=False)
    android = run / 'capture-android-1'
    harmony = run / 'capture-harmony-1'
    paths = [x / 'initial-settled.png' for x in (android, harmony)]
    first, second = [Image.open(path).convert('RGB') for path in paths]
    assert first.size == second.size == (1320, 2856)
    diff = ImageChops.difference(first, second)
    diff.save(output / 'difference.png')
    red, green, blue = diff.split()
    histogram = ImageChops.lighter(ImageChops.lighter(red, green), blue).histogram()
    source, target = nodes(android / 'initial.xml'), nodes(harmony / 'initial.json')
    measured = {}
    for tag in ('pager', 'action-button'):
        left, right = bounds(tagged(source, tag)), bounds(tagged(target, tag))
        measured[tag] = {'android': left, 'harmony': right,
                         'max_delta_pixels': max(abs(x-y) for x, y in zip(left, right))}
    for text in ('Field Notes', 'Chapter 1', 'Page 1 of 4', 'Callback 0'):
        left, right = [bounds(next(n for n in tree if n.get('text') == text)) for tree in (source, target)]
        measured[text] = {'android': left, 'harmony': right}
    report = {'status': 'FAIL-initial-layout-not-full-sequence-acceptance',
              'mae_255': sum(ImageStat.Stat(diff).mean)/3,
              'fraction_delta_over_24': sum(histogram[25:])/(1320*2856),
              'thresholds': {'mae_255': 8, 'fraction_delta_over_24': 0.08, 'geometry_delta_pixels': 3.5},
              'geometry': measured, 'images': {str(path): sha(path) for path in paths},
              'difference_sha256': sha(output / 'difference.png'),
              'note': 'No AI viewing; Harmony full capture stopped at missing painted indicator rectangles.'}
    write_json(output / 'report.json', report)
    print(json.dumps(report, indent=2))
