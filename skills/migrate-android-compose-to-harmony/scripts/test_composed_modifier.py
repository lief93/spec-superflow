import unittest

from analyze_compose_project import ordered_modifier_chain
from kotlin_psi import parse_expression
from page_snapshot import normalize_unresolved
from ui_migration.frontend.values import value_resolver
from ui_migration.frontend.projection import selected_modifiers
from ui_migration.semantics.errors import LayoutExpressionError
import test_layout_expressions as fixtures
from test_layout_mapping_contract import render_nodes


BODY = '''composed {
    if (autoMirror && LocalLayoutDirection.current == LayoutDirection.Rtl) {
        this.scale(scaleX = -1f, scaleY = 1f)
    } else {
        this
    }
}'''


class ComposedModifierTest(unittest.TestCase):
    def test_bare_composed_preserves_receiver_and_selects_mirror(self):
        for enabled, direction, mirrored in ((True, 'rtl', True),
                                               (True, 'ltr', False),
                                               (False, 'rtl', False)):
            with self.subTest(enabled=enabled, direction=direction):
                resolver = value_resolver({}, {'autoMirror': enabled,
                    'LocalLayoutDirection.current': direction}, ordered_modifier_chain)
                resolver.modifier_receivers['this'] = ordered_modifier_chain('Modifier.width(24.dp)')
                chain = resolver.chain(parse_expression(BODY))
                self.assertEqual([m['name'] for m in chain], ['width', 'scale'] if mirrored else ['width'])
                if mirrored:
                    self.assertIn('-1f', chain[-1]['arguments'])

    def test_qualified_composed_keeps_prefix_and_suffix_once(self):
        resolver = value_resolver({}, {}, ordered_modifier_chain)
        chain = resolver.chain(parse_expression('Modifier.width(24.dp).composed { this.height(30.dp) }.padding(2.dp)'))
        self.assertEqual([m['name'] for m in chain], ['width', 'height', 'padding'])

    def test_old_multiline_and_long_reasons_are_read_without_losing_details(self):
        for reason in ('unsupported modifier expression: ' + BODY, 'reason ' * 1000):
            entries = [{'path': 'source.modifiers.unresolvedexpression', 'expression': BODY, 'reason': reason}]
            self.assertEqual(normalize_unresolved(entries, 'migration.unresolved'), entries)

    def test_nested_factory_and_named_factory_ignore_inspector_metadata(self):
        resolver = value_resolver({}, {}, ordered_modifier_chain)
        chain = resolver.chain(parse_expression('''Modifier.width(24.dp).composed(
            inspectorInfo = { unsupportedInspector() },
            factory = { this.composed { this.height(30.dp) } }
        )'''))
        self.assertEqual([m['name'] for m in chain], ['width', 'height'])

    def test_unknown_condition_stays_diagnostic_not_a_guessed_mirror(self):
        resolver = value_resolver({}, {}, ordered_modifier_chain)
        chain, failures, _ = selected_modifiers([{'name': 'composed', 'source_expression': BODY}], resolver)
        self.assertEqual([m['name'] for m in chain], ['unresolvedExpression'])
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]['expression'], BODY)
        normalize_unresolved(failures, 'unresolved')

    def test_disabled_mirroring_does_not_need_layout_direction(self):
        resolver = value_resolver({}, {'autoMirror': False}, ordered_modifier_chain)
        self.assertEqual(resolver.chain(parse_expression(BODY)), [])

    def test_factory_replacement_does_not_reapply_incoming_chain(self):
        resolver = value_resolver({}, {}, ordered_modifier_chain)
        chain = resolver.chain(parse_expression('Modifier.width(24.dp).composed { Modifier.height(30.dp) }'))
        self.assertEqual([m['name'] for m in chain], ['height'])

    def test_factory_effects_and_invalid_signature_are_not_executed(self):
        for expression in ('Modifier.composed { someEffect(); this }',
                           'Modifier.composed(factory = unknown)',
                           'Modifier.composed { parameter -> this }'):
            with self.subTest(expression=expression), self.assertRaises(LayoutExpressionError):
                value_resolver({}, {}, ordered_modifier_chain).chain(parse_expression(expression))

    def test_business_modifier_reaches_generated_page_in_ltr_and_rtl(self):
        declarations = 'fun Modifier.autoMirror(autoMirror: Boolean): Modifier = ' + BODY
        for direction, mirrored in (('rtl', True), ('ltr', False)):
            with self.subTest(direction=direction):
                page = fixtures.LayoutExpressionTest().project(
                    'Box(Modifier.width(24.dp).autoMirror(true).height(30.dp)) {}',
                    declarations, {'LocalLayoutDirection.current': direction})
                box = next(n for n in page['components'] if n['type'] == 'Box')
                self.assertFalse(box['modifier_projection']['failures'])
                self.assertEqual(box['style']['transform']['scale_x'], -1 if mirrored else None)
                code, gate, renderer = render_nodes(page['components'])
                self.assertIn('.width(this.layoutPx(24))', code)
                self.assertIn('.height(this.layoutPx(30))', code)
                self.assertEqual('.scale(' in code, mirrored)
                if mirrored:
                    self.assertIn('.scale({ x: -1, y: 1 })', code)
                self.assertEqual(gate['verdict'], 'pass', gate)
                self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_missing_runtime_direction_still_generates_candidate_without_mirror(self):
        declarations = 'fun Modifier.autoMirror(autoMirror: Boolean): Modifier = ' + BODY
        page = fixtures.LayoutExpressionTest().project(
            'Box(Modifier.autoMirror(true)) {}', declarations)
        box = next(n for n in page['components'] if n['type'] == 'Box')
        self.assertTrue(box['modifier_projection']['failures'])
        code, gate, _ = render_nodes(page['components'])
        self.assertNotIn('.scale(', code)
        self.assertIn('build()', code)
        self.assertEqual(gate['verdict'], 'fail')


if __name__ == '__main__':
    unittest.main()
