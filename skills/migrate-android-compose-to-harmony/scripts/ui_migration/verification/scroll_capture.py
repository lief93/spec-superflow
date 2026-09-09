"""ADB/HDC acquisition; page-specific routes and gestures live in the profile."""
import json
from pathlib import Path
import subprocess
import time

from .long_page import sha, validate_config
from .runtime_tree import read_tree, select, bounds


class Device:
    def __init__(self, platform, profile, out):
        self.platform, self.profile, self.out = platform, profile, out
        self.prefix = [profile['tool'], '-s' if platform == 'android' else '-t', profile['device']['serial']]
        self.events = []

    def run(self, *arguments, binary=False):
        command = self.prefix + list(map(str, arguments))
        start = time.time()
        result = subprocess.run(command, capture_output=True, timeout=90)
        name = f'command-{len(self.events):04}.{"bin" if binary else "log"}'
        (self.out/name).write_bytes(result.stdout + (b'' if binary else result.stderr))
        self.events.append({'argv': command, 'exit_code': result.returncode, 'seconds': time.time()-start, 'output': name, 'output_sha256': sha(self.out/name)})
        (self.out/'commands.json').write_text(json.dumps(self.events,indent=2))
        if result.returncode or (not binary and b'[Fail]' in result.stdout):
            raise ValueError('device command failed; see local command log')
        return result.stdout

    def start(self):
        p = self.profile
        if self.platform == 'android':
            self.run('shell','am','force-stop',p['package'])
            self.run('shell','am','start','-W','-n',p['entry'])
        else:
            self.run('shell','aa','force-stop',p['package'])
            self.run('shell','aa','start','-a',p['entry'],'-b',p['package'])
        time.sleep(p.get('settle_seconds', 1.5))

    def action(self, action):
        if action['type'] == 'tap':
            x,y = action['point']
            if self.platform == 'android':
                self.run('shell','input','tap',x,y)
            else:
                self.run('shell','uitest','uiInput','click',x,y)
        elif action['type'] == 'swipe':
            coords = [*action['from'], *action['to']]
            if self.platform == 'android':
                self.run('shell','input','swipe',*coords,action.get('duration_ms',850))
            else:
                self.run('shell','uitest','uiInput','swipe',*coords,action.get('velocity',1200))
        else:
            raise ValueError('only explicit tap/swipe acquisition actions are supported')
        time.sleep(self.profile.get('settle_seconds',1.5))

    def snapshot(self, token):
        tree = self.out/(token + ('.xml' if self.platform == 'android' else '.json'))
        image = self.out/(token+'.png')
        if self.platform == 'android':
            self.run('shell','uiautomator','dump','/sdcard/a2h-long-page.xml')
            self.run('pull','/sdcard/a2h-long-page.xml',tree)
            image.write_bytes(self.run('exec-out','screencap','-p',binary=True))
        else:
            self.run('shell','uitest','dumpLayout','-p','/data/local/tmp/a2h-long-page.json','-a')
            self.run('file','recv','/data/local/tmp/a2h-long-page.json',tree)
            self.run('shell','uitest','screenCap','-p','/data/local/tmp/a2h-long-page.png')
            self.run('file','recv','/data/local/tmp/a2h-long-page.png',image)
        return tree, image


def capture(config, platform, out):
    validate_config(config)
    profile = config['capture'][platform]
    out = Path(out)
    out.mkdir(parents=True,exist_ok=False)
    device = Device(platform,profile,out)
    package = Path(profile['artifact']).resolve()
    digest = sha(package)
    if digest != profile['artifact_sha256']:
        raise ValueError('artifact hash drift before install')
    device.run('install', *(['-r'] if platform == 'android' else []), package)
    record = {'schema':'long-page-recording.v1','platform':platform,'page_id':config['page_id'],
              'state_id':config['state_id'],'device':profile['device'],'artifact_sha256':digest,
              'device_metadata_source':'explicit verified profile; screenshot dimensions rechecked by analyzer',
              'frames':[], 'stream_status':{}}
    specs = {s['id']:s for s in config['components']}
    for stream in config['streams']:
        plan = stream['capture'][platform]
        if not 2 <= plan.get('max_frames',20) <= 200 or not plan.get('entry_assertions'):
            raise ValueError('capture requires entry assertions and 2..200 frames')
        device.start()
        for action in plan.get('setup',[]):
            device.action(action)
        previous = None
        settled = False
        for index in range(plan.get('max_frames',20)):
            token = f'{stream["id"]}-{index:03}'
            tree,image = device.snapshot(token)
            nodes = read_tree(tree)
            if index == 0:
                for selector in plan['entry_assertions']:
                    if len(select(nodes,selector)) != 1:
                        raise ValueError('page/state entry assertion failed')
            container = select(nodes,plan['container'])
            if len(container) != 1 or container[0]['attributes'].get('scrollable') != 'true':
                raise ValueError('scroll container is missing, ambiguous, or not scrollable')
            b = bounds(container[0]['attributes']['bounds'])
            for x,y in (plan['scroll']['from'],plan['scroll']['to']):
                if not b[0] < x < b[2] or not b[1] < y < b[3]:
                    raise ValueError('gesture lies outside runtime scroll container')
            # Ignore system clocks and unrelated runtime nodes in the end signature.
            signature = []
            for spec in specs.values():
                selected = select(nodes,spec['selectors'][platform])
                signature.append((spec['id'],[n['attributes'].get('origBounds') or n['attributes']['bounds'] for n in selected]))
            end_nodes = select(nodes,specs[stream['end_component']]['selectors'][platform])
            frame = {'id':token,'stream':stream['id'],'screenshot':image.name,'screenshot_sha256':sha(image),
                     'tree':tree.name,'tree_sha256':sha(tree),'after_scroll':index>0}
            record['frames'].append(frame)
            settled = index > 0 and signature == previous and len(end_nodes) == 1
            record['stream_status'][stream['id']] = 'end_observed' if settled else 'incomplete'
            (out/'recording.json').write_text(json.dumps(record,indent=2))
            if settled:
                break
            previous = signature
            device.action(plan['scroll'])
        if not settled:
            record['stream_status'][stream['id']] = 'limit_without_verified_end'
    if sha(package) != digest:
        raise ValueError('artifact drift during capture')
    (out/'recording.json').write_text(json.dumps(record,indent=2))
    return record
