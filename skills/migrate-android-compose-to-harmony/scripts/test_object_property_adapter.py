from pathlib import Path
import unittest
import copy
from kotlin_psi import parse_expression
from ui_migration.frontend.api_adapters.keyed_resources import KeyedResourceAdapter
from ui_migration.frontend.api_adapters.registry import AdapterRegistry
from ui_migration.frontend.values import value_resolver
from ui_migration.semantics.expressions import LayoutExpressionError

import test_keyed_resources as helpers


EXAMPLE = Path(__file__).resolve().parents[1] / 'examples/object-properties/project_adapters.py'


class ObjectPropertyAdapterTest(unittest.TestCase):
    generate = helpers.KeyedResourcesTest.generate

    def test_owner_mapping_applies_multiple_tokens_to_native_text(self):
        page, code, result, renderer = self.generate('''Column {
            Text("Body", style = Tokens.body)
            Text("Title", style = Tokens.title, fontSize = 20.sp)
        }''', extension=EXAMPLE.read_text(),
            source_imports='import company.theme.TypographyTokens as Tokens')
        self.assertIn(".fontSize(StyleToken0.fontSize('body'))", code)
        self.assertIn(".fontWeight(StyleToken0.fontWeight('title'))", code)
        self.assertIn(".fontColor(StyleToken0.color('body'))", code)
        self.assertIn(".lineHeight(StyleToken0.lineHeight('title'))", code)
        self.assertNotIn("fontSize('title')", code)
        self.assertIn('.fontSize(20)', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)
        self.assertEqual(renderer.test_phase_gate['verdict'], 'pass', renderer.test_phase_gate)

    def test_arbitrary_object_members_and_nested_objects_are_explicit(self):
        class Objects(KeyedResourceAdapter):
            def resolve(self, reference):
                if reference.symbol != 'company.Models.active':
                    return None
                target = {'module': './Models', 'export': 'Models', 'member': 'active'}
                return {'key': 'active', 'target': target, 'properties': {
                    'abc': {'kind': 'color', 'target': {**target, 'member': 'active.spinnerTint'}},
                    'details': {'kind': 'object', 'sourceType': 'company.Details',
                        'targetType': {'module': './Models', 'export': 'Details'},
                        'target': {**target, 'member': 'active.info'}, 'properties': {
                            'caption': {'kind': 'string', 'target': {**target, 'member': 'active.info.title'}}}},
                }}
        registry = AdapterRegistry([Objects('objects', ('company.Models.*',), 'object',
            source_type='company.Model', target_type={'module': './Models', 'export': 'Model'}).declaration()])
        resolver = value_resolver({'local': 'company.Models.active'}, {'__api_registry': registry})
        self.assertEqual(resolver.value(parse_expression('local.abc'))['reference']['target']['member'],
                         'active.spinnerTint')
        self.assertEqual(resolver.value(parse_expression('local.details.caption'))['reference']['target']['member'],
                         'active.info.title')
        for expression in ('local.missing', 'local.kind', 'local.key', 'local.reference'):
            with self.subTest(expression=expression), self.assertRaises(LayoutExpressionError):
                resolver.value(parse_expression(expression))

    def test_getter_and_record_forward_object_and_read_properties(self):
        _, code, result, renderer = self.generate('''Column {
            Text("Style", style = wrapper().appearance)
            Text("Size", fontSize = wrapper().appearance.fontSize,
                 color = wrapper().appearance.color)
        }''', '''
data class Appearance(val appearance: TS)
fun wrapper() = Appearance(LocalStyles.body)
object LocalStyles { val body: TS get() = Tokens.body }
''', EXAMPLE.read_text(), source_imports='''import androidx.compose.ui.text.TextStyle as TS
import company.theme.TypographyTokens as Tokens''')
        self.assertEqual(code.count(".fontSize(StyleToken0.fontSize('body'))"), 2)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_copy_and_explicit_arguments_override_object_members(self):
        page, code, result, _ = self.generate('''Text("A",
            style = Tokens.body.copy(fontSize = 22.sp, color = Color.Red),
            fontSize = 24.sp, fontWeight = FontWeight.Bold)''', extension=EXAMPLE.read_text(),
            source_imports='import company.theme.TypographyTokens as Tokens')
        self.assertIn('.fontSize(24)', code)
        self.assertIn('.fontWeight(700)', code)
        self.assertIn(".fontColor('#FFFF0000')", code)
        self.assertNotIn("fontSize('body')", code)
        self.assertNotIn("fontWeight('body')", code)
        self.assertNotIn("color('body')", code)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_source_text_style_getter_can_read_mapped_object_properties(self):
        _, code, result, _ = self.generate('Text("A", style = localStyle())', '''
fun localStyle() = TextStyle(fontSize = Tokens.body.fontSize, color = Tokens.body.color)
''', EXAMPLE.read_text(), source_imports='''import androidx.compose.ui.text.TextStyle
import company.theme.TypographyTokens as Tokens''')
        self.assertIn(".fontSize(StyleToken0.fontSize('body'))", code)
        self.assertIn(".fontColor(StyleToken0.color('body'))", code)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_business_object_with_arbitrary_field_names_generates_native_values(self):
        extension = EXAMPLE.read_text().replace('androidx.compose.ui.text.TextStyle', 'company.Appearance')
        extension = extension.replace("'fontSize': dimension('fontSize')", "'xyz': dimension('fontSize')")
        extension = extension.replace("'color': {'kind': 'color'", "'abc': {'kind': 'color'")
        _, code, result, _ = self.generate('''Text("A", color = getAppearance().abc,
            fontSize = getAppearance().xyz)''',
            'fun getAppearance(): Appearance = Tokens.body', extension,
            source_imports='''import company.Appearance
import company.theme.TypographyTokens as Tokens''')
        self.assertIn(".fontColor(StyleToken0.color('body'))", code)
        self.assertIn(".fontSize(StyleToken0.fontSize('body'))", code)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_whole_object_still_passes_to_reused_component(self):
        extension = EXAMPLE.read_text() + '''
from ui_migration.frontend.component_reuse import ComponentAdapter
COMPONENT_ADAPTERS = [ComponentAdapter('caption', 'example.Caption', './Caption', 'Caption',
    parameters={'appearance':'appearance'})]
'''
        _, code, result, _ = self.generate('Caption(Tokens.body)',
            '@Composable fun Caption(appearance: TextStyle) { Text("source") }', extension,
            source_imports='''import androidx.compose.ui.text.TextStyle
import company.theme.TypographyTokens as Tokens''')
        self.assertIn('appearance: ReusedProjectTypography.getStyle("body")', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_declined_owner_does_not_guess_token_key(self):
        _, code, result, _ = self.generate('Text("A", style = other.TypographyTokens.body)',
            extension=EXAMPLE.read_text())
        self.assertNotIn('ProjectTypography', code)
        self.assertFalse(result['generation_complete'])
        self.assertIn('unsupported text style expression', str(result['unresolved']))

    def test_typed_fallback_needs_no_per_token_symbols(self):
        extension = EXAMPLE.read_text().replace("('company.theme.TypographyTokens.*',)", '()')
        _, code, result, _ = self.generate('Text("A", style = Tokens.newToken)',
            extension=extension, source_imports='import company.theme.TypographyTokens as Tokens')
        self.assertIn("fontSize('newToken')", code)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_wrong_native_property_type_stays_diagnostic(self):
        extension = EXAMPLE.read_text().replace("'fontSize': dimension('fontSize')",
            "'fontSize': {'kind': 'color', 'target': target('color')}")
        _, code, result, _ = self.generate('Text("A", style = Tokens.body)', extension=extension,
            source_imports='import company.theme.TypographyTokens as Tokens')
        self.assertNotIn(".fontSize(StyleToken0.color", code)
        self.assertFalse(result['generation_complete'])
        self.assertIn('does not match', str(result['unresolved']))

    def test_malformed_member_mappings_are_rejected(self):
        from ui_migration.contracts.resource_values import validate_resource_value
        target = {'module': './Bridge', 'export': 'Bridge', 'member': 'value'}
        base = {'kind': 'platform_resource_reference', 'key': 'body', 'reference': {
            'kind': 'object', 'sourceType': 'company.Model',
            'targetType': {'module': './Bridge', 'export': 'Model'}, 'target': target}}
        for properties in ([], {'a.b': {'kind': 'color', 'target': target}},
                           {'size': {'kind': 'dimension', 'sourceUnit': 'dp', 'targetUnit': 'fp', 'target': target}},
                           {'abc': {'kind': 'color', 'target': {**target, 'member': 'value();bad'}}}):
            value = copy.deepcopy(base)
            value['reference']['properties'] = properties
            with self.subTest(properties=properties), self.assertRaises(ValueError):
                validate_resource_value(value)


if __name__ == '__main__':
    unittest.main()
