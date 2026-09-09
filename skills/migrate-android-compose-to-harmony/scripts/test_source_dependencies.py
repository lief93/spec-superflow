import tempfile
import unittest
from pathlib import Path

from analyze_compose_project import analyze, collect_composable_associations, extract_composables
from real_page_pipeline import build_source_page_spec
from generate_lanhu_source_page import project_source_page
from ui_migration.frontend.source_symbols import SourceSymbolIndex


class SourceDependenciesTest(unittest.TestCase):
    def page(self, body, extra):
        files = {'Page.kt': 'package sample\nimport androidx.compose.runtime.Composable\n'
                 'import androidx.compose.foundation.layout.*\nimport androidx.compose.ui.Modifier\n'
                 'import androidx.compose.ui.unit.dp\nimport pieces.*\n'
                 '@Composable fun Page() { ' + body + ' }', **extra}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, text in files.items():
                (root / name).write_text(text)
            contract = analyze(root, {}, files)
            source = build_source_page_spec(contract, 'Page.kt', 'Page', 'page', 'default', 'a'*64, root)
        selected = project_source_page(source, {'schema':'android-to-harmony.page-state-fixture.v1',
            'page': source['page'], 'values': {}}, allow_unresolved=True)[0]
        return source, selected

    def test_scope_alias_and_wildcard_import_keep_nested_content(self):
        source, page = self.page('LazyColumn { section() }', {'Parts.kt': '''package pieces
import androidx.compose.foundation.lazy.LazyListScope
typealias ArticleScope = LazyListScope
fun ArticleScope.section() { ending() }
fun ArticleScope.ending() { item { Text("Last paragraph") } }
'''})
        self.assertIn('Last paragraph', [n['style']['content']['text'] for n in page['components']])
        self.assertIn('ending', [n['name'] for n in source['source_dependency_trace']['definitions']])

    def test_value_alias_and_inferred_modifier_preserve_dimensions(self):
        source, page = self.page('Box(Modifier.card()) {}', {'Parts.kt': '''package pieces
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import tokens.width as cardWidth
fun Modifier.card() = this.width(cardWidth()).height(24.dp)
''', 'Tokens.kt': '''package tokens
import androidx.compose.ui.unit.dp
fun width() = 90.dp
'''})
        box = next(n for n in page['components'] if n['type']=='Box')
        self.assertEqual(box['style']['layout']['width_dp'], 90)
        self.assertEqual(box['style']['layout']['height_dp'], 24)
        trace = source['source_dependency_trace']
        self.assertIn('width', [n['name'] for n in trace['definitions']])
        self.assertFalse(any(n['type']=='card' for n in page['components']))

    def test_trace_separates_content_modifier_style_and_ignores_unused_function(self):
        source, _ = self.page('Tile()', {'Parts.kt': '''package pieces
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
@Composable fun Tile() { Text("A", modifier = Modifier.card(), style = caption()) }
fun Modifier.card() = this.padding(12.dp)
fun caption() = TextStyle(fontSize = 16.sp)
fun unrelatedNetworkOperation() = remoteRequest()
'''})
        trace = source['source_dependency_trace']
        roles = {n['name']: n['role'] for n in trace['definitions']}
        self.assertEqual(roles['Tile'], 'content')
        self.assertEqual(roles['card'], 'modifier')
        self.assertEqual(roles['caption'], 'value')
        self.assertNotIn('unrelatedNetworkOperation', roles)

    def test_missing_content_is_reported_before_code_generation(self):
        index = SourceSymbolIndex({'Page.kt': '@Composable fun Page() { Child() }\n'
                                   '@Composable fun Child() { Text("A") }'})
        trace = index.trace('Page.kt','Page')
        gate = index.reconcile_content(trace, [{'source':'Page.kt','composable':'Page'}])
        self.assertEqual(gate['verdict'], 'fail')
        self.assertEqual([f['name'] for f in gate['missing_content_definitions']], ['Child'])

    def test_missing_aliased_native_control_is_not_hidden_by_empty_inventory(self):
        index = SourceSymbolIndex({'Page.kt':'import androidx.compose.material3.Text as Caption\n'
                                   '@Composable fun Page() { Caption("A") }'})
        gate = index.reconcile_content(index.trace('Page.kt','Page'),
                                       [{'source':'Page.kt','composable':'Page'}], [])
        self.assertEqual(gate['verdict'],'fail')
        self.assertEqual(gate['missing_native_controls'][0]['component'],'Text')

    def test_global_value_dependency_uses_declaration_imports(self):
        source, page = self.page('Box(Modifier.width(cardWidth)) {}', {'Parts.kt': '''package pieces
import tokens.width as compute
val cardWidth = compute()
''', 'Tokens.kt': '''package tokens
import androidx.compose.ui.unit.dp
fun width() = 90.dp
'''})
        box = next(n for n in page['components'] if n['type']=='Box')
        self.assertEqual(box['style']['layout']['width_dp'],90)
        self.assertIn('width',[f['name'] for f in source['source_dependency_trace']['definitions']])

    def test_scope_passed_as_parameter_preserves_content(self):
        _, page = self.page('LazyColumn { addRows(this) }', {'Parts.kt': '''package pieces
import androidx.compose.foundation.lazy.LazyListScope
fun addRows(scope: LazyListScope) { scope.item { Text("Entry") } }
'''})
        self.assertIn('Entry',[n['style']['content']['text'] for n in page['components']])

    def test_modifier_factory_without_extension_receiver(self):
        for body in ('Box(panel()) {}', 'Box(modifier=panel()) {}'):
            _, page = self.page(body, {'Parts.kt': '''package pieces
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
fun panel(): Modifier = Modifier.width(90.dp).height(24.dp)
'''})
            box = next(n for n in page['components'] if n['type']=='Box')
            self.assertEqual(box['style']['layout']['width_dp'],90)
            self.assertEqual(box['style']['layout']['height_dp'],24)

    def test_ambiguous_imports_are_reported_not_arbitrarily_selected(self):
        index = SourceSymbolIndex({'Page.kt':'package app\nimport a.*\nimport b.*\n'
                                   '@Composable fun Page() { Card() }',
                                   'A.kt':'package a\n@Composable fun Card() { Text("A") }',
                                   'B.kt':'package b\n@Composable fun Card() { Text("B") }'})
        trace = index.trace('Page.kt','Page')
        self.assertEqual(trace['unresolved'][0]['status'], 'ambiguous')
        self.assertEqual(len(trace['unresolved'][0]['targets']),2)

    def test_cycle_finishes_and_keeps_call_chain(self):
        index = SourceSymbolIndex({'Page.kt':'@Composable fun Page() { A() }\n'
                                   '@Composable fun A() { Page() }'})
        trace = index.trace('Page.kt','Page')
        self.assertEqual(len(trace['definitions']),2)
        self.assertEqual(len(trace['edges']),2)

    def test_same_name_overloads_do_not_overwrite_ui_inventory(self):
        files = {'Page.kt':'@Composable fun Page(loading: Boolean) { if (loading) Text("Loading") }\n'
                          '@Composable fun Page(title: String) { Text(title) }'}
        associations = collect_composable_associations(files)
        declarations = extract_composables('Page.kt',files['Page.kt'],composable_associations=associations)
        self.assertEqual(len(declarations),2)
        self.assertEqual(len({d['declaration_id'] for d in declarations}),2)
        self.assertEqual(sum(len(d['semantic_ui_calls']) for d in declarations),2)

    def test_state_selection_applies_same_parameters_to_modifier_and_style(self):
        for selected, expected in [('true',12), ('false',0)]:
            source, page = self.page('Tile('+selected+')', {'Parts.kt': '''package pieces
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
@Composable fun Tile(active: Boolean) { Inner(active) }
@Composable fun Inner(active: Boolean) {
Text("A", modifier=Modifier.spacing(active), style=caption(active))
}
fun Modifier.spacing(active: Boolean) = if (active) this.padding(12.dp) else this
fun caption(active: Boolean) = TextStyle(fontSize=if (active) 20.sp else 16.sp)
'''})
            text = next(n for n in page['components'] if n['type']=='Text')
            self.assertEqual((text['style']['layout']['padding_dp'] or {}).get('top',0),expected)
            self.assertEqual(text['style']['typography']['font_size_sp'],20 if selected=='true' else 16)
            self.assertEqual(source['source_dependency_gate']['verdict'],'pass')


if __name__ == '__main__':
    unittest.main()
