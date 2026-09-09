#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
from ui_migration.frontend.preview import PreviewPolicy
from ui_migration.frontend.preview import node_paths
import argparse
import copy
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from ui_migration.contracts.source_storage import pack_source_page, unpack_source_page


def build_catalog(payload, state_inputs=None):
    payload = unpack_source_page(payload)
    paths = node_paths(payload)
    nodes = {node['id']: node for node in payload['components']}
    owners = {}
    for node_id in nodes:
        root = nodes[node_id]
        while root.get('parent_id') in nodes:
            root = nodes[root['parent_id']]
        owners[node_id] = root['id']
    groups = {}
    collections = []
    unclassified = []
    for node in payload['components']:
        if node.get('visibility_condition') and not node.get('ui_state_path'):
            unclassified.append(node['id'])
        for branch in node.get('ui_state_path') or []:
            group = groups.setdefault(branch['group_id'], {
                'id': branch['group_id'], 'branches': branch['branches'],
                'source': node.get('source'), 'targets': {},
                'roots': [], 'conditions': {},
            })
            if owners[node['id']] not in group['roots']:
                group['roots'].append(owners[node['id']])
            group['targets'].setdefault(branch['branch_id'], paths[node['id']])
            group['conditions'][branch['branch_id']] = branch['condition']
        if node.get('list_item_context'):
            parent = next((n for n in payload['components'] if n['id'] == node.get('parent_id')), {})
            if parent.get('list_item_context') != node['list_item_context']:
                collections.append({'id': node['id'], 'context': node['list_item_context'],
                                    'requires': paths[node['id']]})
    roots = list(dict.fromkeys(owners.values()))
    scenes = []
    seen = set()
    if state_inputs is not None:
        if state_inputs.get('schema') != 'android-to-harmony.ui-state-inputs.v1':
            raise ValueError('unsupported UI state input schema')
        if state_inputs.get('page_id') != payload['page']['id']:
            raise ValueError('state input page_id must match source page')
        if not isinstance(state_inputs.get('scenes'), list) or not state_inputs['scenes']:
            raise ValueError('state inputs must name at least one scene')
        for scene in state_inputs['scenes']:
            scene_id = scene.get('id')
            if not isinstance(scene_id, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}', scene_id) or scene_id in seen:
                raise ValueError('scene IDs must be unique safe names')
            seen.add(scene_id)
            if 'choices' in scene or 'collection_counts' in scene:
                raise ValueError('branch switches are not supported; supply source input values')
            root_id = scene.get('root_id', roots[0] if len(roots) == 1 else None)
            if root_id not in roots:
                raise ValueError('multiple source roots require an explicit existing root_id')
            for field in ('values', 'symbols', 'source_bindings'):
                if not isinstance(scene.get(field, {}), dict) or not isinstance(state_inputs.get('common_' + field, {}), dict):
                    raise ValueError(f'scene {field} must be an object')
            scenes.append({'id': scene_id, 'label': str(scene.get('label') or scene_id),
                           'values': {**state_inputs.get('common_values', {}), **scene.get('values', {})},
                           'symbols': {**state_inputs.get('common_symbols', {}), **scene.get('symbols', {})},
                           'source_bindings': {**state_inputs.get('common_source_bindings', {}), **scene.get('source_bindings', {})},
                           'root_id': root_id, 'root_type': nodes[root_id]['type'],
                           'scope': 'isolated-source-root' if len(roots) > 1 else 'page',
                           'other_source_roots': [item for item in roots if item != root_id]})
    return {'schema': 'android-to-harmony.ui-state-catalog.v1', 'page': payload['page'],
            'groups': list(groups.values()), 'collections': collections, 'scenes': scenes,
            'unclassified_condition_nodes': unclassified,
            'coverage_scope': 'explicit input scenes evaluated by source conditions; not exhaustive business states'}


def preview_fixture(payload, scene, display_values=None):
    return {'schema': 'android-to-harmony.page-state-fixture.v1', 'page': payload['page'],
            'values': scene['values'], 'symbols': scene['symbols'],
            'source_bindings': scene.get('source_bindings', {}),
            'ui_preview': {'scene_id': scene['id'],
                           'root_id': scene['root_id'], 'scope': scene['scope'],
                           'sample_count': 3,
                           'display_values': display_values or {}}}


