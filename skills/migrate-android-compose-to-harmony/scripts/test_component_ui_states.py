import argparse
import json
import tempfile
import unittest
from ui_migration.contracts.lanhu_storage import unpack_lanhu_document
from pathlib import Path

from analyze_compose_project import analyze
from real_page_pipeline import build_source_page_spec
from generate_lanhu_source_page import generate
from generate_arkui_page import Renderer, load_lanhu_page_input, derive_page_root
from ui_migration.frontend.project_styles import build_style_definitions
import test_project_style_definitions as style_helpers
from ui_migration.contracts.consumption import build_target_phase_consumption_gate


SOURCE = '''
@Composable fun Page() { Column { Text("Page header", color = Color.Black); AccountCard(state); Text("Page footer", color = Color.Black) } }
@Composable fun AccountCard(state: AccountState) {
    Column(Modifier.padding(12.dp)) {
        Text("Account", color = Color.Black)
        if (state.loading) { Text("Loading", color = Color.Black) }
        else if (state.error) { Text("Retry", color = Color.Black) }
        else { Text(state.name, color = Color.Black) }
    }
}
'''


def compile_states(code=SOURCE):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / 'Page.kt').write_text(code)
        contract = analyze(root, {}, {'Page.kt':code})
        source = build_source_page_spec(contract, 'Page.kt', 'Page', 'page', 'default', 'a'*64, root,
            style_definitions=build_style_definitions(style_helpers.ProjectStyleDefinitionsTest().contract()))
        path = root / 'source.json'
        path.write_text(json.dumps(source))
        result = generate(argparse.Namespace(source_page=path, state_fixture=None,
            output_dir=root/'output', viewport_width_dp=360, viewport_height_dp=740,
            slice_scale=2, device='component-state-test', preserve_component_ui_states=True))
        version = unpack_lanhu_document(json.loads((root/'output/version_json.json').read_text()))
        (root/'Page.kt').unlink()
        path.unlink()
        page = load_lanhu_page_input(root/'output/version_json.json')
        renderer = Renderer(derive_page_root(page), set(), {}, page)
        code = renderer.render()
        renderer.test_phase_gate = build_target_phase_consumption_gate(page,
            renderer.android_page_processed_component_ids, renderer.android_page_processed_call_ids,
            renderer.android_page_applied_paths, renderer.android_page_applied_component_paths,
            getattr(renderer, 'android_page_layout_decisions', []))
        return version, renderer, code, result


