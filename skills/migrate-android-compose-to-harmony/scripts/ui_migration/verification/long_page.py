"""Compare declared long-page components without inferring content from images."""
import hashlib
import html
import json
import math
from pathlib import Path
import re
import statistics

from PIL import Image, ImageChops, ImageDraw, ImageFilter
from compare_local_screenshots import channel_ssim, image_ssim
from .runtime_tree import bounds, read_tree, select


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_config(config):
    if config.get('schema') != 'long-page-check.v1' or not config.get('components') or not config.get('streams'):
        raise ValueError('nonempty components and streams are required')
    for collection in ('components','streams','gaps'):
        ids = [s['id'] for s in config.get(collection,[])]
        if len(ids) != len(set(ids)) or not all(re.fullmatch('[A-Za-z0-9_-]+', i) for i in ids):
            raise ValueError(collection + ' ids must be unique safe tokens')
    for spec in config['components']:
        for platform in ('android','harmony'):
            selector = spec['selectors'][platform]
            if (not isinstance(selector,dict) or not selector or selector.get('match') == {}
                    or selector.get('parent') == {}):
                raise ValueError('empty component selector')
        if not set(spec.get('known_viewport_edges',[])) <= {'left','top','right','bottom'}:
            raise ValueError('invalid known viewport edges')


def artifact(root, name, digest):
    path = root / name
    if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink() or not path.is_file():
        raise ValueError('invalid recording artifact path')
    if sha(path) != digest:
        raise ValueError('recording artifact hash mismatch')
    return path


def load_record(path, config):
    record = json.loads(path.read_text())
    if record.get('schema') != 'long-page-recording.v1':
        raise ValueError('invalid recording schema')
    for key in ('page_id', 'state_id'):
        if record.get(key) != config.get(key):
            raise ValueError(key + ' mismatch')
    device = record['device']
    if (not device.get('serial') or not re.fullmatch('[a-f0-9]{64}', record.get('artifact_sha256', ''))
            or not bounds(device.get('content_bounds')) or len(device.get('size_px', [])) != 2):
        raise ValueError('missing device or artifact identity')
    if any(not isinstance(device.get(key), (int, float)) or not math.isfinite(device[key]) or device[key] <= 0
           for key in ('density', 'font_scale')):
        raise ValueError('invalid density or font scale')
    viewport = device['content_bounds']
    if viewport[0] < 0 or viewport[1] < 0 or viewport[2] > device['size_px'][0] or viewport[3] > device['size_px'][1]:
        raise ValueError('content viewport outside screenshot')
    for frame in record['frames']:
        for key in ('screenshot', 'tree'):
            frame[key + '_path'] = artifact(path.parent, frame[key], frame[key + '_sha256'])
        with Image.open(frame['screenshot_path']) as image:
            if list(image.size) != device['size_px']:
                raise ValueError('screenshot size mismatch')
        frame['nodes'] = read_tree(frame['tree_path'])
    if len({f['id'] for f in record['frames']}) != len(record['frames']):
        raise ValueError('duplicate frame ids')
    return record


def intersect(a, b):
    return bounds([max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])])


def observations(record, spec):
    result, problems = [], []
    selector = spec['selectors'][record['platform']]
    viewport = record['device']['content_bounds']
    for frame in record['frames']:
        if spec.get('stream') and spec['stream'] != frame['stream']:
            continue
        found = select(frame['nodes'], selector)
        if len(found) > 1:
            problems.append('ambiguous selector in frame ' + frame['id'])
            continue
        if not found:
            continue
        a = found[0]['attributes']
        visible = intersect(bounds(a['bounds']), viewport)
        if not visible:
            continue
        original = bounds(a.get('origBounds'))
        if original and intersect(original,visible) != visible:
            problems.append('inconsistent original bounds in frame ' + frame['id'])
            continue
        if original is None:
            # UIAutomator can report clipped bounds. Edge contact cannot prove full size.
            b = bounds(a['bounds'])
            touching = [edge for edge,i in [('left',0),('top',1),('right',2),('bottom',3)]
                        if (b[i] <= viewport[i] if i < 2 else b[i] >= viewport[i])]
            if set(touching) - set(spec.get('known_viewport_edges',[])):
                problems.append('clipped bounds without original geometry in frame ' + frame['id'])
                continue
            original = b
        result.append({'frame': frame['id'], 'stream': frame['stream'], 'bounds': original,
                       'visible': visible, 'path': frame['screenshot_path'],
                       'node_id': a.get('id', ''), 'node_type': a.get('type', '')})
    return result, problems


