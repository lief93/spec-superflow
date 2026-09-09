import unittest

import test_ui_state_semantics as semantics
from test_layout_mapping_contract import render_nodes
from ui_migration.frontend.values import evaluate_expression


class MaterialItemsTest(unittest.TestCase):
    def project(self, body, declarations='', values=None):
        helper = semantics.UiStateSemanticsTest()
        from ui_migration.frontend.theme import selected_theme_colors
        defaults = selected_theme_colors({'color_schemes': [{'variant': 'light', 'constructor': 'lightColorScheme', 'roles': {}}]})
        environment = {'MaterialTheme.colorScheme.' + key: value for key, value in defaults.items()}
        environment.update({'MaterialTheme.colorScheme.secondaryContainer': '#FFE8DEF8',
            'MaterialTheme.colorScheme.onSecondaryContainer': '#FF1D192B',
            'MaterialTheme.colorScheme.outlineVariant': '#FFCAC4D0'})
        return helper.strict(helper.source(body, declarations), {**environment, **(values or {})})

    def test_list_item_preserves_forwarded_slots_and_colors(self):
        page = self.project('Entry(icon = { Text("ICON") })', '''
@Composable fun Entry(icon: @Composable () -> Unit) {
    val colors = ListItemDefaults.colors(containerColor = Color(0xFF123456))
    ListItem(headlineContent = { Text("Title") }, supportingContent = { Text("Detail") },
        leadingContent = icon, trailingContent = { Text("NEXT") }, colors = colors)
}
''')
        item = next(n for n in page['components'] if n['type'] == 'ListItem')
        self.assertEqual(item['style']['surface']['background'], {'type': 'solid', 'color': '#FF123456'})
        output, _, renderer = render_nodes(page['components'])
        for text in ('ICON', 'Title', 'Detail', 'NEXT'):
            self.assertIn("'" + text + "'", output)
        self.assertEqual(output.count('Text(props.'), 4)
        self.assertIn('.constraintSize({ minHeight: this.materialItem0Multiline ? this.layoutPx(88) : this.layoutPx(72) })', output)
        self.assertIn('.onAreaChange', output)
        self.assertIn('.layoutWeight(1)', output)
        self.assertFalse(any('unsupported component ListItem' in str(u) for u in renderer.unresolved))

    def test_filter_chip_keeps_label_selected_fill_and_geometry(self):
        for selected in (True, False):
            page = self.project('FilterChip(selected = selected, onClick = {}, label = { Text("Food") })',
                                values={'selected': selected})
            item = next(n for n in page['components'] if n['type'] == 'FilterChip')
            self.assertIs(item['style']['state']['selected'], selected)
            self.assertIsNotNone(item['style']['surface']['background'])
            output, _, renderer = render_nodes(page['components'])
            self.assertIn("Text('Food')", output)
            self.assertIn('.constraintSize({ minHeight: this.layoutPx(32) })', output)
            self.assertIn('.constraintSize({ minHeight: this.layoutPx(48) })', output)
            self.assertFalse(any('unsupported component FilterChip' in str(u) for u in renderer.unresolved))

    def test_material_default_text_retains_line_box_metrics(self):
        page = self.project('Text("Title", style = MaterialTheme.typography.titleMedium)')
        text = next(n for n in page['components'] if n['type'] == 'Text')
        self.assertEqual(text['style']['typography']['line_height_trim'], 'none')
        self.assertEqual(text['style']['typography']['line_height_alignment'], 'center')
        self.assertIs(text['style']['typography']['include_font_padding'], False)
        self.assertEqual(text['style']['typography']['letter_spacing_sp'], 0.15)

    def test_filter_chip_icon_uses_compact_leading_padding(self):
        page = self.project('FilterChip(selected=false,onClick={},leadingIcon={Text("+")},label={Text("Food")})')
        chip = next(n for n in page['components'] if n['type'] == 'FilterChip')
        self.assertEqual(chip['source']['material_item']['start_padding_dp'], 8)
        output, _, _ = render_nodes(page['components'])
        self.assertIn('.padding({ left: this.layoutPx(8), right: this.layoutPx(16)', output)

    def test_color_factory_consumes_forwarded_color_values(self):
        page = self.project('Tile(background = Accent)', '''
val Accent = Color(0xFFE8F5E9)
@Composable fun Tile(background: Color) {
    val colors = CardDefaults.cardColors(containerColor = background)
    Card(colors = colors) { Text("Income") }
}
''')
        card = next(n for n in page['components'] if n['type'] == 'Card')
        self.assertEqual(card['style']['surface']['background'], {'type': 'solid', 'color': '#FFE8F5E9'})

    def test_extended_fab_preserves_container_and_scaffold_anchor(self):
        for expanded in (True, False):
            page = self.project('Scaffold(floatingActionButton={ ExtendedFloatingActionButton(onClick={}, expanded=expanded, icon={Text("+")}, text={Text("Add")}, containerColor=Color.Red) }) { Text("Body") }', values={'expanded': expanded})
            button = next(n for n in page['components'] if n['type'] == 'ExtendedFloatingActionButton')
            self.assertEqual(button['style']['surface']['background'], {'type': 'solid', 'color': '#FFFF0000'})
            output, _, _ = render_nodes(page['components'])
            self.assertIn('.layoutGravity(LocalizedAlignment.BOTTOM_END)', output)
            self.assertIn('.constraintSize({ minHeight: this.layoutPx(56)', output)
            self.assertEqual("Text('Add')" in output, expanded)

    def test_vector_companion_resource_and_diagonal_gradient(self):
        self.assertEqual(evaluate_expression('ImageVector.Companion.vectorResource(R.drawable.arrow)',
                         {'R.drawable.arrow': 'arrow'}), 'arrow')
        page = self.project('Box(Modifier.size(160.dp, 80.dp).background(Brush.linearGradient(colors = listOf(Color.Red, Color.Blue)))) {}')
        box = next(n for n in page['components'] if n['type'] == 'Box')
        self.assertEqual(box['style']['surface']['background']['type'], 'linear_gradient')
        output, _, _ = render_nodes(page['components'])
        self.assertIn('GradientDirection.RightBottom', output)

    def test_appbar_uses_captured_insets_not_an_implicit_zero(self):
        page = self.project('Scaffold(topBar={ TopAppBar(title={Text("Title")}) }) { padding -> Column(Modifier.padding(padding)) { Text("Body") } }',
            values={'WindowInsets.statusBars': {'left': 0, 'top': 32, 'right': 0, 'bottom': 0}})
        bar = next(n for n in page['components'] if n['type'] == 'TopAppBar')
        self.assertEqual(bar['source']['appbar']['top_inset_dp'], 32)
        output, _, _ = render_nodes(page['components'])
        self.assertIn('.height(this.layoutPx(96))', output)
        self.assertIn('.margin({ left: this.layoutPx(12) })', output)

    def test_resource_index_preserves_module_scoped_identity_and_size(self):
        import tempfile
        import json
        import hashlib
        from pathlib import Path
        from ui_migration.frontend.resources import safe_asset_index
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = []
            for module, size in [('settings', 24), ('other', 48)]:
                relative = f'feature/{module}/src/main/res/drawable/icon.xml'
                path = root/relative
                path.parent.mkdir(parents=True)
                path.write_text(f'<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="{size}dp" android:height="{size}dp"/>')
                records.append({'path': relative, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
            (root/'.android-to-harmony-safe.json').write_text(json.dumps({'source_root': str(root), 'local_only_assets': records}))
            self.assertNotIn('icon', safe_asset_index(root))
            for module, size in [('settings', 24), ('other', 48)]:
                selected = safe_asset_index(root, f'feature/{module}/src/main/kotlin/Page.kt')['icon']
                self.assertEqual(selected['width_dp'], size)
                self.assertIn('/'+module+'/', selected['path'])

    def test_large_flexible_bar_keeps_title_slot_and_expanded_height(self):
        page = self.project('LargeFlexibleTopAppBar(title = { Text("Settings") })',
            values={'WindowInsets.statusBars': {'left': 0, 'top': 28, 'right': 0, 'bottom': 0}})
        output, _, _ = render_nodes(page['components'])
        self.assertIn("Text('Settings')", output)
        self.assertIn('.height(this.layoutPx(148))', output)


if __name__ == '__main__':
    unittest.main()
