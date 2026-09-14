"""Retain the exact source basis independently of subsequent workspace changes."""
import argparse
import json
from pathlib import Path
import shutil
from common import HERE, sha, write_json

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('basis_run', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    root = HERE.parent
    run = args.basis_run.resolve()
    basis = json.loads((run / 'generated-1/generator-inputs.json').read_text())
    def inventory():
        return {str(p): sha(p) for p in sorted((root / 'src').rglob('*.kt')) + [root / 'kotlin-ets']}
    assert inventory() == basis['implementation'], 'Live implementation no longer matches run basis'
    destination = args.destination.resolve()
    destination.mkdir(exist_ok=False)
    copied = destination / 'tools/kotlin-ets'
    shutil.copytree(root, copied, ignore=shutil.ignore_patterns('__pycache__', 'evidence'))
    assert inventory() == basis['implementation'], 'Implementation changed during copying'
    for path, expected in basis['implementation'].items():
        assert sha(copied / Path(path).relative_to(root)) == expected
    evidence = destination / 'basis'
    evidence.mkdir()
    for name in ('generator-inputs.json', 'identity.json', 'Page.ets'):
        shutil.copy2(run / 'generated-1' / name, evidence / name)
    shutil.copy2(run / 'compose-classpath.txt', evidence / 'compose-classpath.txt')
    manifest = destination / 'manifest.json'
    files = {str(p.relative_to(destination)): sha(p) for p in destination.rglob('*') if p.is_file()}
    write_json(manifest, {'basis_run': str(run), 'tool_root': str(copied),
                         'basis_implementation': basis['implementation'],
                         'files': files, 'compose_classpath': basis['classpath'],
                         'generated_sha256': sha(evidence / 'Page.ets')})
    config = json.loads((run / 'inputs.json').read_text())
    source = copied / Path(config['source']).relative_to(root)
    assert sha(source) == config['source_sha256']
    write_json(run / 'frozen-inputs.json', {'source': str(source),
               'source_sha256': config['source_sha256'], 'tool_root': str(copied),
               'manifest': str(manifest), 'manifest_sha256': sha(manifest)})
    for path in destination.rglob('*'):
        if path.is_file():
            path.chmod(path.stat().st_mode & ~0o222)
    print(json.dumps({'tool_root': str(copied), 'manifest': str(manifest),
                      'manifest_sha256': sha(manifest), 'files': len(files)}, indent=2))
