"""Numeric local comparison only. No resampling or screenshot viewing."""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageChops, ImageStat
from common import sha, write_json


def compare(android, harmony, output):
    output.mkdir(exist_ok=False)
    for directory in (android, harmony):
        assert json.loads((directory / 'result.json').read_text())['status'] == 'pass', 'Incomplete runtime evidence'
    a = json.loads((android / 'states.json').read_text())
    h = json.loads((harmony / 'states.json').read_text())
    assert [x['token'] for x in a] == [x['token'] for x in h] == [
        'initial', 'forward-1', 'forward-2', 'forward-3', 'back-2', 'callback', 'restart']
    result = {'thresholds': {'mean_channel_error': 8, 'pixel_max_channel_delta': 24,
                             'changed_fraction': 0.08, 'geometry_delta_pixels': 3.5}, 'states': [], 'status': 'pass'}
    for source, target in zip(a, h):
        assert (source['page'], source['callback']) == (target['page'], target['callback'])
        for item in (source, target):
            assert sha(item['image']) == item['image_sha256']
        first, second = [Image.open(x['image']).convert('RGB') for x in (source, target)]
        assert first.size == second.size == (1320, 2856)
        diff = ImageChops.difference(first, second)
        mean = sum(ImageStat.Stat(diff).mean) / 3
        red, green, blue = diff.split()
        maximum = ImageChops.lighter(ImageChops.lighter(red, green), blue)
        histogram = maximum.histogram()
        fraction = sum(histogram[25:]) / (1320 * 2856)
        verdict = mean <= 8 and fraction <= 0.08
        geometry = {}
        for tag in ('pager', 'action-button'):
            left, right = source['geometry'][tag], target['geometry'][tag]
            delta = max(abs(x-y) for x, y in zip(left, right))
            geometry[tag] = {'android': left, 'harmony': right, 'max_delta_pixels': delta}
            verdict = verdict and delta <= 3.5
        for index, (left, right) in enumerate(zip(source['indicators'], target['indicators'])):
            delta = max(abs(x-y) for x, y in zip(left['bounds'], right['bounds']))
            geometry['indicator-' + str(index)] = {'android': left['bounds'], 'harmony': right['bounds'], 'max_delta_pixels': delta}
            verdict = verdict and delta <= 3.5
        file = output / (source['token'] + '-difference.png')
        diff.save(file)
        result['states'].append({'token': source['token'], 'mae_255': mean,
                                 'fraction_delta_over_24': fraction, 'pass': verdict,
                                 'geometry': geometry,
                                 'android_sha256': source['image_sha256'],
                                 'harmony_sha256': target['image_sha256'],
                                 'difference_sha256': sha(file)})
        if not verdict:
            result['status'] = 'fail'
    if (android / 'boundaries.json').exists() and (harmony / 'boundaries.json').exists():
        source = json.loads((android / 'boundaries.json').read_text())
        target = json.loads((harmony / 'boundaries.json').read_text())
        result['boundaries'] = {'android': source, 'harmony': target,
                               'pass': len(source) == len(target) == 5 and
                               [(x['name'], x['point'], x['observed_page']) for x in source] ==
                               [(x['name'], x['point'], x['observed_page']) for x in target]}
        if not result['boundaries']['pass']:
            result['status'] = 'fail'
    else:
        result['boundaries'] = {'pass': False, 'error': 'Missing paired boundary evidence'}
        result['status'] = 'fail'
    write_json(output / 'comparison.json', result)
    print(json.dumps(result, indent=2))
    return result['status'] == 'pass'


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('android', type=Path)
    p.add_argument('harmony', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    raise SystemExit(0 if compare(a.android, a.harmony, a.output) else 1)
