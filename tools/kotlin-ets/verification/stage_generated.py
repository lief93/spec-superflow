"""Copy generator output without patching it; build only after this seam is ready."""
import argparse
import json
from pathlib import Path
import shutil

from common import HERE, sha, write_json


def stage(run, ets, component):
    run, ets = Path(run).resolve(), Path(ets).resolve()
    config = json.loads((run / 'inputs.json').read_text())
    pages = run / 'harmony/entry/src/main/ets/pages'
    pages.mkdir(parents=True, exist_ok=True)
    if component:
        output = run / 'harmony/entry/src/main/ets/generated'
        output.mkdir(exist_ok=False)
        for file in ets.parent.glob('*.ets'):
            shutil.copy2(file, output / file.name)
            config['generated'][str(file)] = {'sha256': sha(file), 'copy': str(output / file.name)}
        (pages / 'Index.ets').write_text((HERE / 'templates/harmony/Index.ets.in').read_text()
                                       .replace('__COMPONENT__', component).replace('__MODULE__', ets.stem))
    else:
        assert '@Entry' in ets.read_text(), 'Supply --component for a generated exported component'
        shutil.copy2(ets, pages / 'Index.ets')
        config['generated'][str(ets)] = {'sha256': sha(ets), 'copy': str(pages / 'Index.ets')}
    config['status'] = 'ready-to-build'
    config['component'] = component
    ability = run / 'harmony/entry/src/main/ets/entryability/EntryAbility.ets'
    ability.write_text((HERE / 'templates/harmony/EntryAbility.ets').read_text().replace('__GENERATED_SHA256__', sha(ets)))
    config['runtime_generated_sha256'] = sha(ets)
    write_json(run / 'inputs.json', config)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('run', type=Path)
    p.add_argument('ets', type=Path)
    p.add_argument('--component')
    a = p.parse_args()
    stage(a.run, a.ets, a.component)
