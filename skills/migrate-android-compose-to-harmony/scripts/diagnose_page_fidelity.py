#!/usr/bin/env python3
"""Attach local screenshot-comparison evidence to one migration run's diagnosis.md."""
import argparse
import hashlib
import json
from pathlib import Path

from ui_migration.verification.generation_diagnosis import diagnose_run, render_markdown


def refresh(run_dir, comparison_report):
    run_dir, comparison_report = Path(run_dir).resolve(), Path(comparison_report).resolve()
    result_path = run_dir/'result.json'
    report = json.loads(result_path.read_text(encoding='utf-8'))
    raw = comparison_report.read_bytes()
    comparison = json.loads(raw)
    if not isinstance(report, dict) or not isinstance(comparison, dict):
        raise ValueError('Expected result.json and comparison.json objects')
    if report.get('status') not in {'generated', 'partial_generation', 'failed'}:
        raise ValueError('Wait for the migration run to finish before refreshing its diagnosis')
    diagnosis = diagnose_run(run_dir, report, comparison)
    diagnosis['comparison_evidence'] = {'path': str(comparison_report), 'sha256': hashlib.sha256(raw).hexdigest()}
    report['diagnosis'] = diagnosis
    output = run_dir/'diagnosis.md'
    report['diagnosis_report'] = str(output)
    output.write_text(render_markdown(diagnosis), encoding='utf-8')
    result_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'ok': True, 'diagnosis_report': str(output), 'unresolved_count': diagnosis['unresolved_count'],
            'visual_finding_count': diagnosis['visual_triage']['finding_count'],
            'comparable': diagnosis['visual_triage']['comparable']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True, type=Path)
    parser.add_argument('--comparison-report', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = refresh(args.run_dir, args.comparison_report)
    except (OSError, ValueError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