def import_runtime_text(payload, xml_path, binding):
    if binding.get('page') != payload['page']:
        raise ValueError('UIAutomator binding page/state must match source page')
    raw = xml_path.read_bytes()
    nodes = list(ET.fromstring(raw).iter('node'))
    source_ids = {node['id'] for node in payload['components']}
    values = {}
    for source_id, resource_id in binding.get('text_bindings', {}).items():
        base_id = source_id.split('__item', 1)[0]
        if base_id not in source_ids:
            raise ValueError(f'unknown source component: {source_id}')
        if isinstance(resource_id, dict):
            index = resource_id.get('node_index')
            if set(resource_id) != {'node_index'} or type(index) is not int or not 0 <= index < len(nodes):
                raise ValueError('runtime text node_index must be an in-range integer')
            matches = [nodes[index]]
        else:
            matches = [node for node in nodes if node.get('resource-id') == resource_id]
        if len(matches) != 1:
            raise ValueError(f'UIAutomator resource must match exactly once: {resource_id}')
        if matches[0].get('password') == 'true':
            raise ValueError('password fields cannot supply preview text')
        values[source_id] = {'text': matches[0].get('text', ''), 'origin': 'uiautomator_text',
                             'resource_id': resource_id, 'source': str(xml_path.resolve()),
                             'sha256': hashlib.sha256(raw).hexdigest()}
    return values


def generate_previews(args):
    from generate_lanhu_source_page import generate
    payload = unpack_source_page(json.loads(args.source_page.read_text()))
    catalog = build_catalog(payload, json.loads(args.states.read_text()))
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / 'state-catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n')
    values = {}
    if args.uiautomator_xml:
        values = import_runtime_text(payload, args.uiautomator_xml, json.loads(args.text_bindings.read_text()))
    results = []
    for scene in catalog['scenes']:
        directory = root / scene['id']
        directory.mkdir()
        page = copy.deepcopy(payload)
        page['page']['state'] = scene['id']
        source = directory / 'source-page.json'
        fixture = directory / 'state-fixture.json'
        source.write_text(json.dumps(pack_source_page(page), ensure_ascii=False, indent=2) + '\n')
        fixture.write_text(json.dumps(preview_fixture(page, scene, values), ensure_ascii=False, indent=2) + '\n')
        try:
            result = generate(argparse.Namespace(
                source_page=source, state_fixture=fixture, output_dir=directory,
                viewport_width_dp=args.viewport_width_dp, viewport_height_dp=args.viewport_height_dp,
                slice_scale=args.slice_scale, device='ui-preview', api_adapters=getattr(args, 'api_adapters', None)))
        except ValueError as error:
            result = {'status': 'failed', 'error': str(error), 'verdict': 'fail'}
        results.append({'scene_id': scene['id'], 'label': scene['label'],
                        'root_type': scene['root_type'], 'scope': scene['scope'], **result})
    report = {'schema': 'android-to-harmony.ui-preview-report.v1', 'source_sha256': hashlib.sha256(args.source_page.read_bytes()).hexdigest(),
              'state_inputs_sha256': hashlib.sha256(args.states.read_bytes()).hexdigest(),
              'scenes': results, 'business_verified': False, 'visual_acceptance': 'not_verified',
              'generated_count': sum(item['status'] != 'failed' for item in results),
              'scene_count': len(results), 'coverage_scope': catalog['coverage_scope']}
    (root / 'preview-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    lines = ['# UI State Previews', '',
             f"Generated: {report['generated_count']}/{report['scene_count']} scene JSONs.",
             'Business reachability and visual acceptance: not verified.',
             'Sample content is marked in each JSON. Isolated roots are not full-window screenshots.', '',
             '| Scene | Source root | Selection | JSON | Unresolved |',
             '| --- | --- | --- | --- | --- |']
    for result in results:
        version = root / result['scene_id'] / 'version_json.json'
        outcome = f'[Open]({version})' if result['status'] != 'failed' else result['error']
        label = result['label'].replace('|', '\\|')
        lines.append(f"| {result['scene_id']} | {result['root_type']} ({result['scope']}) | {label} | {outcome} | {result.get('unresolved_count', 'failed')} |")
    (root / 'preview-report.md').write_text('\n'.join(lines) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-page', type=Path, required=True)
    parser.add_argument('--states', type=Path, required=True, help='Explicit UI state input samples, not branch switches')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--viewport-width-dp', type=float, required=True)
    parser.add_argument('--viewport-height-dp', type=float, required=True)
    parser.add_argument('--slice-scale', type=float, default=2)
    parser.add_argument('--uiautomator-xml', type=Path)
    parser.add_argument('--text-bindings', type=Path)
    parser.add_argument('--api-adapters', type=Path, help='Explicit trusted hash-pinned project adapter manifest')
    args = parser.parse_args()
    if bool(args.uiautomator_xml) != bool(args.text_bindings):
        parser.error('--uiautomator-xml and --text-bindings are required together')
    try:
        report = generate_previews(args)
    except (ValueError, OSError, ET.ParseError) as error:
        print(json.dumps({'status': 'failed', 'error': str(error)}))
        return 2
    print(json.dumps({key: value for key, value in report.items() if key != 'scenes'}))
    return 0 if report['generated_count'] == report['scene_count'] else 2


if __name__ == "__main__":
    raise SystemExit(main())
