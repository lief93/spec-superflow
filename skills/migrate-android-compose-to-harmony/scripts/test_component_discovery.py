"""Public projection to single-JSON backend, using real SDK declaration parsing."""
import unittest
import test_keyed_resources as helpers


def component(name='Caption', fields='@Prop label: string = ""'):
    return '@Component\nexport struct ' + name + ' {\n' + fields + '\n build() {\n Column() {\n Text("Target")\n }\n }\n}\n'


class ComponentDiscoveryTest(unittest.TestCase):
    def generate(self, body='Caption("Hello")', declarations='@Composable fun Caption(label: String) { Text("Android internals") }',
                 files=None, extension='ADAPTERS = []'):
        return helpers.KeyedResourcesTest.generate(self, body, declarations, extension,
            harmony_files=files if files is not None else {'components/Caption.ets':component()})

    def test_first_pass_reuses_without_registration_or_backend_source(self):
        _, code, result, renderer = self.generate()
        self.assertIn("from '../components/Caption'", code)
        self.assertIn('ReusedCaption({  })', code)
        self.assertNotIn('Android internals', code)
        self.assertFalse(result['generation_complete'])
        self.assertIn('source argument omitted', str(result['unresolved']))
        self.assertEqual(result['discovery']['decisions'][0]['status'], 'matched')

    def test_no_match_keeps_original(self):
        _, code, result, renderer = self.generate(files={'Other.ets':component('Other')})
        self.assertIn('Android internals', code)
        self.assertFalse(renderer.component_reuse.instances)
        self.assertEqual(result['discovery']['decisions'][0]['status'], 'not-found')

    def test_incompatible_property_uses_target_default(self):
        _, code, result, renderer = self.generate(files={'Caption.ets':component(fields='@Prop label: number = 0')})
        self.assertNotIn('Android internals', code)
        self.assertEqual(renderer.component_reuse.instances[0]['properties'], {})
        self.assertFalse(result['generation_complete'])
        self.assertIn('target default', str(result['unresolved']))

    def test_ambiguity_does_not_choose_first(self):
        _, _, result, renderer = self.generate(files={'a/Caption.ets':component(), 'b/Caption.ets':component()})
        self.assertFalse(renderer.component_reuse.instances)
        self.assertIn('ambiguous same-name', str(result['unresolved']))

    def test_explicit_mapping_wins(self):
        extension = '''from ui_migration.frontend.component_reuse import ComponentAdapter
ADAPTERS = []
COMPONENT_ADAPTERS = [ComponentAdapter('explicit','example.Caption','@company/ui','Caption',parameters={'label':'title'})]
'''
        _, code, result, _ = self.generate(files={'a.ets':component(), 'b.ets':component()}, extension=extension)
        self.assertIn("from '@company/ui'", code)
        self.assertIn('title: "Hello"', code)
        self.assertEqual(result['discovery']['decisions'][0]['status'], 'explicit')

    def test_automatic_slot_uses_empty_default(self):
        page, code, result, renderer = self.generate('Shell { Text("Caller", color = Color.Black) }',
            '@Composable fun Shell(content: @Composable () -> Unit) { Column { Text("Internal"); content() } }',
            {'Shell.ets':component('Shell', '@BuilderParam content: () => void')})
        self.assertFalse(result['generation_complete'])
        self.assertNotIn('Internal', code)
        self.assertNotIn('Caller', code)
        self.assertIn('content: () => { this.ShellContent(', code)
        self.assertEqual(len(renderer.component_reuse.instances), 1)
        shell = next(n for n in page['components'] if n['type'] == 'Shell')
        self.assertEqual(shell['source']['component_reuse']['slots']['content'], [])
        self.assertEqual(shell['children_ids'], [])

    def test_unresolved_value_reports_reuse_failure(self):
        _, code, result, _ = self.generate('Caption(missing)')
        self.assertIn('ReusedCaption', code)
        self.assertFalse(result['generation_complete'])
        self.assertIn('target default', str(result['unresolved']))

    def test_source_defaults_and_outer_values_are_not_forwarded(self):
        _, code, result, renderer = self.generate('Column { Caption(); Outer("Two") }', '''
@Composable fun Outer(value: String) { Caption(value) }
@Composable fun Caption(label: String = "Default") { Text("Internal") }
''')
        self.assertNotIn('label: "Default"', code)
        self.assertNotIn('label: props.value', code)
        self.assertEqual(len(renderer.component_reuse.instances), 2)
        self.assertTrue(all(i['properties'] == {} for i in renderer.component_reuse.instances))
        self.assertFalse(result['generation_complete'])

    def test_empty_source_callback_is_omitted(self):
        _, code, result, renderer = self.generate('Action(onAction = {})',
            '@Composable fun Action(onAction: () -> Unit) { Text("Internal") }',
            {'Action.ets':component('Action', 'onAction: () => void = () => {}')})
        self.assertEqual(renderer.component_reuse.instances[0]['properties'], {})
        self.assertFalse(result['generation_complete'])

    def test_nonempty_callback_is_not_replaced_by_empty(self):
        _, code, result, renderer = self.generate('Action(onAction = { business() })',
            '@Composable fun Action(onAction: () -> Unit) { Text("Internal") }',
            {'Action.ets':component('Action', 'onAction: () => void = () => {}')})
        self.assertEqual(renderer.component_reuse.instances[0]['properties'], {})
        self.assertFalse(result['generation_complete'])
        self.assertIn('target default', str(result['unresolved']))

    def test_modifier_does_not_disappear(self):
        _, _, result, renderer = self.generate('Caption("Hi", Modifier.fillMaxWidth())',
            '@Composable fun Caption(label: String, modifier: Modifier) { Text(label) }')
        self.assertEqual(len(renderer.component_reuse.instances), 1)
        self.assertIn('source argument omitted', str(result['unresolved']))
        self.assertIn('modifier', str(result['unresolved']))

    def test_generated_private_entry_and_comments_are_excluded(self):
        _, code, result, renderer = self.generate(files={
            'generated/Caption.ets':component(),
            'Private.ets':component().replace('export struct','struct'),
            'Entry.ets':'@Entry\n' + component(),
            'Comment.ets':'/* ' + component() + ' */\nconst text = "export struct Caption";',
        })
        self.assertFalse(renderer.component_reuse.instances)
        self.assertIn('Android internals', code)
        self.assertEqual(result['discovery']['components'], [])

    def test_internal_state_not_required_as_argument(self):
        _, _, result, renderer = self.generate(files={'Caption.ets':component(fields='@Prop label: string = ""\n@State count: number = 0')})
        self.assertFalse(result['generation_complete'])
        self.assertEqual(renderer.component_reuse.instances[0]['properties'], {})

    def test_inferred_literal_type_and_nullable_type(self):
        _, _, result, renderer = self.generate(files={'Caption.ets':component(fields='@Prop label = ""')})
        self.assertEqual(len(renderer.component_reuse.instances), 1)
        self.assertFalse(result['generation_complete'])
        _, code, result, _ = self.generate('Caption(null)',
            '@Composable fun Caption(label: String?) { Text("Internal") }',
            {'Caption.ets':component(fields='label: string | null = null')})
        self.assertIn('ReusedCaption({  })', code)
        self.assertFalse(result['generation_complete'])

    def test_multiple_names_remain_ambiguous_even_with_different_types(self):
        _, code, result, renderer = self.generate('Caption("Hi")', '''
@Composable fun Caption(label: String) { Text(label) }
''', {'Text.ets':component(), 'Number.ets':component(fields='@Prop label: number = 0')})
        self.assertFalse(renderer.component_reuse.instances)
        self.assertIn('ambiguous same-name', str(result['unresolved']))

    def test_invalid_declaration_and_model_type_are_not_accepted(self):
        _, _, result, renderer = self.generate(files={'Caption.ets':component(fields='@Prop label: = ""')})
        self.assertFalse(renderer.component_reuse.instances)
        self.assertFalse(result['generation_complete'])
        _, _, result, renderer = self.generate('Caption(model)',
            '@Composable fun Caption(model: Account) { Text("Internal") }',
            {'Caption.ets':component(fields='model: Account')})
        self.assertFalse(renderer.component_reuse.instances)
        self.assertIn('required target parameter model', str(result['unresolved']))

    def test_required_extra_and_parameter_name_mismatch(self):
        _, _, result, renderer = self.generate(files={'Caption.ets':component(fields='@Require @Prop title: string')})
        self.assertEqual(renderer.component_reuse.instances[0]['properties'], {'title': ''})
        self.assertFalse(result['generation_complete'])
        self.assertIn('source argument omitted', str(result['unresolved']))

    def test_required_primitives_and_callback_are_defaulted_and_reported(self):
        page, code, result, renderer = self.generate(files={'Caption.ets': component(fields='''
@Require @Prop title: string
@Require @Prop size: number
@Require @Prop enabled: boolean
onClick: () => void
''')})
        props = renderer.component_reuse.instances[0]['properties']
        self.assertEqual(props, {'title':'', 'size':0, 'enabled':False, 'onClick':{'kind':'empty_callback'}})
        self.assertIn('onClick: () => {}', code)
        self.assertFalse(result['generation_complete'])
        from ui_migration.verification.generation_diagnosis import diagnose, render_markdown
        diagnosis = diagnose(manifest={'unresolved':renderer.unresolved}, source_page=page)
        self.assertGreater(diagnosis['counts']['defaulted'], 0)
        self.assertIn('component reuse parameter', render_markdown(diagnosis))

    def test_optional_complex_properties_are_omitted_not_constructed(self):
        _, code, result, renderer = self.generate(files={'Caption.ets':component(fields='''
@Prop label?: string
model?: Account
''')})
        self.assertEqual(renderer.component_reuse.instances[0]['properties'], {})
        self.assertNotIn('model:', code)
        self.assertFalse(result['generation_complete'])

    def test_missing_required_slot_gets_empty_slot_with_diagnostic(self):
        _, code, result, renderer = self.generate(files={'Caption.ets':component(fields='@BuilderParam content: () => void')})
        self.assertEqual(renderer.component_reuse.instances[0]['slots'], {'content':[]})
        self.assertIn('content: () =>', code)
        self.assertFalse(result['generation_complete'])

    def test_required_nullable_and_color_use_default_placeholders(self):
        _, code, result, renderer = self.generate(files={'Caption.ets':component(fields='''
model: Account | null
@Require @Prop color: ResourceColor
''')})
        self.assertEqual(renderer.component_reuse.instances[0]['properties'],
                         {'model':None, 'color':'#FF000000'})
        self.assertIn('model: null', code)
        self.assertFalse(result['generation_complete'])

    def test_required_unions_use_a_supported_member_default(self):
        _, code, result, renderer = self.generate(files={'Caption.ets':component(fields='''
@Require @Prop title: string | Resource
@Require @Prop size: number | string
''')})
        self.assertEqual(renderer.component_reuse.instances[0]['properties'], {'title':'', 'size':''})
        self.assertFalse(result['generation_complete'])
        from ui_migration.frontend.component_arguments import placeholder
        from ui_migration.frontend.page_model import UNRESOLVED
        self.assertEqual(placeholder('ResourceStr|string'), '')
        self.assertEqual(placeholder('Length|number'), 0)
        self.assertIsNone(placeholder('Account|null'))
        self.assertIs(placeholder('Account|Profile'), UNRESOLVED)

    def test_positional_optional_hole_does_not_shift_later_arguments(self):
        _, code, result, _ = self.generate('Caption("Hi")', files={'Caption.ets': '''
@Builder
export function Caption(model: Account = defaultAccount, label: string) { Text(label) }
'''})
        self.assertIn('ReusedCaption(undefined, "")', code)
        self.assertFalse(result['generation_complete'])

    def test_positional_trailing_defaults_are_not_emitted(self):
        _, code, result, _ = self.generate(files={'Caption.ets': '''
@Builder
export function Caption(label: string, model: Account = defaultAccount) { Text(label) }
'''})
        self.assertIn('ReusedCaption("")', code)
        self.assertFalse(result['generation_complete'])

    def test_source_default_references_are_ignored(self):
        _, code, result, renderer = self.generate('Caption()',
            '@Composable fun Caption(key: String = "Key", label: String = key) { Text(label) }')
        self.assertEqual(renderer.component_reuse.instances[0]['properties'], {})
        self.assertFalse(result['generation_complete'])

    def test_auto_reuse_does_not_pass_string_adapter_result(self):
        _, code, result, renderer = self.generate('Caption(Copy.text("hello", "Ada"))',
            files={'Caption.ets':component(fields='@Prop label: ResourceStr = ""')}, extension=helpers.EXTENSION)
        self.assertNotIn('.read("hello", "Ada")', code)
        self.assertEqual(renderer.component_reuse.instances[0]['properties'], {})
        self.assertFalse(result['generation_complete'])

    def test_automatic_binding_never_evaluates_source_arguments(self):
        from ui_migration.frontend.component_discovery import DiscoveredComponentAdapter
        adapter = DiscoveredComponentAdapter('auto', 'example.Caption', '@ui/lib', 'Caption',
            target_parameters=({'name':'label', 'type':'string', 'required':False, 'slot':False},))
        def evaluate(*args):
            self.fail('automatic reuse must not evaluate source values')
        bound = adapter.bind({'parameters':[{'name':'label', 'type':'String'}]},
                             {'invocation_bindings':{'label':'business()'}}, evaluate)
        self.assertEqual(bound['properties'], {})
        self.assertEqual(bound['property_parameters'], {})
        self.assertEqual(bound['diagnostics'][0]['expression'], 'business()')

    def test_no_source_arguments_uses_target_defaults_without_degradation(self):
        for target, expected in [(component(), 'ReusedCaption({  })'),
                ('@Builder\nexport function Caption(label: string = "Default") { Text(label) }', 'ReusedCaption()')]:
            with self.subTest(target=target):
                _, code, result, _ = self.generate('Caption()',
                    '@Composable fun Caption() { Text("Internal") }', {'Caption.ets':target})
                self.assertIn(expected, code)
                self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_placeholder_does_not_forward_incompatible_outer_value(self):
        _, code, result, renderer = self.generate('Outer("Wrong type")',
            '@Composable fun Outer(value: String) { Caption(value) }\n' +
            '@Composable fun Caption(label: String) { Text(label) }',
            {'Caption.ets':component(fields='@Require @Prop label: number')})
        self.assertIn('label: 0', code)
        self.assertNotIn('label: props.value', code)
        self.assertEqual(renderer.component_reuse.instances[0]['property_parameters'], {})
        self.assertFalse(result['generation_complete'])

    def test_positional_omission_marker_is_rejected_for_struct_properties(self):
        from ui_migration.contracts.component_reuse import validate_reuse
        from ui_migration.frontend.component_reuse import ComponentAdapter, ComponentReuse
        definition = {'id':'caption', 'component_kind':'project_component',
                      'identity':{'qualified_name':'example.Caption'}, 'parameters':[{'name':'label','type':'String'}]}
        node = {'definition_id':'caption', 'invocation_bindings':{'label':'"Hi"'}}
        reuse = ComponentReuse([ComponentAdapter('test','example.Caption','@ui/lib','Caption',{'label':'label'})], [definition])
        record = reuse.resolve(node, lambda *args: 'Hi')
        record['properties']['label'] = {'kind':'omitted_argument'}
        with self.assertRaises(ValueError):
            validate_reuse(record)

    def test_builder_function_positional_order(self):
        _, code, result, renderer = self.generate('Caption("Hi", 2)',
            '@Composable fun Caption(label: String, count: Int) { Text(label) }',
            {'Caption.ets':'@Builder\nexport function Caption(count: number, label: string) {\n Text(label)\n }'})
        self.assertIn('ReusedCaption(0, "")', code)
        self.assertFalse(result['generation_complete'])

    def test_color_resource_and_dimension(self):
        from test_property_resources import EXTENSION
        _, code, result, renderer = self.generate('Badge(company.DeclarativeTheme.colors.primary, 24.dp)',
            '@Composable fun Badge(color: Color, size: Dp) { Canvas(Modifier.size(size)) {} }',
            {'Badge.ets':component('Badge', '@Prop color: ResourceColor = Color.Red\n@Prop size: number = 24')}, EXTENSION)
        self.assertNotIn('.color("primary")', code)
        self.assertEqual(renderer.component_reuse.instances[0]['properties'], {})
        self.assertNotIn('Canvas(', code)
        self.assertFalse(result['generation_complete'])

    def test_preserve_states_does_not_reexpand_reused_internals(self):
        _, code, result, renderer = helpers.KeyedResourcesTest.generate(self,
            'Caption(true)', '''@Composable fun Caption(loading: Boolean) {
if (loading) { Canvas(Modifier.size(24.dp)) {} } else { Text("Internal") }
}''', 'ADAPTERS = []', harmony_files={'Caption.ets':component(fields='@Prop loading: boolean = false')},
            preserve_component_ui_states=True)
        self.assertIn('ReusedCaption({  })', code)
        self.assertNotIn('Canvas(', code)
        self.assertFalse(result['generation_complete'])


if __name__ == '__main__':
    unittest.main()
