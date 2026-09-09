import copy
import json
from pathlib import Path
import tempfile
import unittest

from ui_migration.contracts.lanhu_storage import (
    pack_lanhu_document, unpack_lanhu_document, STORAGE, REFERENCE, SCHEMA)


class LanhuStorageTest(unittest.TestCase):
    def test_roundtrip_preserves_identity_order_types_and_isolation(self):
        style = {'color':'#FF0000', 'facts':[{'path':str(i), 'value':None} for i in range(30)]}
        source = {'meta':{}, 'assets':[], 'artboard':{'layers':[
            {'id':f'item__page{i}', 'parent_id':'pager', 'style':copy.deepcopy(style),
             'values':[False, 0, 0.0, -0.0, True, None, '中文']}
            for i in range(20)]}}
        packed = pack_lanhu_document(source)
        self.assertIn(STORAGE, packed)
        self.assertEqual(json.dumps(unpack_lanhu_document(packed)), json.dumps(source))
        self.assertLess(len(json.dumps(packed)), len(json.dumps(source)) * .3)
        self.assertEqual(pack_lanhu_document(packed), packed)
        unpacked = unpack_lanhu_document(packed)
        unpacked['artboard']['layers'][0]['style']['facts'].clear()
        self.assertEqual(len(unpacked['artboard']['layers'][1]['style']['facts']), 30)
        self.assertEqual([n['id'] for n in unpacked['artboard']['layers']],
                         [f'item__page{i}' for i in range(20)])

    def test_invalid_references_and_schema_fail(self):
        for shared, key, error in [({}, 'absent', 'missing'),
            ({'a':{REFERENCE:'b'}, 'b':{REFERENCE:'a'}}, 'a', 'cyclic')]:
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                unpack_lanhu_document({'meta':{REFERENCE:key}, STORAGE:{'schema':SCHEMA, 'shared':shared}})
        with self.assertRaisesRegex(ValueError, 'unsupported'):
            unpack_lanhu_document({STORAGE:{'schema':'future'}})
        with self.assertRaisesRegex(ValueError, 'reserved'):
            pack_lanhu_document({'meta':{REFERENCE:'literal'}})

    def test_single_json_renders_all_pager_states_identically(self):
        from test_component_ui_states import compile_states
        from test_pager_component_states import PAGER, ITEM
        from generate_arkui_page import Renderer, load_lanhu_page_input, derive_page_root
        version, original, expected, _ = compile_states('@Composable fun Page() {\n' + PAGER + '\n}\n' + ITEM)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'version_json.json'
            for document in [version, pack_lanhu_document(version)]:
                path.write_text(json.dumps(document))
                page = load_lanhu_page_input(path)
                renderer = Renderer(derive_page_root(page), set(), {}, page)
                self.assertEqual(renderer.render(), expected)
                self.assertEqual(renderer.unresolved, original.unresolved)
                self.assertEqual(len(page['component_ui_states']), 4)
                self.assertEqual([c['selected'] for c in page['component_ui_states'].values()],
                                 ['then', 'else', 'else', 'else'])

    def test_resource_and_diagnosis_readers_expand_references(self):
        from materialize_static_drawables import page_asset_hashes
        from ui_migration.verification.generation_diagnosis import diagnose
        shared = {'style':{'asset':{'resource':'cover', 'sha256':'a'*64}},
                  'source':{'source':'Page.kt', 'line':3, 'composable':'Page'},
                  'componentType':'Image', 'extra':'x'*300}
        document = {'meta':{}, 'assets':['cover'], 'artboard':{'layers':[
            {'id':str(i), 'migration':copy.deepcopy(shared)} for i in range(2)]}}
        worklist = {'tasks':[{'path':'style.asset.resource', 'expression':'cover',
            'occurrences':[{'component_id':'0', 'reason':'missing image'}]}]}
        packed = pack_lanhu_document(document)
        self.assertIn(STORAGE, packed)
        self.assertEqual(diagnose(worklist=worklist, version_page=packed),
                         diagnose(worklist=worklist, version_page=document))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'version_json.json'
            path.write_text(json.dumps(packed))
            self.assertEqual(page_asset_hashes(path), {'cover':'a'*64})


if __name__ == '__main__':
    unittest.main()
