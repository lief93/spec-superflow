import unittest

from generate_lanhu_source_page import UNRESOLVED, evaluate_expression
import test_ui_state_semantics as semantics


class StructuredValueEvaluationTest(unittest.TestCase):
    def test_scaffold_default_uses_background_role_not_surface_or_white(self):
        helper = semantics.UiStateSemanticsTest()
        source = helper.source('Scaffold { Text("Content") }')
        page = helper.strict(source, {'MaterialTheme.colorScheme.background': '#FFF4F7FB',
                                      'MaterialTheme.colorScheme.onBackground': '#FF101D2D'})
        scaffold = next(n for n in page['components'] if n['type'] == 'Scaffold')
        self.assertEqual(scaffold['style']['surface']['background'], {'type': 'solid', 'color': '#FFF4F7FB'})
    def test_forwarded_style_argument_keeps_callers_import_scope(self):
        import tempfile
        from pathlib import Path
        from analyze_compose_project import analyze
        from real_page_pipeline import build_source_page_spec
        files = {
            'Page.kt': '''package screen
import first.ink
import widget.Caption
@Composable fun Page() { Caption(color = ink()) }
''',
            'Caption.kt': '''package widget
@Composable fun Caption(color: Color) { Text("Caption", color = color) }
''',
            'First.kt': 'package first\nfun ink(): Color = Color(0xFF112233)',
            'Second.kt': 'package second\nfun ink(): Color = Color(0xFF556677)',
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, content in files.items():
                (root / name).write_text(content)
            source = build_source_page_spec(analyze(root, {}, files), 'Page.kt', 'Page',
                                            'page', 'default', 'a' * 64, root)
        page = semantics.UiStateSemanticsTest().strict(source, {})
        text = next(n for n in page['components'] if n['type'] == 'Text')
        self.assertEqual(text['style']['typography']['color'], '#FF112233')

    def test_remember_pure_layout_values_and_collection_predicates(self):
        cases = [
            ('remember(ink) { Color(android.graphics.Color.parseColor(ink)) }', {'ink': '#123456'}, '#FF123456'),
            ('remember(tags) { tags.split(",").map { it.trim() }.filter { it.isNotEmpty() } }',
             {'tags': ' one, ,two '}, ['one', 'two']),
            ('selected.contains(id)', {'selected': [], 'id': 2}, False),
            ('remember(items) { items.any { unknown(it) } }', {'items': []}, False),
            ('remember(items) { items.any { it.enabled } }', {'items': [{'enabled': False}, {'enabled': True}]}, True),
        ]
        for expression, values, expected in cases:
            with self.subTest(expression=expression):
                self.assertEqual(evaluate_expression(expression, values), expected)
        self.assertIs(evaluate_expression('remember { network() }', {}), UNRESOLVED)
        self.assertIs(evaluate_expression('items.filter { unknown(it) }', {'items': [1]}), UNRESOLVED)

    def test_lazy_source_collection_membership_preserves_selected_ui_branch(self):
        expression = 'lazy { mapOf("A" to listOf("one", "two")).values.flatten().toSet() + setOf("three") }'
        self.assertEqual(evaluate_expression(expression, {}), frozenset(['one', 'two', 'three']))
        self.assertIs(evaluate_expression('lazy { network() }', {}), UNRESOLVED)

    def test_border_stroke_overload_reaches_surface_and_modifier(self):
        helper = semantics.UiStateSemanticsTest()
        page = helper.strict(helper.source('''Column {
            Box(Modifier.size(44.dp).border(BorderStroke(1.dp, Color(0x66C2C7D0)), CircleShape)) {}
            Card(border = BorderStroke(1.dp, if (selected) Color.Black else Color(0x66112233))) { Text("Row") }
        }'''), {'selected': False})
        nodes = [n for n in page['components'] if n['type'] in ('Box', 'Card')]
        self.assertEqual([n['style']['surface']['border'] for n in nodes],
                         [{'width_dp': 1, 'color': '#66C2C7D0', 'style': 'solid'},
                          {'width_dp': 1, 'color': '#66112233', 'style': 'solid'}])

    def test_source_color_overloads_use_real_luminance_and_scoped_constants(self):
        helper = semantics.UiStateSemanticsTest()
        source = helper.source('Text("Contrast", color = contrasting(Color(0xFF00BFA5)))', '''
val lightInk = Color(0xFFFAFAFA)
val darkInk = Color(0xFF111114)
fun contrasting(color: Color): Color = if (dark(color.toArgb())) lightInk else darkInk
fun dark(color: Color): Boolean = dark(color.toArgb())
fun dark(color: Int): Boolean = ColorUtils.calculateLuminance(color) <= 0.5
''')
        for function in source['source_functions']:
            function.setdefault('imports', {})['ColorUtils'] = 'androidx.core.graphics.ColorUtils'
        page = helper.strict(source, {})
        self.assertEqual(next(n for n in page['components'] if n['type']=='Text')['style']['typography']['color'], '#FFFAFAFA')

    def test_static_icon_and_callback_nullness_do_not_require_image_pixels_or_execution(self):
        values = {'__source_imports': {'Icons': 'androidx.compose.material.icons.Icons'}}
        self.assertTrue(evaluate_expression('Icons.Rounded.Search != null', values))
        self.assertTrue(evaluate_expression('{ runNetworkAction() } != null', values))
        self.assertIs(evaluate_expression('Other.UnknownIcon != null', values), UNRESOLVED)

    def test_import_disambiguates_same_named_source_extension(self):
        from kotlin_psi import parse_expression
        functions = [{'name': 'toInk', 'package': package, 'source': package + '.kt',
                      'line': 1, 'receiver': 'Int', 'parameters': [], 'body': parse_expression(body)}
                     for package, body in [('first', 'Color(this)'), ('second', 'Color.Black')]]
        values = {'__source_functions': functions, '__source_imports': {'toInk': 'first.toInk'}}
        self.assertEqual(evaluate_expression('0xFF00BFA5.toInk()', values), '#FF00BFA5')
        self.assertIs(evaluate_expression('0xFF00BFA5.toInk()', {'__source_functions': functions}), UNRESOLVED)

    def test_framework_arguments_use_nested_fixed_values_not_literal_patterns(self):
        cases = [
            ('Color(value = if (active) ink else 0xFF000000)', {'active': True, 'ink': 0xFF123456}, '#FF123456'),
            ('items /* comment */ . isNotEmpty ( )', {'items': [1]}, True),
            ('model?.asString()', {'model': None}, None),
            ('stringResource(id = if (active) R.string.title else R.string.other)',
             {'active': True, 'R.string.title': 'Selected'}, 'Selected'),
            ('(ratio * 100).toInt().toString()', {'ratio': 0.125}, '12'),
            ('"Hello $name: ${if (active) "yes" else "no"}"', {'name': 'Sam', 'active': True}, 'Hello Sam: yes'),
            ('"\\$name"', {'name': 'Sam'}, '$name'),
            ('ImageRequest.Builder(context).data(if (active) photo else null).build()',
             {'active': True, 'photo': 'portrait'}, 'portrait'),
            ('DpSize(width = (base + 4).dp, height = 20.dp).width', {'base': 8}, 12),
        ]
        for expression, values, expected in cases:
            with self.subTest(expression=expression):
                self.assertEqual(evaluate_expression(expression, values), expected)

    def test_unknowns_are_not_resource_names_or_stringified_placeholders(self):
        for expression in ['UiText.StringResource(missing)', '"Hello $missing"',
                           'unknownFactory(1)', 'Color(value = missing)',
                           'null.asString()', 'missing?.asString()']:
            with self.subTest(expression=expression):
                self.assertIs(evaluate_expression(expression, {}), UNRESOLVED)

    def test_identical_values_reach_text_style_and_modifier_paths(self):
        helper = semantics.UiStateSemanticsTest()
        source = helper.source('Caption(active = selected)', '''
@Composable
fun Caption(active: Boolean) {
    val ink = if (active) 0xFF123456 else 0xFF654321
    Text("Caption", color = Color(value = ink),
        modifier = Modifier.background(Color(value = ink)).padding(
            if (items /* size */ . isNotEmpty ( )) 12.dp else 4.dp))
}
''')
        for selected, items, color, padding in [(True, [1], '#FF123456', 12),
                                               (False, [], '#FF654321', 4)]:
            page = helper.strict(source, {'selected': selected, 'items': items})
            text = next(n for n in page['components'] if n['type'] == 'Text')
            self.assertEqual(text['style']['typography']['color'], color)
            self.assertEqual(text['style']['surface']['background'], {'type': 'solid', 'color': color})
            self.assertEqual(text['style']['layout']['padding_dp']['top'], padding)

    def test_binding_expands_nested_arguments_without_scanning_api_spellings(self):
        from ui_migration.frontend.bindings import bind_source_expression, resolved_dp_expression
        bindings = {'base': '8.dp', 'gap': 'base + 4.dp', 'outer': 'inner',
                    'inner': 'Modifier.padding(horizontal = gap).fillMaxWidth()'}
        self.assertEqual(resolved_dp_expression('gap * 2', bindings), 24)
        self.assertEqual(bind_source_expression('outer', bindings),
                         'Modifier.padding(horizontal = 12.dp).fillMaxWidth()')

    def test_source_factories_share_positional_named_and_default_scopes(self):
        values = {'__source_value_inventory': {'classes': [{
            'name': 'Card', 'properties': [{'name': 'title'}, {'name': 'count'}],
            'factories': [{'name': 'sample', 'static_record': True,
                           'parameters': [{'name': 'title', 'default': '"A"'},
                                          {'name': 'count', 'default': '2'}],
                           'local_values': {'display': '"Card $title"'},
                           'return_expression': 'Card(display, count + 1)'}],
        }]}}
        self.assertEqual(evaluate_expression('Card.sample(count = 4)', values), {'title': 'Card A', 'count': 5})
        self.assertEqual(evaluate_expression('Card /* factory */ . sample("B", 2)', values),
                         {'title': 'Card B', 'count': 3})

    def test_forwarded_collection_uses_bound_receiver_not_literal_fixture_key(self):
        from ui_migration.frontend.bindings import bind_source_expression
        expression = bind_source_expression('items.data.orEmpty()',
                                             {'items': 'viewModel.items.collectAsStateWithLifecycle()'})
        values = {'viewModel.items.collectAsStateWithLifecycle()': {'data': [1, 2]}}
        self.assertEqual(evaluate_expression(expression, values), [1, 2])
        self.assertFalse(evaluate_expression(expression + '.isEmpty()', values))
        self.assertIs(evaluate_expression('missing.orEmpty()', {}), UNRESOLVED)

    def test_unsupported_calls_do_not_execute_or_change_branch_visibility(self):
        expression = 'if (false) unknownFactory() else "Visible"'
        self.assertEqual(evaluate_expression(expression, {}), 'Visible')
        self.assertIs(evaluate_expression('if (missing) 12.dp else 4.dp', {}), UNRESOLVED)
        self.assertIs(evaluate_expression('"${unknownFactory()}"', {}), UNRESOLVED)
        values = {'record': {'title': 'Known', 'unknown': UNRESOLVED}}
        self.assertEqual(evaluate_expression('record.title', values), 'Known')
        self.assertIs(evaluate_expression('"${record.unknown}"', values), UNRESOLVED)

    def test_dimensionless_shape_overload_is_not_misreported_as_dp(self):
        self.assertEqual(evaluate_expression('RoundedCornerShape(40.dp)', {}),
                         {'kind': 'rounded_corner', 'radius_dp': 40})
        self.assertEqual(evaluate_expression('RoundedCornerShape(40)', {}),
                         {'kind': 'rounded_corner', 'radius_percent': 40})
        self.assertIs(evaluate_expression('RoundedCornerShape(40.sp)', {}), UNRESOLVED)

    def test_declared_string_resources_reach_visibility_and_display_in_same_scope(self):
        helper = semantics.UiStateSemanticsTest()
        source = helper.source('Header(UiText.StringResource(R.string.edit))', '''
@Composable
fun Header(actionLabel: UiText?) {
    Row { if (actionLabel != null) { Text(actionLabel.asString()) } }
}
''')
        source['source_string_resources'] = {'R.string.edit': 'Edit'}
        page = helper.strict(source, {})
        self.assertEqual([node['style']['content']['text'] for node in page['components'] if node['type']=='Text'], ['Edit'])


if __name__ == '__main__':
    unittest.main()