def compose_component(record, observations, output, target_density):
    if not observations:
        return {'status': 'missing'}
    density = record['device']['density']
    sizes = {(o['bounds'][2]-o['bounds'][0], o['bounds'][3]-o['bounds'][1]) for o in observations}
    if len(sizes) != 1:
        return {'status': 'unstable_bounds', 'observed_sizes_px': sorted(sizes)}
    width, height = next(iter(sizes))
    if width * height > 40_000_000:
        return {'status': 'component_too_large_for_local_limit'}
    canvas = Image.new('RGB', (width, height))
    mask = Image.new('L', (width, height))
    for o in observations:
        crop = Image.open(o['path']).convert('RGB').crop(tuple(o['visible']))
        offset = (o['visible'][0]-o['bounds'][0], o['visible'][1]-o['bounds'][1])
        region = (offset[0], offset[1], offset[0]+crop.width, offset[1]+crop.height)
        overlap = mask.crop(region)
        if overlap.getbbox():
            difference = ImageChops.difference(canvas.crop(region), crop).convert('L')
            conflict = ImageChops.multiply(difference.point(lambda p: 255 if p > 8 else 0), overlap)
            if conflict.getbbox():
                return {'status': 'unstable_pixels_across_scroll', 'frame': o['frame']}
        canvas.paste(crop, offset)
        ImageDraw.Draw(mask).rectangle((region[0], region[1], region[2]-1, region[3]-1), fill=255)
    coverage = mask.histogram()[255] / (width * height)
    result = {'size_dp': [width/density, height/density], 'pixel_coverage': coverage,
              'frames': [o['frame'] for o in observations], 'status': 'complete' if coverage == 1 else 'partial'}
    if coverage == 1:
        normalized_size = (max(1, round(width / density * target_density)), max(1, round(height / density * target_density)))
        if canvas.size != normalized_size:
            canvas = canvas.resize(normalized_size, Image.Resampling.LANCZOS)
        canvas.save(output)
    return result


def evaluate(config, left_path, right_path, out):
    validate_config(config)
    specs = config['components']
    ids = [s['id'] for s in specs]
    if len(ids) != len(set(ids)) or not all(re.fullmatch('[A-Za-z0-9_-]+', i) for i in ids):
        raise ValueError('component ids must be unique safe tokens')
    records = [load_record(Path(p), config) for p in (left_path, right_path)]
    if [r['platform'] for r in records] != ['android', 'harmony']:
        raise ValueError('expected Android then Harmony recording')
    devices = [r['device'] for r in records]
    if devices[0]['font_scale'] != devices[1]['font_scale']:
        raise ValueError('font scale mismatch')
    logical = [tuple((d['content_bounds'][i+2]-d['content_bounds'][i])/d['density'] for i in (0,1)) for d in devices]
    if any(abs(a-b) > .01 for a,b in zip(*logical)) or devices[0].get('theme') != devices[1].get('theme'):
        raise ValueError('logical viewport or theme mismatch')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    tolerance = config.get('geometry_tolerance_dp', 1)
    minimum = config.get('min_ssim', .95)
    if not 0 <= tolerance <= 1 or not 0 < minimum <= 1:
        raise ValueError('invalid threshold; geometry tolerance cannot exceed 1dp')
    rows, observed = [], {}
    for spec in specs:
        row = {'id': spec['id'], 'platforms': {}, 'pass': False}
        for record in records:
            platform = record['platform']
            obs, problems = observations(record, spec)
            observed[(platform, spec['id'])] = obs
            result = compose_component(record, obs, out / f'{spec["id"]}-{platform}.png', devices[0]['density'])
            result['diagnostics'] = problems
            result['geometry'] = [{k:v for k,v in o.items() if k != 'path'} for o in obs]
            if any('ambiguous' in p for p in problems):
                result['status'] = 'ambiguous'
            row['platforms'][platform] = result
        a, b = row['platforms'].values()
        if a['status'] == b['status'] == 'complete':
            row['size_delta_dp'] = [v-u for u,v in zip(a['size_dp'], b['size_dp'])]
            images = [Image.open(out/f'{spec["id"]}-{p}.png').convert('RGB') for p in ('android','harmony')]
            size = tuple(max(i.size[axis] for i in images) for axis in (0,1))
            padded = []
            for image in images:
                canvas = Image.new('RGB', size, config.get('canvas_background', '#FFFFFF'))
                canvas.paste(image, (0,0))
                padded.append(canvas)
            for platform, image in zip(('android','harmony'),padded):
                image.save(out/f'{spec["id"]}-{platform}.png')
            row['ssim'] = {'color': image_ssim(*padded),
                           'luma': channel_ssim(*(i.convert('L') for i in padded)),
                           'edges': channel_ssim(*(i.convert('L').filter(ImageFilter.FIND_EDGES).filter(ImageFilter.GaussianBlur(1)) for i in padded))}
            row['pass'] = min(row['ssim'].values()) >= minimum and max(map(abs,row['size_delta_dp'])) <= tolerance
        rows.append(row)
    streams = []
    for stream in config['streams']:
        result = {'id': stream['id'], 'platforms': {}}
        for record in records:
            frames = [f for f in record['frames'] if f['stream'] == stream['id']]
            def signature(frame):
                return [(s['id'], [o['bounds'] for o in observed[(record['platform'],s['id'])] if o['frame'] == frame['id']]) for s in specs]
            end = observed.get((record['platform'], stream['end_component']), [])
            result['platforms'][record['platform']] = (len(frames) >= 2 and frames[-1].get('after_scroll') is True and signature(frames[-1]) == signature(frames[-2])
                and any(o['frame'] == frames[-1]['id'] for o in end))
        result['pass'] = all(result['platforms'].values())
        streams.append(result)
    gaps = []
    for spec in config.get('gaps', []):
        values = {}
        axis = 0 if spec.get('axis', 'y') == 'x' else 1
        for record in records:
            before = observed.get((record['platform'],spec['before']), [])
            after = observed.get((record['platform'],spec['after']), [])
            samples = [(b['bounds'][axis]-a['bounds'][axis+2])/record['device']['density'] for a in before for b in after
                       if a['frame'] == b['frame'] and a['stream'] == b['stream']
                       and a['visible'][axis+2] == a['bounds'][axis+2] and b['visible'][axis] == b['bounds'][axis]]
            if samples:
                values[record['platform']] = statistics.median(samples)
        delta = values.get('harmony', 0)-values.get('android', 0) if len(values) == 2 else None
        gaps.append({'id': spec['id'], 'values_dp': values, 'delta_dp': delta, 'pass': delta is not None and abs(delta) <= tolerance})
    report = {'schema': 'long-page-result.v1', 'page_id': config['page_id'], 'state_id': config['state_id'],
              'scope': 'declared components and scroll streams, not unlisted app content or behavior',
              'components': rows, 'streams': streams, 'gaps': gaps,
              'expected': len(rows), 'complete': sum(all(v['status']=='complete' for v in r['platforms'].values()) for r in rows),
              'passed': sum(r['pass'] for r in rows),
              'input_hashes': [sha(Path(p)) for p in (left_path,right_path)],
              'artifacts': {r['platform']:r['artifact_sha256'] for r in records},
              'config_sha256': hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest(),
              'verdict': 'pass' if all(r['pass'] for r in rows+streams+gaps) else 'fail',
              'limits': ['No OCR or model vision', 'SSIM compares component-local content, not absolute scroll position',
                         'Declared gaps check inter-component layout separately',
                         'Missing original bounds cannot be reconstructed from clipped accessibility bounds']}
    (out/'report.json').write_text(json.dumps(report,indent=2))
    write_html(report,out)
    return report


