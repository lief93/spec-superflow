#!/usr/bin/env python3
"""Compare ordered JSON observations from executed source and target tests.

This compares evidence, not business rules. It neither runs tests nor establishes
scenario coverage, source completeness, or the existing business acceptance gate.
"""
import argparse
import hashlib
import json
from pathlib import Path


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON field: ' + key)
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError('non-finite JSON value: ' + value)


def read_trace(path, prefix):
    raw = path.read_bytes()
    records = [json.loads(line.split(prefix, 1)[1], object_pairs_hook=unique_object,
                          parse_constant=reject_constant)
               for line in raw.decode('utf-8').splitlines() if prefix in line]
    if any(not isinstance(record, dict) or not record for record in records):
        raise ValueError('each observation must be a nonempty JSON object')
    return records, {'path': str(path.resolve()), 'sha256': hashlib.sha256(raw).hexdigest(),
                     'records': len(records)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--target', required=True, type=Path)
    parser.add_argument('--source-prefix', required=True)
    parser.add_argument('--target-prefix', required=True)
    parser.add_argument('--expected-records', required=True, type=int)
    args = parser.parse_args()
    report = {'verdict': 'fail', 'business_verified': False, 'records_compared': 0,
              'differences': [], 'errors': [],
              'limits': ['Trace equality does not prove tests passed or all source branches ran.',
                         'Use execution reports and the existing behavior contract gate separately.']}
    try:
        if args.expected_records <= 0 or not args.source_prefix or not args.target_prefix:
            raise ValueError('positive expected-records and nonempty prefixes are required')
        left, report['source'] = read_trace(args.source, args.source_prefix)
        right, report['target'] = read_trace(args.target, args.target_prefix)
        if len(left) != args.expected_records or len(right) != args.expected_records:
            raise ValueError(f'expected {args.expected_records} records on each side; '
                             f'found source={len(left)}, target={len(right)}')
        report['records_compared'] = len(left)
        report['differences'] = [{'record': index, 'source': source, 'target': target}
                                 for index, (source, target) in enumerate(zip(left, right))
                                 if json.dumps(source, sort_keys=True, allow_nan=False)
                                 != json.dumps(target, sort_keys=True, allow_nan=False)]
        if not report['differences']:
            report['verdict'] = 'pass'
    except (OSError, ValueError) as error:
        report['errors'].append(str(error))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(report['verdict'] != 'pass')


if __name__ == '__main__':
    raise SystemExit(main())
