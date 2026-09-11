"""Value-producing composables must feed expressions, not become UI builders."""
import unittest
import hashlib
import json
from pathlib import Path

import test_keyed_resources as helpers
import test_page_commands as commands
from test_page_roots import source_page
from test_business_components import compile_page
from ui_migration.frontend.source_symbols import SourceSymbolIndex, function_identity
from ui_migration.frontend.values import value_resolver
from ui_migration.frontend.api_adapters.registry import ApiAdapter, AdapterRegistry
from kotlin_psi import parse_expression

COPY_ADAPTER = '''from ui_migration.frontend.api_adapters.keyed_resources import KeyedResourceAdapter
class Copy(KeyedResourceAdapter):
    def harmony_target(self, key, arguments):
        return {"module":"./ProjectCopyBridge", "export":"ProjectCopyBridge", "member":"read", "arguments":[key]}
ADAPTERS = [Copy("project.copy", ("example.getRawString",), "string").declaration()]
'''


class ComposableValuesTest(unittest.TestCase):
    generate = helpers.KeyedResourcesTest.generate

    def test_inferred_getter_feeds_nested_component_parameters(self):
        page, code, result, renderer = self.generate('Column { Banner(getRawString("first")); Banner(getRawString("second")) }', '''
@Composable fun getRawString(key: String) = Copy.text(key, "Alice")
@Composable fun Banner(customTitle: String) { Label(customTitle) }
@Composable fun Label(anotherName: String) { Text(anotherName, color = Color.Black) }
''')
        self.assertNotIn('getRawString', [n['type'] for n in page['components']])
        self.assertNotIn('private getRawString', code)
        self.assertIn("this.Banner(StyleToken0.read('first', 'Alice'))", code)
        self.assertIn("this.Banner(StyleToken0.read('second', 'Alice'))", code)
        self.assertIn('this.Label(props.customTitle)', code)
        self.assertIn('Text(props.anotherName)', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved)

    def test_direct_text_and_button_label_consume_inferred_getter(self):
        page, code, _, _ = self.generate('Column { Text(ReadCopy("heading"), color = Color.Black); Button(onClick = {}) { Text(ReadCopy("next"), color = Color.Black) } }', '''
@Composable fun ReadCopy(key: String) = Copy.text(key, "Alice")
''')
        self.assertNotIn('ReadCopy', [n['type'] for n in page['components']])
        self.assertIn("Text(StyleToken0.read('heading', 'Alice'))", code)
        self.assertIn("Text(StyleToken0.read('next', 'Alice'))", code)

    def test_value_use_follows_local_and_inferred_helper_return(self):
        page, code, _, _ = self.generate('val title = outer("heading"); Text(title, color = Color.Black)', '''
@Composable fun outer(key: String) = inner(key)
@Composable fun inner(key: String) = Copy.text(key, "Alice")
''')
        self.assertFalse({'outer', 'inner'}.intersection(n['type'] for n in page['components']))
        self.assertIn("Text(StyleToken0.read('heading', 'Alice'))", code)

    def test_missing_adapter_retains_value_diagnostic_not_fake_ui(self):
        page, code, result, renderer = self.generate('Text(readUnknown("heading"), color = Color.Black)', '''
@Composable fun readUnknown(key: String) = unknownPlatformRead(key)
''')
        self.assertNotIn('readUnknown', [n['type'] for n in page['components']])
        self.assertNotIn('private readUnknown', code)
        self.assertFalse(result['generation_complete'])

    def test_adapter_matches_android_getter_itself(self):
        page, code, result, renderer = self.generate('Banner(getRawString("heading"))', '''
@Composable fun getRawString(key: String) = Platform.readCopy(key)
@Composable fun Banner(customTitle: String) { Text(customTitle, color = Color.Black) }
''', extension=COPY_ADAPTER)
        self.assertNotIn('getRawString', [n['type'] for n in page['components']])
        self.assertIn("this.Banner(StyleToken0.read('heading'))", code)
        self.assertIn('Text(props.customTitle)', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved)

    def test_import_alias_is_resolved_to_value_declaration(self):
        page, code, _, _ = self.generate('Text(readLabel("heading"), color = Color.Black)',
            extra_files={'Copy.kt': '''package example.copy
import company.Copy
@Composable fun copy(key: String) = Copy.text(key, "Alice")
'''}, source_imports='import example.copy.copy as readLabel')
        self.assertNotIn('copy', [n['type'] for n in page['components']])
        self.assertIn("Text(StyleToken0.read('heading', 'Alice'))", code)

    def test_ui_wrappers_and_slots_are_not_filtered_as_values(self):
        index = SourceSymbolIndex({'Page.kt': '''
@Composable fun Page() { Shell { Header() } }
@Composable fun Header() = Text("Heading")
@Composable fun Shell(content: @Composable () -> Unit) { content() }
@Composable fun Explicit(): kotlin.Unit { Text("Explicit") }
'''})
        roles = {f['name']: index.roles[function_identity(f)] for f in index.functions}
        self.assertEqual(roles, {'Page':'content', 'Header':'content', 'Shell':'content', 'Explicit':'content'})

    def test_same_name_in_another_package_does_not_match_adapter(self):
        page, code, result, renderer = self.generate('Text(getRawString("heading"), color = Color.Black)',
            extra_files={'Other.kt': '''package other
@Composable fun getRawString(key: String) = Platform.readCopy(key)
'''}, source_imports='import other.getRawString', extension=COPY_ADAPTER)
        self.assertNotIn('ProjectCopyBridge', code)
        self.assertFalse(result['generation_complete'])

    def test_ambiguous_overload_is_not_arbitrarily_adapted(self):
        _, code, result, _ = self.generate('Text(getRawString("heading"), color = Color.Black)', '''
@Composable fun getRawString(key: String) = Platform.readCopy(key)
@Composable fun getRawString(key: Int) = Platform.readCopy(key)
''', extension=COPY_ADAPTER)
        self.assertNotIn('ProjectCopyBridge', code)
        self.assertFalse(result['generation_complete'])

    def test_value_returning_ui_function_is_reported_not_silently_dropped(self):
        source = source_page('''
@Composable fun Page() { Text(Mixed()) }
@Composable fun Mixed(): String { Text("Side UI"); return "Value" }
''')
        self.assertTrue(any('both' in u['reason'] and 'value' in u['reason']
                            for u in source['unresolved']), source['unresolved'])

    def test_returned_stored_and_forwarded_slots_are_not_executed(self):
        declarations = '''
class Entry(val content: @Composable () -> Unit)
@Composable fun Holder(content: @Composable () -> Unit) = content
@Composable fun Store(content: @Composable () -> Unit) = Entry(content)
@Composable fun Forward(content: @Composable () -> Unit) = Holder(content)
'''
        for factory in ('Holder', 'Store', 'Forward'):
            with self.subTest(factory=factory):
                page, code, result, _ = self.generate('val later = Deferred(); Column { Text("Visible", color = Color.Black) }',
                    declarations + '@Composable fun Deferred() = ' + factory + ' { Text("Not invoked") }')
                self.assertNotIn('Not invoked', code)
                self.assertNotIn('Deferred', [n['type'] for n in page['components']])
                self.assertFalse(any('both a value and UI' in u['reason'] for u in result['unresolved']))

    def test_forwarded_slot_is_executed_only_by_its_host(self):
        page, code, _, _ = self.generate('Outer { Text("Visible", color = Color.Black) }', '''
@Composable fun Outer(content: @Composable () -> Unit) = Inner(content)
@Composable fun Inner(content: @Composable () -> Unit) { content() }
''')
        self.assertEqual([n['style']['content']['text'] for n in page['components'] if n['type'] == 'Text'], ['Visible'])
        self.assertIn('Text(props.text)', code)

    def test_returned_callable_is_drawn_only_when_invoked(self):
        for annotation in ('', ': @Composable () -> Unit'):
            declaration = '@Composable fun Factory()' + annotation + ' = { Text("Shown", color = Color.Black) }'
            with self.subTest(annotation=annotation):
                _, delayed, _, _ = self.generate('val later = Factory(); Text("Visible", color = Color.Black)', declaration)
                self.assertNotIn('Shown', delayed)
                _, invoked, result, _ = self.generate('Factory().invoke()', declaration)
                self.assertIn("Text('Shown')", invoked)
                self.assertTrue(result['generation_complete'], result['unresolved'])
                self.assertNotIn('private invoke', invoked)
                self.assertNotIn('this.invoke(', invoked)

    def test_immediate_callable_inside_value_used_helper_retains_ui(self):
        for body in ('{ Text("Shown", color = Color.Black) }', '::Header'):
            with self.subTest(body=body):
                page, code, result, _ = self.generate('val ignored = ExecuteFactory(); Text("Visible", color = Color.Black)', '''
@Composable fun Header() { Text("Shown", color = Color.Black) }
@Composable fun Factory(): @Composable () -> Unit = ''' + body + '''
@Composable fun ExecuteFactory() = Factory().invoke()
''')
                self.assertIn('Shown', code)
                self.assertIn('ExecuteFactory', [n['type'] for n in page['components']])
                self.assertTrue(any('both a value and UI' in u['reason'] for u in result['unresolved']))

    def test_unknown_callable_invocation_keeps_diagnostic(self):
        for body in ('Factory().invoke()', 'val ignored = ExecuteFactory(); Text("Visible", color = Color.Black)'):
            with self.subTest(body=body):
                _, _, result, _ = self.generate(body, '''
@Composable fun Factory(): @Composable () -> Unit = Platform.unknown()
@Composable fun ExecuteFactory() = Factory().invoke()
''')
                self.assertFalse(result['generation_complete'])
                self.assertTrue(any(u.get('path') == 'source.callable' for u in result['unresolved']))

    def test_invoking_value_lambda_does_not_make_a_ui_builder(self):
        page, code, result, _ = self.generate('Text(Read(), color = Color.Black)', '''
@Composable fun Factory() = { "Heading" }
@Composable fun Read() = Factory().invoke()
''')
        self.assertIn("Text('Heading')", code)
        self.assertNotIn('Read', [n['type'] for n in page['components']])
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_ambiguous_invoked_reference_is_diagnosed_not_dropped(self):
        _, _, result, _ = self.generate('val ignored = ExecuteFactory(); Text("Visible", color = Color.Black)', '''
@Composable fun Header(value: Float) { Text("Float", color = Color.Black) }
@Composable fun Header(value: Double) { Text("Double", color = Color.Black) }
@Composable fun Factory() = ::Header
@Composable fun ExecuteFactory() = Factory().invoke(1)
''')
        self.assertFalse(result['generation_complete'])
        self.assertTrue(any(u.get('path') == 'source.callable' for u in result['unresolved']))

    def test_cross_file_reference_propagates_unknown_invocation_to_outer_helper(self):
        _, _, result, _ = self.generate('val ignored = ExecuteFactory(); Text("Visible", color = Color.Black)', '''
@Composable fun Factory(): @Composable () -> Unit = ::Header
@Composable fun ExecuteFactory() = Factory().invoke()
''', source_imports='import other.Header', extra_files={'Other.kt': '''package other
@Composable fun Header() { UnknownFactory().invoke() }
@Composable fun UnknownFactory(): @Composable () -> Unit = Platform.unknown()
'''})
        self.assertFalse(result['generation_complete'])
        self.assertTrue(any(u.get('path') == 'source.callable' for u in result['unresolved']))

    def test_callable_projection_does_not_require_adapter_manifest(self):
        for annotation in ('', ': @Composable () -> Unit'):
            with self.subTest(annotation=annotation):
                _, _, page, _, code = compile_page('''
@Composable fun Page() { Factory().invoke() }
@Composable fun Factory()''' + annotation + ''' = { Text("Shown", color = Color.Black) }
''')
                self.assertIn("Text('Shown')", code)
                self.assertEqual([n['style']['content']['text'] for n in page['components'] if n['type'] == 'Text'], ['Shown'])
        _, _, page, _, _ = compile_page('''
@Composable fun Page() { Factory().invoke() }
@Composable fun Factory(): @Composable () -> Unit = Platform.unknown()
''')
        self.assertTrue(any(u.get('path') == 'source.callable'
                            for n in page['components'] for u in n['unresolved']))

    def test_class_member_resolves_top_level_adapter_with_member_shadowing(self):
        getter = '@Composable fun getRawString(key: String) = Platform.readCopy(key)'
        for separate in (False, True):
            for shadow in (False, True):
                with self.subTest(separate=separate, shadow=shadow):
                    files = {'Page.kt': 'package example\n' + ('' if separate else getter) + '''
class Screen {
@Composable fun Content() { Text(getRawString("heading")) }
''' + ('@Composable fun getRawString(key: String): String = "Member"' if shadow else '') + '\n}'}
                    if separate:
                        files['Copy.kt'] = 'package example\n' + getter
                    index = SourceSymbolIndex(files)
                    registry = AdapterRegistry([ApiAdapter('copy', 'text', ('example.getRawString',),
                        lambda call, ctx, seen: 'Adapted ' + ctx.value(call.argument('key'), seen))])
                    resolver = value_resolver({}, {'__source_functions':index.functions,
                        '__source_file':'Page.kt', '__source_owner':'Screen', '__source_imports':{},
                        '__api_registry':registry})
                    self.assertEqual(resolver.value(parse_expression('getRawString("heading")')),
                                     'Member' if shadow else 'Adapted heading')


