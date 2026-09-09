import unittest

import test_dp_size
from generate_lanhu_source_page import project_source_page


class SourceUiCompletenessTest(unittest.TestCase):
    def source(self, body, definitions):
        return test_dp_size.DpSizeTest().source_page(body, definitions)

    def selected(self, source, values=None):
        return project_source_page(source, {'schema':'android-to-harmony.page-state-fixture.v1',
            'page':source['page'], 'values':values or {}}, allow_unresolved=True)[0]

    def test_project_component_can_share_framework_name(self):
        source = self.source('TopAppBar("News")', '''
@Composable fun TopAppBar(title: String) { Row { Text(title) } }
''')
        wrapper = next(n for n in source['components'] if n['type']=='TopAppBar')
        self.assertTrue(wrapper['source']['custom_component'])
        page = self.selected(source)
        self.assertEqual([n['style']['content']['text'] for n in page['components'] if n['type']=='Text'], ['News'])

    def test_non_composable_lazy_builder_keeps_all_content_and_list_instances(self):
        source = self.source('LazyColumn { articleRows(entries) }', '''
fun LazyListScope.articleRows(values: List<String>) {
    item { Text("Header") }
    items(values) { entry -> Text(entry) }
    item { Text("Footer") }
}
''')
        page = self.selected(source, {'entries':['One','Two','Three']})
        self.assertEqual([n['style']['content']['text'] for n in page['components'] if n['type']=='Text'],
                         ['Header','One','Two','Three','Footer'])

    def test_nested_slot_forwarding_retains_scaffold_slot_and_parent(self):
        source = self.source('Shell(header = { Text("Heading") }, footer = { Row { Text("Action") } })', '''
@Composable fun Shell(header: @Composable () -> Unit, footer: @Composable () -> Unit) {
    Inner(top = header, bottom = footer)
}
@Composable fun Inner(top: @Composable () -> Unit, bottom: @Composable () -> Unit) {
    Scaffold(topBar = top, bottomBar = bottom) { Text("Body") }
}
''')
        self.assertFalse(source['unresolved'], source['unresolved'])
        nodes = {n['id']:n for n in source['components']}
        for text, slot in [('Heading','topBar'),('Action','bottomBar')]:
            n = next(n for n in nodes.values() if n['style']['content']['text']==text)
            while nodes[n['parent_id']]['type'] != 'Scaffold':
                n = nodes[n['parent_id']]
            self.assertEqual(n['slot_argument_name'],slot)

    def test_local_ui_function_wins_over_imported_model_constructor(self):
        source = self.source('Paragraph(value = "Body")', '''
import sample.model.Paragraph
@Composable fun Paragraph(value: String) { Text(value) }
''')
        self.assertTrue(any(n['type']=='Text' for n in source['components']))

    def test_value_composable_is_evaluated_not_emitted_as_ui(self):
        source = self.source('''val (height, label) = style(false)
Box(Modifier.height(height)) { Text(label) }''', '''
data class Styling(val height: Dp, val label: String)
@Composable fun style(large: Boolean): Styling {
    var height = 24.dp
    if (large) { height = 80.dp }
    return Styling(height, "Body")
}
''')
        self.assertFalse(any(n['type']=='style' for n in source['components']))
        page = self.selected(source)
        box = next(n for n in page['components'] if n['type']=='Box')
        self.assertEqual(box['style']['layout']['height_dp'],24)
        self.assertEqual(next(n for n in page['components'] if n['type']=='Text')['style']['content']['text'],'Body')

    def test_bottom_bar_keeps_action_container_and_default_size(self):
        from test_layout_mapping_contract import render_nodes
        source = self.source('Scaffold(bottomBar = { BottomAppBar(actions = { IconButton(onClick = {}) { Text("A") } }) }) { Text("Body") }','')
        page = self.selected(source)
        bar = next(n for n in page['components'] if n['type']=='BottomAppBar')
        self.assertEqual(bar['slot_argument_name'],'bottomBar')
        output, _, _ = render_nodes(page['components'])
        self.assertIn('.height(this.layoutPx(80))',output)
        self.assertIn('.layoutGravity(LocalizedAlignment.BOTTOM)',output)

    def test_annotated_text_and_scaffold_padding_survive_projection(self):
        source = self.source('''Scaffold(topBar = { Text("Bar") }) { insets ->
LazyColumn(contentPadding = insets, modifier = Modifier.padding(horizontal = 16.dp)) {
item { Text(AnnotatedString("Body")) }
} }''','')
        page = self.selected(source)
        text = next(n for n in page['components'] if n['type']=='Text' and n['style']['content']['text']=='Body')
        self.assertNotIn('annotated_string',text['style']['content']['text'])
        row = next(n for n in page['components'] if n['type']=='LazyColumn')
        self.assertEqual(row['style']['layout']['padding_dp']['left'],16)
        self.assertEqual(row['source']['scaffold_padding']['edges']['top'],'topBar')

    def test_enum_selects_one_branch_and_extension_reads_receiver_fields(self):
        source = self.source('''when (entry.type) {
Kind.Main -> Text(entry.label())
else -> Text("Other")
}''','''enum class Kind { Main, Other }
data class Entry(val type: Kind, val title: String)
fun Entry.label(): String = title
''')
        page = self.selected(source, {'entry':{'type':'Kind.Main','title':'Actual'}})
        self.assertEqual([n['style']['content']['text'] for n in page['components'] if n['type']=='Text'],['Actual'])

    def test_android_string_resource_escapes_are_not_displayed_literally(self):
        from ui_migration.frontend.resources import resource_values
        values = resource_values({'ui':{'android_value_resource_inventory':{'resources':[
            {'type':'string','name':'title','value':r'Published\n%1$s','qualifier':'values'}]}}})
        self.assertEqual(values['string','title'],'Published\n%1$s')


if __name__ == '__main__': unittest.main()
