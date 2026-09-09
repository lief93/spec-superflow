import unittest

from ui_migration.verification.generation_diagnosis import diagnose, render_markdown


class GenerationDiagnosisTest(unittest.TestCase):
    def task(self, reason, expression='page in arrayOf(0, 1, 2)', path='source.state'):
        return {'path':path, 'expression':expression, 'context':{'bindings':{'page':'0'}},
            'occurrences':[{'component_id':'a', 'component_type':'Button',
                'source':{'source':'Page.kt','line':12,'composable':'Page'}, 'reason':reason}]}

    def test_state_failure_does_not_claim_supplied_variable_is_missing(self):
        item = self.task('state selection is unresolved; source template retained, not selected')
        result = diagnose({'tasks':[item]})
        issue = result['issues'][0]
        self.assertEqual(issue['code'], 'state_not_selected')
        self.assertEqual(issue['bindings'], {'page':'0'})
        self.assertFalse(issue['root_cause_confirmed'])
        self.assertEqual(issue['occurrences'][0]['source']['line'], 12)
        self.assertNotIn('缺少 page', issue['summary'])

    def test_known_mapping_gap_is_explained(self):
        result = diagnose({'tasks':[self.task('modifier has no declared page-layout mapping',
            'windowInsetsPadding(WindowInsets.statusBars)', 'modifiers.windowInsetsPadding')]})
        issue = result['issues'][0]
        self.assertEqual(issue['code'], 'modifier_mapping_missing')
        self.assertEqual(issue['impact'], 'layout')
        self.assertIn('映射', issue['summary'])

    def test_same_issue_from_source_and_target_is_not_double_counted(self):
        task = self.task('modifier has no declared page-layout mapping', 'foo()', 'modifiers.foo')
        manifest = {'unresolved':[{'page_component_id':'a', 'path':'modifiers.foo', 'expression':'foo()',
            'page_reason':task['occurrences'][0]['reason'], 'reason':'Source fact remains unresolved'}]}
        result = diagnose({'tasks':[task]}, manifest)
        self.assertEqual(len(result['issues']), 1)
        self.assertEqual(len(result['issues'][0]['occurrences']), 1)
        self.assertEqual(result['issues'][0]['evidence'], ['arkui_manifest', 'unresolved_worklist'])

    def test_same_expression_with_different_bindings_is_not_merged(self):
        first = self.task('state selection is unresolved')
        second = self.task('state selection is unresolved')
        second['context']['bindings'] = {'page':'3'}
        result = diagnose({'tasks':[first,second]})
        self.assertEqual(len(result['issues']), 2)

    def test_target_only_error_gets_source_location(self):
        source = {'components':[{'id':'b','type':'Divider','source':{'source':'Shared.kt','line':9}}]}
        manifest = {'unresolved':[{'page_component_id':'b','path':'style.control.active_color',
            'reason':'divider visual semantics require control.active_color'}]}
        issue = diagnose({}, manifest, source)['issues'][0]
        self.assertEqual(issue['occurrences'][0]['source']['line'], 9)

    def test_expanded_list_item_location_comes_from_emitted_version_json(self):
        version = {'artboard':{'layers':[{'id':'a__item2', 'migration':{
            'componentType':'Text', 'source':{'source':'Page.kt', 'line':76}}}]}}
        manifest = {'unresolved':[{'page_component_id':'a__item2',
            'path':'style.typography.font_family', 'reason':'font family AppFont has no verified registered asset'}]}
        issue = diagnose(manifest=manifest, version_page=version)['issues'][0]
        self.assertEqual(issue['occurrences'][0]['source']['line'], 76)
        self.assertEqual(issue['occurrences'][0]['component_type'], 'Text')

    def test_cycle_is_guard_evidence_not_proof_of_bad_android_code(self):
        issue = diagnose({'tasks':[self.task('recursive composable cycle')]})['issues'][0]
        self.assertEqual(issue['code'], 'component_expansion_cycle')
        self.assertFalse(issue['root_cause_confirmed'])

    def test_unknown_reason_is_not_guessed_or_discarded(self):
        issue = diagnose({'tasks':[self.task('new failure kind')]})['issues'][0]
        self.assertEqual(issue['code'], 'unclassified')
        self.assertFalse(issue['root_cause_confirmed'])
        self.assertIn('new failure kind', issue['reasons'])

    def test_unconsumed_fact_is_not_misreported_as_missing_style_value(self):
        task = self.task('page JSON fact was not consumed by the ArkUI emitter', '16', 'style.typography.font_size_sp')
        issue = diagnose({'tasks':[task]})['issues'][0]
        self.assertEqual(issue['code'], 'target_fact_not_consumed')
        self.assertEqual(issue['occurrences'][0]['path'], task['path'])

    def test_merged_paths_retain_each_component_property(self):
        first = self.task('page JSON fact was not consumed by the ArkUI emitter', '', 'structure.type')
        second = self.task(first['occurrences'][0]['reason'], '', 'structure.parent_id')
        second['occurrences'][0]['component_id'] = 'b'
        issue = diagnose({'tasks':[first, second]})['issues'][0]
        self.assertEqual([(o['component_id'], o['path']) for o in issue['occurrences']],
            [('a', 'structure.type'), ('b', 'structure.parent_id')])

    def test_fatal_dependency_failure_is_directly_explained(self):
        result = diagnose({}, failure={'stage':'source-page', 'error':'Kotlin PSI dependency missing: kotlin-compiler-embeddable:1.9.22'})
        self.assertEqual(result['issues'][0]['code'], 'psi_dependency_missing')
        self.assertTrue(result['issues'][0]['root_cause_confirmed'])

    def test_markdown_contains_action_and_component_not_only_counts(self):
        result = diagnose({'tasks':[self.task('state selection is unresolved')]})
        markdown = render_markdown(result)
        for text in ('Page.kt:12', 'arrayOf', 'page', '处理', '尚未确定'):
            self.assertIn(text, markdown)

    def test_empty_diagnostics_do_not_claim_visual_acceptance(self):
        result = diagnose({})
        self.assertEqual(result['issue_count'], 0)
        self.assertFalse(result['visual_cause_verified'])
