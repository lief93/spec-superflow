import unittest

import test_dp_size
from generate_lanhu_source_page import project_source_page
from generate_ui_state_previews import build_catalog, preview_fixture


class UiStateSemanticsTest(unittest.TestCase):
    def test_inside_image_preserves_logical_intrinsic_size(self):
        from test_layout_mapping_contract import render_nodes
        page = self.strict(self.source('Image(painterResource(R.drawable.logo), null, Modifier.fillMaxWidth(), contentScale = ContentScale.Inside)'), {})
        node = next(n for n in page['components'] if n['type'] == 'Image')
        node['style']['asset'].update(resource='logo', width_dp=80, height_dp=24)
        output, _, _ = render_nodes([node], resources={'media:logo'})
        self.assertNotIn('ImageFit.ScaleDown', output)
        self.assertIn('.width(80)', output)
        self.assertIn('.height(24)', output)

    def test_top_app_bar_actions_use_their_own_content_color(self):
        source = self.source('CenterAlignedTopAppBar(title = { Text("Title") }, navigationIcon = { Icon(painterResource(R.drawable.logo), null) }, actions = { Icon(painterResource(R.drawable.search), null) })')
        page = self.strict(source, {'MaterialTheme.colorScheme.onSurface':'#FF201A1A',
                                   'MaterialTheme.colorScheme.onSurfaceVariant':'#FF524343'})
        icons = [n for n in page['components'] if n['type'] == 'Icon']
        self.assertEqual([n['style']['asset']['tint'] for n in icons], ['#FF201A1A', '#FF524343'])

    def test_scaffold_padding_survives_parameterized_slot(self):
        source = self.source('Scaffold(topBar = { Text("Header") }) { inset -> Shell(inset) }', '''
@Composable fun Shell(inset: PaddingValues) { LazyColumn(contentPadding = inset) { item { Text("Body") } } }
''')
        page = self.strict(source, {})
        body = next(n for n in page['components'] if n['type'] == 'LazyColumn')
        owner = next(n for n in page['components'] if n['type'] == 'Scaffold')
        self.assertEqual(body['source'].get('scaffold_padding'), {
            'owner_id': owner['id'], 'edges': {'top': 'topBar', 'bottom': 'bottomBar'}})

    def test_composable_slot_binds_callee_arguments_to_caller_lambda(self):
        source = self.source('Shell(state) { entry -> Text(entry.title) }', '''
@Composable fun Shell(value: Ui, content: @Composable (Ui) -> Unit) {
    Column { content(value) }
}
''')
        page = self.strict(source, {'state': {'title': 'Article'}})
        self.assertEqual(self.texts(page), ['Article'])

    def test_named_and_trailing_slots_keep_distinct_parameter_names(self):
        source = self.source('Shell(state, header = { heading -> Text(heading.title) }) { item -> Text(item.subtitle) }', '''
@Composable fun Shell(value: Ui, header: @Composable (Ui) -> Unit, content: @Composable (Ui) -> Unit) {
    Column { header(value); content(value) }
}
''')
        self.assertEqual(self.texts(self.strict(source, {'state': {'title': 'Header', 'subtitle': 'Body'}})), ['Header', 'Body'])

    def test_type_checked_when_argument_preserves_branch_boundaries(self):
        source = self.source('''Gate(empty = when (state) {
            is Ui.Data -> false
            is Ui.Empty -> state.loading
            else -> true
        })''', '''
@Composable fun Gate(empty: Boolean) {
    if (empty) { Text("Empty") } else { Text("Loaded") }
}
''')
        self.assertEqual(self.texts(self.strict(source, {'state':{'__type':'Ui.Data'}})), ['Loaded'])
        self.assertEqual(self.texts(self.strict(source, {'state':{'__type':'Ui.Empty','loading':True}})), ['Empty'])

    def test_selected_painter_replaces_initial_candidate_and_uses_ambient_icon_tint(self):
        source = self.source('Icon(painter = if (selected) painterResource(R.drawable.filled) else painterResource(R.drawable.outline), contentDescription = null)')
        source['source_assets'] = [
            {'resource': name, 'sha256': digest * 64, 'path': name + '.xml'}
            for name, digest in [('filled', 'a'), ('outline', 'b')]]
        page = self.strict(source, {'selected': False, 'LocalContentColor.current': '#FF201A1A'})
        icon = next(n for n in page['components'] if n['type'] == 'Icon')
        self.assertEqual(icon['style']['asset']['resource'], 'outline')
        self.assertEqual(icon['style']['asset']['sha256'], 'b' * 64)
        self.assertEqual(icon['style']['asset']['tint'], '#FF201A1A')
        from page_snapshot import normalize_provenance
        normalize_provenance(icon['provenance'], 'selected icon')

    def test_ambient_content_color_applies_only_without_explicit_color(self):
        page = self.strict(self.source('Column { Text("Ambient"); Text("Explicit", color = Color(0xFFFF0000)) }'),
                           {'LocalContentColor.current': '#FF201A1A'})
        texts = [n for n in page['components'] if n['type'] == 'Text']
        self.assertEqual([n['style']['typography']['color'] for n in texts], ['#FF201A1A', '#FFFF0000'])

    def test_selected_image_refreshes_intrinsic_size_and_hash(self):
        source = self.source('Image(if (selected) painterResource(R.drawable.filled) else painterResource(R.drawable.outline), null)')
        source['source_assets'] = [
            {'resource': name, 'sha256': digest * 64, 'path': name + '.xml',
             'width_dp': size, 'height_dp': size}
            for name, digest, size in [('filled', 'a', 24), ('outline', 'b', 32)]]
        for selected, name, digest, size in [(True, 'filled', 'a', 24), (False, 'outline', 'b', 32)]:
            with self.subTest(selected=selected):
                page = self.strict(source, {'selected': selected})
                asset = next(n for n in page['components'] if n['type'] == 'Image')['style']['asset']
                self.assertEqual((asset['resource'], asset['sha256'], asset['width_dp'], asset['height_dp']),
                                 (name, digest * 64, size, size))

    def test_icon_explicit_tint_and_image_without_tint_do_not_inherit_default(self):
        source = self.source('''Column {
            Icon(painterResource(R.drawable.sample), null, tint = chosenTint)
            Icon(painterResource(R.drawable.sample), null, tint = Color.Unspecified)
            Image(painterResource(R.drawable.sample), null)
            Image(painterResource(R.drawable.sample), null, colorFilter = ColorFilter.tint(chosenTint))
        }''')
        page = self.strict(source, {'LocalContentColor.current': '#FF201A1A', 'chosenTint': '#FFFF0000'})
        self.assertEqual([n['style']['asset']['tint'] for n in page['components']
                          if n['type'] in ('Icon', 'Image')], ['#FFFF0000', None, None, '#FFFF0000'])

    def test_unknown_painter_does_not_keep_a_guessed_branch(self):
        source = self.source('Image(if (selected) painterResource(R.drawable.filled) else painterResource(R.drawable.outline), null, Modifier.size(48.dp))')
        page = self.strict(source, {})
        image = next(n for n in page['components'] if n['type'] == 'Image')
        self.assertIsNone(image['style']['asset']['resource'])
        self.assertIsNone(image['style']['asset']['sha256'])
        self.assertEqual(image['style']['layout']['width_dp'], 48)
        self.assertTrue(any(u['path'] == 'style.asset.resource' for u in image['unresolved']))

    def test_divider_theme_color_and_thickness_are_projected_to_control_fields(self):
        source = self.source('HorizontalDivider(color = shade.copy(alpha = 0.08f), thickness = lineWidth)',
                             'val lineWidth = 2.dp')
        page = self.strict(source, {'shade': '#FF201A1A'})
        divider = next(n for n in page['components'] if n['type'] == 'HorizontalDivider')
        self.assertEqual(divider['style']['control']['active_color'], '#14201A1A')
        self.assertEqual(divider['style']['control']['stroke_width_dp'], 2)
        self.assertIsNone(divider['style']['typography']['color'])
        self.assertFalse([f for f in divider['required_facts']
                          if f['path'].startswith('source.arguments') and f['status'] == 'unresolved'])

    def test_icon_button_external_padding_extends_both_minimum_axes(self):
        from test_layout_mapping_contract import render_nodes
        for kind, arguments in [('IconButton', 'onClick = {}'),
                                ('IconToggleButton', 'checked = false, onCheckedChange = {}')]:
            with self.subTest(kind=kind):
                page = self.strict(self.source(f'''Column {{ {kind}({arguments},
                    modifier = Modifier.clearAndSetSemantics {{}}.padding(horizontal = 6.dp, vertical = 2.dp)) {{
                    Box(Modifier.size(24.dp)) {{}}
                }} }}'''), {})
                output, _, _ = render_nodes(page['components'])
                self.assertIn('minWidth: this.layoutPx(60), minHeight: this.layoutPx(52)', output)

    def test_baked_vector_tint_is_reported_as_consumed(self):
        from test_generate_lanhu_source_page import source_component
        from ui_migration.arkui.leaves import NativeLeafEmitter
        icon = source_component('icon', 'Icon', parent_id=None, sibling_index=0)
        icon['style']['asset'].update(resource='outline', tint='#FF201A1A')
        leaf = NativeLeafEmitter(set(), {('outline', '#FF201A1A'): 'tinted_outline'}, None,
                                 lambda *args: self.fail(str(args))).image(icon, '', None)
        self.assertTrue(leaf.tint_baked)
        self.assertIn('style.asset.tint', leaf.consumed)

    def test_root_parameter_default_is_used_only_when_no_state_value_supplied(self):
        import tempfile
        from pathlib import Path
        from analyze_compose_project import analyze
        from real_page_pipeline import build_source_page_spec
        code = '''
@Composable fun Page(label: String = "Default", contentPadding: PaddingValues = PaddingValues(12.dp)) {
    LazyColumn(contentPadding = contentPadding) { item { Text(label) } }
}
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'Page.kt').write_text(code)
            source = build_source_page_spec(analyze(root, {}, {'Page.kt': code}), 'Page.kt', 'Page',
                                            'page', 'default', 'a' * 64, root)
        page = self.strict(source, {})
        self.assertEqual(self.texts(page), ['Default'])
        root = next(n for n in page['components'] if n['type'] == 'LazyColumn')
        self.assertEqual(root['style']['layout']['padding_dp']['left'], 12)
        self.assertEqual(self.texts(self.strict(source, {'label': 'Chosen'})), ['Chosen'])

    def test_kotlin_for_loop_expands_each_business_component_in_order(self):
        source = self.source('Column { for (post in posts) { Caption(post) } }', '''
