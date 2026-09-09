import unittest

from test_business_components import compile_page
from test_page_roots import source_page, project
from ui_migration.frontend.reference_layout import SourceLayout
from ui_migration.frontend.source_tree import SourceTree


class ComponentOutputRootsTest(unittest.TestCase):
    def test_business_outputs_use_the_actual_parent_layout(self):
        for parent, expected in [('Column', (0, 40)), ('Row', (80, 0)), ('Box', (0, 0))]:
            with self.subTest(parent=parent):
                source = source_page('''
@Composable fun Page() { PARENT { Pair() } }
@Composable fun Pair() { Box(Modifier.size(80.dp, 40.dp)); Box(Modifier.size(80.dp, 40.dp)) }
'''.replace('PARENT', parent))
                selected = project(source)
                tree = SourceTree(selected)
                layout = SourceLayout(tree, 360, 740)
                frames = layout.calculate()
                pair = next(n for n in selected['components'] if n['type'] == 'Pair')
                a, b = [frames[i] for i in pair['children_ids']]
                self.assertEqual((b['x'] - a['x'], b['y'] - a['y']), expected)
                self.assertEqual(pair['parent_id'], tree.root_id)
                self.assertFalse(any('multi-child component measured as overlay' in reason
                                     for reasons in layout.geometry_reasons.values() for reason in reasons))

    def test_parent_spacing_counts_outputs_not_business_wrappers(self):
        selected = project(source_page('''
@Composable fun Page() { Column(verticalArrangement = Arrangement.spacedBy(10.dp)) { Pair(); Pair() } }
@Composable fun Pair() { Leaf(); Leaf() }
@Composable fun Leaf() { Box(Modifier.size(80.dp, 40.dp)) }
'''))
        tree = SourceTree(selected)
        layout = SourceLayout(tree, 360, 740)
        frames = layout.calculate()
        boxes = [n for n in selected['components'] if n['type'] == 'Box']
        self.assertEqual([frames[n['id']]['y'] for n in boxes], [0, 50, 100, 150])
        self.assertEqual(set(frames), set(tree.nodes))
        self.assertEqual(set(layout.measured_sizes), set(tree.nodes))

    def test_standalone_outputs_keep_null_parents_through_json_and_codegen(self):
        source, version, page, _, output = compile_page('''
@Composable fun Page() { Box(Modifier.size(80.dp, 40.dp)); Box(Modifier.size(80.dp, 40.dp)) }
''')
        self.assertEqual(len(source['components']), 2)
        self.assertTrue(all(n['parent_id'] is None for n in page['components']))
        self.assertEqual(len(version['artboard']['layers']), 2)
        projection = version['meta']['sourceGeneration']['stateProjection']
        self.assertEqual(len(projection['active_root_ids']), 2)
        self.assertIsNone(projection['active_root_id'])
        self.assertEqual(projection['root_layout_context'], 'caller_owned')
        # The document's preview Stack is separate from the two source Box outputs.
        self.assertEqual(output.count('Stack()'), 3, output)
        generation = version['meta']['sourceGeneration']
        self.assertFalse(generation['unresolved'])
        self.assertTrue(any(w['path'] == 'layout.root_host' for w in generation['warnings']))
        self.assertEqual(generation['verdict'], 'pass')

    def test_single_business_root_does_not_turn_multiple_outputs_into_a_box(self):
        _, version, _, _, output = compile_page('''
@Composable fun Page() { Pair() }
@Composable fun Pair() { Box(Modifier.size(80.dp, 40.dp)); Box(Modifier.size(80.dp, 40.dp)) }
''')
        self.assertEqual(version['meta']['sourceGeneration']['stateProjection']['root_layout_context'], 'caller_owned')
        self.assertEqual(output.count('Stack()'), 3, output)
        self.assertEqual(version['meta']['sourceGeneration']['verdict'], 'pass')

    def test_caller_owned_roots_do_not_hide_real_unresolved_values(self):
        _, version, _, _, _ = compile_page('''
@Composable fun Page() { Text(unknownTitle); Box(Modifier.size(80.dp, 40.dp)) }
''')
        generation = version['meta']['sourceGeneration']
        self.assertTrue(any(w['path'] == 'layout.root_host' for w in generation['warnings']))
        self.assertTrue(any(u['path'] == 'style.content.text' for u in generation['unresolved']))
        self.assertEqual(generation['verdict'], 'fail')

    def test_cycle_is_not_treated_as_caller_owned_output(self):
        source = project(source_page('@Composable fun Page() { Text("A"); Text("B"); Text("C") }'))
        a, b, _ = source['components']
        a.update(parent_id=b['id'], children_ids=[b['id']])
        b.update(parent_id=a['id'], children_ids=[a['id']])
        with self.assertRaisesRegex(ValueError, 'disconnected|cycle'):
            SourceTree(source)

    def test_root_sibling_order_is_independent_of_inventory_order(self):
        selected = project(source_page('@Composable fun Page() { Text("A"); Text("B") }'))
        expected = [n['id'] for n in selected['components']]
        selected['components'].reverse()
        self.assertEqual(SourceTree(selected).root_ids, expected)

    def test_invalid_parent_is_not_accepted_as_an_independent_output(self):
        source = project(source_page('@Composable fun Page() { Text("A"); Text("B") }'))
        source['components'][1]['parent_id'] = 'missing'
        with self.assertRaisesRegex(ValueError, 'unknown parent'):
            SourceTree(source)


if __name__ == '__main__':
    unittest.main()
