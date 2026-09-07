#!/usr/bin/env python3
"""Internal collection catalog/scaffold CLI and shared source proof validation."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from validate_ai_safe_tree import validate as validate_safe_tree
from analyze_compose_project import lexical_code_mask
from scan_android_behavior_symbols import class_body

CATALOG = Path(__file__).resolve().parent.parent / 'assets/behavior-collection-rules.json'
SCHEMA = 'behavior-collection.v1'
FIELDS = {
    'action': ('trigger', 'handler', 'outcomes', 'source_expressions'),
    'state': ('initial', 'lifetime', 'writes', 'source_expressions'),
    'navigation': ('destination', 'back_stack', 'source_expressions'),
    'branch': ('selector', 'cases', 'source_expressions'),
    'data': ('operation', 'dependency_id', 'inputs', 'outputs', 'availability', 'source_expressions'),
    'async': ('entry', 'normal', 'failure', 'cancellation', 'scope', 'source_expressions'),
    'lifecycle': ('hook', 'effect', 'source_expressions'),
    'check': ('condition', 'on_valid', 'on_invalid', 'availability', 'source_expressions'),
    'scenario': ('action_ids', 'given', 'when', 'then', 'evidence_kind'),
}


def catalog():
    return json.loads(CATALOG.read_text(encoding='utf-8'))


def scaffold(inventory):
    return {'schema_version': SCHEMA, 'status': 'pending',
            'source_revision': inventory['source_revision'],
            'inventory_ids': sorted(item['id'] for item in inventory['items']),
            'categories': [{'family': f['id'], 'disposition': 'unresolved',
                            'rationale': '', 'anchor_ids': [], 'record_ids': []}
                           for f in catalog()['families']],
            'entities': [], 'relationships': [], 'facts': [], 'anchors': []}


def selected(collection):
    families = catalog()['families']
    index = collection.get('categories', [])
    if (len(index) != len(families) or {x.get('family') for x in index} != {f['id'] for f in families}
            or any(x.get('disposition') not in {'applicable', 'not_applicable', 'unresolved'} for x in index)):
        raise ValueError('complete six-family applicability index required')
    names = {x['family'] for x in index if x.get('disposition') == 'applicable'}
    return {'applicability_index': index, 'rules': [f for f in families if f['id'] in names]}


def local_handler_bodies(text, outcome):
    """Recognize only explicit local Kotlin handlers; unknown forms stay unresolved."""
    code = lexical_code_mask(text)
    pattern = (r'\b(?:catch\s*\([^{}]*\)|finally)\s*\{' if outcome == 'failure' else
               r'\b(?:finally|invokeOnCancellation|catch\s*\([^{}]*\bCancellationException\b[^{}]*\))\s*\{')
    for match in re.finditer(pattern, code):
        opening = match.end() - 1
        depth = 1
        for end in range(opening + 1, len(code)):
            depth += (code[end] == '{') - (code[end] == '}')
            if depth == 0:
                yield text[opening + 1:end], code[opening + 1:end]
                break


def is_bound_branch_case(case, source):
    if not isinstance(case, dict) or not all(isinstance(case.get(f), str) and case[f].strip()
                                             for f in ('condition', 'outcome', 'source_clause')):
        return False
    clause = case['source_clause']
    code = lexical_code_mask(clause)
    if clause not in source or code.count('->') != 1:
        return False
    arrow = code.index('->')
    return clause[:arrow].strip() == case['condition'].strip() and case['outcome'] in clause[arrow + 2:]


def validate_collection(contract, inventory, snapshot):
    errors = []
    def error(message):
        errors.append('collection: ' + message)
    collection = contract.get('collection')
    if not isinstance(collection, dict):
        return {'verdict': 'fail', 'errors': ['collection proof is required']}
    if collection.get('schema_version') != SCHEMA or collection.get('status') != 'reviewed':
        error('requires reviewed behavior-collection.v1; scaffold remains pending')
    if collection.get('source_revision') != inventory.get('source_revision'):
        error('source revision differs')
    def records(key):
        value = collection.get(key)
        if not isinstance(value, list) or any(not isinstance(x, dict) for x in value):
            error(f'{key} must be an object array')
            return []
        return value
    def index(items, name):
        result = {}
        for item in items:
            key = item.get('id')
            if not isinstance(key, str) or not key or key in result:
                error(f'{name} missing or duplicate id')
            else:
                result[key] = item
        return result
    anchors = index(records('anchors'), 'anchor')
    entities = index(records('entities'), 'entity')
    facts = index(records('facts'), 'fact')
    relations = index(records('relationships'), 'relationship')
    all_records = {**entities, **facts, **relations}
    if len(all_records) != len(entities) + len(facts) + len(relations):
        error('record ids must be globally unique')
    if not entities:
        error('page/component ownership is missing')
    texts = {}
    if snapshot is None:
        error('approved snapshot is required')
    else:
        snapshot = Path(snapshot)
        # Independent whole-tree check precedes every source read below.
        safe = ({'ok': False, 'violations': ['snapshot root is a symbolic link']}
                if snapshot.is_symlink() else validate_safe_tree(snapshot, require_safe_manifest=True))
        if not safe.get('ok'):
            error('unsafe snapshot: ' + json.dumps(safe.get('violations', [])))
        else:
            manifest = json.loads((snapshot / '.android-to-harmony-safe.json').read_text())
            approved = set(manifest['text_files'])
            revision = manifest.get('source_git', {}).get('revision')
            if revision is not None and revision != inventory.get('source_revision'):
                error('snapshot revision differs')
            for key, anchor in anchors.items():
                path = anchor.get('path')
                if not isinstance(path, str) or path not in approved:
                    error(f'anchor {key} path is missing/excluded/unapproved')
                    continue
                raw = (snapshot / path).read_bytes()
                lines = raw.decode('utf-8').splitlines(keepends=True)
                start, end = anchor.get('start_line'), anchor.get('end_line')
                if (type(start) is not int or type(end) is not int
                        or not 1 <= start <= end <= len(lines)):
                    error(f'anchor {key} has invalid source span')
                    continue
                span = ''.join(lines[start-1:end])
                if (hashlib.sha256(raw).hexdigest() != anchor.get('file_sha256')
                        or hashlib.sha256(span.encode()).hexdigest() != anchor.get('span_sha256')):
                    error(f'anchor {key} source hash is stale')
                    continue
                if anchor.get('kind') not in {'source', 'test'}:
                    error(f'anchor {key} evidence kind is invalid')
                if anchor.get('kind') == 'test':
                    symbol = anchor.get('symbol', '').split('.')
                    try:
                        body = class_body(lexical_code_mask(span), symbol[0])
                    except ValueError:
                        body = ''
                    if (len(symbol) != 2
                            or not re.search(r'@Test(?:\([^)]*\))?\s+(?:public\s+)?fun\s+' + re.escape(symbol[-1]) + r'\s*\(', body)
                            or not any(p in Path(path).parts for p in ('test', 'androidTest'))):
                        error(f'anchor {key} test symbol does not resolve')
                texts[key] = span
    def refs(value, allowed, label, required=True):
        if (not isinstance(value, list) or (required and not value)
                or any(not isinstance(x, str) or x not in allowed for x in value)):
            error(label + ' has missing/unknown references')
            return []
        return value
    inventory_ids = {x['id'] for x in inventory.get('items', []) if isinstance(x, dict) and 'id' in x}
    for key, record in all_records.items():
        refs(record.get('anchor_ids'), anchors, f'{key} anchors')
        refs(record.get('source_inventory_ids'), inventory_ids, f'{key} inventory')
    definitions = set()
    for key, entity in entities.items():
        kind = entity.get('kind')
        if kind not in {'page', 'definition', 'instance', 'dependency'}:
            error(f'{key} invalid entity kind')
        if kind == 'page':
            if 'owner_id' not in entity or entity.get('owner_id') is not None:
                error(f'{key} page cannot have an owner')
        elif entity.get('owner_id') not in entities:
            error(f'{key} missing owner')
        if kind == 'instance' and entities.get(entity.get('definition_id'), {}).get('kind') != 'definition':
            error(f'{key} missing reusable definition')
        if kind in {'definition', 'dependency'}:
            symbol = entity.get('symbol')
            paths = {anchors.get(a, {}).get('path', '') for a in entity.get('anchor_ids', [])}
            primary = entity.get('definition_anchor_id')
            if primary is not None:
                if primary not in entity.get('anchor_ids', []) or primary not in anchors:
                    error(f'{key} definition anchor must be one of its source anchors')
                path = anchors.get(primary, {}).get('path')
            elif len(paths) == 1:
                path = next(iter(paths))
            else:
                error(f'{key} multiple source paths require an explicit definition_anchor_id')
                path = None
            identity = (path, symbol)
            if not isinstance(symbol, str) or not symbol.strip():
                error(f'{key} shared definition requires source symbol')
            elif identity in definitions:
                error(f'{key} duplicate shared definition')
            definitions.add(identity)
        seen = {key}
        parent = entity.get('owner_id')
        while parent in entities:
            if parent in seen:
                error(f'{key} ownership cycle')
                break
            seen.add(parent)
            parent = entities[parent].get('owner_id')
    for key, relation in relations.items():
        if relation.get('from_id') not in entities or relation.get('to_id') not in entities:
            error(f'{key} broken relationship endpoint')
        bindings = relation.get('bindings')
        if not isinstance(bindings, list) or not bindings:
            error(f'{key} missing input/event bindings')
        else:
            for binding in bindings:
                if not isinstance(binding, dict) or binding.get('kind') not in {'input', 'event', 'dependency'}:
                    error(f'{key} invalid binding kind')
                elif not all(isinstance(binding.get(f), str) and binding[f].strip() for f in ('from', 'to', 'expression')):
                    error(f'{key} incomplete binding')
                elif binding['expression'] not in '\n'.join(texts.get(a, '') for a in relation.get('anchor_ids', [])):
                    error(f'{key} binding expression absent from source')
    mapped = set()
    contract_ids = {x['id'] for section in ('actions', 'states', 'navigation', 'scenarios')
                    for x in contract.get(section, []) if isinstance(x, dict) and 'id' in x}
    for key, fact in facts.items():
        kind = fact.get('kind')
        if kind not in FIELDS:
            error(f'{key} invalid fact kind')
            continue
        if fact.get('owner_id') not in entities:
            error(f'{key} missing owner')
        for field in FIELDS[kind]:
            value = fact.get(field)
            expected_type = (dict if kind == 'async' and field in {'failure', 'cancellation'} else
                             list if field in {'outcomes', 'writes', 'source_expressions', 'inputs', 'outputs', 'cases', 'action_ids', 'then'} else str)
            if not value or not isinstance(value, expected_type):
                error(f'{key} requires structured {field}')
            elif isinstance(value, list) and field != 'cases' and any(not isinstance(v, str) or not v.strip() for v in value):
                error(f'{key} {field} requires nonempty string entries')
        if kind == 'state':
            refs(fact.get('writes'), {k for k, v in facts.items() if v.get('kind') == 'action'}, f'{key} writes')
        if kind == 'scenario':
            refs(fact.get('action_ids'), {k for k, v in facts.items() if v.get('kind') == 'action'}, f'{key} actions')
            if fact.get('evidence_kind') not in {'source', 'test'}:
                error(f'{key} invalid evidence kind')
            elif not any(anchors.get(a, {}).get('kind') == fact['evidence_kind'] for a in fact.get('anchor_ids', [])):
                error(f'{key} evidence kind has no matching anchor')
        if kind == 'data' and fact.get('dependency_id') not in entities:
            error(f'{key} missing shared dependency')
        if fact.get('availability', 'available') != 'available':
            error(f'{key} source-unavailable/unsupported detail remains unresolved')
        expressions = fact.get('source_expressions', [])
        span = '\n'.join(texts.get(a, '') for a in fact.get('anchor_ids', []))
        if not isinstance(expressions, list) or any(not isinstance(e, str) or not e.strip() or e not in span for e in expressions):
            error(f'{key} expression absent from source')
        if kind == 'async':
            span = texts.get(fact.get('scope_anchor_id'), '')
            if fact.get('scope_anchor_id') not in fact.get('anchor_ids', []):
                error(f'{key} async requires exact function scope anchor')
            entry, normal = fact.get('entry'), fact.get('normal')
            if (not isinstance(entry, str) or not isinstance(normal, str)
                    or entry not in span or normal not in span or span.find(entry) >= span.find(normal)):
                error(f'{key} async entry/normal order is not source-bound')
            for outcome, pattern in (('failure', r'\bcatch\b|\bfinally\b'),
                                     ('cancellation', r'\bfinally\b|invokeOnCancellation|ensureActive')):
                record = fact.get(outcome)
                if not isinstance(record, dict):
                    error(f'{key} async {outcome} requires explicit disposition')
                    continue
                scope_text = texts.get(record.get('scope_anchor_id'), '')
                if not scope_text or record.get('scope_anchor_id') not in fact.get('anchor_ids', []):
                    error(f'{key} async {outcome} has no bound scope')
                if record.get('disposition') == 'observed':
                    expression = record.get('expression')
                    code = lexical_code_mask(expression) if isinstance(expression, str) else ''
                    if (not code.strip() or not scope_text or scope_text not in span
                            or not any(body_code[m.start():m.end()] == code
                                       for body, body_code in local_handler_bodies(scope_text, outcome)
                                       for m in re.finditer(re.escape(expression), body))):
                        error(f'{key} async {outcome} expression is not inside a supported local handler')
                elif record.get('disposition') == 'absent_local':
                    if not record.get('rationale') or re.search(pattern, scope_text):
                        error(f'{key} async {outcome} local absence conflicts with source')
                else:
                    error(f'{key} async {outcome} remains unresolved')
        if kind == 'branch':
            cases = fact.get('cases')
            if not isinstance(cases, list) or any(not is_bound_branch_case(c, span) for c in cases):
                error(f'{key} invalid source branch outcomes')
        section = {'action': 'actions', 'state': 'states', 'navigation': 'navigation', 'scenario': 'scenarios'}.get(kind)
        allowed_contracts = {x['id'] for x in contract.get(section, []) if isinstance(x, dict) and 'id' in x} if section else set()
        mapped.update(refs(fact.get('contract_ids', []), allowed_contracts, f'{key} contract', required=bool(section)))
    if contract_ids - mapped:
        error('unowned contract facts: ' + ', '.join(sorted(contract_ids - mapped)))
    # Inventory is independent of collection. Context and scenario references do
    # not replace the behavior record whose kind the inventory requires.
    fact_kinds_by_inventory = {}
    for fact in facts.values():
        for inventory_id in refs(fact.get('source_inventory_ids'), inventory_ids,
                                 f"{fact['id']} inventory"):
            fact_kinds_by_inventory.setdefault(inventory_id, set()).add(fact.get('kind'))
    missing_fact_ids = set()
    for item in inventory.get('items', []):
        refs(item.get('source_evidence'), anchors, 'inventory source evidence')
        expected_kind = item.get('record_kind', item.get('category'))
        if not isinstance(expected_kind, str) or expected_kind not in FIELDS:
            error(f"inventory {item['id']} requires an explicit supported record_kind")
            missing_fact_ids.add(item['id'])
        elif expected_kind not in fact_kinds_by_inventory.get(item['id'], set()):
            error(f"inventory {item['id']} lacks its structured {expected_kind} fact")
            missing_fact_ids.add(item['id'])
    for scenario in contract.get('scenarios', []):
        refs(scenario.get('android_evidence'), anchors, 'scenario source/test evidence')
    categories = records('categories')
    expected = {f['id']: f for f in catalog()['families']}
    names = [c.get('family') for c in categories]
    if set(names) != set(expected) or len(names) != len(expected):
        error('all six categories must be accounted exactly once')
    covered = set()
    for category in categories:
        family = category.get('family')
        disposition = category.get('disposition')
        if not isinstance(category.get('rationale'), str) or not category['rationale'].strip():
            error(f'{family} missing applicability rationale')
        refs(category.get('anchor_ids'), anchors, f'{family} applicability anchors')
        allowed = {k for k, v in all_records.items() if
                   ('entity' if k in entities else 'relationship' if k in relations else v.get('kind'))
                   in expected.get(family, {}).get('record_kinds', [])}
        if disposition == 'applicable':
            covered.update(refs(category.get('record_ids'), allowed, f'{family} records'))
        elif disposition == 'not_applicable':
            if category.get('record_ids') or allowed:
                error(f'{family} not-applicable conflicts with collected records')
        else:
            error(f'{family} unresolved applicability')
    if set(all_records) - covered:
        error('records missing category coverage: ' + ', '.join(sorted(set(all_records) - covered)))
    return {'verdict': 'fail' if errors else 'pass', 'errors': errors,
            'category_count': len(categories), 'anchor_count': len(anchors),
            'source_fact_coverage': {'covered': len(inventory_ids - missing_fact_ids),
                                     'total': len(inventory_ids),
                                     'missing': sorted(missing_fact_ids)},
            'limits': ['Checks structure and source provenance; semantic completeness requires source review.',
                       'No Android/Harmony runtime parity is established by collection validation.']}


def main():
    parser = argparse.ArgumentParser(description='Maintainer collection rules; normal gates use validate_behavior_contract_v2.')
    parser.add_argument('command', choices=['catalog', 'scaffold', 'selected'])
    parser.add_argument('--inventory', type=Path)
    parser.add_argument('--collection', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'catalog':
            result = catalog()
        elif args.command == 'scaffold':
            result = scaffold(json.loads(args.inventory.read_text()))
        else:
            result = selected(json.loads(args.collection.read_text()))
        rendered = json.dumps(result, indent=2, ensure_ascii=False) + '\n'
        if args.output:
            with args.output.open('x', encoding='utf-8') as stream:
                stream.write(rendered)
        print(rendered, end='')
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(json.dumps({'verdict': 'fail', 'error': str(error)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