@Composable fun Caption(post: Post) { Text(post.title) }
''')
        page = self.strict(source, {'posts': [{'title': 'First'}, {'title': 'Second'}]})
        self.assertEqual(self.texts(page), ['First', 'Second'])

    def test_explicit_paragraph_metrics_survive_projection(self):
        page = self.strict(self.source('''Text("Content", style = TextStyle(
            platformStyle = PlatformTextStyle(includeFontPadding = false),
            lineHeightStyle = LineHeightStyle(LineHeightStyle.Alignment.Center, LineHeightStyle.Trim.None),
            lineBreak = LineBreak.Heading))'''), {})
        style = next(n for n in page['components'] if n['type'] == 'Text')['style']['typography']
        self.assertIs(style['include_font_padding'], False)
        self.assertEqual(style['line_height_alignment'], 'center')
        self.assertEqual(style['line_height_trim'], 'none')
        self.assertEqual(style['line_break'], 'heading')

    def test_object_owned_business_component_expands_its_children(self):
        page = self.source('Badges.Label("Shopping", Modifier.size(24.dp))', '''
object Badges {
    @Composable
    fun Label(value: String, modifier: Modifier) {
        Text(value, modifier = modifier, fontSize = 18.sp)
    }
}
''')
        projected = self.strict(page, {})
        self.assertEqual(self.texts(projected), ['Shopping'])
        text = next(n for n in projected['components'] if n['type'] == 'Text')
        self.assertEqual(text['style']['layout']['width_dp'], 24)

    def test_imported_object_component_keeps_qualified_owner(self):
        from analyze_compose_project import collect_composable_associations
        files = {'Page.kt': 'package sample\nimport widgets.Badges\n@Composable fun Page() { Badges.Label("Hello") }',
                 'Badges.kt': 'package widgets\nobject Badges { @Composable fun Label(value: String) { Text(value) } }'}
        associations = collect_composable_associations(files)
        self.assertEqual(associations['resolved']['Page.kt'].get('Badges.Label'),
                         [{'source': 'Badges.kt', 'composable': 'Label'}])

    def test_measured_window_insets_padding_is_consumed_by_descendants_not_siblings(self):
        page = self.source('''Column(modifier = Modifier.statusBarsPadding()) {
    Box(modifier = Modifier.statusBarsPadding()) { Text("Nested") }
    Box(modifier = Modifier.navigationBarsPadding()) { Text("Bottom") }
}''')
        result = self.strict(page, {
            'WindowInsets.statusBars': {'left': 0, 'top': 28, 'right': 0, 'bottom': 0},
            'WindowInsets.navigationBars': {'left': 0, 'top': 0, 'right': 0, 'bottom': 24},
        })
        nodes = [n for n in result['components'] if n['type'] in ('Column', 'Box')]
        self.assertEqual([n['style']['layout']['padding_dp']['top'] for n in nodes], [28, 0, 0])
        self.assertEqual(nodes[-1]['style']['layout']['padding_dp']['bottom'], 24)

    def source(self, body, declarations=''):
        return test_dp_size.DpSizeTest().source_page(body, declarations)

    def strict(self, page, values):
        fixture = {'schema': 'android-to-harmony.page-state-fixture.v1', 'page': page['page'], 'values': values}
        return project_source_page(page, fixture)[0]

    def texts(self, page):
        return [n['style']['content']['text'] for n in page['components'] if n['type'] == 'Text']

    def test_else_if_is_excluded_when_first_branch_is_true(self):
        page = self.source('''Column {
if (card != null) { Text("Card") } else if (loading) { Text("Loading") } else { Text("Empty") }
}''')
        for card, loading, expected in [({}, True, 'Card'), ({}, False, 'Card'),
                                        (None, True, 'Loading'), (None, False, 'Empty')]:
            with self.subTest(card=card, loading=loading):
                self.assertEqual(self.texts(self.strict(page, {'card': card, 'loading': loading})), [expected])

    def test_implicit_lazy_item_expands_business_component_for_each_value(self):
        page = self.source('''LazyColumn {
    items(state.accounts) {
        AccountCard(account = it)
    }
}''', '''
@Composable
fun AccountCard(account: Account) {
    Column { Text(account.name); Text(account.balance) }
}
''')
        projected = self.strict(page, {'state': {'accounts': [
            {'name': 'Phyre', 'balance': '2125'},
            {'name': 'DSK', 'balance': '12125'},
            {'name': 'Cash', 'balance': '2020'},
        ]}})
        self.assertEqual(self.texts(projected), ['Phyre', '2125', 'DSK', '12125', 'Cash', '2020'])

    def test_animated_content_binds_current_state_and_renders_selected_children(self):
        from test_layout_mapping_contract import render_nodes
        page = self.source('''AnimatedContent(targetState = selected) { active ->
    if (active) { Text("Selected") } else { Text("Accounts") }
}''')
        for selected, label in [(True, 'Selected'), (False, 'Accounts')]:
            with self.subTest(selected=selected):
                projected = self.strict(page, {'selected': selected})
                self.assertEqual(self.texts(projected), [label])
                # The renderer helper accepts already selected nodes, without a fixture.
                for node in projected['components']:
                    node['visibility_condition'] = None
                output, _, renderer = render_nodes(projected['components'])
                self.assertIn("Text('" + label + "')", output)
                self.assertFalse(any('unsupported component AnimatedContent' in str(x)
                                     for x in renderer.unresolved))

    def test_grouped_map_and_indexed_items_keep_nested_bindings(self):
        page = self.source('''LazyColumn {
    groups.forEach { (day, rows) ->
        item { Text(day) }
        itemsIndexed(rows) { index, record ->
            Entry(record = record, index = index)
        }
    }
}''', '''
@Composable
fun Entry(record: Record, index: Int) {
    Row { Text(record.name); Text(index.toString()) }
}
''')
        projected = self.strict(page, {'groups': {
            'Monday': [{'name': 'Income'}, {'name': 'Shopping'}],
            'Tuesday': [{'name': 'Travel'}],
        }})
        self.assertEqual(self.texts(projected),
                         ['Monday', 'Income', '0', 'Shopping', '1', 'Tuesday', 'Travel', '0'])

    def test_callback_local_does_not_replace_later_list_lambda_parameter(self):
        page = self.source('''Column {
    Button(onClick = { val record = loadOtherRecord(); consume(record) }) { Text("Action") }
    records.forEach { record -> Label(record = record) }
}''', '''
@Composable
fun Label(record: Record) { Text(record.name) }
''')
        self.assertEqual(self.texts(self.strict(page, {'records': [{'name': 'Travel'}]})),
                         ['Action', 'Travel'])

    def test_runtime_scene_value_overrides_page_state_initializer_not_child_parameter(self):
        page = self.source('''val loading = remember { mutableStateOf(true) }
