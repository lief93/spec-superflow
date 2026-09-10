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

    def test_dynamic_conditions_are_deferred_but_still_outstanding(self):
        task = self.task('state selection is unresolved; source template retained, not selected',
                         'currentPage == it', 'source.state_resolution')
        result = diagnose({'tasks': [task]})
        self.assertEqual(result['counts']['pending'], 0)
        self.assertEqual(result['counts']['deferred_dynamic'], 1)
        self.assertEqual(result['unresolved_count'], 1)
        markdown = render_markdown(result)
        self.assertIn('暂缓', markdown)
        self.assertIn('currentPage == it', markdown)
        self.assertIn('内容缺失', markdown)

    def test_other_component_states_do_not_merge_with_current_page(self):
        first = self.task('unresolved color', 'Theme.ink', 'style.typography.color')
        second = self.task('unresolved color', 'Theme.ink', 'style.typography.color')
        second['occurrences'][0]['component_ui_state'] = 'Button/pressed'
        result = diagnose({'tasks': [first, second]})
        self.assertEqual(result['counts']['pending'], 1)
        self.assertEqual(result['counts']['other_state'], 1)
        self.assertEqual(result['unresolved_count'], 2)
        self.assertIn('Button/pressed', render_markdown(result))

    def test_consumed_reference_retires_only_its_exact_component_property(self):
        task = self.task('unresolved color', 'Theme.ink', 'style.typography.color')
        version = {'artboard': {'layers': [{'id': 'a', 'migration': {'source': {
            'style_token_references': {'typography.color': {'android': 'Theme.ink',
                'kind': 'color', 'target': {'module': './Theme', 'export': 'Theme', 'member': 'ink'}}}}}}]}}
        manifest = {'target_phase_consumption_gate': {'checks': [
            {'component_id': 'a', 'path': 'style.typography.color', 'status': 'consumed'}]}}
        result = diagnose({'tasks': [task]}, manifest, version_page=version)
        self.assertEqual(result['counts']['resolved_reference'], 1)
        self.assertEqual(result['unresolved_count'], 0)
        manifest['target_phase_consumption_gate']['checks'][0]['component_id'] = 'another-instance'
        self.assertEqual(diagnose({'tasks': [task]}, manifest, version_page=version)['unresolved_count'], 1)
        manifest['target_phase_consumption_gate']['checks'][0]['component_id'] = 'a'
        manifest['unresolved'] = [{'page_component_id': 'a', 'path': 'style.typography.color',
                                   'reason': 'target expression could not be rendered'}]
        self.assertEqual(diagnose({'tasks': [task]}, manifest, version_page=version)['counts']['resolved_reference'], 0)

    def test_default_warning_is_not_lost_or_counted_twice(self):
        task = self.task('unresolved color', 'Theme.ink', 'style.typography.color')
        warning = {'kind': 'style_default_applied', 'component_id': 'a',
            'path': 'style.typography.color', 'expression': 'Theme.ink',
            'fallback': '#FF000000', 'reason': 'migration default used'}
        manifest = {'warnings': [warning], 'target_phase_consumption_gate': {'checks': [
            {'component_id': 'a', 'path': 'style.typography.color', 'status': 'consumed'}]}}
        for worklist in ({'tasks': [task]}, {}):
            result = diagnose(worklist, manifest)
            self.assertEqual(result['counts']['defaulted'], 1)
            self.assertEqual(result['unresolved_count'], 1)
            self.assertIn('#FF000000', render_markdown(result))

    def test_real_adapter_output_reconciles_historical_style_diagnostic(self):
        from test_keyed_resources import KeyedResourcesTest
        generator = KeyedResourcesTest()
        self.addCleanup(generator.doCleanups)
        page, code, _, renderer = generator.generate('Text("A", color = Palette.get("text.primary"))')
        node = next(n for n in page['components'] if n['type'] == 'Text')
        self.assertIn(".fontColor(StyleToken0.resolve('text.primary'))", code)
        task = self.task('unresolved color', 'Palette.get("text.primary")', 'style.typography.color')
        task['occurrences'][0]['component_id'] = node['id']
        manifest = {'unresolved': renderer.unresolved,
                    'target_phase_consumption_gate': renderer.test_phase_gate}
        report = diagnose({'tasks': [task]}, manifest, source_page=page)
        self.assertEqual(report['counts']['resolved_reference'], 1)
        self.assertEqual(report['unresolved_count'], 0)

    def test_reference_without_consumption_is_still_unresolved(self):
        task = self.task('unresolved color', 'Theme.ink', 'style.typography.color')
        source = {'components': [{'id': 'a', 'source': {'style_token_references': {
            'typography.color': {'android': 'Theme.ink', 'kind': 'color',
                'target': {'module': './Theme', 'export': 'Theme', 'member': 'ink'}}}}}]}
        report = diagnose({'tasks': [task]}, source_page=source)
        self.assertEqual(report['unresolved_count'], 1)
        self.assertIn('尚无最终 ArkUI manifest', render_markdown(report))
