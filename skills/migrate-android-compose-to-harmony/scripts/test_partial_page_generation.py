import copy
import hashlib
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from analyze_compose_project import analyze
from generate_arkui_page import Renderer, derive_page_root, load_lanhu_page_input
from generate_lanhu_source_page import generate
from real_page_pipeline import build_source_page_spec
import test_dp_size
from test_dp_size import ROOT


class PartialPageGenerationTest(unittest.TestCase):
    def source(self, body):
        return test_dp_size.DpSizeTest().source_page(body)

    def generate_page(self, page, values=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source, fixture = root / 'source.json', root / 'fixture.json'
        source.write_text(json.dumps(page))
        fixture.write_text(json.dumps({'schema': 'android-to-harmony.page-state-fixture.v1',
                                      'page': page['page'], 'values': values or {}}))
        result = generate(Namespace(source_page=source, state_fixture=fixture, output_dir=root / 'out',
            viewport_width_dp=360, viewport_height_dp=760, slice_scale=2, device='test'))
        version = root / 'out/version_json.json'
        loaded = load_lanhu_page_input(version)
        return root / 'out', result, loaded

    def test_unknown_branches_preview_first_without_claiming_condition_resolved(self):
        page = self.source('''Column {
Text("Known title")
if (state.loading) { Text("Loading") } else { Text("Content") }
Text("Known footer")
}''')
        out, result, loaded = self.generate_page(page)
        self.assertEqual(result['status'], 'partial_generation')
        self.assertEqual(result['verdict'], 'fail')
        retained = result['state_projection']['retained_components']
        self.assertEqual(len(loaded['components']) + len(retained), len(page['components']))
        defaults = [n for n in loaded['components'] if n['source'].get('state_resolution')]
        self.assertEqual(len(defaults), 1)
        self.assertEqual(defaults[0]['source']['state_resolution']['status'], 'preview_default')
        self.assertFalse(result['state_projection']['selection_complete'])
        renderer = Renderer(derive_page_root(loaded), set(), {}, loaded)
        text = renderer.render()
        self.assertIn("'Known title'", text)
        self.assertIn("'Known footer'", text)
        self.assertIn("Text('Loading')", text)
        self.assertNotIn("Text('Content')", text)
        self.assertTrue(renderer.unresolved)
        worklist = json.loads((out / 'unresolved-worklist.json').read_text())
        self.assertTrue(any(task['category'] == 'state_input' for task in worklist['tasks']))

    def test_unknown_list_keeps_template_not_fake_items_and_known_sibling(self):
        page = self.source('Column { rows.forEach { Text(it.title) }; Text("Footer") }')
        _, result, loaded = self.generate_page(page)
        self.assertEqual(result['state_projection']['expanded_list_instances'], 0)
        self.assertEqual(len(loaded['components']), len(page['components']))
        template = next(n for n in loaded['components'] if n['source'].get('state_resolution'))
        self.assertEqual(template['source']['state_resolution']['kind'], 'collection')
        self.assertEqual(template['source']['state_resolution']['expression'], 'rows')
        self.assertFalse(any('__item' in n['id'] for n in loaded['components']))

    def test_fixed_input_removes_deferred_state_without_editing_generated_json(self):
        page = self.source('Column { if (state.loading) { Text("Loading") } else { Text("Content") } }')
        _, partial, _ = self.generate_page(page)
        self.assertFalse(partial['generation_complete'])
        out, _, loaded = self.generate_page(page, {'state': {'loading': False}})
        self.assertFalse(any(n['source'].get('state_resolution') for n in loaded['components']))
        self.assertEqual([n['style']['content']['text'] for n in loaded['components'] if n['type'] == 'Text'], ['Content'])
        worklist = json.loads((out / 'unresolved-worklist.json').read_text())
        self.assertFalse(any(t['category'] == 'state_input' for t in worklist['tasks']))

    def test_mismatched_identity_and_broken_hierarchy_are_still_errors(self):
        page = self.source('Column { Text("Known") }')
        broken = copy.deepcopy(page)
        broken['components'][1]['parent_id'] = 'missing'
        with self.assertRaises(ValueError):
            self.generate_page(broken)
        from ui_migration.frontend.fixed_state import project_source_page
        with self.assertRaisesRegex(ValueError, 'page/state'):
            project_source_page(page, {'schema': 'android-to-harmony.page-state-fixture.v1',
                'page': {'id': 'other', 'state': 'loading'}}, allow_unresolved=True)

    def test_ambiguous_theme_is_reported_without_invented_typography(self):
        text = 'package example\n@Composable fun Page() { Column { Text("Known") } }'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / ROOT
            path.parent.mkdir(parents=True)
            path.write_text(text)
            contract = analyze(root, {}, {ROOT: text})
            inventory = contract['ui']['compose_theme_token_inventory']
            inventory['theme_applications'] = [
                {'source': 'PageTheme.kt', 'arguments': {'typography': {'expression': 'pageType'}}},
                {'source': 'PasscodeTheme.kt', 'arguments': {'typography': {'expression': 'otherType()'}}}]
            page = build_source_page_spec(contract, ROOT, 'Page', 'page', 'default', 'a' * 64, root)
        self.assertTrue(page['source_diagnostics'])
        text_node = next(n for n in page['components'] if n['type'] == 'Text')
        self.assertIsNone(text_node['style']['typography']['font_size_sp'])
        out, result, _ = self.generate_page(page)
        self.assertFalse(result['generation_complete'])
        tasks = json.loads((out / 'unresolved-worklist.json').read_text())['tasks']
        self.assertTrue(any(t['category'] == 'theme' for t in tasks))

    def test_worklist_has_scoped_dependencies_and_no_unrelated_business_values(self):
        page = self.source('Column { Text("Known", color = accent) }')
        node = next(n for n in page['components'] if n['type'] == 'Text')
        node['local_values'] = {'accent': 'palette.active', 'unrelated': 'repository.loadEverything()'}
        out, _, _ = self.generate_page(page)
        worklist = json.loads((out / 'unresolved-worklist.json').read_text())
        self.assertTrue(worklist['tasks'])
        serialized = json.dumps(worklist)
        self.assertIn('palette.active', serialized)
        self.assertNotIn('loadEverything', serialized)
        self.assertTrue(all(task['id'] and task['occurrences'] for task in worklist['tasks']))
        self.assertIn('version_json_sha256', worklist)
        self.assertEqual(worklist['version_json_sha256'], hashlib.sha256((out / 'version_json.json').read_bytes()).hexdigest())

    def test_recursive_business_component_stops_expansion_and_keeps_known_sibling(self):
        page = test_dp_size.DpSizeTest().source_page('Column { RecursiveItem(); Text("Footer") }', '''
@Composable
fun RecursiveItem() { Column { RecursiveItem() } }
''')
        self.assertLess(len(page['components']), 10)
        self.assertTrue(any('recursive' in issue['reason'] for issue in page['unresolved']))
        self.assertTrue(any(n['style']['content']['text'] == 'Footer' for n in page['components']))
        _, result, _ = self.generate_page(page)
        self.assertTrue(any('recursive' in issue.get('reason', '') for issue in result['unresolved']))

    def test_unparseable_local_style_keeps_text_and_explicit_size(self):
        from ui_migration.frontend.styles import static_style_for_call
        call = {'source': ROOT, 'line': 1, 'component': 'Text', 'semantic_arguments': {
            'text': {'expression': '"Known"'},
            'style': {'expression': 'TextStyle(fontSize = 16.sp, color = when (kind) { A -> accent.copy(alpha = 0.5f) B -> other })'}}}
        style, _, unresolved = static_style_for_call(call, {}, None, {})
        self.assertEqual(style['content']['text'], 'Known')
        self.assertEqual(style['typography']['font_size_sp'], 16)
        self.assertTrue(unresolved)

    def test_long_multiline_expression_roundtrips_without_truncating_solver_input(self):
        from page_snapshot import normalize_unresolved, PageSnapshotError
        expression = 'when (state.kind) {\n' + '\n'.join(f'  {n} -> values[{n}]' for n in range(40)) + '\n}'
        issue = {'path': 'style.surface.background', 'expression': expression, 'reason': 'needs state'}
        self.assertEqual(normalize_unresolved([issue], 'test')[0]['expression'], expression)
        for invalid in ('', None, 'bad\x00value', 'x' * 10001):
            with self.assertRaises(PageSnapshotError):
                normalize_unresolved([{**issue, 'expression': invalid}], 'test')

    def test_worklist_reports_diagnostics_without_ai_dispatch(self):
        from ui_migration.frontend.unresolved_worklist import build_worklist
        from ui_migration.frontend.source_tree import SourceTree
        tree = SourceTree(self.source('Column { Text("Known") }'))
        document = {'meta': {'migration': {'page': tree.payload['page']}}}
        empty = build_worklist(document, tree, [])
        self.assertNotIn('needs_assistance', empty)
        self.assertFalse(empty['has_unresolved'])
        self.assertEqual(empty['tasks'], [])
        issues = [{'path': 'style.typography.color', 'expression': 'palette.active', 'reason': 'unknown'}]
        pending = build_worklist(document, tree, issues)
        self.assertTrue(pending['has_unresolved'])
        self.assertNotIn('needs_assistance', pending)
        self.assertEqual(pending['task_count'], 1)
        self.assertEqual(build_worklist(document, tree, issues), build_worklist(document, tree, issues))
        variants = build_worklist(document, tree, issues + [
            {**issues[0], 'component_ui_state': 'Button/pressed'}])
        self.assertEqual(variants['task_count'], 2)
        self.assertEqual(variants['tasks'][1]['occurrences'][0]['component_ui_state'], 'Button/pressed')


if __name__ == '__main__':
    unittest.main()
