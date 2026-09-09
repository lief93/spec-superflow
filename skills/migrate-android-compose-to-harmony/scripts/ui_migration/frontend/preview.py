from __future__ import annotations


def node_paths(payload):
    nodes = {node['id']: node for node in payload['components']}
    paths = {}

    def visit(node_id, visiting=()):
        if node_id in paths:
            return paths[node_id]
        if node_id in visiting:
            raise ValueError('cyclic source hierarchy')
        node = nodes[node_id]
        parent = node.get('parent_id')
        path = dict(visit(parent, (*visiting, node_id))) if parent in nodes else {}
        for branch in node.get('ui_state_path') or []:
            path[branch['group_id']] = branch['branch_id']
        paths[node_id] = path
        return path

    for node_id in nodes:
        visit(node_id)
    return paths


class PreviewPolicy:
    def __init__(self, payload, config):
        self.config = config
        self.records = []
        self.nodes = {node['id']: node for node in payload['components']}
        self.root_id = config['root_id']
        if self.root_id not in self.nodes or self.nodes[self.root_id].get('parent_id') is not None:
            raise ValueError('preview root must be an existing source root')
        if 'choices' in config or 'collection_counts' in config:
            raise ValueError('branch switches are not supported; supply source input values')
        value = config.get('sample_count', 3)
        if type(value) is not int or not 0 <= value <= 20:
            raise ValueError('preview sample count must be an integer between 0 and 20')

    def collection(self, node, value, unresolved):
        parent = self.nodes.get(node.get('parent_id'), {})
        if parent.get('list_item_context') == node.get('list_item_context'):
            return value
        if value is unresolved or not isinstance(value, list):
            count = self.config.get('sample_count', 3)
            self.records.append({'component_id': node['id'], 'path': 'list_item_context',
                                 'origin': 'ui_preview_sample', 'count': count,
                                 'expression': node['list_item_context']['collection']})
            return [{'__preview_index': index} for index in range(1, count + 1)]
        return value

    def content(self, node, suffix):
        if node['type'] not in {'Text', 'BasicText', 'ClickableText', 'TextField', 'BasicTextField', 'OutlinedTextField'}:
            return
        content = node['style']['content']
        display_values = self.config.get('display_values', {})
        imported = display_values.get(node['id'] + suffix) or display_values.get(node['id'])
        missing = content.get('text') is None or '${' in str(content.get('text')) or any(
            item.get('path') == 'style.content.text' for item in node.get('unresolved') or [])
        if not imported and not missing:
            return
        if imported:
            if imported.get('origin') not in {'uiautomator_text', 'ui_preview_sample'} or not isinstance(imported.get('text'), str):
                raise ValueError('display values require a string and explicit sample/runtime origin')
            record = dict(imported)
        else:
            record = {'text': 'Sample text' + (suffix.replace('__item', ' ') if suffix else ''),
                      'origin': 'ui_preview_sample'}
        record.update({'component_id': node['id'] + suffix, 'paths': ['style.content.text'],
                       'replaces': [item for item in node.get('unresolved') or []
                                    if item.get('path') == 'style.content.text']})
        content['text'] = record['text']
        node['unresolved'] = [item for item in node.get('unresolved') or [] if item.get('path') != 'style.content.text']
        node.setdefault('provenance', []).append({
            'paths': ['style.content.text'],
            'origin': 'runtime' if record['origin'] == 'uiautomator_text' else 'ui_preview_sample',
            'source': (f"{record.get('source')}#sha256={record.get('sha256')}#resource={record.get('resource_id')}"
                       if record['origin'] == 'uiautomator_text'
                       else f"ui-preview:{self.config['scene_id']}:{node['id']}{suffix}"),
        })
        self.records.append(record)

    def report(self):
        return {'scene_id': self.config['scene_id'], 'selection': 'source-condition-evaluation', 'display_data': self.records,
                'root_id': self.root_id, 'scope': self.config['scope'],
                'business_verified': False, 'runtime_reachability_verified': False,
                'visual_acceptance': 'not_verified'}
