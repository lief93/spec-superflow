"""Evidence logging and device bindings for this independent slice only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).resolve().parent
ADB = '/Users/lief123/Library/Android/sdk/platform-tools/adb'
HDC = '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc'
DEVECO = Path('/Applications/DevEco-Studio.app/Contents')
ANDROID = [ADB, '-s', 'emulator-5560']
HARMONY = [HDC, '-t', '127.0.0.1:15557']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


class Evidence:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        assert not (self.directory / 'commands.json').exists(), 'Keep prior evidence: use a fresh run or attempt'
        self.records = []

    def run(self, name, argv, cwd=None, env=None, check=True, binary=None, timeout=240):
        argv = list(map(str, argv))
        if argv[0] in (ADB, HDC):
            assert argv[:3] in (ANDROID, HARMONY), 'Unauthorized device'
        record = {'name': name, 'argv': argv, 'cwd': str(cwd or Path.cwd()),
                  'environment_overrides': env or {}, 'started_at': time.time()}
        prefix = self.directory / f'{len(self.records):03d}-{name}'
        record['stdout'] = str(binary or prefix.with_suffix('.stdout'))
        record['stderr'] = str(prefix.with_suffix('.stderr'))
        self.records.append(record)
        write_json(self.directory / 'commands.json', self.records)
        try:
            with open(record['stdout'], 'wb') as out, open(record['stderr'], 'wb') as err:
                result = subprocess.run(argv, cwd=cwd, env={**os.environ, **(env or {})},
                                        stdout=out, stderr=err, timeout=timeout)
            record['exit'] = result.returncode
        except BaseException as error:
            record['error'] = repr(error)
            raise
        finally:
            record['finished_at'] = time.time()
            write_json(self.directory / 'commands.json', self.records)
        if check and result.returncode:
            raise RuntimeError(f'{name} exit {result.returncode}: {record["stdout"]}; {record["stderr"]}')
        content = Path(record['stdout']).read_bytes()
        if check and argv[0] in (ADB, HDC) and not binary:
            assert b'[Fail]' not in content and b'Error type ' not in content, record
        return content


def build_env():
    return {'JAVA_HOME': str(DEVECO / 'jbr/Contents/Home'),
            'ANDROID_HOME': '/Users/lief123/Library/Android/sdk',
            'DEVECO_SDK_HOME': str(DEVECO / 'sdk'),
            'PATH': str(DEVECO / 'tools/node/bin') + ':' + str(DEVECO / 'tools/ohpm/bin') + ':' + os.environ['PATH']}
