import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_generate_arkui_lanhu_input as fixtures
from generate_arkui_page import Renderer, derive_page_root, load_lanhu_page_input
from page_snapshot import PageSnapshotError, normalize_style
from ui_migration.contracts.style_defaults import DEFAULTS, apply_style_defaults


class ValidationStyleDefaultsTest(unittest.TestCase):
    def test_every_declared_default_passes_strict_validation(self):
        for path, default in DEFAULTS.items():
            with self.subTest(path=path):
                group, field = path.split('.')
                record = {'style': {group: {field: None}}, 'unresolved': [
                    {'path': 'style.' + path, 'expression': 'unknown', 'reason': 'not resolved'}]}
                warnings = apply_style_defaults(record, 'node')
                self.assertEqual(record['style'][group][field], default)
                self.assertEqual(len(warnings), 1)
                normalize_style(record['style'], 'style')
                self.assertFalse(record['unresolved'])

    def test_bad_literals_and_null_pending_facts(self):
        record = {'style': {'asset': {'tint': 'LocalContentColor.current'},
            'typography': {'font_size_sp': 'size', 'color': None}, 'surface': {'alpha': 7}},
            'requiredFacts': [{'path': 'style.typography.color', 'status': 'symbolic'}]}
        warnings = apply_style_defaults(record, 'node')
        self.assertEqual(len(warnings), 4)
        self.assertEqual(record['style']['asset']['tint'], '#FF000000')
        self.assertEqual(record['style']['typography']['font_size_sp'], 16)
        self.assertEqual(record['style']['surface']['alpha'], 1)
        self.assertEqual(record['requiredFacts'][0]['status'], 'default_resolved')
        normalize_style(record['style'], 'style')
        self.assertFalse(apply_style_defaults(record, 'node'))

    def test_valid_values_and_intentional_null_are_preserved(self):
        record = {'style': {'asset': {'tint': None}, 'typography': {'color': '#FFFF0000', 'font_size_sp': 18}},
                  'unresolved': []}
        before = copy.deepcopy(record)
        self.assertFalse(apply_style_defaults(record, 'node'))
        self.assertEqual(record, before)

    def test_resource_reference_wins_and_invalid_reference_stays_error(self):
        ref = {'android':'company.Theme.brand', 'kind':'color', 'key':'brand', 'target':{'module':'./Theme', 'export':'Theme',
               'member':'color', 'arguments':['brand']}}
        record = {'style': {'asset': {'tint':'old expression'}},
                  'source': {'style_token_references': {'asset.tint': ref}}}
        self.assertFalse(apply_style_defaults(record, 'node'))
        self.assertIsNone(record['style']['asset']['tint'])
        self.assertEqual(record['source']['style_token_references']['asset.tint'], ref)
        record['source']['style_token_references']['asset.tint'] = {'kind': 'not-a-color'}
        with self.assertRaises(ValueError):
            apply_style_defaults(record, 'node')

    def test_cross_property_constraints_are_repaired(self):
        record = {'style': {'control': {'minimum': 10, 'maximum': 5},
                           'typography': {'min_lines': 8, 'max_lines': 1}}}
        self.assertEqual(len(apply_style_defaults(record, 'node')), 4)
        normalize_style(record['style'], 'style')

    def test_unknown_schema_and_resource_integrity_remain_strict(self):
        for style in ({'asset': {'sha256':'invalid'}}, {'unknown': {}}, {'surface': {'unknown': 0}}):
            with self.subTest(style=style):
                apply_style_defaults({'style': style}, 'node')
                with self.assertRaises(PageSnapshotError):
                    normalize_style(style, 'style')

    def test_existing_json_loads_and_renders_after_prevalidation(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _ = fixtures.GenerateArkUILanhuInputTest().write_inputs(Path(directory))
            version = json.loads(path.read_text())
            migration = version['artboard']['layers'][0]['layers'][0]['migration']
            migration['style']['asset']['tint'] = 'LocalContentColor.current'
            migration['style']['surface']['alpha'] = 'alphaValue'
            path.write_text(json.dumps(version))
            with patch('ui_migration.contracts.lanhu.prepare_style_defaults', return_value=[]):
                with self.assertRaisesRegex(Exception, 'must be'):
                    load_lanhu_page_input(path)
            page = load_lanhu_page_input(path)
            renderer = Renderer(derive_page_root(page), {'media:ic_cover_ellipse'}, {}, page)
            code = renderer.render()
            self.assertIn('0xFF000000', code)
            self.assertEqual(len(page['generation_warnings']), 2)
            self.assertFalse(renderer.unresolved, renderer.unresolved)
            self.assertEqual(json.loads(path.read_text()), version)


if __name__ == '__main__':
    unittest.main()
