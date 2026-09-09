import copy
import json
import unittest

from ui_migration.contracts.source_storage import pack_source_page, unpack_source_page, STORAGE, REFERENCE, SCHEMA


class SourceStorageTest(unittest.TestCase):
    def test_lossless_sharing_preserves_nulls_types_order_and_all_nodes(self):
        scope = {'imports': {f'name{i}': f'com.example.library.name{i}' for i in range(40)}, 'owner': None}
        page = {'schema': 'android-to-harmony.source-page-spec.v1', 'page': {'id': 'page', 'state': 'loaded'},
                'components': [{'id':str(i), 'parent_id':None, 'scope':copy.deepcopy(scope),
                                'background':None, 'values':[False, 0, 0.0, -0.0, True, 1, 1.0, '中文']}
                               for i in range(20)]}
        original = copy.deepcopy(page)
        packed = pack_source_page(page)
        self.assertEqual(unpack_source_page(packed), page)
        self.assertEqual(json.dumps(unpack_source_page(packed)), json.dumps(page))
        self.assertEqual(page, original)
        self.assertEqual([n['id'] for n in packed['components']], [str(i) for i in range(20)])
        self.assertLess(len(json.dumps(packed)), len(json.dumps(page)) * .3)
        self.assertEqual(pack_source_page(packed), packed)
        unpacked = unpack_source_page(packed)
        unpacked['components'][0]['scope']['imports'].clear()
        self.assertTrue(unpacked['components'][1]['scope']['imports'])

    def test_missing_cyclic_and_unknown_encodings_fail_explicitly(self):
        for table, reference, message in [({}, 'absent', 'missing'),
            ({'a':{REFERENCE:'b'}, 'b':{REFERENCE:'a'}}, 'a', 'cyclic')]:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                unpack_source_page({'components':{REFERENCE:reference}, STORAGE:{'schema':SCHEMA, 'shared':table}})
        with self.assertRaisesRegex(ValueError, 'unsupported'):
            unpack_source_page({STORAGE:{'schema':'future'}})

    def test_inline_documents_and_literal_reference_collision(self):
        page = {'components':[], 'unresolved':[{'value':None}]}
        self.assertEqual(pack_source_page(page), page)
        with self.assertRaisesRegex(ValueError, 'reserved'):
            pack_source_page({'value':{REFERENCE:'literal'}})

    def test_packed_and_inline_inputs_render_identically_without_source(self):
        import argparse
        from pathlib import Path
        import tempfile
        from test_business_components import compile_page
        from generate_lanhu_source_page import generate
        from generate_arkui_page import Renderer, load_lanhu_page_input, derive_page_root
        source, _, _, _, expected = compile_page('''
@Composable fun Page() { Column { Label("One"); Label("Two") } }
@Composable fun Label(title: String) { Text(title) }
''')
        from ui_migration.frontend.api_adapters.scan import scan_source_page
        from ui_migration.verification.generation_diagnosis import diagnose
        from generate_ui_state_previews import build_catalog
        self.assertEqual(scan_source_page(pack_source_page(source)), scan_source_page(source))
        self.assertEqual(diagnose(source_page=pack_source_page(source)), diagnose(source_page=source))
        self.assertEqual(build_catalog(pack_source_page(source)), build_catalog(source))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root/'source.json'
            path.write_text(json.dumps(pack_source_page(source)))
            generate(argparse.Namespace(source_page=path, state_fixture=None, output_dir=root/'page',
                viewport_width_dp=360, viewport_height_dp=740, slice_scale=2, device='component-test'))
            path.unlink()
            page = load_lanhu_page_input(root/'page/version_json.json')
            actual = Renderer(derive_page_root(page), set(), {}, page).render()
            self.assertEqual(actual, expected)


if __name__ == '__main__':
    unittest.main()
