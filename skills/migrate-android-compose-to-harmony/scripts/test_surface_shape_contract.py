import unittest

from generate_lanhu_source_page import evaluate_expression, UNRESOLVED
from page_snapshot import empty_style, normalize_style, PageSnapshotError
from ui_migration.arkui.surface import SurfaceEmitter
import test_ui_state_semantics as semantics


class SurfaceShapeContractTest(unittest.TestCase):
    def test_percent_and_pixels_are_not_dp(self):
        self.assertEqual(evaluate_expression('RoundedCornerShape(percent = 40)', {})['radius_percent'], 40)
        self.assertEqual(evaluate_expression('RoundedCornerShape(8f)', {})['radius_px'], 8)
        self.assertIs(evaluate_expression('RoundedCornerShape(101)', {}), UNRESOLVED)
        self.assertIs(evaluate_expression('RoundedCornerShape(3.sp)', {}), UNRESOLVED)

    def test_selected_forwarded_shape_reaches_clip_without_guessing_dimensions(self):
        helper = semantics.UiStateSemanticsTest()
        source = helper.source('Tile(radius = percent)', '''
@Composable
fun Tile(radius: Int) {
    val shape = if (selected) RoundedCornerShape(radius) else CircleShape
    Box(Modifier.fillMaxWidth().height(40.dp).clip(shape).background(Color(0xFF123456)))
}
''')
        for selected, expected in [(True, 40), (False, 50)]:
            page = helper.strict(source, {'percent': 40, 'selected': selected})
            box = next(node for node in page['components'] if node['type'] == 'Box')
            surface = box['style']['surface']
            self.assertTrue(surface['clip'])
            self.assertEqual(surface['corner_sizes']['top_left'], {'value': expected, 'unit': 'percent'})
            self.assertIsNone(surface['corner_radius_dp'])

    def test_relative_corners_need_direction_but_absolute_corners_do_not(self):
        from ui_migration.frontend.shapes import shape_surface
        shape = evaluate_expression('RoundedCornerShape(topStart = 8.dp, topEnd = 2.dp)', {})
        self.assertIsNone(shape_surface(shape, None))
        self.assertEqual(shape_surface(shape, 'rtl')['corner_radius_dp']['top_right'], 8)
        absolute = evaluate_expression('AbsoluteRoundedCornerShape(topLeft = 8.dp)', {})
        self.assertEqual(shape_surface(absolute, None)['corner_radius_dp']['top_left'], 8)

    def test_typed_corners_are_validated_in_single_document(self):
        style = empty_style()
        style['surface']['corner_sizes'] = dict.fromkeys(
            ['top_left', 'top_right', 'bottom_right', 'bottom_left'], {'unit': 'percent', 'value': 40})
        self.assertEqual(normalize_style(style, 'style'), style)
        style['surface']['corner_sizes']['top_left'] = {'unit': 'sp', 'value': 4}
        with self.assertRaises(PageSnapshotError):
            normalize_style(style, 'style')

    def test_native_types_share_size_dependent_shape_and_border_owner(self):
        for kind in ['Row', 'Column', 'Box', 'Text', 'Image', 'Button']:
            style = empty_style()
            style['surface'].update(corner_sizes=dict.fromkeys(
                ['top_left', 'top_right', 'bottom_right', 'bottom_left'], {'unit': 'percent', 'value': 40}),
                clip=True, border={'width_dp': 1, 'color': '#FF123456', 'style': 'solid'})
            errors = []
            emitter = SurfaceEmitter(lambda *args: errors.append(args))
            lines, fields, updates = emitter.emit({'id': kind, 'type': kind, 'style': style}, '')
            output = '\n'.join(lines + sum(emitter.builders, []) + updates)
            self.assertIn('style.surface.corner_sizes', fields)
            self.assertIn('Math.min(Number(current.width), Number(current.height))', output)
            self.assertIn('0.4', output)
            self.assertNotIn('.borderRadius(40)', output)
            self.assertFalse(errors)

    def test_source_and_target_agree_on_field_phases(self):
        from ui_migration.contracts.consumption import target_fact_phase
        from ui_migration.frontend.lanhu_export import required_phase_paths
        fields = {'source.modifiers.size': 'measure', 'source.modifiers.padding': 'measure',
                  'style.typography.font_size_sp': 'measure', 'style.layout.alignment': 'layout',
                  'source.modifiers.align': 'layout', 'source.modifiers.border': 'draw',
                  'style.surface.corner_sizes': 'draw'}
        node = {'required_facts': [{'path': path, 'status': 'resolved'} for path in fields]}
        for path, expected in fields.items():
            self.assertEqual(target_fact_phase(path), expected)
            self.assertIn(path, required_phase_paths(node, expected))
            self.assertNotIn(path, sum((required_phase_paths(node, phase) for phase in ('measure', 'layout', 'draw')
                                       if phase != expected), []))

    def test_conditional_draw_properties_share_selected_modifier_projection(self):
        helper = semantics.UiStateSemanticsTest()
        source = helper.source('Tile()', '''
@Composable
fun Tile() {
    Box(Modifier.size(80.dp).then(if (selected) Modifier
        .border(width = 2.dp, color = Color(0xFF123456), shape = RoundedCornerShape(8.dp))
        .scale(scaleX = 0.5f, scaleY = 0.75f).rotate(30f) else Modifier))
}
''')
        for selected in (True, False):
            page = helper.strict(source, {'selected': selected})
            box = next(n for n in page['components'] if n['type'] == 'Box')
            self.assertEqual(box['style']['transform']['rotation_degrees'], 30 if selected else None)
            self.assertEqual(box['style']['transform']['scale_x'], 0.5 if selected else None)
            self.assertEqual(box['style']['surface']['border'],
                             {'width_dp': 2, 'color': '#FF123456', 'style': 'solid'} if selected else None)


if __name__ == '__main__':
    unittest.main()