Column { if (loading) { Text("Loading") } else { Text("Loaded") }
    Child(loading = true)
}''', '''
@Composable
fun Child(loading: Boolean) { if (loading) { Text("Child loading") } }
''')
        self.assertEqual(self.texts(self.strict(page, {'loading': False})), ['Loaded', 'Child loading'])

    def test_fully_qualified_business_call_resolves_same_definition_as_short_name(self):
        page = self.source('Column { example.Header(title = "Accounts"); Header(title = "Cards") }', '''
@Composable
fun Header(title: String) { Row { Text(title) } }
''')
        self.assertEqual(self.texts(self.strict(page, {})), ['Accounts', 'Cards'])

    def test_separate_loops_with_identical_arguments_do_not_interleave_siblings(self):
        page = self.source('''Column {
    values.forEach { item -> Text("First $item") }
    values.forEach { item -> Text("Second $item") }
}''')
        self.assertEqual(self.texts(self.strict(page, {'values': [1, 2]})),
                         ['First 1', 'First 2', 'Second 1', 'Second 2'])

    def test_scaffold_zero_insets_keep_ordered_extra_padding(self):
        from test_layout_mapping_contract import render_nodes
        page = self.source('''Scaffold(contentWindowInsets = WindowInsets(0, 0, 0, 0)) { innerPadding ->
    Column(Modifier.padding(innerPadding).padding(top = 32.dp).fillMaxSize().padding(horizontal = 16.dp)) {
        Text("Content")
    }
}''')
        output, _, _ = render_nodes(page['components'])
        self.assertIn('top: this.layoutPx(32)', output)
        self.assertIn('left: this.layoutPx(16)', output)

    def test_nested_else_if_chain_remains_inside_selected_parent(self):
        page = self.source('''Column {
if (visible) {
  if (first) { Text("First") } else if (second) { Text("Second") }
  else if (third) { Text("Third") } else { Text("Last") }
} else { Text("Hidden") }
}''')
        for visible, first, second, third, expected in [
            (True, True, True, True, 'First'), (True, False, True, True, 'Second'),
            (True, False, False, True, 'Third'), (True, False, False, False, 'Last'),
            (False, True, True, True, 'Hidden')]:
            values = dict(visible=visible, first=first, second=second, third=third)
            self.assertEqual(self.texts(self.strict(page, values)), [expected])

    def test_explicit_state_inputs_respect_fixed_component_parameters(self):
        page = self.source('''Column {
SectionHeader(actionLabel = "Edit")
SectionHeader(actionLabel = null)
}''', '''
@Composable
fun SectionHeader(actionLabel: String?) {
    Row { if (actionLabel != null) { Text(actionLabel) } }
}
''')
        spec = {'schema': 'android-to-harmony.ui-state-inputs.v1', 'page_id': 'page',
                'scenes': [{'id': 'loaded', 'label': 'Loaded', 'values': {'actionLabel': 'Ignored'}}]}
        catalog = build_catalog(page, spec)
        self.assertEqual(len(catalog['scenes']), 1)
        fixture = preview_fixture(page, catalog['scenes'][0])
        projected, _ = project_source_page(page, fixture)
        self.assertEqual(self.texts(projected), ['Edit'])

    def test_unknown_state_is_not_replaced_with_an_arbitrary_visible_branch(self):
        page = self.source('Column { if (loading) { Text("Loading") } else { Text("Content") } }')
        spec = {'schema': 'android-to-harmony.ui-state-inputs.v1', 'page_id': 'page',
                'scenes': [{'id': 'unknown', 'label': 'Unknown', 'values': {}}]}
        catalog = build_catalog(page, spec)
        with self.assertRaisesRegex(ValueError, 'resolved boolean'):
            project_source_page(page, preview_fixture(page, catalog['scenes'][0]))

    def test_named_then_positional_arguments_keep_declared_parameter_positions(self):
        page = self.source('Panel(title = "Breakdown", enabled = false, query, entries)', '''
