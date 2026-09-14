"""Real gestures, source-derived assertions and settled captures; no AI image use."""
import argparse
import json
from pathlib import Path
import re
import shutil
import time
import xml.etree.ElementTree as ET

from PIL import Image, ImageChops, ImageStat
from common import ANDROID, HARMONY, Evidence, sha, write_json
from build import verify_inputs

VIEWPORT = (0, 0, 1320, 2856)
DETAILS = ['Observe the world around you.', 'Collect one small discovery.',
           'Connect it with a new idea.', 'Take your next step.']


def nodes(path):
    if path.suffix == '.xml':
        return [dict(n.attrib) for n in ET.parse(path).iter('node')]
    result = []
    def walk(value, visible=True):
        if isinstance(value, dict):
            if 'attributes' in value:
                attributes = dict(value['attributes'])
                visible = visible and attributes.get('visible') != 'false' and attributes.get('opacity') not in ('0', '0.000000')
                attributes['_effectively_visible'] = visible
                result.append(attributes)
            for key, child in value.items():
                if key != 'attributes':
                    walk(child, visible)
        elif isinstance(value, list):
            for child in value:
                walk(child, visible)
    walk(json.loads(path.read_text()))
    return result


def tagged(tree, tag):
    found = [n for n in tree if n.get('id') == tag or n.get('resource-id') == tag]
    assert len(found) == 1, (tag, len(found))
    return found[0]


def bounds(node):
    raw = node['bounds']
    if isinstance(raw, str):
        return tuple(map(int, re.findall(r'-?\d+', raw)))
    return tuple(raw[k] for k in ('left', 'top', 'right', 'bottom'))


def mae(first, second):
    return sum(ImageStat.Stat(ImageChops.difference(first, second)).mean) / 3


def assert_android_foreground(raw):
    activities = re.findall(r'topResumedActivity=([^\n]+)', raw)
    assert len(activities) == 1 and 'dev.ets.verification/.MainActivity' in activities[0], (
        'Expected verification foreground activity before gestures', activities)


def indicator_rectangles(image, tree):
    # Compose accessibility touch targets can expand and partition visual bounds.
    regions = [bounds(tagged(tree, 'indicator-' + str(i))) for i in range(4)]
    l = max(0, min(b[0] for b in regions) - 56)
    t = max(0, min(b[1] for b in regions) - 56)
    r = min(image.width, max(b[2] for b in regions) + 56)
    b = min(image.height, max(b[3] for b in regions) + 56)
    pixels = image.load()
    rectangles = []
    for color in (0, 136):
        active = {}
        for y in range(t, b + 1):
            runs = set()
            start = None
            for x in range(l, r + 1):
                matches = y < b and x < r and all(abs(c-color) <= 2 for c in pixels[x, y])
                if matches and start is None:
                    start = x
                if not matches and start is not None:
                    if x - start == 70:
                        runs.add((start, x))
                    start = None
            for span in set(active) - runs:
                first = active.pop(span)
                if y - first == 28:
                    rectangles.append({'bounds': [span[0], first, span[1], y], 'color': color})
            for span in runs:
                active.setdefault(span, y)
    rectangles.sort(key=lambda item: item['bounds'][0])
    assert len(rectangles) == 4, ('Expected four actual 20x8dp indicator rectangles', rectangles)
    return rectangles


