import unittest

import test_keyed_resources as helpers


class CompanyUnresolvedTest(unittest.TestCase):
    generate = helpers.KeyedResourcesTest.generate

    def test_clip_to_bounds_reaches_target(self):
        page, code, result, renderer = self.generate(
            'Box(Modifier.size(40.dp).clipToBounds()) { Text("A") }')
        self.assertIn('.clip(true)', code)
        self.assertFalse(any('clipToBounds' in str(u) for u in result['unresolved']))
        self.assertFalse(renderer.unresolved)

    def test_focusable_boolean_reaches_target(self):
        for expression, expected in [('focusable()', True), ('focusable(enabled = false)', False)]:
            with self.subTest(expression=expression):
                page, code, result, renderer = self.generate('Box(Modifier.size(40.dp).' + expression + ') {}')
                self.assertIn('.focusable(' + str(expected).lower() + ')', code)
                self.assertFalse(any('focusable' in str(u) for u in result['unresolved']))
                self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_focus_interaction_stream_is_not_silently_dropped(self):
        _, code, result, _ = self.generate('Box(Modifier.focusable(interactionSource = stream)) {}')
        self.assertIn('.focusable(true)', code)
        self.assertIn('focus interaction stream', str(result['unresolved']))

    def test_modifier_argument_is_not_content_callable(self):
        _, code, result, _ = self.generate(
            'Label(Modifier.testTag("topNavbar_title"))', '''
@Composable fun Label(modifier: Modifier = Modifier) {
    Text("Title", modifier = modifier)
}
''')
        self.assertIn('Title', code)
        self.assertFalse(any('content call target' in str(u) for u in result['unresolved']))
        self.assertFalse(any('topNavbar_title' in str(u) for u in result['unresolved']))

    def test_named_padding_and_border_resolve_source_getters(self):
        page, code, result, _ = self.generate('''Box(Modifier
            .padding(horizontal = Dimensions.gap, vertical = Dimensions.small)
            .border(color = ColorTokens.border, width = 1.dp, shape = RectangleShape)) {}''', '''
object Dimensions { val gap: Dp get() = 16.dp; val small: Dp get() = 8.dp }
object ColorTokens { val border: Color get() = Color.Red }
''')
        box = next(n for n in page['components'] if n['type'] == 'Box')
        self.assertEqual(box['style']['layout']['padding_dp']['top'], 8)
        border = next(n['style']['surface']['border'] for n in page['components']
                      if n['style']['surface']['border'])
        self.assertEqual(border['color'], '#FFFF0000')
        self.assertFalse(result['unresolved'], result['unresolved'])

    def test_typography_getter_resolves_source_text_style(self):
        page, _, result, _ = self.generate('Text("A", style = TypographyTokens.body)', '''
object TypographyTokens {
    val body: TextStyle get() = TextStyle(fontSize = 18.sp, lineHeight = 24.sp,
                                        fontWeight = FontWeight.Bold, color = Color.Black)
}
''')
        text = next(n for n in page['components'] if n['type'] == 'Text')
        self.assertEqual(text['style']['typography']['font_size_sp'], 18)
        self.assertFalse(result['unresolved'], result['unresolved'])


if __name__ == '__main__':
    unittest.main()
