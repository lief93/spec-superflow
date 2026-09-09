import copy
import json
import tempfile
import unittest
import os
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import test_dp_size
from generate_lanhu_source_page import generate, project_source_page
from generate_arkui_page import load_lanhu_page_input
from test_layout_mapping_contract import render_nodes
from generate_ui_state_previews import build_catalog, preview_fixture, import_runtime_text


class UiStatePreviewTest(unittest.TestCase):
    def source(self, body, declarations=''):
        return test_dp_size.DpSizeTest().source_page(body, declarations)

    def catalog(self, page, scenes=None):
        return build_catalog(page, {'schema': 'android-to-harmony.ui-state-inputs.v1',
            'page_id': page['page']['id'], 'scenes': scenes or [{'id': 'default', 'values': {}}]})

    def render(self, projected):
        nodes = copy.deepcopy(projected['components'])
        for node in nodes:
            node.pop('visibility_condition', None)
            node.pop('list_item_context', None)
        return render_nodes(nodes)

    def project(self, page, scene):
        fixture = preview_fixture(page, scene)
        return project_source_page(page, fixture)[0]

    def test_unknown_business_branches_generate_separate_scenes_and_keep_strict_mode(self):
        page = self.source('''Column {
if (state.loading) { Text("Loading") } else { Text(state.title) }
}''')
        strict = {'schema': 'android-to-harmony.page-state-fixture.v1', 'page': page['page']}
        with self.assertRaisesRegex(ValueError, 'resolved boolean'):
            project_source_page(page, strict)
        catalog = self.catalog(page, [
            {'id': 'loading', 'values': {'state': {'loading': True}}},
            {'id': 'content', 'values': {'state': {'loading': False}}}])
        self.assertEqual(len(catalog['groups']), 1)
        self.assertEqual(len(catalog['scenes']), 2)
        texts = []
        for scene in catalog['scenes']:
            projected = self.project(page, scene)
            visible = [n for n in projected['components'] if n['type'] == 'Text']
            self.assertEqual(len(visible), 1)
            texts.append(visible[0]['style']['content']['text'])
            output, _, _ = self.render(projected)
            self.assertIn('Text(', output)
        self.assertIn('Loading', texts)
        self.assertTrue(any(text.startswith('Sample') for text in texts))

    def test_when_nested_and_reused_components_are_scoped_not_cartesian(self):
        page = self.source('''Column { Panel(first, firstError); Panel(second, secondError) }''', '''
@Composable
fun Panel(state: String, showError: Boolean) {
    when (state) {
        "loading" -> { Text("Loading") }
        "content" -> { Column { if (showError) { Text("Error") } else { Text("Content") } } }
        else -> { Text("Empty") }
    }
}
''')
        catalog = self.catalog(page, [
            {'id': 'loading-content', 'values': {'first': 'loading', 'second': 'content', 'firstError': False, 'secondError': False}},
            {'id': 'content-loading', 'values': {'first': 'content', 'second': 'loading', 'firstError': False, 'secondError': False}},
            {'id': 'error', 'values': {'first': 'content', 'second': 'content', 'firstError': True, 'secondError': True}},
            {'id': 'empty', 'values': {'first': 'empty', 'second': 'empty', 'firstError': False, 'secondError': False}}])
        self.assertEqual(len(catalog['groups']), 4)
        seen = set()
        for scene in catalog['scenes']:
            projected = self.project(page, scene)
            for node in projected['components']:
                for branch in node.get('ui_state_path') or []:
                    seen.add((branch['group_id'], branch['branch_id']))
        required = {(g['id'], b) for g in catalog['groups'] for b in g['branches']}
        self.assertTrue(required <= seen, (required - seen))
        self.assertLess(len(catalog['scenes']), 36)

    def test_unknown_collection_has_samples_empty_state_and_text_provenance(self):
        page = self.source('''Column { rows.forEach { Text(it.title) } }''')
        catalog = self.catalog(page, [{'id': 'samples', 'values': {}}, {'id': 'empty', 'values': {'rows': []}}])
        self.assertEqual(len(catalog['collections']), 1)
        counts = []
        for scene in catalog['scenes']:
            projected = self.project(page, scene)
            texts = [n for n in projected['components'] if n['type'] == 'Text']
            counts.append(len(texts))
            for node in texts:
                self.assertTrue(node['style']['content']['text'].startswith('Sample'))
                self.assertTrue(any(p['origin'] == 'ui_preview_sample' for p in node['provenance']))
            self.assertFalse(projected['state_projection']['ui_preview']['business_verified'])
        self.assertEqual(set(counts), {0, 3})

    def test_preview_does_not_resolve_missing_styles_or_assets(self):
        page = self.source('''Column {
Text(state.title, color = unknownColor)
Image(painter = painterResource(unknownIcon), contentDescription = null)
}''')
        projected = self.project(page, self.catalog(page)['scenes'][0])
        text = next(n for n in projected['components'] if n['type'] == 'Text')
        self.assertIsNone(text['style']['typography']['color'])
        self.assertTrue(any(n['unresolved'] for n in projected['components']))
        _, gate, renderer = self.render(projected)
        self.assertEqual(gate['verdict'], 'fail')
        self.assertTrue(renderer.unresolved)

    def test_preview_provenance_survives_final_single_json(self):
        page = self.source('Column { Text(balance) }')
        scene = self.catalog(page)['scenes'][0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.json'
            fixture = root / 'fixture.json'
            source.write_text(json.dumps(page))
            fixture.write_text(json.dumps(preview_fixture(page, scene)))
            generate(Namespace(source_page=source, state_fixture=fixture, output_dir=root / 'out',
                               viewport_width_dp=360, viewport_height_dp=760, slice_scale=2, device='test'))
            version = root / 'out/version_json.json'
            final = json.loads(version.read_text())
            self.assertTrue(final['meta']['sourceGeneration']['stateProjection']['ui_preview'])
            single = load_lanhu_page_input(version)
            self.assertTrue(any((n['style']['content'].get('text') or '').startswith('Sample')
                                for n in single['components']))

    def test_empty_image_model_does_not_become_an_invalid_resource_name(self):
        page = self.source('Column { AsyncImage(model = avatarUrl, contentDescription = null, modifier = Modifier.size(150.dp)) }')
        scene = self.catalog(page, [{'id': 'loaded', 'values': {'avatarUrl': ''}}])['scenes'][0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.json'
            fixture = root / 'fixture.json'
            source.write_text(json.dumps(page))
            fixture.write_text(json.dumps(preview_fixture(page, scene)))
            generate(Namespace(source_page=source, state_fixture=fixture, output_dir=root / 'out',
                               viewport_width_dp=360, viewport_height_dp=760, slice_scale=2, device='test'))
            single = load_lanhu_page_input(root / 'out/version_json.json')
            node = next(n for n in single['components'] if n['type'] == 'AsyncImage')
            self.assertIsNone(node['style']['asset']['resource'])
            self.assertEqual(node['style']['layout']['width_dp'], 150)

    def test_runtime_text_is_exact_scoped_and_does_not_supply_geometry(self):
        page = self.source('Column { Text(balance) }')
        node = next(n for n in page['components'] if n['type'] == 'Text')
        binding = {'page': page['page'], 'text_bindings': {node['id']: 'app:id/balance'}}
        with tempfile.TemporaryDirectory() as directory:
            xml = Path(directory) / 'window.xml'
            xml.write_text('<hierarchy><node resource-id="app:id/balance" text="123.45" '
                           'bounds="[0,0][50,20]" password="false"/></hierarchy>')
            values = import_runtime_text(page, xml, binding)
            scene = self.catalog(page)['scenes'][0]
            fixture = preview_fixture(page, scene, display_values=values)
            projected, _ = project_source_page(page, fixture)
            text = next(n for n in projected['components'] if n['type'] == 'Text')
            self.assertEqual(text['style']['content']['text'], '123.45')
            self.assertTrue(any(p.get('origin') == 'runtime' and '#sha256=' in p.get('source', '')
                                for p in text['provenance']))
            wrong = copy.deepcopy(binding)
            wrong['page'] = {'id': 'other', 'state': 'default'}
            with self.assertRaisesRegex(ValueError, 'page/state'):
                import_runtime_text(page, xml, wrong)
            xml.write_text('<hierarchy><node resource-id="app:id/balance" text="secret" password="true"/></hierarchy>')
            with self.assertRaisesRegex(ValueError, 'password'):
                import_runtime_text(page, xml, binding)

    def test_list_children_do_not_expand_again_per_descendant(self):
        page = self.source('''Column { rows.forEach { Row { Text(it.title); Text(it.subtitle) } } }''')
        projected = self.project(page, self.catalog(page)['scenes'][0])
        rows = [n for n in projected['components'] if n['type'] == 'Row']
        texts = [n for n in projected['components'] if n['type'] == 'Text']
        self.assertEqual(len(rows), 3)
        self.assertEqual(len(texts), 6)
        for row in rows:
            self.assertEqual(sum(n['parent_id'] == row['id'] for n in texts), 2)

    def test_runtime_text_without_resource_ids_can_bind_exact_list_instances(self):
        page = self.source('Column { rows.forEach { Text(it.formatted) } }')
        node = next(n for n in page['components'] if n['type'] == 'Text')
        with tempfile.TemporaryDirectory() as directory:
            xml = Path(directory) / 'window.xml'
            xml.write_text('<hierarchy><node text="2,500"/><node text="12,500"/></hierarchy>')
            binding = {'page': page['page'], 'text_bindings': {
                node['id'] + '__item1': {'node_index': 0}, node['id'] + '__item2': {'node_index': 1}}}
            values = import_runtime_text(page, xml, binding)
            scene = self.catalog(page, [{'id': 'default', 'values': {'rows': [{}, {}]}}])['scenes'][0]
            projected, _ = project_source_page(page, preview_fixture(page, scene, values))
            self.assertEqual([n['style']['content']['text'] for n in projected['components'] if n['type'] == 'Text'], ['2,500', '12,500'])
            binding['text_bindings'][node['id']] = {'node_index': -1}
            with self.assertRaises(ValueError):
                import_runtime_text(page, xml, binding)

    def test_independent_dialog_roots_are_separate_previews_not_stacked_windows(self):
        page = self.source('''
Column { Text("Page") }
if (showPicker) { Picker() }
if (showProgress) { Progress() }
''', '''
@Composable
fun Picker() { Column { Text("Picker") } }
@Composable
fun Progress() { Column { Text("Progress") } }
''')
        roots = [node for node in page['components'] if node.get('parent_id') is None]
        catalog = self.catalog(page, [
            {'id': 'root-' + str(index), 'root_id': root['id'],
             'values': {'showPicker': True, 'showProgress': True}}
            for index, root in enumerate(roots)])
        self.assertEqual(len(catalog['scenes']), 3)
        for scene in catalog['scenes']:
            projected = self.project(page, scene)
            self.assertEqual(len([n for n in projected['components'] if n.get('parent_id') is None]), 1)
            self.assertEqual(len([n for n in projected['components'] if n['type'] == 'Text']), 1)

    def test_known_static_collection_keeps_actual_values_in_baseline(self):
        page = self.source('''Column { listOf("One", "Two").forEach { Text(it) } }''')
        projected = self.project(page, self.catalog(page)['scenes'][0])
        self.assertEqual([n['style']['content']['text'] for n in projected['components'] if n['type'] == 'Text'],
                         ['One', 'Two'])

    def test_invalid_choice_or_sample_count_is_not_silently_accepted(self):
        page = self.source('Column { if (loading) { Text("Loading") } else { Text(title) } }')
        fixture = preview_fixture(page, self.catalog(page, [{'id': 'loading', 'values': {'loading': True}}])['scenes'][0])
        invalid = copy.deepcopy(fixture)
        invalid['ui_preview']['choices'] = {}
        with self.assertRaisesRegex(ValueError, 'branch switches'):
            project_source_page(page, invalid)
        fixture['ui_preview']['sample_count'] = -1
        with self.assertRaisesRegex(ValueError, 'sample count'):
            project_source_page(page, fixture)

    def test_duplicate_runtime_id_is_not_guessed_and_unbound_text_stays_sample(self):
        page = self.source('Column { Text(title); Text(balance) }')
        node = next(n for n in page['components'] if n['type'] == 'Text')
        binding = {'page': page['page'], 'text_bindings': {node['id']: 'app:id/value'}}
        with tempfile.TemporaryDirectory() as directory:
            xml = Path(directory) / 'window.xml'
            xml.write_text('<hierarchy><node resource-id="app:id/value" text="One"/>'
                           '<node resource-id="app:id/value" text="Two"/></hierarchy>')
            with self.assertRaisesRegex(ValueError, 'exactly once'):
                import_runtime_text(page, xml, binding)

    def test_cli_report_separates_output_success_from_visual_acceptance(self):
        from generate_ui_state_previews import generate_previews
        page = self.source('Column { Text(title, color = unknownColor) }')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.json'
            source.write_text(json.dumps(page))
            states = root / 'states.json'
            states.write_text(json.dumps({'schema': 'android-to-harmony.ui-state-inputs.v1',
                'page_id': page['page']['id'], 'scenes': [{'id': 'default', 'values': {}}]}))
            report = generate_previews(Namespace(source_page=source, states=states, output_dir=root / 'output',
                viewport_width_dp=360, viewport_height_dp=760, slice_scale=2,
                uiautomator_xml=None, text_bindings=None))
            self.assertEqual(report['generated_count'], 1)
            self.assertEqual(report['scenes'][0]['verdict'], 'fail')
            self.assertEqual(report['visual_acceptance'], 'not_verified')
            self.assertFalse(report['business_verified'])
            self.assertIn('Business reachability and visual acceptance: not verified.',
                          (root / 'output/preview-report.md').read_text())
            with self.assertRaises(FileExistsError):
                generate_previews(Namespace(source_page=source, states=states, output_dir=root / 'output',
                    viewport_width_dp=360, viewport_height_dp=760, slice_scale=2,
                    uiautomator_xml=None, text_bindings=None))

    def test_resolved_shape_object_is_not_written_into_boolean_or_corner_fields(self):
        page = self.source('''
val shape = RoundedCornerShape(12.dp)
Column {
  Card(shape = shape) { Text(title) }
  Box(Modifier.size(40.dp).clip(shape)) { Text(title) }
}
''')
        projected = self.project(page, self.catalog(page)['scenes'][0])
        card = next(n for n in projected['components'] if n['type'] == 'Card')
        box = next(n for n in projected['components'] if n['type'] == 'Box')
        self.assertIs(box['style']['surface']['clip'], True)
        self.assertEqual(set(card['style']['surface']['corner_radius_dp'].values()), {12})
        self.render(projected)

    def test_required_fact_order_is_stable_across_process_hash_seeds(self):
        code = '''import json
from component_required_facts import build_required_facts
node = {'type': 'Slider', 'arguments': {'semantic': {
    name: {'expression': name} for name in ('value', 'valueRange', 'steps', 'enabled')
}}, 'style': {}}
print(json.dumps(build_required_facts(node), sort_keys=True))
'''
        outputs = [subprocess.check_output([sys.executable, '-B', '-c', code],
                   cwd=Path(__file__).parent, env=dict(os.environ, PYTHONHASHSEED=str(seed)))
                   for seed in range(4)]
        self.assertEqual(len(set(outputs)), 1)


if __name__ == '__main__':
    unittest.main()
