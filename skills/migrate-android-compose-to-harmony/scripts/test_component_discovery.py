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
        self.assertIn('ReusedCaption({ label: "Hello" })', code)
        self.assertNotIn('Android internals', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved)
        self.assertEqual(renderer.test_phase_gate['verdict'], 'pass')
        self.assertEqual(result['discovery']['decisions'][0]['status'], 'matched')

    def test_no_match_keeps_original(self):
        _, code, result, renderer = self.generate(files={'Other.ets':component('Other')})
        self.assertIn('Android internals', code)
        self.assertFalse(renderer.component_reuse.instances)
        self.assertEqual(result['discovery']['decisions'][0]['status'], 'not-found')

    def test_incompatible_same_name_is_not_reused(self):
        _, code, result, renderer = self.generate(files={'Caption.ets':component(fields='@Prop label: number = 0')})
        self.assertIn('Android internals', code)
        self.assertFalse(renderer.component_reuse.instances)
        self.assertFalse(result['generation_complete'])
        self.assertIn('String -> number', str(result['unresolved']))

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

    def test_slots_stay_caller_owned(self):
        page, code, result, renderer = self.generate('Shell { Text("Caller", color = Color.Black) }',
            '@Composable fun Shell(content: @Composable () -> Unit) { Column { Text("Internal"); content() } }',
            {'Shell.ets':component('Shell', '@BuilderParam content: () => void')})
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertNotIn('Internal', code)
        self.assertIn('content: () => { this.renderShellContent(', code)
        self.assertEqual(len(renderer.component_reuse.instances), 1)
        shell = next(n for n in page['components'] if n['type'] == 'Shell')
        self.assertEqual(shell['source']['component_reuse']['slots']['content'], shell['children_ids'])
        self.assertFalse(renderer.unresolved)

    def test_unresolved_value_reports_reuse_failure(self):
        _, code, result, _ = self.generate('Caption(missing)')
        self.assertNotIn('ReusedCaption', code)
        self.assertIn('component parameter is unresolved', str(result['unresolved']))

    def test_defaults_repetition_and_forwarding(self):
        _, code, result, renderer = self.generate('Column { Caption(); Outer("Two") }', '''
@Composable fun Outer(value: String) { Caption(value) }
@Composable fun Caption(label: String = "Default") { Text("Internal") }
''')
        self.assertIn('label: "Default"', code)
        self.assertIn('label: props.value', code)
        self.assertEqual(len(renderer.component_reuse.instances), 2)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_empty_callback_preserved_not_invented(self):
        _, code, result, renderer = self.generate('Action(onAction = {})',
            '@Composable fun Action(onAction: () -> Unit) { Text("Internal") }',
            {'Action.ets':component('Action', 'onAction: () => void = () => {}')})
        self.assertIn('onAction: () => {}', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved)

    def test_nonempty_callback_is_not_replaced_by_empty(self):
        _, code, result, renderer = self.generate('Action(onAction = { business() })',
            '@Composable fun Action(onAction: () -> Unit) { Text("Internal") }',
            {'Action.ets':component('Action', 'onAction: () => void = () => {}')})
        self.assertFalse(renderer.component_reuse.instances)
        self.assertFalse(result['generation_complete'])

    def test_modifier_does_not_disappear(self):
        _, _, result, renderer = self.generate('Caption("Hi", Modifier.fillMaxWidth())',
            '@Composable fun Caption(label: String, modifier: Modifier) { Text(label) }')
        self.assertFalse(renderer.component_reuse.instances)
        self.assertIn('missing target parameter modifier', str(result['unresolved']))

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
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertEqual(renderer.component_reuse.instances[0]['properties'], {'label':'Hello'})

    def test_inferred_literal_type_and_nullable_type(self):
        _, _, result, renderer = self.generate(files={'Caption.ets':component(fields='@Prop label = ""')})
        self.assertEqual(len(renderer.component_reuse.instances), 1)
        self.assertTrue(result['generation_complete'])
        _, code, result, _ = self.generate('Caption(null)',
            '@Composable fun Caption(label: String?) { Text("Internal") }',
            {'Caption.ets':component(fields='label: string | null = null')})
        self.assertIn('label: null', code)
        self.assertTrue(result['generation_complete'])

    def test_target_candidates_select_by_type(self):
        _, code, result, renderer = self.generate('Caption("Hi")', '''
@Composable fun Caption(label: String) { Text(label) }
''', {'Text.ets':component(), 'Number.ets':component(fields='@Prop label: number = 0')})
        self.assertIn("from '../Text'", code)
        self.assertEqual(len(renderer.component_reuse.instances), 1)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_invalid_declaration_and_model_type_are_not_accepted(self):
        _, _, result, renderer = self.generate(files={'Caption.ets':component(fields='@Prop label: = ""')})
        self.assertFalse(renderer.component_reuse.instances)
        self.assertFalse(result['generation_complete'])
        _, _, result, renderer = self.generate('Caption(model)',
            '@Composable fun Caption(model: Account) { Text("Internal") }',
            {'Caption.ets':component(fields='model: Account')})
        self.assertFalse(renderer.component_reuse.instances)
        self.assertIn('incompatible types Account', str(result['unresolved']))

    def test_required_extra_and_parameter_name_mismatch(self):
        _, _, result, renderer = self.generate(files={'Caption.ets':component(fields='@Require @Prop title: string')})
        self.assertFalse(renderer.component_reuse.instances)
        self.assertIn('missing target parameter label', str(result['unresolved']))

    def test_builder_function_positional_order(self):
        _, code, result, renderer = self.generate('Caption("Hi", 2)',
            '@Composable fun Caption(label: String, count: Int) { Text(label) }',
            {'Caption.ets':'@Builder\nexport function Caption(count: number, label: string) {\n Text(label)\n }'})
        self.assertIn('ReusedCaption(2, "Hi")', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved)

    def test_color_resource_and_dimension(self):
        from test_property_resources import EXTENSION
        _, code, result, renderer = self.generate('Badge(company.DeclarativeTheme.colors.primary, 24.dp)',
            '@Composable fun Badge(color: Color, size: Dp) { Canvas(Modifier.size(size)) {} }',
            {'Badge.ets':component('Badge', '@Prop color: ResourceColor = Color.Red\n@Prop size: number = 24')}, EXTENSION)
        self.assertIn('.color("primary")', code)
        self.assertNotIn('Canvas(', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved)

    def test_preserve_states_does_not_reexpand_reused_internals(self):
        _, code, result, renderer = helpers.KeyedResourcesTest.generate(self,
            'Caption(true)', '''@Composable fun Caption(loading: Boolean) {
if (loading) { Canvas(Modifier.size(24.dp)) {} } else { Text("Internal") }
}''', 'ADAPTERS = []', harmony_files={'Caption.ets':component(fields='@Prop loading: boolean = false')},
            preserve_component_ui_states=True)
        self.assertIn('ReusedCaption({ loading: true })', code)
        self.assertNotIn('Canvas(', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved)


if __name__ == '__main__':
    unittest.main()
