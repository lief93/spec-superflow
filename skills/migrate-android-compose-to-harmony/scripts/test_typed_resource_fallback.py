import unittest
from pathlib import Path

from kotlin_psi import parse_expression
from ui_migration.frontend.api_adapters.keyed_resources import KeyedResourceAdapter
from ui_migration.frontend.api_adapters.registry import AdapterRegistry
from ui_migration.frontend.values import value_resolver
from ui_migration.semantics.expressions import LayoutDimension, LayoutExpressionError
import test_keyed_resources as helpers


EXTENSION = '''from ui_migration.frontend.api_adapters.keyed_resources import KeyedResourceAdapter
class Colors(KeyedResourceAdapter):
    def resolve(self, reference):
        assert reference.key is None
        assert reference.source_type == 'Color'
        assert reference.reason
        if reference.symbol != 'company.Theme.colors.spinner':
            return None
        return {'key': 'spinner', 'target': {'module': './ThemeBridge',
            'export': 'ThemeBridge', 'member': 'color', 'arguments': ['spinner']}}
ADAPTERS = [Colors('colors', (), 'color').declaration()]
'''


class TypedResourceFallbackTest(unittest.TestCase):
    generate = helpers.KeyedResourcesTest.generate

    def test_business_parameter_name_is_irrelevant(self):
        _, code, result, renderer = self.generate('Label(company.Theme.colors.spinner)', '''
@Composable fun Label(abc: Color) { Text("A", color = abc) }
''', EXTENSION)
        self.assertIn("color('spinner')", code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_getter_and_record_reach_terminal_library_expression(self):
        _, code, result, renderer = self.generate('Text("A", color = style().abc)', '''
data class ButtonStyle(val abc: Color)
fun style() = ButtonStyle(Tokens.value)
object Tokens { val value: Color get() = company.Theme.colors.spinner ?: Color.Black }
''', EXTENSION)
        self.assertIn("color('spinner') ?? \"#FF000000\"", code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_function_return_type_drives_fallback(self):
        _, code, result, _ = self.generate('Text("A", color = answer())', '''
fun answer(): Color = company.Theme.colors.spinner
''', EXTENSION)
        self.assertIn("color('spinner')", code)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_consumer_type_reaches_helper_without_return_annotation(self):
        _, code, result, _ = self.generate('Text("A", color = answer())', '''
fun answer() = intermediate()
fun intermediate() = company.Theme.colors.spinner
''', EXTENSION)
        self.assertIn("color('spinner')", code)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_consumer_type_reaches_inferred_cross_file_property(self):
        _, code, result, _ = self.generate('Text("A", color = Styles.value)', extension=EXTENSION,
            source_imports='import pieces.Styles', extra_files={'Styles.kt': '''package pieces
import company.Theme as T
object Styles { val value get() = T.colors.spinner }
'''})
        self.assertIn("color('spinner')", code)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_style_member_consumer_requests_adapter_without_object_mapping(self):
        _, code, result, _ = self.generate('Text("A", style = style())', '''
fun style() = TextStyle(color = company.Theme.colors.spinner, fontSize = 18.sp)
''', EXTENSION)
        self.assertIn("color('spinner')", code)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_documented_consumer_adapter_generates_without_object_mapping(self):
        example = Path(__file__).resolve().parents[1] / 'examples/object-properties/consumer_adapters.py'
        _, code, result, renderer = self.generate('''Column { Text("A",
            style = TextStyle(fontSize = captionSize(), color = captionColor())) }''', '''
fun captionSize() = company.theme.Dimensions.body
fun captionColor() = company.theme.Colors.body
''', example.read_text())
        self.assertIn(".fontSize(StyleToken0.fontSize('body'))", code)
        self.assertIn(".fontColor(StyleToken0.color('body'))", code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)
        self.assertEqual(renderer.test_phase_gate['verdict'], 'pass', renderer.test_phase_gate['failures'])

    def test_explicit_style_mapping_prevents_typed_adapter_dispatch(self):
        extension = EXTENSION.replace('assert reference.key is None',
            'raise AssertionError("explicit mapping must take priority")')
        _, code, result, _ = self.generate('Text("A", style = TextStyle(color = T.colors.spinner))',
            extension=extension, source_imports='import company.Theme as T', token_mappings={
                'company.Theme.colors.spinner': {'kind': 'color', 'target': {
                    'module': './Exact', 'export': 'Exact', 'member': 'spinner'}}})
        self.assertIn('.fontColor(StyleToken0.spinner)', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_known_wrong_value_does_not_invoke_adapter(self):
        extension = EXTENSION.replace('assert reference.key is None',
            'raise AssertionError("known values must not be coerced by an adapter")')
        _, code, result, _ = self.generate('Text("A", color = "not a color")', extension=extension)
        self.assertNotIn('ThemeBridge', code)
        self.assertFalse(result['generation_complete'])

    def test_arbitrary_declared_object_type_drives_helper_fallback(self):
        extension = '''from ui_migration.frontend.api_adapters.keyed_resources import KeyedResourceAdapter
from ui_migration.frontend.component_reuse import ComponentAdapter
class Values(KeyedResourceAdapter):
    def resolve(self, reference):
        assert reference.source_type == 'company.ChartAppearance'
        if reference.symbol != 'company.Themes.currentChart':
            return None
        return {'key':'chart', 'target':{'module':'./ChartBridge', 'export':'ChartBridge',
            'member':'appearance'}}
ADAPTERS = [Values('values', (), 'object', source_type='company.ChartAppearance',
    target_type={'module':'./ChartBridge', 'export':'ChartConfig'}).declaration()]
COMPONENT_ADAPTERS = [ComponentAdapter('chart', 'example.Chart', './Chart', 'Chart',
    parameters={'abc':'configuration'})]
'''
        _, code, result, _ = self.generate('Chart(getAppearance())', '''
fun getAppearance() = company.Themes.currentChart
@Composable fun Chart(abc: ChartAppearance) { Text("source") }
''', extension, source_imports='import company.ChartAppearance')
        self.assertIn('configuration: ReusedChartBridge.appearance', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_cross_file_getter_uses_declared_type_and_import_alias(self):
        _, code, result, renderer = self.generate('Text("A", color = make().abc)', extension=EXTENSION,
            source_imports='import pieces.style as make', extra_files={
                'Style.kt': 'package pieces\nimport tokens.Values\n'
                    'data class Style(val abc: Color)\nfun style() = Style(Values.value)',
                'Tokens.kt': 'package tokens\nimport androidx.compose.ui.graphics.Color as C\n'
                    'import company.Theme as T\nobject Values { val value: C get() = T.colors.spinner }'})
        self.assertIn("color('spinner')", code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_native_usage_type_drives_fallback_without_declaration(self):
        _, code, result, _ = self.generate('Text("A", color = company.Theme.colors.spinner)', extension=EXTENSION)
        self.assertIn("color('spinner')", code)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_none_keeps_diagnostic_and_target_default(self):
        page, code, result, _ = self.generate('Text("A", color = other.Theme.spinner)', extension=EXTENSION)
        self.assertNotIn('ThemeBridge', code)
        self.assertIn(".fontColor('#FF000000')", code)
        self.assertFalse(result['generation_complete'])
        self.assertTrue(page['generation_warnings'])

    def registry(self, kind='color', **kwargs):
        calls = []
        class Fallback(KeyedResourceAdapter):
            def resolve(self, reference):
                calls.append(reference)
                return {'key': 'runtime', 'target': {'module': './SystemBridge',
                    'export': 'SystemBridge', 'member': 'read', 'arguments': [reference.expression]}}
        return AdapterRegistry([Fallback('fallback', (), kind, **kwargs).declaration()]), calls

    def test_known_constants_and_system_context_take_priority(self):
        registry, calls = self.registry()
        resolver = value_resolver({}, {'__api_registry': registry, 'LocalContentColor.current': '#FF112233'})
        self.assertEqual(resolver.typed_value(parse_expression('Color.Red'), 'Color'), '#FFFF0000')
        self.assertEqual(resolver.typed_value(parse_expression('LocalContentColor.current'), 'Color'), '#FF112233')
        self.assertEqual(calls, [])

    def test_unknown_type_and_name_do_not_guess_color(self):
        registry, calls = self.registry()
        resolver = value_resolver({}, {'__api_registry': registry})
        for source_type in (None, 'Boolean', 'company.Color'):
            with self.assertRaises(LayoutExpressionError):
                resolver.typed_value(parse_expression('colorValue'), source_type)
        self.assertEqual(calls, [])
        resolver.values['__source_imports'] = {'Color': 'company.Color'}
        with self.assertRaises(LayoutExpressionError):
            resolver.typed_value(parse_expression('value'), 'Color')
        self.assertEqual(calls, [])

    def test_prior_unresolved_value_does_not_prevent_typed_retry(self):
        from ui_migration.frontend.values import evaluate_expression, UNRESOLVED
        registry, calls = self.registry()
        value = evaluate_expression('abc', {'__api_registry': registry, 'abc': UNRESOLVED}, source_type='Color')
        self.assertEqual(value['kind'], 'platform_resource_reference')
        self.assertEqual(calls[0].expression, 'abc')

    def test_system_dimension_uses_same_interface_and_keeps_units(self):
        registry, calls = self.registry('dimension', source_unit='dp', target_unit='vp')
        resolver = value_resolver({}, {'__api_registry': registry})
        value = resolver.typed_value(parse_expression('system.statusBarHeight()'), 'Dp')
        self.assertEqual(value['reference']['sourceUnit'], 'dp')
        self.assertEqual(value['reference']['targetUnit'], 'vp')
        self.assertEqual(calls[0].expression, 'system.statusBarHeight()')
        self.assertIsNone(calls[0].key)
        resolver.values['system.statusBarHeight()'] = LayoutDimension(24, 'dp')
        self.assertEqual(resolver.typed_value(parse_expression('system.statusBarHeight()'), 'Dp'), LayoutDimension(24, 'dp'))
        self.assertEqual(len(calls), 1)
        with self.assertRaises(LayoutExpressionError):
            resolver.typed_value(parse_expression('system.statusBarHeight() + missing'), 'TextUnit')

    def test_selected_branch_only_and_unknown_condition_is_not_guessed(self):
        registry, calls = self.registry()
        resolver = value_resolver({}, {'__api_registry': registry})
        resolver.typed_value(parse_expression('if (false) unused else picked'), 'Color')
        self.assertEqual([c.expression for c in calls], ['picked'])
        expression = 'if (flag) first else second'
        resolver.typed_value(parse_expression(expression), 'Color')
        self.assertEqual(calls[-1].expression, expression)

    def test_same_type_adapters_try_in_order_until_resolved(self):
        registry, calls = self.registry()
        attempts = []
        class Declines(KeyedResourceAdapter):
            def resolve(self, reference):
                attempts.append(reference.expression)
                return None
        other = Declines('first', ('company.known',), 'color').declaration()
        registry = AdapterRegistry([other, *registry.adapters,
            Declines('last', (), 'color').declaration()])
        resolver = value_resolver({}, {'__api_registry': registry})
        value = resolver.typed_value(parse_expression('company.unknown'), 'Color')
        self.assertEqual(value['kind'], 'platform_resource_reference')
        self.assertEqual(attempts, ['company.unknown'])
        self.assertEqual(len(calls), 1)

    def test_explicit_symbol_wins_before_type_fallback(self):
        registry, calls = self.registry()
        class Exact(KeyedResourceAdapter):
            def harmony_target(self, key, arguments):
                return {'module': './Exact', 'export': 'Exact', 'member': 'color'}
        registry = AdapterRegistry([*registry.adapters, Exact('exact', ('company.Theme.*',), 'color').declaration()])
        resolver = value_resolver({}, {'__api_registry': registry})
        value = resolver.typed_value(parse_expression('company.Theme.primary'), 'Color')
        self.assertEqual(value['reference']['target']['module'], './Exact')
        self.assertEqual(calls, [])

    def test_explicit_style_mapping_wins_before_type_fallback(self):
        from ui_migration.frontend.style_tokens import StyleTokenProjector
        registry, calls = self.registry()
        spec = {'kind':'color', 'target':{'module':'./Exact', 'export':'Exact', 'member':'color'}}
        projector = StyleTokenProjector({'tokenMappings': {'company.Theme.primary': spec}})
        original = {'type':'Text', 'arguments': {'semantic': {'color': {'expression':'T.primary'}}}}
        result = {'style': {'state': {}, 'typography': {'color': None}}}
        projector.apply(original, result, {'__api_registry':registry, '__source_imports': {'T':'company.Theme'}})
        self.assertEqual(result['source']['style_token_references']['typography.color']['target']['module'], './Exact')
        self.assertEqual(calls, [])

    def test_cyclic_bindings_do_not_get_hidden_by_fallback(self):
        registry, calls = self.registry()
        resolver = value_resolver({'a': 'b', 'b': 'a'}, {'__api_registry': registry})
        with self.assertRaisesRegex(LayoutExpressionError, 'cyclic'):
            resolver.typed_value(parse_expression('a'), 'Color')
        self.assertEqual(calls, [])

    def test_system_text_unit_reference_survives_full_generation(self):
        extension = '''from ui_migration.frontend.api_adapters.keyed_resources import KeyedResourceAdapter
class Sizes(KeyedResourceAdapter):
    def resolve(self, reference):
        assert reference.source_type == 'TextUnit'
        if reference.symbol != 'system.captionSize':
            return None
        return {'key':'caption', 'target':{'module':'./SystemBridge', 'export':'SystemBridge',
            'member':'captionSize'}}
ADAPTERS = [Sizes('sizes', (), 'dimension', source_unit='sp', target_unit='fp').declaration()]
'''
        page, code, result, renderer = self.generate('Text("A", fontSize = caption(), color = Color.Black)',
            'fun caption(): TextUnit = system.captionSize()', extension)
        self.assertIn('.fontSize(StyleToken0.captionSize)', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)
        self.assertEqual(renderer.test_phase_gate['verdict'], 'pass', renderer.test_phase_gate)


if __name__ == '__main__':
    unittest.main()
