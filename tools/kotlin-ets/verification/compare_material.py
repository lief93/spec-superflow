"""Fixed-threshold local MaterialText comparison; no image viewing or alignment."""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageChops, ImageStat
from common import sha, write_json

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('android', type=Path)
    parser.add_argument('harmony', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    records = [json.loads((p / 'result.json').read_text()) for p in (args.android, args.harmony)]
    for item in records:
        assert sha(item['tree']) == item['tree_sha256']
        assert sha(item['image']) == item['image_sha256']
    source, target = records
    first, second = [Image.open(item['image']).convert('RGB') for item in records]
    assert first.size == second.size == (1320, 2856)
    diff = ImageChops.difference(first, second)
    mean = sum(ImageStat.Stat(diff).mean) / 3
    red, green, blue = diff.split()
    histogram = ImageChops.lighter(ImageChops.lighter(red, green), blue).histogram()
    fraction = sum(histogram[25:]) / (1320 * 2856)
    geometry = {name: {'android': value, 'harmony': target['bounds'][name],
                       'max_delta_pixels': max(abs(a-b) for a, b in zip(value, target['bounds'][name]))}
                for name, value in source['bounds'].items()}
    passed = mean <= 8 and fraction <= 0.08 and all(x['max_delta_pixels'] <= 3.5 for x in geometry.values())
    passed = passed and source['labels_nonoverlapping'] and target['labels_nonoverlapping']
    difference = args.output / 'difference.png'
    diff.save(difference)
    result = {'status': 'pass' if passed else 'fail',
              'thresholds': {'mean_channel_error': 8, 'pixel_max_channel_delta': 24,
                             'changed_fraction': 0.08, 'geometry_delta_pixels': 3.5},
              'mae_255': mean, 'fraction_delta_over_24': fraction, 'geometry': geometry,
              'labels_nonoverlapping': {'android': source['labels_nonoverlapping'], 'harmony': target['labels_nonoverlapping']},
              'android_sha256': source['image_sha256'], 'harmony_sha256': target['image_sha256'],
              'difference_sha256': sha(difference)}
    write_json(args.output / 'comparison.json', result)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if passed else 1)
