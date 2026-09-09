import unittest

from kotlin_psi import KotlinPsiSyntaxError, parse_expression
from test_partial_page_generation import PartialPageGenerationTest
from ui_migration.frontend.style_tokens import StyleTokenProjector


class ExpressionCommentsTest(unittest.TestCase):
    def test_trailing_and_nested_comments_are_not_extra_declarations(self):
        for suffix in (' // tail', '\n// tail', ' /* outer /* nested */ end */', '\r\n// tail\r\n'):
            with self.subTest(suffix=suffix):
                tree = parse_expression('Modifier.systemBarsPadding()' + suffix)
                self.assertEqual(tree, parse_expression('Modifier.systemBarsPadding()'))

    def test_comments_in_strings_are_not_removed(self):
        for expression in ('"https://host/path/*literal*/"', '"""//literal\n/*literal*/"""'):
            self.assertEqual(parse_expression(expression)['text'], expression)

    def test_real_trailing_code_and_invalid_syntax_still_fail(self):
        for expression in ('Modifier.width(1.dp)\nval extra = 2',
                           'Modifier.width(1.dp); extra()', 'Modifier.width('):
            with self.subTest(expression=expression), self.assertRaises(KotlinPsiSyntaxError):
                parse_expression(expression)

    def test_comment_in_modifier_chain_survives_json_and_rendering(self):
        helper = PartialPageGenerationTest()
        self.addCleanup(helper.doCleanups)
        source = helper.source('''Column {
Box(Modifier.height(20.dp)
    // Preserve width after the comment
    .width(80.dp)) {}
Text("Footer")
}''')
        _, _, loaded = helper.generate_page(source)
        box = next(n for n in loaded['components'] if n['type'] == 'Box')
        self.assertFalse(any('unparsed trailing' in u['reason'] for u in box['unresolved']))
        from generate_arkui_page import Renderer, derive_page_root
        output = Renderer(derive_page_root(loaded), set(), {}, loaded).render()
        self.assertIn('layoutPx(20)', output)
        self.assertIn('layoutPx(80)', output)

    def test_token_diagnostic_preserves_failed_expression_without_token_mapping(self):
        expression = 'Modifier.width(20.dp)\nval extra = 1'
        original = {'type': 'Box', 'modifiers': [{'name': 'width', 'source_expression': expression}]}
        result = {'style': {'state': {}}, 'unresolved': []}
        StyleTokenProjector({}).apply(original, result, {})
        self.assertEqual(result['unresolved'][0]['expression'], expression)
        from page_snapshot import normalize_unresolved
        self.assertEqual(normalize_unresolved(result['unresolved'], 'token diagnostics'), result['unresolved'])

    def test_failed_alias_reports_alias_body_not_last_successful_expression(self):
        expression = 'AppTokens.ink\nval extra = 1'
        original = {'type': 'Text', 'local_values': {'ink': expression},
                    'arguments': {'semantic': {'color': {'expression': 'ink'}}}}
        result = {'style': {'state': {}}, 'unresolved': []}
        StyleTokenProjector({}).apply(original, result, {})
        self.assertEqual(result['unresolved'][0]['expression'], expression)

    def test_unresolved_modifier_does_not_block_lanhu_reader(self):
        helper = PartialPageGenerationTest()
        self.addCleanup(helper.doCleanups)
        source = helper.source('Column { Box(Modifier.width(20.dp)) {}; Text("Footer") }')
        box = next(n for n in source['components'] if n['type'] == 'Box')
        expression = 'Modifier.width(20.dp)\nval extra = 1'
        box['modifiers'] = [{'name': 'width', 'source_expression': expression}]
        _, result, loaded = helper.generate_page(source)
        self.assertEqual(result['verdict'], 'fail')
        self.assertTrue(any(n['style']['content']['text'] == 'Footer' for n in loaded['components']))
        errors = [u for n in loaded['components'] for u in n['unresolved']
                  if u['path'] == 'source.modifiers.unresolvedexpression']
        self.assertTrue(errors)
        self.assertTrue(all(u['expression'].strip() for u in errors))


if __name__ == '__main__':
    unittest.main()
