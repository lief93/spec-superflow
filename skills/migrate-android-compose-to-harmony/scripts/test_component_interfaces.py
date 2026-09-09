import unittest
import json
import copy

from test_business_components import compile_page
from ui_migration.contracts.component_interfaces import signature, value_matches


class ComponentInterfacesTest(unittest.TestCase):
    def test_unused_business_and_state_parameters_are_retained_in_original_order(self):
        _, _, page, renderer, code = compile_page('''
@Composable fun Page() { Card("Account", 5, true) }
@Composable fun Card(title: String, accountId: Int, loading: Boolean) { Text(title) }
''')
        self.assertIn('private Card(title: string, accountId: number, loading: boolean)', code)
        self.assertIn('this.Card("Account", 5, true)', code)
        parameters = next(n for n in page['components'] if n['type']=='Card')['source']['component_interface']['parameters']
        self.assertEqual([(p['name'],p['kotlin_type'],p['target_type']) for p in parameters],
                         [('title','String','string'),('accountId','Int','number'),('loading','Boolean','boolean')])
        self.assertEqual(renderer.business_components.report()['declared_interfaces'][0]['name'], 'Card')

    def test_current_state_values_do_not_choose_parameter_types(self):
        _, _, _, _, code = compile_page('''
@Composable fun Page() { Component(null, listOf("A"), false) }
@Composable fun Component(title: String?, values: List<String>, selected: Boolean) { Text("Known") }
''')
        self.assertIn('private Component(title: (string) | null, values: ReadonlyArray<string>, selected: boolean)', code)
        self.assertIn('this.Component(null, ["A"], false)', code)

    def test_business_callback_keeps_its_function_signature_even_when_unused(self):
        _, _, _, _, code = compile_page('''
@Composable fun Page() { Action("Open", {}) }
@Composable fun Action(title: String, onClick: () -> Unit) { Text(title) }
''')
        self.assertIn('private Action(title: string, onClick: () => void)', code)
        self.assertIn('this.Action("Open", () => {})', code)

    def test_unknown_nominal_type_is_not_replaced_with_any_or_string(self):
        _, _, page, renderer, code = compile_page('''
@Composable fun Page() { Content(unknownAccount) }
@Composable fun Content(account: Account) { Text("Preview remains") }
''')
        self.assertIn('Preview remains', code)
        self.assertNotIn('account: any', code)
        self.assertNotIn('account: string', code)
        self.assertNotIn('private Content(', code)
        record = next(n for n in page['components'] if n['type']=='Content')['source']['component_interface']
        self.assertEqual(record['parameters'][0]['kotlin_type'], 'Account')
        self.assertEqual(record['parameters'][0]['status'], 'unresolved')
        self.assertTrue(any('source.component_interface.account' in str(u) for u in renderer.unresolved))

    def test_nested_calls_forward_unused_numeric_and_boolean_parameters(self):
        _, _, _, _, code = compile_page('''
@Composable fun Page() { Outer("One", 42, true) }
@Composable fun Outer(title: String, id: Int, loading: Boolean) { Inner(title, id, loading) }
@Composable fun Inner(label: String, accountId: Int, loading: Boolean) { Text(label) }
''')
        self.assertIn('private Outer(title: string, id: number, loading: boolean)', code)
        self.assertIn('private Inner(label: string, accountId: number, loading: boolean)', code)
        self.assertIn('this.Inner(props.title, props.id, props.loading)', code)
        self.assertIn('id: id', code)
        self.assertIn('loading: loading', code)

    def test_multiple_observed_states_keep_both_bodies_and_one_typed_interface(self):
        _, _, _, _, code = compile_page('''
@Composable fun Page() { Column { Status(true); Status(false) } }
@Composable fun Status(loading: Boolean) { if(loading) { Text("Loading") } else { Text("Done") } }
''')
        self.assertEqual(code.count('private Status(loading: boolean)'), 1)
        self.assertIn('Loading', code)
        self.assertIn('Done', code)
        self.assertIn('loading === true', code)
        self.assertIn('loading === false', code)

    def test_state_dispatch_does_not_freeze_unrelated_text_parameters(self):
        _, _, _, _, code = compile_page('''
@Composable fun Page() { Column { Status(true, "A"); Status(false, "B") } }
@Composable fun Status(loading: Boolean, title: String) { if(loading) { Text(title) } else { Text("Done") } }
''')
        self.assertIn('loading === true', code)
        self.assertIn('loading === false', code)
        self.assertNotIn('title ===', code)

    def test_collection_state_not_dispatchable_retains_both_previews_with_diagnostic(self):
        _, _, _, renderer, code = compile_page('''
@Composable fun Page() { Column { Labels(listOf("A")); Labels(listOf("B", "C")) } }
@Composable fun Labels(values: List<String>) { Column { values.forEach { Text(it) } } }
''')
        for text in ("'A'", "'B'", "'C'"):
            self.assertIn(text, code)
        self.assertTrue(any('cannot be distinguished' in str(u) for u in renderer.unresolved))
        self.assertNotIn('private Labels(values: ReadonlyArray<string>) {\n  }', code)

    def test_nonempty_business_callback_is_not_replaced_by_noop(self):
        _, _, _, renderer, code = compile_page('''
@Composable fun Page() { Action("Open", { submit() }) }
@Composable fun Action(title: String, onClick: () -> Unit) { Text(title) }
''')
        self.assertIn('private Action(title: string, onClick: () => void)', code)
        self.assertNotIn('this.Action("Open", () => {})', code)
        self.assertTrue(any('component_interface.onClick' in str(u) for u in renderer.unresolved))

    def test_nullable_callback_and_collection_types_are_structural(self):
        types = signature([{'name':'callback','type':'((value: Int, label: String?) -> Boolean)?'},
                           {'name':'values','type':'List<List<Int?>>'},
                           {'name':'unsupported','type':'Long'}])
        self.assertEqual(types[0]['target_type'], '((value: number, label: (string) | null) => boolean) | null')
        self.assertEqual(types[1]['target_type'], 'ReadonlyArray<ReadonlyArray<(number) | null>>')
        self.assertEqual(types[2]['status'], 'unresolved')
        self.assertEqual(json.loads(json.dumps(types)), types)

    def test_parameterized_nullable_callback_survives_json_roundtrip(self):
        _, _, _, renderer, code = compile_page('''
@Composable fun Page() { Consumer(null) }
@Composable fun Consumer(callback: ((Int, String?) -> Boolean)?) { Text("Known") }
''')
        self.assertIn('private Consumer(callback: ((arg0: number, arg1: (string) | null) => boolean) | null)', code)
        self.assertIn('this.Consumer(null)', code)
        self.assertFalse(any('component_interface' in str(u) for u in renderer.unresolved))

    def test_consumer_rejects_signature_corruption_and_missing_call_arguments(self):
        _, _, page, renderer, _ = compile_page('''
@Composable fun Page() { Card("Title", true) }
@Composable fun Card(title: String, loading: Boolean) { Text(title) }
''')
        node = next(n for n in page['components'] if n['type'] == 'Card')
        definition = renderer.business_components.definitions[node['definition_id']]
        wrong = copy.deepcopy(node)
        wrong['source']['component_interface']['parameters'][1]['target_type'] = 'string'
        with self.assertRaisesRegex(ValueError, 'does not match source declaration'):
            renderer.business_components.interfaces.contract(wrong, definition)
        missing = copy.deepcopy(node)
        missing['source']['component_interface']['arguments'].pop()
        with self.assertRaisesRegex(ValueError, 'every declared argument'):
            renderer.business_components.interfaces.contract(missing, definition)

    def test_source_numeric_types_are_not_inferred_from_values(self):
        integer = signature([{'name':'id', 'type':'Int'}])[0]['type']
        self.assertTrue(value_matches(42, integer))
        for value in (True, '42', 42.5, 2**40, None):
            self.assertFalse(value_matches(value, integer))

    def test_default_argument_is_retained_and_materialized_without_changing_signature(self):
        _, _, page, _, code = compile_page('''
@Composable fun Page() { Caption() }
@Composable fun Caption(title: String = "Default", enabled: Boolean = true) { Text(title) }
''')
        self.assertIn('private Caption(title: string, enabled: boolean)', code)
        self.assertIn('this.Caption("Default", true)', code)
        record = next(n for n in page['components'] if n['type'] == 'Caption')['source']['component_interface']
        self.assertEqual([p['default_expression'] for p in record['parameters']], ['"Default"', 'true'])


if __name__ == '__main__':
    unittest.main()
