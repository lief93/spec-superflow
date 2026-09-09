import unittest

import test_keyed_resources as helpers


EXTENSION = '''from ui_migration.frontend.api_adapters.keyed_resources import KeyedResourceAdapter

class Colors(KeyedResourceAdapter):
    def resolve(self, reference):
        return {"key": reference.key, "target": {"module":"./ThemeBridge",
            "export":"ThemeBridge", "member":"color", "arguments":[reference.key]}}

ADAPTERS = [Colors("company.theme-colors", ("company.DeclarativeTheme.colors.*",), "color").declaration()]
'''

DECLARATIONS = '''
data class ButtonStyle(val loadingTint: Color)
@Composable fun secondaryButtonStyle(): ButtonStyle = ButtonStyle(SecondaryButtonTokens.spinner)
internal object SecondaryButtonTokens {
    val spinner: Color
        @Composable get() = company.DeclarativeTheme.colors.compButtonColorSecondarySpinner ?: Color.Black
}
'''


class PropertyResourcesTest(unittest.TestCase):
    generate = helpers.KeyedResourcesTest.generate

    def test_style_factory_record_getter_reaches_library_key(self):
        page, code, result, renderer = self.generate(
            'Text("Loading", color = secondaryButtonStyle().loadingTint)', DECLARATIONS, EXTENSION)
        text = next(n for n in page['components'] if n['type'] == 'Text')
        reference = text['source']['style_token_references']['typography.color']
        self.assertEqual(reference['key'], 'compButtonColorSecondarySpinner')
        self.assertEqual(reference['kind'], 'color')
        self.assertEqual(reference['fallback'], '#FF000000')
        self.assertIn("color('compButtonColorSecondarySpinner') ?? \"#FF000000\"", code)
        self.assertNotIn('secondaryButtonStyle()', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_direct_property_keeps_reference_without_hex(self):
        _, code, result, renderer = self.generate(
            'Text("Hello", color = company.DeclarativeTheme.colors.primary)', extension=EXTENSION)
        self.assertIn(".fontColor(StyleToken0.color('primary'))", code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved)

    def test_progress_color_from_style_chain(self):
        page, code, result, renderer = self.generate(
            'CircularProgressIndicator(progress = 0.5f, color = secondaryButtonStyle().loadingTint)',
            DECLARATIONS, EXTENSION)
        node = next(n for n in page['components'] if n['type'] == 'CircularProgressIndicator')
        self.assertEqual(node['source']['style_token_references']['control.active_color']['key'],
                         'compButtonColorSecondarySpinner')
        self.assertIn('.color((StyleToken', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_cross_file_factory_and_block_getter_with_import_alias(self):
        _, code, result, renderer = self.generate('Text("A", color = style().loadingTint)',
            extension=EXTENSION, source_imports='import pieces.secondaryButtonStyle as style', extra_files={
                'Style.kt': 'package pieces\nimport tokens.Tokens\n' +
                    'data class ButtonStyle(val loadingTint: Color)\n' +
                    'fun secondaryButtonStyle() = ButtonStyle(Tokens.spinner)',
                'Tokens.kt': 'package tokens\nimport company.DeclarativeTheme as Theme\n' +
                    'object Tokens { val spinner: Color get() { return Theme.colors.spinner ?: Color.Black } }'})
        self.assertIn("color('spinner') ?? \"#FF000000\"", code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_fixed_branch_selects_only_its_key(self):
        _, code, result, _ = self.generate(
            'Text("A", color = choose(false))', '''
fun choose(pressed: Boolean): Color = if (pressed) company.DeclarativeTheme.colors.pressed
    else company.DeclarativeTheme.colors.normal
''', EXTENSION)
        self.assertIn("color('normal')", code)
        self.assertNotIn("color('pressed')", code)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_same_member_on_other_owner_is_not_adapted(self):
        _, code, result, _ = self.generate('Text("A", color = other.Theme.colors.primary ?: Color.Black)', extension=EXTENSION)
        self.assertNotIn('ThemeBridge', code)
        self.assertFalse(result['generation_complete'])
        self.assertTrue(any('unknown fixed-state' in u.get('reason', '') for u in result['unresolved']))

    def test_known_null_and_nonnull_elvis_keep_kotlin_behavior(self):
        for expression, color in [('null ?: Color.Black', '#FF000000'),
                                  ('Color.Red ?: company.DeclarativeTheme.colors.unused', '#FFFF0000')]:
            with self.subTest(expression=expression):
                _, code, result, _ = self.generate('Text("A", color = ' + expression + ')', extension=EXTENSION)
                self.assertIn(color, code)
                self.assertNotIn('ThemeBridge', code)
                self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_cyclic_getter_is_unresolved_not_default_black(self):
        _, code, result, _ = self.generate('Text("A", color = Tokens.a ?: Color.Black)', '''
object Tokens { val a: Color get() = b; val b: Color get() = a }
''', EXTENSION)
        self.assertFalse(result['generation_complete'])
        self.assertNotIn(".fontColor('#FF000000')", code)

    def test_repeated_properties_keep_independent_keys(self):
        _, code, result, renderer = self.generate('Column { Text("A", color = company.DeclarativeTheme.colors.first); Text("B", color = company.DeclarativeTheme.colors.second) }', extension=EXTENSION)
        self.assertIn("color('first')", code)
        self.assertIn("color('second')", code)
        self.assertEqual(code.count('import { ThemeBridge'), 1)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_incompatible_fallback_is_unresolved(self):
        _, _, result, _ = self.generate('Text("A", color = company.DeclarativeTheme.colors.primary ?: "not a color")', extension=EXTENSION)
        self.assertFalse(result['generation_complete'])

    def test_duplicate_owner_registration_is_rejected(self):
        from ui_migration.frontend.api_adapters.registry import AdapterConflict, AdapterRegistry
        scope = {}
        exec(EXTENSION, scope)
        other = scope['Colors']('other', ('company.DeclarativeTheme.colors.*',), 'color').declaration()
        with self.assertRaisesRegex(AdapterConflict, 'duplicate resource owner'):
            AdapterRegistry([*scope['ADAPTERS'], other])

    def test_one_resolver_handles_calls_and_properties_and_remaps_keys(self):
        extension = '''from ui_migration.frontend.api_adapters.keyed_resources import KeyedResourceAdapter
class Colors(KeyedResourceAdapter):
    def resolve(self, reference):
        assert reference.kind == 'color'
        assert reference.symbol in ('company.Theme.colors.primary', 'company.Theme.color')
        assert reference.arguments == {} or reference.arguments == {'key': 'primary'}
        key = 'palette.' + reference.key
        return {'key': key, 'target': {'module':'./ThemeBridge', 'export':'ThemeBridge',
            'member':'color', 'arguments':[key]}}
ADAPTERS = [Colors('theme', ('company.Theme.colors.*', 'company.Theme.color'), 'color').declaration()]
'''
        page, code, result, renderer = self.generate(
            'Column { Text("A", color = T.colors.primary); Text("B", color = T.color("primary")) }',
            extension=extension, source_imports='import company.Theme as T')
        references = [n['source']['style_token_references']['typography.color'] for n in page['components'] if n['type']=='Text']
        self.assertEqual([r['key'] for r in references], ['palette.primary', 'palette.primary'])
        self.assertEqual(code.count("color('palette.primary')"), 2)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_resolver_can_extract_key_from_nonstandard_arguments(self):
        extension = '''from ui_migration.frontend.api_adapters.keyed_resources import KeyedResourceAdapter
class Colors(KeyedResourceAdapter):
    def resolve(self, reference):
        key = reference.arguments['tokenId']
        return {'key': key, 'target': {'module':'./ThemeBridge', 'export':'ThemeBridge',
            'member':'color', 'arguments':[key]}}
ADAPTERS = [Colors('theme', ('company.Theme.color',), 'color').declaration()]
'''
        _, code, result, _ = self.generate('Text("A", color = company.Theme.color(tokenId = "brand"))', extension=extension)
        self.assertIn("color('brand')", code)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_legacy_target_callback_also_accepts_property_registration(self):
        extension = '''from ui_migration.frontend.api_adapters.keyed_resources import KeyedResourceAdapter
class Colors(KeyedResourceAdapter):
    def harmony_target(self, key, arguments):
        assert arguments == {}
        return {'module':'./ThemeBridge', 'export':'ThemeBridge', 'member':'color', 'arguments':[key]}
ADAPTERS = [Colors('theme', ('company.Theme.colors.*', 'company.Theme.color'), 'color').declaration()]
'''
        _, code, result, _ = self.generate('Column { Text("A", color = company.Theme.colors.primary); Text("B", color = company.Theme.color("primary")) }', extension=extension)
        self.assertEqual(code.count("color('primary')"), 2)
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_color_reference_selects_color_helper_overload(self):
        _, code, result, renderer = self.generate(
            'Text("A", color = choose(company.DeclarativeTheme.colors.primary))', '''
fun choose(value: String): Color = Color.Red
fun choose(value: Color): Color = value
''', EXTENSION)
        self.assertIn("color('primary')", code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_unknown_branch_does_not_choose_a_key(self):
        _, code, result, _ = self.generate(
            'Text("A", color = if (unknownFlag) company.DeclarativeTheme.colors.first else company.DeclarativeTheme.colors.second)',
            extension=EXTENSION)
        self.assertNotIn('ThemeBridge', code)
        self.assertFalse(result['generation_complete'])

    def test_icon_tint_uses_resource_call_when_asset_is_available(self):
        from generate_arkui_page import Renderer, derive_page_root
        page, _, result, _ = self.generate(
            'Icon(painterResource(R.drawable.cover), contentDescription = "Icon", tint = company.DeclarativeTheme.colors.primary)',
            extension=EXTENSION)
        renderer = Renderer(derive_page_root(page), {'media:cover'}, {}, page)
        code = renderer.render()
        self.assertIn(".fillColor(StyleToken0.color('primary'))", code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)


if __name__ == '__main__':
    unittest.main()
