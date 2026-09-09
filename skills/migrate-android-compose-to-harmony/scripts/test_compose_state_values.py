import unittest

from ui_migration.frontend.values import evaluate_expression
from ui_migration.frontend.page_model import UNRESOLVED
from test_source_callables import SourceCallablesTest


class ComposeStateValuesTest(unittest.TestCase):
    def test_remember_preserves_state_until_delegate_or_value_read(self):
        self.assertEqual(evaluate_expression('remember { mutableStateOf(false) }', {}), {'value': False})
        self.assertIs(evaluate_expression('run { val flag by remember { mutableStateOf(false) }; flag }', {}), False)
        self.assertEqual(evaluate_expression('run { val state = remember { mutableStateOf("expense") }; state.value }', {}), 'expense')

    def test_plain_remember_does_not_invent_a_state_wrapper(self):
        self.assertEqual(evaluate_expression('remember { "expense" }', {}), 'expense')
        self.assertIs(evaluate_expression('run { val flag by remember(1) { mutableStateOf(value = false) }; flag }', {}), False)

    def test_collection_state_and_flow_use_same_delegate_contract(self):
        self.assertEqual(evaluate_expression('run { val ids by remember { mutableStateOf(emptySet<Int>()) }; ids.isEmpty() }', {}), True)
        for api in ('collectAsState', 'collectAsStateWithLifecycle'):
            with self.subTest(api=api):
                self.assertEqual(evaluate_expression(f'run {{ val rows by model.{api}(); rows }}', {'model': ['A','B']}), ['A','B'])

    def test_missing_business_data_remains_unresolved(self):
        self.assertIs(evaluate_expression('run { val rows by model.collectAsState(); rows.isEmpty() }', {}), UNRESOLVED)
        self.assertIs(evaluate_expression('remember { mutableStateOf(repository.load()) }', {}), UNRESOLVED)

    def test_state_with_record_value_unwraps_only_once(self):
        self.assertEqual(evaluate_expression('run { val row by remember { mutableStateOf(record) }; row }',
                                            {'record': {'value': 'Business field'}}), {'value': 'Business field'})

    def test_default_category_state_selects_header_and_expands_rows(self):
        _, page = SourceCallablesTest().page('''
val categories by model.collectAsState()
var selectedCatType by remember { mutableStateOf("expense") }
var selectedIds by remember { mutableStateOf(emptySet<Int>()) }
var editOrder by remember { mutableStateOf(false) }
var displayed by remember { mutableStateOf(categories.filter { it.type == selectedCatType }) }
Column {
    AnimatedContent(targetState = selectedIds.isNotEmpty()) { selecting ->
        if (selecting) { Text("Selected") } else { Text("Categories") }
    }
    Text(if (editOrder) "Done" else "Edit Order")
    if (!displayed.isEmpty()) {
        displayed.forEach { category -> Text(category.name) }
    }
}
''', '''import androidx.compose.animation.AnimatedContent
import androidx.compose.runtime.*''', {'model':[
            {'name':'Shopping','type':'expense'}, {'name':'Salary','type':'income'},
            {'name':'Travel','type':'expense'}]})
        self.assertEqual(SourceCallablesTest().texts(page), ['Categories', 'Edit Order', 'Shopping', 'Travel'])


if __name__ == '__main__':
    unittest.main()
