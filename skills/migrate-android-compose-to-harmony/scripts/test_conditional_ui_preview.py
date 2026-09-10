import json
import unittest

import test_dp_size
import test_partial_page_generation
from generate_arkui_page import Renderer, derive_page_root


class ConditionalUiPreviewTest(unittest.TestCase):
    def generate(self, body, values=None, declarations=''):
        helper = test_partial_page_generation.PartialPageGenerationTest()
        self.addCleanup(helper.doCleanups)
        page = test_dp_size.DpSizeTest().source_page(body, declarations)
        out, result, loaded = helper.generate_page(page, values)
        from ui_migration.contracts.lanhu_storage import unpack_lanhu_document
        self.document = unpack_lanhu_document(json.loads((out / 'version_json.json').read_text()))
        code = Renderer(derive_page_root(loaded), set(), {}, loaded).render()
        return result, loaded, code

    def test_unknown_branch_renders_first_and_retains_other_properties(self):
        result, loaded, code = self.generate('''Column {
if (currentPage < 3) {
    Text("Next", fontSize = 18.sp, color = Color.Red, modifier = Modifier.height(30.dp))
} else {
    Text("Explore", fontSize = 24.sp, color = Color.Blue, modifier = Modifier.height(90.dp))
}
Text("Footer")
}''')
        self.assertIn("Text('Next')", code)
        self.assertNotIn("Text('Explore')", code)
        self.assertIn("Text('Footer')", code)
        self.assertFalse(result['generation_complete'])
        projection = result['state_projection']
        self.assertFalse(projection['selection_complete'])
        retained = projection['retained_components']
        other = next(n for n in retained if n['type'] == 'Text')
        self.assertEqual(other['style']['content']['text'], 'Explore')
        self.assertEqual(other['style']['typography']['font_size_sp'], 24)
        self.assertEqual(other['style']['typography']['color'], '#FF0000FF')
        self.assertEqual(other['style']['layout']['height_dp'], 90)
        self.assertNotIn(other['id'], loaded['by_id'])
        stored = self.document['meta']['sourceGeneration']['stateProjection']['retained_components']
        self.assertEqual(stored, retained)
        shown = next(n for n in loaded['components'] if n['style']['content'].get('text') == 'Next')
        footer = next(n for n in loaded['components'] if n['style']['content'].get('text') == 'Footer')
        self.assertEqual(footer['bounds_dp']['y'] - shown['bounds_dp']['y'], 30)
        self.assertEqual(shown['source']['state_resolution']['status'], 'preview_default')
        self.assertTrue(any('preview' in u['reason'] for u in shown['unresolved']))

    def test_known_false_selects_else_without_preview_default(self):
        result, loaded, code = self.generate('Column { if (page < 3) { Text("A") } else { Text("B") } }', {'page': 3})
        self.assertIn("Text('B')", code)
        self.assertNotIn("Text('A')", code)
        self.assertTrue(result['state_projection']['selection_complete'])
        self.assertFalse(result['state_projection'].get('retained_components'))

    def test_outer_known_false_does_not_preview_inner_unknown_branch(self):
        result, loaded, code = self.generate('''Column {
if (false) { if (unknown) { Text("Hidden") } }
Text("Footer")
}''')
        self.assertNotIn("Text('Hidden')", code)
        self.assertIn("Text('Footer')", code)
        self.assertTrue(result['state_projection']['selection_complete'])

    def test_unknown_branch_does_not_invent_values_for_its_text(self):
        result, loaded, _ = self.generate('Column { if (page == 3) { Text(page.toString()) } else { Text("Other") } }')
        shown = next(n for n in loaded['components'] if n['type']=='Text')
        self.assertNotEqual(shown['style']['content']['text'], '3')
        self.assertTrue(any(u['path']=='style.content.text' for u in result['unresolved']))

    def test_nested_unknown_groups_keep_all_alternatives_but_one_path(self):
        result, loaded, code = self.generate('''Column {
if (outer) {
    if (inner) { Text("AA") } else { Text("AB") }
} else { Text("B") }
if (other) { Text("C") } else { Text("D") }
}''')
        for label in ('AA', 'C'):
            self.assertIn("Text('" + label + "')", code)
        for label in ('AB', 'B', 'D'):
            self.assertNotIn("Text('" + label + "')", code)
        all_nodes = loaded['components'] + result['state_projection']['retained_components']
        self.assertEqual({n['style']['content'].get('text') for n in all_nodes if n['type']=='Text'}, {'AA', 'AB', 'B', 'C', 'D'})
        self.assertEqual(len(all_nodes), len({n['id'] for n in all_nodes}))

    def test_when_skips_proven_false_before_unknown_alternative(self):
        result, _, code = self.generate('''Column {
when {
  false -> { Text("No") }
  pending -> { Text("Maybe") }
  else -> { Text("Otherwise") }
}
}''')
        self.assertIn("Text('Maybe')", code)
        self.assertNotIn("Text('No')", code)
        self.assertNotIn("Text('Otherwise')", code)
        self.assertFalse(result['state_projection']['selection_complete'])

    def test_loop_instances_resolve_known_index_and_default_only_unknowns(self):
        result, _, code = self.generate('''Column {
repeat(4) { index ->
    if (index < 3 || pending) { Text("A$index") } else { Text("B$index") }
}
}''')
        for index in range(4):
            self.assertIn("Text('A" + str(index) + "')", code)
        self.assertNotIn("Text('B3')", code)
        self.assertEqual([n['style']['content']['text'] for n in result['state_projection']['retained_components'] if n['type']=='Text'], ['B3'])

    def test_unknown_branch_projects_business_children_and_loop_properties(self):
        result, _, code = self.generate('Column { if (ready) { Label("A") } else { repeat(2) { Label("B$it") } } }', declarations='''
@Composable fun Label(value: String) { Text(value, fontSize = 21.sp, color = Color.Blue) }
''')
        nodes = result['state_projection']['retained_components']
        texts = [n for n in nodes if n['type']=='Text']
        self.assertEqual([n['style']['content']['text'] for n in texts], ['B0', 'B1'])
        self.assertTrue(all(n['style']['typography']['font_size_sp'] == 21 for n in texts))
        self.assertIn('this.Label("A")', code)
        self.assertNotIn("'B0'", code)

    def test_pager_pages_keep_independent_branch_choices(self):
        result, loaded, code = self.generate('''
val pager = rememberPagerState(pageCount = { 4 })
HorizontalPager(state = pager) { page ->
    if (page < 3 || pending) { Text("A$page") } else { Text("B$page") }
}''')
        self.assertIn('Swiper()', code)
        for page in range(4):
            self.assertIn("Text('A" + str(page) + "')", code)
        self.assertNotIn("Text('B3')", code)
        self.assertEqual([n['style']['content']['text'] for n in result['state_projection']['retained_components'] if n['type']=='Text'], ['B3'])


if __name__ == '__main__':
    unittest.main()
