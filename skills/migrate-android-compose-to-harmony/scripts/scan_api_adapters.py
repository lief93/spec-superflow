#!/usr/bin/env python3
"""Scan analyzed page facts and emit a small, disabled project extension worklist."""
import argparse
import hashlib
import json
from pathlib import Path
from ui_migration.frontend.api_adapters.scan import scan_source_page, skeleton


def scan(source, output):
    raw = source.read_bytes()
    report = scan_source_page(json.loads(raw))
    report['source_page_sha256'] = hashlib.sha256(raw).hexdigest()
    output.mkdir(parents=True, exist_ok=False)
    (output / 'api-scan.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    lines = ['# Source API Extension Scan', '', report['scope'], '',
             'Candidates are not verified missing APIs. State/business calls are not extension tasks.', '',
             '| API | Classification | Adapter / capability | Locations |', '| --- | --- | --- | --- |']
    for index, record in enumerate(report['apis']):
        locations = '; '.join(f"{o['source'].get('source')}:{o['source'].get('line')} ({o['field']})"
                              for o in record['occurrences'][:4])
        lines.append(f"| `{record['symbol']}` | {record['category']} | {record['adapter'] or record['capability'] or 'needs classification'} | {locations} |")
        if record['category'] == 'api_gap_candidate' and (code := skeleton(record)) is not None:
            (output / f'candidate_{index}.py').write_text(code)
    (output / 'README.md').write_text('\n'.join(lines) + '\n\nSkeletons are disabled. Implement, test, hash and explicitly register each trusted module.\n')
    (output / 'adapters.json').write_text(json.dumps({'schema': 'ui-migration.api-adapters.v1', 'modules': []}, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-page', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(scan(args.source_page, args.output_dir)['counts']))
