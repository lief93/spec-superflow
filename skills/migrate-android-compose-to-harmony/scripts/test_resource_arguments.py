import unittest

import test_keyed_resources as helpers


class ResourceArgumentsTest(unittest.TestCase):
    generate = helpers.KeyedResourcesTest.generate

    def test_arbitrary_named_string_parameter_keeps_call_and_type(self):
        page, code, result, renderer = self.generate('CardLabel(Copy.text("title", "Alice"))', '''
@Composable fun CardLabel(customLabel: String) { Text(customLabel, color = Color.Black) }
''')
        node = next(n for n in page['components'] if n['type'] == 'CardLabel')
        arg = node['source']['component_interface']['arguments'][0]
        self.assertEqual(arg['status'], 'resolved', arg)
        self.assertEqual(arg['value']['key'], 'title')
        self.assertIn('private CardLabel(customLabel: string)', code)
        self.assertRegex(code, r'this.CardLabel\(StyleToken\d+.read\(\x27title\x27, \x27Alice\x27\)\)')
        self.assertNotIn('platform_resource_reference', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_multilevel_parameters_are_forwarded_not_baked(self):
        _, code, result, renderer = self.generate('Outer(Copy.text("title", "Alice"))', '''
@Composable fun Outer(arbitrary: String) { Inner(arbitrary) }
@Composable fun Inner(anotherName: String) { Text(anotherName, color = Color.Black) }
''')
        self.assertIn('private Outer(arbitrary: string)', code)
        self.assertIn('private Inner(anotherName: string)', code)
        self.assertIn('this.Inner(props.arbitrary)', code)
        self.assertIn('Text(props.anotherName)', code)
        self.assertNotIn('platform_resource_reference', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_description_uses_the_same_string_resource(self):
        page, code, result, _ = self.generate('Picture(Copy.text("description", "Alice"))', '''
@Composable fun Picture(customDescription: String) {
    Image(painter = painterResource(R.drawable.cover), contentDescription = customDescription)
}
''')
        image = next(n for n in page['components'] if n['type'] == 'Image')
        self.assertEqual(image['source']['style_token_references']['content.content_description']['key'], 'description')
        self.assertIn('.accessibilityText(props.customDescription)', code)
        self.assertNotIn('platform_resource_reference', code)
        self.assertFalse(any('content_description' in u.get('path', '') for u in result['unresolved']))

    def test_wrong_parameter_type_is_not_accepted(self):
        page, _, _, _ = self.generate('Counter(Copy.text("title", "Alice"))', '''
@Composable fun Counter(count: Int) { Text("Count", color = Color.Black) }
''')
        node = next(n for n in page['components'] if n['type'] == 'Counter')
        self.assertEqual(node['source']['component_interface']['arguments'][0]['status'], 'unresolved')

    def test_input_string_reference_is_forwarded(self):
        _, code, result, renderer = self.generate('Field(Copy.text("entry", "Alice"))', '''
@Composable fun Field(arbitrary: String) {
    BasicTextField(value = arbitrary, onValueChange = {}, singleLine = true,
        textStyle = TextStyle(fontSize = 16.sp, fontWeight = FontWeight.Normal, color = Color.Black))
}
''')
        self.assertIn('TextInput({ text: props.arbitrary })', code)
        self.assertIn("read('entry', 'Alice')", code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_list_of_string_references_keeps_independent_keys(self):
        page, code, result, renderer = self.generate('Labels(listOf(Copy.text("first", "Alice"), Copy.text("second", "Bob")))', '''
@Composable fun Labels(values: List<String>) { Text(values[0], color = Color.Black) }
''')
        node = next(n for n in page['components'] if n['type'] == 'Labels')
        argument = node['source']['component_interface']['arguments'][0]
        self.assertEqual(argument['status'], 'resolved', argument)
        self.assertEqual([v['key'] for v in argument['value']], ['first', 'second'])
        self.assertIn("read('second', 'Bob')", code)
        self.assertNotIn('platform_resource_reference', code)
        self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_repeated_components_pass_distinct_keys(self):
        _, code, _, renderer = self.generate('Column { Label(Copy.text("first", "Alice")); Label(Copy.text("second", "Bob")) }', '''
@Composable fun Label(arbitraryName: String) { Text(arbitraryName, color = Color.Black) }
''')
        self.assertEqual(code.count('private Label(arbitraryName: string)'), 1)
        self.assertIn("this.Label(StyleToken0.read('first', 'Alice'))", code)
        self.assertIn("this.Label(StyleToken0.read('second', 'Bob'))", code)
        self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_malformed_reference_is_rejected(self):
        from ui_migration.contracts.component_interfaces import value_matches, TypeParser
        with self.assertRaisesRegex(ValueError, 'unsafe|invalid'):
            value_matches({'kind':'platform_resource_reference', 'key':'title', 'reference':{
                'kind':'string', 'target':{'module':'./Copy', 'export':'Copy', 'member':'read(); bad'}}},
                TypeParser('String').parse())


if __name__ == '__main__':
    unittest.main()
