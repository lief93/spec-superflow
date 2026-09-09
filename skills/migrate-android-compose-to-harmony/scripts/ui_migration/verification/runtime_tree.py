import json
import re
import xml.etree.ElementTree as ET


def bounds(value):
    numbers = value if isinstance(value, list) else list(map(int, re.findall(r'-?\d+', value or '')))
    if len(numbers) != 4 or numbers[2] <= numbers[0] or numbers[3] <= numbers[1]:
        return None
    return numbers


def read_tree(path):
    if path.suffix == '.xml':
        def convert(node):
            attrs = dict(node.attrib)
            attrs['id'] = attrs.get('resource-id', '')
            attrs['description'] = attrs.get('content-desc', '')
            attrs['type'] = attrs.get('class', '')
            return {'attributes': attrs, 'children': [convert(c) for c in node]}
        root = convert(ET.parse(path).getroot())
    else:
        root = json.loads(path.read_text())
    result = []
    def walk(node, ancestors):
        node['ancestors'] = ancestors
        result.append(node)
        for child in node.get('children', []):
            walk(child, ancestors + [node])
    walk(root, [])
    return result


def matches(node, query):
    for key, expected in query.items():
        if key == 'not':
            if matches(node, expected):
                return False
        elif key in {'contains_text', 'without_text'}:
            descendants = [node]
            found = False
            while descendants:
                child = descendants.pop()
                found |= child.get('attributes', {}).get('text') == expected
                descendants.extend(child.get('children', []))
            if (not found and key == 'contains_text') or (found and key == 'without_text'):
                return False
        elif node.get('attributes', {}).get(key) != expected:
            return False
    return True


def select(nodes, selector):
    query = selector.get('match', {k: v for k, v in selector.items() if k != 'parent'})
    result = []
    for node in nodes:
        if not matches(node, query):
            continue
        target = node
        if 'parent' in selector:
            target = next((p for p in reversed(node['ancestors']) if matches(p, selector['parent'])), None)
        if target is not None and bounds(target.get('attributes', {}).get('bounds')):
            if not any(target is item for item in result):
                result.append(target)
    return result