def write_html(report, out):
    sections = []
    for row in report['components']:
        sides = []
        for platform, value in row['platforms'].items():
            image = f'{row["id"]}-{platform}.png'
            sides.append(f'<div><h3>{platform}: {html.escape(value["status"])}</h3>'
                         + (f'<img src="{image}">' if (out/image).exists() else '<p>没有完整可比图片</p>') + '</div>')
        sections.append(f'<section><h2>{row["id"]}：{"通过" if row["pass"] else "失败"}</h2><p>SSIM {html.escape(str(row.get("ssim", "不可用")))}；宽高差 dp {html.escape(str(row.get("size_delta_dp", "不可用")))}</p><div class="pair">'+''.join(sides)+'</div></section>')
    (out/'index.html').write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>长页面校验</title><style>
body{max-width:1100px;margin:24px auto;padding:0 16px;font:16px system-ui;color:#222;background:#f7f8fa}h1{font-size:24px}h2{font-size:20px}h3{font-size:16px}section{padding:16px 0;border-top:1px solid #ccc}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}img{max-width:100%;display:block}p{line-height:1.6}pre{white-space:pre-wrap;overflow-wrap:anywhere}
</style>'''+f'<h1>长页面校验：{"通过" if report["verdict"]=="pass" else "失败"}</h1><p>声明 {report["expected"]} 个组件，完整可比 {report["complete"]} 个，达标 {report["passed"]} 个。范围仅限配置清单，不代表整 App。缺失/部分采集均不通过。</p><p>只按组件原点平移；仅按设备密度归一化，不缩放以掩盖尺寸差。滚动区域和相邻间距单独判定。</p><a href="report.json">完整数据及诊断</a>'+''.join(sections)+'<h2>滚动区域与间距门禁</h2><pre>'+html.escape(json.dumps({'streams':report['streams'],'gaps':report['gaps']},ensure_ascii=False,indent=2))+'</pre></html>')
