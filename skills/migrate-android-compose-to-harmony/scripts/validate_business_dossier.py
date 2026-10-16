"""Lightweight dossier checks shared by the business and page CLI direct paths.

References are reading/verification anchors, not a static call graph or semantic proof.
This mode never produces the structured Contract's source/runtime completion flags.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

from validate_ai_safe_tree import is_safe_relative_path, validate as validate_safe_tree


HEADERS = ['Chain / trigger', 'Source rule and data effect', 'Target', 'Checks and current result']
LINK = re.compile(r'\[([^\]]+)\]\(([^\s()]+)\)')


def requested(argv):
    options = argv[:argv.index('--') if '--' in argv else len(argv)]
    return any(value == '--dossier' or value.startswith('--dossier=') for value in options)


def chains_from_markdown(text):
    rows, active = [], False
    for line in text.splitlines():
        if line.strip() == '## Business chains':
            active = True
            continue
        if active and line.startswith('#'):
            break
        if not active or not line.strip().startswith('|'):
            continue
        cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
        if cells == HEADERS or all(re.fullmatch(r':?-+:?', cell) for cell in cells):
            continue
        if len(cells) != 4 or not all(cells):
            raise ValueError('Business chains requires four nonempty table columns')
        if cells[0] in [row[0] for row in rows]:
            raise ValueError('duplicate business chain: ' + cells[0])
        rows.append(cells)
    if not rows:
        raise ValueError('missing Business chains table')
    return rows


def references(cell, root, role, manifest=None):
    links = LINK.findall(cell)
    if not links:
        raise ValueError(role + ': missing code reference (relative/path#Lstart-Lend)')
    records = []
    for label, reference in links:
        match = re.fullmatch(r'(.+)#L([1-9][0-9]*)-L([1-9][0-9]*)', reference)
        if not match or not is_safe_relative_path(match[1]):
            raise ValueError(role + ': unsafe or invalid code reference ' + reference)
        relative, start, end = match[1], int(match[2]), int(match[3])
        path = root / relative
        if (not path.resolve().is_relative_to(root.resolve()) or root.is_symlink() or
                any((root / Path(*Path(relative).parts[:index])).is_symlink()
                    for index in range(1, len(Path(relative).parts) + 1))):
            raise ValueError(role + ': symbolic link or escaped reference ' + reference)
        if manifest is not None and relative not in manifest['text_files']:
            raise ValueError(role + ': source absent from safe manifest: ' + relative)
        if {'test', 'tests', 'ohosTest', 'androidTest', 'testFixtures'}.intersection(Path(relative).parts):
            raise ValueError(role + ': expected production source: ' + relative)
        raw = path.read_bytes()
        lines = raw.decode('utf-8').splitlines()
        if start > end or end > len(lines) or not ''.join(lines[start-1:end]).strip():
            raise ValueError(role + ': empty or missing source span: ' + reference)
        records.append({'label': label, 'reference': reference,
                        'sha256': hashlib.sha256(raw).hexdigest()})
    return records


def source_coverage(units, requirements, snapshot, manifest):
    """Account for selected source text, without interpreting or emitting APIs."""
    from analyze_compose_project import lexical_code_mask
    if not units:
        raise ValueError('source scope is required: use --source-file for each reached source file or complete definition span')
    mapped = {}
    for requirement in requirements.values():
        for anchor in requirement['references']:
            match = re.fullmatch(r'(.+)#L(\d+)-L(\d+)', anchor['reference'])
            mapped.setdefault(match[1], set()).update(range(int(match[2]), int(match[3]) + 1))
    missing, scope = [], []
    for unit in sorted(set(units)):
        path = unit.split('#', 1)[0]
        if path not in manifest['text_files']:
            raise ValueError('source scope file is absent from safe snapshot: ' + path)
        text = (snapshot / path).read_text(encoding='utf-8')
        ref = unit if '#' in unit else f'{path}#L1-L{len(text.splitlines())}'
        anchor = references(f'[scope]({ref})', snapshot, 'source scope', manifest)[0]
        scope.append(anchor)
        match = re.fullmatch(r'(.+)#L(\d+)-L(\d+)', ref)
        code = lexical_code_mask(text, mask_strings=False).splitlines()
        for line in range(int(match[2]), int(match[3]) + 1):
            value = code[line - 1].strip()
            if (value and not re.fullmatch(r'[{};]+', value)
                    and not re.match(r'^(package|import)\s', value)
                    and line not in mapped.get(path, set())):
                missing.append(f'{path}:{line}')
    if missing:
        raise ValueError('source coverage is incomplete: ' + ', '.join(missing))
    return {'complete': True, 'scope': scope}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dossier', required=True, type=Path)
    parser.add_argument('--phase', required=True, choices=('source', 'implementation', 'target'))
    parser.add_argument('--snapshot', required=True, type=Path)
    parser.add_argument('--target', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--source-baseline', type=Path,
                        help='Passing source-phase report saved before implementation')
    parser.add_argument('--source-file', action='append', default=[],
                        help='Source phase: reached production file, optionally #Lstart-Lend for a complete scoped definition')
    parser.add_argument('--timeout', type=float, default=300,
                        help='Maximum seconds for the explicit test command (default: 300)')
    parser.add_argument('command', nargs=argparse.REMAINDER,
                        help='After --, the test command emitting JUnit XML on stdout')
    args = parser.parse_args(argv)
    protected_output = bool(args.output and (
        (args.phase == 'source' and args.output.exists()) or
        (args.source_baseline and args.output.resolve() == args.source_baseline.resolve())))
    report = {'artifact_type': 'business_dossier_validation', 'phase': args.phase,
              'verdict': 'fail', 'references_valid': False, 'checks_passed': False,
              'business_verified': False, 'runtime_complete': False, 'chains': [],
              'errors': [], 'failed_checks': [], 'references': {},
              'limits': ['Source coverage is checked within the source-selected definition scope.',
                         'Behavior is checked by source-derived tests of real target entries.',
                         'Native runtime and visual acceptance remain separate gates.']}
    try:
        if protected_output:
            raise ValueError('refusing to overwrite an existing source baseline')
        command = args.command[1:] if args.command[:1] == ['--'] else args.command
        if args.phase != 'target' and command:
            raise ValueError('test command is only used by --phase target')
        safety = validate_safe_tree(args.snapshot, require_safe_manifest=True)
        if not safety['ok']:
            raise ValueError('unsafe snapshot: ' + json.dumps(safety['violations']))
        manifest = json.loads((args.snapshot / '.android-to-harmony-safe.json').read_text())
        if args.target is not None:
            protected = [args.snapshot.resolve()]
            original = manifest.get('source_root') or manifest.get('source', {}).get('root')
            if original:
                protected.append(Path(original).resolve())
            target_root = args.target.resolve()
            if any(target_root.is_relative_to(path) or path.is_relative_to(target_root) for path in protected):
                raise ValueError('source and target must be separate')
        raw = args.dossier.read_bytes()
        report['dossier_sha256'] = hashlib.sha256(raw).hexdigest()
        rows = chains_from_markdown(raw.decode('utf-8'))
        report['chains'] = [row[0] for row in rows]
        report['source_requirements'] = {}
        report['snapshot_sha256'] = hashlib.sha256(
            (args.snapshot / '.android-to-harmony-safe.json').read_bytes()).hexdigest()
        for chain, source, target, checks in rows:
            report['references'][chain] = {'source': references(source, args.snapshot, chain, manifest)}
            tests = sorted(set(re.findall(r'`([^`]+)`', checks)))
            if not tests:
                raise ValueError(chain + ': missing source-derived test identifiers')
            report['source_requirements'][chain] = {
                'rule': source, 'references': report['references'][chain]['source'], 'tests': tests}
            if args.phase != 'source':
                if args.target is None:
                    raise ValueError('implementation checks require --target')
                anchors = references(target, args.target, chain)
                for anchor in anchors:
                    path = anchor['reference'].split('#')[0]
                    if ('/src/main/' not in path or
                            Path(path).suffix not in {'.ets', '.ts', '.js', '.mjs', '.cjs'}):
                        raise ValueError(chain + ': expected production target code: ' + path)
                missing = {'entry', 'implementation', 'binding', 'consumer'} - {a['label'] for a in anchors}
                if missing:
                    raise ValueError(chain + ': missing target anchors: ' + ', '.join(sorted(missing)))
                report['references'][chain]['target'] = anchors
        if args.phase == 'source':
            report['source_coverage'] = source_coverage(
                args.source_file, report['source_requirements'], args.snapshot, manifest)
        else:
            if args.source_baseline is None:
                raise ValueError('source baseline is required before implementation checks')
            baseline_bytes = args.source_baseline.read_bytes()
            baseline = json.loads(baseline_bytes)
            if (not isinstance(baseline, dict) or baseline.get('phase') != 'source'
                    or baseline.get('artifact_type') != 'business_dossier_validation'
                    or baseline.get('verdict') != 'pass'
                    or baseline.get('snapshot_sha256') != report['snapshot_sha256']
                    or not isinstance(baseline.get('source_requirements'), dict)
                    or not baseline.get('source_coverage', {}).get('complete')):
                raise ValueError('source baseline is invalid or belongs to a different source snapshot')
            before, now = baseline['source_requirements'], report['source_requirements']
            changed = sorted(key for key in before.keys() | now.keys() if before.get(key) != now.get(key))
            if changed:
                raise ValueError('source baseline changed or lost chains/checks: ' + ', '.join(changed))
            report['source_coverage'] = source_coverage(
                [anchor['reference'] for anchor in baseline['source_coverage']['scope']],
                report['source_requirements'], args.snapshot, manifest)
            report['source_baseline_sha256'] = hashlib.sha256(baseline_bytes).hexdigest()
        report['references_valid'] = True
        if args.phase == 'target':
            if not command:
                raise ValueError('executed checks are required: supply -- followed by the test command')
            if not 0 < args.timeout < float('inf'):
                raise ValueError('--timeout must be finite and positive')
            started = time.monotonic()
            execution = report['execution'] = {'command': command, 'cwd': str(args.target.resolve()),
                                               'exit_code': None, 'passed_tests': []}
            try:
                completed = subprocess.run(command, cwd=args.target, capture_output=True,
                                           text=True, timeout=args.timeout)
            finally:
                execution['seconds'] = time.monotonic() - started
            execution.update(exit_code=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)
            junit = ET.fromstring(completed.stdout)
            if junit.tag not in {'testsuites', 'testsuite'}:
                raise ValueError('behavior command must emit JUnit XML on stdout')
            for case in junit.iter('testcase'):
                status = next((kind for kind in ('failure', 'error', 'skipped')
                               if case.find(kind) is not None), None)
                if status:
                    name = case.get('name')
                    report['failed_checks'].append({
                        'test': name, 'chains': [chain for chain, requirement in
                            report['source_requirements'].items() if name in requirement['tests']],
                        'status': status})
            if completed.returncode != 0 or report['failed_checks']:
                failures = '; '.join(
                    f"{check['test']} ({', '.join(check['chains']) or 'additional test'}): {check['status']}"
                    for check in report['failed_checks'])
                raise ValueError('behavior test command failed' + (': ' + failures if failures else ''))
            for suite in [node for node in junit.iter() if node.tag in {'testsuites', 'testsuite'}]:
                if (any(int(suite.get(key, '0')) != 0 for key in ('failures', 'errors', 'skipped', 'disabled'))
                        or ('tests' in suite.attrib and int(suite.get('tests')) != len(list(suite.iter('testcase'))))):
                    raise ValueError('JUnit summary is failing, skipped or inconsistent with its test cases')
            cases = list(junit.iter('testcase'))
            names = [case.get('name') for case in cases]
            if (not names or any(not name for name in names) or len(names) != len(set(names))
                    or any(list(junit.iter(kind)) for kind in ('failure', 'error', 'skipped'))):
                raise ValueError('tests must be uniquely named, executed and passing; no skipped cases')
            required = {name for row in rows for name in re.findall(r'`([^`]+)`', row[3])}
            if required - set(names):
                raise ValueError('missing executed behavior tests: ' + ', '.join(sorted(required - set(names))))
            for chain, source, target, checks in rows:
                current = {'source': references(source, args.snapshot, chain, manifest),
                           'target': references(target, args.target, chain)}
                if current != report['references'][chain]:
                    raise ValueError('code changed during behavior checks: ' + chain)
            if hashlib.sha256(args.dossier.read_bytes()).hexdigest() != report['dossier_sha256']:
                raise ValueError('dossier changed during behavior checks')
            if hashlib.sha256(args.source_baseline.read_bytes()).hexdigest() != report['source_baseline_sha256']:
                raise ValueError('source baseline changed during behavior checks')
            execution['passed_tests'] = names
            report['checks_passed'] = True
        report['verdict'] = 'pass'
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.TimeoutExpired, ET.ParseError) as error:
        report['errors'].append(str(error))
    if args.output and not protected_output:
        from validate_behavior_contract_v2 import write_json
        write_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(report['verdict'] != 'pass')


if __name__ == '__main__':
    sys.exit(main())
