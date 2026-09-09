import inspect
import unittest

from test_component_ui_states import compile_states
from ui_migration.controls.registry import CONTROLS, ControlRegistry
from ui_migration.controls.base import RenderContext


class RegisteredControlsTest(unittest.TestCase):
    def compile(self, body):
        return compile_states('@Composable fun Page() { ' + body + ' }')

    def test_each_control_has_its_own_implementation_file(self):
        self.assertEqual(len(CONTROLS.names), 19)
        modules = [type(control).__module__ for control in CONTROLS]
        self.assertEqual(len(set(modules)), 19)
        for control in CONTROLS:
            self.assertNotIn('renderer', inspect.getsource(type(control)))
        self.assertNotIn('renderer', RenderContext.__annotations__)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            ControlRegistry([CONTROLS.get('Tab'), CONTROLS.get('Tab')])

    def test_menu_slots_and_visibility(self):
        for expanded in ('true', 'false'):
            with self.subTest(expanded=expanded):
                _, renderer, code, result = self.compile('''
ExposedDropdownMenuBox(expanded = ''' + expanded + ''', onExpandedChange = {}) {
  Text("Anchor", color = Color.Black)
  DropdownMenu(expanded = ''' + expanded + ''', onDismissRequest = {}, containerColor = Color.White) {
    DropdownMenuItem(text = { Text("Option", color = Color.Black) }, onClick = {},
      leadingIcon = { Text("L", color = Color.Black) }, trailingIcon = { Text("R", color = Color.Black) })
  }
}''')
                for text in ('Anchor', 'Option', 'L', 'R', '.bindPopup('):
                    self.assertIn(text, code)
                self.assertIn('Visible: boolean = false', code)
                self.assertIn('Visible = ' + expanded, code)
                self.assertIn('Number(area.width) > 0', code)
                self.assertTrue(result['generation_complete'], result['unresolved'])
                self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_all_tab_row_variants_keep_tabs_and_selected_indicator(self):
        for kind in ('TabRow', 'PrimaryTabRow', 'SecondaryTabRow'):
            with self.subTest(kind=kind):
                _, renderer, code, result = self.compile(kind + '''(selectedTabIndex = 1, containerColor = Color.White, contentColor = Color.Blue) {
  Tab(selected = false, onClick = {}, text = { Text("One", color = Color.Black) })
  Tab(selected = true, onClick = {}, text = { Text("Two", color = Color.Black) })
}''')
                for text in ('One', 'Two', '.layoutWeight(1)', '.align(Alignment.Bottom)'):
                    self.assertIn(text, code)
                self.assertTrue(result['generation_complete'], result['unresolved'])
                self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_navigation_bar_and_rail_named_slots(self):
        for parent, item in [('NavigationBar', 'NavigationBarItem'), ('NavigationRail', 'NavigationRailItem')]:
            with self.subTest(parent=parent):
                _, renderer, code, result = self.compile(parent + '''(containerColor = Color.White) {
''' + item + '''(selected = true, onClick = {}, icon = { Text("I", color = Color.Black) }, label = { Text("Home", color = Color.Black) })
}''')
                self.assertIn('Home', code)
                self.assertIn("Text('I')", code)
                self.assertIn('.borderRadius(', code)
                self.assertTrue(result['generation_complete'], result['unresolved'])
                self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_drawer_preserves_both_slots_and_reports_modal_policy_gap(self):
        _, renderer, code, result = self.compile('''NavigationDrawer(drawerState = rememberDrawerState(DrawerValue.Open),
drawerContent = { Text("Drawer", color = Color.Black) }) { Text("Page", color = Color.Black) }''')
        for text in ('Drawer', 'Page', 'if (this.NavigationDrawer', ': boolean = true', '.align(Alignment.Start)'):
            self.assertIn(text, code)
        self.assertNotIn('.bindContentCover(', code)
        self.assertTrue(any('source.control.gestures' in str(issue) for issue in renderer.unresolved))

    def test_flow_and_contextual_index_expansion(self):
        for body in ('''FlowRow { Text("A", color = Color.Black); Text("B", color = Color.Black) }''',
                     '''ContextualFlowRow(itemCount = 3) { index -> Text("Item $index", color = Color.Black) }'''):
            _, renderer, code, result = self.compile(body)
            self.assertIn('wrap: FlexWrap.Wrap', code)
            for label in ('Item 0', 'Item 1', 'Item 2') if 'Contextual' in body else ("Text('A')", "Text('B')"):
                self.assertIn(label, code)
            self.assertTrue(result['generation_complete'], result['unresolved'])
            self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_grid_and_staggered_grid_tracks_and_items(self):
        for kind, cells, native in [('LazyVerticalGrid', 'GridCells', 'GridItem'),
                                    ('LazyVerticalStaggeredGrid', 'StaggeredGridCells', 'FlowItem')]:
            with self.subTest(kind=kind):
                _, renderer, code, result = self.compile(kind + '(columns = ' + cells + '''.Fixed(2)) {
items(3) { index -> Text("Cell $index", color = Color.Black) }
}''')
                self.assertEqual(code.count(native + '()'), 3)
                self.assertIn(".columnsTemplate('1fr 1fr')", code)
                for text in ('Cell 0', 'Cell 1', 'Cell 2'):
                    self.assertIn(text, code)
                self.assertTrue(result['generation_complete'], result['unresolved'])
                self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_unsupported_layout_policy_does_not_delete_content(self):
        _, _, code, result = self.compile('FlowRow(maxItemsInEachRow = 2) { Text("Kept", color = Color.Black) }')
        self.assertIn('Kept', code)
        self.assertFalse(result['generation_complete'])
        self.assertTrue(any('maxItemsInEachRow' in str(issue) for issue in result['unresolved']))

    def test_grid_count_variable_and_named_count_use_shared_list_expansion(self):
        _, renderer, code, result = self.compile('''val count = 4
LazyVerticalGrid(columns = GridCells.Fixed(2)) { items(count = count) { i -> Text("Row $i", color = Color.Black) } }''')
        self.assertEqual(code.count('GridItem()'), 4)
        self.assertIn('Row 3', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved)

    def test_flow_spacing_and_one_dp_content_are_consumed(self):
        _, renderer, code, result = self.compile('''FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp),
verticalArrangement = Arrangement.spacedBy(6.dp)) { Box(Modifier.size(1.dp).background(Color.Black)) {} }''')
        for expression in ('LengthMetrics.vp(8)', 'LengthMetrics.vp(6)', 'layoutPx(1)'):
            self.assertIn(expression, code)
        self.assertNotIn('.justifyContent(', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertEqual(renderer.test_phase_gate['verdict'], 'pass', renderer.test_phase_gate['failures'])

    def test_unknown_grid_columns_keep_content_but_fail_completeness(self):
        _, renderer, code, result = self.compile('''LazyVerticalGrid(columns = unknownColumns) {
item { Text("Preserved", color = Color.Black) } }''')
        self.assertIn('Preserved', code)
        self.assertFalse(result['generation_complete'])
        self.assertTrue(any('columns' in str(issue) for issue in renderer.unresolved))

    def test_adaptive_grid_uses_available_width_and_equal_tracks(self):
        for kind, cells in [('LazyVerticalGrid', 'GridCells'), ('LazyVerticalStaggeredGrid', 'StaggeredGridCells')]:
            with self.subTest(kind=kind):
                _, renderer, code, result = self.compile(kind + '(columns = ' + cells + '''.Adaptive(100.dp),
horizontalArrangement = Arrangement.spacedBy(8.dp)) { items(3) { i -> Text("Cell $i", color = Color.Black) } }''')
                self.assertIn('.onAreaChange(', code)
                self.assertIn('Math.floor(', code)
                self.assertIn('/ 108)', code)
                self.assertIn('"1fr ".repeat(', code)
                self.assertFalse(renderer.unresolved, renderer.unresolved)
                self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_navigation_and_menu_color_apis_feed_named_slots(self):
        _, renderer, code, result = self.compile('''NavigationBar {
NavigationBarItem(selected = true, onClick = {}, icon = { Text("I") }, label = { Text("Home") },
colors = NavigationBarItemDefaults.colors(selectedIconColor = Color.Red, selectedTextColor = Color.Blue,
indicatorColor = Color.Green)) }''')
        for color in ('#FFFF0000', '#FF0000FF', '#FF00FF00'):
            self.assertIn(color, code)
        self.assertFalse(renderer.unresolved, renderer.unresolved)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        _, renderer, code, result = self.compile('''DropdownMenuItem(text = { Text("Menu") },
onClick = {}, colors = MenuDefaults.itemColors(textColor = Color.Red))''')
        self.assertIn('#FFFF0000', code)
        self.assertFalse(renderer.unresolved, renderer.unresolved)
        self.assertTrue(result['generation_complete'], result['unresolved'])


if __name__ == '__main__':
    unittest.main()
