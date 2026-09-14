"""Invoke the independent public CLI and bind its implementation and inputs."""
import argparse
import json
from pathlib import Path
from common import HERE, Evidence, sha, write_json
from build import verify_inputs


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('run', type=Path)
    p.add_argument('--attempt', default='1')
    a = p.parse_args()
    run = a.run.resolve()
    config = verify_inputs(run)
    root = Path(config.get('tool_root', HERE.parent))
    output = run / ('generated-' + a.attempt)
    output.mkdir(exist_ok=False)
    def implementation():
        files = sorted((root / 'src').rglob('*.kt')) + [root / 'kotlin-ets']
        return {str(file): sha(file) for file in files}
    original = implementation()
    e = Evidence(run / ('generation-' + a.attempt))
    cp = run / 'compose-classpath.txt'
    write_json(output / 'generator-inputs.json', {'implementation': original,
                'source': {'path': config['source'], 'sha256': config['source_sha256']},
                'classpath': {line: sha(line) for line in cp.read_text().splitlines() if line}})
    e.run('source-to-ets', [root / 'kotlin-ets', '--entry', config['root'],
          '--classpath-file', cp, '--out', output / 'Page.ets', config['source']], timeout=600)
    assert original == implementation(), 'Compiler changed during generation'
    verify_inputs(run)
    write_json(output / 'identity.json', {'Page.ets': sha(output / 'Page.ets')})
    print(output / 'Page.ets')
