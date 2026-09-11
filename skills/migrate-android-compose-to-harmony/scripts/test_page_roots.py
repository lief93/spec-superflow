import tempfile
import unittest
from pathlib import Path

from analyze_compose_project import analyze
from real_page_pipeline import build_source_page_spec
from ui_migration.frontend.fixed_state import project_source_page
from test_business_components import compile_page


def source_page(code):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / 'Page.kt').write_text(code)
        contract = analyze(root, {}, {'Page.kt': code})
        return build_source_page_spec(contract, 'Page.kt', 'Page', 'page', 'default', 'a' * 64, root)


def project(source):
    return project_source_page(source, {'schema': 'android-to-harmony.page-state-fixture.v1',
        'page': source['page'], 'values': {}}, allow_unresolved=True)[0]


class PageRootsTest(unittest.TestCase):
    def test_composable_value_and_callback_factories_are_not_visual_roots(self):
        source = source_page('''
@Composable fun Page() {
    val back = onBackForOnboarding()
    val title = getRawString("Title")
    BackHandler { back() }
    CompositionLocalProvider(LocalDensity provides density) {
        Column { Text(title); Button(onClick = back) { Text("Next") } }
    }
}
@Composable fun onBackForOnboarding() = { navigate() }
@Composable fun getRawString(key: String) = key
''')
        roots = [n['type'] for n in project(source)['components'] if n['parent_id'] is None]
        self.assertEqual(roots, ['Column'])
        self.assertTrue({'getRawString', 'onBackForOnboarding'}.issubset(
            {f['name'] for f in source['source_functions']}))

    def test_expression_bodied_ui_is_not_filtered_as_a_value(self):
        _, _, _, _, output = compile_page('''
@Composable fun Page() { Column { Header() } }
@Composable fun Header() = Text("Still visible")
''')
        self.assertIn('Still visible', output)

    def test_overloaded_entry_delegates_instead_of_flattening_both_bodies(self):
        source, _, _, _, output = compile_page('''
@Composable fun Page() { Page(title = "Title") }
@Composable private fun Page(title: String) { Column { Text(title) } }
''')
        self.assertEqual(len([n for n in source['components'] if n['parent_id'] is None]), 1)
        self.assertEqual(len([n for n in source['components'] if n['type'] == 'Text']), 1)
        self.assertIn('Title', output)
        self.assertFalse(any('recursive composable cycle' in u.get('reason', '')
            for u in source.get('unresolved', [])))

    def test_independent_overloads_are_diagnosed_before_building_a_mixed_page(self):
        with self.assertRaisesRegex(Exception, 'page entry overload is ambiguous'):
            source_page('''
@Composable fun Page(title: String) { Text(title) }
@Composable fun Page(count: Int) { Text("Count") }
''')

    def test_existing_contract_cannot_reintroduce_proven_value_roots(self):
        code = '''
@Composable fun Page() { val label = Label("Keep"); Column { Text(label) } }
@Composable fun Label(text: String) = text
'''
        with tempfile.TemporaryDirectory() as directory:
            from unittest.mock import patch
            from ui_migration.frontend.source_symbols import SourceSymbolIndex
            root = Path(directory)
            (root / 'Page.kt').write_text(code)
            original = SourceSymbolIndex._initial_role
            with patch.object(SourceSymbolIndex, '_initial_role',
                    lambda self, f: 'content' if f['name'] == 'Label' else original(self, f)), \
                    patch('ui_migration.frontend.content_roles.refine_value_roles'):
                contract = analyze(root, {}, {'Page.kt': code})
            source = build_source_page_spec(contract, 'Page.kt', 'Page', 'page', 'default', 'a' * 64, root)
        self.assertEqual([n['type'] for n in project(source)['components'] if n['parent_id'] is None], ['Column'])
        self.assertTrue(source['non_ui_calls'])

    def test_same_named_local_navhost_does_not_prove_a_route_host(self):
        source = source_page('''
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
@Composable fun NavHost(content: @Composable () -> Unit) { content() }
@Composable fun Routes() { NavHost { composable("page") { Page() } } }
@Composable fun Page() { Text("One"); Text("Two") }
''')
        self.assertFalse(source.get('page_host'))

    def test_conditional_value_factory_and_deferred_ui_lambda_do_not_add_roots(self):
        source = source_page('''
@Composable fun Page() {
    val title = Title(true, "Name")
    val later = ContentFactory()
    Column { Text(title) }
}
@Composable fun Title(flag: Boolean, name: String) = if (flag) "Hi $name" else name
@Composable fun ContentFactory() = { Text("Not invoked") }
''')
        selected = project(source)['components']
        self.assertEqual([n['type'] for n in selected if n['parent_id'] is None], ['Column'])
        self.assertNotIn('Not invoked', [n['style']['content']['text'] for n in selected])

    def test_route_insets_are_consumed_once_and_unknown_insets_are_not_zero(self):
        source = source_page('''
import androidx.navigation.compose.NavHost as Host
import androidx.navigation.compose.composable as destination
@Composable fun Routes() { Host(navController=nav, startDestination="page",
    modifier=Modifier.statusBarsPadding()) { destination("page") { Page() } } }
@Composable fun Page() { Column(Modifier.statusBarsPadding()) { Text("Content") } }
''')
        fixture = {'schema': 'android-to-harmony.page-state-fixture.v1', 'page': source['page'],
            'values': {'WindowInsets.statusBars': {'left': 0, 'right': 0, 'top': 28, 'bottom': 0}}}
        selected, _ = project_source_page(source, fixture, allow_unresolved=True)
        root = next(n for n in selected['components'] if n['parent_id'] is None)
        column = next(n for n in selected['components'] if n['type'] == 'Column')
        self.assertEqual(root['style']['layout']['padding_dp']['top'], 28)
        self.assertEqual(column['style']['layout']['padding_dp']['top'], 0)
        unknown = next(n for n in project(source)['components'] if n['parent_id'] is None)
        self.assertTrue(any('statusBarsPadding' in u.get('expression', '') for u in unknown['unresolved']))

    def test_route_host_preserves_four_roots_order_modifier_and_alignment(self):
        code = '''
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
@Composable fun Routes() {
    NavHost(navController = nav, startDestination = "page",
        modifier = Modifier.background(Color.White).padding(12.dp),
        contentAlignment = Alignment.CenterEnd) {
        composable("page") { Page() }
    }
}
@Composable fun Page() { Text("One"); Text("Two"); Text("Three"); Text("Four") }
'''
        source, _, page, _, output = compile_page(code)
        projected = project(source)
        root = next(n for n in projected['components'] if n['parent_id'] is None)
        self.assertEqual(root['type'], 'Box')
        self.assertTrue(root['source']['route_content_host'])
        children = [n for n in projected['components'] if n['parent_id'] == root['id']]
        self.assertEqual([n['style']['content']['text'] for n in children], ['One', 'Two', 'Three', 'Four'])
        self.assertEqual(root['style']['surface']['background']['color'], '#FFFFFFFF')
        self.assertEqual(root['style']['layout']['padding_dp']['left'], 12)
        self.assertIn('Alignment.End', output)
        self.assertEqual(len([n for n in page['components'] if n['type'] == 'Text']), 4)

    def test_unknown_multi_root_is_not_silently_wrapped(self):
        source = source_page('@Composable fun Page() { Text("One"); Text("Two") }')
        selected = project(source)
        self.assertEqual([n['type'] for n in selected['components']], ['Text', 'Text'])
        self.assertTrue(all(n['parent_id'] is None for n in selected['components']))

    def test_page_nested_in_row_is_not_misidentified_as_route_host_content(self):
        source = source_page('''
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
@Composable fun Routes() { NavHost(navController=nav, startDestination="page") {
    composable("page") { Row { Page() } }
} }
@Composable fun Page() { Text("One"); Text("Two") }
''')
        self.assertFalse(source.get('page_host'))
        selected = project(source)
        self.assertEqual([n['type'] for n in selected['components']], ['Text', 'Text'])
        self.assertTrue(all(n['parent_id'] is None for n in selected['components']))


if __name__ == '__main__':
    unittest.main()
