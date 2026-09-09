import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from kotlin_psi import parse_expression
from ui_migration.frontend.page_model import UNRESOLVED
from ui_migration.frontend.values import value_resolver
from ui_migration.frontend.api_adapters.registry import ApiAdapter, AdapterRegistry, AdapterConflict
from ui_migration.frontend.api_adapters.loader import load_adapters
from ui_migration.semantics.expressions import LayoutExpressionError


class ApiAdaptersTest(unittest.TestCase):
    def test_string_resource_formats_indexed_arguments_and_literal_percent(self):
        resolver = value_resolver({}, {'R.string.read': '%1$s - %2$d min read (100%%)',
                                     'post': {'name': 'Alice', 'minutes': 5}})
        self.assertEqual(resolver.value(parse_expression(
            'stringResource(id = R.string.read, post.name, post.minutes)')),
            'Alice - 5 min read (100%)')
        with self.assertRaises(LayoutExpressionError):
            resolver.value(parse_expression('stringResource(R.string.read, post.name)'))

    def test_typed_chain_does_not_evaluate_receivers_repeatedly(self):
        calls = []
        def start(call, ctx, seen):
            calls.append('start')
            return {'kind': 'sample', 'value': 0}
        def step(call, ctx, seen):
            calls.append('step')
            return {'kind': 'sample', 'value': ctx.receiver['value'] + 1}
        registry = AdapterRegistry([
            ApiAdapter('start', 'size', ('sample.start',), start),
            ApiAdapter('step', 'size', ('step',), step, receiver_kind='sample')])
        value = value_resolver({}, {'__api_registry': registry}).value(parse_expression('sample.start().step().step().step()'))
        self.assertEqual(value['value'], 3)
        self.assertEqual(calls, ['start', 'step', 'step', 'step'])

    def test_typed_members_share_dispatch_without_overlapping_copy(self):
        resolver = value_resolver({}, {})
        self.assertEqual(resolver.value(parse_expression('Color(0xFF112233).copy(alpha = 0.5f)')), '#80112233')
        style = resolver.value(parse_expression('TextStyle(fontSize = 12.sp).copy(fontSize = 18.sp)'))
        self.assertEqual(style['properties']['fontSize'], '18.sp')
        self.assertEqual(resolver.value(parse_expression('Color(0xFFFFFFFF).toArgb()')), -1)

    def test_image_request_uses_typed_chain_and_import_alias(self):
        resolver = value_resolver({}, {'__source_imports': {'Request': 'coil.request.ImageRequest'}})
        self.assertEqual(resolver.value(parse_expression('Request.Builder(context).data("photo").build()')), 'photo')
        self.assertEqual(resolver.value(parse_expression('Request.Builder(context).data("photo").crossfade(true).build()')), 'photo')
        with self.assertRaises(LayoutExpressionError):
            resolver.value(parse_expression('Request.Builder(context).build()'))

    def test_forbidden_output_is_rejected_separately_from_context_mutation(self):
        for value in ({'bbox': [0, 0, 1, 1]}, {'visible': False}, float('nan')):
            registry = AdapterRegistry([ApiAdapter('bad', 'image', ('test.bad',), lambda *args: value)])
            with self.assertRaises(ValueError):
                registry.evaluate(parse_expression('test.bad()'), value_resolver({}, {}), ())

    def test_project_adapter_reaches_page_surface_without_generator_changes(self):
        from test_ui_state_semantics import UiStateSemanticsTest
        from ui_migration.frontend.fixed_state import project_source_page
        from ui_migration.frontend.api_adapters.builtins import BUILTIN_ADAPTERS
        source = UiStateSemanticsTest().source('Box(Modifier.size(48.dp).background(company.fill())) { Text("Body") }')
        registry = AdapterRegistry([*BUILTIN_ADAPTERS, ApiAdapter('company.fill', 'background',
            ('company.fill',), lambda *args: {'kind': 'linear_brush', 'colors': ['#FF112233', '#FF445566'], 'axis': 'horizontal'})])
        result, _ = project_source_page(source, {'schema': 'android-to-harmony.page-state-fixture.v1',
            'page': source['page'], 'values': {}}, api_registry=registry)
        box = next(n for n in result['components'] if n['type'] == 'Box')
        self.assertEqual(box['style']['surface']['background'], {'type': 'linear_gradient',
            'colors': ['#FF112233', '#FF445566'], 'angle_degrees': 90, 'tile_mode': 'clamp'})
        self.assertTrue(any(n['type'] == 'Text' for n in result['components']))

    def test_scan_separates_api_gap_from_state_and_never_executes_source(self):
        from ui_migration.frontend.api_adapters.scan import scan_source_page
        page = {'components': [{'id': 'image', 'source': {'source': 'Page.kt', 'composable': 'Page', 'line': 8},
            'arguments': {'semantic': {'painter': {'expression': 'company.painter(id)'}}},
            'local_values': {'id': 'repository.load()'}}]}
        result = scan_source_page(page)
        self.assertFalse(result['project_code_executed'])
        self.assertEqual(result['counts'], {'api_gap_candidate': 1, 'state_or_business_call': 1})

    def test_import_alias_and_fully_qualified_call_use_same_adapter(self):
        adapter = ApiAdapter('sample.image', 'image', ('sample.assets.photo',),
                             lambda call, ctx, seen: ctx.value(call.argument('id'), seen))
        registry = AdapterRegistry([adapter])
        for expression, imports in [('photo(7)', {'photo': 'sample.assets.photo'}),
                                    ('picture(7)', {'picture': 'sample.assets.photo'}),
                                    ('sample.assets.photo(7)', {})]:
            resolver = value_resolver({}, {'__source_imports': imports, '__api_registry': registry})
            self.assertEqual(resolver.value(parse_expression(expression)), 7)

    def test_duplicate_symbols_and_ambiguous_aliases_fail(self):
        a = ApiAdapter('a', 'image', ('one.icon',), lambda *args: UNRESOLVED, aliases=('icon',))
        with self.assertRaises(AdapterConflict):
            AdapterRegistry([a, ApiAdapter('b', 'image', ('one.icon',), lambda *args: None)])
        registry = AdapterRegistry([a, ApiAdapter('b', 'image', ('two.icon',), lambda *args: None, aliases=('icon',))])
        with self.assertRaises(AdapterConflict):
            registry.select('icon', {})
        self.assertEqual(registry.select('icon', {'icon': 'two.icon'}).id, 'b')
        self.assertIsNone(registry.select('icon', {'icon': 'unrelated.icon'}))

    def test_hash_pinned_explicit_extension_and_isolated_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code = ('from ui_migration.frontend.api_adapters.registry import ApiAdapter\n'
                    'def value(call, context, seen):\n'
                    '    return context.value(call.argument("value"), seen)\n'
                    'ADAPTERS = [ApiAdapter("company.color", "background", ("company.ink",), value)]\n')
            module = root / 'colors.py'; module.write_text(code)
            manifest = root / 'adapters.json'
            def write(digest):
                manifest.write_text(json.dumps({'schema': 'ui-migration.api-adapters.v1',
                    'modules': [{'path': 'colors.py', 'sha256': digest}]}))
            write(hashlib.sha256(module.read_bytes()).hexdigest())
            registry = load_adapters(manifest)
            self.assertEqual(registry.select('company.ink', {}).id, 'company.color')
            self.assertIsNone(load_adapters(None).select('company.ink', {}))
            write('0' * 64)
            with self.assertRaisesRegex(ValueError, 'SHA'):
                load_adapters(manifest)

    def test_adapter_cannot_return_layout_nodes_or_mutate_context(self):
        def unsafe(call, context, seen):
            context.values['x'] = 99
            return {'components': []}
        registry = AdapterRegistry([ApiAdapter('unsafe', 'image', ('test.image',), unsafe)])
        resolver = value_resolver({}, {'x': 1, '__api_registry': registry})
        with self.assertRaises((TypeError, ValueError)):
            resolver.value(parse_expression('test.image()'))
        self.assertEqual(resolver.values['x'], 1)

    def test_unresolved_is_not_null_and_remains_local(self):
        registry = AdapterRegistry([ApiAdapter('missing', 'image', ('test.image',), lambda *args: UNRESOLVED)])
        self.assertIs(registry.evaluate(parse_expression('test.image()'), value_resolver({}, {}), ()), UNRESOLVED)


if __name__ == '__main__':
    unittest.main()