class ComponentUiStatesTest(unittest.TestCase):
    def test_business_states_are_kept_without_creating_page_states(self):
        version, renderer, code, result = compile_states()
        catalog = version['meta']['migration']['componentUiStates']
        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog[0]['name'], 'AccountCard')
        self.assertEqual(len(catalog[0]['variants']), 3)
        self.assertEqual(version['meta']['migration']['page']['state'], 'default')
        self.assertIn('private AccountCard(', code)
        self.assertIn('uiState: string', code)
        self.assertNotIn('@State private uiState', code)
        for text in ('Loading', 'Retry', 'Sample text', 'Page header', 'Page footer'):
            self.assertIn(text, code)
        self.assertIn('state: UiBusinessArgument | null', code)
        self.assertNotIn('state.loading', code)
        self.assertNotIn('state: any', code)
        self.assertEqual(code.count('private AccountCard('), 1)
        self.assertFalse(any('state_resolution' in str(u) for u in renderer.unresolved))
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertEqual(renderer.test_phase_gate['verdict'], 'pass', renderer.test_phase_gate['failures'])
        coverage = renderer.business_components.ui_states.coverage
        self.assertEqual(len(coverage), 3)
        self.assertTrue(all(c['component_count'] > 0 and not c['missing_component_ids'] for c in coverage))

    def test_instance_specific_style_cannot_silently_reuse_first_state_body(self):
        _, renderer, _, _ = compile_states('''
@Composable fun Page() { Column { Badge(40.dp, true); Badge(60.dp, false) } }
@Composable fun Badge(size: Dp, loading: Boolean) {
    Box(Modifier.size(size)) {
        if(loading) { Text("Wait", color = Color.Black) } else { Text("Ready", color = Color.Black) }
    }
}
''')
        self.assertTrue(any('different non-parameter UI facts' in str(u) for u in renderer.unresolved))

    def test_repeated_component_has_one_interface_and_preserves_text_parameters(self):
        _, renderer, code, result = compile_states('''
@Composable fun Page() { Column { Badge("One", true); Badge("Two", false) } }
@Composable fun Badge(label: String, loading: Boolean) { if(loading) { Text("Loading", color = Color.Black) } else { Text(label, color = Color.Black) } }
''')
        self.assertEqual(code.count('private Badge('), 1)
        self.assertIn('this.Badge("One", true, "then")', code)
        self.assertIn('this.Badge("Two", false, "else")', code)
        self.assertIn('label ??', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_each_branch_keeps_its_own_layout_and_background(self):
        _, _, code, result = compile_states('''
@Composable fun Page() { Tile() }
@Composable fun Tile() {
    if(loading) { Box(Modifier.size(40.dp).background(Color.Red)) { Text("Wait", color = Color.Black) } }
    else { Column(Modifier.padding(24.dp).background(Color.Blue)) { Text("Ready", color = Color.Black) } }
}
''')
        self.assertIn(".backgroundColor('#FFFF0000')", code)
        self.assertIn(".backgroundColor('#FF0000FF')", code)
        self.assertIn('layoutPx(24)', code)
        self.assertIn('layoutPx(40)', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_when_branches_are_preserved_without_resolving_business_enum(self):
        version, _, code, result = compile_states('''
@Composable fun Page() { Badge(state) }
@Composable fun Badge(state: State) { when(state) {
    State.Loading -> Text("Loading", color = Color.Black)
    State.Error -> Text("Retry", color = Color.Black)
    else -> Text("Ready", color = Color.Black)
} }
''')
        self.assertEqual(len(version['meta']['migration']['componentUiStates'][0]['variants']), 3)
        for text in ('Loading', 'Retry', 'Ready'):
            self.assertIn(text, code)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_page_branches_are_not_component_states(self):
        version, _, _, _ = compile_states('''
@Composable fun Page() { if(true) { Text("Page A") } else { Text("Page B") } }
''')
        self.assertEqual(version['meta']['migration'].get('componentUiStates', []), [])

    def test_independent_component_groups_are_reported_not_silently_complete(self):
        version, _, _, result = compile_states('''
@Composable fun Page() { Card() }
@Composable fun Card() { Column { if(a) { Text("A") } else { Text("B") }; if(b) { Text("C") } else { Text("D") } } }
''')
        self.assertFalse(result['generation_complete'])
        self.assertTrue(any('multiple UI branch groups' in str(u) for u in result['unresolved']))

    def test_incomplete_legacy_when_inventory_is_not_accepted(self):
        _, _, _, result = compile_states('''
@Composable fun Page() { Badge(state) }
@Composable fun Badge(state: State) { when(state) { State.A -> Text("A"); State.B -> Text("B"); else -> Text("C") } }
''')
        self.assertFalse(result['generation_complete'])
        self.assertTrue(any('PSI when branches disagree' in str(u) for u in result['unresolved']))

    def test_nonselected_unresolved_style_gets_reported_target_default(self):
        _, renderer, _, result = compile_states('''
@Composable fun Page() { Badge(false) }
@Composable fun Badge(loading: Boolean) { if(loading) { Text("Wait", color = unknownColor) } else { Text("Ready", color = Color.Black) } }
''')
        self.assertFalse(result['generation_complete'])
        self.assertTrue(any(u.get('component_ui_state') == 'Badge/then' for u in result['unresolved']))
        self.assertFalse(any('unknownColor' in str(u) for u in renderer.unresolved))
        self.assertTrue(any('unknownColor' in str(w) and w.get('component_ui_state') == 'Badge/then'
                            for w in renderer.android_page_input['generation_warnings']))


if __name__ == '__main__':
    unittest.main()
