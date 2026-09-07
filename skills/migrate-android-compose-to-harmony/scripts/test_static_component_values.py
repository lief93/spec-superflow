import unittest

from analyze_compose_project import extract_kotlin_data_classes
from generate_lanhu_source_page import project_source_page
from test_generate_lanhu_source_page import source_component
from test_layout_mapping_contract import render_nodes


SOURCE = r'''
data class Badge(val number: String, val amount: String, val date: String, val unknown: String) {
    companion object {
        fun sample(date: String = "02/24"): Badge {
            val digits = "2298126833989874"
            return Badge(number = digits.groupLabel(), amount = "\$2887.65",
                date = date, unknown = fetchFromNetwork())
        }
    }
}
fun String.groupLabel(group: Int = 4, separator: Char = ' '): String {
    val result = StringBuilder()
    var index = 0
    for (letter in this) {
        if (index > 0 && index % group == 0) { result.append(separator) }
        result.append(letter)
        index++
    }
    return result.toString()
}
'''


class StaticComponentValuesTest(unittest.TestCase):
    def project(self, source=SOURCE, invocation='Badge.sample()'):
        inventory = extract_kotlin_data_classes({'Badge.kt': source})
        root = source_component('root', 'Column', parent_id=None, sibling_index=0,
                                children_ids=['number', 'amount', 'date', 'unknown'])
        nodes = [root]
        for i, name in enumerate(root['children_ids']):
            node = source_component(name, 'Text', parent_id='root', sibling_index=i, font_size_sp=12)
            node['local_values'] = {'badge': invocation}
            node['unresolved'] = [{'path': 'style.content.text', 'expression': 'badge.' + name,
                                   'reason': 'unresolved source value'}]
            nodes.append(node)
        payload = {'schema': 'android-to-harmony.source-page-spec.v1',
                   'page': {'id': 'sample', 'state': 'default'}, 'components': nodes,
                   'source_value_inventory': inventory}
        return project_source_page(payload, {'schema': 'android-to-harmony.page-state-fixture.v1',
                                              'page': payload['page'], 'values': {}})[0]

    def test_static_factory_members_reach_final_json_and_native_text(self):
        page = self.project()
        nodes = {node['id']: node for node in page['components']}
        for name, expected in [('number', '2298 1268 3398 9874'), ('amount', '$2887.65'), ('date', '02/24')]:
            self.assertEqual(nodes[name]['style']['content']['text'], expected)
            self.assertEqual(nodes[name]['unresolved'], [])
        self.assertIsNone(nodes['unknown']['style']['content']['text'])
        self.assertTrue(nodes['unknown']['unresolved'])
        output, _, _ = render_nodes(page['components'])
        self.assertIn("Text('2298 1268 3398 9874')", output)
        self.assertIn("Text('$2887.65')", output)
        self.assertIn(".id('unknown')", output)

    def test_call_site_static_argument_overrides_factory_default(self):
        page = self.project(invocation='Badge.sample(date = "12/30")')
        self.assertEqual(next(n for n in page['components'] if n['id'] == 'date')['style']['content']['text'], '12/30')

    def test_helper_name_does_not_imply_implementation(self):
        source = SOURCE[:SOURCE.index('fun String.groupLabel')] + 'fun String.groupLabel(): String { return this }'
        page = self.project(source)
        node = next(n for n in page['components'] if n['id'] == 'number')
        self.assertIsNone(node['style']['content']['text'])
        self.assertTrue(node['unresolved'])

    def test_conditional_factory_does_not_choose_first_return(self):
        source = SOURCE.replace('val digits =', 'if (globalFlag) return Badge("wrong", "wrong", "wrong", "wrong")\n val digits =')
        page = self.project(source)
        self.assertTrue(all(n['style']['content']['text'] is None for n in page['components'][1:]))


if __name__ == '__main__':
    unittest.main()
