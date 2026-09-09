import argparse
import json
from pathlib import Path
import tempfile
import unittest

from analyze_compose_project import analyze
from real_page_pipeline import build_source_page_spec
from generate_lanhu_source_page import generate
from generate_arkui_page import Renderer, load_lanhu_page_input, derive_page_root
from ui_migration.common import ArkUIPageError


def compile_page(code):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / 'Page.kt').write_text(code)
        contract = analyze(root, {}, {'Page.kt': code})
        source = build_source_page_spec(contract, 'Page.kt', 'Page', 'page', 'default', 'a' * 64, root)
        path = root / 'source.json'
        path.write_text(json.dumps(source))
        generate(argparse.Namespace(source_page=path, state_fixture=None,
            output_dir=root / 'page', viewport_width_dp=360, viewport_height_dp=740,
            slice_scale=2, device='component-test'))
        version = json.loads((root / 'page/version_json.json').read_text())
        (root / 'Page.kt').unlink()
        path.unlink()
        page = load_lanhu_page_input(root / 'page/version_json.json')
        renderer = Renderer(derive_page_root(page), set(), {}, page)
        output = renderer.render()
        return source, version, page, renderer, output


class BusinessComponentsTest(unittest.TestCase):
    def test_overloaded_business_components_keep_separate_bodies_and_bindings(self):
        _, _, page, _, output = compile_page('''
@Composable fun Page() { Column { Badge(label = "First"); Badge(value = 2) } }
@Composable fun Badge(label: String) { Badge(value = 1); Text(label) }
@Composable fun Badge(value: Int) { if (value == 1) { Text("Number 1") } else { Text("Number 2") } }
''')
        definitions = [d for d in page['component_definitions'] if d['type']=='Badge']
        self.assertEqual(len(definitions), 2)
        self.assertTrue(all(d['component_kind']=='project_component' for d in definitions))
        for text in ('First', 'Number 1', 'Number 2'):
            self.assertIn(text, output)

    def test_scaffold_business_slot_attributes_belong_to_native_host(self):
        _, _, _, _, output = compile_page('''
@Composable fun Page() { Scaffold(topBar = { Header() }) { Body() } }
@Composable fun Header() { Text("Header") }
@Composable fun Body() { Text("Body") }
''')
        import re
        self.assertFalse(re.search(r'this\.business[^\n]+\n\s+\.align\(', output), output)
        self.assertIn('scaffold0Topbar = Number(area.height)', output)

    CODE = '''
@Composable fun Page() { Column { Caption("One"); Caption("Two") } }
@Composable fun Caption(label: String) { Text(label) }
'''

    def test_single_json_retains_definition_body_and_parameter_bindings(self):
        source, version, page, _, _ = compile_page(self.CODE)
        definitions = version['meta']['migration']['componentDefinitions']
        caption = next(d for d in definitions if d['type'] == 'Caption')
        self.assertEqual(caption['parameters'][0]['name'], 'label')
        self.assertEqual(caption['ui_template']['calls'][0]['component'], 'Text')
        instances = [n for n in page['components'] if n['type'] == 'Caption']
        self.assertEqual(len(instances), 2)
        self.assertEqual({n['definition_id'] for n in instances}, {caption['id']})
        self.assertEqual([n['invocation_bindings']['label'] for n in instances], ['"One"', '"Two"'])
        for instance in instances:
            child = page['by_id'][instance['children_ids'][0]]
            self.assertEqual(child['component_context']['business_component_id'], instance['id'])

    def test_repeated_component_is_one_builder_with_distinct_arguments(self):
        _, _, _, renderer, output = compile_page(self.CODE)
        report = renderer.business_components.report()
        self.assertEqual(report['definition_count'], 1)
        self.assertEqual(report['instance_count'], 2)
        self.assertEqual(report['builder_count'], 1, report)
        self.assertEqual(output.count('Text('), 1, output)
        self.assertIn("'One'", output)
        self.assertIn("'Two'", output)
        self.assertIn('Text(props.', output)

    def test_nested_components_and_multiple_roots_are_not_wrapped_in_stacks(self):
        _, _, _, renderer, output = compile_page('''
@Composable fun Page() { Row { PairLabel("A"); PairLabel("B") } }
@Composable fun PairLabel(label: String) { Caption(label); Spacer(Modifier.width(12.dp)); Caption("suffix") }
@Composable fun Caption(label: String) { Text(label) }
''')
        report = renderer.business_components.report()
        self.assertEqual(report['definition_count'], 2)
        self.assertEqual(report['instance_count'], 6)
        self.assertEqual(output.count('Text('), 1, output)
        self.assertEqual(output.count('Row()'), 1)
        self.assertEqual(output.count('Stack()'), 2, output)
        self.assertIn('Blank()', output)

    def test_caller_slots_are_parameters_not_inlined_into_business_body(self):
        _, _, _, renderer, output = compile_page('''
@Composable fun Page() { Column { Shell { Text("First"); Text("Second") }; Shell { Row { Text("Third") } } } }
@Composable fun Shell(content: @Composable () -> Unit) { Column(Modifier.padding(12.dp)) { content() } }
''')
        report = renderer.business_components.report()
        shell = [d for d in report['definitions'] if d['symbol'] == 'Shell'][0]
        self.assertEqual(shell['builder_count'], 1, report)
        self.assertIn('slot0: BusinessSlot', output)
        self.assertIn('this.renderBusinessSlot(slot0)', output)
        self.assertNotIn('slot0()', output)

    def test_missing_definition_is_not_silently_flattened(self):
        _, _, page, _, _ = compile_page(self.CODE)
        page['component_definitions'] = []
        with self.assertRaisesRegex(ArkUIPageError, 'missing project component definition'):
            Renderer(derive_page_root(page), set(), {}, page).render()

    def test_duplicate_definition_is_rejected(self):
        _, _, page, _, _ = compile_page(self.CODE)
        page['component_definitions'].append(page['component_definitions'][0])
        with self.assertRaisesRegex(ArkUIPageError, 'duplicate component definition'):
            Renderer(derive_page_root(page), set(), {}, page)

    def test_render_is_repeatable_and_registry_does_not_leak_across_pages(self):
        _, _, _, renderer, output = compile_page(self.CODE)
        self.assertEqual(renderer.render(), output)
        _, _, _, next_renderer, next_output = compile_page('''
@Composable fun Page() { Caption("Other") }
@Composable fun Caption(label: String) { Text(label) }
''')
        self.assertNotIn("'One'", next_output)
        self.assertEqual(next_renderer.business_components.report()['instance_count'], 1)

    def test_style_specializations_preserve_both_invocations_and_explain_count(self):
        _, _, _, renderer, output = compile_page('''
@Composable fun Page() { Row { Caption("A", 12.dp); Caption("B", 24.dp) } }
@Composable fun Caption(label: String, inset: Dp) { Text(label, Modifier.padding(inset)) }
''')
        report = renderer.business_components.report()
        self.assertEqual(report['definition_count'], 1)
        self.assertEqual(report['instance_count'], 2)
        self.assertEqual(report['definitions'][0]['specialization_count'], 2)
        self.assertIn('.padding(this.layoutPx(12))', output)
        self.assertIn('.padding(this.layoutPx(24))', output)

    def test_weight_and_alignment_keep_original_parent_scope(self):
        _, _, _, _, output = compile_page('''
@Composable fun Page() { Row { Caption("A", Modifier.weight(1f)); Caption("B", Modifier.weight(2f)) } }
@Composable fun Caption(label: String, modifier: Modifier) { Text(label, modifier = modifier) }
''')
        self.assertIn('.layoutWeight(1)', output)
        self.assertIn('.layoutWeight(2)', output)
        self.assertEqual(output.count('Row()'), 1)
        self.assertEqual(output.count('Stack()'), 2)

    def test_same_line_multiple_roots_keep_source_order_not_component_name_order(self):
        _, _, page, _, _ = compile_page('''
@Composable fun Page() { Pair() }
@Composable fun Pair() { Label("First"); Spacer(Modifier.height(12.dp)); Label("Last") }
@Composable fun Label(text: String) { Text(text) }
''')
        pair = next(n for n in page['components'] if n['type'] == 'Pair')
        self.assertEqual([page['by_id'][key]['type'] for key in pair['children_ids']],
                         ['Label', 'Spacer', 'Label'])


if __name__ == '__main__':
    unittest.main()