@Composable
fun Panel(title: String, enabled: Boolean, query: String, entries: List<String>) {
    Column {
        Text(title)
        Text(query)
        if (enabled) { Text("Enabled") }
        if (entries.isNotEmpty()) { Text("Has entries") }
    }
}
''')
        self.assertEqual(self.texts(self.strict(page, {'query': 'This Week', 'entries': ['Food']})),
                         ['Breakdown', 'This Week', 'Has entries'])

    def test_catalog_never_creates_scenes_from_independent_branch_switches(self):
        page = self.source('Column { if (loading) { Text("Loading") } else { Text("Content") } }')
        self.assertEqual(build_catalog(page)['scenes'], [])

    def test_file_constants_and_state_card_color_reach_projected_style(self):
        page = self.source('Payment(cardColor = color)', '''
private val CardShape = RoundedCornerShape(10.dp)
private const val RATIO = 1.5f
private val HEIGHT = 200.dp
@Composable
fun Payment(cardColor: Color) {
    Card(shape = CardShape, colors = CardDefaults.cardColors(containerColor = cardColor)) {
        Box(Modifier.height(HEIGHT).width(HEIGHT * RATIO)) { Text("Card") }
    }
}
''')
        projected = self.strict(page, {'color': '#FF100D40'})
        card = next(n for n in projected['components'] if n['type'] == 'Card')
        box = next(n for n in projected['components'] if n['type'] == 'Box')
        self.assertEqual(box['style']['layout']['height_dp'], 200)
        self.assertEqual(box['style']['layout']['width_dp'], 300)
        self.assertEqual(card['style']['surface']['background'], {'type': 'solid', 'color': '#FF100D40'})
        self.assertEqual(set(card['style']['surface']['corner_radius_dp'].values()), {10})


if __name__ == '__main__':
    unittest.main()
