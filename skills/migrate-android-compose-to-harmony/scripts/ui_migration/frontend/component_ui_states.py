"""Preserve business-definition UI alternatives independently of page state selection."""
import copy

from .fixed_state import project_source_page


def descendants(nodes, root):
    result = []
    pending = [root]
    while pending:
        node = nodes[pending.pop()]
        result.append(node)
        pending.extend(reversed(node.get('children_ids', [])))
    return result


def when_entry_counts(value):
    if isinstance(value, dict):
        result = [len(value['entries'])] if value.get('kind') == 'when' else []
        return result + [count for child in value.values() for count in when_entry_counts(child)]
    if isinstance(value, list):
        return [count for child in value for count in when_entry_counts(child)]
    return []


def preserve_component_states(raw, projected, fixture, registry):
    nodes = {n['id']:n for n in raw['components']}
    definitions = {d['id']:d for d in raw.get('component_definitions', [])}
    active = {n['id']:n for n in projected['components']}
    catalogs, diagnostics = [], []
    replacements = {}
    for instance in raw['components']:
        definition = definitions.get(instance.get('definition_id'), {})
        if definition.get('component_kind') != 'project_component' or instance['id'] not in active:
            continue
        subtree = descendants(nodes, instance['id'])
        # Branch ownership is the callee definition, never the page's enclosing branch.
        owned = [n for n in subtree[1:] if n.get('source', {}).get('composable') == definition['type']
                 and n.get('source', {}).get('source') == definition['identity'].get('source')]
        groups = {}
        for node in owned:
            for path in node.get('ui_state_path', []):
                if path['group_id'] not in {p['group_id'] for p in instance.get('ui_state_path', [])}:
                    group = groups.setdefault(path['group_id'], {'branches':path['branches'], 'conditions':{}})
                    group['conditions'][path['branch_id']] = path.get('condition')
        if not groups:
            continue
        if len(groups) != 1:
            diagnostics.append({'component_id':instance['id'], 'path':'source.component_ui_states',
                'expression':definition['type'], 'reason':'multiple UI branch groups require explicit local-state composition; all-state coverage is incomplete'})
            continue
        group_id, group = next(iter(groups.items()))
        function = next((f for f in raw.get('source_functions', []) if f.get('name') == definition['type']
                         and f.get('source') == definition['identity'].get('source')), {})
        counts = when_entry_counts(function.get('body'))
        if len(counts) == 1 and ':when:' in group_id and counts[0] != len(group['branches']):
            diagnostics.append({'component_id':instance['id'], 'path':'source.component_ui_states',
                'expression':definition['type'], 'reason':'PSI when branches disagree with collected UI paths; all-state coverage is incomplete'})
            continue
        if len(group['branches']) > 16:
            diagnostics.append({'component_id':instance['id'], 'path':'source.component_ui_states',
                'expression':definition['type'], 'reason':'component UI branch count exceeds 16; not truncated silently'})
            continue
        selected = next((p['branch_id'] for n in owned if n['id'] in active
            and active[n['id']].get('source', {}).get('state_resolution', {}).get('status') != 'unresolved'
            for p in n.get('ui_state_path', []) if p['group_id'] == group_id), None)
        selection_origin = 'selected-page-state' if selected else 'ui-placeholder-default'
        selected = selected or ('else' if 'else' in group['branches'] else group['branches'][0])
        catalog = {'schema':'ui-migration.component-ui-states.v1', 'definition_id':definition['id'],
            'instance_id':instance['id'], 'name':definition['type'], 'parameters':definition.get('parameters', []),
            'selector':'uiState', 'selected':selected, 'selection_origin':selection_origin,
            'business_verified':False, 'variants':[]}
        for branch in group['branches']:
            payload = copy.deepcopy(raw)
            subtree_ids = {n['id'] for n in subtree}
            for node in payload['components']:
                if node['id'] not in subtree_ids or node['id'] == instance['id']:
                    continue
                path = next((p for p in node.get('ui_state_path', []) if p['group_id'] == group_id), None)
                if path is not None:
                    node['source']['ui_branch_origin'] = copy.deepcopy(node.get('visibility_condition'))
                    node['visibility_condition'] = {'expression':'true' if path['branch_id'] == branch else 'false'}
            scene = copy.deepcopy(fixture)
            scene['page'] = payload['page']
            root = instance
            while root.get('parent_id') in nodes:
                root = nodes[root['parent_id']]
            scene['ui_preview'] = {'scene_id':definition['type'] + '/' + branch,
                'scope':'business-component-ui', 'root_id':root['id'], 'sample_count':3,
                'display_values':fixture.get('ui_preview', {}).get('display_values', {})}
            value, projection = project_source_page(payload, scene, allow_unresolved=True, api_registry=registry)
            # Resolve within the caller's theme/layout context before isolating the component.
            value['components'] = descendants({n['id']:n for n in value['components']}, instance['id'])
            value['components'][0].update(parent_id=None, sibling_index=0)
            catalog['variants'].append({'id':branch, 'condition':group['conditions'].get(branch),
                                        'payload':value, 'projection':projection})
            if branch == selected:
                replacement = copy.deepcopy(value['components'])
                replacement[0].update(parent_id=instance.get('parent_id'), sibling_index=instance.get('sibling_index', 0))
                replacements[instance['id']] = ({n['id'] for n in subtree}, replacement)
        catalogs.append(catalog)
    result = copy.deepcopy(projected)
    for _, (removed, replacement) in replacements.items():
        current = result['components']
        index = next((i for i,n in enumerate(current) if n['id'] == replacement[0]['id']), None)
        if index is not None:
            result['components'] = [n for n in current[:index] if n['id'] not in removed] + replacement + [n for n in current[index:] if n['id'] not in removed]
    result.setdefault('source_diagnostics', []).extend(diagnostics)
    return result, catalogs
