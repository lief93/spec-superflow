#!/usr/bin/env python3
"""Generate one source-page.json from an exact Compose root and explicit project styles."""
import argparse
import json
from pathlib import Path
import subprocess
import time

from analyze_compose_project import load_snapshot
from init_harmony_project import load_contract, sha256_file
from real_page_pipeline import build_source_page_spec
from ui_migration.frontend.project_styles import load_style_definitions
from ui_migration.progress import Progress, step, checkpoint
from ui_migration.contracts.source_storage import pack_source_page


def generate(args):
    started = time.monotonic()
    styles = step('load-project-styles', load_style_definitions, args.style_definitions.expanduser().resolve())
    contract, contract_path = step('load-contract', load_contract, args.contract)
    snapshot, manifest = step('validate-snapshot', load_snapshot, args.snapshot)
    if Path(contract['source']['safe_snapshot_root']).resolve() != snapshot:
        raise ValueError('--snapshot does not match the contract source.safe_snapshot_root')
    source_file = (snapshot / args.root_source).resolve()
    if Path(args.root_source).is_absolute() or not source_file.is_relative_to(snapshot):
        raise ValueError('--root-source must be a relative file inside --snapshot')
    root_source = source_file.relative_to(snapshot).as_posix()
    if root_source not in manifest['text_files'] or not source_file.is_file():
        raise ValueError('--root-source is not an approved snapshot text file: ' + root_source)
    roots = [item.get('root', {}) for item in contract['ui'].get(
        'custom_composable_call_graph', {}).get('transitive_closures', [])]
    matches = [r for r in roots if r == {'source':root_source, 'composable':args.root_composable}]
    if len(matches) != 1:
        candidates = sorted({r.get('composable', '') for r in roots if r.get('source') == root_source})
        raise ValueError('Expected one exact root; candidates in ' + root_source + ': ' + ', '.join(candidates))
    output = args.output.expanduser().resolve()
    original = Path(manifest['source_root']).resolve() if 'source_root' in manifest else Path(contract['source']['original_root']).resolve()
    if output.is_relative_to(snapshot) or output.is_relative_to(original):
        raise ValueError('--output must be outside the Android source and snapshot')
    if output.exists():
        raise ValueError('Output already exists; use a new page output path: ' + str(output))
    page = step('build-source-page', build_source_page_spec, contract, root_source, args.root_composable,
        args.page_id, args.state_id, sha256_file(contract_path), snapshot, style_definitions=styles)
    output.parent.mkdir(parents=True, exist_ok=True)
    checkpoint('write-source-page', components=len(page['components']), output=str(output))
    with output.open('x', encoding='utf-8') as stream:
        json.dump(pack_source_page(page), stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return {'ok':True, 'output':str(output), 'root':page['root'], 'page':page['page'],
        'component_count':len(page['components']), 'seconds':time.monotonic()-started,
        'style_definitions':str(args.style_definitions.expanduser().resolve()),
        'scope':'source-inventory', 'visual_verified':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('snapshot', 'contract', 'style-definitions', 'output'):
        parser.add_argument('--'+name, required=True, type=Path)
    parser.add_argument('--root-source', required=True)
    parser.add_argument('--root-composable', required=True)
    parser.add_argument('--page-id', required=True)
    parser.add_argument('--state-id', default='default')
    args = parser.parse_args()
    try:
        with Progress('source-page'):
            result = generate(args)
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({'ok':False, 'stage':'source-page', 'error':str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
