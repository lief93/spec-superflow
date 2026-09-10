import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from ui_migration.verification.generation_diagnosis import diagnose
from ui_migration.verification.visual_triage import correlate


class VisualTriageTest(unittest.TestCase):
    def inputs(self):
        page = {'id': 'home', 'state': 'loaded'}
        source = {'page': page, 'components': [{'id': 's1', 'semantic_key': 'caption',
            'type': 'Text', 'source': {'source': 'Page.kt', 'line': 12},
            'style': {'typography': {'color': '#FFFF0000'}}}]}
        version = {'meta': {'migration': {'page': page}}, 'artboard': {'layers': [
            {'id': 's1', 'migration': {'semanticKey': 'caption', 'componentType': 'Text',
                'source': source['components'][0]['source'],
                'style': {'typography': {'color': '#FF000000'}}}}]}}
        comparison = {'schema': 'android-to-harmony.local-image-comparison.v1',
            'component_inventories': [{'side': side, 'page': page,
                'schema': 'android-to-harmony.page-snapshot.v2'} for side in ('left', 'right')],
            'viewport_compatibility': {'pixel_comparison_compatible': True},
            'difference_analysis': {'component_presence': {'missing_in_right': [], 'missing_in_left': []},
                'component_geometry_deltas': [], 'component_hierarchy_deltas': [],
                'component_style_deltas': [{'semantic_key': 'caption', 'status': 'fail',
                    'comparisons': [{'path': 'style.typography.color', 'left': '#FFFF0000',
                        'right': '#FF000000', 'over_tolerance': True}]}]}}
        worklist = {'tasks': [{'path': 'style.typography.color', 'expression': 'Theme.ink',
            'occurrences': [{'component_id': 's1', 'reason': 'unresolved color'}]}]}
        return diagnose(worklist), comparison, source, version

    def test_correlates_property_and_finds_first_observed_value_difference(self):
        diagnosis, comparison, source, version = self.inputs()
        result = correlate(diagnosis, comparison, source, version, {})
        finding = result['findings'][0]
        self.assertEqual(finding['related_issue_indexes'], [1])
        self.assertEqual(finding['trace']['last_matching_artifact'], 'source-page.json')
        self.assertEqual(finding['trace']['first_differing_artifact'], 'version_json.json')
        self.assertFalse(finding['root_cause_confirmed'])
        self.assertEqual(finding['evidence']['right'], '#FF000000')

    def test_runtime_difference_still_reported_without_unresolved(self):
        _, comparison, source, version = self.inputs()
        version['artboard']['layers'][0]['migration']['style']['typography']['color'] = '#FFFF0000'
        result = correlate(diagnose(), comparison, source, version, {})
        finding = result['findings'][0]
        self.assertEqual(finding['related_issue_indexes'], [])
        self.assertEqual(finding['trace']['last_matching_artifact'], 'version_json.json')
        self.assertEqual(finding['trace']['first_differing_artifact'], 'harmony runtime')

    def test_wrong_state_or_viewport_blocks_causal_join(self):
        for change in ('state', 'viewport'):
            diagnosis, comparison, source, version = self.inputs()
            if change == 'state':
                comparison['component_inventories'][1]['page'] = {'id': 'home', 'state': 'loading'}
            else:
                comparison['viewport_compatibility']['pixel_comparison_compatible'] = False
            result = correlate(diagnosis, comparison, source, version, {})
            self.assertFalse(result['comparable'])
            self.assertEqual(result['findings'][0]['priority'], 'P0')
            self.assertEqual(result['findings'][0]['related_issue_indexes'], [])

    def test_ambiguous_identity_is_not_guessed_from_names(self):
        diagnosis, comparison, source, version = self.inputs()
        source['components'].append({**copy.deepcopy(source['components'][0]), 'id': 's2'})
        finding = correlate(diagnosis, comparison, source, version, {})['findings'][0]
        self.assertEqual(finding['related_issue_indexes'], [])
        self.assertEqual(finding['source_binding'], 'ambiguous')
        self.assertIsNone(finding['trace']['last_matching_artifact'])

    def test_missing_component_ranks_before_style_and_retains_deferred_reason(self):
        diagnosis, comparison, source, version = self.inputs()
        comparison['difference_analysis']['component_presence']['missing_in_right'] = ['caption']
        diagnosis['issues'][0].update(status='deferred_dynamic', paths=['source.state_resolution'])
        diagnosis['issues'][0]['occurrences'][0]['path'] = 'source.state_resolution'
        result = correlate(diagnosis, comparison, source, version, {})
        finding = result['findings'][0]
        self.assertEqual(finding['kind'], 'missing_component')
        self.assertEqual(finding['priority'], 'P1')
        self.assertEqual(finding['related_issue_indexes'], [1])
        self.assertEqual(diagnosis['issues'][0]['status'], 'deferred_dynamic')

    def test_other_state_issue_is_not_joined_to_current_visual_difference(self):
        diagnosis, comparison, source, version = self.inputs()
        diagnosis['issues'][0]['occurrences'][0]['component_ui_state'] = 'Button/pressed'
        result = correlate(diagnosis, comparison, source, version, {})
        self.assertEqual(result['findings'][0]['related_issue_indexes'], [])

    def test_background_leaf_correlates_to_its_structured_property(self):
        diagnosis, comparison, source, version = self.inputs()
        diagnosis['issues'][0]['occurrences'][0]['path'] = 'style.surface.background'
        comparison['difference_analysis']['component_style_deltas'][0]['comparisons'][0]['path'] = 'style.surface.background.color'
        result = correlate(diagnosis, comparison, source, version, {})
        self.assertEqual(result['findings'][0]['related_issue_indexes'], [1])

    def test_refresh_command_updates_one_report_without_changing_generation_verdict(self):
        from ui_migration.contracts.identity import canonical_sha256
        _, comparison, source, version = self.inputs()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'lanhu').mkdir()
            (root/'source-page.json').write_text(json.dumps(source))
            raw = json.dumps(version).encode()
            (root/'lanhu/version_json.json').write_bytes(raw)
            version_sha = hashlib.sha256(raw).hexdigest()
            (root/'lanhu/unresolved-worklist.json').write_text(json.dumps({'version_json_sha256': version_sha}))
            manifest = {'semantic_input_sha256': canonical_sha256({'input_mode': 'page-json-only',
                'page_json_sha256': canonical_sha256({'version_json_sha256': version_sha})})}
            (root/'manifest.json').write_text(json.dumps(manifest))
            report = {'status': 'generated', 'generation_complete': True, 'verdict': 'pass',
                      'arkui': {'manifest': str(root/'manifest.json')}}
            (root/'result.json').write_text(json.dumps(report))
            (root/'comparison.json').write_text(json.dumps(comparison))
            command = [sys.executable, str(Path(__file__).with_name('diagnose_page_fidelity.py')),
                       '--run-dir', str(root), '--comparison-report', str(root/'comparison.json')]
            for _ in range(2):
                completed = subprocess.run(command, capture_output=True, text=True, timeout=20)
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                result = json.loads((root/'result.json').read_text())
                self.assertEqual(result['verdict'], 'pass')
                self.assertEqual(result['diagnosis']['visual_triage']['finding_count'], 1)
                self.assertEqual(Path(result['diagnosis_report']), (root/'diagnosis.md').resolve())
                self.assertIn('实测异常与生成诊断关联', (root/'diagnosis.md').read_text())
            previous = (root/'result.json').read_bytes()
            (root/'lanhu/version_json.json').write_text(json.dumps({**version, 'changed': True}))
            completed = subprocess.run(command, capture_output=True, text=True, timeout=20)
            self.assertEqual(completed.returncode, 1)
            self.assertIn('different version_json', completed.stdout)
            self.assertEqual((root/'result.json').read_bytes(), previous)

    def test_real_local_comparator_output_is_consumed_without_ai(self):
        from test_compare_local_screenshots import write_solid_ppm, write_page_snapshot_v2
        _, _, source, version = self.inputs()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for side, density, size in [('android', 3, (192, 144)), ('harmony', 2, (128, 96))]:
                screenshot = root/(side + '.ppm')
                write_solid_ppm(screenshot, *size)
                write_page_snapshot_v2(root/(side + '.json'), side, screenshot, density,
                    radius_dp=8, font_size_sp=16 if side == 'android' else 20,
                    background='#FFFFFFFF', asset_sha256='a'*64, state_id='loaded')
            command = [sys.executable, str(Path(__file__).with_name('compare_local_screenshots.py')),
                '--left', str(root/'android.ppm'), '--right', str(root/'harmony.ppm'),
                '--left-components', str(root/'android.json'), '--right-components', str(root/'harmony.json'),
                '--output-dir', str(root/'comparison')]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            comparison = json.loads((root/'comparison/comparison.json').read_text())
            result = correlate(diagnose(), comparison, source, version, {})
            self.assertTrue(result['comparable'])
            self.assertTrue(any(f['path'] == 'style.typography.font_size_sp' and
                f['evidence']['left'] == 16 and f['evidence']['right'] == 20 for f in result['findings']))
