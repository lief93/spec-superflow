import tempfile
import unittest
from pathlib import Path

from analyze_compose_project import analyze
from real_page_pipeline import build_source_page_spec
from test_layout_mapping_contract import render_nodes


ROOT = 'app/src/main/java/example/Page.kt'


class DpSizeTest(unittest.TestCase):
    def source_page(self, body, declarations=''):
        source = '''package example
import androidx.compose.runtime.Composable
import androidx.compose.foundation.layout.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.DpSize
import androidx.compose.ui.unit.dp
@Composable
fun Page() {
''' + body + '\n}\n' + declarations
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / ROOT
            path.parent.mkdir(parents=True)
            path.write_text(source)
            contract = analyze(root, {}, {ROOT: source})
            return build_source_page_spec(contract, ROOT, 'Page', 'page', 'default', 'a' * 64, root)

    def assert_size(self, page, width, height):
        box = next(n for n in page['components'] if n['type'] == 'Box')
        self.assertEqual(box['style']['layout']['width_dp'], width)
        self.assertEqual(box['style']['layout']['height_dp'], height)
        output, gate, renderer = render_nodes(page['components'])
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        self.assertEqual(renderer.unresolved, [])
        self.assertIn(f'.width(this.layoutPx({width}))', output)
        self.assertIn(f'.height(this.layoutPx({height}))', output)
        self.assertNotIn('.position(', output)

    def test_official_dp_size_overload_reaches_json_and_arkui(self):
        self.assert_size(self.source_page('Box(Modifier.size(DpSize(90.dp, 60.dp))) {}'), 90, 60)

    def test_default_size_is_forwarded_through_business_components(self):
        page = self.source_page('CardSection()', '''
@Composable
fun CardSection(size: DpSize = DpSize(width = 90.dp, height = 60.dp)) {
    SmallCard(cardSize = size)
}
@Composable
fun SmallCard(cardSize: DpSize) {
    Box(Modifier.size(cardSize)) {}
}
''')
        self.assert_size(page, 90, 60)

    def test_caller_local_alias_overrides_default_through_two_scopes(self):
        page = self.source_page('''
val width = 108.dp
val dimensions = DpSize(height = 72.dp, width = width)
val alias = dimensions
CardSection(size = alias)
''', '''
@Composable
fun CardSection(size: DpSize = DpSize(90.dp, 60.dp)) {
    val forwarded = size
    SmallCard(cardSize = forwarded)
}
@Composable
fun SmallCard(cardSize: DpSize) {
    Box(Modifier.size(cardSize)) {}
}
''')
        self.assert_size(page, 108, 72)

    def test_official_argument_forms_and_existing_scalar_overloads(self):
        for expression in (
            'DpSize(height = 60.dp, width = 90.dp)',
            'DpSize(90.dp, height = 60.dp)',
            'size = DpSize(90.dp, 60.dp)',
            'androidx.compose.ui.unit.DpSize(90.dp, 60.dp)',
            'width = 90.dp, height = 60.dp',
            '90.dp, 60.dp',
        ):
            with self.subTest(expression=expression):
                self.assert_size(self.source_page(f'Box(Modifier.size({expression})) {{}}'), 90, 60)
        self.assert_size(self.source_page('Box(Modifier.size(48.dp)) {}'), 48, 48)

    def test_repeated_component_calls_keep_independent_values(self):
        page = self.source_page('''Column {
    Tile()
    Tile(DpSize(120.dp, 80.dp))
}''', '''
@Composable
fun Tile(size: DpSize = DpSize(90.dp, 60.dp)) {
    Box(Modifier.size(size)) {}
}
''')
        boxes = [n for n in page['components'] if n['type'] == 'Box']
        self.assertEqual([(n['style']['layout']['width_dp'], n['style']['layout']['height_dp'])
                          for n in boxes], [(90, 60), (120, 80)])
        self.assertEqual(len({n['id'] for n in boxes}), 2)
        output, gate, _ = render_nodes(page['components'])
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        for value in (90, 60, 120, 80):
            self.assertIn(f'this.layoutPx({value})', output)

    def test_unknown_and_cyclic_sizes_retain_control_without_fake_dimensions(self):
        for expression, declarations in (
            ('loadSize()', ''),
            ('DpSize.Unspecified', ''),
            ('alias', 'val alias = missing'),
            ('first', 'val first = second\nval second = first'),
            ('DpSize(loadWidth(), 60.dp)', ''),
        ):
            with self.subTest(expression=expression):
                page = self.source_page(declarations + f'\nBox(Modifier.size({expression})) {{}}')
                box = next(n for n in page['components'] if n['type'] == 'Box')
                self.assertIsNone(box['style']['layout']['width_dp'])
                output, gate, renderer = render_nodes(page['components'])
                self.assertEqual(gate['verdict'], 'fail')
                self.assertIn(f".id('{box['semantic_key']}')", output)
                self.assertTrue(renderer.unresolved)

    def test_default_constructor_uses_overridden_dimension_parameters(self):
        page = self.source_page('CardSection(width = 120.dp)', '''
@Composable
fun CardSection(width: Dp = 90.dp, size: DpSize = DpSize(width, 60.dp)) {
    SmallCard(size)
}
@Composable
fun SmallCard(size: DpSize) {
    Box(Modifier.size(size)) {}
}
''')
        self.assert_size(page, 120, 60)

    def test_size_member_dimensions_preserve_units(self):
        page = self.source_page('''
val dimensions = DpSize(90.dp, 60.dp)
Box(Modifier.size(width = dimensions.width, height = dimensions.height)) {}
''')
        self.assert_size(page, 90, 60)

    def test_callee_default_does_not_capture_same_named_caller_parameter(self):
        page = self.source_page('Outer()', '''
@Composable
fun Outer(width: Dp = 200.dp) {
    CardSection()
}
@Composable
fun CardSection(width: Dp = 90.dp, size: DpSize = DpSize(width, 60.dp)) {
    Box(Modifier.size(size)) {}
}
''')
        self.assert_size(page, 90, 60)

    def test_modifier_argument_captures_size_before_entering_child_scope(self):
        page = self.source_page('CardSection()', '''
@Composable
fun CardSection(cardSize: DpSize = DpSize(90.dp, 60.dp)) {
    SmallCard(modifier = Modifier.size(cardSize).padding(16.dp))
}
@Composable
fun SmallCard(modifier: Modifier) {
    Box(modifier) {}
}
''')
        self.assert_size(page, 90, 60)
        box = next(n for n in page['components'] if n['type'] == 'Box')
        self.assertEqual([m['name'] for m in box['modifiers']], ['size', 'padding'])

    def test_outer_padding_keeps_its_position_when_size_is_forwarded(self):
        page = self.source_page('CardSection()', '''
@Composable
fun CardSection(cardSize: DpSize = DpSize(90.dp, 60.dp)) {
    SmallCard(Modifier.padding(16.dp).size(cardSize))
}
@Composable
fun SmallCard(modifier: Modifier) {
    Box(modifier = modifier) {}
}
''')
        box = next(n for n in page['components'] if n['type'] == 'Box')
        self.assertEqual([m['name'] for m in box['modifiers']], ['padding', 'size'])
        output, _, renderer = render_nodes(page['components'])
        inner = next(n for n in renderer.android_page_by_id.values()
                     if n['style']['layout']['width_dp'] == 90 and not n['source']['custom_component'])
        parent = renderer.android_page_by_id[inner['parent_id']]
        self.assertEqual(inner['style']['layout']['height_dp'], 60)
        self.assertEqual(parent['style']['layout']['padding_dp'], dict(left=16, right=16, top=16, bottom=16))
        self.assertIn('.width(this.layoutPx(90))', output)

    def test_nested_then_captures_dimensions_without_rewriting_string_literals(self):
        page = self.source_page('CardSection()', '''
@Composable
fun CardSection(cardSize: DpSize = DpSize(90.dp, 60.dp)) {
    SmallCard(Modifier.then(Modifier.size(cardSize)).testTag("literal.size(cardSize)"))
}
@Composable
fun SmallCard(modifier: Modifier) {
    Box(modifier = modifier) {}
}
''')
        box = next(n for n in page['components'] if n['type'] == 'Box')
        self.assertEqual(box['style']['layout']['width_dp'], 90)
        self.assertEqual(box['style']['layout']['height_dp'], 60)
        self.assertIn('literal.size(cardSize)', box['parameter_bindings']['modifier'])


if __name__ == '__main__':
    unittest.main()
