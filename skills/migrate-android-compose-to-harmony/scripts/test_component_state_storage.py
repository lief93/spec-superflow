import json
import copy
import unittest
from unittest.mock import patch

from test_component_ui_states import compile_states
from ui_migration.contracts.component_ui_states import decode_catalogs, variant_source_generation


class ComponentStateStorageTest(unittest.TestCase):
    def test_decoder_does_not_copy_other_variants_or_main_page_layers(self):
        version, _, _, _ = compile_states()
        catalogs = version['meta']['migration']['componentUiStates']
        blocked = [catalogs, version['meta'], version['artboard'], version['artboard']['layers']]
        deepcopy = copy.deepcopy

        def checked_copy(value, *args, **kwargs):
            self.assertFalse(any(value is item for item in blocked), 'copied a whole-page container')
            return deepcopy(value, *args, **kwargs)

        original = json.dumps(version)
        with patch('ui_migration.contracts.component_ui_states.copy.deepcopy', side_effect=checked_copy):
            result = decode_catalogs(version, lambda document: {'components':[
                {'parent_id':None, 'definition_id':catalogs[0]['definition_id']}]})
        self.assertEqual(len(result[catalogs[0]['instance_id']]['variants']), 3)
        self.assertEqual(original, json.dumps(version))

    def test_layout_context_and_phase_failures_are_not_trimmed(self):
        source = {'layoutRelationships':[{'id':'relation'}],
                  'stateProjection':{'root_layout_context':'caller_owned', 'inactive_source_ids':['unused']},
                  'warnings':[{'reason':'caller-owned placement'}],
                  'phaseConsumptionGate':{'verdict':'fail', 'failures':[{'reason':'unconsumed layout'}]}}
        compact = variant_source_generation(source)
        self.assertEqual(compact['layoutRelationships'], source['layoutRelationships'])
        self.assertEqual(compact['phaseConsumptionGate'], source['phaseConsumptionGate'])
        self.assertEqual(compact['warnings'], source['warnings'])
        self.assertEqual(compact['stateProjection'], {'root_layout_context':'caller_owned'})

    def test_variants_only_embed_consumed_generation_metadata(self):
        version, _, _, _ = compile_states()
        for catalog in version['meta']['migration']['componentUiStates']:
            for variant in catalog['variants']:
                self.assertNotIn('projection', variant)
                self.assertEqual(set(variant['source_generation']), {
                    'layoutRelationships', 'stateProjection', 'warnings', 'phaseConsumptionGate'})
                projection = variant['source_generation']['stateProjection']
                self.assertTrue(projection is None or set(projection) <= {'root_layout_context'})

    def test_legacy_metadata_and_compact_metadata_generate_identical_code(self):
        compact, compact_renderer, compact_code, compact_result = compile_states()
        with patch('generate_lanhu_source_page.variant_source_generation', side_effect=lambda value: value):
            legacy, legacy_renderer, legacy_code, legacy_result = compile_states()
        self.assertEqual(compact_code, legacy_code)
        self.assertEqual(compact_renderer.unresolved, legacy_renderer.unresolved)
        self.assertEqual(compact_result['unresolved'], legacy_result['unresolved'])
        self.assertEqual(compact_result['verdict'], legacy_result['verdict'])
        self.assertLess(len(json.dumps(compact)), len(json.dumps(legacy)))

    def test_failed_unselected_variant_remains_failed(self):
        version, _, _, result = compile_states('''
@Composable fun Page() { Badge(false) }
@Composable fun Badge(loading: Boolean) {
    if (loading) { Box(Modifier.size(40.dp).background(unknownColor)) }
    else { Text("Ready", color = Color.Black) }
}
''')
        self.assertFalse(result['generation_complete'])
        self.assertTrue(any(u.get('component_ui_state') == 'Badge/then' for u in result['unresolved']))
        self.assertEqual(version['meta']['sourceGeneration']['unresolved'], result['unresolved'])


if __name__ == '__main__':
    unittest.main()
