"""Source methods must reach a native consumer, not just an unused export."""
import unittest
import json
import os
import subprocess
import tempfile
from unittest.mock import patch
from pathlib import Path

import test_keyed_resources as helpers
from ui_migration.arkui.source_modules import render_modules


MODEL = '''
data class Person(val name: String, val active: Boolean)
fun caption(person: Person, labels: List<String>): String {
    var result = person.name
    for (label in labels) { result = result + label }
    if (person.active) { return result } else { return "Inactive" }
}
fun title(person: Person): String = caption(person, listOf("!", "?"))
'''


class SourceValueMethodsTest(unittest.TestCase):
    def generate(self, body, declarations=MODEL, **kwargs):
        page, code, result, renderer = helpers.KeyedResourcesTest.generate(
            self, body, declarations, **kwargs)
        files, report = render_modules(code, renderer.root, renderer.business_components,
            Path('/tmp/value-methods'), Path('/tmp/value-methods/Page.ets'))
        return '\n'.join(v.decode() for v in files.values()), page, result, renderer, report

    def test_record_function_branch_loop_are_consumed_by_text(self):
        code, page, _, _, report = self.generate('Text(title(Person("Ada", true)), color = Color.Black)')
        self.assertIn('export class Person', code)
        self.assertIn('export function caption(person: Person, labels: string[]): string', code)
        self.assertIn('for (const label of labels)', code)
        self.assertIn('export function title(person: Person): string', code)
        self.assertIn('Text(title(new Person(', code)
        self.assertNotIn('previewcaption', code)
        self.assertTrue(report['value_methods']['functions'])
        self.assertIn('source_program', page)

    def test_cross_file_methods_keep_source_modules(self):
        code, _, _, _, report = self.generate('Text(title(Person("Ada", true)), color = Color.Black)',
            '', extra_files={'Labels.kt': 'package example\n' + MODEL})
        self.assertTrue(any(item['output'] == 'Labels.ets' for item in report['value_methods']['functions']))
        self.assertIn('import { Person, title } from "./Labels"', code)

    def test_reusable_ui_parameter_is_not_baked_into_value_method_call(self):
        code, _, _, renderer, _ = self.generate('Column { Label("Ada"); Label("Bob") }', '''
fun format(value: String): String = value + "!"
@Composable fun Label(title: String) { Text(format(title), color = Color.Black) }
''')
        self.assertIn('format(title)', code)
        self.assertNotIn('format(("Ada"))', code)
        self.assertNotIn('format(("Bob"))', code)
        self.assertEqual(renderer.source_program.failures, [])

    def test_local_callable_shadow_does_not_resolve_to_top_level_function(self):
        code, _, _, _, _ = self.generate('val title = { "Local" }; Text(title())',
            'fun title(): String = "Global"')
        self.assertNotIn('export function title', code)

    def test_value_methods_do_not_require_adapters_or_state_fixture(self):
        generate = helpers.generate
        def without_adapters(args):
            args.api_adapters = None
            return generate(args)
        with patch.object(helpers, 'generate', side_effect=without_adapters):
            code, _, _, renderer, _ = self.generate('Text(title(Person("Ada", true)), color = Color.Black)')
        self.assertIn('Text(title(new Person(', code)
        self.assertEqual(renderer.source_program.failures, [])

    def test_registered_adapter_takes_precedence_over_source_method(self):
        extension = '''from ui_migration.frontend.api_adapters.keyed_resources import KeyedResourceAdapter
class Copy(KeyedResourceAdapter):
    def harmony_target(self, key, arguments):
        return {"module":"./Copy", "export":"Copy", "member":"read", "arguments":[key]}
ADAPTERS = [Copy("copy", ("example.caption",), "string").declaration()]
'''
        code, _, _, renderer, _ = self.generate('Text(caption("label"))',
            'fun caption(key: String): String = Remote.load(key)', extension=extension)
        self.assertIn("Copy.read('label')", code)
        self.assertNotIn('export function caption', code)
        self.assertEqual(renderer.source_program.failures, [])

    def test_nested_records_and_constructor_defaults_are_preserved(self):
        declarations = '''
data class Person(val name: String = "Ada")
data class State(val person: Person)
fun title(state: State): String = state.person.name
'''
        code, _, _, renderer, _ = self.generate('Text(title(State(Person())))', declarations)
        self.assertIn('export class State', code)
        self.assertIn('constructor(name: string = ("Ada"))', code)
        self.assertEqual(renderer.source_program.failures, [])

    def test_unknown_dependency_does_not_emit_a_fake_method(self):
        code, _, _, renderer, _ = self.generate('Text(title("Ada"), color = Color.Black)',
            'fun title(name: String): String = Remote.load(name)')
        self.assertNotIn('export function title', code)
        self.assertTrue(any('Remote.load' in str(u) for u in renderer.unresolved), renderer.unresolved)

    def test_int_arithmetic_defaults_and_multiple_inputs_match_kotlin(self):
        declarations = MODEL + '''
fun score(value: Int, offset: Int = 1): String {
    val total = value * 3 + offset
    return "$total"
}
'''
        _, _, _, renderer, _ = self.generate('Column { Text(title(Person("Ada", true))); Text(score(2)) }', declarations)
        self.assertEqual(renderer.source_program.failures, [])
        self.compare_kotlin(declarations, renderer.source_program.code(),
            ['title(Person("Ada", true))', 'title(Person("Bob", false))',
             'caption(Person("Empty", true), listOf())', 'score(2147483647)', 'score(-2147483647, -2)'],
            ['title(new Person("Ada", true))', 'title(new Person("Bob", false))',
             'caption(new Person("Empty", true), [])', 'score(2147483647)', 'score(-2147483647, -2)'])

    def compare_kotlin(self, kotlin, target, source_calls, target_calls):
        from kotlin_psi import ARTIFACTS
        from ui_migration.arkts_sdk import parser_runtime
        cache = Path(os.environ.get('GRADLE_USER_HOME', str(Path.home()/'.gradle'))) / 'caches/modules-2/files-2.1'
        jars = [next((cache/group/artifact/version).glob('*/' + artifact + '-' + version + '.jar'))
                for group, artifact, version in ARTIFACTS]
        classpath = os.pathsep.join(map(str, jars))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root/'Main.kt'
            file.write_text(kotlin + '\nfun main() {\n' + '\n'.join('println(' + c + ')' for c in source_calls) + '\n}')
            result = subprocess.run(['java', '-cp', classpath, 'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
                '-no-stdlib', '-no-reflect', '-classpath', classpath, '-d', str(root/'classes'), str(file)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            source = subprocess.check_output(['java', '-cp', str(root/'classes') + os.pathsep + classpath, 'MainKt'], text=True)
            node, compiler = parser_runtime()
            script = '''const ts = require(process.argv[1]);
const data = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const js = ts.transpileModule(data.code, {compilerOptions: {target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS}}).outputText;
eval(js + '\\n' + data.calls.map(c => 'console.log(' + c + ');').join('\\n'));
'''
            result = subprocess.run([node, '-e', script, compiler], input=json.dumps({'code': target, 'calls': target_calls}),
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, source)

    def test_when_and_repeat_keep_selection_at_call_time(self):
        declarations = '''
fun button(page: Int): String = when (page) { 0, 1, 2 -> "Next"; else -> "Explore" }
fun dots(count: Int): String {
    var text = ""
    repeat(count) { text = text + "." }
    return text
}
'''
        _, _, _, renderer, _ = self.generate('Column { Text(button(0)); Text(dots(4)) }', declarations)
        self.assertEqual(renderer.source_program.failures, [])
        self.compare_kotlin(declarations, renderer.source_program.code(),
            ['button(0)', 'button(3)', 'dots(4)', 'dots(0)', 'dots(-1)'],
            ['button(0)', 'button(3)', 'dots(4)', 'dots(0)', 'dots(-1)'])

    def test_unsupported_numeric_semantics_and_record_equality_are_reported(self):
        for declarations, call in [
            ('fun label(n: Long): String = "$n"', 'label(1L)'),
            ('data class Item(val value: Int)\nfun label(a: Item, b: Item): String = if (a == b) "yes" else "no"', 'label(Item(1), Item(1))'),
            ('fun label(a: Int): String = "${a / 0}"', 'label(1)'),
        ]:
            with self.subTest(call=call):
                code, _, _, renderer, _ = self.generate('Text(' + call + ')', declarations)
                self.assertTrue(renderer.source_program.failures)
                self.assertNotIn('export function label', code)

    def test_source_and_target_name_collisions_fail_closed(self):
        code, _, _, renderer, _ = self.generate('Text(label("A"))',
            'fun label(value: String): String = value\nfun label(value: Int): String = "$value"')
        self.assertTrue(renderer.source_program.failures)
        self.assertNotIn('export function label', code)

    def test_external_list_of_is_not_treated_as_kotlin_builtin(self):
        _, _, _, renderer, _ = self.generate('Text(title("A"))',
            'fun title(value: String): String { val labels = listOf(value); return labels.size.toString() }',
            source_imports='import external.listOf')
        self.assertTrue(renderer.source_program.failures)

    def test_intrinsics_and_normalized_fields_fail_closed_on_collision(self):
        for declarations, body in [
            ('fun String(active: Boolean): String = "custom"\nfun title(active: Boolean): String = "$active"',
             'Column { Text(String(true)); Text(title(false)) }'),
            ('data class Pair(val `default`: String, val defaultValue: String)\nfun title(pair: Pair): String = pair.`default` + pair.defaultValue',
             'Text(title(Pair("A", "B")))'),
            ('fun title(String: Boolean): String = "$String"', 'Text(title(true))'),
        ]:
            with self.subTest(body=body):
                code, _, _, renderer, _ = self.generate(body, declarations)
                self.assertTrue(renderer.source_program.failures)
                self.assertNotIn('export function String', code)
                self.assertNotIn('export class Pair', code)

    def test_import_and_builder_aliases_do_not_shadow_value_functions(self):
        code, _, _, renderer, _ = self.generate('Column { Text(StyleToken0(), color = Palette.get("ink")); Label() }', '''
fun StyleToken0(): String = "Token"
fun renderLabel(): String = "Body"
@Composable fun Label() { Text(renderLabel()) }
''')
        self.assertEqual(renderer.source_program.failures, [])
        self.assertIn('export function StyleToken0()', code)
        self.assertIn('export function renderLabel()', code)
        self.assertNotIn('as StyleToken0', code)
        self.assertEqual(code.count('export function renderLabel('), 1)

    def test_target_runtime_and_enum_names_do_not_shadow_generated_layout(self):
        for symbol in ('Number', 'Alignment', 'FontWeight'):
            with self.subTest(symbol=symbol):
                code, _, _, renderer, _ = self.generate(
                    'Column { Text(' + symbol + '(1)); Button(onClick = {}) { Text("OK") } }',
                    'fun ' + symbol + '(value: Int): String = "custom"')
                self.assertNotIn('export function ' + symbol + '(', code)
                self.assertTrue(any('conflicts with UI/import: ' + symbol in item['reason']
                                    for item in renderer.source_program.failures))
                if symbol == 'Number':
                    self.assertIn('Number(current.width)', code)

    def test_unrelated_local_declaration_does_not_pollute_top_level_resolution(self):
        code, _, _, renderer, _ = self.generate('Text(title("Top"))', '''
fun wrapper(): String { fun title(value: String): String = value; return title("Local") }
fun title(value: String): String = value + "!"
''')
        self.assertIn('export function title(value: string)', code)
        self.assertEqual(renderer.source_program.failures, [])

    def test_local_methods_and_records_are_not_exported(self):
        code, _, _, _, _ = self.generate('fun title(): String = "Local"; Text(title())', '')
        self.assertNotIn('export function title', code)
        code, _, _, _, _ = self.generate('data class Person(val name: String); Text(title(Person("A")))',
            'fun title(value: String): String = value')
        self.assertNotIn('export class Person', code)


if __name__ == '__main__':
    unittest.main()
