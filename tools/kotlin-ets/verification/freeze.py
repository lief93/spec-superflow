"""Retain a hash manifest for reviewable verification inputs, commands and results."""
import argparse
from pathlib import Path
from common import HERE, sha, write_json

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('run', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    run = a.run.resolve()
    files = {p for p in run.iterdir() if p.is_file()}
    for directory in run.iterdir():
        if directory.is_dir() and directory.name not in ('android', 'harmony'):
            files.update(p for p in directory.rglob('*') if p.is_file())
    for platform in ('android', 'harmony'):
        directory = run / platform
        for file in directory.rglob('*'):
            relative = file.relative_to(directory)
            if file.is_file() and not set(relative.parts).intersection({'build', '.gradle', '.hvigor', 'oh_modules', '.test'}):
                files.add(file)
    import json
    package_manifest = run / 'packages.json'
    packages = json.loads(package_manifest.read_text()) if package_manifest.exists() else {}
    files.update(Path(item['path']) for item in packages.values())
    for file in HERE.rglob('*'):
        if file.is_file() and not set(file.relative_to(HERE).parts).intersection({'evidence', '__pycache__'}):
            files.add(file)
    write_json(a.output, {'run': str(run), 'status': 'diagnostic-freeze-not-acceptance',
                         'package_manifest_present': package_manifest.exists(),
                         'files': {str(file): sha(file) for file in sorted(files)}})
    print(f'{len(files)} exact file identities: {a.output}')
