#!/usr/bin/env python3
"""Independent, conservative Kotlin source denominator. Never generates business facts.

Balanced source regions retain every operation, including unclassified expressions.
This is a coverage ledger, not a Kotlin type checker or a proof of semantic parity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from analyze_compose_project import lexical_code_mask
from validate_ai_safe_tree import validate as validate_safe_tree


def digest(value):
    return hashlib.sha256((json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')) + '\n').encode()).hexdigest()


def safe_sources(snapshot):
    snapshot = Path(snapshot)
    if snapshot.is_symlink():
        raise ValueError('snapshot root is a symbolic link')
    safety = validate_safe_tree(snapshot, require_safe_manifest=True)
    if not safety.get('ok'):
        raise ValueError('unsafe snapshot: ' + json.dumps(safety.get('violations', [])))
    manifest = json.loads((snapshot / '.android-to-harmony-safe.json').read_text())
    texts = {p: (snapshot / p).read_text(encoding='utf-8') for p in manifest['text_files']
             if Path(p).suffix in {'.kt', '.java'}
             and not {'test', 'androidTest', 'testFixtures'}.intersection(Path(p).parts)}
    return manifest, texts


def pairs(code):
    stack, result = [], {}
    for pos, char in enumerate(code):
        if char in '({[':
            stack.append((pos, char))
        elif char in ')}]':
            if not stack or stack[-1][1] != {')': '(', '}': '{', ']': '['}[char]:
                raise ValueError(f'unbalanced source delimiter at offset {pos}')
            opening, _ = stack.pop()
            result[opening] = pos
    if stack:
        raise ValueError(f'unclosed source delimiter at offset {stack[-1][0]}')
    return result


def expression_end(code, start, matching):
    pos = start
    while pos < len(code):
        if pos in matching:
            pos = matching[pos] + 1
            continue
        if code[pos] in ';}':
            break
        if code[pos] == '\n':
            before, after = code[start:pos].rstrip(), code[pos + 1:].lstrip()
            if not (after.startswith(('.', '?.', '?:'))
                    or before.endswith(('=', '.', ',', '->', '+', '-', '&&', '||', '?:'))):
                break
        pos += 1
    return pos


FUNCTION = r'\bfun\s+(?:<[^{}\n]+>\s*)?(?:[\w<>?]+\.)?(`[^`]+`|\w+)\s*\('
DECLARATION = re.compile(
    FUNCTION + r'|\b(?:class|interface|object|typealias)\s+(\w+)'
    r'|\b(?:val|var)\s+(?:[\w<>?.]+\.)?(\w+)')


def declaration_units(code):
    """Index whole top-level definitions, never individual class members.

    Property accessors stay with their property. Leading annotations stay with
    the following definition. Root files remain whole; these units only bound
    transitive source reads so an imported enum does not pull in its sibling UI.
    """
    matching = pairs(code)
    starts, pos, annotation = [], 0, None
    while pos < len(code):
        if code[pos] == '@':
            annotation = pos if annotation is None else annotation
        match = DECLARATION.match(code, pos)
        if match:
            start = code.rfind('\n', 0, pos) + 1
            prefix = code[start:pos].strip().split()
            modifiers = {'public', 'private', 'internal', 'protected', 'data', 'enum', 'sealed',
                         'annotation', 'value', 'open', 'abstract', 'final', 'expect', 'actual',
                         'suspend', 'inline', 'tailrec', 'external', 'infix', 'operator', 'const', 'lateinit'}
            if any(token not in modifiers for token in prefix):
                start = pos
            starts.append((next(g for g in match.groups() if g is not None).strip('`'),
                           annotation if annotation is not None else start))
            annotation = None
            # Skip the name, not its opening parameter delimiter.
            pos = match.end() - (1 if code[match.end() - 1] == '(' else 0)
            continue
        if pos in matching:
            pos = matching[pos] + 1
        else:
            pos += 1
    return [{'symbol': name, 'start': start,
             'end': starts[n + 1][1] if n + 1 < len(starts) else len(code)}
            for n, (name, start) in enumerate(starts)]


def source_regions(path, text):
    code = lexical_code_mask(text)
    matching = pairs(code)
    regions, unresolved = [], []

    def add(kind, start, end, symbol=None):
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if start == end:
            return
        region = {'path': path, 'kind': kind, 'start': start, 'end': end,
                  'start_line': text.count('\n', 0, start) + 1,
                  'end_line': text.count('\n', 0, end - 1) + 1,
                  'expression': text[start:end],
                  'span_sha256': hashlib.sha256(text[start:end].encode()).hexdigest()}
        if symbol is not None:
            region['symbol'] = symbol
        region['id'] = digest(region)
        regions.append(region)

    # Locate the body immediately following each signature. Do not scan through
    # the next declaration for an abstract function's nonexistent implementation.
    for match in re.finditer(FUNCTION, code):
        opening = match.end() - 1
        end_params = matching[opening] + 1
        pos = end_params
        while pos < len(code) and code[pos].isspace():
            pos += 1
        if pos < len(code) and code[pos] == ':':
            pos += 1
            while pos < len(code) and code[pos].isspace():
                pos += 1
            generic_depth = 0
            while pos < len(code) and code[pos] not in '{=;}':
                if code[pos] == '\n' and not generic_depth:
                    break
                if pos in matching:
                    pos = matching[pos] + 1
                    continue
                if code[pos] == '<':
                    generic_depth += 1
                elif code[pos] == '>' and generic_depth:
                    generic_depth -= 1
                pos += 1
            if generic_depth:
                unresolved.append({'path': path, 'reason': 'unsupported callable return type'})
        while pos < len(code) and code[pos].isspace():
            pos += 1
        if pos < len(code) and code[pos] == '{':
            end = matching[pos] + 1
        elif pos < len(code) and code[pos] == '=':
            pos += 1
            while pos < len(code) and code[pos].isspace():
                pos += 1
            end = expression_end(code, pos, matching)
        else:
            end = pos
            if pos < len(code) and not re.match(
                    r'[};@]|\b(?:fun|val|var|class|interface|object|public|private|internal|'
                    r'protected|override|abstract|open|final|suspend|operator|inline|external|companion)\b', code[pos:]):
                unresolved.append({'path': path, 'reason': 'unsupported callable continuation'})
        add('callable', match.start(), end, match.group(1))

    # Split balanced blocks into statement regions. Parent headers and child
    # operations remain separate: one broad function anchor cannot cover them all.
    def block(start, end):
        beginning, pos = start, start
        while pos < end:
            char = code[pos]
            if char in '([':
                inner = pos + 1
                while inner < matching[pos]:
                    if code[inner] == '{':
                        block(inner + 1, matching[inner])
                        inner = matching[inner] + 1
                    else:
                        inner += 1
                pos = matching[pos] + 1
                continue
            if char == '{':
                emit(beginning, pos)
                block(pos + 1, matching[pos])
                pos = matching[pos] + 1
                beginning = pos
                continue
            if char in '\n;':
                before, after = code[beginning:pos].rstrip(), code[pos + 1:end].lstrip()
                if char == ';' or not (after.startswith(('.', '?.', '?:')) or
                    before.endswith(('=', '.', ',', '->', '+', '-', '&&', '||', '?:'))):
                    emit(beginning, pos)
                    beginning = pos + 1
            pos += 1
        emit(beginning, end)

    def emit(start, end):
        snippet = code[start:end].strip()
        if not snippet or re.match(r'^(package|import)\b', snippet):
            return
        # Declaration headers are independently owned; full callable bodies have
        # an additional obligation. Unknown expressions are retained, never skipped.
        kind = ('decision' if re.search(r'\b(?:if|when|else|catch|finally)\b|->|\?:|&&|\|\|', snippet)
                else 'declaration' if re.search(r'\b(?:class|interface|object|fun|typealias)\b', snippet)
                else 'state' if re.search(r'\b(?:val|var)\b', snippet)
                else 'operation')
        add(kind, start, end)

    block(0, len(code))
    if re.search(r'\b(?:getDeclaredMethod|Class\.forName|kotlin\.reflect|external\s+fun)\b', code):
        unresolved.append({'path': path, 'reason': 'dynamic/native behavior needs explicit source resolution'})
    if len(re.findall(r'\bfun\b', code)) != sum(r['kind'] == 'callable' for r in regions):
        unresolved.append({'path': path, 'reason': 'unsupported callable syntax'})
    return sorted(regions, key=lambda r: (r['start'], r['kind'])), unresolved


def census(snapshot, scope):
    manifest, texts = safe_sources(snapshot)
    if (scope.get('schema_version') != 'behavior-source-scope.v1'
            or scope.get('kind') not in {'page', 'flow', 'application'}
            or not isinstance(scope.get('id'), str) or not scope['id']):
        raise ValueError('explicit page/flow/application source scope required')
    revision = manifest.get('source_git', {}).get('revision')
    if not revision or scope.get('source_revision') != revision:
        raise ValueError('source scope revision differs from fixed snapshot')
    entries = scope.get('entry_paths')
    if not isinstance(entries, list) or not entries or any(p not in texts for p in entries):
        raise ValueError('scope entry_paths must name approved production source files')
    masks = {p: lexical_code_mask(t) for p, t in texts.items()}
    packages, symbols, units = {}, {}, {}
    for path, code in masks.items():
        package = re.search(r'(?m)^\s*package\s+([\w.]+)', code)
        packages[path] = package.group(1) if package else ''
        units[path] = declaration_units(code)
        for index, unit in enumerate(units[path]):
            symbols.setdefault(unit['symbol'], set()).add((path, index))
    qualified_symbols = {packages[p] + '.' + s for s, definitions in symbols.items() for p, _ in definitions}
    package_names = set(packages.values())
    file_symbols = {}
    for path in texts:
        file_symbols.setdefault(packages[path] + '.' + Path(path).stem, set()).add(path)
    roots = set(texts) if scope['kind'] == 'application' else set(entries)
    # None denotes a complete root file. A dependency denotes a whole top-level
    # definition (class with every member, or full callable/property/accessors).
    included = {(path, None) for path in roots}
    edges, external = set(), set()
    pending = list(included)
    while pending:
        path, index = pending.pop()
        unit = units[path][index] if index is not None else {'start': 0, 'end': len(masks[path])}
        code = masks[path][unit['start']:unit['end']]
        imports = re.findall(r'(?m)^\s*import\s+([\w.*]+)(?:\s+as\s+(\w+))?', masks[path])
        # Imports are lookup context, not executable references. This matters
        # especially for root files that import unused helpers or entire packages.
        code = re.sub(r'(?m)^\s*(?:import|package)\s+[^\n]+', '', code)
        referenced = set(re.findall(r'\b[A-Za-z_]\w*\b', code))
        dependencies = set()
        lookup_names = referenced.copy()
        for imp, alias in imports:
            if (alias or imp.rsplit('.', 1)[-1]) in referenced:
                lookup_names.update(imp.split('.'))
        for symbol in lookup_names.intersection(symbols):
            candidates = symbols[symbol]
            for other, other_index in candidates:
                qualified = packages[other] + '.' + symbol
                if ((symbol in referenced and packages[other] == packages[path])
                        or any((imp == qualified and (alias or symbol) in referenced)
                               or (imp == packages[other] + '.*' and symbol in referenced)
                               or (imp.startswith(qualified + '.') and
                                   (alias or imp.rsplit('.', 1)[-1]) in referenced)
                               for imp, alias in imports)
                        or qualified in code):
                    dependencies.add((other, other_index))
        for imp, alias in imports:
            if not imp.endswith('*') and (alias or imp.rsplit('.', 1)[-1]) not in referenced:
                continue
            matches = file_symbols.get(imp, set())
            # Unsupported declarations retain the complete matching source file.
            dependencies.update((p, None) for p in matches if not units[p])
            segments = imp.split('.')
            is_local = any('.'.join(segments[:n]) in qualified_symbols for n in range(1, len(segments) + 1))
            if not matches and not is_local and not (imp.endswith('.*') and imp[:-2] in package_names):
                external.add((path, imp))
        for other in dependencies:
            if other[0] != path:
                edges.add((path, other[0]))
            if other not in included and (other[0], None) not in included:
                included.add(other)
                pending.append(other)
    included_paths = {p for p, _ in included}
    projected = {}
    for path in included_paths:
        if (path, None) in included:
            projected[path] = texts[path]
            continue
        chars = ['\n' if c == '\n' else ' ' for c in texts[path]]
        for p, index in included:
            if p == path:
                unit = units[p][index]
                chars[unit['start']:unit['end']] = texts[p][unit['start']:unit['end']]
        projected[path] = ''.join(chars)
    obligations = []
    unresolved = [{'path': path, 'dependency': imp,
                   'reason': 'project import has no approved source definition; resolve generated/unavailable code'}
                  for path, imp in sorted(external)
                  if any(package and imp.startswith(package + '.') for package in package_names)]
    unavailable = [x for x in manifest.get('blocked_files', [])
                   if Path(x.get('path', '')).suffix in {'.kt', '.java'}]
    for item in unavailable:
        symbol = Path(item['path']).stem
        if (scope['kind'] == 'application'
                or any(re.search(r'\b' + re.escape(symbol) + r'\b', lexical_code_mask(projected[p]))
                       for p in included_paths)):
            unresolved.append({'path': item['path'], 'reason': 'required source is privacy-blocked; never read'})
    for path in sorted(included_paths):
        if not path.endswith('.kt'):
            unresolved.append({'path': path, 'reason': 'Java source requires an independent semantic adapter'})
            continue
        regions, unknown = source_regions(path, projected[path])
        obligations.extend(regions)
        unresolved.extend(unknown)
    payload = {'schema_version': 'behavior-source-census.v1', 'scope': scope,
        'scope_sha256': digest(scope), 'source_revision': revision,
        'snapshot_manifest_sha256': hashlib.sha256((Path(snapshot) / '.android-to-harmony-safe.json').read_bytes()).hexdigest(),
        'files': [{'path': p, 'sha256': manifest['text_file_sha256'][p]} for p in sorted(included_paths)],
        'reached_definitions': [{'path': p, **units[p][i]} for p, i in
            sorted(included, key=lambda item: (item[0], -1 if item[1] is None else item[1])) if i is not None],
        'dependency_edges': [{'from_path': a, 'to_path': b} for a, b in sorted(edges)],
        'external_dependencies': [{'from_path': a, 'import': b} for a, b in sorted(external)],
        'obligations': obligations, 'unresolved': unresolved,
        'limits': ['Balanced Kotlin source coverage is not semantic correctness or runtime parity.',
                   'Dependency injection, external APIs and platform behavior require semantic review and execution.']}
    return {**payload, 'census_sha256': digest(payload)}


def validate_closure(contract, inventory, snapshot, scope):
    """Regenerate the denominator before looking at authored coverage bindings."""
    errors, missing = [], []
    result = {'coverage_complete': False, 'missing': [], 'errors': errors}
    try:
        if snapshot is None or not isinstance(scope, dict):
            raise ValueError('independent --source-scope and approved snapshot are required')
        current = census(snapshot, scope)
        result.update(census_sha256=current['census_sha256'], scope=current['scope'],
                      snapshot_manifest_sha256=current['snapshot_manifest_sha256'],
                      scope_sha256=current['scope_sha256'],
                      obligation_ids=[o['id'] for o in current['obligations']],
                      dependency_edges=current['dependency_edges'],
                      file_count=len(current['files']), total=len(current['obligations']),
                      unresolved=current['unresolved'], external_dependencies=current['external_dependencies'])
        proof = contract.get('source_closure', {})
        if proof.get('schema_version') != 'behavior-source-closure.v1':
            errors.append('independent source denominator is required')
        if proof.get('census_sha256') != current['census_sha256']:
            errors.append('source census is missing or stale')
        if proof.get('inventory_sha256') != digest(inventory):
            errors.append('source inventory is missing or stale relative to reviewed contract')
        if scope['id'] not in contract.get('scope', {}).get('included_scopes', []):
            errors.append('reviewed source scope does not match contract scope')
        if scope['source_revision'] != contract.get('identity', {}).get('source_revision'):
            errors.append('source scope revision does not match contract')
        collection = contract.get('collection', {})
        records = {r['id']: r for key in ('facts', 'entities') for r in collection.get(key, [])}
        anchors = {r['id']: r for r in collection.get('anchors', [])}
        scenarios = {r['id'] for r in contract.get('scenarios', [])}
        bindings = {}
        for binding in proof.get('bindings', []):
            key = binding.get('obligation_id')
            if not isinstance(key, str) or key in bindings:
                errors.append('missing or duplicate source obligation binding')
            else:
                bindings[key] = binding
        for obligation in current['obligations']:
            binding = bindings.pop(obligation['id'], {})
            chosen = binding.get('record_ids', [])
            scenario_ids = binding.get('scenario_ids', [])
            valid = bool(chosen) and all(x in records for x in chosen)
            if obligation['kind'] != 'declaration':
                valid = valid and bool(scenario_ids) and all(x in scenarios for x in scenario_ids)
            for key in chosen:
                record = records.get(key, {})
                sources = [anchors.get(a, {}) for a in record.get('anchor_ids', [])]
                if not any(a.get('kind') == 'source' and a.get('path') == obligation['path']
                           and a.get('start_line', 0) <= obligation['start_line']
                           and a.get('end_line', 0) >= obligation['end_line'] for a in sources):
                    valid = False
                if obligation['kind'] == 'declaration':
                    continue
                if obligation['expression'] not in record.get('source_expressions', []):
                    valid = False
                if obligation['kind'] == 'decision' and record.get('kind') not in {'branch', 'check'}:
                    valid = False
                if record.get('kind') == 'scenario':
                    valid = False
            if not valid:
                missing.append(obligation['id'])
        if bindings:
            errors.append('bindings name unknown source obligations')
        if missing:
            errors.append(f'{len(missing)} independently discovered source obligations are unmapped')
        if current['unresolved']:
            errors.append('source census contains unresolved syntax/dependencies')
        result.update(covered=len(current['obligations']) - len(missing), missing=missing,
                      coverage_complete=not errors)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        errors.append(str(error))
    result['errors'] = ['source closure: ' + e for e in errors]
    return result


def validate_semantic_review(contract, closure, review):
    """Bind an actual independent source review; hashes do not replace that review."""
    errors = []
    if not isinstance(review, dict):
        return ['source semantic review is required; structural coverage alone is not completeness']
    if (review.get('schema_version') != 'behavior-source-review.v1' or review.get('verdict') != 'pass'
            or not isinstance(review.get('reviewer'), str) or not review['reviewer'].strip()
            or review.get('unresolved') != []):
        errors.append('source semantic review is pending/unresolved')
    for key in ('scope_sha256', 'census_sha256'):
        if not closure.get(key) or review.get(key) != closure[key]:
            errors.append('source semantic review ' + key + ' differs')
    if review.get('contract_sha256') != digest(contract):
        errors.append('source semantic review contract is stale')
    for key in ('dependency_edges', 'external_dependencies'):
        if review.get(key) != closure.get(key):
            errors.append('source semantic review has unexamined ' + key)
    required = set(closure.get('obligation_ids', []))
    covered, expectation_ids = set(), set()
    bindings = {b.get('obligation_id'): b for b in contract.get('source_closure', {}).get('bindings', [])}
    record_ids = {r['id'] for section in ('facts', 'entities')
                  for r in contract.get('collection', {}).get(section, [])}
    scenario_ids = {s['id'] for s in contract.get('scenarios', [])}
    expectations = review.get('expectations')
    if not isinstance(expectations, list) or not expectations:
        errors.append('source semantic review needs independent behavior expectations')
        expectations = []
    for item in expectations:
        if not isinstance(item, dict):
            errors.append('invalid source semantic expectation')
            continue
        key, summary = item.get('id'), item.get('summary')
        obligations = item.get('obligation_ids', [])
        records, scenarios = item.get('record_ids', []), item.get('scenario_ids', [])
        if (not isinstance(key, str) or not key or key in expectation_ids
                or not isinstance(summary, str) or not summary.strip()
                or not isinstance(obligations, list) or not obligations
                or not isinstance(records, list) or not records
                or not isinstance(scenarios, list) or not scenarios):
            errors.append('source semantic expectation lacks unique ID, meaning or mapped proof')
            continue
        expectation_ids.add(key)
        linked_records, linked_scenarios = set(), set()
        for obligation in obligations:
            binding = bindings.get(obligation, {})
            linked_records.update(binding.get('record_ids', []))
            linked_scenarios.update(binding.get('scenario_ids', []))
            if (obligation not in required
                    or not set(records).intersection(binding.get('record_ids', []))
                    or not set(scenarios).intersection(binding.get('scenario_ids', []))):
                errors.append('source semantic expectation is not mapped: ' + str(key))
            else:
                covered.add(obligation)
        if (not set(records).issubset(record_ids & linked_records)
                or not set(scenarios).issubset(scenario_ids & linked_scenarios)):
            errors.append('source semantic expectation has unknown/unbound required proof: ' + key)
    if covered != required or not required:
        errors.append('source semantic review does not cover the full current denominator')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['census'])
    parser.add_argument('--snapshot', required=True, type=Path)
    parser.add_argument('--scope', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        result = census(args.snapshot, json.loads(args.scope.read_text()))
        status = 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        result, status = {'verdict': 'fail', 'errors': [str(error)]}, 1
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(rendered)
    print(rendered, end='')
    return status


if __name__ == '__main__':
    raise SystemExit(main())
