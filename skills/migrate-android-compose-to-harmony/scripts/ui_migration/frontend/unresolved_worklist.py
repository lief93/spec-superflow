"""Source-scoped diagnostics; no AI dispatch, completion stage or acceptance decision."""
from __future__ import annotations

import hashlib
import json
import re


def category(path: str) -> str:
    if path.startswith('source.theme.'):
        return 'theme'
    if path.startswith('source.state_resolution'):
        return 'state_input'
    if path.startswith('style.asset'):
        return 'resource'
    if path.startswith(('style.content', 'source.arguments.text')):
        return 'display_value'
    return 'ui_fact'


def dependencies(node: dict, expression: str) -> dict:
    """Select lexical references for context only; never evaluate code by matching text."""
    pool = {**(node.get('file_values') or {}), **(node.get('parameter_bindings') or {}),
            **(node.get('local_values') or {})}
    selected = {}
    pending = [expression]
    while pending and len(selected) < 32:
        text = pending.pop()
        for name in re.findall(r'\b[A-Za-z_]\w*\b', text):
            if name in pool and name not in selected and len(selected) < 32:
                selected[name] = str(pool[name])
                pending.append(selected[name])
    return {'bindings': selected, 'context_limit_reached': bool(pending)}


def build_worklist(document: dict, tree, unresolved: list[dict]) -> dict:
    grouped = {}
    for issue in unresolved:
        component_id = issue.get('component_id') or tree.root_id
        node = tree.nodes.get(component_id, {})
        source = node.get('source') or {}
        path = str(issue.get('path') or issue.get('field') or issue.get('kind') or 'unknown')
        expression = str(issue.get('expression') or '')
        context = dependencies(node, expression)
        if issue.get('candidates'):
            context['candidates'] = issue['candidates']
        key = json.dumps([category(path), path, expression, source.get('source'),
                          source.get('composable'), context], sort_keys=True, ensure_ascii=False)
        task_id = hashlib.sha256(key.encode()).hexdigest()[:20]
        task = grouped.setdefault(task_id, {
            'id': task_id, 'category': category(path), 'path': path, 'expression': expression,
            'context': context, 'occurrences': [], 'status': 'unresolved',
        })
        occurrence = {'component_id': component_id, 'component_type': node.get('type'),
                      'source': {k: source[k] for k in ('source', 'line', 'composable', 'call_id') if k in source},
                      'reason': issue.get('reason') or issue.get('message') or issue.get('status')}
        if occurrence not in task['occurrences']:
            task['occurrences'].append(occurrence)
    tasks = list(grouped.values())
    raw_document = json.dumps(document, ensure_ascii=False, indent=2) + '\n'
    return {
        'schema': 'android-to-harmony.unresolved-worklist.v1',
        'page': document['meta']['migration']['page'],
        'version_json_sha256': hashlib.sha256(raw_document.encode()).hexdigest(),
        'has_unresolved': bool(tasks), 'unresolved_count': len(unresolved), 'task_count': len(tasks),
        'purpose': 'Diagnostic report only; no AI completion or review stage.',
        'resolution_policy': 'Continue known output with unresolved facts reported. Use supported parsers, '
                             'explicit state inputs or verified runtime facts; shared-rule repairs are separate '
                             'maintenance work. Do not invent values, erase diagnostics or approve the page.',
        'tasks': tasks,
    }
