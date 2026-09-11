import copy
import unittest

import test_keyed_resources as helpers
from ui_migration.contracts.component_reuse import validate_reuse
from ui_migration.frontend.component_reuse import ComponentAdapter, ComponentReuse


EXTENSION = '''from ui_migration.frontend.component_reuse import ComponentAdapter
ADAPTERS = []
COMPONENT_ADAPTERS = [ComponentAdapter('company.caption', 'example.Caption', './CompanyUi', 'Caption',
    parameters={'label':'title'})]
'''


class ComponentReuseTest(unittest.TestCase):
    def generate(self, body, declarations, extension=EXTENSION):
        return helpers.KeyedResourcesTest.generate(self, body, declarations, extension)

    def test_explicit_reuse_survives_single_json_without_source_or_adapter(self):
        page, code, result, renderer = self.generate('Column { Caption("One"); Caption("Two") }',
            '@Composable fun Caption(label: String) { Text(label) }')
        self.assertIn("import { Caption as ReusedCaption } from './CompanyUi';", code)
        self.assertIn('ReusedCaption({ title: "One" })', code)
        self.assertIn('ReusedCaption({ title: "Two" })', code)
        self.assertNotIn('Text(', code)
        self.assertNotIn('private Caption(', code)
        self.assertEqual(len(renderer.component_reuse.instances), 2)
        self.assertEqual(len(page['components']), 3)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertEqual(renderer.test_phase_gate['verdict'], 'pass', renderer.test_phase_gate['failures'])

    def test_name_alone_does_not_reuse(self):
        _, code, _, renderer = self.generate('Caption("Original")',
            '@Composable fun Caption(label: String) { Text(label) }',
            EXTENSION.replace('example.Caption', 'another.Caption'))
        self.assertNotIn('ReusedCaption', code)
        self.assertIn("Text(props.label)", code)
        self.assertEqual(renderer.component_reuse.instances, [])

    def test_unresolved_argument_keeps_original_and_fails_explicitly(self):
        _, code, result, _ = self.generate('Caption(missing)',
            '@Composable fun Caption(label: String) { Text("Known content") }')
        self.assertIn('Known content', code)
        self.assertFalse(result['generation_complete'])
        self.assertTrue(any('component parameter is unresolved: label' in str(u) for u in result['unresolved']))

    def test_inline_slot_preserves_children_once_and_removes_only_implementation(self):
        extension = '''from ui_migration.frontend.component_reuse import ComponentAdapter
ADAPTERS = []
COMPONENT_ADAPTERS = [ComponentAdapter('shell', 'example.Shell', './CompanyUi', 'Shell',
    parameters={'title':'heading'}, slots={'content':'body'})]
'''
        page, code, result, renderer = self.generate('Shell("Title") { Text("First", color = Color.Black); Text("Second", color = Color.Black) }',
            '@Composable fun Shell(title: String, content: @Composable () -> Unit) { Column { Text("Internal"); content() } }', extension)
        self.assertIn('heading: "Title", body: () => { this.ShellBody() }', code)
        self.assertNotIn('Internal', code)
        self.assertEqual(code.count("Text('First')"), 1)
        self.assertEqual(code.count("Text('Second')"), 1)
        self.assertNotIn('renderShellBody', code)
        root = next(n for n in page['components'] if n['type'] == 'Shell')
        self.assertEqual(root['source']['component_reuse']['slots']['body'], root['children_ids'])
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertEqual(renderer.test_phase_gate['verdict'], 'pass', renderer.test_phase_gate['failures'])

    def test_unaccounted_parameter_does_not_disappear(self):
        _, code, result, _ = self.generate('Caption("Name", true)',
            '@Composable fun Caption(label: String, enabled: Boolean) { Text(label) }')
        self.assertIn('Text(', code)
        self.assertNotIn('ReusedCaption', code)
        self.assertTrue(any('account for every parameter: enabled' in str(u) for u in result['unresolved']))

    def test_ambiguous_adapters_do_not_choose_first(self):
        _, code, result, _ = self.generate('Caption("Name")',
            '@Composable fun Caption(label: String) { Text(label) }',
            EXTENSION + "\nCOMPONENT_ADAPTERS.append(ComponentAdapter('other', 'example.Caption', './Other', 'Caption', parameters={'label':'text'}))")
        self.assertNotIn('ReusedCaption', code)
        self.assertTrue(any('ambiguous component adapters' in str(u) for u in result['unresolved']))

    def test_safe_contract_rejects_code_and_duplicate_slot_children(self):
        record = {'schema':'ui-migration.component-reuse.v1','adapter_id':'a','definition_id':'d',
            'android':'example.Caption','target':{'module':'./Ui','export':'Caption'},
            'properties':{'title':'safe'},'slots':{}}
        validate_reuse(record)
        bad = copy.deepcopy(record)
        bad['properties']['title'] = {'arkts':'arbitrary()'}
        with self.assertRaises(ValueError):
            validate_reuse(bad)
        bad = copy.deepcopy(record)
        bad['slots'] = {'first':['child'], 'second':['child']}
        with self.assertRaises(ValueError):
            validate_reuse(bad)

    def test_forwarded_parameters_and_defaults(self):
        _, code, result, _ = self.generate('Column { Caption(); Outer("First") }', '''
@Composable fun Outer(value: String) { Caption(value) }
@Composable fun Caption(label: String = "Default") { Text(label) }
''')
        self.assertIn('this.Outer("First")', code)
        self.assertIn('ReusedCaption({ title: props.value })', code)
        self.assertIn('title: "Default"', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_slot_inside_generated_wrapper_forwards_scoped_props(self):
        extension = '''from ui_migration.frontend.component_reuse import ComponentAdapter
ADAPTERS = []
COMPONENT_ADAPTERS = [ComponentAdapter('shell', 'example.Shell', './CompanyUi', 'Shell', slots={'content':'body'})]
'''
        _, code, result, renderer = self.generate('Outer("Forwarded")', '''
@Composable fun Outer(title: String) { Shell { Text(title, color = Color.Black) } }
@Composable fun Shell(content: @Composable () -> Unit) { Column { content() } }
''', extension)
        self.assertIn('this.Outer("Forwarded")', code)
        self.assertIn('body: () => { this.ShellBody(props.title) }', code)
        self.assertNotIn('renderShellBody', code)
        self.assertIn('Text(title)', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertEqual(renderer.test_phase_gate['verdict'], 'pass', renderer.test_phase_gate['failures'])

    def test_list_instances_preserve_slot_root_ids(self):
        extension = '''from ui_migration.frontend.component_reuse import ComponentAdapter
ADAPTERS = []
COMPONENT_ADAPTERS = [ComponentAdapter('shell', 'example.Shell', './CompanyUi', 'Shell', slots={'content':'body'})]
'''
        page, code, result, renderer = self.generate('Column { listOf("One", "Two").forEach { label -> Shell { Text(label, color = Color.Black) } } }',
            '@Composable fun Shell(content: @Composable () -> Unit) { Column { content() } }', extension)
        self.assertEqual(len(renderer.component_reuse.instances), 2)
        for node in page['components']:
            if node['type'] == 'Shell':
                self.assertEqual(node['source']['component_reuse']['slots']['body'], node['children_ids'])
        self.assertEqual(code.count("Text('One')"), 1)
        self.assertEqual(code.count("Text('Two')"), 1)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_code_adapter_converts_dimension_without_raw_code(self):
        extension = '''from ui_migration.frontend.component_reuse import ComponentAdapter
class Sized(ComponentAdapter):
    def properties(self, arguments):
        size = arguments['size']
        if size.unit != 'dp':
            raise ValueError('expected dp')
        return {'size':size.value}
ADAPTERS = []
COMPONENT_ADAPTERS = [Sized('sized', 'example.Sized', './CompanyUi', 'Sized', parameters={'size':'size'})]
'''
        _, code, result, _ = self.generate('Sized(24.dp)',
            '@Composable fun Sized(size: Dp) { Box(Modifier.size(size)) {} }', extension)
        self.assertRegex(code, r'ReusedSized\(\{ size: 24(?:\.0)? \}\)')
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_keyed_resource_property_stays_a_library_call(self):
        extension = helpers.EXTENSION + '''
from ui_migration.frontend.component_reuse import ComponentAdapter
COMPONENT_ADAPTERS = [ComponentAdapter('colored', 'example.Colored', './CompanyUi', 'Colored', parameters={'color':'color'})]
'''
        _, code, result, _ = self.generate('Colored(Palette.get("brand.primary"))',
            '@Composable fun Colored(color: Color) { Box(Modifier.background(color)) {} }', extension)
        self.assertIn('.resolve("brand.primary")', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_overload_requires_declaration_identity(self):
        definitions = [{'id': d, 'component_kind':'project_component',
            'identity':{'qualified_name':'example.Caption', 'source':'Page.kt','declaration_id':d},
            'parameters':[{'name':'label','type':kind}]} for d, kind in [('a','String'),('b','Int')]]
        adapter = ComponentAdapter('caption', 'example.Caption', './Ui', 'Caption', parameters={'label':'title'})
        node = {'definition_id':'a', 'invocation_bindings':{'label':'"Text"'}}
        with self.assertRaisesRegex(ValueError, 'multiple source definitions'):
            ComponentReuse([adapter], definitions).resolve(node, lambda *args: 'Text')
        precise = ComponentAdapter('caption', 'example.Caption', './Ui', 'Caption',
            parameters={'label':'title'}, declaration_id='a')
        self.assertEqual(ComponentReuse([precise], definitions).resolve(node, lambda *args:'Text')['properties'], {'title':'Text'})

    def test_default_uses_callee_parameters_but_explicit_argument_uses_caller(self):
        extension = EXTENSION.replace("{'label':'title'}", "{'subtitle':'subtitle','label':'title'}")
        _, code, result, _ = self.generate('Column { val label = "Caller"; Caption("First"); Caption("Second", label) }',
            '@Composable fun Caption(label: String, subtitle: String = label) { Text(label); Text(subtitle) }', extension)
        self.assertIn('subtitle: "First", title: "First"', code)
        self.assertIn('subtitle: "Caller", title: "Second"', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_two_named_slots_keep_their_ownership(self):
        extension = '''from ui_migration.frontend.component_reuse import ComponentAdapter
ADAPTERS = []
COMPONENT_ADAPTERS = [ComponentAdapter('panel', 'example.Panel', './Ui', 'Panel', slots={'header':'top','content':'body'})]
'''
        page, code, result, renderer = self.generate('Panel(header = { Text("Header", color = Color.Black) }) { Text("Body", color = Color.Black) }',
            '@Composable fun Panel(header: @Composable () -> Unit, content: @Composable () -> Unit) { Column { header(); content() } }', extension)
        record = renderer.component_reuse.instances[0]
        self.assertEqual(len(record['slots']['top']), 1)
        self.assertEqual(len(record['slots']['body']), 1)
        self.assertNotEqual(record['slots']['top'], record['slots']['body'])
        self.assertEqual(code.count("Text('Header')"), 1)
        self.assertEqual(code.count("Text('Body')"), 1)
        self.assertIn('top: () => { this.PanelTop() }', code)
        self.assertIn('body: () => { this.PanelBody() }', code)
        self.assertNotIn('renderPanelTop', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertEqual(renderer.test_phase_gate['verdict'], 'pass', renderer.test_phase_gate['failures'])

    def test_unknown_modifier_is_not_silently_removed(self):
        extension = EXTENSION.replace("{'label':'title'}", "{'label':'title','modifier':'modifier'}")
        _, code, result, _ = self.generate('Caption("Known", Modifier.fillMaxWidth())',
            '@Composable fun Caption(label: String, modifier: Modifier) { Text(label, modifier = modifier) }', extension)
        self.assertNotIn('ReusedCaption', code)
        self.assertIn('Text(', code)
        self.assertTrue(any('source.component_reuse' in str(u) for u in result['unresolved']))

    def test_parameterized_slot_is_diagnostic_not_empty_ui(self):
        extension = '''from ui_migration.frontend.component_reuse import ComponentAdapter
ADAPTERS = []
COMPONENT_ADAPTERS = [ComponentAdapter('panel','example.Panel','./Ui','Panel',slots={'content':'body'})]
'''
        _, code, result, _ = self.generate('Panel { value -> Text(value, color = Color.Black) }',
            '@Composable fun Panel(content: @Composable (String) -> Unit) { content("Actual") }', extension)
        self.assertNotIn('ReusedPanel', code)
        self.assertTrue(any('only no-argument composable slots' in str(u) for u in result['unresolved']))


if __name__ == '__main__':
    unittest.main()
