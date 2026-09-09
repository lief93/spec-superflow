import tempfile
import unittest
from pathlib import Path

from analyze_compose_project import analyze
from real_page_pipeline import build_source_page_spec
from generate_lanhu_source_page import project_source_page
from ui_migration.frontend.values import evaluate_expression


class SourceCallablesTest(unittest.TestCase):
    def page(self, body, declarations='', values=None):
        text = '''package example
import androidx.compose.runtime.Composable
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
''' + declarations + '\n@Composable fun Page() { ' + body + ' }'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'Page.kt').write_text(text)
            contract = analyze(root, {}, {'Page.kt': text})
            source = build_source_page_spec(contract,'Page.kt','Page','page','loaded','a'*64,root)
        page = project_source_page(source, {'schema':'android-to-harmony.page-state-fixture.v1',
            'page':source['page'],'values':values or {}}, allow_unresolved=True)[0]
        return source, page

    def texts(self, page):
        return [n['style']['content']['text'] for n in page['components'] if n['type']=='Text']

    def test_lambda_retains_defining_environment(self):
        closure = evaluate_expression('{ n: Int -> n + offset }', {'offset':7})
        self.assertEqual(evaluate_expression('fn(3)', {'fn':closure,'offset':100}),10)

    def test_multiline_trailing_slot_keeps_statement_and_string_whitespace(self):
        _, page = self.page('''Wrapper {
    val first = "Two  spaces"
    val second = "Next"
    Text(first)
    Text(second)
}''', '''@Composable fun Wrapper(content: @Composable () -> Unit) {
    Column { content() }
}''')
        self.assertEqual(self.texts(page), ['Two  spaces', 'Next'])

    def test_object_slot_selects_current_content_and_preserves_capture(self):
        source, page = self.page('''
val tabs = makeTabs("Topics")
val selected = 0
Box { tabs[selected].content() }
''', '''class Entry(val content: @Composable () -> Unit)
fun makeTabs(label: String): List<Entry> {
    val first = Entry(content = { Text(label) })
    val second = Entry(content = { Text("Other") })
    return listOf(first, second)
}''')
        self.assertEqual(self.texts(page), ['Topics'])
        text = next(n for n in page['components'] if n['type']=='Text')
        self.assertIsNotNone(text['parent_id'])

    def test_multiple_forwarders_and_parameterized_slot(self):
        _, page = self.page('Column { Outer { value -> Text(value) } }', '''
@Composable fun Outer(body: @Composable (String) -> Unit) { Middle(body) }
@Composable fun Middle(body: @Composable (String) -> Unit) {
    val entry = Entry(body)
    Row { entry.content("Hello") }
}
class Entry(val content: @Composable (String) -> Unit)
''')
        self.assertEqual(self.texts(page), ['Hello'])

    def test_function_reference_and_conditional_selection(self):
        _, page = self.page('''
val slot = if (true) ::Greeting else ::Other
Box { slot() }
''', '''@Composable fun Greeting() { Text("Hello") }
@Composable fun Other() { Text("Other") }''')
        self.assertEqual(self.texts(page), ['Hello'])

    def test_unknown_slot_is_retained_at_callsite(self):
        _, page = self.page('Box { entry.content() }',
            'class Entry(val content: @Composable () -> Unit)')
        slots = [n for n in page['components'] if n.get('slot_invocation')]
        self.assertTrue(slots)
        self.assertTrue(any(u.get('path')=='source.callable' for n in slots for u in n['unresolved']))

    def test_reference_arguments_and_local_lambda_are_not_rendered_at_definition(self):
        _, page = self.page('''
val unused = { Text("Unused") }
val slot = ::Greeting
Column { slot("One"); slot("Two") }
''', '@Composable fun Greeting(label: String) { Text(label) }')
        self.assertEqual(self.texts(page), ['One', 'Two'])

    def test_captured_layout_and_invocation_parent_are_preserved(self):
        _, page = self.page('''
val gap = 12.dp
val entry = Entry { Row(Modifier.fillMaxWidth().padding(gap)) { Text("A") } }
Box { entry.content() }
''', '''import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
class Entry(val content: @Composable () -> Unit)''')
        row = next(n for n in page['components'] if n['type']=='Row')
        self.assertEqual(row['style']['layout']['padding_dp'],dict.fromkeys(('left','top','right','bottom'),12))
        parents = {n['id']:n for n in page['components']}
        ancestor = parents[row['parent_id']]
        while ancestor.get('slot_invocation'):
            ancestor = parents[ancestor['parent_id']]
        self.assertEqual(ancestor['type'],'Box')

    def test_content_factory_captures_delegated_state_and_forwards_record_list(self):
        _, page = self.page('Body(makeEntries(model))', '''
class Entry(val content: @Composable () -> Unit)
data class Section(val title: String, val topics: List<String>)
fun makeEntries(model: Model): List<Entry> {
    val state by model.collectAsStateWithLifecycle()
    return listOf(Entry { Sections(state) })
}
@Composable fun Body(entries: List<Entry>) { Box { entries[0].content() } }
@Composable fun Sections(title: String) {
    val sections = listOf(Section(title, listOf("One", "Two")))
    Column { sections.forEach { (heading, topics) ->
        Text(heading)
        topics.forEach { topic -> Text(topic) }
    } }
}
''', {'model':'Topics'})
        self.assertEqual(self.texts(page),['Topics','One','Two'])

    def test_custom_measurement_does_not_remove_forwarded_content(self):
        _, page = self.page('Custom { Text("Retained") }', '''
import androidx.compose.ui.layout.Layout
@Composable fun Custom(content: @Composable () -> Unit) {
    Layout(content = content) { measurables, constraints -> unsupportedMeasure() }
}
''')
        self.assertEqual(self.texts(page),['Retained'])
        text = next(n for n in page['components'] if n['type']=='Text')
        parent = next(n for n in page['components'] if n['id']==text['parent_id'])
        self.assertEqual(parent['type'],'Layout')

    def test_slot_local_delegate_is_evaluated_as_value_not_state_container(self):
        _, page = self.page('val entry = Entry { val title by model.collectAsStateWithLifecycle(); Text(title) }; Box { entry.content() }',
            'class Entry(val content: @Composable () -> Unit)', {'model':'Visible'})
        self.assertEqual(self.texts(page),['Visible'])


if __name__ == '__main__':
    unittest.main()
