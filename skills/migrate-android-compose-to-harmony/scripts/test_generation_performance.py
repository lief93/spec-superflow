import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ui_migration.frontend.resources import safe_asset_index, safe_asset_indexes
from ui_migration.frontend.unresolved_worklist import collect_unresolved


def reference_collect(components, initial):
    unresolved = list(initial)
    for component in components:
        for item in component.get('unresolved') or []:
            unresolved.append({'component_id': component['id'], **item})
        for item in component.get('required_facts') or []:
            if item['status'] in {'symbolic', 'unresolved'} and not any(
                existing['component_id'] == component['id']
                and existing.get('path') == item.get('path')
                and existing.get('expression') == item.get('expression')
                for existing in unresolved
            ):
                unresolved.append({'component_id': component['id'], **item})
    return unresolved


class GenerationPerformanceTest(unittest.TestCase):
    def test_asset_batch_hashes_once_and_preserves_scopes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = []
            sources = ['other/src/main/Page.kt', 'settings/src/main/Page.kt']
            for module, size in [('settings', 24), ('other', 48)]:
                relative = f'{module}/src/main/res/drawable/icon.xml'
                path = root / relative
                path.parent.mkdir(parents=True)
                path.write_text(f'<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="{size}dp" android:height="{size}dp"/>')
                assets.append({'path': relative, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
            (root / '.android-to-harmony-safe.json').write_text(json.dumps({
                'source_root': str(root), 'local_only_assets': assets}))
            expected = (safe_asset_index(root), {s: safe_asset_index(root, s) for s in sources})
            reads = []
            original = Path.read_bytes

            def read_bytes(path):
                reads.append(path)
                return original(path)

            with patch.object(Path, 'read_bytes', read_bytes):
                actual = safe_asset_indexes(root, iter(sources * 5))
            self.assertEqual(actual, expected)
            self.assertEqual(list(actual[1]), sources)
            self.assertEqual(len(reads), 2)
            self.assertNotIn('icon', actual[0])
            self.assertEqual(actual[1][sources[0]]['icon']['width_dp'], 48)
            (root / assets[0]['path']).write_text('<vector/>')
            refreshed = safe_asset_indexes(root, sources)
            self.assertNotIn('width_dp', refreshed[1][sources[1]]['icon'])

    def test_asset_scopes_do_not_share_mutable_evidence(self):
        from ui_migration.frontend.resources import _select_asset_candidates
        candidates = {'icon': [{'path': 'icon.xml', 'sha256': 'abc'}]}
        first = _select_asset_candidates(candidates, None)
        second = _select_asset_candidates(candidates, 'Page.kt')
        first['icon']['path'] = 'changed'
        self.assertEqual(second['icon']['path'], 'icon.xml')

    def test_empty_asset_input(self):
        self.assertEqual(safe_asset_indexes(None, ['Page.kt', 'Page.kt']), ({}, {'Page.kt': {}}))

    def test_unresolved_retains_order_duplicates_and_structured_expressions(self):
        initial = [{'component_id': 'a', 'path': 'x', 'expression': {'value': [1]}}]
        components = [
            {'id': 'a', 'unresolved': [{'path': 'z'}, {'path': 'z'}], 'required_facts': [
                {'path': 'x', 'expression': {'value': [1]}, 'status': 'unresolved'},
                {'path': 'z', 'status': 'symbolic'},
                {'path': 'ok', 'status': 'resolved'},
                {'path': 'new', 'expression': [1, 2], 'status': 'symbolic'}]},
            {'id': 'b', 'required_facts': [
                {'path': 'x', 'expression': {'value': [1]}, 'status': 'unresolved'},
                {'component_id': 'a', 'path': 'other', 'status': 'unresolved'}]},
            {'id': 'a', 'required_facts': [{'path': 'other', 'status': 'unresolved'}]},
        ]
        self.assertEqual(collect_unresolved(iter(components), initial), reference_collect(components, initial))
        self.assertEqual(len(initial), 1)

    def test_required_fact_lookup_does_not_scan_other_components(self):
        class ComponentId(str):
            comparisons = 0

            def __eq__(self, other):
                ComponentId.comparisons += 1
                return super().__eq__(other)

            __hash__ = str.__hash__

        components = [{'id': ComponentId(str(i)), 'required_facts': [
            {'path': 'color', 'expression': 'Theme.color', 'status': 'symbolic'}
        ]} for i in range(1000)]
        result = collect_unresolved(components, [])
        self.assertEqual(len(result), 1000)
        self.assertLess(ComponentId.comparisons, 1000)


if __name__ == '__main__':
    unittest.main()
