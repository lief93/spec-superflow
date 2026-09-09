import unittest

from test_component_ui_states import compile_states


ITEM = '''
@Composable fun BannerPageItem(label: String, loading: Boolean) {
    Column(Modifier.fillMaxWidth().height(120.dp)) {
        if (loading) { Text("Loading", color = Color.Black) }
        else { Text(label, color = Color.Black) }
    }
}
'''
PAGER = '''
val labels = listOf("One", "Two", "Three", "Four")
val pager = rememberPagerState { labels.size }
HorizontalPager(state = pager, modifier = Modifier.fillMaxWidth().height(160.dp)) { page ->
    BannerPageItem(label = labels[page], loading = page == 0)
}
'''


class PagerComponentStatesTest(unittest.TestCase):
    def assert_tree(self, renderer):
        nodes = renderer.android_page_by_id
        for node in nodes.values():
            parent = node.get('parent_id')
            if parent is not None:
                self.assertIn(parent, nodes)
            for child in node.get('children_ids', []):
                self.assertIn(child, nodes)
                self.assertEqual(nodes[child]['parent_id'], node['id'])

    def test_parent_state_replacement_removes_expanded_pager_subtree(self):
        source = '''
@Composable fun Page() { Column { Text("Header", color = Color.Black); Banner(false); Text("Footer", color = Color.Black) } }
@Composable fun Banner(loading: Boolean) {
    if (loading) { Text("Wait", color = Color.Black) } else {
''' + PAGER + '\n}\n}\n' + ITEM
        version, renderer, code, result = compile_states(source)
        self.assert_tree(renderer)
        self.assertIn('Swiper()', code)
        self.assertIn('Footer', code)
        items = [c for c in version['meta']['migration']['componentUiStates'] if c['name'] == 'BannerPageItem']
        self.assertEqual(len(items), 4)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_each_pager_instance_keeps_both_states_and_its_selection(self):
        version, renderer, code, result = compile_states('@Composable fun Page() {\n' + PAGER + '\n}\n' + ITEM)
        self.assert_tree(renderer)
        catalogs = version['meta']['migration']['componentUiStates']
        items = [c for c in catalogs if c['name'] == 'BannerPageItem']
        self.assertEqual(len(items), 4)
        self.assertEqual(len({c['instance_id'] for c in items}), 4)
        self.assertEqual([c['selected'] for c in items], ['then', 'else', 'else', 'else'])
        self.assertTrue(all(len(c['variants']) == 2 for c in items))
        for label, loading, state in [('One', 'true', 'then'), ('Two', 'false', 'else'),
                                      ('Three', 'false', 'else'), ('Four', 'false', 'else')]:
            self.assertIn(f'this.BannerPageItem("{label}", {loading}, "{state}")', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_list_instances_use_same_instance_identity_rule(self):
        source = '''@Composable fun Page() {
val labels = listOf("One", "Two")
Column { labels.forEach { label -> BannerPageItem(label, false) } }
}''' + ITEM
        version, renderer, _, result = compile_states(source)
        self.assert_tree(renderer)
        items = version['meta']['migration']['componentUiStates']
        self.assertEqual(len(items), 2)
        self.assertTrue(all(c['selected'] == 'else' and len(c['variants']) == 2 for c in items))
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_nested_pagers_keep_full_instance_path(self):
        source = '''@Composable fun Page() {
val outer = rememberPagerState { 2 }
HorizontalPager(state = outer) { outerPage ->
    val inner = rememberPagerState { 2 }
    HorizontalPager(state = inner) { innerPage ->
        BannerPageItem(label = "Nested", loading = innerPage == 0)
    }
}
}''' + ITEM
        version, renderer, _, result = compile_states(source)
        self.assert_tree(renderer)
        items = version['meta']['migration']['componentUiStates']
        self.assertEqual(len(items), 4)
        self.assertEqual(len({c['instance_id'] for c in items}), 4)
        self.assertEqual([c['selected'] for c in items], ['then', 'else', 'then', 'else'])
        self.assertTrue(result['generation_complete'], result['unresolved'])


if __name__ == '__main__':
    unittest.main()