class Capture:
    def __init__(self, run, platform, attempt, android_oracle=None):
        self.run = run
        self.platform = platform
        self.android_oracle = android_oracle or run / 'capture-android-1/boundaries.json'
        self.directory = run / f'capture-{platform}-{attempt}'
        self.directory.mkdir(exist_ok=False)
        self.e = Evidence(self.directory / 'commands')
        scripts = self.directory / 'harness'
        scripts.mkdir()
        for name in ('capture.py', 'common.py', 'build.py'):
            shutil.copy2(Path(__file__).parent / name, scripts / name)
        write_json(scripts / 'identity.json', {file.name: sha(file) for file in scripts.glob('*.py')})
        self.prefix = ANDROID if platform == 'android' else HARMONY
        self.states = []

    def command(self, name, *args, **kwargs):
        return self.e.run(name, self.prefix + list(map(str, args)), **kwargs)

    def start(self):
        if self.platform == 'android':
            self.command('stop', 'shell', 'am', 'force-stop', 'dev.ets.verification')
            self.command('start', 'shell', 'am', 'start', '-W', '-n', 'dev.ets.verification/.MainActivity')
        else:
            self.command('stop', 'shell', 'aa', 'force-stop', 'com.joker.kit')
            self.command('start', 'shell', 'aa', 'start', '-a', 'EntryAbility', '-b', 'com.joker.kit')
        time.sleep(2)
        if self.platform == 'android':
            foreground = self.command('launch-foreground', 'shell', 'dumpsys', 'activity', 'activities').decode()
            assert_android_foreground(foreground)
        package = 'dev.ets.verification' if self.platform == 'android' else 'com.joker.kit'
        assert self.command('launch-pid', 'shell', 'pidof', package).decode().strip().isdigit(), 'Missing launched process'

    def installed_identity(self):
        packages = json.loads((self.run / 'packages.json').read_text())
        if self.platform == 'android':
            raw = self.command('package-path', 'shell', 'pm', 'path', 'dev.ets.verification').decode()
            path = raw.strip().removeprefix('package:')
            actual = self.command('installed-sha256', 'shell', 'sha256sum', path).decode().split()[0]
            assert actual == packages['apk']['sha256'], 'Installed Android APK differs'
        else:
            installed = json.loads((self.run / 'install-harmony/identity.json').read_text())
            for key in ('main_hap', 'test_hap'):
                assert installed[key] == packages[key] and sha(packages[key]['path']) == packages[key]['sha256']
        write_json(self.directory / 'package-identity.json', packages)

    def screenshot(self, token):
        if self.platform == 'android':
            foreground = self.command('capture-foreground', 'shell', 'dumpsys', 'activity', 'activities').decode()
            assert_android_foreground(foreground)
        image = self.directory / (token + '.png')
        if self.platform == 'android':
            self.command(token, 'exec-out', 'screencap', '-p', binary=image)
        else:
            self.command(token, 'shell', 'uitest', 'screenCap', '-p', '/data/local/tmp/kotlin-ets.png')
            self.command(token + '-recv', 'file', 'recv', '/data/local/tmp/kotlin-ets.png', image)
        assert Image.open(image).size == (1320, 2856), 'Viewport mismatch'
        return image

    def tree(self, token):
        if self.platform == 'android':
            path = self.directory / (token + '.xml')
            self.command('dump-' + token, 'shell', 'uiautomator', 'dump', '/sdcard/kotlin-ets.xml')
            self.command('tree-' + token, 'pull', '/sdcard/kotlin-ets.xml', path)
        else:
            path = self.directory / (token + '.json')
            self.command('dump-' + token, 'shell', 'uitest', 'dumpLayout', '-p', '/data/local/tmp/kotlin-ets.json', '-a')
            self.command('tree-' + token, 'file', 'recv', '/data/local/tmp/kotlin-ets.json', path)
        tree = nodes(path)
        if self.platform == 'android':
            packages = {n['package'] for n in tree if n.get('package')}
            assert packages == {'dev.ets.verification'}, ('Wrong captured package', packages)
        else:
            packages = {n['bundleName'] for n in tree if n.get('bundleName') and n.get('_effectively_visible', True)}
            assert packages == {'com.joker.kit'}, ('Wrong captured bundle', packages)
        return path, tree

    def environment(self):
        package = 'dev.ets.verification' if self.platform == 'android' else 'com.joker.kit'
        pid = self.command('pid', 'shell', 'pidof', package).decode().strip()
        assert pid.isdigit(), pid
        raw = self.command('environment', 'logcat', '-d', '--pid=' + pid, '-v', 'raw', '-s', 'SliceEnvironment:I', '*:S') if self.platform == 'android' else self.command('environment', 'shell', 'hilog', '-x', '-P', pid, '-T', 'SliceEnvironment')
        entries = [line[line.index('{'):] for line in raw.decode().splitlines() if '{' in line]
        assert entries, 'Missing current process environment'
        value = json.loads(entries[-1])
        if self.platform == 'android':
            assert value['locale'] == 'en-US' and value['fontScale'] == 1 and value['nightMode'] == 16, value
            assert value['density'] == 3.5 and tuple(value['bounds']) == VIEWPORT, value
        else:
            c = value['config']
            assert c['language'] == 'en-US' and c['fontSizeScale'] == 1 and c['colorMode'] == 1, value
            assert value['window']['width'] == 1320 and value['window']['height'] == 2856, value
            assert value['density'] == 3.5, value
            identity = self.command('runtime-generated-identity', 'shell', 'hilog', '-x', '-P', pid, '-T', 'SliceIdentity').decode()
            expected = json.loads((self.run / 'inputs.json').read_text())['runtime_generated_sha256']
            assert expected in identity, 'Current process does not identify the expected generated ETS'
        write_json(self.directory / 'environment.json', value)

    def state(self, token, page, count):
        time.sleep(1.2)
        path, tree = self.tree(token)
        tree = [n for n in tree if n.get('_effectively_visible', True)]
        actual = {n.get('text', '') for n in tree}
        expected = ['Field Notes', 'Chapter ' + str(page + 1), DETAILS[page],
                    f'Page {page + 1} of 4', f'Callback {count}', 'Finish' if page == 3 else 'Continue']
        for text in expected:
            assert text in actual, (token, text, sorted(actual))
            matches = [bounds(n) for n in tree if n.get('text') == text]
            assert any(0 <= l < r <= 1320 and 0 <= t < b <= 2856 for l, t, r, b in matches), ('Offscreen expected content', text, matches)
        assert ('Continue' if page == 3 else 'Finish') not in actual, 'Stale button branch'
        first = self.screenshot(token + '-first')
        time.sleep(0.8)
        second = self.screenshot(token + '-settled')
        image = Image.open(second).convert('RGB')
        movement = mae(Image.open(first).convert('RGB'), image)
        assert movement <= 0.25, (token, 'unsettled', movement)
        indicators = indicator_rectangles(image, tree)
        assert [x['color'] for x in indicators] == [0 if i == page else 136 for i in range(4)], (token, indicators)
        assert [indicators[i+1]['bounds'][0] - indicators[i]['bounds'][0] for i in range(3)] == [98]*3, '28dp outer indicator width'
        assert len({x['bounds'][1] for x in indicators}) == 1, 'Indicator alignment'
        geometry = {tag: bounds(tagged(tree, tag)) for tag in ('pager', 'action-button')}
        title = next(n for n in tree if n.get('text') == 'Chapter ' + str(page + 1))
        detail = next(n for n in tree if n.get('text') == DETAILS[page])
        # A zero-width Spacer has no Android accessibility node; its actual
        # height is observable between the neighboring source-defined Texts.
        spacing = bounds(detail)[1] - bounds(title)[3]
        assert spacing == 56, ('source (base + extra).dp spacing', spacing)
        geometry['computed_spacing_pixels'] = spacing
        geometry['indicator_outer_width_pixels'] = 98
        geometry['indicator_inner_size_pixels'] = [70, 28]
        page_label = next(n for n in tree if n.get('text') == f'Page {page + 1} of 4')
        outer_height = bounds(page_label)[1] - geometry['pager'][3] - 56
        assert outer_height == 56, ('16dp outer indicator height after excluding Row 8dp padding', outer_height)
        geometry['indicator_outer_height_pixels'] = outer_height
        for tag, height in [('pager', 840), ('action-button', 168)]:
            b = geometry[tag]
            assert b[3] - b[1] == height, (token, tag, b, height)
        item = {'token': token, 'page': page, 'callback': count, 'expected_text': expected,
                'tree': str(path), 'tree_sha256': sha(path), 'first': str(first), 'first_sha256': sha(first),
                'image': str(second), 'image_sha256': sha(second), 'settled_mae': movement,
                'indicators': indicators, 'geometry': geometry}
        self.states.append(item)
        write_json(self.directory / 'states.json', self.states)
        return tree

    def swipe(self, tree, back=False):
        l, t, r, b = bounds(tagged(tree, 'pager'))
        y, left, right = (t+b)//2, round(l+(r-l)*0.18), round(l+(r-l)*0.82)
        start, end = (left, right) if back else (right, left)
        if self.platform == 'android':
            self.command('swipe', 'shell', 'input', 'swipe', start, y, end, y, 850)
        else:
            self.command('swipe', 'shell', 'uitest', 'uiInput', 'swipe', start, y, end, y, 1000)

    def boundary_probe(self):
        probes = []
        # First-slice modifier requirement: 4dp padding around a 20x8dp Box.
        # Record actual behavior, including Android's native minimum touch target.
        painted = self.states[-1]['indicators'][2]['bounds']
        l, t, r, b = painted
        points = [('padding-ring', (l-7, (t+b)//2)), ('painted-inner', ((l+r)//2, (t+b)//2))]
        middle = (self.states[-1]['indicators'][1]['bounds'][2] + l) // 2
        points.extend((name, (middle + offset, (t+b)//2)) for name, offset in (
            ('gap-left', -1), ('gap-tie', 0), ('gap-right', 1)))
        if self.platform == 'harmony':
            oracle = self.android_oracle
            source = json.loads(oracle.read_text())
            points = [(item['name'], tuple(item['point'])) for item in source]
            assert [name for name, _ in points] == ['padding-ring', 'painted-inner', 'gap-left', 'gap-tie', 'gap-right']
            write_json(self.directory / 'boundary-oracle.json', {'path': str(oracle), 'sha256': sha(oracle)})
        for name, point in points:
            self.start()
            _, initial = self.tree('before-boundary-' + name)
            initial_text = {n.get('text', '') for n in initial}
            assert {'Field Notes', 'Chapter 1', 'Page 1 of 4', 'Callback 0', 'Continue'} <= initial_text, (
                'Wrong source initial state before boundary tap', initial_text)
            self.command('boundary-' + name, *(['shell', 'input', 'tap'] if self.platform == 'android'
                         else ['shell', 'uitest', 'uiInput', 'click']), *point)
            time.sleep(1.2)
            path, tree = self.tree('boundary-' + name)
            texts = {n.get('text', '') for n in tree}
            pages = [int(match.group(1))-1 for text in texts if (match := re.fullmatch(r'Page ([1-4]) of 4', text))]
            assert len(pages) == 1 and 'Callback 0' in texts, texts
            image = self.screenshot('boundary-' + name)
            probes.append({'name': name, 'point': point, 'observed_page': pages[0],
                           'image': str(image), 'image_sha256': sha(image),
                           'tree': str(path), 'tree_sha256': sha(path)})
            write_json(self.directory / 'boundaries.json', probes)
        assert probes[1]['observed_page'] == 2, 'Inner indicator click did not navigate'
        self.start()

    def execute(self):
        original = {}
        try:
            self.installed_identity()
            if self.platform == 'android':
                for key, value in [('size', '1320x2856'), ('density', '560')]:
                    original[key] = self.command('original-' + key, 'shell', 'wm', key).decode()
                    self.command('normalize-' + key, 'shell', 'wm', key, value)
                write_json(self.directory / 'original-display.json', original)
            self.start()
            self.environment()
            tree = self.state('initial', 0, 0)
            for page in range(1, 4):
                self.swipe(tree)
                tree = self.state('forward-' + str(page), page, 0)
            self.swipe(tree, back=True)
            tree = self.state('back-2', 2, 0)
            l, t, r, b = bounds(tagged(tree, 'action-button'))
            args = ['shell', 'input', 'tap'] if self.platform == 'android' else ['shell', 'uitest', 'uiInput', 'click']
            self.command('callback', *args, (l+r)//2, (t+b)//2)
            self.state('callback', 3, 1)
            self.start()
            self.state('restart', 0, 0)
            self.boundary_probe()
            self.installed_identity()
            write_json(self.directory / 'result.json', {'status': 'pass', 'states': len(self.states)})
        except BaseException as error:
            write_json(self.directory / 'result.json', {'status': 'fail', 'error': repr(error), 'states': len(self.states)})
            raise
        finally:
            for key, raw in original.items():
                override = re.search(r'Override \w+:\s*(\S+)', raw)
                self.command('restore-' + key, 'shell', 'wm', key, override.group(1) if override else 'reset')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('run', type=Path)
    p.add_argument('--platform', choices=['android', 'harmony'], required=True)
    p.add_argument('--attempt', default='1')
    p.add_argument('--android-oracle', type=Path, help='Exact Android boundary evidence for Harmony replay')
    a = p.parse_args()
    verify_inputs(a.run.resolve())
    Capture(a.run.resolve(), a.platform, a.attempt, a.android_oracle).execute()