class ComposableValuePageTest(unittest.TestCase):
    setUp = commands.PageCommandsTest.setUp
    run_tool = commands.PageCommandsTest.run_tool
    full_args = commands.PageCommandsTest.full_args

    def generate(self):
        files = {
            'Page.kt': '''package example
@Composable fun Page() { Column {
    Banner(getRawString("first"))
    Banner(getRawString("second"))
    Button(onClick = {}) { Text(getRawString("next")) }
} }
''',
            'Copy.kt': '''package example
@Composable fun getRawString(key: String) = Platform.readCopy(key)
''',
            'Banner.kt': '''package example
@Composable fun Banner(customTitle: String) { Label(customTitle) }
@Composable fun Label(anotherName: String) { Text(anotherName, color = Color.Black) }
''',
        }
        for name, content in files.items():
            (self.source/name).write_text(content)
        self.snapshot = self.root/'copy-snapshot'
        self.contract = self.root/'copy-contract.json'
        self.run_tool('prepare_safe_snapshot.py', '--source', self.source, '--snapshot', self.snapshot)
        self.run_tool('analyze_compose_project.py', '--snapshot', self.snapshot, '--output', self.contract)
        self.run_tool('generate_project_style_definitions.py', '--contract', self.contract, '--output', self.styles, '--refresh')
        styles = json.loads(self.styles.read_text())
        styles['theme']['colors'].update(primary='#FF123456', onPrimary='#FFFFFFFF')
        self.styles.write_text(json.dumps(styles))
        (self.root/'adapter.py').write_text(COPY_ADAPTER)
        manifest = self.root/'adapters.json'
        manifest.write_text(json.dumps({'schema':'ui-migration.api-adapters.v1', 'modules':[
            {'path':'adapter.py', 'sha256':hashlib.sha256(COPY_ADAPTER.encode()).hexdigest()}]}))
        target = self.root/'harmony'
        self.run_tool('init_harmony_project.py', '--output', target, '--contract', self.contract,
                      '--project-name', 'CopyPage', '--bundle-name', 'com.example.copypage', '--sdk-version', '6.0.0(20)')
        bridge = target/'entry/src/main/ets/generated/ProjectCopyBridge.ets'
        bridge.parent.mkdir(parents=True, exist_ok=True)
        bridge.write_text('''export class ProjectCopyBridge {
  static read(key: string): string {
    if (key === 'first') { return 'First title'; }
    if (key === 'second') { return 'Second title'; }
    if (key === 'next') { return 'Next'; }
    return key;
  }
}
''')
        result = self.run_tool('migrate_compose_page.py', *self.full_args(), '--api-adapters', manifest, '--no-auto-component-reuse')
        return result, target

    def test_complete_page_keeps_copy_values_connected_to_text(self):
        result, target = self.generate()
        self.assertTrue(result['generation_complete'], result.get('diagnosis'))
        self.assertEqual(result['verdict'], 'pass')
        page = Path(result['arkui']['output']).read_text()
        banner = (target/'entry/src/main/ets/generated/Banner.ets').read_text()
        self.assertIn("Banner(StyleToken0.read('first'))", page)
        self.assertIn("Banner(StyleToken0.read('second'))", page)
        self.assertIn("Text(StyleToken0.read('next'))", page)
        self.assertIn('Label(props.customTitle)', banner)
        self.assertIn('Text(props.anotherName)', banner)
        self.assertFalse((target/'entry/src/main/ets/generated/Copy.ets').exists())
        self.assertNotIn('getRawString', page + banner)


if __name__ == '__main__':
    unittest.main()
