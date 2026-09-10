import unittest

from analyze_compose_project import extract_semantic_ui_calls
from generate_lanhu_source_page import UNRESOLVED, evaluate_expression
import test_dp_size
import test_partial_page_generation
from generate_arkui_page import Renderer, derive_page_root


class UiIterationGapsTest(unittest.TestCase):
    def generate(self, body, values=None, declarations=''):
        helper = test_partial_page_generation.PartialPageGenerationTest()
        self.addCleanup(helper.doCleanups)
        page = test_dp_size.DpSizeTest().source_page(body, declarations)
        _, result, loaded = helper.generate_page(page, values)
        renderer = Renderer(derive_page_root(loaded), set(), {}, loaded)
        return page, loaded, renderer.render(), result

    def test_array_membership_and_index_keep_unknowns_unknown(self):
        for expression, expected in [
            ('arrayOf(0, 1, 2)', [0, 1, 2]),
            ('kotlin.arrayOf(0, 1, 2)[1]', 1),
            ('arrayOf<Int>().size', 0),
            ('page in arrayOf(0, 1, 2)', True),
            ('page !in arrayOf(0, 1, 2)', False),
        ]:
            with self.subTest(expression=expression):
                self.assertEqual(evaluate_expression(expression, {'page': 1}), expected)
        self.assertIs(evaluate_expression('missing in arrayOf(0, 1, 2)', {}), UNRESOLVED)
        self.assertIs(evaluate_expression('1 in arrayOf(missing)', {}), UNRESOLVED)

    def test_array_condition_selects_next_explore_and_previews_missing_page(self):
        body = 'Column { if (currentPage in arrayOf(0, 1, 2)) { Text("Next") } else { Text("Explore") } }'
        for current, expected in [(0, 'Next'), (2, 'Next'), (3, 'Explore')]:
            _, loaded, code, _ = self.generate(body, {'currentPage': current})
            self.assertEqual([n['style']['content']['text'] for n in loaded['components'] if n['type']=='Text'], [expected])
            self.assertIn("Text('" + expected + "')", code)
        _, loaded, code, result = self.generate(body)
        self.assertEqual(result['status'], 'partial_generation')
        self.assertIn("Text('Next')", code)
        self.assertFalse(result['state_projection']['selection_complete'])
        self.assertNotIn("Text('Explore')", code)

    def test_array_respects_imports_aliases_and_source_functions(self):
        self.assertEqual(evaluate_expression('valuesOf(1, 2)',
            {'__source_imports': {'valuesOf': 'kotlin.arrayOf'}}), [1, 2])
        self.assertIs(evaluate_expression('arrayOf(1, 2)',
            {'__source_imports': {'arrayOf': 'company.arrayOf'}}), UNRESOLVED)
        _, loaded, _, _ = self.generate('Column { Text(arrayOf(1).size.toString()) }', declarations='''
fun arrayOf(value: Int) = listOf(value, value, value)
''')
        self.assertEqual([n['style']['content']['text'] for n in loaded['components'] if n['type']=='Text'], ['3'])

    def test_repeat_scanner_binds_named_implicit_and_qualified_indices(self):
        for call, parameter in [
            ('repeat(count) { index -> Text(index.toString()) }', 'index'),
            ('repeat(times = count, action = { Text(it.toString()) })', 'it'),
            ('kotlin.repeat(count) { Text(it.toString()) }', 'it'),
        ]:
            with self.subTest(call=call):
                calls = extract_semantic_ui_calls('Page.kt', call, 'Page', call, 0, set(), {}, {})
                text = next(c for c in calls if c['component']=='Text')
                self.assertEqual(text['list_item_context']['collection'], 'count')
                self.assertEqual(text['list_item_context']['item_parameter'], parameter)
                self.assertTrue(text['list_item_context']['accepts_count'])

    def test_repeat_import_alias_and_shadowing_are_not_name_only(self):
        prefix = 'import kotlin.repeat as times\n'
        body = 'times(4) { Text(it.toString()) }'
        calls = extract_semantic_ui_calls('Page.kt', prefix + body, 'Page', body, len(prefix), set(), {}, {})
        self.assertEqual(next(c for c in calls if c['component']=='Text')['list_item_context']['collection'], '4')
        for prefix, body in [
            ('import company.repeat\n', 'repeat(4) { Text("Custom") }'),
            ('fun repeat(times: Int, action: () -> Unit) { action() }\n', 'repeat(4) { Text("Custom") }'),
            ('', 'val repeat = { count: Int -> count }; repeat(4) { Text("Custom") }'),
            ('', 'repeater.repeat(4) { Text("Custom") }'),
        ]:
            with self.subTest(prefix=prefix, body=body):
                calls = extract_semantic_ui_calls('Page.kt', prefix + body, 'Page', body, len(prefix), set(), {}, {})
                self.assertFalse(any(c.get('list_item_context') for c in calls))

    def test_repeat_emits_four_independent_dots_and_ordered_gaps(self):
        _, loaded, code, result = self.generate('''
val count = 4
val currentPage = 2
Row {
    repeat(count) { index ->
        Box(Modifier.size(8.dp).background(if (currentPage == index) Color.Red else Color.Black)) {}
        Spacer(Modifier.width(4.dp))
    }
    Text("Footer")
}''')
        nodes = loaded['components']
        dots = [n for n in nodes if n['type']=='Box']
        self.assertEqual(len(dots), 4)
        self.assertEqual([n['style']['surface']['background']['color'] for n in dots],
                         ['#FF000000', '#FF000000', '#FFFF0000', '#FF000000'])
        self.assertEqual([n['type'] for n in nodes], ['Row'] + ['Box', 'Spacer'] * 4 + ['Text'])
        self.assertEqual(len({n['id'] for n in nodes}), len(nodes))
        self.assertFalse(result['state_projection']['deferred_component_ids'])
        self.assertIn("Text('Footer')", code)
        self.assertEqual(code.count('.backgroundColor('), 4)

    def test_repeat_nested_scopes_and_adjacent_loops_do_not_merge(self):
        _, loaded, _, _ = self.generate('''Column {
repeat(2) { outer -> repeat(2) { inner -> Text("$outer:$inner") } }
repeat(2) { Text("after:$it") }
}''')
        self.assertEqual([n['style']['content']['text'] for n in loaded['components'] if n['type']=='Text'],
                         ['0:0', '0:1', '1:0', '1:1', 'after:0', 'after:1'])
        self.assertEqual(len(loaded['components']), len({n['id'] for n in loaded['components']}))

    def test_repeat_through_business_wrapper_binds_index_before_ui_branch(self):
        _, loaded, code, _ = self.generate('Column { Dots(4); Text("Footer") }', declarations='''
@Composable fun Dots(count: Int) {
    Row { repeat(count) { if (it == 2) { Text("Selected") } else { Text("Other") } } }
}
''')
        self.assertEqual([n['style']['content']['text'] for n in loaded['components'] if n['type']=='Text'],
                         ['Other', 'Other', 'Selected', 'Other', 'Footer'])
        self.assertIn("text3: 'Selected'", code)
        self.assertIn('Text(props.text3)', code)

    def test_repeat_zero_negative_and_unknown_counts_never_guess_one_item(self):
        for count in [0, -2]:
            _, loaded, _, _ = self.generate('Column { repeat(count) { Text("Dot") }; Text("Footer") }', {'count': count})
            self.assertEqual([n['style']['content']['text'] for n in loaded['components'] if n['type']=='Text'], ['Footer'])
        for values in [{}, {'count': 201}, {'count': True}, {'count': 2.5}]:
            _, loaded, code, result = self.generate('Column { repeat(count) { Text("Dot") }; Text("Footer") }', values)
            self.assertTrue(result['state_projection']['deferred_component_ids'])
            self.assertNotIn("Text('Dot')", code)
            self.assertIn("Text('Footer')", code)

    def test_repeat_early_return_is_not_silently_ignored(self):
        _, loaded, code, result = self.generate('''Column {
repeat(4) { if (it == 2) return@repeat; Text("Dot") }
Text("Footer")
}''')
        self.assertTrue(result['state_projection']['deferred_component_ids'])
        self.assertNotIn("Text('Dot')", code)
        self.assertIn("Text('Footer')", code)
        self.assertTrue(any('control transfer' in u['reason'] for n in loaded['components'] for u in n['unresolved']))

    def test_modifier_selector_named_like_local_remember_is_not_content(self):
        source, loaded, code, _ = self.generate('''
val focusRequester = remember { FocusRequester() }
Column { Text("Title", modifier = Modifier.focusRequester(focusRequester).padding(8.dp)) }
''')
        self.assertFalse(any(n.get('slot_invocation') for n in source['components']))
        self.assertEqual([n['type'] for n in loaded['components']], ['Column', 'Text'])
        text = next(n for n in loaded['components'] if n['type']=='Text')
        self.assertEqual(text['style']['layout']['padding_dp']['top'], 8)
        self.assertIn("Text('Title')", code)
        self.assertFalse(any(n['parent_id']==text['id'] for n in loaded['components']))


if __name__ == '__main__':
    unittest.main()
