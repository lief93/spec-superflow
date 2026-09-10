import unittest

import test_keyed_resources as helpers
from kotlin_psi import parse_expression
from ui_migration.frontend.api_adapters.keyed_resources import KeyedResourceAdapter
from ui_migration.frontend.api_adapters.registry import AdapterRegistry
from ui_migration.frontend.values import value_resolver
from ui_migration.semantics.expressions import LayoutExpressionError


EXTENSION = '''from ui_migration.frontend.api_adapters.keyed_resources import KeyedResourceAdapter
from ui_migration.frontend.component_reuse import ComponentAdapter
class Styles(KeyedResourceAdapter):
    def resolve(self, reference):
        if reference.symbol != 'company.Typography.body':
            return None
        return {'key':'body', 'target':{'module':'./ThemeBridge', 'export':'ThemeBridge',
                                      'member':'style', 'arguments':['body']}}
ADAPTERS = [Styles('styles', (), 'object', source_type='androidx.compose.ui.text.TextStyle',
    target_type={'module':'./ThemeBridge', 'export':'BusinessTextStyle'}).declaration()]
COMPONENT_ADAPTERS = [ComponentAdapter('caption', 'example.Caption', './Caption', 'Caption',
    parameters={'abc':'appearance'})]
'''


class ObjectResourceAdapterTest(unittest.TestCase):
    generate = helpers.KeyedResourcesTest.generate

    def test_object_passes_whole_to_reused_business_component(self):
        page, code, result, renderer = self.generate('Caption(company.Typography.body)',
            '@Composable fun Caption(abc: TextStyle) { Text("Source implementation") }',
            EXTENSION, source_imports='import androidx.compose.ui.text.TextStyle')
        self.assertIn('appearance: ReusedThemeBridge.style("body")', code)
        self.assertNotIn('Source implementation', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)
        value = next(n for n in page['components'] if n['type'] == 'Caption')['source']['component_reuse']['properties']['appearance']
        self.assertEqual(value['reference']['sourceType'], 'androidx.compose.ui.text.TextStyle')
        self.assertEqual(value['reference']['targetType']['export'], 'BusinessTextStyle')

    def test_unknown_object_is_not_accepted_by_native_text_style(self):
        _, code, result, _ = self.generate('Text("A", style = company.Typography.body)',
            extension=EXTENSION, source_imports='import androidx.compose.ui.text.TextStyle')
        self.assertNotIn('ThemeBridge.style', code)
        self.assertFalse(result['generation_complete'])

    def test_type_identity_not_short_name_selects_adapter(self):
        calls = []
        class Objects(KeyedResourceAdapter):
            def resolve(self, reference):
                calls.append(reference)
                return {'key':'value', 'target':{'module':'./Bridge', 'export':'Bridge', 'member':'value'}}
        registry = AdapterRegistry([Objects('objects', (), 'object', source_type='company.Model',
            target_type={'module':'./Bridge', 'export':'TargetModel'}).declaration()])
        resolver = value_resolver({}, {'__api_registry':registry, '__source_imports':{'Alias':'company.Model'}})
        self.assertEqual(resolver.typed_value(parse_expression('missing'), 'Alias')['reference']['kind'], 'object')
        with self.assertRaises(LayoutExpressionError):
            resolver.typed_value(parse_expression('missing'), 'other.Model')
        self.assertEqual(len(calls), 1)

    def test_getter_record_and_alias_preserve_whole_object(self):
        _, code, result, renderer = self.generate('Caption(style().appearance)', '''
@Composable fun Caption(abc: TS) { Text("Source implementation") }
data class Styles(val appearance: TS)
fun style() = Styles(Tokens.body)
object Tokens { val body: TS get() = company.Typography.body }
''', EXTENSION, source_imports='import androidx.compose.ui.text.TextStyle as TS')
        self.assertIn('appearance: ReusedThemeBridge.style("body")', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_unhandled_object_does_not_invent_a_target_value(self):
        _, code, result, _ = self.generate('Caption(other.body)',
            '@Composable fun Caption(abc: TextStyle) { Text("Source implementation") }',
            EXTENSION, source_imports='import androidx.compose.ui.text.TextStyle')
        self.assertNotIn('ReusedCaption(', code)
        self.assertIn('component parameter is unresolved', str(result['unresolved']))

    def test_object_type_and_target_metadata_are_validated(self):
        from ui_migration.contracts.resource_values import validate_resource_value
        for source, target in [('Model(); run()', {'module':'./Bridge', 'export':'Model'}),
                               ('Model', {'module':'./Bridge', 'export':'Model;run()'}),
                               ('Model', None)]:
            with self.subTest(source=source, target=target), self.assertRaises(ValueError):
                KeyedResourceAdapter('bad', (), 'object', source_type=source, target_type=target)
        with self.assertRaisesRegex(ValueError, 'sourceType/targetType/target'):
            validate_resource_value({'kind':'platform_resource_reference', 'key':'value',
                'reference':{'kind':'object', 'target':{'module':'./Bridge','export':'Bridge','member':'value'}}})


if __name__ == '__main__':
    unittest.main()
