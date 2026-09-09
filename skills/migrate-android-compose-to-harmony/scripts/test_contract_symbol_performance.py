import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import analyze_compose_project as analyzer
from ui_migration.frontend.declaration_lookup import DeclarationLookup
from ui_migration.frontend.source_symbols import SourceSymbolIndex, resolve_functions


class ContractSymbolPerformanceTest(unittest.TestCase):
    def test_association_queries_do_not_scan_full_declarations(self):
        files = {f'F{i}.kt': f'package p{i}\n' + '\n'.join(
            f'@Composable fun C{i}_{j}() {{ Text("Value") }}' for j in range(3)) for i in range(30)}
        candidates = 0
        queries = 0

        def resolve(functions, name, **scope):
            nonlocal candidates, queries
            queries += 1
            candidates += len(functions.candidates(name, scope.get('imports', {}), scope.get('package'))
                              if isinstance(functions, DeclarationLookup) else functions)
            return resolve_functions(functions, name, **scope)

        with patch.object(analyzer, 'resolve_functions', side_effect=resolve):
            associations = analyzer.collect_composable_associations(files)
        self.assertEqual(len(associations['ui_functions']), 30)
        self.assertGreater(queries, 2000)
        self.assertLessEqual(candidates, queries, 'each name lookup scanned unrelated function declarations')
        self.assertEqual(associations['resolved']['F0.kt']['C0_0'], [{'source': 'F0.kt', 'composable': 'C0_0'}])

    def test_complete_contract_matches_linear_resolution(self):
        files = {
            'Page.kt': '''package app
import a.Card as Aliased
import a.*
import b.*
@Composable fun Page() { Column { Aliased(); Card(); Other(); Local(); a.Card() } }
@Composable fun Local() { Text("Local") }
''',
            'A.kt': 'package a\n@Composable fun Card() { Text("A") }\n'
                    '@Composable fun Card(value: Int) { Text("Overload") }',
            'B.kt': 'package b\n@Composable fun Card() { Text("B") }',
            'Other.kt': 'package app\n@Composable fun Other() { Text("Other") }',
            'src/test/Test.kt': 'package test\n@Composable fun Test() { Text("Test") }',
        }
        declarations = SourceSymbolIndex(files).functions
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            actual = analyzer.analyze(root, {}, files)
            with patch.object(analyzer, 'resolve_functions', side_effect=lambda _, name, **scope:
                              resolve_functions(declarations, name, **scope)):
                expected = analyzer.analyze(root, {}, files)
        self.assertEqual(actual, expected)


if __name__ == '__main__':
    unittest.main()
