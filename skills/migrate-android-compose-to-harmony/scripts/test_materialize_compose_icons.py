import unittest
from materialize_compose_icons import convert
from ui_migration.contracts.material_icons import material_icon_identity


class MaterialIconTest(unittest.TestCase):
    def test_arc_commands_preserve_radii_rotation_flags_and_endpoint(self):
        source = '''val Icons.Rounded.Example: ImageVector
get() { cached = materialIcon(name = "Rounded.Example") {
    materialPath { moveTo(1f, 2f)
        arcToRelative(3f, 4f, 45f, true, false, 5f, 6f)
        arcTo(2f, 2f, 0f, false, true, 10f, 12f)
    }
}; return cached!! }'''
        self.assertIn('a3 4 45 1 0 5 6 A2 2 0 0 1 10 12', convert(source).decode())
        with self.assertRaises(ValueError):
            convert(source.replace('45f, true', '45f, 2f'))

    def test_material_icon_has_logical_intrinsic_size_before_asset_is_rendered(self):
        from test_dp_size import DpSizeTest
        from test_layout_mapping_contract import render_nodes
        page = DpSizeTest().source_page('Icon(imageVector = Icons.Rounded.ChevronRight, contentDescription = null)')
        icon = next(n for n in page['components'] if n['type'] == 'Icon')
        self.assertEqual(icon['style']['asset']['width_dp'], 24)
        output, _, _ = render_nodes(page['components'])
        self.assertIn('.constraintSize({ maxWidth: 24, maxHeight: 24 })', output)

    def test_source_paths_are_preserved_and_not_substituted(self):
        source = '''val Icons.Rounded.Example: ImageVector
get() { cached = materialIcon(name = "Rounded.Example") {
    materialPath { moveTo(1f, 2f); lineToRelative(3f, -4f); close() }
}; return cached!! }'''
        svg = convert(source).decode()
        self.assertIn('d="M1 2 l3 -4 Z"', svg)
        self.assertIn('viewBox="0 0 24 24"', svg)
        self.assertEqual(material_icon_identity('Icons.AutoMirrored.Rounded.KeyboardArrowLeft'),
                         ('automirrored/rounded/KeyboardArrowLeft.kt', 'compose_icon_automirrored_rounded_keyboardarrowleft'))
        self.assertIsNone(material_icon_identity('Other.Search'))
        with self.assertRaises(ValueError):
            convert(source.replace('lineToRelative(3f, -4f)', 'unknownPath()'))


if __name__ == '__main__':
    unittest.main()
